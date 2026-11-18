"""Tests for statements of a measure, and the two commands that compare them: `conflicts`, between sources, and
`consistency`, between the notes and drafts."""
import shutil
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

from support import CODE_ROOT, run_cli

from drillcore import conflicts, consistency, identity, sourcedb, statements, workspace
from drillcore.measures import Period

ANNUAL = "https://example.com/northbridge/annual-2025.html"
ORDERS = "https://example.com/northbridge/orders.html"
RELEASE = "https://example.com/news/northbridge-results.html"
NOTE = """# Northbridge

## Results (S1)

| Item | 2025 | 2024 |
|---|---|---|
| Revenue, $M | 551.1 | 572.5 |
| Gross margin | 41.2% | 44.9% |

- Revenue for 2025 was $551.1M (S1).

## Sources

- **S1.** Annual report. https://example.com/northbridge/annual-2025.html
- **S2.** Release. https://example.com/news/northbridge-results.html
"""


class Reading(unittest.TestCase):
    def test_a_tables_cells_are_statements_of_their_row_and_column(self):
        found = list(statements.table_statements("01.md", NOTE, markdown=True, headings=statements.headings_of(NOTE)))
        self.assertEqual([(s.label, s.period.shown(), s.written, s.scale, s.percent) for s in found], [
            ("Revenue, $M", "2025", "551.1", 1e6, False), ("Revenue, $M", "2024", "572.5", 1e6, False),
            ("Gross margin", "2025", "41.2%", 1.0, True), ("Gross margin", "2024", "44.9%", 1.0, True)])
        self.assertEqual(found[0].line_no, 7)

    def test_a_sources_table_is_read_with_the_unit_it_states(self):
        text = "In thousands of US dollars\nYear ended December 31 | 2025 | 2024\nTotal revenue | 551,102 | 572,514"
        found = list(statements.table_statements(RELEASE, text, markdown=False))
        self.assertEqual([(s.words, s.period, s.value, s.scale) for s in found][0],
                         (frozenset({"revenue"}), Period(12, "", "", 2025), 551102.0, 1e3))

    def test_a_plain_clause_is_a_statement_and_a_crowded_one_isnt(self):
        found = list(statements.prose_statements("d.md", "Revenue for 2025 was $551.1M.\n"
                                                         "Revenue per employee in 2025 was $313.6K.\n"
                                                         "Revenue fell to $551.1M in 2025 against $572.5M in 2024."))
        self.assertEqual([(s.words, s.written, s.period.shown()) for s in found], [
            ({"revenue"}, "$551.1M", "2025"),
            # Per employee is another measure, not revenue.
            ({"revenue", "staff"}, "$313.6K", "2025"),
            # The clause the second figure opens names no line, so only the first is read.
            ({"revenue"}, "$551.1M", "2025")])
        crowded = list(statements.prose_statements("d.md", "Revenue and margin for 2025 were $551.1M and 41.2%."))
        self.assertEqual(crowded, [])
        # A prior year's comparative in brackets is a clause of its own, so it doesn't crowd the figure before it.
        compared = list(statements.prose_statements("d.md", "Revenue for 2025 was $551.1M (2024: $572.5M)."))
        self.assertEqual([(s.words, s.written, s.period.shown()) for s in compared], [({"revenue"}, "$551.1M", "2025")])

    def test_figures_agree_within_their_rounding_at_the_scale_they_state(self):
        def one(written, value, decimals, scale, percent=False):
            return statements.Statement("x", 1, "Revenue", frozenset({"revenue"}), Period(None, "", "", 2025), written, value,
                                        decimals, percent, scale, "")
        self.assertTrue(statements.agree(one("551.1", 551.1, 1, 1e6), one("551,102", 551102, 0, 1e3)))
        self.assertTrue(statements.agree(one("551.1", 551.1, 1, 1e6), one("0.55bn", 0.55, 2, 1e9)))
        self.assertTrue(statements.agree(one("551.1", 551.1, 1, None), one("551,102", 551102, 0, None)))
        self.assertFalse(statements.agree(one("551.1", 551.1, 1, 1e6), one("549.8", 549.8, 1, 1e6)))
        self.assertFalse(statements.agree(one("551.1", 551.1, 1, 1e6), one("551,102", 551102, 0, 1.0)))

    def test_only_the_same_label_and_period_are_the_same_measure(self):
        self.assertTrue(statements.same_period(Period(None, "", "", 2025), Period(None, "", "", 2025)))
        self.assertTrue(statements.same_period(Period(None, "", "", 2025), Period(12, "", "", 2025)))
        self.assertFalse(statements.same_period(Period(None, "", "", 2025), Period(3, "Q3", "", 2025)))
        self.assertFalse(statements.same_period(Period(None, "", "", 2025), Period(9, "", "", 2025)))
        self.assertFalse(statements.same_period(Period(9), Period(9)))


