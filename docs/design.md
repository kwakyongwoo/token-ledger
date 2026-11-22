# token-ledger design

Status: agreed 2026-11-20; v0.2.0 built. The `per_member` switch was dropped in 0.2.0.

## Goal

Show a team where Claude Code tokens go: per prompt, grouped by work unit, branch, worktree, model, member and tag, in an HTML report. Set up once per repo and shared through git.

Main question it answers: which work costs the most (to change habits). Secondary: which model fits which work.

## Shape (graphify column for reference only)

| | graphify | token-ledger |
|---|---|---|
| First setup | `/graphify .` | `/token-ledger:init` (one person, once) |
| In the repo | `graphify-out/` | `token-ledger-out/` |
| Auto update | git hook | `pre-commit` git hook |
| Claude wiring | `## graphify` in CLAUDE.md | `## token-ledger` in CLAUDE.md (tag usage) |
| Teammates | pull and read | pull and read; their usage is added on their commits |
| View | `graph.html` | `report.html` |
| Packaging | Python package + CLI via `uv tool install` | same |

## Data flow

1. **Source**: each member's local transcripts in `~/.claude/projects/*/*.jsonl` (already hold model, tokens, branch, cwd per response). No per-turn Claude hook.
2. **Collect** (`pre-commit`): read prompts since the last collected point for this repo, dedupe responses by `requestId`, fold subagent transcripts into their parent prompt, write the rows to a new chunk file, and stage it in the same commit. Only closed prompts are collected (a later prompt exists; or the session file and its subagents have been idle 30 minutes and the last response ended the turn with `end_turn`; or they have been idle 24 hours): the prompt that runs `git commit` is usually still running, so it waits for the next commit.
3. **Cluster + name** (`report`): build a prompt graph, cluster it, name clusters, render `report.html`.

### Prompt unit

One user message until the next one, including tool calls and subagents. Injected (`isMeta`) and tool-result lines are not prompts.

## Files

```
token-ledger-out/                 committed, shared
├── data/<member>/<time>-<rand>.jsonl  one row per prompt; a new file per collect, never edited (no merge conflicts); readers dedupe by prompt id
├── units/<member>/<time>-<rand>.jsonl  {id, unit} assignments, write-once; the first assignment of a prompt wins
├── vocabulary.jsonl              one work unit name per line (aliases, NEW flag), sorted so edits merge cleanly
├── config.json                   {"classify": true}
└── report.html                   gitignored, built locally
.git/token-ledger/                local only, never tracked
├── state.json                    last collected point
├── tags.jsonl                    tag on/off intervals (copied into rows at collect time)
└── local.jsonl                   prompt excerpts (first 80 chars), for the member's own report only
```

`.gitattributes`: `token-ledger-out/data/**` and `token-ledger-out/units/**` are `linguist-generated`, so PR diffs collapse them.

### Shared row (no prompt text)

time, member (git `user.name`, no email), session id, session title, branch, worktree name, tag, models (per model split), input / output / cache write / cache read / thinking tokens, cost, duration, tool count, subagent count, changed files (repo-relative paths only).

## Work units

Clustering is automatic and always on. Tags are separate: a human label, never an input to clustering.

- **Edges between prompts**: same changed file (strong), adjacent in the same session (medium), same branch (weak).
- **Algorithm**: networkx Louvain (required); graspologic Leiden when installed.
- **Naming**: Haiku (`claude -p --model haiku`) names a cluster in 2-5 words from shared fields only (paths, branch, session title, tag), picking an existing vocabulary name first. Prompts with no changed files may use the local excerpt, so only the author's machine labels those.
- **Stability**: a prompt keeps its first unit. A new cluster that contains already-named prompts takes their most common name; only clusters with no named prompt are sent to the model, in one batched call.
- **Classify off** (`config.json` or `report --no-classify`): names come from the cluster's hub file, no model.

### Vocabulary

Flat (one level). New names are added automatically and flagged `new` in the report.

- `vocab merge <from> <to>`: `<from>` becomes an alias; its rows regroup under `<to>`.
- `vocab rename <old> <new>`: old name stays as an alias.
- `vocab ok`: clear `new` flags.

## Tags

`/token-ledger:tag <name>` sticks to following prompts in this repo (all its worktrees) until `/token-ledger:tag off`. Names are normalized (lowercase, hyphens, dots kept) and close existing tags are suggested. Tags never feed clustering.

## Report

Self-contained HTML, no server.

- Filters: period (days in the data), member, branch, worktree, tag, work unit, model.
- Group by (mode switch): work unit, tag, session, branch, worktree, model, day, member.
- Prompt list sorted by cost. Own prompts show excerpts; others do not.
- Cost at API list prices, price table dated in the report.

## Teammate setup

Teammates install the plugin themselves (listing it in the repo's `.claude/settings.json` is a later option; `init` does not write it). On session start the plugin offers to install the CLI from its own folder when it is missing; once the CLI is there, it installs the git hook when `token-ledger-out/` exists, inserting its lines right after the shebang of an existing shell hook (non-shell hooks and tracked hook folders are left alone with a manual line to add), and says so in one line. `token-ledger hook uninstall` opts the member out.

## Constraints and risks

- Prompt text never leaves the member's machine.
- Transcript format is undocumented; the reader must skip unknown lines and fields instead of failing.
- Per-member stats can be personal data: tell the team before enabling.
- Prompts never followed by a commit stay out of team stats until the member's next commit in the repo.
- Changed files come from Edit/Write tool calls only; edits made through Bash (sed, heredocs) are not seen, so file links are sparser than the real work.
- Rows are attributed by each response's `cwd`, so a session that moves between repos splits correctly.
- Licenses: own code MIT; networkx BSD-3; graspologic optional. No code is copied from other projects; if any is, add its license notice.
- Do not present the plugin as affiliated with graphify or Anthropic. The README describes our own features only.
- The repo is private for now; teammates need access until it is made public.
