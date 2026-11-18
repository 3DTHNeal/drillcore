"""Tests for notes on economic data: periods named by month or written year first, the words that tell apart two series
sharing a noun (real or nominal, a change on the year or the month, a forecast or an outturn), changes in a rate written
in points, a CSV download read as a table, and a short percentage held to the words of its row. Every figure and
source here is made up."""
import shutil
import tempfile
import unittest
from pathlib import Path

from support import CODE_ROOT

from assay import numbers as assay_numbers
from drillcore import arithmetic, measures, research, sourcedb, workspace
from drillcore.measures import Context, Period


def one(row: str) -> arithmetic.Result:
    """The single result on a worked-out bullet."""
    results = arithmetic.check_text("n.md", f"COMPUTED:\n\n{row}\n")
    assert len(results) == 1, results
    return results[0]


class Months(unittest.TestCase):
    def test_a_month_or_a_quarter_as_economic_data_names_it(self):
        cases = {
            "October 2026": Period(1, "M10", "", 2026), "Oct. 2026": Period(1, "M10", "", 2026),
            "Oct-26": Period(1, "M10", "", 2026), "Oct '26": Period(1, "M10", "", 2026),
            "SEPTEMBER 2026": Period(1, "M9", "", 2026), "2026M10": Period(1, "M10", "", 2026),
            "2026-M3": Period(1, "M3", "", 2026), "2026Q3": Period(3, "Q3", "", 2026),
            "2026:Q3": Period(3, "Q3", "", 2026), "2026 Q3": Period(3, "Q3", "", 2026),
        }
        for written, period in cases.items():
            with self.subTest(written):
                self.assertEqual(measures.periods(written), [period])
        self.assertEqual(Period(1, "M10", "", 2026).shown(), "Oct 2026")

    def test_a_date_isnt_a_month(self):
        # Each is read as its year alone, as before months were read.
        for written in ("28 October 2026", "October 28, 2026", "the 28th October 2026", "Sep 26, 2026", "2026-10-01",
                        "quarter ended September 2026", "the twelve months to October 2026", "rates may 2026"):
            with self.subTest(written):
                self.assertNotIn(1, [period.months for period in measures.periods(written)])

    def test_a_month_differs_from_another_month_and_from_the_quarter_it_ends(self):
        october, september = measures.periods("October 2026")[0], measures.periods("September 2026")[0]
        self.assertEqual(measures.differ(october, september), "part of the year")
        self.assertEqual(measures.differ(september, measures.periods("Q3 2026")[0]), "length")
        self.assertEqual(measures.differ(october, measures.periods("2026")[0]), "")


class Series(unittest.TestCase):
    def clash(self, note: str, source: str) -> str:
        return measures.qualifier_clash(measures.label_words(note), measures.label_words(source))

    def test_the_words_that_tell_two_series_apart(self):
        self.assertEqual(self.clash("Real GDP growth", "Nominal GDP growth"), "nominal where the note says real")
        self.assertTrue(self.clash("Core CPI inflation", "Headline CPI inflation"))
        self.assertTrue(self.clash("CPI, year-over-year", "CPI, month over month"))
        self.assertTrue(self.clash("CPI, y/y", "CPI, m/m"))
        self.assertTrue(self.clash("Payrolls, seasonally adjusted", "Payrolls, not seasonally adjusted"))
        self.assertTrue(self.clash("GDP growth forecast", "GDP growth outturn"))

    def test_words_that_only_look_like_them_dont_clash(self):
        self.assertFalse(self.clash("Real estate revenue", "Nominal revenue"))
        self.assertFalse(self.clash("GDP growth, y/y", "Real GDP growth from a year earlier"))
        # Seasonally adjusted isn't the adjusted of an adjusted profit.
        self.assertFalse(self.clash("Seasonally adjusted payrolls", "Unadjusted payrolls"))

    def test_a_forecast_in_the_source_is_another_line_unless_the_note_says_it_is_one(self):
        source = Context("We project real GDP growth of 2.1 percent", (Period(None, "", "", 2027),))
        stated = Context("Real GDP grew 2.1%", (Period(None, "", "", 2027),))
        outcome, why = measures.compare(stated, source)
        self.assertEqual(outcome, measures.OTHER_LABEL)
        self.assertIn("a forecast in the source", why)
        for said in ("Real GDP is projected to grow 2.1%", "The fund expects real GDP growth of 2.1%",
                     "Real GDP growth will be 2.1%", "Real GDP growth forecast: 2.1%"):
            with self.subTest(said):
                self.assertEqual(measures.compare(Context(said, stated.periods), source)[0], measures.AGREES)

    def test_a_result_described_against_expectations_isnt_a_forecast(self):
        source = Context("Real GDP grew 2.1 percent, faster than expected", (Period(None, "", "", 2026),))
        self.assertEqual(measures.compare(Context("Real GDP grew 2.1%", source.periods), source)[0], measures.AGREES)