class Commands(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        self.ws = workspace.Workspace(root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)
        (root / "research" / "01_northbridge.md").write_text(NOTE, encoding="utf-8")
        for path in (root / "drafts").glob("*.md"):
            path.unlink()

    def hold(self, url: str, text: str) -> None:
        sourcedb.keep_text(self.con, url, sourcedb.Extracted(None, text, "html"))
        self.con.commit()

    def run_here(self, *argv):
        with mock.patch.dict(workspace.os.environ, {identity.HOME_VARIABLE: str(self.ws.root)}):
            return run_cli(*argv)

    def test_another_source_stating_a_different_figure_is_a_conflict(self):
        self.hold(ANNUAL, "Year ended December 31 | 2025 | 2024\nRevenue | 551.1 | 572.5")
        self.hold(RELEASE, "US$ millions\nFull year | 2025 | 2024\nNet sales | 549.8 | 572.5\nSales | 549.8 | 572.5")
        found = conflicts.check(self.ws, self.con)
        self.assertEqual({(c.said.line_no, c.said.written, c.other.where, c.other.written) for c in found},
                         {(7, "551.1", RELEASE, "549.8"), (10, "$551.1M", RELEASE, "549.8")})
        out, _, code = self.run_here("conflicts")
        self.assertEqual(code, 1)
        self.assertIn(f"{RELEASE} states 549.8", out)
        self.assertIn("Which is right is for you to decide.", out)
        self.assertIn("549.8", (self.ws.data / "conflicts.csv").read_text(encoding="utf-8"))

    def test_sources_that_agree_or_name_another_period_arent_a_conflict(self):
        self.hold(RELEASE, "In thousands\nQ4 2025 | Year 2025\nSales | 140.2 | 551,102")
        self.assertEqual(conflicts.check(self.ws, self.con), [])
        out, _, code = self.run_here("conflicts")
        self.assertEqual((code, out.splitlines()[0]), (0, "0 figure(s) another source states differently"))

    def test_a_measure_stated_two_ways_in_the_notes_and_drafts_is_reported(self):
        (self.ws.root / "drafts" / "01.md").write_text("# Draft\n\nRevenue for 2025 was $556.1M.\n\nGross margin in 2025 was 41.2%.\n",
                                                       encoding="utf-8")
        found = consistency.check(self.ws)
        self.assertEqual([(d.first.where, d.first.line_no, d.second.where, d.second.line_no) for d in found],
                         [("research/01_northbridge.md", 7, "drafts/01.md", 3), ("research/01_northbridge.md", 10, "drafts/01.md", 3)])
        out, _, code = self.run_here("consistency")
        self.assertEqual(code, 1)
        self.assertIn("'Revenue, $M' 2025: 551.1 at research/01_northbridge.md:7, $556.1M at drafts/01.md:3", out)

    def test_statements_that_agree_within_their_rounding_pass(self):
        (self.ws.root / "drafts" / "01.md").write_text("Revenue for 2025 was $0.55bn.\n", encoding="utf-8")
        self.assertEqual(consistency.check(self.ws), [])
        out, _, code = self.run_here("consistency")
        self.assertEqual((code, out.splitlines()[0]), (0, "0 measure(s) stated differently in two places"))

    def test_cells_of_one_row_under_different_measures_arent_one_measure(self):
        (self.ws.root / "drafts" / "01.md").write_text(
            "# Draft\n\n| Company, 2025 | Gross margin | Net margin |\n|---|---|---|\n| Northbridge, 2025 | 41.2% | 9.0% |\n",
            encoding="utf-8")
        self.assertEqual(consistency.check(self.ws), [])
        read = statements.written_statements("01.md", (self.ws.root / "drafts" / "01.md").read_text(encoding="utf-8"))
        self.assertEqual([s.label for s in read], ["Northbridge, 2025: Gross margin", "Northbridge, 2025: Net margin"])

    def test_a_row_labelled_by_a_date_alone_is_read_as_before(self):
        text = "| Date | Northbridge close | Index close |\n|---|---|---|\n| 2025-01-31 | 12.30 | 4,410.2 |\n"
        self.assertEqual(statements.written_statements("01.md", text), [])

    def test_one_companys_figure_isnt_paired_with_anothers(self):
        with self.ws.config_path.open("a", encoding="utf-8") as out:
            out.write('\n[consistency]\nentities = ["Harbor Arms"]\n')
        (self.ws.root / "research" / "02_harbor.md").write_text(
            "# Harbor Arms\n\n| Item | FY2025 |\n|---|---|\n| Net loss | $(12.0)M |\n", encoding="utf-8")
        (self.ws.root / "drafts" / "01.md").write_text(
            "# Northbridge Robotics: a report\n\n| Item | Value |\n|---|---|\n| Net loss, 2025 | $8.0M |\n", encoding="utf-8")
        self.assertEqual(consistency.check(self.ws), [])
        # The same company's figure stated two ways is still found.
        (self.ws.root / "drafts" / "02.md").write_text(
            "# Notes on Harbor Arms (owner of Northbridge Robotics)\n\nNet loss for 2025 was $11.0M.\n", encoding="utf-8")
        found = consistency.check(self.ws)
        self.assertEqual([(d.first.where, d.second.where, d.first.entity) for d in found],
                         [("research/02_harbor.md", "drafts/02.md", "Harbor Arms")])

    def test_entities_that_cant_be_used_are_refused(self):
        with self.ws.config_path.open("a", encoding="utf-8") as out:
            out.write('\n[consistency]\nentities = [""]\n')
        _, err, code = self.run_here("consistency")
        self.assertEqual(code, 1)
        self.assertIn("[consistency] entities", err)


class Entities(unittest.TestCase):
    def test_a_companys_name_as_prose_writes_it(self):
        self.assertEqual(statements.short_name("Northbridge Robotics, Inc."), "Northbridge Robotics")
        self.assertEqual(statements.short_name("The Harbor Arms Company"), "Harbor Arms")
        self.assertEqual(statements.short_name("Kestrel Holdings Ltd. (Cayman)"), "Kestrel")

    def test_the_nearest_level_that_names_one_says_whose_a_figure_is(self):
        known = ("Northbridge", "Harbor Arms")
        self.assertEqual(statements.entity_of(["Net loss", "### Harbor Arms", "# Northbridge report"], known), "Harbor Arms")
        self.assertEqual(statements.entity_of(["Net loss", "", "# Northbridge report"], known), "Northbridge")
        # A level naming two gives the one it opens with, and otherwise says nothing.
        self.assertEqual(statements.entity_of(["Harbor Arms (owner of Northbridge) - USD:"], known), "Harbor Arms")
        self.assertEqual(statements.entity_of(["Sales of Northbridge and Harbor Arms", "# Northbridge"], known), "")
        # A citation says where a figure is from, not whose it is.
        self.assertEqual(statements.entity_of(["Net loss was $8.0M (Harbor Arms 2026)", "# Northbridge"], known), "Northbridge")
        self.assertEqual(statements.entity_of(["Net loss"], known), "")


if __name__ == "__main__":
    unittest.main()
