"""token-ledger command line."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict

from . import collect as c


def cmd_collect(args) -> int:
    repo = c.Repo()
    rows, local, state = c.collect(repo, idle_minutes=args.idle_minutes)
    if args.dry_run:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False, sort_keys=True))
        print(f"{len(rows)} prompts (dry run, nothing written)", file=sys.stderr)
        return 0
    out = c.write(repo, rows, local, state, stage=args.stage)
    print(f"token-ledger: {len(rows)} prompts" + (f" -> {out.relative_to(repo.root)}" if out else ""), file=sys.stderr)
    return 0


def cmd_summary(args) -> int:
    rows = c.read_all(c.Repo().root)
    by = defaultdict(lambda: [0, 0.0, 0, 0])
    for r in rows:
        key = r.get(args.by) or "-"
        if args.by == "model":
            for m, u in r["models"].items():
                b = by[m]
                b[0] += 1; b[1] += u["cost"] or 0; b[2] += u["output"]; b[3] += u["input"] + u["cache_read"] + u["cache_write"]
            continue
        b = by[key]
        b[0] += 1; b[1] += r["cost"] or 0
        for u in r["models"].values():
            b[2] += u["output"]; b[3] += u["input"] + u["cache_read"] + u["cache_write"]
    print(f"{args.by:<40} {'prompts':>7} {'cost $':>9} {'out':>10} {'in(all)':>12}")
    for k, (n, cost, out, inp) in sorted(by.items(), key=lambda kv: -kv[1][1]):
        print(f"{str(k)[:40]:<40} {n:>7} {cost:>9.2f} {out:>10} {inp:>12}")
    return 0


def cmd_report(args) -> int:
    from pathlib import Path
    from . import report
    repo = c.Repo()
    out_dir = repo.root / c.OUT_DIR
    units, new = report.load_units(out_dir)
    excerpts = {}
    for line in c._read_lines(repo.state_dir / "local.jsonl"):  # this member's own prompts only
        try:
            r = json.loads(line)
            excerpts[r["id"]] = r["excerpt"]
        except (ValueError, KeyError):
            continue
    out = Path(args.out) if args.out else out_dir / "report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.build(c.read_all(repo.root), units, new, excerpts, repo.main.name))
    print(out)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="token-ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("collect", help="add closed prompts since the last run to a new chunk file")
    p.add_argument("--stage", action="store_true", help="git add the new chunk (used by the pre-commit hook)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--idle-minutes", type=float, default=30, help="treat a session's last prompt as closed after this")
    p.set_defaults(func=cmd_collect)
    p = sub.add_parser("summary", help="print totals from the shared data")
    p.add_argument("--by", default="session", choices=["session", "title", "branch", "member", "model", "tag", "worktree"])
    p.set_defaults(func=cmd_summary)
    p = sub.add_parser("report", help="write a self-contained HTML report")
    p.add_argument("--out", help="default: token-ledger-out/report.html")
    p.set_defaults(func=cmd_report)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
