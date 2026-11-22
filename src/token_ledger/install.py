"""`token-ledger init` and the pre-commit hook."""
from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path

from .collect import OUT_DIR, Repo, git

BEGIN, END = "# >>> token-ledger >>>", "# <<< token-ledger <<<"
# Never blocks a commit: missing CLI or any error still exits 0.
HOOK_BLOCK = f"""{BEGIN}
command -v token-ledger >/dev/null 2>&1 && token-ledger collect --stage --quiet || true
{END}
"""
CLAUDE_SECTION = """
## token-ledger

This repo records Claude Code token usage per prompt in `token-ledger-out/` (no prompt text; usage, branch, tag, session title and changed file paths). A pre-commit hook adds new rows to each commit.

- `/token-ledger:tag <name>` labels the following prompts with a tag; `/token-ledger:tag off` stops it.
- `/token-ledger:report` builds `token-ledger-out/report.html`.
- Do not edit files under `token-ledger-out/data/` by hand.
"""


def _append_line(path: Path, line: str) -> bool:
    text = path.read_text() if path.exists() else ""
    if line in text.splitlines():
        return False
    path.write_text(text + ("" if not text or text.endswith("\n") else "\n") + line + "\n")
    return True


def hooks_dir(repo: Repo) -> tuple[Path, bool]:
    """(hooks directory, whether it is ours to edit). A tracked hooksPath (husky etc.) is not."""
    d = Path(git("rev-parse", "--git-path", "hooks", cwd=str(repo.root)))
    d = d if d.is_absolute() else (repo.root / d).resolve()
    try:
        rel = d.relative_to(repo.root)
    except ValueError:
        return d, True  # outside the working tree (.git/hooks or a global dir)
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(rel)], cwd=repo.root,
                             capture_output=True).returncode == 0
    return d, not tracked


def is_shell(first_line: str) -> bool:
    """Whether a hook with this first line runs as a POSIX-style shell script."""
    if not first_line.startswith("#!"):
        return True  # no shebang: git runs it with sh
    parts = first_line[2:].split()
    if parts and parts[0].rsplit("/", 1)[-1] == "env":
        parts = [p for p in parts[1:] if not p.startswith("-")]
    return bool(parts) and parts[0].rsplit("/", 1)[-1] in {"sh", "bash", "zsh", "dash", "ksh"}


def disabled_flag(repo: Repo) -> Path:
    return repo.state_dir / "hook-disabled"


def hook_state(repo: Repo) -> str:
    """installed | disabled (member opted out) | manual (tracked hooks folder) | missing."""
    d, ours = hooks_dir(repo)
    hook = d / "pre-commit"
    if hook.exists() and BEGIN in hook.read_text():
        return "installed"
    if disabled_flag(repo).exists():
        return "disabled"
    if hook.exists() and not is_shell(hook.read_text().partition("\n")[0]):
        return "manual"
    return "missing" if ours else "manual"


def install_hook(repo: Repo) -> tuple[bool, str]:
    """(installed, message). Explicit install clears a previous opt-out."""
    disabled_flag(repo).unlink(missing_ok=True)
    d, ours = hooks_dir(repo)
    hook = d / "pre-commit"
    if not ours:
        return False, (f"hooks live in a tracked folder ({d.relative_to(repo.root)}); add this line to its pre-commit yourself:\n"
                "  command -v token-ledger >/dev/null 2>&1 && token-ledger collect --stage --quiet || true")
    d.mkdir(parents=True, exist_ok=True)
    text = hook.read_text() if hook.exists() else ""
    if BEGIN in text:
        return True, f"hook already installed: {hook}"
    created = not text
    if created:
        text = "#!/bin/sh\n" + HOOK_BLOCK
    else:  # insert right after the shebang so an `exit` later in the existing hook cannot skip it
        first, _, rest = text.partition("\n")
        if not is_shell(first):
            return False, (f"{hook} is not a shell script; add this line to it yourself (or run it from there):\n"
                           "  command -v token-ledger >/dev/null 2>&1 && token-ledger collect --stage --quiet || true")
        text = first + "\n" + HOOK_BLOCK + rest if first.startswith("#!") else HOOK_BLOCK + text
    hook.write_text(text)
    if created:  # an existing hook keeps its mode (someone may have disabled it with chmod -x)
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return True, f"hook installed: {hook}"


def uninstall_hook(repo: Repo) -> str:
    """Remove the hook and remember the opt-out, so the SessionStart hook does not put it back."""
    repo.state_dir.mkdir(parents=True, exist_ok=True)
    disabled_flag(repo).touch()
    hook = hooks_dir(repo)[0] / "pre-commit"
    text = hook.read_text() if hook.exists() else ""
    if BEGIN not in text:
        return "hook not installed"
    head, _, tail = text.partition(BEGIN)
    text = head + tail.partition(END)[2].lstrip("\n")
    if text.strip() in ("", "#!/bin/sh"):
        hook.unlink()
    else:
        hook.write_text(text)
    return f"hook removed: {hook}"


def init(repo: Repo) -> list[str]:
    done = []
    out = repo.root / OUT_DIR
    out.mkdir(exist_ok=True)
    cfg = out / "config.json"
    if not cfg.exists():
        cfg.write_text(json.dumps({"classify": True, "per_member": True}, indent=2) + "\n")
        done.append(f"created {OUT_DIR}/config.json")
    added = [_append_line(repo.root / ".gitattributes", f"{OUT_DIR}/{d}/** linguist-generated") for d in ("data", "units")]
    if any(added):
        done.append(".gitattributes: data and units marked as generated (collapsed in PR diffs)")
    if _append_line(repo.root / ".gitignore", f"{OUT_DIR}/report.html"):
        done.append(".gitignore: report.html is built locally")
    claude = repo.root / "CLAUDE.md"
    text = claude.read_text() if claude.exists() else ""
    if "## token-ledger" not in text:
        claude.write_text(text.rstrip("\n") + ("\n" if text else "") + CLAUDE_SECTION)
        done.append("CLAUDE.md: added the token-ledger section")
    done.append(install_hook(repo)[1])
    return done


def has_ledger(repo: Repo) -> bool:
    return (repo.root / OUT_DIR / "config.json").exists()
