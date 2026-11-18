"""Tests for `record`: the figures a draft gives about the workspace's own record, held to the database and to the last
`check` run. Every figure and draft here is made up; the workspace is a throwaway copy of the example."""
import unittest
from collections import Counter

from support import run_cli  # noqa: F401  (sets up the import path and the example workspace)

from drillcore import history, record
from test_proof import Proofed

NOW = {"entries": 40, "addresses": 31, "fetches": 33, "documents": 30, "companies": 3, "facts": 9000,
       "fact filings": 25, "filing list": 700, "compared": 20, "match": 18, "mismatch": 0, "no_fact": 2}
LATEST = record.Run("2026-03-02T10:00:00Z", {"judged": "410", "failed": "0", "waived": "2", "warnings": "51",
                                              "not judged": "90", "not judged: input_not_judged": "60",
                                              "not judged: no_source_key": "12", "not judged: no_text": "18",
                                              "warning: input_not_traced": "14", record.NOTES: "today"})
EARLIER = record.Run("2026-03-01T10:00:00Z", {"judged": "402", "warnings": "55", record.NOTES: "before"})


def judged(text: str, kept: list[record.Run] | None = None, notes: str = "today") -> list[tuple[int, str, str]]:
    """What the check finds in a draft whose whole text sits under "Appendix C"."""
    found = record.judge("# Appendix C. Evidence\n\n" + text, ("Appendix C",), NOW,
                         [LATEST, EARLIER] if kept is None else kept, notes)
    return [(f.line - 2, f.verdict, f.item) for f in found if f.verdict != record.PASS]


class FiguresFromTheDatabase(unittest.TestCase):
    def test_a_figure_that_is_the_databases_passes_and_one_that_isnt_fails(self):
        self.assertEqual(judged("31 distinct source addresses; 33 fetches; 30 documents with stored text.\n"), [])
        self.assertEqual(judged("31 distinct source addresses; 34 fetches.\n"), [(1, "fail", "34 fetches")])

    def test_another_measures_count_given_as_this_one_says_whose_it_is(self):
        found = list(record.judge("# Appendix C\n9,000 tagged facts from 700 filings.\n", ("Appendix C",), NOW, [LATEST], "today"))
        failed = [f for f in found if f.verdict == record.FAIL]
        self.assertEqual(len(failed), 1)
        self.assertIn("25 filings the tagged facts were drawn from", failed[0].detail)
        self.assertIn("700 is the count of entries of the companies' filing lists", failed[0].detail)
        self.assertEqual(judged("9,000 tagged facts, drawn from 25 of their filings, and the filing lists (700 entries).\n"), [])

    def test_a_count_of_a_part_is_no_count_of_the_whole(self):
        self.assertEqual(judged("Not judged: 13 source entries whose stored copy is a data file; 33 fetches.\n", kept=[]), [])
        self.assertEqual(judged("33 fetches, 5 documents with no stored text.\n"), [])

    def test_sources_alone_are_distinct_addresses_and_entries_are_a_warning(self):
        self.assertEqual(judged("31 sources; 33 fetches.\n"), [])
        self.assertEqual(judged("40 sources listed; 33 fetches.\n"), [(1, "warn", "40 sources listed")])

    def test_words_that_could_mean_anything_are_judged_only_beside_another_measure(self):
        self.assertEqual(judged("Three filings of 12 November are kept, and 9 sources were read by hand.\n"), [])
        self.assertEqual(judged("SEC data for 4 companies: 9,000 tagged facts.\n"), [(1, "fail", "4 companies")])

    def test_dates_years_amounts_and_percentages_are_no_counts(self):
        self.assertEqual(judged("Fetched on 14 March 2026 and March 3, 2026: 2026 fetches cost $5 and 7% fetches.\n"), [])

    def test_nothing_outside_the_named_sections_is_judged(self):
        text = "# Results\n\n34 fetches.\n\n# Appendix C. Evidence\n\n34 fetches.\n\n# Appendix D\n\n34 fetches.\n"
        found = list(record.judge(text, ("Appendix C",), NOW, [LATEST], "today"))
        self.assertEqual([(f.line, f.verdict) for f in found], [(7, "fail")])


