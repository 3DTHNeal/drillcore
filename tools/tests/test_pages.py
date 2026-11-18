"""Tests for pinpoint citations: reading `S1 p.47` and `S1 §Note 12`, keeping a PDF's pages, and holding a figure or a
quotation to the page or section cited."""
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

from support import CODE_ROOT

from drillcore import pages, quotes, sourcedb, workspace
from drillcore.pages import Pin

REPORT = "https://example.com/northbridge/annual-2025.pdf"
# Three pages: a cover, the results printed as page 1, and a note printed as page 2.
LEAVES = ["Northbridge Robotics\nAnnual Report 2025",
          "Results\nRevenue was $551.1 million for 2025.\n\"Discipline before growth\" set the year.\n1",
          "Note 12 Staff\nStaff at year end were 1,757.\nNote 13 Leases\nLease payments were 12.4 million.\n2"]


class Reading(unittest.TestCase):
    def test_a_pinpoint_is_read_after_the_key_it_belongs_to(self):
        known = {"S1", "S2"}
        self.assertEqual(pages.pins_in("Revenue $551.1M (S1 p.47)", known), {"S1": Pin("S1", 47, 47)})
        self.assertEqual(pages.pins_in("(S1, pp. 47-48; S2 §Note 12)", known),
                         {"S1": Pin("S1", 47, 48), "S2": Pin("S2", section="Note 12")})
        self.assertEqual(pages.pins_in("S1 § 2.3 says", known), {"S1": Pin("S1", section="2.3")})
        self.assertEqual(pages.pins_in("(S9 p.4)", known), {})
        self.assertEqual([pin.shown() for pin in (Pin("S1", 4, 4), Pin("S1", 4, 6), Pin("S1", section="Note 2"))],
                         ["p.4", "pp.4-6", "§Note 2"])

    def test_a_pinpoints_digits_arent_a_figure(self):
        row = sourcedb.without_keys("- Revenue $551.1M (S1 pp.147-148)", {"S1": []})
        self.assertEqual([raw for raw, *_ in sourcedb.numbers_in(row)], ["551.1"])

    def test_the_number_printed_on_a_page_is_read_from_a_line_of_its_own(self):
        self.assertEqual(pages.folio("Heading\ntext\n- 47 -"), "47")
        self.assertEqual(pages.folio("Page 3 of 9\ntext"), "3")
        self.assertEqual(pages.folio("Revenue 551\nmore text\nand more"), "")

    def test_pages_are_joined_with_where_each_starts(self):
        text, spans = pages.joined(["one\n1", "", "two\n2"])
        self.assertEqual(text, "one\n1\ntwo\n2")
        self.assertEqual(spans, [(0, 5, "1"), (5, 5, ""), (6, 11, "2")])

    def test_a_pdfs_pages_are_kept_as_it_is_read(self):
        done = subprocess.CompletedProcess([], 0, ("\f".join(LEAVES) + "\f").encode("utf-8"), b"")
        with tempfile.TemporaryDirectory() as tmp:
            ws = workspace.Workspace(Path(tmp).resolve())
            _, raw = sourcedb.save_raw(ws, b"%PDF-1.4", ".pdf")
            with mock.patch.object(sourcedb.shutil, "which", return_value="pdftotext"), \
                    mock.patch.object(sourcedb.subprocess, "run", return_value=done):
                read = sourcedb.extract(ws, raw, ".pdf", "application/pdf")
        assert read.text is not None and read.pages is not None
        self.assertEqual(len(read.pages), 3)
        self.assertEqual([printed for _, _, printed in read.pages], ["", "1", "2"])
        start, end, _ = read.pages[2]
        self.assertTrue(read.text[start:end].startswith("Note 12 Staff"))


class Regions(unittest.TestCase):
    TEXT = "Contents\nNote 12 Staff 9\nNote 13 Leases 10\nNote 12 Staff\nStaff were 1,757.\nNote 13 Leases\nLeases 12.4.\n"

    def test_a_section_runs_from_its_heading_to_the_next_numbered_the_same_way(self):
        stretches, why = pages.section_region(self.TEXT, Pin("S1", section="Note 12"))
        assert stretches is not None
        there = pages.region_text(self.TEXT, stretches)
        self.assertIn("1,757", there)
        self.assertNotIn("12.4", there)
        self.assertEqual(why, "")

    def test_a_section_that_cant_be_found_isnt_judged(self):
        self.assertEqual(pages.section_region(self.TEXT, Pin("S1", section="Note 40"))[0], None)
        stretches, why = pages.section_region(self.TEXT, Pin("S1", section="Revenue recognition"))
        self.assertIsNone(stretches)
        self.assertIn("only a numbered section", why)

    def test_a_bare_number_names_a_numbered_heading(self):
        text = "1 Overview\nWords.\n2.3 Revenue\nRevenue 551.1.\n2.4 Costs\nCosts 300.\n"
        stretches, _ = pages.section_region(text, Pin("S1", section="2.3"))
        assert stretches is not None
        self.assertEqual(pages.region_text(text, stretches), "2.3 Revenue\nRevenue 551.1.\n")


