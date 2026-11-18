"""Tests for `proof`: a draft held to itself and the workspace. Every draft, reference and source here is made up, and
lives in a throwaway copy of the example workspace."""
import json
import shutil
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

from support import CODE_ROOT, run_cli

from drillcore import identity, proof, record_log, sessions, sourcedb, workspace

ANNUAL = "https://example.com/northbridge/annual-2025.html"
REFERENCES = """# References

- Harbor Arms Ltd. (海港公司). 2026. *Annual Report 2025.* https://example.com/harbor/annual-2025.html.
- Northbridge Robotics. 2025a. *Annual Report.* https://example.com/northbridge/annual-2025.html.
- Northbridge Robotics. 2025b. "Orders." https://example.com/northbridge/orders.html.
- Roe, Jane, Al Poe, and Bo Coe. 2024. "Arms That Learn." *Journal of Robots* 3 (1): 1–9.
- Thomas, Douglas S., and Stanley W. Gilbert. 2014. *Costs and Cost Effectiveness.* NIST.
- U.S. Securities and Exchange Commission. n.d.-a. "Company Facts." https://data.sec.gov/api/xbrl/companyfacts/CIK0009999999.json.
- U.S. Securities and Exchange Commission. n.d.-b. "Company Facts: Northbridge." https://data.sec.gov/api/xbrl/companyconcept/CIK0009999999/.
- Uncited Press. 2020. *A Book Nobody Cites.* https://example.com/nowhere.html.

## Changes made

- Northbridge Robotics 2025b added after review.
"""


class Proofed(unittest.TestCase):
    """A workspace of its own for each test, with the example's notes, a reference list and no drafts."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        shutil.rmtree(root / "drafts")
        (root / "drafts").mkdir()
        (root / "report").mkdir()
        (root / "report" / "references.md").write_text(REFERENCES, encoding="utf-8")
        self.ws = workspace.Workspace(root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)
        sourcedb.record_sources(self.ws, self.con)
        self.settings(references=["report/references.md"])

    def settings(self, **proofing: list[str]) -> None:
        """The example's settings, with a [proof] table of the lists given."""
        table = "".join(f"{key} = {json.dumps(values, ensure_ascii=False)}\n" for key, values in proofing.items())
        self.ws.config_path.write_text((CODE_ROOT / "example" / "workspace.toml").read_text(encoding="utf-8")
                                       + (f"\n[proof]\n{table}" if proofing else ""), encoding="utf-8")

    def draft(self, text: str, name: str = "01_draft.md") -> Path:
        path = self.ws.root / "drafts" / name
        path.write_text(text, encoding="utf-8")
        return path

    def found(self, check: str) -> list[tuple[str, int, str, str]]:
        return [(r.file, r.line, r.verdict, r.item) for r in proof.proof(self.ws, self.con) if r.check == check and r.verdict != proof.PASS]

    def run_here(self, *argv: str) -> tuple[str, str, int]:
        with mock.patch.dict(workspace.os.environ, {identity.HOME_VARIABLE: str(self.ws.root)}):
            return run_cli(*argv)


class Citations(Proofed):
    def test_each_citation_names_an_entry(self):
        self.draft("# Draft\n\nRevenue fell (Northbridge Robotics 2025a, 2025b; Roe et al. 2024, 45). Costs were measured "
                   "(see Thomas and Gilbert 2014). Harbor grew (Harbor Arms Ltd. (海港公司) 2026). Facts came from the SEC "
                   "(author's calculation from U.S. Securities and Exchange Commission n.d.-a, n.d.-b).\n\n"
                   "*Exhibit 1. Revenue. Source: Northbridge Robotics 2025a; Roe et al. 2024.*\n\nExhibit 1 shows it.\n")
        self.assertEqual(self.found("citations"), [])
        self.assertEqual([item for _, _, _, item in self.found("references")],
                         ["Harbor Arms Ltd. (海港公司) 2026", "Uncited Press 2020", "Uncited Press 2020"])

    def test_a_year_the_list_doesnt_have_fails_and_an_unknown_author_warns(self):
        self.draft("Revenue fell (Northbridge Robotics 2025c). The standard was frozen (LTE 2008).\n")
        self.assertEqual(self.found("citations"), [("01_draft.md", 1, "fail", "Northbridge Robotics 2025c"),
                                                   ("01_draft.md", 1, "warn", "LTE 2008")])

    def test_brackets_that_arent_a_citation_are_passed_over(self):
        self.draft("Sales rose (Q3 2026), as expected (up from 2024), and margins held (33.5% in 2025; author's estimate).\n"
                   "The rivals (Harbor, Kestrel and others 2021) were smaller, and one went (Osprey, sold in 2018).\n")
        self.assertEqual(self.found("citations"), [])

    def test_a_narrative_citation_or_a_label_cites_an_entry(self):
        self.settings()
        self.draft("# Draft\n\nKestrel and Lark (2023) measured the arms. Roe et al. (2024) disagreed.\n\n*Framework: Poe 2019.*\n\n"
                   "## References\n\n- Kestrel, Ann, and Bo Lark. 2023. *Arms.*\n- Poe, Al. 2019. *Frames.*\n"
                   "- Roe, Jane, and Al Poe. 2024. *Hands.*\n- Uncited, Una. 2020. *Nothing.*\n")
        self.assertEqual([item for _, _, _, item in self.found("references")], ["Uncited, Una 2020"])

    def test_a_narrative_citation_is_held_to_the_list(self):
        self.draft("Roe et al. (2024, 45) measured the arms, as Roe et al. (2023) had not. Thomas and Gilbert's (2014) costs "
                   "held. Northbridge Robotics (2025a, 2025c) reported orders.\n"
                   "Doe et al. (2022) disagree. Revenue (2024) and Kestrel and Lark (2023) are no citations of the list's.\n")
        found = [(r.line, r.verdict, r.item, r.detail) for r in proof.proof(self.ws, self.con) if r.check == "citations" and r.item]
        self.assertEqual([(line, verdict, item) for line, verdict, item, _ in found], [
            (1, "warn", "Roe et al. 2023"), (1, "warn", "Northbridge Robotics 2025c"), (2, "warn", "Doe et al. 2022")])
        self.assertEqual(found[0][3], "the list has Roe et al. for 2024, not 2023")
        self.assertIn("no entry of the reference list has this author", found[2][3])

    def test_the_names_before_the_year_are_read_as_few_as_name_the_entry(self):
        self.draft("As Roe et al. (2023) and the UK. Roe (2022) say, In Northbridge Robotics (2024) it fell.\n")
        self.assertEqual([item for _, _, _, item in self.found("citations")],
                         ["Roe et al. 2023", "Roe 2022", "Northbridge Robotics 2024"])

    def test_an_entry_isnt_cited_by_its_own_line(self):
        self.settings()
        self.draft("# Draft\n\nRevenue fell.\n\n## References\n\n- Kestrel Ltd. 2024. *Report.*\n")
        self.assertEqual([(verdict, item) for _, _, verdict, item in self.found("references")], [("warn", "Kestrel Ltd 2024")])

    def test_a_draft_with_its_own_list_needs_no_setting(self):
        self.settings()
        self.draft("# Draft\n\nRevenue fell (Kestrel 2024).\n\n## Works cited\n\n- Kestrel. 2024. *Report.*\n")
        self.assertEqual(self.found("citations"), [])

    def test_no_list_at_all_is_said(self):
        self.settings()
        self.draft("Revenue fell (Kestrel 2024).\n")
        [result] = [r for r in proof.proof(self.ws, self.con) if r.check == "citations"]
        self.assertEqual(result.verdict, proof.WARN)
        self.assertIn("no reference list was found", result.detail)


