"""Tests for the judge: the assay holding a draft to the notes. Every note, draft and source here is made up, and lives in
a throwaway copy of the example workspace."""
import argparse
import contextlib
import csv
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from support import CODE_ROOT, write_docx

import assay
from assay import seal as assay_seal
from drillcore import judge, sourcedb, workspace

ANNUAL = "https://example.com/northbridge/annual-2025.html"
ORDERS = "https://example.com/northbridge/orders.html"
NOTE = """# Judge notes

Fictional, for the tests.

## 1. Figures (S1)

| Item | 2025 |
|---|---|
| Revenue | $551.1M |
| Margin | 41.2% |
| Staff at year end | 1,757 |

- Orders doubled in the year (S2).
- The press desk is press@northbridge.example, and the site northbridge.example (S2).

## Gaps and cautions

- A blog gives $123.4M for the order book. Nothing confirms it.

## Sources

- **S1.** Northbridge Robotics. Annual report, 88 pages. https://example.com/northbridge/annual-2025.html
- **S2.** Northbridge Robotics. Orders. https://example.com/northbridge/orders.html
"""


class Judged(unittest.TestCase):
    """A workspace of its own for each test: the example's notes and one more, no drafts, and the database open."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        shutil.rmtree(root / "drafts")
        (root / "drafts").mkdir()
        (root / "research" / "02_judge.md").write_text(NOTE, encoding="utf-8")
        self.ws = workspace.Workspace(root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)
        sourcedb.record_sources(self.ws, self.con)

    def draft(self, text, name="01_draft.md"):
        path = self.ws.root / "drafts" / name
        path.write_text(text, encoding="utf-8")
        return path

    def source(self, url, text):
        self.con.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?)", (url, None, text, len(text), "text"))
        self.con.commit()

    def settings(self, extra):
        with self.ws.config_path.open("a", encoding="utf-8") as out:
            out.write("\n" + extra + "\n")

    def results(self, check, drafts=None):
        return [r for r in judge.judge(self.ws, self.con, drafts) if r.check == check]

    def problems(self, check):
        return [(r.line, r.verdict, r.item) for r in self.results(check) if r.verdict != judge.PASS]

    def run_judge(self, *drafts):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = judge.run(self.ws, self.con, argparse.Namespace(drafts=list(drafts)))
        return out.getvalue(), err.getvalue(), code


class Numbers(Judged):
    def test_a_draft_that_states_only_what_the_notes_hold_passes(self):
        self.draft("# Draft\n\nIn 2025 revenue was $551.1M and the margin 41.2%, with 1,757 staff.\nOrders doubled.\n")
        [result] = self.results("numbers")
        self.assertEqual((result.verdict, result.detail), (judge.PASS, "every figure is in the notes"))
        self.assertEqual(self.results(judge.VERDICT)[0].verdict, judge.PASS)

    def test_a_figure_the_notes_dont_hold_exactly_fails(self):
        self.draft("# Draft\n\nRevenue was $560M,\nsome sixty staff left, and orders tripled. Revenue was 551.1 million.\n")
        self.assertEqual(self.problems("numbers"), [(3, "fail", "$560M"), (4, "fail", "sixty"), (4, "fail", "tripled")])

    def test_the_same_value_at_another_scale_isnt_the_notes_figure(self):
        self.draft("Revenue was $551.1 thousand.\n")
        self.assertEqual([item for _, _, item in self.problems("numbers")], ["$551.1 thousand"])

    def test_the_sources_list_and_the_gaps_approve_nothing(self):
        self.draft("The report runs to 88 pages. A blog gives $123.4M.\n")
        self.assertEqual([item for _, _, item in self.problems("numbers")], ["88", "$123.4M"])

    def test_a_figure_only_a_cited_source_holds_is_a_warning(self):
        self.source(ANNUAL, "Annual report. In thousands of dollars. Operating loss was 12,400 for the year.")
        self.draft("# Draft\n\nThe operating loss was $12.4M.\n")
        [result] = self.results("numbers")
        self.assertEqual((result.line, result.verdict, result.item), (3, judge.WARN, "$12.4M"))
        self.assertIn(f"supported by a source, not by the notes ({ANNUAL})", result.detail)
        self.assertEqual(self.results(judge.VERDICT)[0].verdict, judge.WARN)

    def test_a_figure_neither_the_notes_nor_a_source_holds_fails(self):
        self.draft("The operating loss was $12.4M.\n")
        [unfetched] = self.results("numbers")
        self.assertEqual(unfetched.verdict, judge.FAIL)
        self.assertIn("no source they cite has been fetched", unfetched.detail)
        self.source(ORDERS, "Order book 95.4 million.")
        [missing] = self.results("numbers")
        self.assertEqual(missing.verdict, judge.FAIL)
        self.assertIn("nor in the text of a source they cite", missing.detail)

    def test_dates_and_years_measure_nothing(self):
        self.draft("On 3 March 2026 revenue for 2025 was $551.1M.\n")
        self.assertEqual(self.problems("numbers"), [])

    def test_a_scale_letter_after_a_space_isnt_the_bare_number(self):
        self.draft("The arm sold 1,757 K units.\n")
        self.assertEqual(self.problems("numbers"), [(1, "fail", "1,757 K")])


class Bound(Judged):
    """A figure the notes hold is held to what they hold it for: a line of the notes that says what it is."""

    def test_a_figure_beside_the_words_the_notes_give_it_passes(self):
        self.draft("Revenue was $551.1M, on a margin of 41.2%, with 1,757 staff at the year's end.\n")
        self.assertEqual(self.problems("numbers"), [])

    def test_a_figure_the_notes_give_for_something_else_is_a_warning(self):
        self.draft("# Draft\n\nThe order backlog was $551.1M, and churn was 41.2%.\n")
        found = [(r.line, r.verdict, r.item) for r in self.results("numbers") if r.verdict != judge.PASS]
        self.assertEqual(found, [(3, "warn", "$551.1M"), (3, "warn", "41.2%")])
        detail = next(r.detail for r in self.results("numbers") if r.item == "$551.1M")
        self.assertIn("in the notes, but only on lines about other things", detail)
        # The warning points at the lines that hold it, with the stretch around the figure.
        self.assertIn("02_judge.md:9 '| Revenue | $551.1M |'", detail)
        self.assertEqual(self.results(judge.VERDICT)[0].verdict, judge.WARN)

    def test_a_sentence_wrapped_over_lines_is_read_whole(self):
        self.draft("The order book stood at its level, and revenue for the\nyear came to $551.1M.\n\n- Patents gave $551.1M.\n")
        self.assertEqual(self.problems("numbers"), [(4, "warn", "$551.1M")])

    def test_the_heading_says_what_a_figure_is_too(self):
        # The example's 1,757 sits in a table under "1. Results".
        self.draft("Results gave 1,757.\n")
        self.assertEqual(self.problems("numbers"), [])
        self.draft("Patents gave 1,757.\n")
        self.assertEqual(self.problems("numbers"), [(1, "warn", "1,757")])

    def test_a_short_figure_or_a_sentence_with_nothing_to_compare_isnt_judged(self):
        self.draft("Orders doubled, and churn was 12.\nIt was $551.1M.\n")
        self.assertEqual(self.problems("numbers"), [(1, "fail", "12")])


class Titles(Judged):
    TITLED = "\n- The chief financial officer, Jane Roe, joined from a vice president of sales role (S1).\n"

    def setUp(self):
        super().setUp()
        note = self.ws.root / "research" / "02_judge.md"
        note.write_text(NOTE.replace("\n## Gaps", self.TITLED + "\n## Gaps"), encoding="utf-8")

    def test_a_title_the_notes_give_passes_in_part_or_whole(self):
        self.draft("Chief Financial Officer Jane Roe was once a Vice President, and the Financial Officer signs.\n")
        [result] = self.results("titles")
        self.assertEqual((result.verdict, result.detail), (judge.PASS, "every title is one the notes give"))

    def test_a_title_put_together_from_two_is_a_warning(self):
        self.draft("# Draft\n\nJane Roe, Chief Financial Vice President, spoke.\nShe was Vice President of Finance.\n")
        self.assertEqual(self.problems("titles"), [(3, "warn", "Chief Financial Vice President"),
                                                   (4, "warn", "Vice President of Finance")])

    def test_a_title_dropping_what_lessens_it_is_a_warning(self):
        self.draft("She was the President.\n")
        self.assertEqual(self.problems("titles"), [(1, "warn", "President")])


class Links(Judged):
    def test_addresses_the_notes_write_pass(self):
        self.draft(f"See {ORDERS}, www.example.com/northbridge/orders.html, northbridge.example or press@northbridge.example.\n")
        [result] = self.results("links")
        self.assertEqual(result.verdict, judge.PASS)

    def test_addresses_the_notes_dont_write_fail(self):
        self.draft("# Draft\n\nRead https://elsewhere.example/page or other.example,\nor write to desk@other.example.\n")
        self.assertEqual(self.problems("links"), [(3, "fail", "https://elsewhere.example/page"), (3, "fail", "other.example"),
                                                  (4, "fail", "desk@other.example")])

    def test_a_look_alike_letter_makes_another_domain(self):
        self.draft("See northbridgе.example for more.\n")  # The last e is Cyrillic.
        self.assertEqual(len(self.problems("links")), 1)

    def test_an_address_the_settings_accept_passes_with_their_reason(self):
        self.settings('[assay.accept_addresses]\n"https://doi.org/10.0000/frames.2019" = "a framework article"\n'
                      '"quotes.example/arm/history" = "the page behind a price series the notes cite"')
        self.draft("# Draft\n\nSee https://doi.org/10.0000/frames.2019. and quotes.example/arm/history,\n"
                   "but not https://doi.org/10.0000/other.2020 or quotes.example/arm.\n")
        found = [(r.line, r.verdict, r.item, r.detail) for r in self.results("links") if r.line]
        self.assertEqual([(line, verdict, item) for line, verdict, item, _ in found], [
            (3, "pass", "https://doi.org/10.0000/frames.2019"), (3, "pass", "quotes.example/arm/history"),
            (4, "fail", "https://doi.org/10.0000/other.2020"), (4, "fail", "quotes.example/arm")])
        self.assertIn("accepted by [assay.accept_addresses]: a framework article", found[0][3])
        self.assertEqual(judge.rules(self.ws).digestible()["accepted addresses"],
                         ["doi.org/10.0000/frames.2019: a framework article",
                          "quotes.example/arm/history: the page behind a price series the notes cite"])

    def test_accepted_addresses_that_cant_be_used_are_refused(self):
        self.draft("Revenue was $551.1M.\n")
        for table, said in (('accept_addresses = ["https://doi.org/10.0000/frames.2019"]', "must be a table"),
                            ('[assay.accept_addresses]\n"https://doi.org/10.0000/frames.2019" = ""', "must say why"),
                            ('[assay.accept_addresses]\n"every page" = "all of them"', "isn't a web address")):
            with self.subTest(table):
                self.ws.config_path.write_text((CODE_ROOT / "example" / "workspace.toml").read_text(encoding="utf-8")
                                               + ("\n[assay]\n" if not table.startswith("[") else "\n") + table + "\n", encoding="utf-8")
                with self.assertRaises(ValueError) as refused:
                    judge.judge(self.ws, self.con)
                self.assertIn(said, str(refused.exception))


class Names(Judged):
    def test_a_confidential_name_fails_however_its_split(self):
        self.settings('[assay]\nforbidden = ["Kestrel", "Project Osprey"]')
        self.draft("# Draft\n\nThe K-e-s-t-r-e-l arm shipped.\nWork on project-ospreys went on, and **Kes**trel too.\n")
        self.assertEqual(self.problems("names"), [(3, "fail", "K-e-s-t-r-e-l"), (4, "fail", "Kestrel"), (4, "fail", "project-ospreys")])

    def test_digits_written_for_letters_dont_hide_one(self):
        self.settings('[assay]\nforbidden = ["Kestrel", "Project Osprey"]')
        self.draft("The K3str3l arm and Pr0ject 0spr3y shipped.\n")
        self.assertEqual(self.problems("names"), [(1, "fail", "K3str3l"), (1, "fail", "Pr0ject 0spr3y")])

    def test_a_draft_without_one_passes_and_no_list_means_no_check(self):
        self.draft("The arm shipped.\n")
        self.assertEqual(self.results("names"), [])
        self.settings('[assay]\nforbidden = ["Kestrel"]')
        [result] = self.results("names")
        self.assertEqual(result.verdict, judge.PASS)


UNITS = """# Units

