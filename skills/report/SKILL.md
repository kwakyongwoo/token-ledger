---
name: report
description: Build and open the token-ledger HTML report (cost and tokens by work unit, tag, branch, worktree, model, day and member). Use when the user asks where tokens or money went, for a usage report, or to see the token ledger.
---

# report

1. `token-ledger collect` first, so this member's latest finished prompts are included (they are not committed by this step).
2. `token-ledger report` writes `token-ledger-out/report.html` and prints its path. Add `--no-classify` when the user asks not to spend tokens on naming work units, or when `token-ledger-out/config.json` has `"classify": false`.
3. Open the printed file for the user and summarize in a few lines: total cost, the three most expensive work units, and any work unit flagged NEW (offer `/token-ledger:vocab` to merge or rename).

The report shows prompt text only for this member's own prompts; other members show the session title.

New work unit names (`token-ledger-out/units/`, `vocabulary.jsonl`) and rows from a manual collect are staged by the pre-commit hook and ride along with the next commit that has other changes. To share them right away, commit them directly: `git add token-ledger-out && git commit -m "chore: token-ledger names"`.