class References(Proofed):
    def test_an_entry_twice_fails(self):
        (self.ws.root / "report" / "references.md").write_text(
            REFERENCES.replace("## Changes made", "- Northbridge Robotics. 2025a. *Another title.*\n\n## Changes made"), encoding="utf-8")
        self.draft("Revenue fell (Northbridge Robotics 2025a).\n")
        failed = [(line, item) for _, line, verdict, item in self.found("references") if verdict == "fail"]
        self.assertEqual(failed, [(12, "Northbridge Robotics 2025a")])

    def test_an_address_no_note_cites_is_a_warning_but_the_secs_data_isnt(self):
        self.settings(references=["report/references.md"])
        with self.ws.config_path.open("a", encoding="utf-8") as out:
            out.write("\n[[sec.company]]\ncik = 9999999\nname = \"Northbridge Robotics\"\n")
        self.draft("Revenue fell (Northbridge Robotics 2025a; U.S. Securities and Exchange Commission n.d.-a, n.d.-b; Uncited Press 2020; "
                   "Harbor Arms Ltd. (海港公司) 2026; Northbridge Robotics 2025b; Roe et al. 2024; Thomas and Gilbert 2014).\n")
        found = [(r.item, r.detail) for r in proof.proof(self.ws, self.con) if r.check == "references" and r.verdict != proof.PASS]
        self.assertEqual([item for item, _ in found], ["Harbor Arms Ltd. (海港公司) 2026", "Uncited Press 2020"])
        self.assertIn("no source the notes cite", found[-1][1])

    def test_an_address_the_settings_accept_passes_with_their_reason(self):
        with self.ws.config_path.open("a", encoding="utf-8") as out:
            out.write('\n[assay.accept_addresses]\n"https://example.com/nowhere.html" = "a book cited for its framework"\n')
        self.draft("Revenue fell (Uncited Press 2020; Harbor Arms Ltd. (海港公司) 2026).\n")
        found = [(r.verdict, r.item, r.detail) for r in proof.proof(self.ws, self.con) if r.check == "references" and r.item]
        self.assertIn(("pass", "Uncited Press 2020", "its web address is no source the notes cite, and [assay.accept_addresses] "
                       "accepts example.com/nowhere.html: a book cited for its framework"), found)
        self.assertIn("Harbor Arms Ltd. (海港公司) 2026", [item for verdict, item, _ in found if verdict == "warn"])


