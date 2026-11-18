"""Tests for what reading a finished report against its checks turned up: a citation's lettered year read as a figure, a
reference list's escaped addresses, a citation counted as copied text, "the Appendix" where there are several, and a
companion part's spellings. Every draft, note and source here is made up, in a throwaway copy of the example workspace."""
import json
import unittest

from support import CODE_ROOT

from drillcore import judge, names, overlap, proof, workspace
from test_judge import Judged
from test_overlap import Overlap
from test_proof import REFERENCES, Proofed


class CitedYears(Judged):
    def test_a_citations_lettered_year_is_no_figure(self):
        self.draft("Revenue was $551.1M (Northbridge Robotics 2025k; Roe 2024b, 2026m).\n")
        self.assertEqual(self.problems("numbers"), [])

    def test_the_same_writing_outside_a_citation_is_still_read(self):
        self.draft("The arm sold 2025k units.\n")
        self.assertEqual([item for _, _, item in self.problems("numbers")], ["2025k"])

    def test_only_the_year_is_set_aside_and_every_place_keeps_its_offset(self):
        line = "Up (Roe 2024k) to $560M."
        self.assertEqual(judge.without_cited_years(line), "Up (Roe      ) to $560M.")


class EscapedAddresses(Proofed):
    def test_an_address_written_with_markdowns_escapes_is_the_plain_address(self):
        escaped = REFERENCES.replace("https://example.com/northbridge/annual-2025.html",
                                     "https://example.com/northbridge/annual\\-2025.html")
        (self.ws.root / "report" / "references.md").write_text(escaped, encoding="utf-8")
        self.draft("Revenue fell (Northbridge Robotics 2025a).\n")
        warned = [item for _, _, verdict, item in self.found("references") if verdict == proof.WARN]
        self.assertNotIn("Northbridge Robotics 2025a", warned)


class CitationsAreNotCopying(Overlap):
    def test_a_citation_naming_a_court_in_full_is_no_shared_passage(self):
        url = "https://example.com/court/judgment.pdf"
        self.source(url, "United States District Court for the Northern District of Somewhere, Western Division. Judgment.")
        self.draft("The jury agreed (United States District Court for the Northern District of Somewhere, Western Division 2025).\n")
        self.assertEqual(overlap.check(self.ws, self.con), [])


class TheAppendix(Proofed):
    APPENDICES = "# Appendix\n\n## Appendix A. Data\n\nTables.\n\n## Appendix B. Log\n\n**Entry 4.** A prompt.\n"

    def test_the_appendix_warns_where_there_are_lettered_ones_and_names_the_part_holding_the_entry(self):
        (self.ws.root / "report" / "appendix.md").write_text(self.APPENDICES, encoding="utf-8")
        self.settings(references=["report/references.md"], companions=["report/appendix.md"])
        self.draft("*Drafted with Claude; AI citation in the Appendix, entry 4.*\n\nSee Appendix B and the Appendix A tables.\n")
        found = [r for r in proof.proof(self.ws, self.con) if r.check == "cross-references" and r.verdict != proof.PASS]
        self.assertEqual([(r.line, r.verdict, r.item) for r in found], [(1, proof.WARN, "the Appendix")])
        self.assertIn("Appendix A or Appendix B", found[0].detail)
        self.assertIn("entries it names are in Appendix B", found[0].detail)

    def test_a_single_appendix_is_the_appendix(self):
        (self.ws.root / "report" / "appendix.md").write_text("# Appendix A. Data\n\n**Entry 4.** A prompt.\n", encoding="utf-8")
        self.settings(references=["report/references.md"], companions=["report/appendix.md"])
        self.draft("AI citation in the Appendix, entry 4.\n")
        self.assertEqual(self.found("cross-references"), [])


DATED_REFERENCES = """# References

- Northbridge Robotics. 2025a. *Annual Report.* Filed March 3, 2025. Accessed May 1, 2026. https://example.com/northbridge/annual-2025.html.
- Northbridge Robotics. 2025b. "Orders." Press release, July 1, 2025. https://example.com/northbridge/orders.html.
"""


