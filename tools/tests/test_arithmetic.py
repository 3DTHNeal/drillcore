"""Tests for the arithmetic check: the parser for sums, the forms a working takes, which rows count as worked out, and
the command's report. Every note here is fictional."""
import argparse
import contextlib
import io
import sqlite3
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from support import WORKSPACE

from drillcore import arithmetic, formula, workspace


def verdicts(text: str) -> list[tuple[int, str, str]]:
    """(line, status, figure as written) for each result on a note's text."""
    return [(result.line, result.status, result.stated) for result in arithmetic.check_text("n.md", text)]


def one(row: str) -> arithmetic.Result:
    """The single result on a worked-out bullet."""
    results = arithmetic.check_text("n.md", f"COMPUTED:\n\n{row}\n")
    assert len(results) == 1, results
    return results[0]


class Evaluate(unittest.TestCase):
    def test_arithmetic_and_order(self):
        self.assertEqual(formula.evaluate("95.4 - 67.5"), Fraction("27.9"))
        self.assertEqual(formula.evaluate("2 + 3 * 4"), 14)
        self.assertEqual(formula.evaluate("(2 + 3) * 4"), 20)
        self.assertEqual(formula.evaluate("10 - 4 - 3"), 3)
        self.assertEqual(formula.evaluate("12 / 4 / 3"), 1)
        self.assertEqual(formula.evaluate("-(2 - 5)"), 3)
        self.assertEqual(formula.evaluate("--2"), 2)

    def test_commas_percent_and_other_signs(self):
        self.assertEqual(formula.evaluate("1,757 - 1,820"), -63)
        self.assertEqual(formula.evaluate("3% * 40"), Fraction("1.2"))
        self.assertEqual(formula.evaluate("41.2% - 44.9%"), Fraction("-0.037"))
        self.assertEqual(formula.evaluate("6 × 7 − 2 ÷ 4"), Fraction("41.5"))
        self.assertEqual(formula.evaluate(".5 + 1,234,567.25"), Fraction("1234567.75"))

    def test_anything_but_arithmetic_is_refused(self):
        for bad in ("__import__('os')", "__import__('os').system('echo hi')", "2 ** 10", "log(2)", "nosuch(2)", "1e3", "1,23",
                    "2 +", "(2", "2)", "2 3", "", "   ", "%", "1 / 0", "1 / (2 - 2)", "x + 1", "2 // 1",
                    "(" * 500 + "1" + ")" * 500, "-" * 500 + "1"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                formula.evaluate(bad)


class Forms(unittest.TestCase):
    def test_change_new_against_old(self):
        result = one("- Revenue change: -3.7% (551.1 against 572.5).")
        self.assertEqual((result.status, result.stated, result.detail), ("ok", "-3.7%", "551.1 against 572.5"))
        self.assertAlmostEqual(result.computed or 0, -3.7380, places=3)
        self.assertEqual(one("- Revenue change: -3.7% (551.1 vs 572.5).").status, "ok")
        self.assertEqual(one("- Revenue change: -3.7% (551.1 vs. 572.5).").status, "ok")
        self.assertEqual(one("- Revenue change: -3.7% ($551.1M versus $572.5M).").status, "ok")

    def test_change_written_old_first(self):
        self.assertEqual(one("- Revenue change: -3.7% (from 572.5 to 551.1).").status, "ok")
        self.assertEqual(one("- Revenue change: 3.9% (from 551.1 to 572.5).").status, "ok")

    def test_share(self):
        self.assertEqual(one("- Due within a year: 70.8% (67.5 of 95.4).").status, "ok")
        self.assertEqual(one("- Due within a year: 71% (67.5 of 95.4).").status, "ok")
        self.assertEqual(one("- Due within a year: 70% (67.5 of 95.4).").status, "wrong")

    def test_expression(self):
        self.assertEqual(one("- Due after a year: $27.9M (= 95.4 - 67.5).").status, "ok")
        wrong = one("- Due after a year: $28.4M (= 95.4 - 67.5).")
        self.assertEqual((wrong.status, wrong.stated, wrong.shown()), ("wrong", "$28.4M", "27.9"))
        self.assertEqual(one("- Margin fell 3.7pp (= 41.2% - 44.9%).").status, "ok")
        self.assertEqual(one("- Share: 70.8% (= 67.5 / 95.4).").status, "ok")
        self.assertEqual(one("- Staff change: -63 (= 1,757 - 1,820).").status, "ok")

    def test_rounding_is_half_a_unit_in_the_last_place(self):
        self.assertEqual(one("- Revenue change: -3.74% (551.1 against 572.5).").status, "ok")
        self.assertEqual(one("- Revenue change: -3.73% (551.1 against 572.5).").status, "wrong")
        self.assertEqual(one("- Revenue change: -3.8% (551.1 against 572.5).").status, "wrong")
        self.assertEqual(one("- Half: 2.5 (= 2.45 + 0.1)").status, "ok")
        self.assertEqual(one("- Edge: 2.5 (= 2.55)").status, "ok")
        self.assertEqual(one("- Over: 2.5 (= 2.551)").status, "wrong")

    def test_sign(self):
        self.assertEqual(one("- Revenue fell 3.7% (551.1 against 572.5).").status, "ok")
        self.assertEqual(one("- Revenue change: +3.7% (551.1 against 572.5).").status, "wrong")
        self.assertEqual(one("- Revenue change: −3.7% (551.1 against 572.5).").status, "ok")

    def test_remark_after_a_semicolon(self):
        self.assertEqual(one("- Revenue change: -3.7% (551.1 against 572.5; both in $M).").status, "ok")

    def test_unreadable_workings_are_unparsed(self):
        hostile = one("- Implied: 5.0 (= __import__('os').system('echo hi')).")
        self.assertEqual(hostile.status, "unparsed")
        self.assertIn("can't be read", hostile.detail)
        self.assertEqual(one("- Implied: 5.0 (= 1 / 0).").status, "unparsed")
        self.assertIn("percentage", one("- Implied: $5.0M (551.1 against 572.5).").detail)
        self.assertEqual(one("- Implied: 5.0% (5.0 of 0).").status, "unparsed")

    def test_a_worked_out_row_without_working(self):
        result = one("- Revenue change: -3.7% (S1).")
        self.assertEqual((result.status, result.stated, result.computed), ("unparsed", "", None))
        self.assertEqual(one("- Revenue change: -3.7%, from the table.").status, "unparsed")


class Rows(unittest.TestCase):
    def test_which_rows_are_worked_out(self):
        text = "\n".join([
            "# Notes",                                              # 1
            "- Unmarked: -3.9% (551.1 against 572.5).",             # 2  not worked out: skipped
            "- Derived: -3.9% (551.1 against 572.5).",              # 3  marked on the row
            "",                                                     # 4
            "COMPUTED from the table above:",                       # 5
            "",                                                     # 6
            "- Change: -3.7% (551.1 against 572.5).",               # 7  marked by the lead-in
            "- No working: 12.5%.",                                 # 8
            "- No figure at all.",                                  # 9
            "",                                                     # 10
            "Back to sourced figures (S1).",                        # 11 prose without a marker ends the lead-in
            "- Revenue was 551.1 (S1).",                            # 12
            "## Implied figures",                                   # 13 marked heading
            "| Item | Change |",                                    # 14 no figure
            "|---|---|",                                            # 15
            "| Revenue | -3.7% (551.1 against 572.5) | 71% (67.5 of 95.4) |",  # 16
            "## Sources",                                           # 17
            "- **S1.** Derived: 5.0 (= 1 + 1). https://example.com/a(1).html",  # 18 skipped
        ])
        self.assertEqual(verdicts(text), [(3, "wrong", "-3.9%"), (7, "ok", "-3.7%"), (8, "unparsed", ""),
                                          (16, "ok", "-3.7%"), (16, "ok", "71%")])

    def test_a_url_in_a_row_is_not_read_as_a_working(self):
        self.assertEqual(one("- Implied: 4.0% (= 2% * 2) https://example.com/x/12.5(3).html").status, "ok")


class Equations(unittest.TestCase):
    def test_what_counts_as_an_equation(self):
        texts = lambda line: [e.text for e in arithmetic.equations(line)]
        self.assertEqual(texts("$613.0 million = $201.4 million cash + 48,218,063 shares"), [])  # Words break it.
        self.assertEqual(texts("the range 2.5-3.1% = 3"), [])
        self.assertEqual(texts("$942.4 million ($942,408 thousand) = 150.4 + 792.0"), ["( $942,408 thousand ) = 150.4 + 792.0"])
        self.assertEqual(texts("613.0 / 66.574 = 9.2x (575 / 66.574 = 8.6x on announced value)"),
                         ["613.0 / 66.574 = 9.2x", "575 / 66.574 = 8.6x"])
        for line in ("$942.4 million ($942,408 thousand) = 150.4 + 792.0", "613.0 / 66.574 = 9.2x (575 / 66.574 = 8.6x)",
                     "$115,080k / $5.00 = about 23.0 million shares", "59,253 + 31,803 - 24,482 = $66,574 thousand",
                     "25% x 520.8 = $130.2M", "-$25.5M = (244.5 - 150.7) - 119.3"):
            for equation in arithmetic.equations(line):
                self.assertTrue(arithmetic.recompute(equation)[0], equation.text)
        nothing = arithmetic.equations("5 / (2 - 2) = 1")
        self.assertEqual(arithmetic.recompute(nothing[0]), (False, "it divides by a figure that could be zero"))

    def test_rounding_in_figures(self):
        whole = arithmetic.figure(arithmetic.AMOUNT.fullmatch("24"))
        self.assertEqual((whole.value, whole.half), (24, 0))  # A count as an input is exact.
        self.assertEqual(arithmetic.figure(arithmetic.AMOUNT.fullmatch("24"), as_result=True).half, Fraction(1, 2))
        scaled = arithmetic.figure(arithmetic.AMOUNT.fullmatch("$1.5M"))
        self.assertEqual((scaled.value, scaled.half), (1_500_000, 50_000))
        self.assertEqual(arithmetic.figure(arithmetic.AMOUNT.fullmatch("37.5%")).value, Fraction(3, 8))

    def test_equations_are_read_anywhere_in_the_body_and_rounded_inputs_are_allowed_for(self):
        text = "\n".join([
            "# Notes",                                                  # 1
            "Revenue was 150.4 + 43.2 = $193.6 million (S1).",          # 2  prose, not worked out: still read
            "- Deals: 12 + 8 = 21 (S1).",                               # 3  wrong
            "- Chained: 7.34 x 1.335 = 9.79.",                          # 4  ok only within the inputs' rounding
            "- Growth: 6.063 / 5.165 = +17.4%.",                        # 5  a change
            "- Split: 5 / (2 - 2) = 1.",                                # 6  can't be read
            "",
            "| Measure | Result | Arithmetic |",                        # 8
            "|---|---|---|",
            "| Revenue change | about -3.7% | (551.1 - 572.5) / 572.5 |",  # 10
            "| Share | 31.0% | R&D / revenue |",                        # 11 not worked out, so nothing to say
            "## Sources",
            "- **S1.** 1 + 1 = 3. https://example.com/a",               # 13 skipped
        ])
        results = [(r.line, r.status, r.item) for r in arithmetic.check_text("n.md", text)]
        self.assertEqual(results, [(2, "ok", "150.4 + 43.2 = $193.6 million"), (3, "wrong", "12 + 8 = 21"),
                                   (4, "ok", "7.34 x 1.335 = 9.79"), (5, "ok", "6.063 / 5.165 = +17.4%"),
                                   (6, "unparsed", "5 / ( 2 - 2 ) = 1"), (10, "ok", "(551.1 - 572.5) / 572.5 = about -3.7%")])
        why = {r.line: r.why for r in arithmetic.check_text("n.md", text)}
        self.assertEqual(why[3], "computes to 20, not 21")
        self.assertIn("within the rounding of its inputs", why[4])
        self.assertEqual(why[5], "recomputes as a change: 17.3863%")

    def test_brackets_are_exact_but_an_equation_allows_for_its_inputs_rounding(self):
        # -3.73% is what 551.1 / 572.5 - 1 gives only if the inputs may be off by half their last digit.
        self.assertEqual(one("- Revenue change: -3.73% (= (551.1 - 572.5) / 572.5 * 100%)").status, "wrong")
        self.assertEqual(one("- Revenue change: (551.1 - 572.5) / 572.5 = -3.73%").status, "ok")

    def test_a_working_in_brackets_isnt_read_again_as_an_equation(self):
        result = one("- Due after a year: $27.9M (= 95.4 - 67.5).")
        self.assertEqual((result.status, result.item, result.why), ("ok", "$27.9M (= 95.4 - 67.5)", "gives 27.9"))
        both = arithmetic.check_text("n.md", "COMPUTED:\n\n- Both: 27.9 (= 95.4 - 67.5), and 1 + 1 = 2.\n")
        self.assertEqual([(r.status, r.item) for r in both], [("ok", "27.9 (= 95.4 - 67.5)"), ("ok", "1 + 1 = 2")])


def results(text: str) -> dict[str, tuple[str, str]]:
    """Each result on a note's text by what it judged, as (status, why or detail)."""
    return {r.item: (r.status, r.why or r.detail) for r in arithmetic.check_text("n.md", text)}


class Conversions(unittest.TestCase):
    def test_a_conversion_with_its_rate_recomputes_on_any_line(self):
        found = results("# Notes\n\nRevenue was $510M (RMB 3.7bn at 7.25), the release says (S1).\n"
                        "- Booked: €5.0M (£4.3M @ 0.86).\n- At a rate of: $510M (RMB 3.7bn at a rate of 7.25).\n")
        self.assertEqual(found["$510M (RMB 3.7bn at 7.25)"], ("ok", "recomputes at 7.25 RMB to the $: $510.3448M"))
        self.assertEqual(found["€5.0M (£4.3M @ 0.86)"][0], "ok")
        self.assertEqual(found["$510M (RMB 3.7bn at a rate of 7.25)"][0], "ok")

    def test_the_rate_is_the_bracketed_currency_to_one_of_the_figures_unless_written_otherwise(self):
        found = results("- Other way: $510M (RMB 3.7bn at 0.138 $/RMB).\n- Per: $510M (RMB 3.7bn at 0.138 USD per RMB).\n"
                        "- Wrong way: $510M (RMB 3.7bn at 0.138).\n- Neither: $510M (RMB 3.7bn at 7.25 EUR/$).\n")
        self.assertEqual(found["$510M (RMB 3.7bn at 0.138 $/RMB)"][0], "ok")
        self.assertEqual(found["$510M (RMB 3.7bn at 0.138 USD per RMB)"][0], "ok")
        status, why = found["$510M (RMB 3.7bn at 0.138)"]
        self.assertEqual(status, "wrong")
        self.assertIn("write it as 0.138 $/RMB", why)
        self.assertEqual(found["$510M (RMB 3.7bn at 7.25 EUR/$)"],
                         ("unparsed", "$510M (RMB 3.7bn at 7.25 EUR/$): the rate is written in EUR per $, but the conversion is from RMB to $"))

    def test_the_rounding_of_the_amount_and_the_rate_is_allowed_for_and_no_more(self):
        self.assertEqual(results("- $510M (RMB 3.7bn at 7.25)\n")["$510M (RMB 3.7bn at 7.25)"][0], "ok")
        self.assertEqual(results("- $530M (RMB 3.7bn at 7.25)\n")["$530M (RMB 3.7bn at 7.25)"],
                         ("wrong", "computes to $510.3448M at 7.25 RMB to the $, not $530M; if the rate is $ per RMB, write it as 7.25 $/RMB"))
        self.assertEqual(results("- $510M (RMB 3,700 million at 7.25)\n")["$510M (RMB 3,700 million at 7.25)"][0], "ok")

    def test_a_conversion_without_its_rate_is_unparsed_and_one_currency_is_no_conversion(self):
        found = results("- Revenue was $510M (RMB 3.7bn) (S1).\n- Restated: $510M ($0.51bn).\n")
        self.assertEqual(found["$510M (RMB 3.7bn)"][0], "unparsed")
        self.assertIn("no rate written", found["$510M (RMB 3.7bn)"][1])
        self.assertEqual(len(found), 1)

    def test_a_conversion_on_a_worked_out_row_isnt_read_again(self):
        self.assertEqual([(r.status, r.item) for r in arithmetic.check_text("n.md", "COMPUTED:\n\n- $510M (RMB 3.7bn at 7.25).\n")],
                         [("ok", "$510M (RMB 3.7bn at 7.25)")])

    def test_the_converted_figure_is_blanked_for_the_numbers_check(self):
        line = "- Revenue was $510M (RMB 3.7bn at 7.25) and $5M (RMB 36M) (S1)."
        blanked = arithmetic.without_conversions(line)
        self.assertEqual(len(blanked), len(line))
        self.assertNotIn("$510M", blanked)
        self.assertIn("RMB 3.7bn at 7.25", blanked)
        self.assertIn("$5M (RMB 36M)", blanked)  # No rate, so nothing recomputed it: it's still for a source to hold.


TABLE = """# Notes

| Segment | 2025 | 2024 | Change | Source |
|---|---|---|---|---|
| Robots | 300.0 | 310.2 | -3.3% | S1 |
| Software | 251.1 | 262.3 | -4.3% | S1 |
| of which cloud | 80.0 | 70.0 | 14% | S1 |
| **Total** | 551.1 | 580.0 | -3.7% | S1 |
"""


class Footing(unittest.TestCase):
    def test_each_column_adds_to_its_total_allowing_for_rounding(self):
        found = results(TABLE)
        self.assertEqual(found["Total, 2025: 300.0 + 251.1 = 551.1"], ("ok", "recomputes: 551.1"))
        self.assertEqual(found["Total, 2024: 310.2 + 262.3 = 580.0"], ("wrong", "computes to 572.5, not 580.0"))
        self.assertEqual(len(found), 2)  # Not the change, not the sources, not the "of which" row.
        self.assertEqual(results(TABLE.replace("580.0", "572.6"))["Total, 2024: 310.2 + 262.3 = 572.6"][0], "ok")
        self.assertEqual(results(TABLE.replace("580.0", "572.7"))["Total, 2024: 310.2 + 262.3 = 572.7"][0], "wrong")
        lines = [(r.line, r.status) for r in arithmetic.check_text("n.md", TABLE)]
        self.assertEqual(lines, [(8, "ok"), (8, "wrong")])

    def test_a_tables_total_is_a_total_and_a_rows_working_is_a_working(self):
        # A report counting what couldn't be read says "totals" or "workings", and `check` keeps which is which.
        text = TABLE + "\nCOMPUTED:\n\n- Change: -3.7% (551.1 against 572.5).\n- No working: 12.5%.\n"
        kinds = {(r.status, r.kind) for r in arithmetic.check_text("n.md", text)}
        self.assertEqual(kinds, {("ok", arithmetic.TOTAL), ("wrong", arithmetic.TOTAL), ("ok", arithmetic.WORKING),
                                 ("unparsed", arithmetic.WORKING)})

    def test_a_total_x_row_that_isnt_a_sum_is_not_judged_but_a_bare_total_is(self):
        kpis = "\n".join(["| Item | 2025 |", "|---|---|", "| Revenue, $M | 551.1 |", "| Operating profit, $M | 40.2 |",
                          "| Total debt, $M | 120.0 |", "| Total average price | 3.1 |", ""])
        found = [(r.status, r.detail) for r in arithmetic.check_text("n.md", kpis)]
        self.assertEqual([status for status, _ in found], ["unparsed"])
        self.assertIn("label doesn't say it's their total", found[0][1])
        excluded = kpis.replace("Total debt, $M", "Total (excl. B)")
        self.assertEqual([r.status for r in arithmetic.check_text("n.md", excluded)], ["unparsed"])
        self.assertEqual([r.status for r in arithmetic.check_text("n.md", kpis.replace("Total debt, $M", "Total, $M"))], ["wrong"])

    def test_a_later_total_may_add_the_totals_above_it(self):
        sheet = "\n".join(["| Item | 2025 |", "|---|---|", "| Cash | 10 |", "| Receivables | 20 |", "| Total current assets | 30 |",
                           "| Plant | 50 |", "| Total assets | 80 |", "| Debt | 40 |", "| Total liabilities | 45 |",
                           "| Total equity and liabilities | 35 |"])
        found = results(sheet)
        self.assertEqual(found["Total assets, 2025: 30 + 50 = 80"][0], "ok")
        # "Total liabilities" names what it totals, so a row that doesn't add up is shown, not failed: a table of key
        # figures has "Total debt" rows that were never meant as the sum of the rows above them.
        status, why = found["Total liabilities, 2025: 40 = 45"]
        self.assertEqual(status, "unparsed")
        self.assertIn("computes to 40, not 45; nor with the totals above it", why)
        self.assertEqual(found["Total equity and liabilities, 2025: 45 = 35"][0], "unparsed")

    def test_segments_add_to_the_consolidated_or_group_figure(self):
        found = results("| Segment | Revenue | Share |\n|---|---|---|\n| A | (1.0) | 25% |\n| B | — | 75% |\n| Eliminations | 0.5 | - |\n"
                        "| Group | -0.5 | 100% |\n\n| Segment | Revenue |\n|---|---|\n| A | 1.0 |\n| B | 2.0 |\n| Consolidated | 4.0 |\n")
        self.assertEqual(found["Group, Revenue: (1.0) + — + 0.5 = -0.5"][0], "ok")
        self.assertEqual(found["Group, Share: 25% + 75% + - = 100%"], ("ok", "adds to 100%"))
        self.assertEqual(found["Consolidated, Revenue: 1.0 + 2.0 = 4.0"][0], "wrong")

    def test_a_cell_it_cant_read_leaves_the_column_unparsed(self):
        found = results("| Segment | Revenue |\n|---|---|\n| A | 1.0 |\n| B | n/a |\n| Total | 2.0 |\n")
        self.assertEqual(found["Total, Revenue"], ("unparsed", "Total, Revenue can't be footed: line 4's cell 'n/a' isn't a figure this adds"))
        # A percentage total other than 100% is a margin or a change, and isn't added.
        self.assertEqual(results("| Item | Margin now |\n|---|---|\n| A | 40% |\n| B | 30% |\n| Total | 35% |\n"), {})

    def test_shares_without_a_total_row(self):
        over = results("| Customer | Share of revenue |\n|---|---|\n| A | 60% |\n| B | 45% |\n")
        self.assertEqual(over["Share of revenue, every row: 60% + 45% = 100%"], ("wrong", "adds to 105%, not 100%"))
        self.assertEqual(results("| Customer | Share |\n|---|---|\n| A | 60% |\n| Other | 30% |\n")["Share, every row: 60% + 30% = 100%"][0],
                         "wrong")
        self.assertEqual(results("| Customer | Share |\n|---|---|\n| A | 60.4% |\n| B | 39.7% |\n")["Share, every row: 60.4% + 39.7% = 100%"][0],
                         "ok")
        # The top customers needn't make up the whole, and a column of growth rates isn't one of shares.
        self.assertEqual(results("| Customer | Share |\n|---|---|\n| A | 60% |\n| B | 30% |\n"), {})
        self.assertEqual(results("| Customer | Growth |\n|---|---|\n| A | 60% |\n| B | 70% |\n"), {})

    def test_the_sources_section_and_a_result_and_arithmetic_table_arent_footed(self):
        self.assertEqual(results("## Sources\n\n| Item | 2025 |\n|---|---|\n| A | 1 |\n| Total | 5 |\n"), {})
        self.assertNotIn("Total, Result", " ".join(results("| Measure | Result | Arithmetic |\n|---|---|---|\n| Total | 3 | 1 + 2 |\n")))


class Workspaces(unittest.TestCase):
    def test_the_example_note(self):
        lines = (WORKSPACE / "research" / "01_northbridge.md").read_text(encoding="utf-8").splitlines()
        line = next(at for at, text in enumerate(lines, 1) if "-3.7% (551.1 against 572.5)" in text)
        results = [r for r in arithmetic.check(workspace.Workspace(WORKSPACE)) if r.note == "01_northbridge.md" and r.line == line]
        self.assertEqual([(r.status, r.stated) for r in results], [("ok", "-3.7%")])

    def test_the_command_reports_and_exits_1_on_a_wrong_working(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            notes = Path(folder) / "research"
            notes.mkdir()
            note = "# Fictional\n\nCOMPUTED:\n\n- Fine: 70.8% (67.5 of 95.4).\n- Off: $28.4M (= 95.4 - 67.5).\n- Bare: 12.5%.\n"
            (notes / "a.md").write_text(note, encoding="utf-8")
            out = io.StringIO()
            with contextlib.closing(sqlite3.connect(":memory:")) as con, contextlib.redirect_stdout(out):
                code = arithmetic.run(workspace.Workspace(Path(folder)), con, argparse.Namespace())
            printed = out.getvalue()
            self.assertEqual(code, 1)
            self.assertIn("a.md:6  wrong     $28.4M (= 95.4 - 67.5) gives 27.9", printed)
            self.assertIn("a.md:7  unparsed", printed)
            self.assertIn("1 ok, 1 wrong, 1 unparsed", printed)
            (notes / "a.md").write_text(note.replace("28.4", "27.9"), encoding="utf-8")
            with contextlib.closing(sqlite3.connect(":memory:")) as con, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(arithmetic.run(workspace.Workspace(Path(folder)), con, argparse.Namespace()), 0)


RESULTS = """# Fictional

| Item | 2025 | 2024 | 2023 |
|---|---|---|---|
| Revenue, $M | 551.1 | 572.5 | 545.2 |
| Gross profit, $M | 227.0 | 257.0 | 240.0 |
| Gross margin | 41.2% | 44.9% | 44.0% |
| Revenue growth | -3.7% | 5.0% | |
"""


class Formulas(unittest.TestCase):
    def test_a_compound_rate(self):
        for working in ("from 450.0 to 551.1 over 5 years", "CAGR 450.0 to 551.1 in 5 years", "450.0 to 551.1, over 5 years",
                        "= cagr(450.0, 551.1, 5)", "= (551.1 / 450.0) ^ (1 / 5) - 1"):
            with self.subTest(working=working):
                result = one(f"- Revenue grew 4.1% ({working}) a year.")
                self.assertEqual((result.status, result.why), ("ok", "gives 4.1366%"))
        self.assertEqual(one("- Grew 4.2% (from 450.0 to 551.1 over 5 years).").status, "wrong")
        self.assertIn("percentage", one("- Grew 4.1 (from 450.0 to 551.1 over 5 years).").detail)
        self.assertIn("zero or negative", one("- Grew 4.1% (= cagr(-450.0, 551.1, 5)).").detail)
        self.assertEqual(one("- Grew 4.1% (from 450.0 to 551.1 over 5 years).").inputs, ("450.0", "551.1"))

    def test_functions_and_powers_in_equations(self):
        found = results("- Average: avg(551.1, 572.5) = 561.8.\n- Compounded: 1.05^3 = 1.158.\n- Off: sqrt(16) = 5.\n")
        self.assertEqual(found["avg(551.1, 572.5) = 561.8"][0], "ok")
        self.assertEqual(found["1.05 ^ 3 = 1.158"][0], "ok")
        self.assertEqual(found["sqrt(16) = 5"], ("wrong", "computes to 4, not 5"))

    def test_a_working_can_name_the_notes_figures(self):
        text = RESULTS + ("\nCOMPUTED:\n\n- Margin: 41.2% (= {Gross profit 2025} / {Revenue 2025}).\n"
                          "- Margin: 41.0% (= {Gross profit 2025} / {Revenue 2025}).\n"
                          "- Vague: 41.2% (= {Gross profit} / {Revenue}).\n- Missing: 1.0 (= {Net profit 2025}).\n")
        found = results(text)
        self.assertEqual(found["41.2% (= {Gross profit 2025} / {Revenue 2025})"], ("ok", "gives 41.1903% from 227.0 / 551.1"))
        self.assertEqual(found["41.0% (= {Gross profit 2025} / {Revenue 2025})"][0], "wrong")
        status, why = found["41.2% (= {Gross profit} / {Revenue})"]
        self.assertEqual(status, "unparsed")
        self.assertIn("name the period", why)
        self.assertEqual(found["1.0 (= {Net profit 2025})"], ("unparsed", "{Net profit 2025} names no figure a table of the notes states for 2025"))
        inputs = [r.inputs for r in arithmetic.check_text("n.md", text) if r.status == "ok" and "{" in r.item]
        self.assertEqual(inputs, [("227.0", "551.1")])  # Traced to the notes like any other input.

    def test_an_equation_can_name_the_notes_figures(self):
        found = results(RESULTS + "\nThe margin was {Gross profit 2025} / {Revenue 2025} = 41.2%, on {Revenue 2025} = $551.1M.\n")
        self.assertEqual(found["{Gross profit 2025} / {Revenue 2025} = 41.2%"],
                         ("ok", "recomputes: 41.1903%, from 227.0 / 551.1 = 41.2%"))
        self.assertEqual(found["{Revenue 2025} = $551.1M"][0], "ok")


def run_with(rules: str, note: str) -> tuple[int, str, list[arithmetic.Result]]:
    """`drillcore arithmetic` on a workspace with these rules and one note, and the results `check` gives."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        (Path(folder) / "research").mkdir()
        (Path(folder) / "research" / "a.md").write_text(note, encoding="utf-8")
        (Path(folder) / "workspace.toml").write_text(rules, encoding="utf-8")
        ws = workspace.Workspace(Path(folder))
        out = io.StringIO()
        with contextlib.closing(sqlite3.connect(":memory:")) as con, contextlib.redirect_stdout(out):
            code = arithmetic.run(ws, con, argparse.Namespace())
        return code, out.getvalue(), arithmetic.check(ws)


MARGIN = '[[arithmetic.rules]]\nname = "Gross margin"\nformula = "{Gross margin} = {Gross profit} / {Revenue}"\n'
GROWTH = '[[arithmetic.rules]]\nformula = "{Revenue} / {Revenue, prior} - 1 = {Revenue growth}"\n'


class Rules(unittest.TestCase):
    def test_a_rule_holds_each_period_the_notes_state_it_for(self):
        code, printed, found = run_with(MARGIN + GROWTH, RESULTS)
        verdicts = [(r.line, r.status, r.item) for r in found if r.rule]
        self.assertEqual(verdicts, [
            (7, "ok", "Gross margin, 2025: 41.2% = 227.0 / 551.1"),
            (7, "ok", "Gross margin, 2024: 44.9% = 257.0 / 572.5"),
            (7, "ok", "Gross margin, 2023: 44.0% = 240.0 / 545.2"),
            (8, "ok", "{Revenue} / {Revenue, prior} - 1 = {Revenue growth}, 2025: -3.7% = 551.1 / 572.5 - 1"),
            (8, "ok", "{Revenue} / {Revenue, prior} - 1 = {Revenue growth}, 2024: 5.0% = 572.5 / 545.2 - 1"),
        ])
        self.assertEqual(code, 0)
        self.assertIn("5 ok, 0 wrong", printed)

    def test_a_figure_that_breaks_a_rule_is_wrong(self):
        code, printed, _ = run_with(MARGIN, RESULTS.replace("44.9%", "45.9%"))
        self.assertEqual(code, 1)
        self.assertIn("a.md:7  wrong     Gross margin, 2024: 45.9% = 257.0 / 572.5 computes to 44.8908%, not 45.9%", printed)

    def test_a_rule_that_judges_nothing_is_a_warning(self):
        rule = '[[arithmetic.rules]]\nformula = "{Net margin} = {Net profit} / {Revenue}"\n'
        code, printed, found = run_with(rule, RESULTS)
        self.assertEqual((code, [r for r in found if r.rule]), (0, []))
        self.assertIn("warning: the rule '{Net margin} = {Net profit} / {Revenue}' judged nothing", printed)

    def test_a_name_that_matches_two_figures_is_unparsed(self):
        note = RESULTS + "\n| Item | 2025 |\n|---|---|\n| Revenue | 600.0 |\n"
        _, _, found = run_with(MARGIN, note)
        unparsed = [r for r in found if r.rule and r.status == "unparsed"]
        self.assertEqual(len(unparsed), 1)
        self.assertIn("{Revenue} names more than one figure", unparsed[0].detail)

    def test_a_rule_that_cant_be_read_stops_the_run(self):
        for rules, said in (('[[arithmetic.rules]]\nname = "x"\n', "needs a formula"),
                            ('[[arithmetic.rules]]\nformula = "{A} = {B} = {C}"\n', "needs one ="),
                            ('[[arithmetic.rules]]\nformula = "{A} + 1 = {B} + 2"\n', "alone in braces"),
                            ('[[arithmetic.rules]]\nformula = "{A} = 2 + 2"\n', "names no figure"),
                            ('[[arithmetic.rules]]\nformula = "{A} = import(1)"\n', "isn't a function"),
                            ('[arithmetic]\nrules = "{A} = {B}"\n', "table of their own")):
            with self.subTest(rules=rules), self.assertRaises(workspace.WorkspaceError) as caught:
                run_with(rules, RESULTS)
            self.assertIn(said, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