class CitedFigures(Proofed):
    def test_a_figure_the_cited_source_doesnt_hold_is_a_warning(self):
        sourcedb.keep_text(self.con, ANNUAL, sourcedb.Extracted(None, "Revenue was $551.1 million. Staff numbered 1,757.", "html"))
        self.con.commit()
        self.draft("Revenue was $551.1M with 1,757 staff (Northbridge Robotics 2025a). Orders were $612.4M (Northbridge Robotics 2025a).\n")
        self.assertEqual(self.found("cited figures"), [("01_draft.md", 1, "warn", "$612.4M")])

    def test_a_narrative_citation_holds_its_sentence_to_its_source(self):
        sourcedb.keep_text(self.con, ANNUAL, sourcedb.Extracted(None, "Revenue was $551.1 million.", "html"))
        self.con.commit()
        self.draft("Revenue was $551.1M (Northbridge Robotics 2025a). Northbridge Robotics (2025a) gives orders of $612.4M.\n")
        self.assertEqual(self.found("cited figures"), [("01_draft.md", 1, "warn", "$612.4M")])

    def test_a_figure_labelled_as_the_authors_working_is_traced_to_the_notes_working(self):
        sourcedb.keep_text(self.con, ANNUAL, sourcedb.Extracted(None, "Revenue was $551.1 million, against $572.5 million.", "html"))
        self.con.commit()
        # The example's notes work out the 3.7% fall under "COMPUTED from the table above".
        self.draft("# Draft\n\nRevenue fell 3.7% (author's calculation from Northbridge Robotics 2025a).\n\n"
                   "Revenue fell 3.7% (Northbridge Robotics 2025a).\n\n"
                   "Revenue fell 4.1% (author's calculation from Northbridge Robotics 2025a).\n\n"
                   "Orders were $612.4M (Northbridge Robotics 2025a), and revenue fell 3.7% (summed by the author; Northbridge "
                   "Robotics 2025a).\n\n"
                   "Revenue fell 3.7% (Northbridge Robotics 2025a; author's estimate).\n\n"
                   # Read as a sentence, this ends at "p.", inside its citation; the label after it is still its own.
                   "Revenue fell 3.7% (Northbridge Robotics 2025a, p. 4; summed by the author).\n")
        found = [(r.line, r.verdict, r.item, r.detail) for r in proof.proof(self.ws, self.con) if r.check == "cited figures" and r.item]
        self.assertEqual([(line, verdict, item) for line, verdict, item, _ in found], [
            (3, "pass", "3.7%"), (5, "warn", "3.7%"), (7, "warn", "4.1%"), (9, "warn", "$612.4M"), (9, "pass", "3.7%"), (11, "warn", "3.7%"),
            (13, "pass", "3.7%")])
        self.assertIn("labelled as the author's working, not the source's figure: the notes work it out at 01_northbridge.md:", found[0][3])
        self.assertIn("it's labelled as the author's working, but no worked-out line of the notes gives it", found[2][3])
        self.assertNotIn("labelled", found[1][3])
        out, _, code = self.run_here("proof")
        self.assertIn("cited figures     0 failed, 4 warned, 3 passed with a reason given", out)
        self.assertNotIn("PASS cited figures", out)
        out, _, _ = self.run_here("proof", "--all")
        self.assertIn("PASS cited figures 01_draft.md:3 '3.7%'", out)

    def test_a_label_covers_the_figures_back_to_the_citation_before_it(self):
        def covered(sentence: str) -> list[str]:
            return [sentence[begin:end] for begin, end in proof.labelled(sentence)]
        self.assertEqual(covered("Orders were $612.4M (Roe 2024), and revenue fell 3.7% (author's calculation from Roe 2024)."),
                         [", and revenue fell 3.7% "])
        self.assertEqual(covered("Ratios of 2.46 (two years) and 3.05 (five years) give 7.8% (author's calculation; Roe 2024)."),
                         ["Ratios of 2.46 (two years) and 3.05 (five years) give 7.8% "])
        self.assertEqual(covered("Summed by the author, the lines give $9.9M (Roe 2024)."), ["Summed by the author, the lines give $9.9M (Roe 2024)."])
        self.assertEqual(covered("Revenue fell 3.7% (Roe 2024; author's estimate)."), [])

    def test_a_sentence_cut_inside_its_citation_reads_on_to_the_bracket_closing(self):
        text = "Intro. Sales fell 3.7% (Roe Ltd. 2024; summed by the author). Next (open.\n\nNew paragraph)."
        self.assertEqual(proof.closed(text, 7, "Sales fell 3.7% (Roe Ltd."), "Sales fell 3.7% (Roe Ltd. 2024; summed by the author)")
        self.assertEqual(proof.closed(text, 7, "Sales fell 3.7%."), "Sales fell 3.7%.")
        # A bracket left open to a blank line isn't read on.
        self.assertEqual(proof.closed(text, 62, "Next (open."), "Next (open.")


class CrossReferences(Proofed):
    def test_each_reference_names_a_target_that_exists(self):
        (self.ws.root / "report" / "appendix_a.md").write_text("# Appendix A. Data\n\n**Entry 4.** A prompt.\n", encoding="utf-8")
        self.settings(references=["report/references.md"], companions=["report/appendix_a.md"])
        self.draft("# Draft\n\n## 1. Results\n\n### 1.2 Costs\n\nSee section 1.2 and sections 1 and 3, Exhibit 1, Exhibit 2, "
                   "Appendix A, Appendix B and entries 4 and 5. Section 301 of the Trade Act applies (Roe 2024, section 9).\n\n"
                   "*Exhibit 1. Costs.*\n")
        self.assertEqual([item for _, _, _, item in self.found("cross-references")], ["section 3", "Exhibit 2", "Appendix B", "entry 5"])

    def test_that_date_after_two_dates_is_a_warning_naming_them(self):
        self.draft("# Draft\n\nData runs to close of business, 11 November 2025. Three filings of 12 November are kept "
                   "because they report facts as of that date.\n\n"
                   "Data runs to 11 November 2025. Filings published on 12 November are kept for facts as of the cut-off.\n\n"
                   "The plan was approved on 3 March 2025, and work began that day.\n\n"
                   "The board met on March 3, 2025. It met again on 3 March; that day it voted.\n\n"
                   "It was filed on 2025-06-30, and the 6 July report came later. Prices rose after that date.\n\n"
                   "Filed on 2025-06-30. The report came later. Prices rose after that date.\n")
        found = [r for r in proof.proof(self.ws, self.con) if r.check == "cross-references" and r.verdict != proof.PASS]
        self.assertEqual([(r.line, r.verdict, r.item) for r in found], [(3, "warn", "that date"), (11, "warn", "that date")])
        self.assertIn("could mean 12 November or 11 November 2025", found[0].detail)
        self.assertIn("could mean 6 July or 2025-06-30", found[1].detail)


class WhatADraftSays(Proofed):
    def test_the_reference_list_and_the_records_hold_no_cross_references_citations_or_sums(self):
        with self.ws.config_path.open("a", encoding="utf-8") as out:
            out.write('\n[drafts]\nrecords = ["Appendix B"]\n')
        self.draft("# Draft\n\nRevenue fell (Northbridge Robotics 2025a), as Appendix B logs.\n\n## References\n\n"
                   "- Northbridge Robotics. 2025c. *Form 8-K, Exhibit 99.1.* See section 12.\n\n## Appendix B. Prompts\n\n"
                   "Check section 7, Exhibit 4 and (Nobody 2019). Arms cost $12M and grippers $8M, a total of $25M.\n")
        for check in ("cross-references", "citations", "sums", "exhibits"):
            self.assertEqual(self.found(check), [], check)