class FiguresFromTheLastRun(unittest.TestCase):
    def test_the_last_runs_counts_pass_and_others_fail(self):
        self.assertEqual(judged("410 judged; 0 failed; 2 waived; 51 warnings.\n"), [])
        self.assertEqual(judged("411 judged; **0 failed**; two waivers.\n"), [(1, "fail", "411 judged")])

    def test_an_earlier_runs_count_is_a_warning_naming_it(self):
        found = list(record.judge("# Appendix C\n402 judged.\n", ("Appendix C",), NOW, [LATEST, EARLIER], "today"))
        self.assertEqual([(f.verdict, f.item) for f in found], [("warn", "402 judged")])
        self.assertIn("2026-03-01T10:00:00Z", found[0].detail)

    def test_inputs_to_derived_figures_are_those_not_judged_or_those_warned_of(self):
        self.assertEqual(judged("60 inputs to derived figures; 14 inputs to derived figures that no row holds.\n"), [])
        self.assertEqual(judged("61 inputs to derived figures.\n"), [(1, "fail", "61 inputs to derived figures")])

    def test_a_breakdown_must_add_up_to_the_runs_total(self):
        self.assertEqual(judged("- **Not judged:** 60 inputs to derived figures; 12 lines that cite no source; 18 data files.\n"), [])
        found = judged("- **Not judged:** 60 inputs to derived figures; 12 lines that cite no source.\n")
        self.assertEqual(found, [(1, "warn", "Not judged")])
        self.assertEqual(judged("Not judged: 90, of which 60 inputs to derived figures.\n"), [])

    def test_changed_notes_and_no_kept_run_are_said_once_per_section(self):
        self.assertEqual(judged("410 judged; 51 warnings.\n", notes="edited"), [(-1, "warn", "")])
        self.assertEqual(judged("410 judged; 51 warnings.\n", kept=[]), [(-1, "warn", "")])
        self.assertEqual(judged("33 fetches.\n", kept=[]), [])


MADE = record.Run("2026-03-02T10:00:00Z", {
    "judged": "410", "failed": "0", "waived": "2", "warnings": "51", "not judged": "98",
    "not judged: input_not_judged": "60", "not judged: no_source_key": "12", "not judged: not_parsed": "8",
    "not judged: source_text_unavailable": "18", "warning: input_not_traced": "14",
    "part: judged: quotation": "100", "part: judged: row": "250", "part: judged: figure": "40", "part: judged: input": "20",
    "part: not judged: input_not_judged: input": "60", "lines: not judged: input_not_judged": "21",
    "part: not judged: no_source_key: row": "9", "part: not judged: no_source_key: quotation": "3",
    "lines: not judged: no_source_key": "11",
    "part: not judged: not_parsed: working": "6", "part: not judged: not_parsed: total": "2", "lines: not judged: not_parsed": "8",
    "part: not judged: source_text_unavailable: row": "18", "lines: not judged: source_text_unavailable": "18",
    record.NOTES: "today"})


