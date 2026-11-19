"""Work units: clustering, stable names across runs, vocabulary merge/rename. Needs networkx.

Run: uv run --with networkx python -m unittest discover -s tests
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from token_ledger import cluster, vocab  # noqa: E402

try:
    import networkx  # noqa: F401
except ImportError:  # pragma: no cover
    networkx = None


def row(i, session, files=(), branch="main", title=None, ts=None):
    return {"id": i, "ts": ts or f"2026-11-20T00:{int(i[1:]):02d}:00Z", "session": session, "files": list(files),
            "branch": branch, "title": title, "tag": None}


ROWS = [
    row("p1", "s1", ["src/report/filters.ts"], "feat/report"),
    row("p2", "s1", ["src/report/filters.ts", "src/report/table.ts"], "feat/report"),
    row("p3", "s2", ["src/report/table.ts"], "feat/report"),
    row("p4", "s3", ["src/pricing.py"], "feat/price"),
    row("p5", "s3", ["src/pricing.py", "tests/test_pricing.py"], "feat/price"),
    row("p6", "s4", [], "main", title="Onboarding docs"),
]


@unittest.skipIf(networkx is None, "networkx not installed")
class ClusterTest(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())
        self.calls = []

    def namer(self, clusters, existing):
        self.calls.append(clusters)
        return [("report filters" if "src/report/filters.ts" in c["files"] else
                 "price table" if c["files"] else "onboarding docs") for c in clusters]

    def test_groups_and_stable_names(self):
        v = vocab.Vocabulary(self.out)
        which = mock.patch.object(cluster.shutil, "which", return_value="/usr/bin/claude")
        which.start()
        self.addCleanup(which.stop)
        pairs, created = cluster.assign(ROWS, {}, v, {}, classify=True, namer=self.namer)
        self.assertEqual(pairs["p1"], pairs["p3"])  # linked through shared files
        self.assertEqual(pairs["p4"], "price-table")
        self.assertNotEqual(pairs["p1"], pairs["p4"])
        self.assertEqual(sorted(created), ["onboarding-docs", "price-table", "report-filters"])
        self.assertTrue(all(v.entries[n]["new"] for n in created))
        self.assertNotIn("prompt_excerpts", self.calls[0][0])  # clusters with files never send excerpts

        # next run: a new prompt joins an existing unit without calling the model
        more = ROWS + [row("p7", "s5", ["src/report/table.ts"], "feat/report")]
        pairs2, created2 = cluster.assign(more, pairs, v, {}, classify=True, namer=self.namer)
        self.assertEqual(pairs2, {"p7": "report-filters"})
        self.assertEqual(created2, [])
        self.assertEqual(len(self.calls), 1)

    def test_classify_off_uses_files(self):
        v = vocab.Vocabulary(self.out)
        pairs, _ = cluster.assign(ROWS, {}, v, {"p6": "write the setup guide"}, classify=False, namer=self.namer)
        self.assertEqual(self.calls, [])
        self.assertIn(pairs["p4"], {"pricing", "test-pricing"})
        self.assertEqual(pairs["p6"], "onboarding-docs")  # no files, default branch: session title

    def test_model_failure_leaves_clusters_for_retry(self):
        v = vocab.Vocabulary(self.out)
        with mock.patch.object(cluster.shutil, "which", return_value="/usr/bin/claude"):
            pairs, created = cluster.assign(ROWS, {}, v, {}, classify=True, namer=lambda c, e: None)
        self.assertEqual((pairs, created), ({}, []))
        with mock.patch.object(cluster.shutil, "which", return_value=None):  # no CLI at all: fall back to files
            pairs, _ = cluster.assign(ROWS, {}, v, {}, classify=True, namer=lambda c, e: None)
        self.assertEqual(len(pairs), len(ROWS))


class VocabTest(unittest.TestCase):
    def test_merge_rename_resolve_roundtrip(self):
        out = Path(tempfile.mkdtemp())
        v = vocab.Vocabulary(out)
        v.add("Report Filters")
        v.add("report-filter-ui")
        v.merge("report-filter-ui", "report-filters")
        v.rename("report-filters", "report-ui")
        v.save()
        w = vocab.Vocabulary(out)
        self.assertEqual(w.resolve("report-filter-ui"), "report-ui")
        self.assertEqual(w.resolve("report-filters"), "report-ui")
        self.assertEqual(w.resolve("unknown-x"), "unknown-x")
        self.assertEqual(sorted(w.entries), ["report-ui"])
        lines = (out / "vocabulary.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 1)  # one name per line
        self.assertEqual(w.close("report-table"), ["report-ui"])
        w.ok([])
        self.assertFalse(w.entries["report-ui"]["new"])

    def test_assignments_first_wins(self):
        out = Path(tempfile.mkdtemp())
        vocab.write_assignments(out, "a", {"p1": "x"})
        (out / "units" / "b").mkdir(parents=True)
        (out / "units" / "b" / "99999999T000000Z-zz.jsonl").write_text('{"id": "p1", "unit": "y"}\n')
        self.assertEqual(vocab.read_assignments(out)["p1"], "x")


if __name__ == "__main__":
    unittest.main()