class Provenance(Proofed):
    def test_a_summary_figure_the_body_gives_only_for_something_else_is_a_warning(self):
        self.draft("# Report\n\n## 1. Executive summary\n\nArm revenue climbed 12.5% in 2025, and gripper orders climbed 6.8%.\n\n"
                   "## 2. Results\n\nArm revenue climbed 12.5% in 2025.\n\nThe hurdle is tested from 6.8% to 10.5%.\n")
        self.assertEqual(self.found("summary"), [("01_draft.md", 5, "warn", "6.8%")])

    def test_a_figure_must_be_in_the_part_its_sentence_points_to(self):
        self.draft("# Report\n\n## 1. Results\n\n### 1.1 Arms\n\nArm revenue climbed 12.5% in 2025.\n\n### 1.2 Grippers\n\n"
                   "Gripper costs were cut.\n\n### 1.3 Orders\n\nGripper revenue slipped 3.4% in 2025.\n\n## 2. Discussion\n\n"
                   "Arm revenue climbed 12.5% (section 1). Gripper revenue slipped 3.4% (section 1.2). Gripper revenue "
                   "slipped 3.4% (sections 1.1 to 1.3).\n")
        # Only the figures no part named gives; the ones they give without a source are test_finished_report's.
        [found] = [r for r in proof.proof(self.ws, self.con) if r.check == "pointers" and r.verdict != proof.PASS
                   and "none gives it" in r.detail]
        self.assertEqual((found.line, found.verdict, found.item), (19, proof.WARN, "3.4%"))
        self.assertIn("points to section 1.2, but none gives it for anything the sentence names; it's given in section 1.3", found.detail)
        # In a list of clauses, a pointer covers its own clause: the others' figures aren't held to section 1.2. A sentence
        # of two clauses is one claim, and a semicolon between citations in brackets separates nothing.
        results = ("# Report\n\n## 1. Results\n\n### 1.1 Arms\n\nArm revenue climbed 12.5% in 2025.\n\n### 1.2 Grippers\n\n"
                   "Gripper costs were cut by 4.4%.\n\n## 2. Limits\n\n")
        self.draft(results + "- Limits: arm revenue climbed 12.5%; gripper costs were cut by 4.4% (section 1.2); prices held.\n")
        self.assertEqual([r.item for r in proof.proof(self.ws, self.con) if r.check == "pointers" and "none gives it" in r.detail], [])
        self.draft(results + "Arm revenue climbed 12.5% (Northbridge Robotics 2025a; Northbridge Robotics 2025b); section 1.2 builds on it.\n")
        self.assertEqual(self.found("pointers"), [("01_draft.md", 15, "warn", "12.5%")])


class Exhibits(Proofed):
    def test_each_exhibit_is_captioned_once_and_mentioned(self):
        self.draft("# Draft\n\n[image: Exhibit 1: costs]\n\n*Exhibit 1. Costs.*\n\nText.\n\n*Exhibit 2. Prices.*\n\n"
                   "*Exhibit 2. Prices again.*\n\nAs Exhibit 2 shows.\n")
        self.assertEqual(self.found("exhibits"), [("01_draft.md", 5, "warn", "Exhibit 1"), ("01_draft.md", 11, "fail", "Exhibit 2")])


class Sums(Proofed):
    def test_a_total_column_and_a_total_row_add_up(self):
        self.draft("| Option | Fit | Cost | Total /10 |\n|---|---|---|---|\n| A | 5 | 4 | 9 |\n| B | 3 | 2 | 6 |\n\n"
                   "| Line | $M |\n|---|---|\n| Arms | 20.5 |\n| Grippers | 10.2 |\n| Total | 30.7 |\n\n"
                   "| Line | $M |\n|---|---|\n| Arms | 20.5 |\n| Grippers | 10.2 |\n| Total | 30.0 |\n")
        self.assertEqual(self.found("sums"), [("01_draft.md", 4, "fail", "6"), ("01_draft.md", 16, "fail", "Total, $M: 20.5 + 10.2 = 30.0")])

    def test_a_total_in_prose_adds_up(self):
        self.draft("| # | Initiative | Cash |\n|---|---|---|\n| 1 | Shift research | Within the budget |\n"
                   "| 2 | Qualify plants | Up to $18M (six at $1.5M to $3.0M each) |\n| 3 | Stakes | Up to $11M |\n| 4 | Pilot | Up to $6M |\n\n"
                   "The three cash lines total about $35M.\n\nArms cost $12M and grippers $8M, a total of $25M.\n\n"
                   "Arms cost $12M and grippers $8M, a total of $20M.\n")
        self.assertEqual(self.found("sums"), [("01_draft.md", 10, "warn", "total of $25M")])


class PersonalData(Proofed):
    def test_paths_emails_handles_and_listed_terms(self):
        self.settings(references=["report/references.md"], personal=["Jo Roe"], allow=["press@northbridge.example"])
        # "alex" is a name the repository's own privacy check knows for a placeholder; proof knows no such list.
        self.draft("Nov 14, 2026 · @jroe\n\nSaved at C:\\Users\\alex\\report.md and /home/alex/notes.\n"
                   "Write to jo@example.com or press@northbridge.example. Jo Roe wrote it.\n")
        self.assertEqual(self.found("personal data"), [
            ("01_draft.md", 1, "warn", "@jroe"), ("01_draft.md", 3, "fail", "C:\\Users\\alex"), ("01_draft.md", 3, "fail", "/home/alex"),
            ("01_draft.md", 4, "fail", "jo@example.com"), ("01_draft.md", 4, "fail", "Jo Roe")])


class Spelling(Proofed):
    def test_a_british_spelling_in_american_drafts_is_warned_of(self):
        self.draft("Defense spending rose. Its color and favorite parts, and its behavior, were analyzed.\n\n"
                   "| Category | Evidence |\n|---|---|\n| Shifts in consumer behaviour or technology | In-house printing |\n")
        self.assertEqual(self.found("spelling"), [("01_draft.md", 5, "warn", "behaviour")])

    def test_the_other_way_round_too_but_never_ize_or_license(self):
        # "-ize" is Oxford spelling and "license" a British verb: neither is held against a British draft.
        self.draft("The colour of the defence centre was analysed. They organize it under licence, and license it.\n"
                   "Its behavior changed.\n")
        self.assertEqual(self.found("spelling"), [("01_draft.md", 2, "warn", "behavior")])

    def test_quotations_names_and_programmed_keep_their_spelling(self):
        self.draft('Defense and color matter. The UK "Ministry of Defence programme" said so, and the Centre for '
                   "Printing agreed; the printers were programmed.\n")
        self.assertEqual(self.found("spelling"), [])

    def test_drafts_evenly_split_or_using_neither_say_nothing(self):
        self.draft("Its colour and its behavior.\n")
        self.assertEqual(self.found("spelling"), [])


