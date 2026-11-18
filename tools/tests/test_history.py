"""Tests for what changed since the last run: each run's findings are kept, and the next says what's new, fixed and
unchanged, listing the new ones first."""
import os
import shutil
import sqlite3
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

from support import CODE_ROOT, run_cli

from drillcore import history, sourcedb, workspace


def found(*names):
    return [history.Finding(history.fingerprint("check", name), f"  {name}") for name in names]


class Compare(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.addCleanup(self.con.close)

    def test_a_first_run_has_nothing_to_compare_with(self):
        changes = history.compare(self.con, "check", found("a", "b"))
        self.assertTrue(changes.first)
        self.assertIn("first run", changes.summary())

    def test_new_fixed_and_unchanged_are_told_apart(self):
        history.compare(self.con, "check", found("a", "b"))
        changes = history.compare(self.con, "check", found("b", "c"))
        self.assertEqual((changes.new, changes.unchanged, changes.fixed), ([1], [0], ["  a"]))
        self.assertTrue(changes.summary().startswith("1 new, 1 unchanged, 1 fixed since the last run"))

    def test_the_same_finding_twice_counts_twice(self):
        history.compare(self.con, "check", found("a"))
        changes = history.compare(self.con, "check", found("a", "a"))
        self.assertEqual((changes.new, changes.unchanged), ([1], [0]))

    def test_each_command_is_compared_with_its_own_last_run(self):
        history.compare(self.con, "check", found("a"))
        self.assertTrue(history.compare(self.con, "figures", found("a")).first)
        self.assertEqual(history.compare(self.con, "check", found("a")).unchanged, [0])

    def test_only_the_last_few_runs_are_kept(self):
        for _ in range(history.KEEP + 5):
            history.compare(self.con, "check", found("a"))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM runs").fetchone()[0], history.KEEP)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM run_findings").fetchone()[0], history.KEEP)

    def test_the_report_lists_new_first_and_counts_the_unchanged_unless_asked(self):
        history.compare(self.con, "check", found("a", "b"))
        findings = found("b", "c")
        changes = history.compare(self.con, "check", findings)
        said: list[str] = []
        history.report(changes, findings, False, said.append)
        self.assertEqual(said, ["New since the last run (1):", "  c", "1 unchanged since the last run, not listed; --all lists them.",
                                "Fixed since the last run (1):", "  a"])
        said.clear()
        history.report(changes, findings, True, said.append)
        self.assertEqual(said[2:4], ["Unchanged since the last run (1):", "  b"])


class Commands(unittest.TestCase):
    """`figures` and `assay` on a copy of the example, run twice."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", self.root, ignore=shutil.ignore_patterns("data"))
        ws = workspace.Workspace(self.root, "test")
        con = sourcedb.connect(ws)
        self.addCleanup(con.close)
        page = b"<p>Revenue 551.1 against 572.5, margin 41.2% and 44.9%, staff 1,757 and 1,820, research $77.3 million.</p>"
        sourcedb.record_sources(ws, con)
        sourcedb.fetch(ws, con, get=lambda url: (200, "text/html", url, page, None), say=lambda _: None)

    def cli(self, *argv):
        with mock.patch.dict(os.environ, {"DRILLCORE_HOME": str(self.root)}):
            return run_cli(*argv)

    def test_figures_lists_a_finding_once_then_counts_it_as_unchanged(self):
        out, _, _ = self.cli("figures")
        self.assertIn("not found [S1] 999.9", out)
        self.assertIn("first run recorded", out)
        out, _, _ = self.cli("figures")
        self.assertNotIn("not found [S1] 999.9", out)
        self.assertIn("unchanged since the last run, not listed", out)
        out, _, _ = self.cli("figures", "--all")
        self.assertIn("not found [S1] 999.9", out)

    def test_rewording_a_line_leaves_its_finding_unchanged(self):
        self.cli("figures")
        note = self.root / "research" / "01_northbridge.md"
        note.write_text(note.read_text(encoding="utf-8").replace("A figure no source holds", "A figure that no source holds"),
                        encoding="utf-8")
        out, _, _ = self.cli("figures")
        self.assertRegex(out, r"0 new, \d+ unchanged, 0 fixed")

    def test_a_converted_figure_is_left_to_arithmetic(self):
        note = self.root / "research" / "01_northbridge.md"
        note.write_text(note.read_text(encoding="utf-8").replace(
            "- Research spending", "- Revenue in dollars: $76.0M (RMB 551.1M at 7.25) (S1).\n- Research spending"), encoding="utf-8")
        out, _, _ = self.cli("figures", "--all")
        self.assertNotIn(" 76.0 ", out)

    def test_a_fixed_figure_is_named_as_fixed(self):
        self.cli("figures")
        note = self.root / "research" / "01_northbridge.md"
        note.write_text(note.read_text(encoding="utf-8").replace("- A figure no source holds: $999.9M (S1).\n", ""), encoding="utf-8")
        out, _, _ = self.cli("figures")
        self.assertIn("Fixed since the last run", out)
        self.assertIn("999.9", out)

    def test_a_finding_waived_since_the_last_run_is_not_called_fixed(self):
        self.cli("figures")
        (self.root / "checks" / "waivers.csv").write_text(
            "check,note_file,line_no,item,reason,accepted_by,accepted_on\n"
            "figures,01_northbridge.md,,999.9,Confirmed by phone,A. Researcher,2026-11-11\n", encoding="utf-8")
        out, _, _ = self.cli("figures")
        self.assertNotIn("Fixed since the last run", out)
        self.assertIn("waived [S1] 999.9", out)
        self.assertRegex(out, r"0 new, \d+ unchanged, 0 fixed")

    def test_assay_compares_each_draft_with_its_own_last_judging(self):
        out, _, code = self.cli("assay")
        self.assertEqual(code, 1)
        self.assertIn("'sixty'", out)
        out, _, code = self.cli("assay")
        self.assertEqual(code, 1)
        self.assertNotIn("'sixty'", out)
        self.assertIn("01_northbridge.md: FAIL", out)
        self.assertIn("0 new,", out)
        out, _, _ = self.cli("assay", "--all")
        self.assertIn("'sixty'", out)


if __name__ == "__main__":
    unittest.main()
