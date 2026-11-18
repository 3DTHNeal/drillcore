"""Tests for the quotations check. Everything quoted is fictional, and nothing reaches the network: each fetch is
answered by a stand-in."""
import argparse
import contextlib
import csv
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from support import CODE_ROOT

from drillcore import quotes, sourcedb, workspace

LETTER = "https://example.com/northbridge/letter.html"
SERVICES = "https://example.com/northbridge/services.txt"
LETTER_PAGE = b"""<html><head><title>Letter from the chair</title></head><body>
<p>Demand for our warehouse robots stayed firm through the year, and the order book grew 11% in every region.</p>
<p>Margins narrowed because of higher component costs &mdash; chiefly motors and sensors.</p>
<p>We didn&#8217;t cut prices to win orders.</p></body></html>"""
SERVICES_TEXT = b"""Services review 2025
Our service busi-
ness grew faster than hardware sales in 2025. Hardware sales were flat
in a slow market."""

NOTE = """# Quotes

Everything here is fictional.

## 1. Demand (S1)

- The chair: “Demand for our warehouse robots stayed firm through the year.”
- Misquoted: "Demand for our warehouse robots stayed strong through the year."
- Wrong case: "DEMAND for our warehouse robots stayed firm"
- A number changed: "the order book grew 12% in every region"
- Cut short: "Demand for our warehouse robots ... the order book grew 11% in every region."
- Curly apostrophe against a straight one: "We didn't cut prices to win orders"
- A short quotation counts too: "stayed firm", and code isn't one: `"one two three four five"`.

```
"Text in a code block is not a quotation either"
```

## 2. Services (S2)

The services review put it plainly:

> Our service business grew faster than hardware sales in 2025.

> “Margins narrowed because of higher component costs – chiefly motors and sensors.”

— the chair, S1

The review also said "Hardware sales were flat
in a slow market" and left it there.

| Who | Said |
|---|---|
| Press (S3) | "Shipments to new customers doubled in the second half" |

## 3. Unsourced

- Someone said "we will double the fleet by next spring" at a fair.

## Sources

- **S1.** Northbridge Robotics. 2026. "Letter to shareholders from the chair." https://example.com/northbridge/letter.html
- **S2.** Northbridge Robotics. 2026. Services review. https://example.com/northbridge/services.txt
- **S3.** Trade press. 2026. "Northbridge ships to new customers." https://example.com/press/shipments.html
"""


class Normalising(unittest.TestCase):
    def test_only_what_doesnt_change_the_meaning_is_evened_out(self):
        self.assertEqual(quotes.normalise("“It’s  firm” —\nsaid\xa0the chair – again…"),
                         "\"It's firm\"-said the chair-again...")
        self.assertEqual(quotes.normalise("eﬃcient pro\xadfit"), "efficient profit")

    def test_case_wording_and_numbers_still_count(self):
        source = quotes.source_forms("Demand stayed firm; the order book grew 11% in every region.")
        # The first letter's case may change to fit the sentence a quotation sits in. No other letter's may.
        for quoted, there in (("Demand stayed firm.", True), ("demand stayed firm", True), ("Demand Stayed Firm", False),
                              ("dEMAND stayed firm", False), ("Demand stayed strong", False),
                              ("the order book grew 12% in every region", False), ("the order book grew 11% in every region,", True)):
            with self.subTest(quoted):
                self.assertEqual(any(quotes.appears_in(quotes.pieces(quoted), form) for form in source), there)

    def test_a_word_hyphenated_across_a_line_is_found_either_way(self):
        forms = quotes.source_forms("an eco-\nnomic result, and a well-\nknown one")
        for quoted, there in (("an economic result", True), ("a well-known one", True), ("a wellknown one", True),
                              ("an eco-nomic result", True), ("an economic result", True)):
            with self.subTest(quoted):
                self.assertEqual(any(quotes.appears_in(quotes.pieces(quoted), form) for form in forms), there)
        self.assertEqual(quotes.source_forms("no breaks here"), ("no breaks here",))
        self.assertEqual(quotes.source_forms("a 2024-\n25 figure"), ("a 2024-25 figure",))  # Only words are joined.

    def test_an_ellipsis_leaves_words_out_but_the_rest_must_come_in_order(self):
        text = quotes.normalise("Demand stayed firm through the year, and the order book grew.")
        self.assertEqual(quotes.pieces("Demand stayed firm [...] the order book grew..."), ["Demand stayed firm", "the order book grew"])
        self.assertTrue(quotes.appears_in(quotes.pieces("Demand stayed firm … the order book grew"), text))
        self.assertFalse(quotes.appears_in(quotes.pieces("the order book grew ... Demand stayed firm"), text))
        self.assertFalse(quotes.appears_in(quotes.pieces("..."), text))
        self.assertFalse(quotes.appears_in(quotes.pieces("two ... one"), "one two"))

    def test_words_put_in_square_brackets_are_a_gap_too(self):
        self.assertEqual(quotes.pieces("one ... two [sic] three."), ["one", "two", "three"])
        self.assertTrue(quotes.appears_in(quotes.pieces("Demand [for robots] stayed firm"), "Demand for our robots stayed firm"))

    def test_text_is_read_as_the_assay_reads_it(self):
        self.assertEqual(quotes.readable("café ﬁnal *firm* １２"), "cafe final firm 12")
        self.assertEqual(quotes.readable("de<!-- a note -->mand"), "demand")
        self.assertEqual(quotes.source_forms("Crème brûlée"), ("Creme brulee",))

    def test_a_miss_that_only_capitals_explain_says_so(self):
        forms = quotes.source_forms("ORDER BOOK REVIEW")
        self.assertTrue(quotes.case_only(quotes.pieces("Order Book Review"), forms))
        self.assertFalse(quotes.case_only(quotes.pieces("Order Book Summary"), forms))


