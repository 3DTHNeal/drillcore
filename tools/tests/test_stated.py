"""Tests for the figures the notes state, by label and period, as a formula names them. Every note here is fictional."""
import unittest

import support  # noqa: F401

from drillcore import formula, stated

NOTE = """# Fictional

| Item | 2025 | 2024 |
|---|---|---|
| Revenue, $M | 551.1 | 572.5 |
| **Total revenue** | 600.0 | 610.0 |
| Gross profit | 227.0 | (12.0) |
| Staff | 1,757 | - |

| Item | Value |
|---|---|
| Order book Q3 2025 | 95.4 |
| Sales growth | 4.1% |

## Sources

| Item | 2025 |
|---|---|
| Revenue | 999.9 |
"""


def find(text: str, note: str = "a.md", notes: tuple[tuple[str, str], ...] = (("a.md", NOTE),), **where) -> str:
    return stated.Book.of(notes).find(stated.reference(text), note, **where).figure.text


class Reading(unittest.TestCase):
    def test_a_figure_is_found_by_its_rows_label_and_its_columns_period(self):
        self.assertEqual(find("Revenue 2025"), "551.1")
        self.assertEqual(find("revenues, FY2024"), "572.5")  # A plural, a case and a fiscal year it doesn't contradict.
        self.assertEqual(find("Sales 2024"), "572.5")         # Sales and revenue are the same line.
        self.assertEqual(find("Gross profit 2024"), "-12.0")
        self.assertEqual(find("Staff 2025"), "1,757")

    def test_total_counts(self):
        self.assertEqual(find("Total revenue 2025"), "600.0")
        self.assertEqual(find("Revenue 2025"), "551.1")

    def test_a_period_in_the_label(self):
        self.assertEqual(find("Order book, Q3 2025"), "95.4")
        self.assertEqual(find("Backlog"), "95.4")
        self.assertEqual(find("Sales growth"), "4.1%")

    def test_the_sources_section_states_nothing(self):
        entries = list(stated.read("a.md", NOTE))
        self.assertNotIn("999.9", [entry.figure.text for entry in entries])


class NotFound(unittest.TestCase):
    def test_what_cant_be_found_says_what_it_found(self):
        with self.assertRaises(stated.Ambiguous) as caught:
            find("Revenue")
        self.assertIn("551.1 at a.md:5 (2025), 572.5 at a.md:5 (2024); name the period", str(caught.exception))
        with self.assertRaises(stated.NotStated) as missing:
            find("Revenue 2023")
        self.assertIn("for 2023", str(missing.exception))
        with self.assertRaises(stated.NotStated):
            find("Net profit 2025")
        for bad in ("2025", "Revenue 2024 2025"):
            with self.subTest(bad=bad), self.assertRaises(formula.Undefined):
                stated.reference(bad)

    def test_the_note_its_in_comes_first(self):
        other = "| Item | 2025 |\n|---|---|\n| Revenue | 500.0 |\n"
        notes = (("a.md", NOTE), ("b.md", other))
        self.assertEqual(find("Revenue 2025", "a.md", notes), "551.1")
        self.assertEqual(find("Revenue 2025", "b.md", notes), "500.0")
        self.assertEqual(find("Gross profit 2025", "b.md", notes), "227.0")  # b.md states none, so a.md's is used.
        with self.assertRaises(stated.Ambiguous):
            find("Revenue 2025", "c.md", notes)


class InAPeriod(unittest.TestCase):
    def test_a_rule_gives_the_period_and_prior_counts_a_year_back(self):
        period = stated.reference("Revenue 2025").period
        self.assertEqual(find("Revenue", period=period, in_period=True), "551.1")
        self.assertEqual(find("Revenue, prior", period=period, in_period=True), "572.5")
        self.assertEqual(find("Revenue a year earlier", period=period, in_period=True), "572.5")
        with self.assertRaises(stated.NotStated):
            find("Revenue", period=None, in_period=True)  # No period means a figure stated without one.
        with self.assertRaises(formula.Undefined):
            find("Revenue, prior")


if __name__ == "__main__":
    unittest.main()
