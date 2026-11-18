"""Tests for section coverage: a workspace names sections of its notes, and `check` fails one with too few lines held
to a source."""
import os
import shutil
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

from support import CODE_ROOT, run_cli

from drillcore import research, sections, sourcedb, workspace

ANNUAL = "https://example.com/northbridge/annual-2025.html"
ORDERS = "https://example.com/northbridge/orders.html"
PAGES = {
    ANNUAL: b"<html><body><table><tr><td>Revenue</td><td>551.1</td><td>572.5</td></tr><tr><td>Gross margin</td><td>41.2%</td>"
            b"<td>44.9%</td></tr><tr><td>Staff</td><td>1,757</td><td>1,820</td></tr></table><p>Research spending was $77.3 million."
            b" Rivalry in the trade is fierce and rising.</p></body></html>",
    ORDERS: b"<html><body><p>The order book was $95.4 million, of which $67.5 million is due within a year.</p></body></html>",
}
# A fictional note laid out by forces. Rivalry rests on three lines, one under a sub-heading. Buyer power rests on one.
# Supplier power rests on none: a line citing nothing and one with nothing to judge. Substitutes takes its key from its
# heading, New entrants rests on a figure its source doesn't hold, and the working cites the source of its inputs.
NOTE = """# Industry: warehouse robots

## 1. Rivalry (S1)

- Revenue fell to $551.1M in 2025 (S1).
- The company says rivalry is "fierce and rising" (S1).

### Prices

- Gross margin fell to 41.2% (S1).

## 2. Buyer power

- Buyers are large and few.
- The order book stood at $95.4M (S2).

## 3. Supplier power

- A handful of makers supply the arms.
- Staff numbered 1,757.

## 4. Substitutes (S1)

- Gross margin held up at 41.2%.

## 5. New entrants

- Entrants spent $999.9M (S1).

## 6. Worked out

COMPUTED:

- Revenue change: -3.7% (551.1 against 572.5) (S1).

## Sources

- **S1.** Northbridge Robotics. 2026. *Annual Report 2025.* https://example.com/northbridge/annual-2025.html
- **S2.** Northbridge Robotics. 2026. "Order book update." https://example.com/northbridge/orders.html
"""
FORCES = """
[[check.sections]]
notes = ["03_*.md"]
headings = ["Rivalry", "Buyer power", "Supplier power", "Substitutes", "New entrants", "Worked out"]
min_sourced = {least}
"""
HEADER = "check,note_file,line_no,item,reason,accepted_by,accepted_on\n"
WAIVER = "sections,03_industry.md,,Supplier power,The makers of the arms publish nothing,A. Researcher,2026-11-11\n"