class Dates(Proofed):
    def setUp(self):
        super().setUp()
        (self.ws.root / "report" / "references.md").write_text(DATED_REFERENCES, encoding="utf-8")

    def annual(self, text: str) -> None:
        from drillcore import sourcedb
        sourcedb.keep_text(self.con, "https://example.com/northbridge/annual-2025.html", sourcedb.Extracted(None, text, "html"))
        self.con.commit()

    def test_a_date_later_than_every_work_cited_is_a_warning(self):
        self.annual("Revenue was $551.1 million. The strike ran from January 2025.")
        self.draft("The strike has been over since April 2025 (Northbridge Robotics 2025a).\n")
        found = [r for r in proof.proof(self.ws, self.con) if r.check == "dates" and r.verdict != proof.PASS]
        self.assertEqual([(r.line, r.verdict, r.item) for r in found], [(1, proof.WARN, "April 2025")])
        self.assertIn("Northbridge Robotics 2025a, is dated March 3, 2025", found[0].detail)

    def test_a_date_the_cited_source_gives_in_advance_passes(self):
        self.annual("The lock-up runs through September 14, 2025.")
        self.draft("The lock-up ended on 14 September 2025 (Northbridge Robotics 2025a).\n")
        self.assertEqual(self.found("dates"), [])

    def test_a_later_work_cited_beside_it_or_a_plan_passes(self):
        self.draft("The strike has been over since April 2025 (Northbridge Robotics 2025a, 2025b). "
                   "The plant is expected to move in December 2025 (Northbridge Robotics 2025a).\n")
        self.assertEqual(self.found("dates"), [])

    def test_a_cutoff_stated_as_absolute_is_held_to_the_works_cited(self):
        self.draft("- **Data:** nothing published after 30 June 2025.\n\nOrders rose (Northbridge Robotics 2025a, 2025b).\n")
        found = [r for r in proof.proof(self.ws, self.con) if r.check == "dates" and r.verdict != proof.PASS]
        self.assertEqual([(r.line, r.item) for r in found], [(1, "nothing published after")])
        self.assertIn("Northbridge Robotics 2025b (July 1, 2025)", found[0].detail)
        self.assertNotIn("2025a", found[0].detail)

    def test_a_cutoff_that_names_its_exception_passes(self):
        self.draft("Data: nothing published after 30 June 2025, except the orders release.\n\n"
                   "Orders rose (Northbridge Robotics 2025b).\n")
        self.assertEqual(self.found("dates"), [])


class SourceLineAuthors(Proofed):
    def test_an_author_a_source_line_names_needs_an_entry(self):
        self.draft("Costs rose (Exhibit 1).\n\n*Exhibit 1. Costs. Source: annual reports of Northbridge Robotics Ltd. and "
                   "Kestrel Arms Inc., U.S. Securities and Exchange Commission, accessed May 1, 2026.*\n\n"
                   "*Source: filings and releases of the companies named, cited in the references.*\n")
        found = [(r.line, r.verdict, r.item) for r in proof.proof(self.ws, self.con)
                 if r.check == "references" and "source line" in r.detail]
        self.assertEqual(found, [(3, proof.WARN, "Kestrel Arms Inc.")])


class CompanyRows(unittest.TestCase):
    """A company's measure stated in two tables whose rows are companies and whose columns are measures."""

    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        shutil.rmtree(root / "drafts")
        (root / "drafts").mkdir()
        self.ws = workspace.Workspace(root, "test")

    def draft(self, name: str, text: str) -> None:
        (self.ws.root / "drafts" / name).write_text(text, encoding="utf-8")

    def test_a_yearly_cell_and_a_year_from_the_lead_in_are_held_together(self):
        from drillcore import consistency
        self.draft("01_body.md", "| Company | How it grew | Revenue growth |\n|---|---|---|\n"
                                 "| Northbridge Robotics | Bought | +3.1% (2024); +41.6% (2025) with the deals |\n")
        self.draft("02_appendix.md", "**Cross-section: 2025, the latest full year**\n\n| Company | Revenue growth |\n|---|---|\n"
                                     "| Northbridge Robotics (maker) | +41.5% |\n| US machinery average | +2.0% |\n")
        found = [(pair.first.written, pair.second.written, pair.first.label) for pair in consistency.check(self.ws)]
        self.assertEqual(found, [("+41.6%", "+41.5%", "Northbridge Robotics: Revenue growth")])

    def test_rows_repeating_a_company_and_rows_naming_none_are_not_read_as_its_measure(self):
        from drillcore import consistency
        self.draft("01_deals.md", "Deals of 2025:\n\n| Buyer | Price |\n|---|---|\n| Northbridge Robotics | $12.0M |\n"
                                  "| Northbridge Robotics | $30.0M |\n")
        self.draft("02_scorecard.md", "| View | Baseline |\n|---|---|\n| Financial | -4.4% (2025) |\n| Financial | -9.6% (2025) |\n")
        self.assertEqual(consistency.check(self.ws), [])

    def test_a_bracketed_negative_before_its_percent_sign_is_negative(self):
        from drillcore import statements
        value, decimals, percent, _ = statements.amount(statements.AMOUNT.fullmatch("(12.7)%"), None)
        self.assertEqual((value, decimals, percent), (-12.7, 1, True))


