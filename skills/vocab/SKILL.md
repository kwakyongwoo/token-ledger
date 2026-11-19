---
name: vocab
description: Review and tidy the shared work-unit vocabulary of token-ledger (merge duplicates, rename, clear NEW flags). Use when the user wants to merge, rename or clean up work unit names, or after a report flags new work units.
---

# vocab

- `token-ledger vocab list` shows names, aliases and NEW flags.
- `token-ledger vocab merge <from> <to>`: `<from>` becomes an alias of `<to>`; its prompts regroup under `<to>`.
- `token-ledger vocab rename <old> <new>`: the old name stays as an alias.
- `token-ledger vocab ok [name ...]`: clear NEW flags (all when no name is given).

Show the list first, propose merges for names that mean the same work, and run the commands the user agrees to. Changes go to `token-ledger-out/vocabulary.jsonl`, which is shared through git.
