# token-ledger

English | [한국어](README.ko.md)

Ledger of Claude Code token usage per prompt, feature, branch and worktree, grouped by model, feature and session.

## Example

![Example report](examples/screenshot-light.jpg)

A report built from fictional data (three made-up members, 140 prompts). Open [`examples/report.html`](examples/report.html) in a browser to try the filters and group-by buttons, and see [`examples/token-ledger-out/`](examples/token-ledger-out/) for what gets committed: rows without prompt text, work units and the vocabulary. Regenerate with `python3 examples/make_example.py`.

## Install

```
/plugin marketplace add kwakyongwoo/token-ledger
/plugin install token-ledger@token-ledger
```

## Usage

Requires [`uv`](https://docs.astral.sh/uv/) and git. The plugin installs the `token-ledger` CLI from its own folder when needed.

**Set up a repo (one person, once)**

```
/token-ledger:init
```

This creates `token-ledger-out/`, marks its data as generated in `.gitattributes`, ignores the local report, adds a `## token-ledger` section to `CLAUDE.md`, and installs a pre-commit hook. Commit the new files.

**Teammates** install the plugin and open the repo in Claude Code. A SessionStart hook offers to install the CLI and installs the pre-commit hook for them.

**Every commit** then adds a new file under `token-ledger-out/data/<member>/` with one row per finished prompt in this repo: tokens by model, cost at API list prices, branch, worktree, tag and changed file paths. Prompt text is never committed. (One exception: a work unit made only of your own prompts that changed no files is named from short excerpts of them, so its name can reflect what you asked.) The prompt that is still running when you commit is picked up by the next commit.

**Commands**

| In Claude Code | CLI | What it does |
|---|---|---|
| `/token-ledger:report` | `token-ledger report` | Groups new prompts into work units, then writes `token-ledger-out/report.html` |
| `/token-ledger:tag <name>` | `token-ledger tag <name>` | Tags the following prompts (`off` to stop) |
| `/token-ledger:vocab` | `token-ledger vocab list\|merge\|rename\|ok` | Tidies work unit names |
| | `token-ledger summary --by branch` | Quick totals in the terminal |
| | `token-ledger hook status\|install\|uninstall` | Manages the pre-commit hook |

**Work units** are found automatically: prompts that edit the same files, follow each other in a session, or share a feature branch are grouped, and each new group gets a short name from Claude Haiku (`claude -p --model haiku`, using file paths, branch and session titles). Names are kept in `token-ledger-out/vocabulary.jsonl` and reused, so a group is named once. Set `"classify": false` in `token-ledger-out/config.json`, or pass `--no-classify`, to name groups from file names without a model.

**Tags** are your own labels (a release, an experiment) and do not affect work units.

**Privacy.** Committed rows hold numbers, branch, tag, session title and repo-relative paths, plus each member's `git config user.name`. Tell your team before turning it on; `"per_member": false` in the config is reserved for hiding the member view.

## Status

Early skeleton (v0.1.0). Expect breaking changes until the first stable release.
