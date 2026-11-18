"""Tests for two readings of a figure beyond its value: a note's working read again from the facts as filed (`filed`,
and `assay` on a draft that copies it), and a figure the notes qualify, as a change or as someone's estimate, that a
draft states without the qualifier. Every note, claim and draft here is made up, in a throwaway copy of the example."""
import argparse
import contextlib
import csv
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from support import CODE_ROOT

from drillcore import cli, filed, judge, sourcedb, workspace

COMPANY, OTHER = 9999999, 8888888
NOTE = """# Ratios notes

Fictional, for the tests.

## 1. Ratios, Larkspur Printing (COMPUTED)

| Year | Operating margin | Return on equity | Revenue growth | Gross margin |
|---|---|---|---|---|
| 2025 | -84.3% (= -31.6 / 37.5) | -184.6% (= -52.8 / ((29.3 + 27.9) / 2)) | +11.3% (37.5 against 33.7) | 41.2% (= 18.9 / 45.9) |

## 2. Costs

- Duties: about $3.8M of incremental duty cost in 2025 (S1).
- The supplier's brochure gives a 10x estimated cost saving for qualification (S1).
- Freight: $7.2M of incremental cost in 2025 (S1).
- Freight cost $7.2M in 2025 (S1).

## Sources

- **S1.** Larkspur Printing. 2026. *Annual Report 2025.* https://example.com/larkspur/annual-2025.html
"""
# claim, company, as the note writes it, as filed
CLAIMS = [("K-2025-rev", COMPANY, 37.5, 37.482), ("K-2025-op", COMPANY, -31.6, -31.571), ("K-2024-rev", COMPANY, 33.7, 33.738),
          ("K-2025-ni", COMPANY, -52.8, -52.83), ("K-2024-eq", COMPANY, 29.3, 29.346), ("K-2025-eq", COMPANY, 27.9, 27.861),
          ("K-2025-gp", COMPANY, 18.9, 18.91), ("K-2025-rev2", COMPANY, 45.9, 45.903),
          # Another company's 37.5 doesn't make the working's 37.5 ambiguous: the other inputs settle the company.
          ("O-2025-rev", OTHER, 37.5, 37.54)]


