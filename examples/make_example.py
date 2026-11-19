"""Generate the fictional example in examples/: shared data, work units, vocabulary and report.html.

Everything here is made up (people, prompts, numbers). Run: python3 examples/make_example.py
"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
from token_ledger import report, vocab  # noqa: E402
from token_ledger.pricing import request_cost  # noqa: E402

OUT = HERE / "token-ledger-out"
VIEWER = "Alex Kim"  # the report is rendered as this member, so only their excerpts show
MEMBERS = ["Alex Kim", "Sam Lee", "Jordan Park"]
UNITS = {  # unit: (branch, files, sample prompts)
    "report-filters": ("feat/report-filters", ["src/report/filters.ts", "src/report/table.ts"],
                       ["add a date range filter to the report", "group rows by branch when the toggle is on",
                        "the model filter drops mixed prompts, fix it"]),
    "price-table": ("feat/price-table", ["src/pricing.py", "tests/test_pricing.py"],
                    ["update prices for the new models", "split cache writes into 5m and 1h"]),
    "hook-install": ("fix/hook-install", ["scripts/install-hook.sh", "src/hooks.py"],
                     ["pre-commit hook overwrites husky, append instead", "make the hook fail open"]),
    "vocab-command": ("feat/vocab", ["src/vocab.py"], ["add vocab merge and rename commands"]),
    "onboarding-docs": ("main", ["README.md", "docs/setup.md"], ["rewrite the setup section for teammates"]),
}
NEW = {"vocab-command"}
MODELS = [("claude-opus-5-5", 0.7), ("claude-sonnet-5-5", 0.25), ("claude-haiku-5-5", 0.05)]


def usage(rng, scale):
    return {"input_tokens": rng.randint(5, 400), "output_tokens": int(rng.randint(800, 9000) * scale),
            "cache_read_input_tokens": int(rng.randint(80_000, 900_000) * scale),
            "cache_creation_input_tokens": int(rng.randint(2_000, 40_000) * scale),
            "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": int(rng.randint(2_000, 40_000) * scale)},
            "output_tokens_details": {"thinking_tokens": int(rng.randint(100, 3000) * scale)}}


def main():
    rng = random.Random(7)
    rows, excerpts, units = [], {}, {u: {"prompts": []} for u in UNITS}
    for i in range(140):
        unit = rng.choices(list(UNITS), weights=[5, 3, 3, 1, 2])[0]
        branch, files, texts = UNITS[unit]
        member = rng.choice(MEMBERS)
        day, hour, minute = 10 + i // 14, rng.randint(9, 19), rng.randint(0, 59)
        ts = f"2026-11-{day:02d}T{hour:02d}:{minute:02d}:00Z"
        models = {}
        for m, w in MODELS:
            if rng.random() < w or not models and m == MODELS[-1][0]:
                n = rng.randint(1, 12) if m != "claude-haiku-5-5" else rng.randint(1, 3)
                agg = {"requests": n, "input": 0, "output": 0, "cache_write": 0, "cache_read": 0, "thinking": 0, "cost": 0.0}
                for _ in range(n):
                    u = usage(rng, 0.15 if m == "claude-haiku-5-5" else 1)
                    agg["input"] += u["input_tokens"]; agg["output"] += u["output_tokens"]
                    agg["cache_write"] += u["cache_creation_input_tokens"]; agg["cache_read"] += u["cache_read_input_tokens"]
                    agg["thinking"] += u["output_tokens_details"]["thinking_tokens"]; agg["cost"] += request_cost(m, u)
                agg["cost"] = round(agg["cost"], 6)
                models[m] = agg
        pid = f"ex-{i:03d}"
        rows.append({"v": 1, "id": pid, "ts": ts, "member": member, "session": f"sess-{i // 6:02d}",
                     "title": unit.replace("-", " ").capitalize(), "branch": branch,
                     "worktree": "wt-" + branch.split("/")[-1] if branch != "main" and rng.random() < 0.3 else None,
                     "tag": "release-0.2" if day >= 17 and unit != "onboarding-docs" else None,
                     "models": models, "cost": round(sum(v["cost"] for v in models.values()), 6),
                     "duration_s": rng.randint(20, 900), "tools": rng.randint(0, 40),
                     "subagents": rng.randint(0, 2), "files": rng.sample(files, rng.randint(0, len(files)))})
        units[unit]["prompts"].append(pid)
        if member == VIEWER:
            excerpts[pid] = rng.choice(texts)

    by_id = {r["id"]: r for r in rows}
    for f in OUT.glob("data/*/*.jsonl"):
        f.unlink()
    for m in MEMBERS:  # one chunk per member and day, as collect would write them
        for day in sorted({r["ts"][:10] for r in rows if r["member"] == m}):
            chunk = [r for r in rows if r["member"] == m and r["ts"][:10] == day]
            path = OUT / "data" / m.lower().replace(" ", "-") / f"{day.replace('-', '')}T200000Z-example.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in chunk))
    for old in [OUT / "work-units.json", OUT / "vocabulary.json", *OUT.glob("units/*/*.jsonl")]:
        old.unlink(missing_ok=True)
    for m in MEMBERS:  # as if each member's report run assigned units to the prompts it found
        mine = {pid: u for u, d in units.items() for pid in d["prompts"] if by_id[pid]["member"] == m}
        path = OUT / "units" / m.lower().replace(" ", "-") / "20261119T200000Z-example.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps({"id": i, "unit": u}) + "\n" for i, u in sorted(mine.items())))
    v = vocab.Vocabulary(OUT)
    for u in UNITS:
        v.entries[u] = {"name": u, "aliases": [], "added": "2026-11-10", "new": u in NEW}
    v.entries["report-filters"]["aliases"] = ["report-filter-ui"]
    v.save()
    ids, new = report.load_units(OUT)
    (HERE / "report.html").write_text(report.build(rows, ids, new, excerpts, "example-repo"))
    print(f"{len(rows)} prompts, ${sum(r['cost'] for r in rows):.2f} -> {HERE / 'report.html'}")


if __name__ == "__main__":
    main()
