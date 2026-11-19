"""init and the pre-commit hook, driven through real git commits."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from token_ledger import collect as c, install  # noqa: E402


class HookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Test User")
        self.git("config", "user.email", "t@example.com")
        (self.repo / "a.txt").write_text("a\n")
        self.git("add", "a.txt")
        self.git("commit", "-q", "-m", "init")
        root = c.git("rev-parse", "--show-toplevel", cwd=str(self.repo))
        # a CLI shim on PATH, as uv tool install would provide
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        shim = self.bin / "token-ledger"
        shim.write_text(f"#!/bin/sh\nPYTHONPATH={SRC} exec {sys.executable} -m token_ledger.cli \"$@\"\n")
        shim.chmod(0o755)
        proj = self.tmp / "projects" / "p"
        proj.mkdir(parents=True)
        lines = [
            {"type": "user", "promptId": "p1", "uuid": "p1", "timestamp": "2026-11-20T00:00:00Z", "cwd": root,
             "sessionId": "s1", "origin": {"kind": "human"}, "turnPosition": {"promptIndex": 1}, "message": {"content": "hi"}},
            {"type": "assistant", "requestId": "r1", "timestamp": "2026-11-20T00:00:05Z", "cwd": root, "gitBranch": "main",
             "message": {"model": "claude-opus-5-5", "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 2}, "content": []}},
        ]
        f = proj / "s1.jsonl"
        f.write_text("".join(json.dumps(l) + "\n" for l in lines))
        old = time.time() - 7200
        os.utime(f, (old, old))  # idle session: its last prompt counts as closed
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", TOKEN_LEDGER_PROJECTS=str(self.tmp / "projects"))

    def git(self, *a, env=None):
        return subprocess.run(["git", *a], cwd=self.repo, check=True, capture_output=True, text=True, env=env).stdout

    def committed(self):
        return self.git("show", "--name-only", "--format=", "HEAD").split()

    def test_init_and_commit_variants(self):
        done = install.init(c.Repo(cwd=str(self.repo)))
        self.assertTrue(any("hook installed" in d for d in done))
        self.assertIn("## token-ledger", (self.repo / "CLAUDE.md").read_text())
        self.assertIn("token-ledger-out/report.html", (self.repo / ".gitignore").read_text())
        self.assertEqual(install.init(c.Repo(cwd=str(self.repo)))[-1].startswith("hook already"), True)  # idempotent
        self.assertEqual((self.repo / ".gitignore").read_text().count("report.html"), 1)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "setup", env=self.env)
        chunk = [f for f in self.committed() if f.startswith("token-ledger-out/data/")]
        self.assertEqual(len(chunk), 1, self.committed())  # the hook staged its chunk into this commit
        self.assertEqual(self.git("status", "--porcelain"), "")

        # commit -a and commit <path> use a temporary index; new rows must still land in the commit
        for n, args in ((5, ["commit", "-q", "-a", "-m", "all"]), (6, ["commit", "-q", "-m", "path", "a.txt"])):
            with open(self.repo / "a.txt", "a") as f:
                f.write("x\n")
            with open(self.tmp / "projects" / "p" / "s1.jsonl", "a") as f:
                f.write(json.dumps({"type": "user", "promptId": f"q{n}", "uuid": f"q{n}", "timestamp": "2026-11-20T01:00:00Z",
                                    "cwd": str(c.Repo(cwd=str(self.repo)).root), "sessionId": "s1", "origin": {"kind": "human"},
                                    "turnPosition": {"promptIndex": n}, "message": {"content": "more"}}) + "\n")
                f.write(json.dumps({"type": "assistant", "requestId": f"rq{n}", "timestamp": "2026-11-20T01:00:05Z",
                                    "cwd": str(c.Repo(cwd=str(self.repo)).root), "gitBranch": "main",
                                    "message": {"model": "claude-opus-5-5", "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 2}}}) + "\n")
            old = time.time() - 7200
            os.utime(self.tmp / "projects" / "p" / "s1.jsonl", (old, old))
            self.git(*args, env=self.env)
            self.assertTrue(any(f.startswith("token-ledger-out/data/") for f in self.committed()), (args, self.committed()))
            self.assertEqual(self.git("status", "--porcelain"), "", args)
        ids = sorted(r["id"] for r in c.read_all(c.Repo(cwd=str(self.repo)).root))
        self.assertEqual(ids, ["p1", "q5", "q6"])

    def test_existing_hook_and_missing_cli(self):
        hooks = self.repo / ".git" / "hooks"
        (hooks / "pre-commit").write_text("#!/bin/sh\necho mine\nexit 0\n")
        install.init(c.Repo(cwd=str(self.repo)))
        text = (hooks / "pre-commit").read_text()
        self.assertIn("echo mine", text)
        self.assertLess(text.index(install.BEGIN), text.index("exit 0"))  # runs before the existing exit
        # CLI not on PATH: the commit still succeeds
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "no cli", env=dict(os.environ, PATH="/usr/bin:/bin"))
        repo = c.Repo(cwd=str(self.repo))
        self.assertIn(install.uninstall_hook(repo).split(":")[0], "hook removed")
        self.assertEqual((hooks / "pre-commit").read_text(), "#!/bin/sh\necho mine\nexit 0\n")
        self.assertEqual(install.hook_state(repo), "disabled")  # SessionStart will not reinstall it
        self.assertTrue(install.install_hook(repo)[0])  # an explicit install clears the opt-out
        self.assertEqual(install.hook_state(repo), "installed")

    def test_manual_collect_output_is_committed_later(self):
        install.init(c.Repo(cwd=str(self.repo)))
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "setup", env=dict(self.env, PATH="/usr/bin:/bin"))  # no CLI: nothing collected
        subprocess.run([str(self.bin / "token-ledger"), "collect"], cwd=self.repo, env=self.env, check=True,
                       capture_output=True)  # manual run: untracked chunk
        self.assertIn("??", self.git("status", "--porcelain"))
        (self.repo / "a.txt").write_text("b\n")
        self.git("commit", "-q", "-am", "next", env=self.env)
        self.assertTrue(any(f.startswith("token-ledger-out/data/") for f in self.committed()))
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_non_shell_hook_is_left_alone(self):
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/usr/bin/env python3\nprint('lint')\n")
        hook.chmod(0o755)
        ok, msg = install.install_hook(c.Repo(cwd=str(self.repo)))
        self.assertFalse(ok)
        self.assertEqual(hook.read_text(), "#!/usr/bin/env python3\nprint('lint')\n")
        self.assertEqual(install.hook_state(c.Repo(cwd=str(self.repo))), "manual")

    def test_tracked_hooks_path_is_left_alone(self):
        (self.repo / ".husky").mkdir()
        (self.repo / ".husky" / "pre-commit").write_text("#!/bin/sh\nnpm test\n")
        self.git("add", ".husky")
        self.git("commit", "-q", "-m", "husky")
        self.git("config", "core.hooksPath", ".husky")
        ok, msg = install.install_hook(c.Repo(cwd=str(self.repo)))
        self.assertFalse(ok)
        self.assertIn("add this line", msg)
        self.assertEqual(install.hook_state(c.Repo(cwd=str(self.repo))), "manual")
        self.assertEqual((self.repo / ".husky" / "pre-commit").read_text(), "#!/bin/sh\nnpm test\n")


if __name__ == "__main__":
    unittest.main()
