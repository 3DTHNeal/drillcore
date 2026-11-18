"""Tests for waivers: a finding accepted by a row of checks/waivers.csv is reported as waived and doesn't fail a run,
until what it was judged against changes."""
import os
import shutil
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

from support import CODE_ROOT, run_cli

from drillcore import research, sourcedb, waivers, workspace

ANNUAL = "https://example.com/northbridge/annual-2025.html"
ORDERS = "https://example.com/northbridge/orders.html"
# Every figure the example's note takes from S1 and S2, except the $999.9M it says no source holds.
PAGES = {
    ANNUAL: b"<html><body><table><tr><td>Revenue</td><td>551.1</td><td>572.5</td></tr><tr><td>Gross margin</td><td>41.2%</td>"
            b"<td>44.9%</td></tr><tr><td>Staff</td><td>1,757</td><td>1,820</td></tr></table><p>Research spending was $77.3 million."
            b" We said \"discipline before growth\".</p></body></html>",
    ORDERS: b"<html><body><p>The order book was $95.4 million, of which $67.5 million is due within a year.</p></body></html>",
}
HEADER = "check,note_file,line_no,item,reason,accepted_by,accepted_on\n"
FIGURE = "numbers,01_northbridge.md,,$999.9M,Confirmed by phone with the press office,A. Researcher,2026-11-11\n"
EXTRA = """
## 3. More

- The release said "growth before discipline" (S1).
- Wrong: 12 + 8 = 21 transactions.
"""