class Finding(unittest.TestCase):
    def setUp(self):
        self.found = quotes.find_quotes("02_quotes.md", NOTE, {"S1", "S2", "S3"})
        self.by_text = {quote.text: quote for quote in self.found}

    def test_quotations_of_any_length_and_blockquotes_are_found(self):
        self.assertEqual(len(self.found), 12)
        self.assertIn("stayed firm", self.by_text)
        texts = " | ".join(self.by_text)
        for left_out in ("one two three", "code block", "Letter to shareholders", "Northbridge ships"):
            self.assertNotIn(left_out, texts)
        self.assertEqual(self.by_text["Our service business grew faster than hardware sales in 2025."].form, "blockquote")

    def test_each_quotation_takes_the_keys_its_row_or_section_names(self):
        def cited(start):
            quote = next(quote for text, quote in self.by_text.items() if text.startswith(start))
            return quote.keys, quote.key_basis
        self.assertEqual(cited("Demand for our warehouse robots stayed firm through"), (("S1",), "section"))
        self.assertEqual(cited("Our service business"), (("S2",), "section"))
        self.assertEqual(cited("Margins narrowed"), (("S1",), "attribution"))
        self.assertEqual(cited("Shipments to new"), (("S3",), "row"))
        self.assertEqual(cited("we will double"), ((), "section"))

    def test_a_blockquote_drops_its_citation_and_takes_its_lead_in(self):
        found = quotes.find_quotes("n.md", "## A\n\nThe chair wrote (S2):\n\n> Demand stayed firm.\n> It grew. (S1)\n\n> Margins narrowed.\n", {"S1", "S2"})
        self.assertEqual([(q.text, q.keys, q.key_basis, q.line_no) for q in found],
                         [("Demand stayed firm. It grew.",("S1",), "row", 5), ("Margins narrowed.", ("S2",), "section", 8)])
        lead_in = quotes.find_quotes("n.md", "The chair wrote (S2):\n> Demand stayed firm.\n", {"S2"})
        self.assertEqual((lead_in[0].keys, lead_in[0].key_basis), (("S2",), "lead-in"))

    def test_a_quotation_wrapped_across_lines_is_read_whole_from_the_line_it_starts(self):
        quote = self.by_text["Hardware sales were flat in a slow market"]
        self.assertEqual(NOTE.splitlines()[quote.line_no - 1], 'The review also said "Hardware sales were flat')

    def test_code_isnt_read(self):
        found = quotes.find_quotes("n.md", 'a "b" c “d” `"code"` e', set())
        self.assertEqual([quote.text for quote in found], ["b", "d"])

    def test_an_unknown_key_isnt_a_key(self):
        found = quotes.find_quotes("n.md", '- "Shipments to new customers doubled" (S9)\n', {"S1"})
        self.assertEqual(found[0].keys, ())


