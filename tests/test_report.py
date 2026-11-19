"""report.build renders a self-contained page and cannot be broken out of by row text."""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from token_ledger import report  # noqa: E402


class ReportTest(unittest.TestCase):
    def test_embeds_rows_safely(self):
        row = {"id": "p1", "ts": "2026-11-20T00:00:00Z", "member": "A", "branch": "main",
               "models": {"claude-opus-5-5": {"requests": 1, "input": 1, "output": 2, "cache_write": 0,
                                               "cache_read": 0, "thinking": 0, "cost": 0.5}},
               "cost": 0.5, "files": ["a.py"]}
        html = report.build([row], {"p1": "unit-a"}, {"unit-a"}, {"p1": "</script><b>x"}, "repo")
        self.assertEqual(html.count("</script>"), 1)  # only the real closing tag
        data = json.loads(re.search(r"const D=(.*?);\n", html).group(1).replace("<\\/", "</"))
        self.assertEqual(data["rows"][0]["unit"], "unit-a")
        self.assertEqual(data["newUnits"], ["unit-a"])
        self.assertNotIn("http", html.split("<script>")[0].split("<style>")[0])  # no external assets


if __name__ == "__main__":
    unittest.main()