Fictional, for the tests.

## Worked out (S1)

- COMPUTED, US$ millions: the premium over the model was 377.2 to 418.6.
- Return on the arm business: 7.36%.
- Shared tooling cut test time: a 10x saving.

Worked out (US$ millions):

| Measure | Result |
|---|---|
| Put into the arm business, 2013 to 2025 | 264.9 |

| Item | Cost ($M) | Share |
|---|---|---|
| Gripper line | 31.8 | 7.7% |

## Sources

- **S1.** Northbridge Robotics. Annual report. https://example.com/northbridge/annual-2025.html
"""


class HowAFigureIsWritten(Judged):
    """A figure is read as a writer states it: in a unit given once, as a word multiple, as a count, or rounded."""

    def setUp(self):
        super().setUp()
        (self.ws.root / "research" / "03_units.md").write_text(UNITS, encoding="utf-8")
        sourcedb.record_sources(self.ws, self.con)

    def test_a_unit_a_label_or_a_table_states_applies_to_the_bare_figures_under_it(self):
        self.draft("# Draft\n\nThe premium was $377.2M to $418.6M, and $264.9M was put into the arm business.\n"
                   "The gripper line cost $31.8 million.\n")
        self.assertEqual(self.problems("numbers"), [])
        # Read at the unit, never at another: $418.6 thousand isn't the notes' figure.
        self.draft("The premium was $418.6 thousand.\n")
        self.assertEqual([item for _, _, item in self.problems("numbers")], ["$418.6 thousand"])

    def test_a_draft_table_states_its_unit_too(self):
        self.draft("# Draft\n\n| Item | US$ millions |\n|---|---|\n| Arm business | 264.9 |\n| Something else | 777.7 |\n")
        self.assertEqual(self.problems("numbers"), [(6, "fail", "777.7")])

    def test_a_multiple_in_words_and_a_count_of_figures(self):
        self.draft("# Draft\n\nShared tooling cut test time tenfold, and the check showed seven figures accepted after review.\n")
        self.assertEqual(self.problems("numbers"), [])
        self.draft("The founder earns six figures.\n")
        self.assertEqual([item for _, _, item in self.problems("numbers")], ["six figures"])

    def test_a_rounding_of_the_notes_figure_passes_and_says_so(self):
        self.draft("# Draft\n\nThe arm business returned 7.4%, or about 7%.\n")
        found = [(r.verdict, r.item, r.detail) for r in self.results("numbers") if r.line]
        self.assertEqual(found, [("pass", "7.4%", "percent 7.4: rounds 7.36%, which the notes give"), ("fail", "7%", found[1][2])])
        out, _, _ = self.run_judge()
        self.assertIn("1 passed with a reason given", out)

    def test_a_rounding_on_a_line_about_this_beats_the_same_figure_on_a_line_about_something_else(self):
        # The notes give 7.4% only for staff turnover, and 7.36% for the arm business's return.
        (self.ws.root / "research" / "04_turnover.md").write_text("# Turnover\n\n## People (S1)\n\n- Staff turnover was 7.4%.\n",
                                                                  encoding="utf-8")
        self.draft("# Draft\n\nThe arm business returned 7.4%.\n")
        [found] = [r for r in self.results("numbers") if r.line]
        self.assertEqual((found.verdict, found.item), (judge.PASS, "7.4%"))
        self.assertIn("rounds 7.36%, which the notes give at 03_units.md:8", found.detail)
        # One word in common ("returned") is too easily chance: the figure stays a warning.
        self.draft("# Draft\n\nThe line returned 7.4%.\n")
        self.assertEqual(self.problems("numbers"), [(3, "warn", "7.4%")])


UNSTATED = """# Cases