class Filed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        shutil.rmtree(root / "drafts")
        (root / "drafts").mkdir()
        (root / "research" / "02_ratios.md").write_text(NOTE, encoding="utf-8")
        self.ws = workspace.Workspace(root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)
        sourcedb.record_sources(self.ws, self.con)
        self.claims(CLAIMS)

    def claims(self, rows):
        self.con.executemany("INSERT INTO xbrl_claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             [(claim, "02_ratios.md", claim, cik, "Revenues", "2025-01-01", "2025-12-31", expected, 1e6, 0.051,
                               "match", found, "Revenues", "10-K", "2026-03-01", "") for claim, cik, expected, found in rows])
        self.con.commit()

    def refiled(self):
        return {found.stated: found for found in filed.refile(self.ws, self.con)}

    def draft(self, text):
        (self.ws.root / "drafts" / "01_draft.md").write_text(text, encoding="utf-8")
        return [(r.verdict, r.item, r.detail) for r in judge.judge(self.ws, self.con) if r.check == "numbers"
                and r.verdict != judge.PASS]

    # ------------------------------------------------------------ the notes' workings

    def test_a_working_from_rounded_inputs_is_worked_again_from_the_facts_as_filed(self):
        found = self.refiled()
        self.assertEqual(sorted(found), ["+11.3%", "-184.6%", "-84.3%"])
        self.assertEqual(found["-84.3%"].gives, "-84.2298%")
        self.assertEqual(found["-84.3%"].filed, "-84.3% (= -31.571 / 37.482)")
        self.assertEqual(found["+11.3%"].gives, "11.0973%")
        self.assertEqual(found["-84.3%"].where, "02_ratios.md:9")
        self.assertEqual(found["-84.3%"].claims, ("K-2025-op", "K-2025-rev"))

    def test_the_two_of_an_average_is_a_constant_not_a_figure(self):
        self.assertEqual(self.refiled()["-184.6%"].filed, "-184.6% (= -52.83 / ((29.346 + 27.861) / 2))")

    def test_a_working_the_facts_as_filed_still_give_is_not_listed(self):
        self.assertNotIn("41.2%", self.refiled())  # 18.91 / 45.903 is 41.196%, which is 41.2%.

    def test_an_input_one_company_files_two_ways_leaves_the_working_unread(self):
        self.claims([("K-2023-x", COMPANY, 37.5, 37.52)])
        found = self.refiled()
        self.assertNotIn("-84.3%", found)
        self.assertNotIn("+11.3%", found)
        self.assertIn("-184.6%", found)  # Its inputs aren't the doubled one.

    def test_inputs_no_one_company_gives_together_leave_the_working_unread(self):
        # The margin's loss is now a third company's: none gives both its inputs.
        self.con.execute("UPDATE xbrl_claims SET cik = 7777777 WHERE claim_id = 'K-2025-op'")
        self.con.commit()
        self.assertNotIn("-84.3%", self.refiled())

    def test_with_no_claims_matched_nothing_is_read(self):
        self.con.execute("UPDATE xbrl_claims SET status = 'MISMATCH'")
        self.con.commit()
        self.assertEqual(filed.refile(self.ws, self.con), [])

    def test_claims_lists_them_as_warnings_and_writes_them_down(self):
        (self.ws.root / "checks" / "xbrl_claims.csv").write_text(
            "claim_id,note_file,description,cik,concepts,period_start,period_end,expected,scale,tolerance\n", encoding="utf-8")
        # `claims` reloads its table from the file, so the claims go back in afterwards through its own reading.
        original = sourcedb.check_claims
        self.addCleanup(setattr, sourcedb, "check_claims", original)
        sourcedb.check_claims = lambda ws, con: {"match": len(CLAIMS)}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.cmd_claims(self.ws, self.con, argparse.Namespace())
        self.assertEqual(code, 0)  # Warnings only.
        self.assertIn("3 worked-out figures in the notes that the facts as filed don't give", out.getvalue())
        self.assertIn("02_ratios.md:9  -84.3% (= -31.6 / 37.5)  as filed: -84.3% (= -31.571 / 37.482) gives -84.2298%",
                      out.getvalue())
        with (self.ws.data / filed.REPORT).open(encoding="utf-8", newline="") as written:
            rows = list(csv.DictReader(written))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["claims"], "K-2025-op K-2025-rev")

    # ------------------------------------------------------------ a draft that copies one

    def test_a_draft_figure_the_notes_work_from_rounded_inputs_is_warned_of(self):
        [(verdict, item, detail)] = [f for f in self.draft("Larkspur's operating margin was -84.3% in 2025.\n")
                                     if "facts as filed" in f[2]]
        self.assertEqual((verdict, item), (judge.WARN, "84.3%"))  # The judge names a figure as the draft writes its digits.
        self.assertIn("from the SEC's facts as filed, -84.3% (= -31.571 / 37.482) gives -84.2298%", detail)

    def test_the_same_figure_about_something_else_is_not_warned_of(self):
        # The working is about Larkspur: a sentence that names only the measure, for another company, isn't its copy.
        found = self.draft("Ostrava's operating margin was -84.3% in 2025.\n")
        self.assertFalse([f for f in found if "facts as filed" in f[2]])
        # "COMPUTED" in the working's heading says how its figures came about, not what they're about.
        found = self.draft("Ostrava's operating margin, computed from its accounts, was -84.3% in 2025.\n")
        self.assertFalse([f for f in found if "facts as filed" in f[2]])

    def test_the_figure_with_another_sign_is_not_warned_of(self):
        # The working gives growth of +11.3%; a return of -11.3% is another figure that happens to share its digits.
        found = self.draft("Larkspur's revenue growth was -11.3% in 2025.\n")
        self.assertFalse([f for f in found if "facts as filed" in f[2]])
        found = self.draft("Larkspur's revenue growth was +11.3% in 2025.\n")
        self.assertTrue([f for f in found if "facts as filed" in f[2]])

    def test_a_line_that_states_it_from_a_source_vouches_for_it(self):
        (self.ws.root / "research" / "02_ratios.md").write_text(
            NOTE.replace("## Sources", "## 3. As the company gives it\n\n- Larkspur gives its operating margin as -84.3% (S1).\n\n"
                         "## Sources"), encoding="utf-8")
        found = self.draft("Larkspur's operating margin was -84.3% in 2025.\n")
        self.assertFalse([f for f in found if "facts as filed" in f[2]])

    def test_a_figure_in_a_table_whose_row_names_nothing_is_bound_by_its_caption_and_header(self):
        table = "\n\n| Year | Operating margin |\n|---|---|\n| 2025 | -84.3% |\n"
        [(verdict, item, detail)] = [f for f in self.draft("**Larkspur Printing, 2024 and 2025**" + table)
                                     if "facts as filed" in f[2]]
        self.assertEqual(verdict, judge.WARN)
        self.assertIn("02_ratios.md:9", detail)
        # The same table captioned for another company is about that company.
        self.assertFalse([f for f in self.draft("**Ostrava Labs, 2024 and 2025**" + table) if "facts as filed" in f[2]])

    def test_a_figure_for_another_year_is_not_the_workings_copy(self):
        # The working is on the 2025 row. A row for 2024, or a table captioned 2024, gives that year's figure.
        for draft in ("**Larkspur Printing, 2024 and 2025**\n\n| Year | Operating margin |\n|---|---|\n| 2024 | -84.3% |\n",
                      "**Cross-section, 2024**\n\n| Company | Operating margin |\n|---|---|\n| Larkspur Printing | -84.3% |\n"):
            with self.subTest(draft):
                self.assertFalse([f for f in self.draft(draft) if "facts as filed" in f[2]])
        found = self.draft("**Cross-section, 2025**\n\n| Company | Operating margin |\n|---|---|\n| Larkspur Printing | -84.3% |\n")
        self.assertTrue([f for f in found if "facts as filed" in f[2]])

    # ------------------------------------------------------------ qualifiers dropped

    def test_an_amount_the_notes_give_only_as_a_change_stated_as_a_level_is_warned_of(self):
        [(verdict, item, detail)] = [f for f in self.draft("Duties cost about $3.8M in 2025.\n") if "change" in f[2]]
        self.assertEqual((verdict, item), (judge.WARN, "$3.8M"))
        self.assertIn("the notes give it only as a change, at 02_ratios.md:13 ('incremental')", detail)

    def test_the_same_amount_said_as_a_change_passes(self):
        self.assertFalse([f for f in self.draft("Duties added about $3.8M of cost in 2025.\n") if "change" in f[2]])

    def test_an_amount_one_line_gives_plainly_passes(self):
        self.assertFalse([f for f in self.draft("Freight cost $7.2M in 2025.\n") if "change" in f[2]])

    def test_an_estimate_stated_as_fact_is_warned_of(self):
        [(verdict, item, detail)] = [f for f in self.draft("Shared data cut the qualification cost tenfold.\n")
                                     if "estimate" in f[2]]
        self.assertEqual((verdict, item), (judge.WARN, "tenfold"))
        self.assertIn("someone's estimate or claim, at 02_ratios.md:14 ('estimated')", detail)

    def test_an_estimate_said_to_be_one_or_given_a_source_passes(self):
        for sentence in ("Shared data cut the qualification cost tenfold, by the vendor's estimate.",
                         "Shared data cut the qualification cost tenfold (Larkspur Printing 2026).",
                         "Shared data cut the qualification cost tenfold, the vendor says."):
            with self.subTest(sentence):
                self.assertFalse([f for f in self.draft(sentence + "\n") if "estimate" in f[2]])