class Waived(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", self.root, ignore=shutil.ignore_patterns("data"))
        self.ws = workspace.Workspace(self.root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)
        self.note = self.root / "research" / "01_northbridge.md"
        self.fetch()

    def fetch(self):
        def get(url):
            body = PAGES.get(url)
            return (200, "text/html", url, body, None) if body else (404, "", url, b"", "HTTP 404")
        sourcedb.record_sources(self.ws, self.con)
        sourcedb.fetch(self.ws, self.con, get=get, say=lambda _: None)

    def waive(self, *rows):
        (self.root / "checks" / "waivers.csv").write_text(HEADER + "".join(rows), encoding="utf-8")

    def add_to_note(self, text):
        body = self.note.read_text(encoding="utf-8")
        self.note.write_text(body.replace("## Sources", text.strip() + "\n\n## Sources"), encoding="utf-8")

    def cli(self, *argv):
        with mock.patch.dict(os.environ, {"DRILLCORE_HOME": str(self.root)}):
            return run_cli(*argv)

    def verdicts(self):
        return [(r.check, r.status, r.verdict, r.item) for r in research.run(self.ws, self.con) if r.verdict != research.PASS
                and r.verdict != research.NOT_JUDGED]

    def test_without_a_waiver_the_figure_fails(self):
        self.assertEqual(self.verdicts(), [("numbers", "not_in_source", research.FAIL, "$999.9M")])
        _, _, code = self.cli("check")
        self.assertEqual(code, 1)

    def test_a_waived_finding_is_reported_as_waived_and_check_passes(self):
        self.waive(FIGURE)
        results = research.run(self.ws, self.con)
        waived = [r for r in results if r.verdict == research.WAIVED]
        self.assertEqual([(r.item, r.status) for r in waived], [("$999.9M", "not_in_source")])
        self.assertIn("Confirmed by phone", waived[0].waiver)
        self.assertIn("A. Researcher on 2026-11-11", waived[0].waiver)
        out, _, code = self.cli("check")
        self.assertEqual(code, 0)
        self.assertIn("1 not in source (waived)", out)
        self.assertIn("WAIVED numbers 01_northbridge.md", out)
        self.assertIn("0 failed, 1 waived", out)
        report = (self.root / "data" / research.REPORT).read_text(encoding="utf-8")
        self.assertIn("waived,not_in_source", report)
        self.assertIn("Confirmed by phone", report)

    def test_the_figure_alone_names_it_so_figures_honours_the_same_waiver(self):
        self.waive(FIGURE)
        out, _, code = self.cli("figures")
        self.assertEqual(code, 0)
        self.assertIn("waived [S1] 999.9: Confirmed by phone", out)
        self.assertIn("0 figures not confirmed, 1 waived", out)

    def test_a_waiver_lapses_when_the_line_changes(self):
        self.waive(FIGURE)
        research.run(self.ws, self.con)
        self.note.write_text(self.note.read_text(encoding="utf-8").replace("A figure no source holds", "A figure nobody holds"),
                             encoding="utf-8")
        results = research.run(self.ws, self.con)
        self.assertEqual([r.item for r in results if r.verdict == research.FAIL], ["$999.9M"])
        lapsed = [r for r in results if r.status == "lapsed_waiver"]
        self.assertEqual(len(lapsed), 1)
        self.assertIn("the line in the notes has changed", lapsed[0].detail)
        self.assertEqual(lapsed[0].verdict, research.WARN)

    def test_a_waiver_lapses_when_the_cited_source_changes_and_a_new_date_accepts_it_again(self):
        self.waive(FIGURE)
        research.run(self.ws, self.con)
        self.con.execute("UPDATE documents SET text = text || ' Restated.' WHERE url=?", (ANNUAL,))
        self.con.commit()
        results = research.run(self.ws, self.con)
        self.assertEqual([r.item for r in results if r.verdict == research.FAIL], ["$999.9M"])
        self.assertIn("the text of a source the line cites has changed",
                      next(r.detail for r in results if r.status == "lapsed_waiver"))
        self.waive(FIGURE.replace("2026-11-11", "2026-11-12"))
        results = research.run(self.ws, self.con)
        self.assertEqual([r.item for r in results if r.verdict == research.WAIVED], ["$999.9M"])
        self.assertFalse([r for r in results if r.check == "waivers"])

    def test_a_quotation_whose_key_is_on_its_attribution_lapses_when_that_source_changes(self):
        self.add_to_note("## 3. More\n\n> We will never cut research spending.\n\nSo wrote the chief executive (S2).")
        self.waive("quotations,01_northbridge.md,,We will never cut research spending.,Said on a call,A. Researcher,2026-11-11\n")
        self.assertEqual([r.item for r in research.run(self.ws, self.con) if r.verdict == research.WAIVED],
                         ["We will never cut research spending."])
        self.con.execute("UPDATE documents SET text = text || ' Restated.' WHERE url=?", (ORDERS,))
        self.con.commit()
        results = research.run(self.ws, self.con)
        self.assertIn("We will never cut research spending.", [r.item for r in results if r.verdict == research.FAIL])
        self.assertEqual([r.status for r in results if r.check == "waivers"], ["lapsed_waiver"])

    def test_a_waiver_on_a_line_number_holds_only_there(self):
        line = self.note.read_text(encoding="utf-8").splitlines().index("- A figure no source holds: $999.9M (S1).") + 1
        self.waive(FIGURE.replace(",,", f",{line + 1},"))
        results = research.run(self.ws, self.con)
        self.assertEqual([r.item for r in results if r.verdict == research.FAIL], ["$999.9M"])
        self.assertEqual([r.status for r in results if r.check == "waivers"], ["unused_waiver"])
        self.waive(FIGURE.replace(",,", f",{line},"))
        self.assertEqual([r.item for r in research.run(self.ws, self.con) if r.verdict == research.WAIVED], ["$999.9M"])

    def test_a_waiver_that_matches_nothing_is_a_warning(self):
        self.waive(FIGURE, "numbers,01_northbridge.md,,$123.4M,A figure since removed,A. Researcher,2026-11-11\n")
        results = research.run(self.ws, self.con)
        unused = [r for r in results if r.status == "unused_waiver"]
        self.assertEqual([(r.item, r.verdict) for r in unused], [("$123.4M", research.WARN)])
        self.assertIn("checks/waivers.csv:3", unused[0].detail)
        out, _, code = self.cli("check")
        self.assertEqual(code, 0)
        self.assertIn("waivers     1 unused waiver", out)

    def test_the_same_item_on_two_lines_is_pinned_to_both_on_its_first_run(self):
        self.add_to_note("## 3. Again\n\n- Again, a figure no source holds: $999.9M (S1).")
        self.waive(FIGURE)
        results = research.run(self.ws, self.con)
        self.assertEqual(len([r for r in results if r.verdict == research.WAIVED]), 2)
        self.assertFalse([r for r in results if r.check == "waivers"])
        results = research.run(self.ws, self.con)
        self.assertEqual(len([r for r in results if r.verdict == research.WAIVED]), 2)

    def test_the_standalone_quotes_and_arithmetic_honour_waivers(self):
        self.add_to_note(EXTRA)
        self.fetch()
        out, _, code = self.cli("quotes")
        self.assertEqual(code, 1)
        out, _, code = self.cli("arithmetic")
        self.assertEqual(code, 1)
        self.waive('quotes,01_northbridge.md,,Growth  before discipline,Quoted from a translation,A. Researcher,2026-11-11\n',
                   "arithmetic,01_northbridge.md,,12 + 8 = 21,One deal was counted twice in the release,A. Researcher,2026-11-11\n")
        out, _, code = self.cli("quotes")
        self.assertEqual(code, 0)
        self.assertIn("waived [S1]", out)
        self.assertIn("Quoted from a translation", out)
        out, _, code = self.cli("arithmetic")
        self.assertEqual(code, 0)
        self.assertIn("1 ok, 0 wrong, 0 unparsed, 1 waived", out)

    def test_the_standalone_citations_honour_a_waiver_by_key(self):
        self.add_to_note("- A report we couldn't find (S9).")
        _, _, code = self.cli("citations")
        self.assertEqual(code, 1)
        self.waive("citations,01_northbridge.md,,S9,The report is on paper in the archive,A. Researcher,2026-11-11\n")
        out, _, code = self.cli("citations")
        self.assertEqual(code, 0)
        self.assertIn("waived: S9 is cited", out)
        self.assertIn("0 error(s), 0 warning(s), 1 waived", out)


class Reading(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        (root / "checks").mkdir(parents=True)
        self.ws = workspace.Workspace(root, "test")

    def write(self, text):
        (self.ws.root / "checks" / "waivers.csv").write_text(text, encoding="utf-8")

    def test_no_file_means_no_waivers(self):
        self.assertEqual(waivers.read(self.ws), [])

    def test_rows_are_read_with_aliases_comments_and_blank_lines_skipped(self):
        self.write(HEADER + FIGURE + "\n#numbers,a note,,1,,,\nQuotes,01_northbridge.md,12,a phrase,Translation,A. Researcher,2026-11-11\n")
        found = waivers.read(self.ws)
        self.assertEqual([(w.check, w.line_no, w.row) for w in found], [("numbers", None, 2), ("quotations", 12, 5)])

    def test_a_row_missing_a_reason_a_check_or_a_date_says_which_line(self):
        for row, said in ((FIGURE.replace("Confirmed by phone with the press office", ""), "this one has no reason"),
                          (FIGURE.replace("numbers", "spelling"), "'spelling' isn't a check"),
                          (FIGURE.replace("2026-11-11", "last week"), "accepted_on must be a date"),
                          (FIGURE.replace(",,", ",twelve,"), "line_no must be a line number")):
            self.write(HEADER + row)
            with self.assertRaises(workspace.WorkspaceError) as raised:
                waivers.read(self.ws)
            self.assertIn("waivers.csv:2", str(raised.exception))
            self.assertIn(said, str(raised.exception))

    def test_a_file_without_the_columns_is_refused(self):
        self.write("check,note_file,item\nnumbers,a.md,1\n")
        with self.assertRaises(workspace.WorkspaceError) as raised:
            waivers.read(self.ws)
        self.assertIn("no reason, accepted_by, accepted_on column", str(raised.exception))

    def test_items_match_by_words_and_figures_by_digits(self):
        self.assertTrue(waivers.same_item("numbers", "$999.9M", "999.9"))
        self.assertTrue(waivers.same_item("numbers", "1,757", "1757 staff"))
        self.assertFalse(waivers.same_item("numbers", "999.9", "999.90"))
        self.assertFalse(waivers.same_item("numbers", "no digits", "no digits"))
        self.assertTrue(waivers.same_item("quotations", "We  Shipped", "we shipped"))
        self.assertFalse(waivers.same_item("quotations", "we shipped", "we shipped it"))

    def test_rewording_the_reason_keeps_the_waiver_but_a_new_date_makes_a_new_one(self):
        self.write(HEADER + FIGURE + FIGURE.replace("Confirmed by phone", "Checked by phone") + FIGURE.replace("11-11", "11-12"))
        first, reworded, redated = waivers.read(self.ws)
        self.assertEqual(first.ident, reworded.ident)
        self.assertNotEqual(first.ident, redated.ident)


if __name__ == "__main__":
    unittest.main()