Fictional, for the tests.

## Cases set by the author (S1)

| Case | Spending $9M a year |
|---|---|
| Base | 27.3 (= 88.1 - 60.8) |

## Sources

- **S1.** Northbridge Robotics. Annual report. https://example.com/northbridge/annual-2025.html
"""


class GivenOtherwise(Judged):
    """A figure the notes give only bare, in a table that states no unit, on a line about the draft's sentence."""

    def setUp(self):
        super().setUp()
        self.note = self.ws.root / "research" / "03_cases.md"
        self.note.write_text(UNSTATED, encoding="utf-8")
        sourcedb.record_sources(self.ws, self.con)

    def test_the_finding_names_the_line_to_state_the_unit_on_and_keeps_its_verdict(self):
        self.draft("# Draft\n\nIn the base case, $27.3M is left.\n")
        [found] = [r for r in self.results("numbers") if r.line]
        self.assertEqual((found.verdict, found.item), (judge.FAIL, "$27.3M"))
        self.assertIn("in no unit they state, on a line about this: 03_cases.md:9 '| Base | 27.3", found.detail)
        # A source that holds it as written makes it a warning, as it was, and the line is still named.
        self.source(ANNUAL, "Of the cash, 27.3 million is left in the base case.")
        [found] = [r for r in self.results("numbers") if r.line]
        self.assertEqual(found.verdict, judge.WARN)
        self.assertIn("03_cases.md:9", found.detail)
        self.assertIn(f"a source they cite holds it as written ({ANNUAL})", found.detail)

    def test_a_unit_stated_in_a_heading_above_the_table_settles_it(self):
        self.note.write_text(UNSTATED.replace("(S1)", "(US$ millions; S1)", 1), encoding="utf-8")
        self.draft("# Draft\n\nIn the base case, $27.3M is left.\n")
        self.assertEqual(self.problems("numbers"), [])


