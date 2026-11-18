"""Tests for reading what a figure measures: its period and its label, in a note and in a source, and for `figures`
holding a found figure to them."""
import shutil
import tempfile
import unittest
from pathlib import Path

from support import CODE_ROOT

from drillcore import measures, sourcedb, workspace
from drillcore.measures import Period

QUARTERLY = "https://example.com/northbridge/q3.html"
QUARTERLY_PAGE = b"""<html><body><p>Three months ended September 30</p>
<table><tr><th></th><th>2025</th><th>2024</th></tr>
<tr><td>Revenue</td><td>551.1</td><td>572.5</td></tr>
<tr><td>Gross profit</td><td>227.0</td><td>257.1</td></tr>
<tr><td>Net profit</td><td>31.4</td><td>40.2</td></tr></table>
<p>Revenue was $551.1 million in the third quarter of 2025, against $572.5 million a year earlier.</p>
</body></html>"""


class Periods(unittest.TestCase):
    def test_the_ways_a_period_is_written(self):
        cases = {
            "Q3 2025": Period(3, "Q3", "", 2025), "3Q25": Period(3, "Q3", "", 2025),
            "third quarter of 2025": Period(3, "Q3", "", 2025), "H1 2025": Period(6, "H1", "", 2025),
            "first half of 2025": Period(6, "H1", "", 2025), "nine months ended September 30, 2025": Period(9, "", "", 2025),
            "9M25": Period(9, "", "", 2025), "FY2025": Period(12, "", "fiscal", 2025), "fiscal 2025": Period(12, "", "fiscal", 2025),
            "calendar 2025": Period(12, "", "calendar", 2025), "Year ended December 31, 2025": Period(12, "", "", 2025),
            "2025": Period(None, "", "", 2025), "Nine Months Ended": Period(9, "", "", None),
        }
        for written, period in cases.items():
            with self.subTest(written):
                self.assertEqual(measures.periods(written), [period])

    def test_what_isnt_a_period(self):
        for written in ("Revenue, $M", "1,757", "$2025", "2,025.5", "S1"):
            with self.subTest(written):
                self.assertEqual(measures.periods(written), [])

    def test_two_periods_differ_only_in_what_both_say(self):
        self.assertEqual(measures.differ(Period(3, "Q3", "", 2025), Period(9, "", "", 2025)), "length")
        self.assertEqual(measures.differ(Period(None, "", "", 2025), Period(3, "Q3", "", 2025)), "")
        self.assertEqual(measures.differ(Period(12, "", "fiscal", 2025), Period(12, "", "calendar", 2025)), "fiscal against calendar year")
        self.assertEqual(measures.differ(Period(None, "", "", 2024), Period(None, "", "", 2025)), "year")
        self.assertEqual(Period(None, "", "", 2025).filled_from(Period(9)), Period(9, "", "", 2025))
        self.assertEqual([p.shown() for p in (Period(9, "", "", 2025), Period(12, "", "fiscal", 2025), Period(None, "", "", 2025))],
                         ["9M 2025", "FY2025", "2025"])


class Labels(unittest.TestCase):
    def test_words_that_mean_the_same_line_read_the_same(self):
        self.assertEqual(measures.label_words("Total net sales, $M"), {"net", "revenue"})
        self.assertEqual(measures.label_words("Employees at year end"), measures.label_words("Staff"))
        self.assertEqual(measures.label_words("Backlog"), measures.label_words("Order book"))

    def test_a_qualifier_tells_two_lines_apart(self):
        clash = measures.qualifier_clash(measures.label_words("Gross margin"), measures.label_words("Net margin"))
        self.assertEqual(clash, "net where the note says gross")
        self.assertTrue(measures.qualifier_clash(measures.label_words("EPS, diluted"), measures.label_words("Basic earnings per share")))
        self.assertTrue(measures.qualifier_clash(measures.label_words("Revenue (restated)"), measures.label_words("Revenue as previously reported")))
        self.assertFalse(measures.qualifier_clash(measures.label_words("Revenue"), measures.label_words("Net sales")))


