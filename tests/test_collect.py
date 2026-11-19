"""collect on synthetic transcripts. Run: python3 -m unittest discover -s tests"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from token_ledger import collect as c  # noqa: E402
from token_ledger.pricing import request_cost  # noqa: E402

OPUS = "claude-opus-5-5"


def human(uuid, ts, text, cwd, idx):
    return {"type": "user", "uuid": uuid, "promptId": uuid, "timestamp": ts, "cwd": cwd, "sessionId": "s1",
            "origin": {"kind": "human"}, "turnPosition": {"promptIndex": idx}, "message": {"role": "user", "content": text}}


def assistant(rid, ts, cwd, usage, content=None, model=OPUS):
    return {"type": "assistant", "requestId": rid, "timestamp": ts, "cwd": cwd, "gitBranch": "feat/x", "sessionId": "s1",
            "message": {"model": model, "usage": usage, "content": content or [{"type": "text", "text": "ok"}]}}


U = {"input_tokens": 10, "output_tokens": 100, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 200,
     "cache_creation": {"ephemeral_5m_input_tokens": 200, "ephemeral_1h_input_tokens": 0},
     "output_tokens_details": {"thinking_tokens": 40}}


class CollectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        g = lambda *a: subprocess.run(["git", *a], cwd=self.repo, check=True, capture_output=True)
        g("init", "-q", "-b", "main")
        g("config", "user.name", "Test User")
        g("commit", "-q", "--allow-empty", "-m", "init")
        self.root = str(Path(c.git("rev-parse", "--show-toplevel", cwd=str(self.repo))))
        proj = self.tmp / "projects" / "p"
        (proj / "s1" / "subagents").mkdir(parents=True)
        os.environ["TOKEN_LEDGER_PROJECTS"] = str(self.tmp / "projects")
        r = self.root
        self.session = proj / "s1.jsonl"
        lines = [
            {"type": "custom-title", "customTitle": "Build ledger", "sessionId": "s1"},
            human("p1", "2026-11-20T00:00:00Z", "fix the parser please", r, 1),
            # one response written as two lines with the same requestId: count once
            assistant("r1", "2026-11-20T00:00:05Z", r, U, [{"type": "tool_use", "id": "tu-edit", "name": "Edit",
                                                            "input": {"file_path": r + "/src/a.py"}}]),
            assistant("r1", "2026-11-20T00:00:05Z", r, U, [{"type": "tool_use", "id": "tu-agent", "name": "Agent", "input": {}}]),
            {"type": "user", "timestamp": "2026-11-20T00:00:06Z", "cwd": r, "sessionId": "s1",
             "origin": {"kind": "task-notification"}, "message": {"content": "<task-notification>done</task-notification>"}},
            {"type": "user", "isMeta": True, "cwd": r, "message": {"content": "injected"}},
            assistant("r2", "2026-11-20T00:00:30Z", r, U),
            human("p2", "2026-11-20T00:01:00Z", "elsewhere", "/somewhere/else", 2),
            assistant("r3", "2026-11-20T00:01:05Z", "/somewhere/else", U),
            human("p3", "2026-11-20T00:02:00Z", "still running", r, 3),
            assistant("r4", "2026-11-20T00:02:05Z", r, U, model="claude-unknown-9"),
        ]
        self.session.write_text("".join(json.dumps(l) + "\n" for l in lines))
        sub = proj / "s1" / "subagents"
        (sub / "agent-a1.meta.json").write_text(json.dumps({"toolUseId": "tu-agent"}))
        (sub / "agent-a1.jsonl").write_text(json.dumps(dict(assistant("r9", "2026-11-20T00:00:20Z", r, U), isSidechain=True)) + "\n")

    def run_collect(self, idle):
        repo = c.Repo(cwd=str(self.repo))
        now = time.time() + (10_000 if idle else 0)
        rows, local, state = c.collect(repo, idle_minutes=30, now=now)
        out = c.write(repo, rows, local, state, stage=False)
        return rows, out

    def test_rows(self):
        rows, out = self.run_collect(idle=False)
        self.assertEqual([r["id"] for r in rows], ["p1"])  # p2 is outside the repo, p3 is still open
        p1 = rows[0]
        u = p1["models"][OPUS]
        self.assertEqual(u["requests"], 3)  # r1 once, r2, subagent r9
        self.assertEqual(u["output"], 300)
        self.assertEqual(u["thinking"], 120)
        self.assertEqual(p1["subagents"], 1)
        self.assertEqual(p1["files"], ["src/a.py"])
        self.assertEqual(p1["title"], "Build ledger")
        self.assertEqual(p1["branch"], "feat/x")
        self.assertEqual(p1["member"], "Test User")
        self.assertAlmostEqual(p1["cost"], 3 * request_cost(OPUS, U), places=9)
        self.assertNotIn("fix the parser", out.read_text())  # prompt text stays local
        local = (Path(c.Repo(cwd=str(self.repo)).state_dir) / "local.jsonl").read_text()
        self.assertIn("fix the parser", local)

        rows2, out2 = self.run_collect(idle=False)
        self.assertEqual(rows2, [])  # nothing new
        self.assertIsNone(out2)

        rows3, out3 = self.run_collect(idle=True)  # session went idle: p3 closes
        self.assertEqual([r["id"] for r in rows3], ["p3"])
        self.assertIsNone(rows3[0]["cost"])  # unknown model: no guessed price
        self.assertNotEqual(out, out3)  # each run writes its own file
        self.assertEqual(sorted(r["id"] for r in c.read_all(Path(self.root))), ["p1", "p3"])

    def test_pricing(self):
        # opus 5.5: 10*4 + 100*20 + 1000*0.2 + 200*4*1.25 per MTok
        self.assertAlmostEqual(request_cost(OPUS, U), (40 + 2000 + 200 + 1000) / 1e6)
        self.assertAlmostEqual(request_cost(OPUS, dict(U, speed="fast")), 2 * request_cost(OPUS, U))
        long = {"input_tokens": 150_000, "output_tokens": 0}
        self.assertAlmostEqual(request_cost("claude-haiku-5-5", long), 150_000 * 0.5 / 1e6)
        self.assertIsNone(request_cost("claude-unknown-9", U))
        one_hour = dict(U, cache_creation={"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 200})
        self.assertAlmostEqual(request_cost(OPUS, one_hour) - request_cost(OPUS, U), 200 * 4 * (2 - 1.25) / 1e6)


if __name__ == "__main__":
    unittest.main()