WRITTEN = """# As written

Fictional, for the tests.

## 4. Costs (S1)

| Item | 2025 |
|---|---|
| R&D, net | $64.2M |

- A study quoted: "orders of 58 000 or fewer ship from stock" (S1).
- Gripper spending, half year, US$ thousands: (18,437) (S1).

| Line (EUR) | 2024 |
|---|---|
| Order intake | 46.3m |

| Part | Reach |
|---|---|
| Gripper arm | 1.5m |

## Sources

- **S1.** Northbridge Robotics. Annual report. https://example.com/northbridge/annual-2025.html
"""


class AsTheNotesWriteIt(Judged):
    """An abbreviation as a describing word, thousands grouped by spaces, a currency named by a table, and a draft's
    figure rounded in its own table's unit."""

    def setUp(self):
        super().setUp()
        (self.ws.root / "research" / "03_written.md").write_text(WRITTEN, encoding="utf-8")
        sourcedb.record_sources(self.ws, self.con)

    def test_an_abbreviation_joined_by_an_ampersand_is_a_describing_word(self):
        # The line's only describing words are "Costs", from its heading, and R&D.
        self.draft("# Draft\n\n| Move | Cash |\n|---|---|\n| Move R&D to grippers | Restore it to $64.2M |\n")
        self.assertEqual(self.problems("numbers"), [])
        self.draft("# Draft\n\nMove spending to grippers, restoring it to $64.2M.\n")
        self.assertEqual(self.problems("numbers"), [(3, "warn", "$64.2M")])

    def test_thousands_grouped_by_spaces_are_one_number(self):
        self.draft("# Draft\n\nOrders of up to about 58,000 ship from stock.\n")
        self.assertEqual(self.problems("numbers"), [])
        self.draft("# Draft\n\nOrders of up to about 59,000 ship from stock.\n")
        self.assertEqual([item for _, _, item in self.problems("numbers")], ["59,000"])

    def test_a_lowercase_m_in_a_table_that_names_its_currency_is_million(self):
        self.draft("# Draft\n\nOrder intake was EUR 46.3M in 2024.\n")
        self.assertEqual(self.problems("numbers"), [])
        # A table that names no currency may give metres: 1.5m there is no $1.5M.
        self.draft("# Draft\n\nThe gripper arm cost $1.5M.\n")
        self.assertEqual([item for _, _, item in self.problems("numbers")], ["$1.5M"])

    def test_a_bare_figure_rounds_one_in_the_unit_its_draft_table_states(self):
        self.draft("# Draft\n\n**Spending** (US$M)\n\n| Line | Half year |\n|---|---|\n| Gripper spending | (18.4) |\n"
                   "| Gripper spending, again | (18.9) |\n")
        found = [(r.line, r.verdict, r.item, r.detail) for r in self.results("numbers") if r.line]
        self.assertEqual([(line, verdict, item) for line, verdict, item, _ in found], [(7, "pass", "(18.4)"), (8, "fail", "(18.9)")])
        self.assertEqual(found[0][3], "number 18.4: read in millions, as its table or label states, it rounds 18437000, which the notes give")
        # The notes give 18.4 as written too, for something else: the rounding on the line about this still settles it.
        note = self.ws.root / "research" / "03_written.md"
        note.write_text(WRITTEN.replace("\n## Sources", "- Canteen seats per hundred staff: 18.4 (S1).\n\n## Sources"), encoding="utf-8")
        [found] = [r for r in self.results("numbers") if r.line == 7]
        self.assertEqual((found.verdict, found.item), (judge.PASS, "(18.4)"))
        self.assertIn("read in millions, as its table or label states, it rounds 18437000, which the notes give at 03_written.md:12",
                      found.detail)