class Surroundings(unittest.TestCase):
    TABLE = "Nine months ended September 30\nItem | 2025 | 2024\nRevenue | 551.1 | 572.5\nGross margin | $ | 41.2% | $ | 44.9%"

    def test_a_cell_is_read_with_its_rows_label_and_its_columns_heading(self):
        at = self.TABLE.index("572.5")
        found = measures.source_context(self.TABLE, at, at + 5)
        self.assertEqual(found, measures.Context("Revenue", (Period(9, "", "", 2024),), True))

    def test_cells_out_of_line_with_the_heading_are_matched_in_order(self):
        at = self.TABLE.index("41.2")
        self.assertEqual(measures.source_context(self.TABLE, at, at + 4).periods, (Period(9, "", "", 2025),))

    def test_prose_is_read_by_the_clause_a_figure_stands_in(self):
        text = "Revenue was $551.1 million in Q3 2025, against $572.5 million in Q3 2024."
        at = text.index("572.5")
        found = measures.source_context(text, at, at + 5)
        self.assertEqual(found.periods, (Period(3, "Q3", "", 2024),))
        self.assertFalse(found.row)

    def test_a_comparative_in_brackets_is_a_clause_of_its_own(self):
        # As UK and European reports give the prior year: the 2024 is the bracketed figure's, not the one before it.
        text = "Revenue was £551.1m (2024: £572.5m), and we ended the year with 1,757 staff (FY24: 1,820)."
        at = text.index("551.1")
        self.assertEqual(measures.source_context(text, at, at + 5).periods, ())
        at = text.index("572.5")
        found = measures.source_context(text, at, at + 5)
        self.assertEqual((found.label, found.periods), ("2024: £572.5m", (Period(None, "", "", 2024),)))
        at = text.index("1,757")
        self.assertEqual(measures.source_context(text, at, at + 5).periods, ())
        at = text.index("1,820")
        self.assertEqual(measures.source_context(text, at, at + 5).periods, (Period(12, "", "fiscal", 2024),))
        # A period beside the figure still counts, and brackets that name no period are words of the clause.
        text = "Revenue for 2025 was £551.1m (2024: £572.5m) (see note 4: segments)."
        at = text.index("551.1")
        self.assertEqual(measures.source_context(text, at, at + 5).periods, (Period(None, "", "", 2025),))

    def test_a_note_row_is_read_with_its_tables_heading_and_its_sections(self):
        row = "| Revenue, $M | 551.1 | 572.5 |"
        at = row.index("572.5")
        found = measures.note_context(row, at, at + 5, ["Item", "2025", "2024"], "## Nine months to September")
        self.assertEqual(found, measures.Context("Revenue, $M", (Period(9, "", "", 2024),), True))

    def test_an_unreadable_surrounding_is_never_a_disagreement(self):
        note = measures.Context("Revenue", (Period(None, "", "", 2025),), True)
        self.assertEqual(measures.compare(note, measures.Context()), (measures.UNREAD, ""))
        self.assertEqual(measures.verdict(note, []), (measures.UNREAD, ""))
        self.assertEqual(measures.verdict(note, [measures.Context("Staff", (Period(None, "", "", 2024),), True),
                                                 measures.Context()]), (measures.UNREAD, ""))


class Figures(unittest.TestCase):
    """`figures` on a workspace whose note cites a quarterly report."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        self.ws = workspace.Workspace(root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)
        (root / "research" / "01_northbridge.md").unlink()

    def check(self, note: str, page: bytes = QUARTERLY_PAGE) -> dict[str, tuple[str, str]]:
        (self.ws.root / "research" / "02_quarter.md").write_text(note + f"\n\n## Sources\n\n- **S1.** Q3 report. {QUARTERLY}\n",
                                                                  encoding="utf-8")
        sourcedb.record_sources(self.ws, self.con)
        sourcedb.fetch(self.ws, self.con, get=lambda url: (200, "text/html", url, page, None), say=lambda _: None)
        sourcedb.check_figures(self.ws, self.con)
        return {text: (status, detail) for text, status, detail in
                self.con.execute("SELECT number_text, status, detail FROM note_figures")}

    def test_the_right_number_for_the_wrong_period_is_said_so(self):
        found = self.check("## Nine months (S1)\n\n| Item | 9M 2025 | 9M 2024 |\n|---|---|---|\n| Revenue | 551.1 | 572.5 |")
        self.assertEqual(found["551.1"][0], "beside_another_period")
        self.assertIn("where the note says 9M 2025 (length)", found["551.1"][1])
        report = (self.ws.data / "figures_not_found.csv").read_text(encoding="utf-8")
        self.assertIn("beside_another_period", report)

    def test_the_right_period_agrees(self):
        found = self.check("## Q3 (S1)\n\n| Item | Q3 2025 | Q3 2024 |\n|---|---|---|\n| Revenue | 551.1 | 572.5 |")
        self.assertEqual({status for status, _ in found.values()}, {"found"})

    def test_a_figure_from_the_wrong_year_is_said_so(self):
        table_only = QUARTERLY_PAGE.split(b"<p>Revenue was")[0]
        found = self.check("## Q3 (S1)\n\n| Item | Q3 2025 |\n|---|---|\n| Revenue | 572.5 |", page=table_only)
        self.assertEqual(found["572.5"][0], "beside_another_period")

    def test_one_place_that_cant_be_read_leaves_a_figure_unjudged(self):
        # The release's sentence gives 572.5 no year, and it may be the place the note means.
        found = self.check("## Q3 (S1)\n\n| Item | Q3 2025 |\n|---|---|\n| Revenue | 572.5 |")
        self.assertEqual(found["572.5"][0], "found")

    def test_the_right_number_from_the_wrong_line_is_said_so(self):
        found = self.check("- Q3 2025 net profit was $227.0M (S1).")
        self.assertEqual(found["227.0"], ("beside_another_label", "beside 'Gross profit': gross where the note says net"))

    def test_a_figure_beside_its_prior_year_comparative_is_found(self):
        page = b"<p>Revenue was $551.1 million (2024: $572.5 million).</p>"
        found = self.check("## Results (S1)\n\n| Item | 2025 | 2024 |\n|---|---|---|\n| Revenue | 551.1 | 572.5 |", page=page)
        self.assertEqual(found, {"551.1": ("found", ""), "572.5": ("found", "")})

    def test_a_figure_whose_surroundings_cant_be_read_is_found_and_not_judged(self):
        found = self.check("- Something came to 551.1 (S1).", page=b"<p>A total of 551.1 was recorded.</p>")
        self.assertEqual(found["551.1"], ("found", ""))


if __name__ == "__main__":
    unittest.main()
