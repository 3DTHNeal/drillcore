"""Tests for `drillcore newer`: a cited filing overtaken by a later one, and a fact a later filing restates. The SEC's
tables are filled in directly; nothing reaches the network."""
import shutil
import tempfile
import unittest
from pathlib import Path

from support import CODE_ROOT, run_cli

from drillcore import filings, sourcedb, workspace

FOLDER = "https://www.sec.gov/Archives/edgar/data/9999999/000000000025000004/"
NOTE = f"""# Quarter

## Results (S3)

| Item | Q1 2025 |
|---|---|
| Revenue, $M | 131.2 |
| Staff | 1,790 |

## Sources

- **S3.** Northbridge Robotics. 2025. Form 10-Q. {FOLDER}q1.htm
"""
FILED = [  # cik, entity, accession, form, filing date, report date, document, description, items, url
    (9999999, "Northbridge", "0000000000-25-000004", "10-Q", "2025-05-08", "2025-03-31", "q1.htm", "", "", f"{FOLDER}q1.htm"),
    (9999999, "Northbridge", "0000000000-25-000006", "8-K", "2025-06-01", "", "", "", "", ""),
    (9999999, "Northbridge", "0000000000-25-000007", "10-Q", "2025-08-07", "2025-06-30", "q2.htm", "", "", ""),
    (9999999, "Northbridge", "0000000000-26-000001", "10-K", "2026-03-05", "2025-12-31", "annual.htm", "", "", ""),
]
FACTS = [  # cik, entity, taxonomy, concept, label, unit, start, end, value, fy, fp, form, filed, accession, frame
    (9999999, "N", "us-gaap", "Revenues", "", "USD", "2025-01-01", "2025-03-31", 131200000, 2025, "Q1", "10-Q", "2025-05-08", "0000000000-25-000004", ""),
    (9999999, "N", "us-gaap", "Revenues", "", "USD", "2025-01-01", "2025-03-31", 129800000, 2025, "Q1", "10-K", "2026-03-05", "0000000000-26-000001", ""),
    (9999999, "N", "us-gaap", "OtherIncome", "", "USD", "2025-01-01", "2025-03-31", 4400000, 2025, "Q1", "10-Q", "2025-05-08", "0000000000-25-000004", ""),
    (9999999, "N", "us-gaap", "OtherIncome", "", "USD", "2025-01-01", "2025-03-31", 4100000, 2025, "Q1", "10-K", "2026-03-05", "0000000000-26-000001", ""),
    (9999999, "N", "us-gaap", "Revenues", "", "USD", "2024-01-01", "2024-12-31", 572458000, 2024, "FY", "10-K", "2025-03-06", "0000000000-25-000001", ""),
    (9999999, "N", "us-gaap", "Revenues", "", "USD", "2024-01-01", "2024-12-31", 572500000, 2025, "FY", "10-K", "2026-03-05", "0000000000-26-000001", ""),
]


class Newer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        (root / "research" / "02_quarter.md").write_text(NOTE, encoding="utf-8")
        self.ws = workspace.Workspace(root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)
        sourcedb.record_sources(self.ws, self.con)
        self.con.executemany("INSERT INTO filings VALUES (?,?,?,?,?,?,?,?,?,?)", FILED)
        self.con.executemany("INSERT INTO xbrl_facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", FACTS)
        self.con.commit()

    def found(self, kind):
        return [n for n in filings.check(self.ws, self.con) if n.kind == kind]

    def test_a_cited_quarterly_report_with_a_later_periodic_filing_is_named(self):
        newer = self.found("newer_filing")
        self.assertEqual(len(newer), 1)
        self.assertEqual((newer[0].note, newer[0].key), ("02_quarter.md", "S3"))
        self.assertIn("the 10-Q filed 2025-08-07 (0000000000-25-000007), and 1 more after it", newer[0].detail)
        self.assertNotIn("8-K", newer[0].detail)  # A current report isn't a periodic one.

    def test_a_fact_the_note_writes_that_a_later_filing_restates_is_reported_with_both_values(self):
        restated = [n for n in self.found("restated") if n.note == "02_quarter.md"]
        self.assertEqual(len(restated), 1)  # Other income changed too, but the note doesn't write it.
        self.assertIn("Revenues for 2025-01-01 to 2025-03-31 (USD) is 131,200,000", restated[0].detail)
        self.assertIn("129,800,000 in the 10-K filed 2026-03-05 (0000000000-26-000001)", restated[0].detail)

    def test_a_claim_whose_period_a_later_filing_restates_is_reported(self):
        claims = [n for n in self.found("restated") if n.key == "NBR-2024-rev"]
        self.assertEqual(len(claims), 1)
        self.assertIn("572,458,000 in the 10-K filed 2025-03-06", claims[0].detail)

    def test_without_a_later_filing_there_is_nothing_to_say(self):
        self.con.execute("DELETE FROM filings WHERE filing_date > '2025-05-08'")
        self.assertEqual(self.found("newer_filing"), [])

    def test_the_command_only_ever_warns(self):
        out, err, code = run_cli("newer")
        self.assertEqual(code, 0)
        self.assertIn("No SEC filing lists are loaded", err)
        self.assertIn("0 newer filing warning(s)", out)


if __name__ == "__main__":
    unittest.main()