class Points(unittest.TestCase):
    def test_a_change_in_a_rate_in_percentage_points(self):
        self.assertEqual((one("- Inflation fell: -0.4pp (2.7 against 3.1).").status), "ok")
        self.assertEqual(one("- Inflation fell: -0.4pp (from 3.1% to 2.7%).").status, "ok")
        self.assertEqual(one("- Inflation fell: 0.4pp (2.7 against 3.1).").status, "ok")  # Its size; the words say which way.
        wrong = one("- Inflation fell: -0.5pp (2.7 against 3.1).")
        self.assertEqual((wrong.status, wrong.why), ("wrong", "gives -0.4pp"))

    def test_a_change_in_basis_points(self):
        self.assertEqual(one("- The policy rate rose: +25bp (from 4.25% to 4.50%).").status, "ok")
        self.assertEqual(one("- The policy rate rose: +25bps (4.50 against 4.25).").status, "ok")
        self.assertEqual(one("- The policy rate rose: +50bp (4.50 against 4.25).").status, "wrong")

    def test_a_sum_in_points_with_or_without_percent_signs(self):
        self.assertEqual(one("- Gap: 0.4pp (= 3.1 - 2.7).").status, "ok")
        self.assertEqual(one("- Gap: 0.4pp (= 3.1% - 2.7%).").status, "ok")
        self.assertEqual(one("- Gap: 40bp (= 3.1 - 2.7).").status, "ok")

    def test_a_relative_change_in_a_rate_is_still_a_percentage(self):
        self.assertEqual(one("- Inflation fell: -12.9% (2.7 against 3.1).").status, "ok")
        self.assertEqual(one("- Share: 5pp (2 of 40).").status, "unparsed")


class CsvText(unittest.TestCase):
    def test_a_csv_file_is_read_as_a_table(self):
        text = sourcedb.csv_text('Country,2025,2026\r\nUnited States,2.8,2.0\r\nRevenue,"551,102",572\r\nA|B,1,2\r\n\r\n')
        self.assertEqual(text, "Country | 2025 | 2026\nUnited States | 2.8 | 2.0\nRevenue | 551,102 | 572\nA/B | 1 | 2")

    def test_semicolons_and_tabs_separate_cells_too(self):
        self.assertEqual(sourcedb.csv_text("date;value\n2026-10-01;3.1\n"), "date | value\n2026-10-01 | 3.1")
        self.assertEqual(sourcedb.csv_text("date\tvalue\n2026-10-01\t3.1\n"), "date | value\n2026-10-01 | 3.1")

    def test_figures_side_by_side_are_never_read_as_one(self):
        read = lambda text: [q.value for q in assay_numbers.quantities(text, research.POLICY)]
        self.assertEqual(read("Revenue,551,572"), ["551572"])  # As plain text, the two cells are one number.
        self.assertEqual(read(sourcedb.csv_text("Revenue,551,572\n")), ["551", "572"])

    def test_a_cell_is_read_with_its_rows_label_and_its_columns_year(self):
        text = sourcedb.csv_text("Real GDP growth,2025,2026,2027\nUnited States,2.8,2.0,2.1\n")
        at = text.index("2.0")
        self.assertEqual(measures.source_context(text, at, at + 3), Context("United States", (Period(None, "", "", 2026),), True))


RELEASE = "https://stats.example.org/release/employment-2026-10.html"
OUTLOOK = "https://fund.example.org/outlook/2026-10/table.csv"
PROJECTION = "https://bank.example.org/projections-2026-10.html"
RESULTS = "https://example.com/northbridge/results.csv"
FILLER = "Nothing else of note was published in this part of the release. " * 6
PAGES = {
    RELEASE: ("text/html", f"<html><body><p>The unemployment rate rose to 4.4 percent in October 2026.</p><p>{FILLER}</p>"
                           "<p>Average hourly earnings rose by 3.8 percent over the year.</p></body></html>".encode()),
    OUTLOOK: ("text/csv; charset=utf-8", b"Real GDP growth,2025,2026,2027\r\nUnited States,2.8,2.0,2.1\r\nEuro area,0.9,1.2,1.4\r\n"),
    PROJECTION: ("text/html", b"<html><body><p>We project real GDP growth of 1.7 percent in 2027.</p></body></html>"),
    RESULTS: ("text/csv", b"Item,2025,2024\nRevenue,551,572\n"),
}
NOTE = f"""# Outlook

Made up, for the tests.

## 1. Labour market (S1)

- The unemployment rate was 4.4% in October 2026 (S1).
- The unemployment rate was 4.4% in September 2026 (S1).
- The unemployment rate was 3.8% (S1).

## 2. Growth (S2)

| Real GDP growth, % | 2026 | 2027 |
|---|---|---|
| Euro area | 1.2 | 1.4 |

- Euro area real GDP growth in 2027 was 1.2% (S2).
- Real GDP grew 1.7% in 2027 (S3).
- Real GDP is projected to grow 1.7% in 2027 (S3).

## 3. Results (S4)

| Item | 2025 | 2024 |
|---|---|---|
| Revenue, $M | 551 | 572 |

## Sources

- **S1.** Statistics office. 2026. "Employment, October 2026." {RELEASE}
- **S2.** The fund. 2026. "Outlook table." {OUTLOOK}
- **S3.** The bank. 2026. "Projections." {PROJECTION}
- **S4.** Northbridge Robotics. 2026. "Results." {RESULTS}
"""


