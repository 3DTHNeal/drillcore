"""Tests for the citations check, on a copy of the example workspace. Nothing here reaches the network: each fetch is
answered by a stand-in."""
import argparse
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from support import CODE_ROOT

from drillcore import citations, sourcedb, workspace

ANNUAL = "https://example.com/northbridge/annual-2025.html"
ORDERS = "https://example.com/northbridge/orders.html"
PAGES = {ANNUAL: (200, "text/html", b"<p>Revenue 551,102</p>"), ORDERS: (200, "text/plain", b"Order book 95.4 million")}


class Citations(unittest.TestCase):
    """A copy of the example workspace for each test, with its database open."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        self.ws = workspace.Workspace(root, "test")
        self.note = root / "research" / "01_northbridge.md"
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)

    def fetch(self, **answers):
        """Fetch every cited source, each URL answering with the (status, type, body) given for it."""
        pages = {**PAGES, **answers}

        def get(url):
            status, kind, body = pages.get(url, (404, "text/html", b""))
            return status, kind, url, body, None if status == 200 else f"HTTP {status}"
        sourcedb.record_sources(self.ws, self.con)
        sourcedb.fetch(self.ws, self.con, get=get, say=lambda _: None)

    def edit(self, old, new):
        text = self.note.read_text(encoding="utf-8")
        self.assertIn(old, text)
        self.note.write_text(text.replace(old, new), encoding="utf-8")

    def write(self, name, text):
        (self.ws.root / "research" / name).write_text(text, encoding="utf-8")

    def borrow(self, borrower, lender):
        with self.ws.config_path.open("a", encoding="utf-8") as settings:
            settings.write(f'\n[notes.borrows]\n"{borrower}" = "{lender}"\n')

    def found(self):
        return [(f.note, f.line, f.severity, f.kind) for f in citations.check(self.ws, self.con)]

    def test_the_example_resolves_once_its_sources_are_fetched(self):
        self.fetch()
        self.assertEqual(self.found(), [])

    def test_a_source_never_fetched_is_an_error(self):
        findings = citations.check(self.ws, self.con)
        self.assertEqual([(f.line, f.kind) for f in findings], [(26, "not_fetched"), (27, "not_fetched")])
        self.assertIn(ANNUAL, findings[0].message)
        self.assertIn("drillcore fetch", findings[0].message)

    def test_a_refused_source_is_an_error_until_its_text_is_gathered_by_hand(self):
        self.fetch(**{ORDERS: (403, "text/html", b"")})
        findings = citations.check(self.ws, self.con)
        self.assertEqual([(f.line, f.severity, f.kind) for f in findings], [(27, "error", "fetch_failed")])
        self.assertIn("HTTP 403", findings[0].message)
        (self.ws.data / "raw" / "browser_capture.jsonl").write_text(
            json.dumps({"url": ORDERS, "text": "Order book 95.4 million", "method": "by hand"}) + "\n", encoding="utf-8")
        sourcedb.import_text(self.ws, self.con)
        self.assertEqual(self.found(), [])

    def test_a_page_fetched_with_no_text_is_a_warning(self):
        self.fetch(**{ORDERS: (200, "image/png", b"\x89PNG")})
        self.assertEqual(self.found(), [("01_northbridge.md", 27, "warning", "no_text")])

    def test_a_key_cited_without_an_entry_is_an_error_but_a_quarter_is_not_a_key(self):
        self.edit("- A figure no source holds", "- In Q3 2025 and per R18, a figure no source holds")
        self.edit("## 2. Worked out", "## 2. Worked out (S9)\n\nAlso S9 and S1.")
        self.fetch()
        findings = citations.check(self.ws, self.con)
        self.assertEqual([(f.line, f.kind) for f in findings], [(18, "no_entry"), (20, "no_entry")])
        self.assertIn("S9 is cited", findings[0].message)

    def test_an_entry_without_a_url_is_an_error_and_one_nothing_cites_a_warning(self):
        self.edit("https://example.com/northbridge/orders.html", "(address to follow)")
        self.edit("(S2)", "(see the order book)")
        self.note.write_text(self.note.read_text(encoding="utf-8") + "\n## Gaps and cautions\n\n- S1 only covers 2025.\n",
                             encoding="utf-8")
        self.fetch()
        self.assertEqual(self.found(), [("01_northbridge.md", 27, "error", "no_url"), ("01_northbridge.md", 27, "warning", "unused")])
        self.edit("## 1. Results (S1)", "## 1. Results")
        self.edit("(S1)", "(the annual report)")
        self.assertIn(("01_northbridge.md", 26, "warning", "unused"), self.found())

    def test_a_note_uses_another_notes_keys_only_when_the_workspace_says_it_borrows(self):
        self.write("02_more.md", "## More\n\n- Staff were 1,757 (S1).\n")
        self.edit("## 1. Results (S1)", "## 1. Results")
        self.edit("(S1)", "(the annual report)")
        self.fetch()
        findings = citations.check(self.ws, self.con)
        self.assertEqual([(f.note, f.line, f.kind) for f in findings],
                         [("01_northbridge.md", 26, "unused"), ("02_more.md", 3, "no_entry")])
        self.assertIn("01_northbridge.md defines it", findings[1].message)
        self.borrow("02_more.md", "01_northbridge.md")
        self.assertEqual(self.found(), [])

    def test_a_borrowed_note_that_isnt_there_is_an_error(self):
        self.write("02_more.md", "## More\n\n- Staff were 1,757 (S1).\n")
        self.borrow("02_more.md", "00_gone.md")
        self.fetch()
        self.assertEqual(self.found(), [("02_more.md", 0, "error", "no_lender"), ("02_more.md", 3, "error", "no_entry")])

    def test_run_prints_each_finding_and_fails_only_on_an_error(self):
        args = argparse.Namespace()
        self.fetch(**{ORDERS: (200, "image/png", b"\x89PNG")})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(citations.run(self.ws, self.con, args), 0)
        self.assertIn("01_northbridge.md:27: warning:", out.getvalue())
        self.assertIn("0 error(s), 1 warning(s) in 1 note\n", out.getvalue())
        self.edit("(S2)", "(S3)")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(citations.run(self.ws, self.con, args), 1)

    def test_a_line_can_cite_another_notes_list_by_its_number(self):
        self.edit("(S2)", "(see the order book)")
        self.write("02_more.md", "## More\n\n- The order book (file 01 sources S2) and staff (file 01 sources S7, S1).\n"
                                 "- Something else (file 09 sources S1).\n")
        self.fetch()
        findings = citations.check(self.ws, self.con)
        self.assertEqual([(f.note, f.line, f.kind, f.key) for f in findings],
                         [("02_more.md", 3, "no_entry", "S7"), ("02_more.md", 4, "no_entry", "S1")])  # 01's S2 is cited.
        self.assertIn("cited from 01_northbridge.md", findings[0].message)
        self.assertIn("cited from file 09", findings[1].message)
        cited = [(c.line, c.key, c.status, c.detail) for c in citations.examine(self.ws, self.con)[0] if c.note == "02_more.md"]
        self.assertEqual(cited, [(3, "S2", "resolves", "1 address(es) in 01_northbridge.md"),
                                 (3, "S7", "no_entry", "01_northbridge.md gives no address for it"),
                                 (3, "S1", "resolves", "1 address(es) in 01_northbridge.md"),
                                 (4, "S1", "no_entry", "that file gives no address for it")])

    def test_a_word_is_a_key_only_when_its_letters_are_those_of_a_key_the_note_can_use(self):
        self.write("02_parts.md", "## Parts (P1)\n\n- The F370 printer and part P2 (P1), in Q3.\n\n"
                                  "## Sources\n\n- **P1.** Parts list. https://example.com/parts.html\n")
        self.write("03_fleet.md", "## Fleet (F1)\n\n- Ten units (F1).\n\n## Sources\n\n- **F1.** Fleet. https://example.com/fleet.html\n")
        self.write("04_bare.md", "## Bare\n\n- Ten units (F1).\n")  # With no list of its own, any note's letters count.
        self.fetch()
        missing = [(f.note, f.line, f.key) for f in citations.check(self.ws, self.con) if f.kind == "no_entry"]
        self.assertEqual(missing, [("02_parts.md", 3, "P2"), ("04_bare.md", 3, "F1")])


if __name__ == "__main__":
    unittest.main()
