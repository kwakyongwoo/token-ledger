"""Group prompts into work units: link prompts, cluster the graph, name only clusters without a name yet."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import PurePosixPath

from .vocab import Vocabulary, normalize

W_FILE, W_SESSION, W_BRANCH = 1.0, 0.6, 0.2  # see docs/design.md: Work units
DEFAULT_BRANCHES = {None, "", "HEAD", "main", "master", "develop"}
LINK_BACK = 3  # link each prompt to the previous few sharing a key, instead of every pair


def build_graph(rows: list[dict]):
    import networkx as nx

    g = nx.Graph()
    rows = sorted(rows, key=lambda r: r["ts"])
    for r in rows:
        g.add_node(r["id"])

    def link(groups: dict, weight: float):
        for ids in groups.values():
            for i, a in enumerate(ids):
                for b in ids[max(0, i - LINK_BACK):i]:
                    w = g[a][b]["weight"] + weight if g.has_edge(a, b) else weight
                    g.add_edge(a, b, weight=w)

    by_file, by_session, by_branch = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in rows:
        for f in r.get("files", []):
            by_file[f].append(r["id"])
        by_session[r.get("session")].append(r["id"])
        if r.get("branch") not in DEFAULT_BRANCHES:
            by_branch[r["branch"]].append(r["id"])
    link(by_file, W_FILE)
    # only the directly previous prompt of the same session
    for ids in by_session.values():
        for a, b in zip(ids, ids[1:]):
            g.add_edge(a, b, weight=(g[a][b]["weight"] if g.has_edge(a, b) else 0) + W_SESSION)
    link(by_branch, W_BRANCH)
    return g


def communities(g) -> list[set]:
    """Leiden when graspologic is installed, otherwise networkx Louvain (fixed seed: same input, same groups)."""
    try:
        from graspologic.partition import leiden  # optional, heavy

        part = leiden(g, random_seed=42)
        groups = defaultdict(set)
        for node, cid in part.items():
            groups[cid].add(node)
        found = list(groups.values())
        covered = set().union(*found) if found else set()
        return found + [{n} for n in g.nodes if n not in covered]
    except Exception:  # not installed, or it failed on this graph
        import networkx as nx

        return [set(c) for c in nx.algorithms.community.louvain_communities(g, weight="weight", seed=42)]


def fallback_name(rows: list[dict]) -> str:
    """Model-free name: the most edited file's stem, else the branch, else the session title."""
    files = Counter(PurePosixPath(f).stem for r in rows for f in r.get("files", []))
    if files:
        return normalize(files.most_common(1)[0][0]) or "misc"
    branches = Counter(r["branch"] for r in rows if r.get("branch") not in DEFAULT_BRANCHES)
    if branches:
        return normalize(branches.most_common(1)[0][0].split("/")[-1]) or "misc"
    titles = Counter(r.get("title") for r in rows if r.get("title"))
    return normalize(titles.most_common(1)[0][0]) if titles else "misc"


def describe(rows: list[dict], excerpts: dict) -> dict:
    """What the model may see about a cluster: shared fields, plus own excerpts only when no file was changed."""
    files = Counter(f for r in rows for f in r.get("files", []))
    d = {
        "prompts": len(rows),
        "files": [f for f, _ in files.most_common(8)],
        "branches": sorted({r["branch"] for r in rows if r.get("branch") not in DEFAULT_BRANCHES})[:4],
        "session_titles": sorted({r["title"] for r in rows if r.get("title")})[:5],
        "tags": sorted({r["tag"] for r in rows if r.get("tag")})[:3],
    }
    if not files:
        d["prompt_excerpts"] = [excerpts[r["id"]] for r in rows if r["id"] in excerpts][:5]
    return d


def name_with_model(clusters: list[dict], existing: list[str], model: str = "haiku", timeout: int = 180) -> list[str] | None:
    """One `claude -p` call naming every cluster. None when the CLI is missing or the answer is unusable."""
    if not clusters or not shutil.which("claude"):
        return None
    prompt = (
        "You name work units in a software project's token usage report. Each cluster below is a group of "
        "Claude Code prompts that touched the same files or followed each other. Give each cluster a work unit "
        "name: 2-5 English words, lowercase, joined by hyphens (e.g. report-filters, price-table). Reuse an "
        "existing name when it fits the same work; only invent a new one when none fits.\n\n"
        f"Existing names: {json.dumps(existing)}\n\nClusters:\n{json.dumps(clusters, ensure_ascii=False, indent=1)}\n\n"
        f"Answer with only a JSON array of {len(clusters)} strings, one name per cluster, in order."
    )
    try:
        out = subprocess.run(["claude", "-p", "--model", model, prompt], capture_output=True, text=True,
                             timeout=timeout, cwd=tempfile.gettempdir())  # outside the repo: not collected as a prompt
        text = out.stdout.strip()
        names = json.loads(text[text.index("["): text.rindex("]") + 1])
    except (subprocess.SubprocessError, ValueError, OSError):
        return None
    if not isinstance(names, list) or len(names) != len(clusters):
        return None
    return [normalize(str(n)) or "misc" for n in names]


def assign(rows: list[dict], assigned: dict, vocab: Vocabulary, excerpts: dict, classify: bool,
           namer=name_with_model) -> tuple[dict, list[str]]:
    """New {prompt id: unit} for prompts without a unit, and the names created this run.

    A cluster that already holds named prompts takes their most common name; only clusters with no
    named prompt are named (by the model when classify is on, otherwise from their files/branch).
    """
    if not rows:
        return {}, []
    groups = communities(build_graph(rows))
    by_id = {r["id"]: r for r in rows}
    new_pairs, to_name = {}, []
    for members in groups:
        todo = [i for i in members if i not in assigned]
        if not todo:
            continue
        known = Counter(vocab.resolve(assigned[i]) for i in members if i in assigned)
        if known:
            unit = known.most_common(1)[0][0]
            new_pairs.update({i: unit for i in todo})
        else:
            to_name.append(sorted(members))
    names = None
    if to_name and classify and shutil.which("claude"):
        names = namer([describe([by_id[i] for i in m], excerpts) for m in to_name], sorted(vocab.entries))
        if names is None:  # the call failed: retry next time instead of fixing fallback names forever
            return new_pairs, []
    created = []
    for k, members in enumerate(to_name):
        raw = names[k] if names else fallback_name([by_id[i] for i in members])
        unit = vocab.resolve(normalize(raw) or "misc")
        if unit not in vocab.entries:
            vocab.add(unit)
            created.append(unit)
        new_pairs.update({i: unit for i in members})
    return new_pairs, created