class WhatADraftSays(Judged):
    """A draft's reference list and its records aren't judged as what it says."""

    def test_the_reference_list_gives_no_figures_to_judge_but_its_addresses_are_judged(self):
        self.draft("# Draft\n\nRevenue was $551.1M.\n\n## References\n\n- Roe, Jane. 2024. *Arms*, 88 pages. Form 8-K, "
                   "Exhibit 99.1. https://elsewhere.example/roe.\n- SEC. n.d. https://data.sec.gov/api/xbrl/companyconcept/CIK0009999999/ "
                   "and https://data.sec.gov/api/xbrl/companyconcept/CIK0001234567/.\n")
        self.assertEqual(self.problems("numbers"), [])
        # The SEC's structured data for the company the settings load is a source the workspace holds; another isn't.
        self.assertEqual(self.problems("links"), [(7, "fail", "https://elsewhere.example/roe"),
                                                  (8, "fail", "https://data.sec.gov/api/xbrl/companyconcept/CIK0001234567/")])

    def test_a_section_named_as_a_record_is_judged_for_confidential_names_alone(self):
        self.settings('[assay]\nforbidden = ["Kestrel"]\n\n[drafts]\nrecords = ["Appendix B"]')
        self.draft("# Draft\n\nRevenue was $551.1M.\n\n## Appendix B. Prompts\n\nAsk for 777.7 words from https://elsewhere.example "
                   "about Kestrel.\n\n## Appendix C. Notes\n\nIt cost $612.4M.\n")
        self.assertEqual(self.problems("numbers"), [(11, "fail", "$612.4M")])
        self.assertEqual(self.problems("links"), [])
        self.assertEqual(self.problems("names"), [(7, "fail", "Kestrel")])
        self.assertEqual(judge.rules(self.ws).digestible()["records"], ["Appendix B"])

    def test_records_that_cant_be_used_are_refused(self):
        self.settings('[drafts]\nrecords = "Appendix B"')
        self.draft("Revenue was $551.1M.\n")
        with self.assertRaises(ValueError):
            judge.judge(self.ws, self.con)


