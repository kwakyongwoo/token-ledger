# Data format

Everything token-ledger commits lives in `token-ledger-out/`. This page describes format version 1. The design rationale is in [design.md](design.md).

## Compatibility rules

- Chunk files in `data/` and `units/` are write-once. A newer version never rewrites old chunks. It reads them and upgrades them in memory.
- Adding an optional field does not change the version.
  - Readers must ignore fields they don't know.
  - Readers must treat a missing optional field as absent.
- Removing or renaming a field, or changing its meaning, raises the row version `v`.
- A reader skips rows whose `v` is newer than it knows, and warns: "update the CLI". It never guesses. This holds from 0.1.1; 0.1.0 counted such rows as if they were v1.
- The commands and flags in the README's Commands table are the stable CLI. Within a major version they will not be removed or change meaning.

## `data/<member>/<UTC time>-<hex>.jsonl`

One JSON object per line, one line per finished prompt. `<member>` is a slug of `git config user.name`. A prompt id that appears in more than one file is counted once: files are read in name order and the first row wins.

| Field | Type | Since | Meaning |
|---|---|---|---|
| `v` | int | 0.1.0 | Row format version, currently `1` |
| `id` | string | 0.1.0 | Prompt id from the transcript (`promptId`, else `uuid`) |
| `ts` | string | 0.1.0 | When the prompt was sent, ISO 8601 UTC |
| `member` | string | 0.1.0 | `git config user.name` |
| `session` | string | 0.1.0 | Claude Code session id |
| `title` | string or null | 0.1.0 | Session title |
| `branch` | string or null | 0.1.0 | Git branch at the first response |
| `worktree` | string or null | 0.1.0 | Worktree folder name, null for the main checkout |
| `tag` | string or null | 0.1.0 | Tag active when the prompt was sent |
| `models` | object | 0.1.0 | Totals per model key, see below |
| `cost` | number or null | 0.1.0 | Sum of the per-model costs. Null if any model had no known price |
| `duration_s` | number or null | 0.1.0 | Wall-clock seconds in 0.1.x. **Since 0.2.0, working time:** sum of gaps of 5 minutes or less between transcript lines |
| `tools` | int | 0.1.0 | Tool calls, including subagents |
| `subagents` | int | 0.1.0 | Subagents started, counted recursively |
| `files` | string[] | 0.1.0 | Repo-relative paths edited with Edit, Write, MultiEdit or NotebookEdit |
| `cc` | string or null | 0.2.0 | Claude Code version that wrote the transcript |

### `models`

Keys are model ids as Claude Code wrote them. Since 0.2.0, fast-mode requests are kept under `"<model> (fast)"`.

| Field | Since | Meaning |
|---|---|---|
| `requests` | 0.1.0 | API responses, each counted once by `requestId` |
| `input`, `output`, `cache_read` | 0.1.0 | Token totals |
| `cache_write` | 0.1.0 | All cache-write tokens |
| `cache_write_1h` | 0.2.0 | Part of `cache_write` with the 1-hour TTL |
| `thinking` | 0.1.0 | Part of `output`, for display only |
| `cost` | 0.1.0 | USD at the API list prices of `pricing.py`. Null if the model had no price |

A row written with a null cost gets a cost when it is read, if the reading version knows the model's price. Rows from 0.1.x lack `cache_write_1h` and the fast key, so such repriced costs can be low.

## `units/<member>/<UTC time>-<hex>.jsonl`

`{"id": "<prompt id>", "unit": "<work unit name>"}` per line. This is write-once, like `data/`. The first assignment of a prompt wins, in file-name order across all members.

## `vocabulary.jsonl`

One work unit per line, sorted by name:

```json
{"added": "2026-11-19", "aliases": ["old-name"], "name": "report-filters", "new": true}
```

A unit name, or a name listed in `aliases`, resolves to `name`. Merging and renaming only change this file. Assignments are resolved through it at read time. `new` stays true until someone runs `token-ledger vocab ok` or renames the unit. A destination created by `vocab merge` starts with `new` false.

## `config.json`

| Key | Default | Meaning |
|---|---|---|
| `classify` | `true` | Name new work units with Claude Haiku |

Unknown keys are ignored. `per_member`, written by 0.1.x, has no effect.

## Local only (never committed)

These files live in `.git/token-ledger/` and are shared by all worktrees of the repo:

| File | Contents |
|---|---|
| `state.json` | Read offset per transcript, known worktrees |
| `local.jsonl` | Short prompt excerpts for this member's report |
| `tags.jsonl` | Tag history: `{"ts", "tag", "branch"}` per switch. Since 0.3.0 a tag applies only to prompts on its `branch`; rows without one apply everywhere |
| `hook-disabled` | Present if this member opted out |
