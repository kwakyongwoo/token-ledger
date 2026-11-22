# token-ledger

Write all docs, code comments and commit messages in English. Translated READMEs (`README.<lang>.md` at the repo root) mirror `README.md`; update them together.

## token-ledger

This repo records Claude Code token usage per prompt in `token-ledger-out/` (no prompt text; usage, branch, tag, session title and changed file paths). A pre-commit hook adds new rows to each commit.

- `/token-ledger:tag <name>` labels the following prompts with a tag; `/token-ledger:tag off` stops it.
- `/token-ledger:report` builds `token-ledger-out/report.html`.
- Do not edit files under `token-ledger-out/data/` by hand.