class AllowedPlaces(Judged):
    def test_a_confidential_name_may_stand_where_the_settings_allow_it(self):
        self.settings('[assay]\nforbidden = ["Kestrel"]\n\n[assay.allowed]\n"Kestrel" = ["captions", "sources", "citations"]')
        self.draft("# Draft\n\n*Exhibit 1. Arm prices. Source: Kestrel Ltd., price list.*\n\nKestrel won the bid.\n\n"
                   "Prices fell (Kestrel Ltd. 2025).\n\nThe rival line was dropped. Source: Kestrel filings.\n")
        found = [(r.line, r.verdict, r.detail) for r in self.results("names") if r.line]
        self.assertEqual([(line, verdict) for line, verdict, _ in found], [(3, "pass"), (5, "fail"), (7, "pass"), (9, "pass")])
        self.assertIn("allowed here (captions, sources)", found[0][2])
        self.assertIn("lets it stand only in captions, sources, citations", found[1][2])

    def test_a_name_with_no_places_fails_everywhere_as_before(self):
        self.settings('[assay]\nforbidden = ["Kestrel"]')
        self.draft("*Exhibit 1. Source: Kestrel.*\n")
        self.assertEqual(self.problems("names"), [(1, "fail", "Kestrel")])

    def test_places_that_cant_be_used_are_refused(self):
        self.draft("Revenue fell.\n")
        for extra in ('[assay]\nforbidden = ["Kestrel"]\n\n[assay.allowed]\n"Osprey" = ["captions"]',
                      '[assay]\nforbidden = ["Kestrel"]\n\n[assay.allowed]\n"Kestrel" = ["footnotes"]'):
            with self.subTest(extra):
                self.ws.config_path.write_text((CODE_ROOT / "example" / "workspace.toml").read_text(encoding="utf-8") + "\n" + extra + "\n",
                                               encoding="utf-8")
                with self.assertRaises(ValueError):
                    judge.judge(self.ws, self.con)


