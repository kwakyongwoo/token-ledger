#!/bin/sh
# In a repo set up with token-ledger: make sure this member's CLI and pre-commit hook exist.
# Silent elsewhere; never fails the session.
root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
[ -f "$root/token-ledger-out/config.json" ] || exit 0
plugin_root="${CLAUDE_PLUGIN_ROOT:-$(dirname "$0")/..}"
want="$(sed -n 's/^version = "\(.*\)"/\1/p' "$plugin_root/pyproject.toml" | head -1)"
if ! command -v token-ledger >/dev/null 2>&1; then
  echo "token-ledger: this repo records Claude Code token usage, but the token-ledger CLI is not installed for this user. Offer to install it with: uv tool install \"$plugin_root\" and then run: token-ledger hook install"
  exit 0
fi
have="$(token-ledger --version 2>/dev/null)"
if [ -n "$want" ] && [ "$have" != "$want" ]; then
  echo "token-ledger: CLI $have differs from the plugin ($want). Offer to update it with: uv tool install --reinstall \"$plugin_root\""
fi
case "$(token-ledger hook status 2>/dev/null)" in
  missing)
    token-ledger hook install >/dev/null 2>&1 &&
      echo "token-ledger: installed the pre-commit hook that adds token usage rows to commits. Mention this once to the user (they can opt out with: token-ledger hook uninstall)." ;;
  manual)
    echo "token-ledger: the pre-commit hook was not installed because this repo's hooks live in a tracked folder or the existing hook is not a shell script. If the user wants usage recorded, show them the output of: token-ledger hook install" ;;
esac
exit 0