class Held(unittest.TestCase):
    """A note citing a PDF report by page, checked by `figures` and `quotes`."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        self.ws = workspace.Workspace(root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)
        (root / "research" / "01_northbridge.md").unlink()

    def write(self, note: str, keep_pages: bool = True) -> None:
        (self.ws.root / "research" / "02_report.md").write_text(note + f"\n\n## Sources\n\n- **S1.** Annual report. {REPORT}\n",
                                                                 encoding="utf-8")
        sourcedb.record_sources(self.ws, self.con)
        text, spans = pages.joined(LEAVES)
        sourcedb.keep_text(self.con, REPORT, sourcedb.Extracted(None, text, "pdftotext", spans if keep_pages else None))

    def figures(self) -> dict[str, tuple[str, str]]:
        sourcedb.check_figures(self.ws, self.con)
        return {text: (status, detail) for text, status, detail in self.con.execute("SELECT number_text, status, detail FROM note_figures")}

    def test_a_figure_on_the_page_cited_is_found(self):
        # Page 2 counted from the front, or the page printed 1: both hold it.
        for pin in ("p.2", "p.1", "pp.1-3"):
            with self.subTest(pin):
                self.write(f"- Revenue for 2025 was $551.1M (S1 {pin}).")
                self.assertEqual(self.figures()["551.1"][0], "found")

    def test_a_figure_in_the_source_but_not_on_the_page_cited_is_said_so(self):
        self.write("- Staff at year end: 1,757 (S1 p.1).")
        self.assertEqual(self.figures()["1,757"], ("not_on_cited_page", "in the source, but not at page 1"))
        self.write("- Staff at year end: 1,757 (S1 p.40).")
        self.assertEqual(self.figures()["1,757"], ("not_on_cited_page", "in the source, but not at page 40: the source has 3 pages"))

    def test_a_figure_is_held_to_the_section_cited(self):
        self.write("- Staff at year end: 1,757 (S1 §Note 12).")
        self.assertEqual(self.figures()["1,757"][0], "found")
        self.write("- Staff at year end: 1,757 (S1 §Note 13).")
        self.assertEqual(self.figures()["1,757"][0], "not_in_cited_section")

    def test_a_page_that_cant_be_read_isnt_judged(self):
        self.write("- Staff at year end: 1,757 (S1 p.1).", keep_pages=False)
        self.assertEqual(self.figures()["1,757"], ("found", "p.1 not judged: its pages weren't kept when it was read; "
                                                             "`fetch --reread` reads it again with them"))

    def test_check_holds_figures_and_quotations_to_the_page_cited(self):
        from drillcore import research
        self.write('- Staff at year end: 1,757 (S1 p.3).\n- Revenue for 2025: $551.1M (S1 p.3).\n'
                   '- The report says "discipline before growth" set the year (S1 p.3).')
        results = {(r.check, r.line_no): r for r in research.run(self.ws, self.con)}
        self.assertEqual(results["numbers", 1].status, "supported")
        self.assertEqual(results["numbers", 2].status, "not_on_cited_page")
        self.assertIn("in the cited source, but not at page 3 of S1", results["numbers", 2].detail)
        self.assertEqual((results["quotations", 3].status, results["quotations", 3].verdict), ("not_on_cited_page", research.FAIL))

    def test_a_quotation_is_held_to_the_page_cited(self):
        self.write('- The report says "discipline before growth" set the year (S1 p.1).')
        self.assertEqual([quote.status for quote in quotes.examine(self.ws, self.con)], ["exact"])
        self.write('- The report says "discipline before growth" set the year (S1 p.3).')
        found = quotes.examine(self.ws, self.con)
        self.assertEqual([(quote.status, quote.detail) for quote in found],
                         [("not_on_cited_page", f"in {REPORT}, but not at page 3")])


if __name__ == "__main__":
    unittest.main()
