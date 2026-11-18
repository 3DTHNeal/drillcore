"""Tests for the overlap check: whether a draft shares a long passage with a fetched source. Every draft and source
here is made up, and lives in a throwaway copy of the example workspace."""
import argparse
import contextlib
import csv
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from support import CODE_ROOT

from drillcore import overlap, sourcedb, workspace

REPORT = "https://example.com/northbridge/annual-2025.html"
COPY = "https://example.com/northbridge/annual-2025-copy.html"
LETTER = "https://example.com/northbridge/letter.html"
# Twenty-one words of a made-up annual report.
SOURCE = ("In the year under review the company reshaped its assembly lines around smaller collaborative arms that "
          "share the floor with people.")
UNRELATED = "The weather in the harbour town stayed mild for most of the winter, and the ferries ran to time."


class Overlap(unittest.TestCase):
    """A workspace of its own for each test, with its database open and a drafts folder to write into."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        shutil.rmtree(root / "drafts", ignore_errors=True)
        (root / "drafts").mkdir()
        self.ws = workspace.Workspace(root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)

    def source(self, url, text):
        self.con.execute("INSERT INTO documents VALUES (?,?,?,?,?)", (url, None, text, len(text), "text"))
        self.con.commit()

    def draft(self, text, name="01_draft.md", folder="drafts"):
        (self.ws.root / folder).mkdir(exist_ok=True)
        (self.ws.root / folder / name).write_text(text, encoding="utf-8")

    def settings(self, extra):
        with self.ws.config_path.open("a", encoding="utf-8") as out:
            out.write("\n" + extra + "\n")


class Finding(Overlap):
    def test_a_copied_passage_is_found_with_its_line_length_and_source(self):
        self.source(LETTER, UNRELATED)
        self.source(REPORT, "Annual report. " + SOURCE + " Revenue fell.")
        self.draft("# Draft\n\nMy own opening.\nAs the report says, in the year under review the company reshaped its assembly\n"
                   "lines around smaller collaborative arms that share the floor with people. My own close.\n")
        [passage] = overlap.check(self.ws, self.con)
        self.assertEqual((passage.draft, passage.line, passage.words, passage.url), ("01_draft.md", 4, 21, REPORT))
        self.assertTrue(passage.excerpt.startswith("in the year under review the company reshaped its assembly lines"))
        self.assertLessEqual(len(passage.excerpt), overlap.EXCERPT_CHARS + 4)

    def test_case_punctuation_and_spacing_are_ignored(self):
        self.source(REPORT, SOURCE)
        self.draft("IN THE YEAR -- under review, the Company reshaped its\n\nassembly   lines; around smaller collaborative arms.\n")
        [passage] = overlap.check(self.ws, self.con)
        self.assertEqual(passage.words, 15)

    def test_a_run_shorter_than_the_threshold_is_not_reported(self):
        self.source(REPORT, SOURCE)
        self.draft("We saw that the company reshaped its assembly lines around smaller collaborative arms, then stopped.\n")
        self.assertEqual(overlap.check(self.ws, self.con), [])  # Ten words shared.
        self.assertEqual([p.words for p in overlap.check(self.ws, self.con, min_words=10)], [10])

    def test_the_threshold_and_folder_come_from_the_settings(self):
        self.source(REPORT, SOURCE)
        self.settings('[drafts]\nfolder = "writing"\nmin_words = 8')
        self.draft("The company reshaped its assembly lines around smaller arms.\n", folder="writing")
        self.draft("The company reshaped its assembly lines around smaller arms.\n", name="ignored.md")
        [passage] = overlap.check(self.ws, self.con)
        self.assertEqual((passage.draft, passage.words), ("01_draft.md", 8))
        self.assertEqual(overlap.min_words_for(self.ws, 15), 15)  # The command wins over the setting.

    def test_a_threshold_that_isnt_a_whole_number_of_at_least_two_is_refused(self):
        for bad in (0, 1, "12", 2.5):
            with self.assertRaises(ValueError):
                overlap.min_words_for(self.ws, bad)

    def test_a_large_source_is_read_quickly(self):
        filler = " ".join(f"word{i % 997} filler{i % 13}" for i in range(200_000))
        self.source(REPORT, filler + " " + SOURCE + " " + filler)
        self.draft("Opening. " + SOURCE + "\n")
        [passage] = overlap.check(self.ws, self.con)
        self.assertEqual(passage.words, 21)

    def test_the_reference_list_and_the_records_are_left_out(self):
        self.source(REPORT, SOURCE)
        self.settings('[drafts]\nrecords = ["Appendix B"]')
        self.draft("# Draft\n\nMy own words.\n\n## References\n\n- Northbridge. 2025. " + SOURCE + "\n\n## Appendix B. Prompts\n\n"
                   + SOURCE + "\n\n## Appendix C. Notes\n\n" + SOURCE + "\n")
        [passage] = overlap.check(self.ws, self.con)
        self.assertEqual(passage.line, 15)

    def test_records_that_cant_be_used_are_refused(self):
        self.settings('[drafts]\nrecords = "Appendix B"')
        with self.assertRaises(ValueError):
            overlap.records(self.ws)


class Merging(Overlap):
    def test_overlapping_runs_make_one_passage_reported_once_even_from_two_sources(self):
        self.source(REPORT, SOURCE)
        self.source(COPY, "A reprint. " + SOURCE)
        self.draft("Mine. " + SOURCE + " Mine again.\n")
        [passage] = overlap.check(self.ws, self.con)
        # Both share all of it, so the URL first in order is named.
        self.assertEqual((passage.words, passage.url), (21, COPY))

    def test_the_source_sharing_most_of_a_passage_is_named(self):
        self.source(REPORT, "the year under review the company reshaped its assembly lines around smaller collaborative")
        self.source(COPY, SOURCE)
        self.draft(SOURCE + "\n")
        [passage] = overlap.check(self.ws, self.con)
        self.assertEqual((passage.words, passage.url), (21, COPY))

    def test_two_separate_copies_are_two_passages(self):
        second = "Its suppliers in the northern valley were asked to deliver parts twice a week instead of once a month."
        self.source(REPORT, SOURCE + " Something else entirely here. " + second)
        self.draft(f"{SOURCE}\n\nMy own words between them, not taken from anywhere at all.\n\n{second}\n", name="02_two.md")
        self.draft("Nothing borrowed here.\n", name="01_clean.md")
        passages = overlap.check(self.ws, self.con)
        self.assertEqual([(p.draft, p.line, p.words) for p in passages], [("02_two.md", 1, 21), ("02_two.md", 5, 19)])


class Quoting(Overlap):
    def test_quoted_text_is_left_out(self):
        self.source(REPORT, SOURCE)
        self.draft(f'The report says "{SOURCE[:-1]}"\nand then moves on.\n'
                   f"Its letter adds “{SOURCE}”, in so many words, and ‘{SOURCE}’ again.\n")
        self.assertEqual(overlap.check(self.ws, self.con), [])

    def test_a_quotation_wrapped_over_lines_is_left_out_but_an_unclosed_mark_hides_nothing_past_a_blank_line(self):
        self.source(REPORT, SOURCE)
        wrapped = SOURCE.replace(" company ", "\ncompany ")
        self.draft(f'As quoted: "{wrapped}" (Annual report, p. 3).\n\nA stray " mark here.\n\n{SOURCE}\n')
        [passage] = overlap.check(self.ws, self.con)
        self.assertEqual((passage.line, passage.words), (6, 21))

    def test_a_blockquote_is_left_out(self):
        self.source(REPORT, SOURCE)
        self.draft(f"Before.\n\n> {SOURCE}\n> (Annual report)\n\nAfter.\n")
        self.assertEqual(overlap.check(self.ws, self.con), [])

    def test_words_either_side_of_a_quotation_are_not_joined(self):
        self.source(REPORT, SOURCE)
        words = SOURCE.split()
        self.draft(" ".join(words[:8]) + ' "an aside" ' + " ".join(words[8:]) + "\n")
        self.assertEqual([p.words for p in overlap.check(self.ws, self.con)], [13])  # Only the thirteen after it.


class Output(Overlap):
    def test_the_passages_are_written_to_a_csv(self):
        self.source(REPORT, SOURCE)
        self.draft("Mine. " + SOURCE + "\n")
        overlap.check(self.ws, self.con)
        with (self.ws.data / "overlap.csv").open(encoding="utf-8", newline="") as written:
            rows = list(csv.reader(written))
        self.assertEqual(rows[0], ["draft", "line_no", "words", "url", "excerpt"])
        self.assertEqual(rows[1][:4], ["01_draft.md", "1", "21", REPORT])

    def run_command(self, **given):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = overlap.run(self.ws, self.con, argparse.Namespace(**given))
        return out.getvalue(), err.getvalue(), code

    def test_the_command_exits_1_when_a_passage_is_shared(self):
        self.source(REPORT, SOURCE)
        self.draft("Mine. " + SOURCE + "\n")
        out, _, code = self.run_command()
        self.assertEqual(code, 1)
        self.assertIn(f"01_draft.md:1  21 words  {REPORT}", out)
        self.assertIn("1 passage(s) of 12 or more words", out)

    def test_the_command_takes_its_threshold_and_exits_0_when_nothing_is_shared(self):
        self.source(REPORT, SOURCE)
        self.draft("Mine. " + SOURCE + "\n")
        out, _, code = self.run_command(min_words=22)
        self.assertEqual(code, 0)
        self.assertIn("0 passage(s) of 22 or more words", out)
        _, err, code = self.run_command(min_words=1)
        self.assertEqual(code, 1)
        self.assertIn("at least 2", err)

    def test_the_command_says_when_there_are_no_drafts(self):
        shutil.rmtree(self.ws.root / "drafts")
        _, err, code = self.run_command()
        self.assertEqual(code, 0)
        self.assertIn("No drafts to check", err)


class Example(unittest.TestCase):
    def test_the_example_draft_is_read_and_shares_nothing_with_the_example_notes(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp).resolve() / "ws"
            shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
            ws = workspace.Workspace(root, "test")
            with contextlib.closing(sourcedb.connect(ws)) as con:
                self.assertEqual([path.name for path in overlap.draft_files(ws)], ["01_northbridge.md"])
                notes = (root / "research" / "01_northbridge.md").read_text(encoding="utf-8")
                con.execute("INSERT INTO documents VALUES (?,?,?,?,?)", (REPORT, None, notes, len(notes), "text"))
                self.assertEqual(overlap.check(ws, con, min_words=8), [])


if __name__ == "__main__":
    unittest.main()
