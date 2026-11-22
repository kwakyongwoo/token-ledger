"""token-ledger command line."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict

from . import collect as c


def cmd_collect(args) -> int:
    from . import install
    repo = c.Repo()
    if args.stage and not install.has_ledger(repo):  # hook in a repo without token-ledger: do nothing
        return 0
    rows, local, state = c.collect(repo, idle_minutes=args.idle_minutes)
    if args.dry_run:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False, sort_keys=True))
        print(f"{len(rows)} prompts (dry run, nothing written)", file=sys.stderr)
        return 0
    out = c.write(repo, rows, local, state, stage=args.stage)
    if args.quiet and not rows:
        return 0
    print(f"token-ledger: {len(rows)} prompts" + (f" -> {out.relative_to(repo.root)}" if out else ""), file=sys.stderr)
    return 0


def cmd_summary(args) -> int:
    rows = c.read_all(c.Repo().root)
    by = defaultdict(lambda: [0, 0.0, 0, 0, 0])  # prompts, cost, output, input, prompts without a price
    g = lambda u, k: u.get(k) or 0
    for r in rows:
        parts = r["models"].items() if args.by == "model" else [(r.get(args.by) or "-", None)]
        for key, u in parts:
            b = by[key]
            b[0] += 1
            cost = r.get("cost") if u is None else u.get("cost")
            if cost is None:
                b[4] += 1
            else:
                b[1] += cost
            for x in ([u] if u is not None else r["models"].values()):
                b[2] += g(x, "output"); b[3] += g(x, "input") + g(x, "cache_read") + g(x, "cache_write")
    print(f"{args.by:<40} {'prompts':>7} {'cost $':>10} {'out':>10} {'in(all)':>12}")
    for k, (n, cost, out, inp, unknown) in sorted(by.items(), key=lambda kv: -kv[1][1]):
        print(f"{str(k)[:40]:<40} {n:>7} {cost:>9.2f}{'+' if unknown else ' '} {out:>10} {inp:>12}")
    if any(b[4] for b in by.values()):
        print("+ some prompts use a model without a known price; their cost is not included", file=sys.stderr)
    return 0


def cmd_report(args) -> int:
    from pathlib import Path
    from . import report, vocab
    repo = c.Repo()
    out_dir = repo.root / c.OUT_DIR
    excerpts = {}
    for line in c._read_lines(repo.state_dir / "local.jsonl"):  # this member's own prompts only
        try:
            r = json.loads(line)
            excerpts[r["id"]] = r["excerpt"]
        except (ValueError, KeyError):
            continue
    rows = c.read_all(repo.root)
    try:
        from . import cluster
        cfg = json.loads((out_dir / "config.json").read_text()) if (out_dir / "config.json").exists() else {}
        classify = cfg.get("classify", True) and not args.no_classify
        v = vocab.Vocabulary(out_dir)
        assigned = vocab.read_assignments(out_dir)
        pairs, created = cluster.assign(rows, assigned, v, excerpts, classify)
        if pairs:
            vocab.write_assignments(out_dir, c.slug(repo.member), pairs)
            v.save()
            print(f"work units: {len(pairs)} prompts assigned" + (f", new: {', '.join(created)}" if created else ""),
                  file=sys.stderr)
    except ImportError:
        print("work units skipped: networkx is not installed (uv tool install brings it)", file=sys.stderr)
    units, new = report.load_units(out_dir)
    left = sum(1 for r in rows if r["id"] not in units)
    if left:
        print(f"{left} prompts are not grouped yet (naming call failed or skipped); the next report retries",
              file=sys.stderr)
    out = Path(args.out) if args.out else out_dir / "report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.build(rows, units, new, excerpts, repo.main.name))
    print(out)
    return 0


def cmd_vocab(args) -> int:
    from . import vocab
    out_dir = c.Repo().root / c.OUT_DIR
    v = vocab.Vocabulary(out_dir)
    if args.action == "list":
        for n, e in sorted(v.entries.items()):
            print(n + (" [NEW]" if e.get("new") else "") + (f"  aliases: {', '.join(e['aliases'])}" if e.get("aliases") else ""))
        return 0
    if args.action in ("merge", "rename") and len(args.names) != 2:
        print(f"usage: token-ledger vocab {args.action} <from> <to>", file=sys.stderr)
        return 2
    msg = {"merge": lambda: v.merge(*args.names), "rename": lambda: v.rename(*args.names),
           "ok": lambda: v.ok(args.names)}[args.action]()
    v.save()
    print(msg)
    return 0


def cmd_tag(args) -> int:
    from datetime import datetime, timezone
    import re
    repo = c.Repo()
    path = repo.state_dir / "tags.jsonl"
    history = []
    for line in c._read_lines(path):
        try:
            h = json.loads(line)
        except ValueError:
            continue
        if isinstance(h, dict):
            history.append(h)
    current = history[-1].get("tag") if history else None
    if args.name is None:
        print(f"current tag: {current or '(none)'}")
        return 0
    tag = None if args.name.lower() == "off" else re.sub(r"[^a-z0-9.]+", "-", args.name.lower()).strip("-.")[:40]
    if args.name.lower() != "off" and not tag:
        print("tag name needs letters or digits", file=sys.stderr)
        return 2
    known = {h["tag"] for h in history if h.get("tag")} | {r.get("tag") for r in c.read_all(repo.root) if r.get("tag")}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps({"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "tag": tag}) + "\n")
    print(f"tag: {tag}" if tag else "tag off")
    words = set((tag or "").split("-"))
    close = sorted(t for t in known if t != tag and words & set(t.split("-")))
    if close:
        print(f"similar existing tags: {', '.join(close)}")
    return 0


def cmd_init(args) -> int:
    from . import install
    for line in install.init(c.Repo()):
        print(line)
    return 0


def cmd_hook(args) -> int:
    from . import install
    repo = c.Repo()
    if args.action == "install":
        ok, msg = install.install_hook(repo)
        print(msg)
        return 0 if ok else 1
    if args.action == "uninstall":
        print(install.uninstall_hook(repo))
        return 0
    print(install.hook_state(repo))
    return 0


def main(argv=None) -> int:
    from . import __version__
    ap = argparse.ArgumentParser(prog="token-ledger")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("collect", help="add closed prompts since the last run to a new chunk file")
    p.add_argument("--stage", action="store_true", help="git add this member's chunks, unit assignments and the vocabulary (used by the pre-commit hook)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--quiet", action="store_true", help="print nothing when there is nothing new")
    p.add_argument("--idle-minutes", type=float, default=30, help="treat a session's last prompt as closed after this")
    p.set_defaults(func=cmd_collect)
    p = sub.add_parser("summary", help="print totals from the shared data")
    p.add_argument("--by", default="session", choices=["session", "title", "branch", "member", "model", "tag", "worktree"])
    p.set_defaults(func=cmd_summary)
    p = sub.add_parser("report", help="group new prompts into work units and write the HTML report")
    p.add_argument("--out", help="default: token-ledger-out/report.html")
    p.add_argument("--no-classify", action="store_true", help="name new work units from files instead of a model")
    p.set_defaults(func=cmd_report)
    p = sub.add_parser("tag", help="tag the following prompts in this repo (off to stop, no name to show)")
    p.add_argument("name", nargs="?")
    p.set_defaults(func=cmd_tag)
    p = sub.add_parser("vocab", help="list, merge, rename work unit names or clear NEW flags")
    p.add_argument("action", choices=["list", "merge", "rename", "ok"])
    p.add_argument("names", nargs="*")
    p.set_defaults(func=cmd_vocab)
    p = sub.add_parser("init", help="set up token-ledger in this repo and install the pre-commit hook")
    p.set_defaults(func=cmd_init)
    p = sub.add_parser("hook", help="install, remove or check the pre-commit hook")
    p.add_argument("action", choices=["install", "uninstall", "status"])
    p.set_defaults(func=cmd_hook)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
