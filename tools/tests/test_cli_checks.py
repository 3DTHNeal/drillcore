"""The research checks are reachable from the command line, each with the exit status its module promises."""
import unittest

from support import run_cli


class ResearchChecks(unittest.TestCase):
    def test_citations_fail_while_the_example_sources_are_unfetched(self):
        out, _, code = run_cli("citations")
        self.assertIn("hasn't been fetched", out)
        self.assertEqual(code, 1)

    def test_quotes_pass_when_the_notes_quote_nothing(self):
        out, _, code = run_cli("quotes")
        self.assertIn("no quotations", out)
        self.assertEqual(code, 0)

    def test_the_example_arithmetic_reproduces(self):
        out, _, code = run_cli("arithmetic")
        self.assertIn("1 ok, 0 wrong", out)
        self.assertEqual(code, 0)

    def test_overlap_takes_a_shortest_run_and_refuses_a_bad_one(self):
        out, _, code = run_cli("overlap", "--min-words", "8")
        self.assertIn("8 or more words", out)
        self.assertEqual(code, 0)
        _, _, code = run_cli("overlap", "--min-words", "1")
        self.assertEqual(code, 1)

    def test_the_assay_catches_the_example_drafts_worked_out_figure(self):
        out, _, code = run_cli("assay")
        self.assertIn("'sixty'", out)
        self.assertIn("01_northbridge.md: FAIL", out)
        self.assertEqual(code, 1)

    def test_the_assay_refuses_a_draft_that_isnt_there(self):
        _, _, code = run_cli("assay", "no-such-draft.md")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