MORE = """# More workings

Fictional, for the tests.

## 1. Larkspur Printing (COMPUTED)

| Year | Net margin |
|---|---|
| 2024 | -11.9% (= -4.0 / 33.6) |

## 2. The makers added together (COMPUTED)

| Year | Makers | Revenue | Operating income | Operating margin |
|---|---|---|---|---|
| 2012 | LARK, OSTR | 21.5 + 35.4 = 56.9 | 1.7 + 6.1 = 7.8 | 13.7% (= 7.8 / 56.9) |
| All years | LARK, OSTR | 21.5 + 35.4 = 56.9 | 1.7 + 6.1 = 7.8 | n/m |

## 3. Each company's own total (COMPUTED)

| Company and years | Result | Arithmetic |
|---|---|---|
| Larkspur Printing, net income, 2021 to 2023, US$ millions | 4.5 | 1.2 + 1.5 + 1.8 |

## 4. Cash over three years (COMPUTED)

- Three years of cash from operations: 45.3 (= 15.1 * 3).
- Cash at the end, plus three years of cash, less spending: 211.0 (= 210.7 + 45.3 - 45.0).
- Less the cash kept in hand: 115.6 (= 211.0 - 95.4).
- Spending less a grant: 30.1 (= 45.0 - 14.9).
"""
# claim, company, year, as the note writes it, as filed
DATED = [("M-2024-ni", COMPANY, 2024, -4.0, -3.96), ("M-2019-op", COMPANY, 2019, 4.0, 4.04),
         ("M-2024-rev", COMPANY, 2024, 33.6, 33.62),
         # A sum's inputs are figures in millions to the thousand, as filed, or the sum's own tolerance takes them in.
         ("M-2012-rev-L", COMPANY, 2012, 21.5, 21.462), ("M-2012-rev-O", OTHER, 2012, 35.4, 35.441),
         ("M-2015-x-T", 7777777, 2015, 21.5, 21.52), ("M-2012-op-L", COMPANY, 2012, 1.7, 1.658),
         ("M-2012-op-O", OTHER, 2012, 6.1, 6.081),
         # Claims of the sums' sizes, which the margin must not be read from: it takes the sums on its line.
         ("M-2012-d1", COMPANY, 2012, 7.8, 7.83), ("M-2012-d2", COMPANY, 2012, 56.9, 56.95),
         ("M-2021-ni", COMPANY, 2021, 1.2, 1.241), ("M-2022-ni", COMPANY, 2022, 1.5, 1.462),
         ("M-2025-y", COMPANY, 2025, 1.5, 1.53), ("M-2023-ni", COMPANY, 2023, 1.8, 1.863),
         ("M-2025-cfo", COMPANY, 2025, 15.1, 15.144), ("M-2025-grant", COMPANY, 2025, 14.9, 14.84)]