class YearLetters(Proofed):
    def test_the_example_list_is_lettered_as_it_should_be(self):
        self.draft("Revenue fell (Northbridge Robotics 2025a).\n")
        self.assertEqual(self.found("year letters"), [])

    def test_letters_run_a_b_c_within_an_author_and_year_and_a_lone_work_has_none(self):
        (self.ws.root / "report" / "references.md").write_text(
            "# References\n\n- Roe, Jane. 2024k. *One.*\n- Northbridge Robotics. 2026a. *First.*\n"
            "- Northbridge Robotics. 2026m. *Second.*\n- Northbridge Robotics. 2026c. *Third.*\n- Northbridge Robotics. 2024. *Alone.*\n"
            "- Data Office. n.d.-p. *Tables.*\n- Poe, Al. n.d. *Undated.*\n- Poe, Al. n.d.-b. *Also undated.*\n", encoding="utf-8")
        self.draft("Revenue fell (Roe 2024k; Northbridge Robotics 2026m), and again (Northbridge Robotics 2026m). Data came "
                   "from tables (Data Office n.d.-p; Poe n.d.; Poe n.d.-b).\n")
        found = {r.item: r.detail for r in proof.proof(self.ws, self.con) if r.check == "year letters" and r.verdict == proof.FAIL}
        self.assertEqual({item: detail.split(":")[0] for item, detail in found.items()}, {
            "Roe, Jane 2024k": "should be Roe, Jane 2024", "Northbridge Robotics 2026m": "should be Northbridge Robotics 2026b",
            "Data Office n.d.-p": "should be Data Office n.d.", "Poe, Al n.d.": "should be Poe, Al n.d.-a"})
        self.assertIn("lettered a to c in the order listed, and this is number 2; the drafts cite it 2 times",
                      found["Northbridge Robotics 2026m"])
        self.assertIn("so it takes no letter; the drafts cite it 1 time,", found["Roe, Jane 2024k"])


class Filings(Proofed):
    def setUp(self):
        super().setUp()
        for year in (2012, 2013, 2014):
            self.con.execute("INSERT INTO filings(cik, entity, accession, form, filing_date, report_date) VALUES (?,?,?,?,?,?)",
                             (9999999, "NORTHBRIDGE ROBOTICS LTD.", f"0000-{year}", "20-F", f"{year + 1}-03-01", f"{year}-12-31"))
        self.con.execute("INSERT INTO filings(cik, entity, accession, form, filing_date, report_date) VALUES (?,?,?,?,?,?)",
                         (9999999, "NORTHBRIDGE ROBOTICS LTD.", "0000-6k", "6-K", "2015-05-01", "2015-03-31"))
        self.con.commit()

    def test_a_form_named_for_years_the_filing_list_lacks_fails(self):
        self.draft("*Exhibit 1. Revenue, 2010 to 2014. Source: Northbridge Robotics Ltd., annual reports on Form 20-F for fiscal "
                   "2010 to 2014.*\n\nExhibit 1 shows it. Northbridge Robotics filed on Form 20-F for fiscal 2012 through "
                   "2014, and Northbridge Robotics Ltd. on Form 10-K for fiscal 2013 (Roe et al. 2024).\n")
        found = [(r.line, r.item, r.detail) for r in proof.proof(self.ws, self.con) if r.check == "filings" and r.verdict == proof.FAIL]
        self.assertEqual([(line, item) for line, item, _ in found],
                         [(1, "Form 20-F for fiscal 2010 to 2014"), (3, "Form 10-K for fiscal 2013")])
        self.assertIn("filed no 20-F for fiscal 2010 to 2011: in the filing list `sec` loaded, its 20-Fs are for fiscal 2012 "
                      "to 2014", found[0][2])
        self.assertIn("it has no 10-K at all, and its 20-F covers some of those years", found[1][2])

    def test_another_filer_of_the_name_and_an_unknown_company_arent_judged(self):
        self.draft("Source: Northbridge Robotics, Inc., annual reports on Form 10-K for fiscal 2008 to 2011.\n\n"
                   "Source: Harbor Arms, annual reports on Form 20-F for fiscal 2010 to 2011.\n")
        self.assertEqual(self.found("filings"), [])


class Numbering(Proofed):
    def test_a_records_entries_run_once_each_and_in_order_across_its_headings(self):
        (self.ws.root / "report" / "log.md").write_text(
            "# Log\n\n## Entries\n\n1. Helper AI. helper.example. November 10, 2026. \"First.\"\n\n   Follow-up.\n\n"
            "2. Helper AI. helper.example. November 10, 2026. \"Second.\"\n\n3. Third.\n\n5. Fifth.\n\n4. Fourth.\n\n"
            "## Notes\n\n- Keep it current.\n\n5. Added by another session.\n\n## Steps\n\n1. Open it.\n2. Read it.\n", encoding="utf-8")
        self.settings(references=["report/references.md"], companions=["report/log.md"])
        self.draft("Revenue fell (Northbridge Robotics 2025a).\n")
        self.assertEqual(self.found("numbering"), [("log.md", 13, "warn", "5."), ("log.md", 15, "fail", "4."),
                                                   ("log.md", 21, "fail", "5.")])
        detail = [r.detail for r in proof.proof(self.ws, self.con) if r.check == "numbering" and r.line == 21]
        self.assertEqual(detail, ["numbered twice: also at log.md:13"])
        # A log's entries, each dated in full under its "Entries" heading, are no reference list.
        self.assertEqual([file for file, _, _, _ in self.found("references") + self.found("year letters") if file == "log.md"], [])

    def test_a_drafts_record_section_is_read_and_its_analysis_isnt(self):
        self.ws.config_path.write_text(self.ws.config_path.read_text(encoding="utf-8") + '\n[drafts]\nrecords = ["Appendix B"]\n',
                                       encoding="utf-8")
        self.draft("# Draft\n\n1. A point.\n\n1. A list that starts again.\n\n3. Skipped, but this isn't a record.\n\n"
                   "## Appendix B. Log\n\n**Entry 1.** One.\n\n**Entry 2.** Two.\n\n**Entry 2.** Two again.\n")
        self.assertEqual(self.found("numbering"), [("01_draft.md", 15, "fail", "entry 2")])