class Outlook(unittest.TestCase):
    """A note on economic data, its sources answered by stand-ins: a release, a CSV download and a projection."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        (root / "research" / "01_northbridge.md").unlink()
        (root / "research" / "02_outlook.md").write_text(NOTE, encoding="utf-8")
        self.ws = workspace.Workspace(root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)
        sourcedb.record_sources(self.ws, self.con)
        sourcedb.fetch(self.ws, self.con, get=lambda url: (200, *PAGES[url][:1], url, PAGES[url][1], None), say=lambda _: None)

    def figures(self) -> dict[tuple[str, str], str]:
        sourcedb.check_figures(self.ws, self.con)
        return {(row[:60], number): status for row, number, status in
                self.con.execute("SELECT row_text, number_text, status FROM note_figures")}

    def test_a_csv_download_is_kept_and_read_as_a_table(self):
        how = dict(self.con.execute("SELECT url, extractor FROM documents"))
        self.assertEqual((how[OUTLOOK], how[RESULTS]), ("csv", "csv"))
        stored = self.con.execute("SELECT raw_path FROM fetches WHERE url=?", (OUTLOOK,)).fetchone()[0]
        self.assertTrue(stored.endswith(".csv"))

    def test_a_copy_kept_as_plain_text_is_read_as_a_table_when_read_again(self):
        # As a version before this one kept it: under .txt, read as plain text.
        raw = self.con.execute("SELECT raw_path FROM fetches WHERE url=?", (RESULTS,)).fetchone()[0]
        old = raw[:-len(".csv")] + ".txt"
        (self.ws.root / raw).rename(self.ws.root / old)
        self.con.execute("UPDATE fetches SET raw_path=? WHERE url=?", (old, RESULTS))
        self.con.execute("UPDATE documents SET text=?, extractor='text' WHERE url=?", ("Item,2025,2024\nRevenue,551,572", RESULTS))
        self.con.commit()
        sourcedb.reread(self.ws, self.con)
        text, how = self.con.execute("SELECT text, extractor FROM documents WHERE url=?", (RESULTS,)).fetchone()
        self.assertEqual((text, how), ("Item | 2025 | 2024\nRevenue | 551 | 572", "csv"))

    def test_figures_in_cells_side_by_side_are_each_found(self):
        results = [r for r in research.run(self.ws, self.con) if r.check == "numbers" and r.row_text.startswith("| Revenue")]
        self.assertEqual([r.status for r in results], ["supported"])

    def test_a_figure_is_held_to_its_month_and_its_year(self):
        found = self.figures()
        self.assertEqual(found["- The unemployment rate was 4.4% in October 2026 (S1).", "4.4"], "found")
        self.assertEqual(found["- The unemployment rate was 4.4% in September 2026 (S1).", "4.4"], "beside_another_period")
        self.assertEqual(found["| Euro area | 1.2 | 1.4 |", "1.2"], "found")
        self.assertEqual(found["- Euro area real GDP growth in 2027 was 1.2% (S2).", "1.2"], "beside_another_period")

    def test_a_forecast_stated_as_a_result_is_said_so(self):
        found = self.figures()
        self.assertEqual(found["- Real GDP grew 1.7% in 2027 (S3).", "1.7"], "beside_another_label")
        self.assertEqual(found["- Real GDP is projected to grow 1.7% in 2027 (S3).", "1.7"], "found")

    def test_a_short_percentage_is_held_to_the_words_of_its_row(self):
        warned = {r.row_text for r in research.run(self.ws, self.con) if r.status == "not_near_label"}
        # 3.8 percent is the release's figure for earnings, nowhere near the word "unemployment".
        self.assertEqual(warned, {"- The unemployment rate was 3.8% (S1)."})


if __name__ == "__main__":
    unittest.main()
