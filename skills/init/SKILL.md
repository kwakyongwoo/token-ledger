---
name: init
description: Set up token-ledger in the current git repo so the team's Claude Code token usage is recorded on every commit. Use when the user asks to set up, enable or start token-ledger in a repo.
---

# init

1. Make sure the CLI exists: `command -v token-ledger`. If missing, install it from this plugin: `uv tool install "<this skill dir>/../.."` (needs `uv`; if `uv` is missing, tell the user to install it from https://docs.astral.sh/uv/ and stop).
2. Run `token-ledger init` at the repo root. It creates `token-ledger-out/config.json`, adds `.gitattributes` and `.gitignore` lines and a `## token-ledger` section to `CLAUDE.md`, and installs the pre-commit hook. It is safe to run again.
3. Show the user what it printed, then explain in two lines:
   - Each commit adds rows for this member's finished prompts (usage, branch, tag, changed paths; never prompt text).
   - Teammates get the hook automatically when they open the repo in Claude Code with this plugin.
4. Suggest committing the new files. Do not commit unless asked.

If the output says hooks live in a tracked folder (husky and similar), show the line it printed and ask the user to add it to that hook.