LOG = """# Helper log

## Entries

1. Helper AI. helper.example. November 10, 2026. "list the open tasks". Generated: a list.

2. Helper AI. helper.example. November 11, 2026. "draft the summary". Generated: a draft.
   Follow-up in the same session, exact wording: "Yes, shorten it"; "keep the table" (answering "Shorten it?"). Generated: less.

3. Helper AI, a session another started. helper.example. November 12, 2026. The prompt, exact wording:

   > "Background: a long prompt
   > written by the other session."

   Generated: a script.

4. Helper AI. helper.example. November 12, 2026. "check the figures and say whether my old boss was right". Generated: checks.

5. Helper AI. helper.example. November 13, 2026. "one more". Generated: more.
   Follow-up in the same session, exact wording: "fine". Generated: a reading of each prompt after "exact wording:" as the author's, "unless" cut.

## Notes

- Keep it current.

7. Not an entry: it's under the notes.
"""

CUTS = """# Left out on purpose

## Entry 3: a prompt another session wrote, left out in full

> "Background: a long prompt
> written by the other session."
"""

RECORD = """# Report

Text.

## Appendix B. AI citations

**Entry 1.**

- URL: helper.example
- Date: November 10, 2026
- Exact final prompt: "list the open tasks"

**Entry 2.**

- URL: helper.example
- Date: November 12, 2026
- Exact final prompt: "draft the sumary"
  - Follow-up: "Yes, shorten it"
- Used as set out in that entry.

**Entry 3.**

- URL: other.example
- Date: November 12, 2026
- Exact final prompt: written by another session to start this one; see entry 9.

**Entry 4.**

- URL: helper.example
- Date: November 12, 2026
- Exact final prompt: "check the figures and say …"

## Appendix C

Other.
"""


SESSION_LOG = """# Helper log

1. Helper AI. helper.example. November 10, 2026. "list the open tasks". Generated: a list.
   Follow-up in the same session, exact wording: "draft the summary from the notes and the table". Generated: a draft.
   Follow-up in the same session, exact wording: "the first part of a message that went on". Generated: more.
   Follow-up in the same session, exact wording: "a long answer in two paragraphs" and "the second paragraph of that same answer". Generated: a reading.
   Follow-up in the same session, exact wording: "I agree with that reading of the table". Generated: a note.

2. Helper AI, a session another started. helper.example. November 11, 2026. The prompt, exact wording:

   > "Background: the person asked "draft the summary from the notes and the table" earlier.
   > Carry on."

## Notes
"""

SESSION_RECORD = """# Report

## Appendix B. AI citations

**Entry 1.**

- URL: helper.example
- Date: November 10, 2026
- Exact final prompt: "list the open tasks"
  - Follow-up: "draft the summary from the notes and the table"
  - Follow-up: "the first part of a message that went on"
  - Follow-up: "a long answer in two paragraphs"
  - Follow-up: "the second paragraph of that same answer"
  - Follow-up (quoting the helper's reading): "I agree with that reading of the table"
- What it produced: as the log says, with "draft the summary" quoted in passing.

**Entry 2.**

- URL: helper.example
- Date: November 11, 2026
- Exact final prompt: written by the session in entry 1 to start this one; described, not quoted.
"""

SESSION_CUTS = """# Left out on purpose

## Entry 2: a prompt another session wrote

> "Background: the person asked "draft the summary from the notes and the table" earlier.
> Carry on."
"""


def _said(text: object, at: str, **more: object) -> dict:
    return {"type": "user", "timestamp": at, "message": {"role": "user", "content": text}, **more}


# Fictional transcripts, one list of records per session. s3 is a fork of s1: it repeats s1's first message as sent.
SESSIONS = {
    "s1": [
        _said("list the open tasks", "2026-11-10T10:00:00Z"),
        _said([{"type": "text", "text": "<page-context>\nthe page\n</page-context>\n\ndraft the summary from the notes and the table"}],
              "2026-11-10T10:01:00Z"),
        _said("the first part of a message that went on, and then its second part", "2026-11-10T10:02:00Z"),
        _said("a long answer in two paragraphs\n\nthe second paragraph of that same answer", "2026-11-10T10:03:00Z"),
        _said("The helper said: the table is wrong.\n\nI agree with that reading of the table", "2026-11-10T10:04:00Z"),
        {"type": "attachment", "timestamp": "2026-11-10T10:05:00Z",
         "attachment": {"type": "queued_command", "prompt": "a prompt typed while it was busy"}},
        _said("This session is being continued from a previous conversation.", "2026-11-10T10:06:00Z", isCompactSummary=True),
        _said("[Request interrupted by user]", "2026-11-10T10:07:00Z"),
        _said("a sub-agent's task", "2026-11-10T10:08:00Z", isSidechain=True),
        _said([{"type": "tool_result", "content": "output"}], "2026-11-10T10:09:00Z"),
        _said("<task-notification>done</task-notification>", "2026-11-10T10:10:00Z"),
    ],
    "s2": [_said("a session nobody logged at all", "2026-11-12T09:00:00Z"), _said("and its second prompt", "2026-11-12T09:01:00Z")],
    "s3": [_said("list the open tasks", "2026-11-10T10:00:00Z")],
    "s4": [_said('Background: the person asked "draft the summary from the notes and the table" earlier.\nCarry on.',
                 "2026-11-11T08:00:00Z")],
}