class Judgments(Judged):
    def test_a_judgment_passes_only_attributed_or_cited(self):
        self.settings(r"""[assay]
judgments = ['\bshould\b']""")
        self.draft("# Draft\n\nNorthbridge should cut costs. In the author's view, Northbridge should hire.\n"
                   "Northbridge should sell the line (Roe 2024).\n")
        found = [(r.line, r.verdict) for r in self.results("judgments")]
        self.assertEqual(found, [(3, "fail"), (3, "pass"), (4, "pass")])
        self.assertEqual(self.results(judge.VERDICT)[0].verdict, judge.FAIL)

    def test_no_list_means_no_check(self):
        self.draft("Northbridge should cut costs.\n")
        self.assertEqual(self.results("judgments"), [])


class Plans(Judged):
    def test_a_plan_for_a_period_begun_by_the_cutoff_is_a_warning(self):
        self.settings("[assay]\ncutoff = 2026-10-31")
        self.draft("# Draft\n\nThe Harbor plant is planned to open in the second half of 2026.\n"
                   "In March 2025 Northbridge said it plans to open a plant by 2027, and expects to hire in Q1 2027.\n"
                   "The merger was expected to close in the first quarter of 2024 (Roe 2026).\n"
                   "Its materials plan met a rule from September 2025, with lower expected growth in 2025.\n"
                   "It aims to finish by 2025, and will ship on 3 December 2026 and in mid-2026.\n")
        found = [(r.line, r.verdict, r.item) for r in self.results("plans")]
        self.assertEqual(found, [(3, "warn", "the second half of 2026"), (5, "warn", "the first quarter of 2024"),
                                 (7, "warn", "by 2025"), (7, "warn", "mid-2026")])
        detail = next(r.detail for r in self.results("plans") if r.line == 3)
        self.assertIn("('planned') for a period that was under way by the data cut-off of 2026-10-31", detail)
        self.assertIn("had ended", next(r.detail for r in self.results("plans") if r.line == 5))
        self.assertEqual(judge.rules(self.ws).digestible()["cutoff"], ["2026-10-31"])

    def test_no_cutoff_means_no_check_and_a_bad_one_is_refused(self):
        self.draft("The Harbor plant is planned to open in the second half of 2026.\n")
        self.assertEqual(self.results("plans"), [])
        self.settings('[assay]\ncutoff = "31 October 2026"')
        with self.assertRaises(ValueError) as refused:
            judge.judge(self.ws, self.con)
        self.assertIn("must be a date, as cutoff = 2026-10-31", str(refused.exception))

    def test_a_cutoff_written_as_a_string_will_do(self):
        self.settings('[assay]\ncutoff = "2026-10-31"')
        self.draft("The Harbor plant is planned to open in the second half of 2026.\n")
        self.assertEqual([r.verdict for r in self.results("plans")], ["warn"])


class WordDrafts(Judged):
    def test_a_word_document_in_the_drafts_folder_is_judged_as_text(self):
        write_docx(self.ws.root / "drafts" / "report.docx", [
            ("Heading1", "Northbridge"), "In 2025 revenue was $551.1M, with 1,757 staff.",
            [["Item", "2025"], ["Margin", "41.2%"], ["Orders", "99.9"]]])
        found = [(r.draft, r.line, r.verdict, r.item) for r in self.results("numbers") if r.verdict != judge.PASS]
        self.assertEqual(found, [("report.docx", 8, "fail", "99.9")])

    def test_one_that_cant_be_read_is_said(self):
        (self.ws.root / "drafts" / "broken.docx").write_bytes(b"not a zip file")
        _, err, code = self.run_judge()
        self.assertEqual(code, 1)
        self.assertIn("broken.docx can't be read as a Word document", err)


class Claims(Judged):
    def test_an_unsupported_claim_fails_unless_the_sentence_denies_it(self):
        self.settings('[assay]\nunsupported = ["record year"]')
        self.draft("# Draft\n\nIt was a record year for the company.\nIt was not a record year.\n")
        found = [(r.line, r.verdict, r.item) for r in self.results("claims")]
        self.assertEqual(found, [(3, "fail", "It was a record year for the company."), (4, "pass", "record year")])

    def test_a_draft_without_one_passes(self):
        self.settings('[assay]\nunsupported = ["record year"]')
        self.draft("Revenue fell.\n")
        [result] = self.results("claims")
        self.assertEqual(result.verdict, judge.PASS)

    def test_settings_that_cant_be_used_are_refused(self):
        self.draft("Revenue fell.\n")
        self.settings('[assay]\nunsupported = ["record (year"]')
        with self.assertRaises(ValueError):
            judge.judge(self.ws, self.con)
        _, err, code = self.run_judge()
        self.assertIn("isn't a regular expression", err)
        self.assertEqual(code, 1)