class Checking(unittest.TestCase):
    """A workspace of its own for each test, holding a note full of quotations, with its database open."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        (root / "research" / "02_quotes.md").write_text(NOTE, encoding="utf-8")
        self.ws = workspace.Workspace(root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)
        pages = {LETTER: (200, "text/html", LETTER_PAGE), SERVICES: (200, "text/plain; charset=utf-8", SERVICES_TEXT)}

        def get(url: str) -> sourcedb.Response:
            status, kind, body = pages.get(url, (404, "text/html", b""))
            return status, kind, url, body, None if status == 200 else f"HTTP {status}"
        sourcedb.record_sources(self.ws, self.con)
        sourcedb.fetch(self.ws, self.con, get=get, say=lambda _: None)

    def status_of(self, results, start):
        return next(quote for quote in results if quote.text.startswith(start)).status

    def test_each_quotation_is_looked_for_in_the_source_it_cites(self):
        results = quotes.check(self.ws, self.con)
        expected = {"Demand for our warehouse robots stayed firm through": "exact",
                    "Demand for our warehouse robots stayed strong": "not_found",
                    "DEMAND for our": "not_found",
                    "stayed firm": "exact",
                    "the order book grew 12%": "not_found",
                    "Demand for our warehouse robots ...": "exact",
                    "We didn't cut prices": "exact",
                    "Our service business": "exact",
                    "Margins narrowed": "exact",
                    "Hardware sales were flat": "exact",
                    "Shipments to new customers": "no_text",
                    "we will double": "no_source"}
        for start, status in expected.items():
            with self.subTest(start):
                self.assertEqual(self.status_of(results, start), status)
        stored = dict(self.con.execute("SELECT status, COUNT(*) FROM note_quotes GROUP BY 1"))
        self.assertEqual(stored, {"exact": 7, "not_found": 3, "no_text": 1, "no_source": 1})
        matched = self.con.execute("SELECT matched_url FROM note_quotes WHERE quote LIKE 'Our service%'").fetchone()
        self.assertEqual(matched, (SERVICES,))

    def test_a_miss_says_where_the_quotation_parts_from_the_source(self):
        results = quotes.check(self.ws, self.con)
        miss = next(quote for quote in results if "stayed strong" in quote.text)
        self.assertEqual(miss.detail, f'the first 6 of 10 words are in {LETTER}; it parts at "strong"')
        capitals = next(quote for quote in results if quote.text.startswith("DEMAND")).detail
        self.assertEqual(capitals, "no run of its opening words is in the cited text; it matches if capital letters are ignored")

    def test_the_misses_are_written_out(self):
        quotes.check(self.ws, self.con)
        with (self.ws.data / quotes.REPORT).open(encoding="utf-8", newline="") as report:
            rows = list(csv.DictReader(report))
        self.assertEqual(sorted(row["status"] for row in rows), ["no_source", "no_text", "not_found", "not_found", "not_found"])
        self.assertTrue(all(row["note_file"] == "02_quotes.md" and row["line_no"].isdigit() for row in rows))

    def test_checking_again_replaces_what_was_stored(self):
        quotes.check(self.ws, self.con)
        quotes.check(self.ws, self.con)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM note_quotes").fetchone(), (12,))

    def test_the_command_fails_only_when_a_quotation_isnt_in_its_source(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = quotes.run(self.ws, self.con, argparse.Namespace())
        self.assertEqual(code, 1)
        printed = out.getvalue()
        self.assertIn("02_quotes.md", printed)
        self.assertIn("not_found", printed)
        self.assertIn("parts at \"strong\"", printed)
        self.assertIn(quotes.REPORT, printed)
        note = self.ws.root / "research" / "02_quotes.md"
        kept = [line for line in NOTE.splitlines() if not line.startswith(("- Misquoted", "- Wrong case", "- A number"))]
        note.write_text("\n".join(kept) + "\n", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(quotes.run(self.ws, self.con, argparse.Namespace()), 0)


BRIEF = """# Against the brief

## Claims (S1)

- The brief says "orders doubled in every region" (S1).
- The letter says "Demand for our warehouse robots stayed firm" (S1).

The brief puts it this way:

> Margins widened on cheaper motors.

The letter puts it another way:

> Margins grew on cheaper motors.

## Sources

- **S1.** Letter. {letter}
"""
NOT_SOURCES = '\n[check.quotations]\nnot_sources = ["brief"]\n'


class NotSources(unittest.TestCase):
    """A workspace that names a document its notes quote but don't cite as a source."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        (root / "research" / "02_brief.md").write_text(BRIEF.format(letter=LETTER), encoding="utf-8")
        self.ws = workspace.Workspace(root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)
        sourcedb.record_sources(self.ws, self.con)
        sourcedb.fetch(self.ws, self.con, get=lambda url: (200, "text/html", url, LETTER_PAGE, None) if url == LETTER
                       else (404, "text/html", url, b"", "HTTP 404"), say=lambda _: None)

    def statuses(self):
        return [(quote.text, quote.status) for quote in quotes.check(self.ws, self.con) if quote.note_file == "02_brief.md"]

    def test_a_quotation_of_a_document_that_isnt_a_source_isnt_looked_for(self):
        self.assertEqual([status for _, status in self.statuses()], ["not_found", "exact", "not_found", "not_found"])
        with self.ws.config_path.open("a", encoding="utf-8") as settings:
            settings.write(NOT_SOURCES)
        self.assertEqual(self.statuses(), [("orders doubled in every region", "not_a_source"),
                                           ("Demand for our warehouse robots stayed firm", "exact"),
                                           ("Margins widened on cheaper motors.", "not_a_source"),  # Its lead-in names the brief.
                                           ("Margins grew on cheaper motors.", "not_found")])
        with (self.ws.data / quotes.REPORT).open(encoding="utf-8", newline="") as report:
            self.assertEqual([row["quote"] for row in csv.DictReader(report)], ["Margins grew on cheaper motors."])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(quotes.run(self.ws, self.con, argparse.Namespace()), 1)