class RecordLogs(Proofed):
    def setUp(self):
        super().setUp()
        (self.ws.root / "ai_log.md").write_text(LOG, encoding="utf-8")
        (self.ws.root / "report" / "left_out.md").write_text(CUTS, encoding="utf-8")

    def hold(self, record: str = "Appendix B") -> None:
        self.ws.config_path.write_text(self.ws.config_path.read_text(encoding="utf-8")
                                       + f'\n[[proof.record_logs]]\nrecord = "{record}"\nlog = "ai_log.md"\n'
                                       'cuts = ["report/left_out.md"]\n', encoding="utf-8")

    def test_a_record_is_held_to_its_log(self):
        self.draft(RECORD)
        self.hold()
        lines = RECORD.split("\n")
        at = {number: lines.index(f"**Entry {number}.**") + 1 for number in (1, 2, 3, 4)}
        found = [(line, verdict, item) for _, line, verdict, item in self.found("records")]
        self.assertEqual(found, [
            (at[2], "fail", "entry 2: November 12, 2026"),
            (at[2], "fail", 'entry 2: "draft the sumary"'),
            (at[2], "fail", 'entry 2: "draft the summary"'),
            (at[2], "fail", 'entry 2: "keep the table"'),
            (at[2], "warn", 'entry 2: "that entry"'),
            (at[3], "fail", "entry 3: other.example"),
            (at[3], "fail", "entry 3: entry 9"),
            (at[4], "fail", "entry 5"),
        ])
        details = {r.item: r.detail for r in proof.proof(self.ws, self.con) if r.check == "records"}
        self.assertEqual(details["entry 2: November 12, 2026"], "the log's entry is dated November 11, 2026 (ai_log.md:7)")
        self.assertEqual(details["entry 5"], "ai_log.md:19 has it, and the record doesn't")

    def test_a_record_kept_as_a_companion_file_and_a_cut_that_says_so(self):
        (self.ws.root / "report" / "appendix_b.md").write_text(
            '**Entry 1.**\n\n- Date: November 10, 2026\n- Exact final prompt: "list the open tasks"\n\n'
            '**Entry 2.**\n\n- Exact final prompt: "draft the summary"\n  - Follow-ups: "Yes, shorten it"; '
            '"keep the table" (answering "Shorten it?")\n\n**Entry 3.**\n\n- Described, not quoted: see the left-out file.\n\n'
            '**Entry 4.**\n\n- "check the figures and say …", the rest left out.\n\n**Entry 5.**\n\n- "one more", then "fine"\n', encoding="utf-8")
        self.settings(references=["report/references.md"], companions=["report/appendix_b.md"])
        self.draft("Revenue fell (Northbridge Robotics 2025a).\n")
        self.hold("report/appendix_b.md")
        self.assertEqual(self.found("records"), [])

    def test_a_record_that_isnt_there_is_said(self):
        self.draft("# Report\n\nText.\n")
        self.hold()
        self.assertEqual([(verdict, item) for _, _, verdict, item in self.found("records")], [("fail", "Appendix B")])

    def test_a_record_and_its_log_held_to_the_sessions_transcripts(self):
        folder = self.ws.root / "sessions"
        folder.mkdir()
        for name, records in SESSIONS.items():
            (folder / f"{name}.jsonl").write_text("\n".join(json.dumps(record) for record in records) + "\nnot json\n",
                                                  encoding="utf-8")
        (self.ws.root / "ai_log.md").write_text(SESSION_LOG, encoding="utf-8")
        (self.ws.root / "report" / "left_out.md").write_text(SESSION_CUTS, encoding="utf-8")
        self.draft(SESSION_RECORD)
        self.ws.config_path.write_text(self.ws.config_path.read_text(encoding="utf-8")
                                       + '\n[[proof.record_logs]]\nrecord = "Appendix B"\nlog = "ai_log.md"\n'
                                       'cuts = ["report/left_out.md"]\nsessions = "sessions"\n', encoding="utf-8")
        entry_1 = SESSION_RECORD.split("\n").index("**Entry 1.**") + 1
        found = {(r.file, r.line, r.verdict, r.item): r.detail for r in proof.proof(self.ws, self.con)
                 if r.check == "records" and r.verdict != proof.PASS}
        self.assertEqual(list(found), [
            ("01_draft.md", entry_1, "fail", 'entry 1: "the first part of a message that went on"'),
            ("01_draft.md", entry_1, "fail", 'entry 1: "a long answer in two paragraphs"'),
            # The log quotes only part of that message too, so the log hasn't got what was typed.
            ("ai_log.md", 0, "fail", '"the first part of a message that went on, and then its second part"'),
            ("ai_log.md", 0, "fail", '"a prompt typed while it was busy"'),
            ("ai_log.md", 0, "fail", "session s2 (2026-11-12 09:00 UTC)"),
        ])
        details = list(found.values())
        self.assertIn('goes on ", and then its second part" after it', details[0])
        self.assertIn('given as two quotations; the rest of it is "the second paragraph of that same answer"', details[1])
        self.assertEqual(details[3], "typed in session s1 on 2026-11-10 10:05 UTC, and neither ai_log.md nor a cuts file quotes it")
        self.assertIn('none of its 2 prompts is in ai_log.md or a cuts file, so it has no entry; the first is '
                      '"a session nobody logged at all"', details[4])

    def test_what_a_transcript_counts_as_typed(self):
        self.assertEqual(sessions.typed("<page-context>\nthe page\n</page-context>\n\nfix it<system-reminder>x</system-reminder>"),
                         "fix it")
        for not_typed in ("<task-notification>done</task-notification>", "[Request interrupted by user]", "<local-command>"):
            self.assertEqual(sessions.typed(not_typed), "")
        self.assertTrue(record_log._quoting("draft the summary", 'he asked "draft the summary" first'))
        self.assertFalse(record_log._quoting("draft the summary", "draft the summary, then stop"))
        self.assertEqual(record_log.answers("Quoted.\n\nMine.\n \nMore."), ["Quoted.\n\nMine.\n\nMore.", "Mine.\n\nMore.", "More."])

    def test_words_left_out_of_a_quotation(self):
        log = "my old boss was right about the figures"
        self.assertTrue(record_log.found_in("my old boss … the figures", log))
        self.assertTrue(record_log.found_in("my \\[name left out\\] was right", "my [name left out] was right"))
        self.assertFalse(record_log.found_in("the figures … my old boss", log))
        self.assertTrue(record_log.found_in("my old boss …", log, whole=True))
        self.assertFalse(record_log.found_in("old boss was right", log, whole=True))


