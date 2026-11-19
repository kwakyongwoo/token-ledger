---
name: tag
description: Label the following prompts in this repo with a tag (a human label such as a release or experiment, separate from automatic work units), or turn the tag off. Use when the user says tag, label or "/token-ledger:tag".
---

# tag

- `token-ledger tag <name>` starts a tag; it applies to every following prompt in this repo until changed.
- `token-ledger tag off` stops tagging. `token-ledger tag` with no name shows the current tag.

The CLI normalizes the name (lowercase, hyphens, dots kept) and records it right away. If it prints similar existing tags, tell the user; if they meant one of those, run `token-ledger tag <that name>` (the later switch wins for following prompts).