class Settled(unittest.TestCase):
    """Workings whose inputs only the row's year, the line's other workings or an earlier working settle."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        (root / "research" / "03_more.md").write_text(MORE, encoding="utf-8")
        self.ws = workspace.Workspace(root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)
        sourcedb.record_sources(self.ws, self.con)
        self.con.executemany("INSERT INTO xbrl_claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             [(claim, "03_more.md", claim, cik, "Revenues", f"{year}-01-01", f"{year}-12-31", expected,
                               1e6, 0.051, "match", found, "Revenues", "10-K", "2026-03-01", "")
                              for claim, cik, year, expected, found in DATED])
        self.con.commit()
        self.found = {(found.line, found.stated): found for found in filed.refile(self.ws, self.con)}

    def test_the_year_a_row_names_settles_which_claim_an_input_is(self):
        # 4.0 is the 2024 net loss and 2019's operating income; the 2024 row takes the first.
        found = self.found[(9, "-11.9%")]
        self.assertEqual(found.filed, "-11.9% (= -3.96 / 33.62)")
        self.assertEqual(found.claims, ("M-2024-ni", "M-2024-rev"))

    def test_a_sum_on_a_year_row_adds_the_companies_figures_each_settled_by_the_year(self):
        self.assertEqual(self.found[(15, "7.8")].filed, "1.658 + 6.081 = 7.8")
        self.assertNotIn((15, "56.9"), self.found)  # 21.462 + 35.441 is 56.9 as written.
        # On a row that names no year, nothing settles whose 21.5 it is.
        self.assertFalse([key for key in self.found if key[0] == 16])

    def test_a_ratio_of_the_sums_on_its_line_takes_what_they_come_to_as_filed(self):
        found = self.found[(15, "13.7%")]
        self.assertEqual(found.filed, "13.7% (= 7.739 / 56.903)")
        self.assertEqual(found.gives, "13.6003%")
        self.assertEqual(found.via, ())  # Its own line's workings.

    def test_a_total_over_a_span_of_years_takes_its_figures_a_year_each(self):
        found = self.found[(22, "4.5")]
        self.assertEqual(found.filed, "1.241 + 1.462 + 1.863 = 4.5")
        self.assertEqual(found.gives, "4.566")

    def test_a_draft_that_copies_a_total_in_millions_is_warned_of(self):
        shutil.rmtree(self.ws.root / "drafts")
        (self.ws.root / "drafts").mkdir()
        (self.ws.root / "drafts" / "01_draft.md").write_text(
            "Larkspur Printing's net income over 2021 to 2023 came to $4.5M.\n", encoding="utf-8")
        [detail] = [r.detail for r in judge.judge(self.ws, self.con)
                    if r.check == "numbers" and r.verdict == judge.WARN and "facts as filed" in r.detail]
        self.assertIn("1.241 + 1.462 + 1.863 = 4.5 gives 4.566", detail)

    def test_a_working_that_takes_an_earlier_one_carries_its_rounding(self):
        self.assertEqual(self.found[(26, "45.3")].gives, "45.432")
        later = self.found[(27, "211.0")]
        self.assertEqual(later.filed, "211.0 (= 210.7 + 45.432 - 45.0)")  # The figures no claim gives stay as written.
        self.assertEqual(later.via, ("03_more.md:26",))
        self.assertEqual(self.found[(28, "115.6")].via, ("03_more.md:27",))

    def test_a_figure_no_claim_gives_still_leaves_a_working_unread_unless_it_takes_an_earlier_one(self):
        self.assertNotIn((29, "30.1"), self.found)  # 45.0 - 14.84 is 30.16, but nothing settles the 45.0.


if __name__ == "__main__":
    unittest.main()