class WhatACountCounts(unittest.TestCase):
    def test_judged_counts_quotations_so_figures_alone_is_the_wrong_name(self):
        self.assertEqual(judged("- **Figures held to their source:** 410 judged; **0 failed**.\n", kept=[MADE]),
                         [(1, "fail", "410 judged")])
        self.assertEqual(judged("410 figures judged.\n", kept=[MADE]), [(1, "fail", "410 figures judged")])
        self.assertEqual(judged("Quotations and figures held to their source: 410 judged (100 quotations).\n", kept=[MADE]), [])
        self.assertEqual(judged("Run of 2 March: 410 judged; 0 failed.\n", kept=[MADE]), [])
        # A run that kept no makeup says nothing about it.
        self.assertEqual(judged("Figures held to their source: 410 judged.\n"), [])

    def test_lines_are_the_lines_the_results_stand_on(self):
        found = list(record.judge("# Appendix C\n12 lines that cite no source.\n", ("Appendix C",), NOW, [MADE], "today"))
        self.assertEqual([(f.verdict, f.item) for f in found], [("fail", "12 lines that cite no source")])
        self.assertIn("9 rows of figures, 3 quotations", found[0].detail)
        self.assertIn("they stand on 11 lines", found[0].detail)
        self.assertEqual(judged("11 lines that cite no source.\n", kept=[MADE]), [])
        self.assertEqual(judged("10 lines that cite no source.\n", kept=[MADE]), [(1, "fail", "10 lines that cite no source")])

    def test_a_breakdowns_parts_are_called_what_they_count(self):
        found = judged("- **Not judged:** 60 inputs to derived figures; 12 lines that cite no source; 8 sums whose cells "
                       "it could not read; 18 rows with no stored text.\n", kept=[MADE])
        self.assertEqual(found, [(1, "fail", "12 lines that cite no source"), (1, "fail", "8 sums whose cells it could not read")])
        self.assertEqual(judged("- **Not judged:** 60 inputs to derived figures; 9 rows of figures and 3 quotations that "
                                "cite no source; 8 workings and totals it could not read (6 workings, 2 totals); 18 rows "
                                "with no stored text.\n", kept=[MADE]), [])

    def test_counts_in_brackets_break_a_part_down_and_add_none(self):
        self.assertEqual(judged("Not judged: 60 inputs; 12 unsourced (9 rows, 3 quotations); 8 unread; 18 with no text.\n",
                                kept=[MADE]), [])


class KeptCounts(Proofed):
    def test_check_keeps_what_its_counts_are_made_of(self):
        self.run_here("check")
        latest = record.runs(self.con)[0].values()
        # Nothing is fetched here, so nothing is judged; what wasn't, is kept by what it is.
        self.assertEqual(sum(n for key, n in latest.items() if key.startswith("part: judged: ")), latest["judged"])
        self.assertTrue(any(key.startswith("part: not judged: ") for key in latest))
        for key, n in latest.items():
            if key.startswith(("not judged: ", "warning: ")):
                self.assertEqual(sum(v for k, v in latest.items() if k.startswith(f"part: {key}: ")), n, key)
                self.assertLessEqual(latest[f"lines: {key}"], n, key)

    def test_a_runs_counts_are_kept_beside_it_and_go_with_it(self):
        for n in range(history.KEEP + 2):
            history.compare(self.con, "check", [])
            record.keep(self.con, self.ws, "check", record.counts(100 + n, Counter({("warning", "unused"): 3})))
        kept = record.runs(self.con)
        self.assertEqual(len(kept), history.KEEP)
        self.assertEqual(kept[0].values()["judged"], 100 + history.KEEP + 1)
        self.assertEqual(kept[0].values()["warning: unused"], 3)
        self.assertEqual(kept[0].kept[record.NOTES], record.digest(self.ws))

    def test_check_keeps_its_counts_and_proof_holds_a_section_to_them(self):
        self.run_here("check")
        latest = record.runs(self.con)[0].values()
        self.settings(references=["report/references.md"], workspace_sections=["Appendix C"])
        self.draft(f"# Appendix C. Evidence of activities\n\n{latest['judged']} judged; {latest['warnings']} warnings.\n\n"
                   f"Run again: {latest['judged'] + 1} judged.\n")
        found = self.found("workspace figures")
        self.assertEqual(found, [("01_draft.md", 5, "fail", f"{latest['judged'] + 1} judged")])
        out, _, code = self.run_here("proof")
        self.assertEqual(code, 1)
        self.assertIn("workspace figures 1 failed, 0 warned, 2 passed with a reason given", out)

    def test_no_sections_named_is_no_check(self):
        self.draft("# Appendix C\n\n999 fetches.\n")
        self.assertEqual(self.found("workspace figures"), [])


if __name__ == "__main__":
    unittest.main()
