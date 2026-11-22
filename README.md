<h1 align="center">token-ledger</h1>

<p align="center">
  <em>Where did the team's Claude Code tokens go? Find out per prompt, per feature and per branch.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.1.1-111111?style=flat-square" alt="Version 0.1.1">
  <img src="https://img.shields.io/badge/Claude%20Code-plugin-111111?style=flat-square" alt="Claude Code plugin">
  <img src="https://img.shields.io/badge/python-3.9%2B-111111?style=flat-square" alt="Python 3.9+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-111111?style=flat-square" alt="MIT license"></a>
</p>

<p align="center">
  <b>English</b> · <a href="README.ko.md">한국어</a>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="examples/screenshot-dark.jpg">
    <img src="examples/screenshot-light.jpg" alt="token-ledger report: cost by work unit, with filters" width="820">
  </picture>
</p>

token-ledger records the token usage of every Claude Code prompt in a git repo, for everyone on the team. It shares that record through git, so every member sees the same numbers. Then it groups the prompts into work units, like `report-filters` or `pricing-fix`, and builds an HTML report you can filter and slice.

- **No new habits.** Rows are added by a pre-commit hook. You keep working and committing as usual.
- **No prompt text in git.** Committed rows hold numbers, branch, tag, session title and changed file paths. See [Privacy](#privacy).
- **Grouped by feature.** Prompts that edit the same files are put in one work unit. A one-line name for each unit comes from Claude Haiku, or from file names if you turn the model off.
- **Shared names.** A vocabulary file keeps unit names the same across the team and across runs.
- **Your own labels.** Tags mark a release or an experiment on top of the automatic grouping.

## Quick start

**1. Install the plugin** in Claude Code:

```
/plugin marketplace add kwakyongwoo/token-ledger
/plugin install token-ledger@token-ledger
```

**2. Install the CLI** ([`uv`](https://docs.astral.sh/uv/) needed). If you skip this, Claude offers to do it the first time you open a repo that uses token-ledger.

```bash
uv tool install git+https://github.com/kwakyongwoo/token-ledger
```

**3. Turn it on in a repo** (one person, once), then commit the new files:

```
/token-ledger:init
```

**4. Work and commit as usual.** Later, open the report:

```
/token-ledger:report
```

Teammates only need steps 1 and 2. When they open the repo, a SessionStart hook installs the pre-commit hook for them.

## Try the example

[`examples/report.html`](examples/report.html) is a full report built from made-up data: three members and 140 prompts. Open it in a browser and try the filters and group-by buttons. [`examples/token-ledger-out/`](examples/token-ledger-out/) shows exactly what gets committed. To rebuild it, run `python3 examples/make_example.py`.

## What you get

| | |
|---|---|
| **Summary cards** | Cost, prompts, input, output, and cost per prompt |
| **Filters** | Date range, member, branch, worktree, tag, work unit, model |
| **Group by** | Work unit, tag, session, branch, worktree, model, day, member |
| **Most expensive prompts** | The top 25, with a short excerpt shown for your own prompts only |
| **Light and dark** | Follows your system theme |

Each committed row holds:
- tokens per model: input, output, cache write, cache read and thinking
- cost at API list prices
- duration
- tool calls and subagents
- branch, worktree and tag
- the session title and the repo-relative paths of edited files

## How it works

```
your Claude Code session ──> ~/.claude/projects/*.jsonl   (local transcripts)
                                        │
git commit ──> pre-commit hook ──> token-ledger collect
                                        │  finished prompts only, no prompt text
                                        ▼
                    token-ledger-out/data/<member>/<time>-<id>.jsonl   (committed, write-once)
                                        │
token-ledger report ──> group into work units ──> name new units (Haiku) ──> report.html
```

1. **Collect.** On each commit, the hook reads the parts of local transcripts it has not read yet. It keeps prompts that touched this repo and have finished. A prompt counts as finished when a later prompt exists, or when the session has been idle for 30 minutes after a normal reply.
2. **Share.** Each run writes a new file that is never edited again. Two members committing at the same time never conflict.
3. **Group.** Prompts are linked when they:
   - edit the same files (strongest)
   - come one after another in a session
   - share a feature branch

   Louvain community detection then finds the groups.
4. **Name.** One `claude -p --model haiku` call names all new groups. It sends file paths, the branch and session titles, not prompt text. A group that already has a name keeps it.

## Cost and speed

Measured on a real repo with 192 MB of transcripts:

| When | Extra time | Tokens |
|---|---|---|
| Every commit | about 0.2 s (1.5 s the first time) | 0 |
| Opening Claude Code | about 0.2 s | 0 |
| `token-ledger report` | about 8 s with naming | one small Haiku call, only for new groups |

Set `"classify": false` to skip the model completely.

## Commands

| In Claude Code | CLI | What it does |
|---|---|---|
| `/token-ledger:init` | `token-ledger init` | Turns token-ledger on in this repo |
| `/token-ledger:report` | `token-ledger report` | Groups new prompts, then writes `token-ledger-out/report.html` |
| `/token-ledger:tag <name>` | `token-ledger tag <name>` | Tags the prompts that follow (`off` to stop) |
| `/token-ledger:vocab` | `token-ledger vocab list\|merge\|rename\|ok` | Merges, renames and confirms work unit names |
| | `token-ledger summary --by branch` | Quick totals in the terminal |
| | `token-ledger hook status\|install\|uninstall` | Manages the pre-commit hook for you only |

## Configuration

`token-ledger-out/config.json`:

| Key | Default | Meaning |
|---|---|---|
| `classify` | `true` | Name new work units with Claude Haiku. `false` names them from file names, then the branch, then the session title. |
| `per_member` | `true` | Reserved for hiding the member view. Not implemented yet. |

## Privacy

- **Never committed:** prompt text and replies. Short excerpts stay on your machine in `.git/token-ledger/`.
- **Committed:** numbers, branch, tag, session title, repo-relative paths, and each member's `git config user.name`. Claude Code names sessions from your first prompt, so a session title can hint at what you asked.
- **One exception:** a work unit that changed no files and is made only of your own prompts is named from short excerpts of them. Its name can reflect what you asked.
- **Telling your team:** do it before you turn this on. Anyone can opt out on their machine with `token-ledger hook uninstall`.

## FAQ

**I committed, but my last prompt is missing.**
It was still running, or the session had not been idle for 30 minutes yet. The next commit picks it up.

**Do I need to commit for the report to update?**
No. `token-ledger report` reads every row in `token-ledger-out/data/`, including teammates' rows after you pull. To include your own newest prompts right away, run `token-ledger collect` first.

**Are the costs what I actually pay?**
They are estimates at API list prices (checked 2026-11-03). On a subscription plan, they show what the same usage would cost on the API. Models without a known price show no cost.

**Does it work with worktrees and subagents?**
Yes. Worktrees of the same repo are combined, and tokens from subagents count toward the prompt that started them.

**Our repo already has a pre-commit hook.**
If it is a shell script, token-ledger adds one line to it and never blocks the commit. If it is not a shell script, or your hooks live in a tracked folder, `token-ledger hook install` tells you what to add by hand.

## Requirements

- Claude Code
- git
- Python 3.9+, through `uv`
- `claude` on your PATH for naming. Without it, names come from file names.

## Status

v0.1.1, early. The data format may change before 1.0. Design notes: [`docs/design.md`](docs/design.md).

## License

[MIT](LICENSE)