class Seal(Judged):
    def seal(self):
        return self.results(judge.VERDICT)[0].item

    def test_the_seal_changes_with_the_draft_and_the_notes_and_is_recorded(self):
        path = self.draft("Revenue was $551.1M.\n")
        first = self.seal()
        self.assertEqual(self.seal(), first)
        self.assertEqual(judge.stale(self.ws, self.con, path), [])
        self.draft("Revenue was $551.1M, as reported.\n")
        self.assertEqual(judge.stale(self.ws, self.con, path), ["draft"])
        second = self.seal()
        self.assertNotEqual(second, first)
        note = self.ws.root / "research" / "02_judge.md"
        note.write_text(NOTE.replace("1,757", "1,758"), encoding="utf-8")
        self.assertEqual(judge.stale(self.ws, self.con, path), ["notes"])
        third = self.seal()
        self.assertNotIn(third, (first, second))
        self.settings('[assay]\nforbidden = ["Kestrel"]')
        self.assertEqual(judge.stale(self.ws, self.con, path), ["rules"])
        rows = self.con.execute("SELECT seal, verdict FROM assay_verdicts WHERE draft='01_draft.md'").fetchall()
        self.assertEqual({seal for seal, _ in rows}, {first, second, third})
        self.assertEqual({verdict for _, verdict in rows}, {judge.PASS})
        # An address accepted is part of the rules a pass was given under.
        fourth = self.seal()
        self.settings('[assay.accept_addresses]\n"https://doi.org/10.0000/frames.2019" = "a framework article"')
        self.assertEqual(judge.stale(self.ws, self.con, path), ["rules"])
        self.assertNotEqual(self.seal(), fourth)

    def test_the_seal_names_the_version_of_the_assay_that_judged(self):
        path = self.draft("Revenue was $551.1M.\n")
        parts = judge.seal_parts(path, judge.fact_bank(self.ws, self.con), judge.rules(self.ws))
        self.assertEqual(parts[assay_seal.CHECKER_KEY], assay.__version__)

    def test_a_draft_never_judged_has_no_seal_to_go_stale(self):
        self.assertIsNone(judge.stale(self.ws, self.con, self.draft("Revenue fell.\n")))


class Run(Judged):
    def test_the_exit_status_says_whether_a_draft_failed(self):
        self.draft("Revenue was $551.1M.\n", "01_good.md")
        out, _, code = self.run_judge()
        self.assertEqual(code, 0)
        self.assertIn("01_good.md: PASS", out)
        self.source(ANNUAL, "Operating loss was 12,400 thousand.")
        self.draft("The operating loss was $12.4M.\n", "02_warned.md")
        out, _, code = self.run_judge()
        self.assertEqual(code, 0)
        self.assertIn("WARN numbers 02_warned.md:1 '$12.4M'", out)
        self.draft("Revenue was $560M.\n", "03_bad.md")
        out, _, code = self.run_judge()
        self.assertEqual(code, 1)
        self.assertIn("FAIL numbers 03_bad.md:1 '$560M'", out)
        self.assertRegex(out, r"03_bad\.md: FAIL \(1 failed, 0 warned, on numbers, titles, links\), seal [0-9a-f]{12}\n")
        with (self.ws.data / judge.REPORT).open(encoding="utf-8") as report:
            rows = list(csv.DictReader(report))
        self.assertEqual({row["draft"] for row in rows}, {"01_good.md", "02_warned.md", "03_bad.md"})

    def test_named_drafts_alone_are_judged(self):
        self.draft("Revenue was $560M.\n", "01_bad.md")
        self.draft("Revenue was $551.1M.\n", "02_good.md")
        out, _, code = self.run_judge("02_good.md")
        self.assertEqual(code, 0)
        self.assertNotIn("01_bad.md", out)
        _, err, code = self.run_judge("03_missing.md")
        self.assertIn("No such draft", err)
        self.assertEqual(code, 1)

    def test_no_drafts_is_said_and_isnt_a_failure(self):
        _, err, code = self.run_judge()
        self.assertIn("No drafts to judge", err)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