MEETING = "https://example.com/northbridge/meeting.html"
FILLER = "The meeting then turned to the accounts, the auditors and the dates of next year's meetings. " * 5
MEETING_PAGE = f"""<html><body><p>Jane Doe, the chief executive, opened the meeting.</p><p>{FILLER}</p>
<p>&ldquo;Orders held up well,&rdquo; the chairman noted.</p><p>{FILLER}</p>
<p>&ldquo;Costs will fall next year,&rdquo; the chief financial officer said.</p></body></html>""".encode()
SPOKEN = """# Who said it

## Meeting (S1)

- The chief executive said "Costs will fall next year" (S1).
- The CFO said "Costs will fall next year" (S1).
- Jane Doe said "Orders held up well" (S1).
- "Orders held up well," said the chair (S1).
- The founder said "Orders held up well" (S1).
- He said "Orders held up well" (S1).

## Sources

- **S1.** Meeting. {meeting}
"""


class Speakers(unittest.TestCase):
    """A quotation whose note says who said it is held to that person being named near it in the source."""

    def test_the_speaker_is_read_from_the_words_around_a_quotation(self):
        self.assertEqual(quotes.speaker_of("The chief executive said  ."), "chief executive")
        self.assertEqual(quotes.speaker_of("The chair:"), "chair")
        self.assertEqual(quotes.speaker_of("Jane Doe said"), "Jane Doe")
        self.assertEqual(quotes.speaker_of(", said Jane Doe, on the call"), "Jane Doe")
        self.assertEqual(quotes.speaker_of("according to Mary-Ann Smith"), "Mary-Ann Smith")
        self.assertEqual(quotes.speaker_of("He said"), "")
        self.assertEqual(quotes.speaker_of("The release says"), "")
        self.assertEqual(quotes.speaker_of("The release calls it"), "")
        self.assertEqual(quotes.speaker_of("a chief executive without a word of saying"), "")
        self.assertEqual(quotes.speaker_of("According to Jane Doe,"), "Jane Doe")
        self.assertEqual(quotes.speaker_of("Analysts said"), "")

    def test_with_two_speakers_in_a_sentence_each_quotation_takes_the_nearest(self):
        note = '# N\n\n- Doe said "we sold more", and the founder added "we hired more" (S1).\n'
        found = {quote.text: quote.speaker for quote in quotes.find_quotes("n.md", note, {"S1"})}
        self.assertEqual(found, {"we sold more": "Doe", "we hired more": "founder"})

    def test_a_quotation_far_from_its_speaker_is_a_warning(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        (root / "research" / "02_spoken.md").write_text(SPOKEN.format(meeting=MEETING), encoding="utf-8")
        ws = workspace.Workspace(root, "test")
        con = sourcedb.connect(ws)
        self.addCleanup(con.close)
        sourcedb.record_sources(ws, con)
        sourcedb.fetch(ws, con, get=lambda url: (200, "text/html", url, MEETING_PAGE, None) if url == MEETING
                       else (404, "text/html", url, b"", "HTTP 404"), say=lambda _: None)
        results = [quote for quote in quotes.check(ws, con) if quote.note_file == "02_spoken.md"]
        self.assertEqual([(quote.speaker, quote.status) for quote in results], [
            ("chief executive", "not_near_speaker"),  # The chief executive is named, but at the top of the page.
            ("CFO", "exact"),                         # The chief financial officer said it, written another way.
            ("Jane Doe", "not_near_speaker"),
            ("chair", "exact"),                       # The chairman, the same role.
            ("founder", "exact"),                     # The page names no founder, so it can't say.
            ("", "exact")])
        self.assertIn("'chief executive' said them", results[0].detail)
        self.assertEqual(results[0].matched_url, MEETING)
        with (ws.data / quotes.REPORT).open(encoding="utf-8", newline="") as report:
            self.assertEqual([row["status"] for row in csv.DictReader(report)], ["not_near_speaker", "not_near_speaker"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(quotes.run(ws, con, argparse.Namespace()), 0)  # A warning: the words are right.
        self.assertIn("not_near_speaker", out.getvalue())


if __name__ == "__main__":
    unittest.main()