class SmallFalseAlarms(Proofed):
    def test_a_companys_founding_year_in_brackets_is_no_citation(self):
        self.draft("| Origins | 2008 merger of Northbridge Robotics (1979) and Kestrel Ltd. |\n|---|---|\n"
                   "Revenue fell (Northbridge Robotics 2025a). Northbridge Robotics (2024) said so.\n")
        self.assertEqual([item for _, _, _, item in self.found("citations")], ["Northbridge Robotics 2024"])

    def test_a_citation_covers_its_own_clause_up_to_a_semicolon(self):
        self.assertEqual(proof.cited_clauses("Costs $1M each (Doe 2024; Roe 2025); restores the 20% cut"), [(0, 35)])
        self.assertEqual(proof.cited_clauses("No citation here; 20%"), [])

    def test_a_pointer_landing_on_an_uncited_line_is_a_warning(self):
        self.draft("# Report\n\n## 1. Summary\n\nAssets sold for 17.5% of their price or less (section 2).\n\n"
                   "## 2. Deals\n\nEvery asset sold went for 17.5% of its price or less.\n\n"
                   "## 3. Costs\n\nCosts fell to $412.5M of sales (section 4).\n\n## 4. Detail\n\nCosts fell to $412.5M of sales "
                   "(Northbridge Robotics 2025a).\n")
        found = [(line, item) for _, line, _, item in self.found("pointers")]
        self.assertEqual(found, [(5, "17.5%")])


class Hypothetical(Judged):
    def test_a_multiple_in_a_what_if_claims_nothing(self):
        self.draft("Doubling the weight of time would put option C ahead. Orders tripled.\n")
        self.assertEqual([item for _, _, item in self.problems("numbers")], ["tripled"])


class LegalForms(unittest.TestCase):
    def test_a_legal_form_after_a_name_is_the_same_spelling(self):
        self.assertEqual(names.spelling("Kestrel Laser Technologies Co"), "Kestrel Laser Technologies")
        self.assertEqual(names.spelling("Kestrel Capital Management LP's"), "Kestrel Capital Management")
        self.assertEqual(names.spelling("Coco"), "Coco")


class CompanionNames(unittest.TestCase):
    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        (root / "report").mkdir()
        self.ws = workspace.Workspace(root, "test")

    def companion(self, text: str) -> None:
        (self.ws.root / "report" / "appendix_c.md").write_text(text, encoding="utf-8")
        with self.ws.config_path.open("a", encoding="utf-8") as out:
            out.write("\n[proof]\ncompanions = " + json.dumps(["report/appendix_c.md"]) + "\n")

    def test_a_companion_parts_spelling_is_held_to_the_others(self):
        self.companion("# Appendix C\n\nThe NorthBridge Robotics notes are held by the author.\n")
        found = {spelling: group for group in names.check(self.ws) for spelling in group.spellings}
        self.assertIn("NorthBridge Robotics", found)
        self.assertIn("report/appendix_c.md", {mention.file for mention in found["NorthBridge Robotics"].mentions})

    def test_a_reference_lists_titles_keep_their_sources_spelling(self):
        self.companion("# Appendix C\n\nNotes.\n\n## References\n\n- NorthBridge Robotics. 2026. *Annual Report.*\n")
        every = {spelling for group in names.check(self.ws) for spelling in group.spellings}
        self.assertNotIn("NorthBridge Robotics", every)


if __name__ == "__main__":
    unittest.main()