class Coverage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", self.root, ignore=shutil.ignore_patterns("data"))
        self.note = self.root / "research" / "03_industry.md"
        self.note.write_text(NOTE, encoding="utf-8")
        self.settings = (self.root / "workspace.toml").read_text(encoding="utf-8")
        self.ws = workspace.Workspace(self.root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)

    def rule(self, text):
        (self.root / "workspace.toml").write_text(self.settings + text, encoding="utf-8")

    def fetch(self, pages=None):
        pages = PAGES if pages is None else pages

        def get(url):
            body = pages.get(url)
            return (200, "text/html", url, body, None) if body else (404, "", url, b"", "HTTP 404")
        sourcedb.record_sources(self.ws, self.con)
        sourcedb.fetch(self.ws, self.con, get=get, say=lambda _: None)

    def covered(self, least=1, pages=None):
        self.rule(FORCES.format(least=least))
        self.fetch(pages)
        return {r.item: (r.status, r.detail) for r in research.run(self.ws, self.con) if r.check == "sections"}

    def cli(self, *argv):
        with mock.patch.dict(os.environ, {"DRILLCORE_HOME": str(self.root)}):
            return run_cli(*argv)

    def test_a_section_with_enough_lines_held_to_a_source_is_covered_and_one_without_is_thin(self):
        found = self.covered()
        self.assertEqual(found["Rivalry"][0], "covered")
        self.assertEqual(found["Buyer power"][0], "covered")
        status, detail = found["Supplier power"]
        self.assertEqual(status, "thin")
        self.assertEqual(detail, "0 of 1 line held to a source. Under it: 2 lines: 1 citing no source, "
                                 "1 with nothing the checks judge against a source")
        self.assertEqual(research.VERDICT[status], research.FAIL)

    def test_min_sourced_sets_how_many_lines_a_section_needs(self):
        found = self.covered(least=2)
        self.assertEqual(found["Rivalry"][0], "covered")
        self.assertEqual(found["Buyer power"],
                         ("thin", "1 of 2 lines held to a source. Under it: 2 lines: 1 held to a source, "
                                  "1 with nothing the checks judge against a source"))

    def test_lines_under_a_sub_heading_count_and_lines_after_the_next_heading_at_its_level_dont(self):
        self.assertEqual(self.covered(least=3)["Rivalry"][0], "covered")
        self.assertEqual(self.covered(least=4)["Rivalry"][0], "thin")

    def test_keys_inherited_from_the_heading_count(self):
        self.assertEqual(self.covered()["Substitutes"][0], "covered")

    def test_a_line_that_fails_its_check_still_counts_since_that_check_reports_it(self):
        self.rule(FORCES.format(least=1))
        self.fetch()
        results = research.run(self.ws, self.con)
        self.assertIn(("numbers", "not_in_source", "$999.9M"),
                      [(r.check, r.status, r.item) for r in results if r.note == "03_industry.md"])
        self.assertEqual(next(r.status for r in results if r.item == "New entrants"), "covered")

    def test_a_worked_out_row_whose_inputs_are_traced_counts(self):
        self.assertEqual(self.covered()["Worked out"][0], "covered")

    def test_a_worked_out_row_whose_inputs_arent_traced_doesnt(self):
        without = {**PAGES, ANNUAL: PAGES[ANNUAL].replace(b"572.5", b"570.0")}
        self.assertEqual(self.covered(pages=without)["Worked out"][0], "thin")

    def test_a_section_waiting_on_a_source_with_no_text_isnt_judged(self):
        found = self.covered(pages={ANNUAL: PAGES[ANNUAL]})
        status, detail = found["Buyer power"]
        self.assertEqual(status, "section_not_judged")
        self.assertIn("1 waiting on a source with no text held", detail)
        self.assertEqual(research.VERDICT[status], research.NOT_JUDGED)

    def test_a_heading_missing_from_a_note_fails_and_a_rule_that_covers_no_note_is_a_warning(self):
        self.rule('[[check.sections]]\nnotes = ["03_*.md"]\nheadings = "Threat of substitutes"\n'
                  '[[check.sections]]\nnotes = ["09_*.md"]\nheadings = "Rivalry"\n')
        self.fetch()
        found = [(r.status, r.note, r.line_no, r.item, r.verdict) for r in research.run(self.ws, self.con) if r.check == "sections"]
        self.assertEqual(found, [("section_missing", "03_industry.md", 0, "Threat of substitutes", research.FAIL),
                                 ("unused_rule", "", 0, "09_*.md", research.WARN)])
        out, _, code = self.cli("check")
        self.assertEqual(code, 1)
        self.assertIn("FAIL sections 03_industry.md [-] 'Threat of substitutes': no heading in the note matches", out)
        self.assertIn("WARNING sections [[check.sections]] rule 2 covers 09_*.md, which matches no note", out)

    def test_check_prints_a_line_for_sections_and_fails_a_thin_one(self):
        self.rule(FORCES.format(least=1))
        self.fetch()
        out, _, code = self.cli("check")
        self.assertEqual(code, 1)
        self.assertIn("sections    1 thin, 5 covered", out)
        self.assertIn("FAIL sections 03_industry.md:17 [-] 'Supplier power': 0 of 1 line held to a source.", out)
        self.assertIn("held to a source:", out)

    def test_a_waiver_accepts_a_thin_section_and_lapses_when_a_line_under_it_changes(self):
        (self.root / "checks" / "waivers.csv").write_text(HEADER + WAIVER, encoding="utf-8")
        self.rule(FORCES.format(least=1))
        self.fetch()
        results = research.run(self.ws, self.con)
        thin = next(r for r in results if r.item == "Supplier power")
        self.assertEqual(thin.verdict, research.WAIVED)
        self.assertIn("publish nothing", thin.waiver)
        self.assertFalse([r for r in results if r.check == "waivers"])
        self.note.write_text(NOTE.replace("A handful of makers", "Three makers"), encoding="utf-8")
        results = research.run(self.ws, self.con)
        self.assertEqual(next(r for r in results if r.item == "Supplier power").verdict, research.FAIL)
        self.assertIn("the section in the notes has changed", next(r.detail for r in results if r.status == "lapsed_waiver"))

    def test_without_a_rule_nothing_about_sections_is_checked_or_said(self):
        self.fetch()
        self.assertFalse([r for r in research.run(self.ws, self.con) if r.check == "sections"])
        out, _, _ = self.cli("check")
        self.assertNotIn("sections", out)

    def test_a_rule_that_cant_be_used_is_refused_saying_which(self):
        for text, said in (('[[check.sections]]\nmin_sourced = 2\n', "needs `headings`"),
                           ('[[check.sections]]\nheadings = []\n', "`headings` must be a name or a list"),
                           ('[[check.sections]]\nheadings = "Rivalry"\nmin_sourced = 0\n', "`min_sourced` must be a whole number"),
                           ('[[check.sections]]\nheadings = "Rivalry"\nmin_sourced = true\n', "`min_sourced` must be a whole number"),
                           ('[[check.sections]]\nheadings = "Rivalry"\nmin_source = 2\n', "min_source isn't a setting")):
            with self.subTest(text=text):
                self.rule(text)
                with self.assertRaises(workspace.WorkspaceError) as refused:
                    sections.rules(self.ws)
                self.assertIn("[[check.sections]] rule 1", str(refused.exception))
                self.assertIn(said, str(refused.exception))


class Headings(unittest.TestCase):
    def test_a_heading_matches_on_its_words_without_its_number_keys_or_case(self):
        for written in ("## 4. Buyer power (S3)", "### 2.3 Buyer Power", "## 3) buyer  power", "## IV. Buyer power (S3 p.12, S4)",
                        "# Buyer power"):
            with self.subTest(written=written):
                self.assertEqual(sections.heading_words(written), "buyer power")

    def test_nothing_looser_matches(self):
        self.assertEqual(sections.heading_words("## Buyer power in Asia"), "buyer power in asia")
        self.assertEqual(sections.heading_words("## Buyer power (2025)"), "buyer power (2025)")
        self.assertEqual(sections.heading_words("## 2025 results"), "2025 results")

    def test_a_rule_covers_the_notes_its_patterns_match_or_every_note(self):
        rule = sections.Rule(1, ("Rivalry",), ("03_*.md",), 1)
        self.assertTrue(rule.covers("03_industry.md"))
        self.assertTrue(rule.covers("03_Industry.MD"))
        self.assertFalse(rule.covers("01_northbridge.md"))
        self.assertTrue(sections.Rule(1, ("Rivalry",), (), 1).covers("01_northbridge.md"))


if __name__ == "__main__":
    unittest.main()