RULES = '''
[[proof.table_rules]]
name = "Ansoff"
column = "Ansoff"
values = ["Market penetration", "Market development", "Product development", "Diversification", "n/a"]

[[proof.table_rules]]
name = "VRIO"
column = "Outcome"
derive = [
    { when = { Valuable = "No" }, then = "disadvantage" },
    { when = { Rare = ["No", "Partly"] }, then = "parity" },
    { when = { "Hard to imitate" = "No" }, then = "temporary" },
    { when = { Organized = "No" }, then = "unused" },
    { when = {}, then = "sustained" },
]
'''


class Tables(Proofed):
    def test_a_column_holds_only_what_the_rule_allows(self):
        self.ws.config_path.write_text(self.ws.config_path.read_text(encoding="utf-8") + RULES, encoding="utf-8")
        self.draft("| Option | Score | **Ansoff** |\n| --- | --- | --- |\n| A. Arms | 5 | Product development |\n"
                   "| B. Services | 3 | Vertical integration |\n| C. Cash | | n/a |\n| D. Later | | |\n")
        found = [(r.line, r.item, r.detail) for r in proof.proof(self.ws, self.con) if r.check == "tables" and r.verdict == proof.FAIL]
        self.assertEqual([(line, item) for line, item, _ in found], [(4, "Vertical integration")])
        self.assertIn("B. Services: the '**Ansoff**' column may hold only Market penetration", found[0][2])

    def test_an_outcome_is_the_one_the_first_matching_case_gives(self):
        self.ws.config_path.write_text(self.ws.config_path.read_text(encoding="utf-8") + RULES, encoding="utf-8")
        self.draft("| Resource | Valuable | Rare | Hard to imitate | Organized | Outcome |\n| --- | --- | --- | --- | --- | --- |\n"
                   "| Materials | Yes | Yes | Yes | Yes | Sustained advantage |\n"
                   "| Dealers | Yes | Partly | Yes | Yes | Sustained, for now |\n"
                   "| Base | Yes | Yes, in industry | No | Yes | Temporary |\n"
                   "| Patents | Yes | No | No | Yes | Eroding parity |\n"
                   "| Cash | No | Yes | No | n/a | Parity |\n"
                   "| Software | Yes | Yes | Yes | No | |\n\n"
                   "| Deal | Outcome |\n| --- | --- |\n| Arms | Sustained |\n")
        found = [(r.line, r.item, r.detail) for r in proof.proof(self.ws, self.con) if r.check == "tables" and r.verdict == proof.FAIL]
        self.assertEqual([(line, item) for line, item, _ in found], [(4, "Sustained, for now"), (7, "Parity")])
        self.assertIn("Dealers: by [[proof.table_rules]] 'VRIO', Rare: Partly makes it parity, but the 'Outcome' column says "
                      "'Sustained, for now'", found[0][2])

    def test_rules_that_cant_be_used_are_refused(self):
        self.draft("Revenue fell.\n")
        base = self.ws.config_path.read_text(encoding="utf-8")
        for rule, said in (('values = ["A"]', "must name the column"),
                           ('column = "Ansoff"', "must give values, derive or both"),
                           ('column = "Ansoff"\nvalue = ["A"]', "settings it doesn't know: value"),
                           ('column = "Outcome"\nderive = [{ when = { Rare = 1 }, then = "parity" }]', "each case of derive"),
                           ('column = "Outcome"\nderive = [{ when = {}, then = "" }]', "each case of derive")):
            with self.subTest(rule):
                self.ws.config_path.write_text(base + f"\n[[proof.table_rules]]\n{rule}\n", encoding="utf-8")
                with self.assertRaises(ValueError) as refused:
                    proof.proof(self.ws, self.con)
                self.assertIn(said, str(refused.exception))


class Command(Proofed):
    def test_the_exit_status_says_whether_anything_failed(self):
        self.draft("Revenue fell (Northbridge Robotics 2025a).\n")
        out, _, code = self.run_here("proof")
        self.assertEqual(code, 0)
        self.assertIn("citations         0 failed, 0 warned", out)
        self.assertTrue((self.ws.data / "proof.csv").is_file())
        self.draft("Revenue fell (Northbridge Robotics 2031).\n")
        out, _, code = self.run_here("proof")
        self.assertEqual(code, 1)
        self.assertIn("FAIL citations 01_draft.md:1 'Northbridge Robotics 2031'", out)

    def test_settings_that_cant_be_used_are_refused(self):
        self.draft("Revenue fell.\n")
        self.settings(references=["report/missing.md"])
        _, err, code = self.run_here("proof")
        self.assertEqual(code, 1)
        self.assertIn("names files that don't exist", err)

    def test_record_logs_that_cant_be_used_are_refused(self):
        self.draft("Revenue fell.\n")
        self.ws.config_path.write_text(self.ws.config_path.read_text(encoding="utf-8")
                                       + '\n[[proof.record_logs]]\nrecord = "Appendix B"\nlog = "missing_log.md"\n', encoding="utf-8")
        _, err, code = self.run_here("proof")
        self.assertEqual(code, 1)
        self.assertIn("names files that don't exist", err)

    def test_a_sessions_folder_that_isnt_there_is_refused(self):
        self.draft("Revenue fell.\n")
        (self.ws.root / "ai_log.md").write_text(LOG, encoding="utf-8")
        self.ws.config_path.write_text(self.ws.config_path.read_text(encoding="utf-8")
                                       + '\n[[proof.record_logs]]\nrecord = "Appendix B"\nlog = "ai_log.md"\n'
                                       'sessions = "no_such_folder"\n', encoding="utf-8")
        _, err, code = self.run_here("proof")
        self.assertEqual(code, 1)
        self.assertIn("names a folder that doesn't exist", err)

    def test_no_drafts_is_said(self):
        _, err, code = self.run_here("proof")
        self.assertEqual(code, 0)
        self.assertIn("No drafts to proof", err)


if __name__ == "__main__":
    unittest.main()
