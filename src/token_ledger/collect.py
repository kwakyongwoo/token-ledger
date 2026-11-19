"""Collect closed prompts for the current repo into a new, write-once chunk file."""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from . import transcripts

OUT_DIR = "token-ledger-out"


def git(*args: str, cwd: str | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


class Repo:
    def __init__(self, cwd: str | None = None):
        self.root = Path(git("rev-parse", "--show-toplevel", cwd=cwd))
        common = Path(git("rev-parse", "--git-common-dir", cwd=cwd))
        self.common = common if common.is_absolute() else (self.root / common).resolve()
        listing = git("worktree", "list", "--porcelain", cwd=cwd)
        self.worktrees = [Path(l[len("worktree "):]) for l in listing.splitlines() if l.startswith("worktree ")]
        self.main = self.worktrees[0] if self.worktrees else self.root
        try:
            self.member = git("config", "user.name", cwd=cwd) or "unknown"
        except subprocess.CalledProcessError:
            self.member = "unknown"

    @property
    def state_dir(self) -> Path:
        return self.common / "token-ledger"

    def worktree_of(self, path: str | None) -> Path | None:
        if not path:
            return None
        best = None
        for w in self.worktrees:
            if path == str(w) or path.startswith(str(w) + os.sep):
                if best is None or len(str(w)) > len(str(best)):
                    best = w
        return best

    def in_repo(self, path: str | None) -> bool:
        return self.worktree_of(path) is not None


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unknown"


def _load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def active_tag(tags: list[dict], ts: str) -> str | None:
    """Tag switched on most recently at or before ts (tags.jsonl rows: {"ts", "tag"}; tag null = off)."""
    tag = None
    for row in tags:
        if row.get("ts", "") <= ts:
            tag = row.get("tag")
    return tag


def to_row(p: transcripts.Prompt, repo: Repo, title: str | None, tag: str | None) -> dict:
    wt = repo.worktree_of(p.cwd)
    files = set()
    for f in p.files:
        owner = repo.worktree_of(f)
        if owner is not None:
            files.add(os.path.relpath(f, owner))
    models = {}
    total = 0.0
    for m, u in sorted(p.models.items()):
        models[m] = {k: getattr(u, k) for k in ("requests", "input", "output", "cache_write", "cache_read", "thinking")}
        models[m]["cost"] = None if u.cost is None else round(u.cost, 6)
        total = None if u.cost is None or total is None else total + u.cost
    duration = None
    try:
        duration = round((_ts(p.end_ts) - _ts(p.ts)), 1) if p.end_ts else None
    except ValueError:
        pass
    return {
        "v": 1,
        "id": p.id,
        "ts": p.ts,
        "member": repo.member,
        "session": p.session,
        "title": title,
        "branch": p.branch,
        "worktree": None if wt in (None, repo.main) else wt.name,
        "tag": tag,
        "models": models,
        "cost": None if total is None else round(total, 6),
        "duration_s": duration,
        "tools": p.tools,
        "subagents": p.subagents,
        "files": sorted(files),
    }


def _ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def collect(repo: Repo, idle_minutes: float = 30, now: float | None = None) -> tuple[list[dict], list[dict], dict]:
    """Return (rows, local_rows, new_state) without writing anything."""
    now = time.time() if now is None else now
    state = _load(repo.state_dir / "state.json", {"files": {}})
    tags = [json.loads(l) for l in _read_lines(repo.state_dir / "tags.jsonl")]
    rows, local = [], []
    files = state.setdefault("files", {})
    for path in sorted(transcripts.projects_dir().glob("*/*.jsonl")):
        key = str(path)
        entry = files.get(key, {})
        try:
            stat = path.stat()
        except OSError:
            continue
        offset = entry.get("offset", 0)
        if offset > stat.st_size:  # file was rewritten: start over
            offset = 0
        if offset == stat.st_size:
            continue
        idle = now - stat.st_mtime > idle_minutes * 60
        prompts, title, next_offset = transcripts.read_session(path, offset, repo.in_repo, closed_at_eof=idle)
        title = title or entry.get("title")
        for p in prompts:
            if not p.models:  # nothing in this repo
                continue
            rows.append(to_row(p, repo, title, active_tag(tags, p.ts)))
            local.append({"id": p.id, "excerpt": p.excerpt})
        files[key] = {"offset": next_offset, "title": title}
    return rows, local, state


def _read_lines(path: Path):
    try:
        return [l for l in path.read_text().splitlines() if l.strip()]
    except OSError:
        return []


def write(repo: Repo, rows: list[dict], local: list[dict], state: dict, stage: bool) -> Path | None:
    """Write rows to a new chunk file (never edited again) and save local state."""
    out = None
    if rows:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = repo.root / OUT_DIR / "data" / slug(repo.member) / f"{stamp}-{secrets.token_hex(3)}.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows))
        if stage:
            git("add", str(out), cwd=str(repo.root))
    repo.state_dir.mkdir(parents=True, exist_ok=True)
    if local:
        with open(repo.state_dir / "local.jsonl", "a") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in local)
    tmp = repo.state_dir / "state.json.tmp"
    tmp.write_text(json.dumps(state))
    tmp.replace(repo.state_dir / "state.json")
    return out


def read_all(root: Path) -> list[dict]:
    """Every shared row in the repo, deduplicated by prompt id."""
    seen = {}
    for f in sorted((root / OUT_DIR / "data").glob("*/*.jsonl")):
        for line in _read_lines(f):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            seen.setdefault(r.get("id"), r)
    return list(seen.values())
