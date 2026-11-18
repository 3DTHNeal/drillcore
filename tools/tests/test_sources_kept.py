"""Tests for what a workspace keeps of its sources: local files imported by hand, the inventory of every source, and
search that shows each hit in place with the notes that cite it. Nothing reaches the network."""
import csv
import shutil
import tempfile
import unittest
import unittest.mock as mock
from email.message import EmailMessage
from pathlib import Path

from support import CODE_ROOT, run_cli

from drillcore import citations, identity, inventory, sourcedb, workspace

ANNUAL = "https://example.com/northbridge/annual-2025.html"
ORDERS = "https://example.com/northbridge/orders.html"
ANNUAL_PAGE = b"<html><body><p>Revenue was 551,102 thousand. Research spending was $77.3 million.</p></body></html>"
DECK_ENTRY = "- **S7.** Northbridge Robotics. 2026. Investor deck, from the data room. file:deck.txt\n"


class Kept(unittest.TestCase):
    """A copy of the example for each test, with its database open and a folder outside it for local files."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        self.ws = workspace.Workspace(root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)
        self.outside = Path(self.tmp.name).resolve() / "dataroom"
        self.outside.mkdir()
        self.note = root / "research" / "01_northbridge.md"

    def add_to_note(self, body_line: str = "", entry: str = "") -> None:
        text = self.note.read_text(encoding="utf-8")
        if body_line:
            text = text.replace("## 2. Worked out", body_line + "\n\n## 2. Worked out")
        self.note.write_text(text + entry, encoding="utf-8")

    def local(self, name: str, body: bytes) -> Path:
        path = self.outside / name
        path.write_bytes(body)
        return path

    def fetch(self, pages=None):
        pages = {ANNUAL: (200, "text/html", ANNUAL_PAGE), ORDERS: (403, "text/html", b""), **(pages or {})}
        self.asked: list[str] = []

        def get(url):
            self.asked.append(url)
            status, kind, body = pages.get(url, (404, "text/html", b""))
            return status, kind, url, body, None if status == 200 else f"HTTP {status}"
        sourcedb.record_sources(self.ws, self.con)
        return sourcedb.fetch(self.ws, self.con, get=get, say=lambda _: None)

    def run_here(self, *argv):
        self.con.commit()
        with mock.patch.dict(workspace.os.environ, {identity.HOME_VARIABLE: str(self.ws.root)}), \
                mock.patch.object(sourcedb, "http_get", lambda url: (404, "", url, b"", "HTTP 404")):
            return run_cli(*argv)


class LocalFiles(Kept):
    def test_a_file_a_sources_entry_names_is_imported_under_that_address_and_read(self):
        self.add_to_note("- The deck puts the order book at $95.4M (S7).", DECK_ENTRY)
        done = sourcedb.import_file(self.ws, self.con, self.local("Deck v2.txt", b"Order book: 95.4 million."), "S7")
        self.assertEqual((done.address, done.notes, done.named, done.how), ("file:deck.txt", ("01_northbridge.md",), True, "text"))
        digest, raw, kind = self.con.execute("SELECT sha256, raw_path, content_type FROM fetches WHERE url='file:deck.txt'").fetchone()
        self.assertEqual((self.ws.root / raw).read_bytes(), b"Order book: 95.4 million.")
        self.assertTrue(raw.startswith(f"data/raw/{digest[:20]}"))
        self.assertEqual(kind, "local file (txt)")
        self.assertEqual(self.con.execute("SELECT text FROM documents WHERE url='file:deck.txt'").fetchone(), ("Order book: 95.4 million.",))
        name, original = self.con.execute("SELECT file_name, original_path FROM local_files").fetchone()
        self.assertEqual((name, Path(original).parent), ("Deck v2.txt", self.outside))

    def test_fetch_never_asks_the_network_for_a_file_and_says_to_import_it(self):
        self.add_to_note("- The deck (S7).", DECK_ENTRY)
        said: list[str] = []
        sourcedb.record_sources(self.ws, self.con)
        counts = sourcedb.fetch(self.ws, self.con, get=lambda url: (404, "", url, b"", "HTTP 404"), say=said.append)
        self.assertEqual(counts["local"], 1)
        self.assertTrue(any("import-file PATH --key S7" in line for line in said))
        sourcedb.import_file(self.ws, self.con, self.local("deck.txt", b"text"), "S7")
        counts = sourcedb.fetch(self.ws, self.con, get=lambda url: (404, "", url, b"", "HTTP 404"), say=said.append)
        self.assertNotIn("local", counts)

    def test_citations_ask_for_the_import_then_accept_the_file(self):
        self.add_to_note("- The deck (S7).", DECK_ENTRY)
        problems = [f for f in citations.check(self.ws, self.con) if f.key == "S7"]
        self.assertEqual([(f.kind, "import-file" in f.message) for f in problems], [("not_fetched", True)])
        sourcedb.import_file(self.ws, self.con, self.local("deck.txt", b"text"), "S7")
        self.assertEqual([f for f in citations.check(self.ws, self.con) if f.key == "S7"], [])

    def test_a_key_whose_entry_gives_no_address_takes_the_file_by_its_name(self):
        self.add_to_note("- The deck (S7).", "- **S7.** Investor deck, from the data room.\n")
        done = sourcedb.import_file(self.ws, self.con, self.local("investor deck.txt", b"95.4"), "S7")
        self.assertRegex(done.address, r"^file:investor_deck-[0-9a-f]{8}\.txt$")
        self.assertEqual((done.notes, done.named), (("01_northbridge.md",), False))
        self.assertEqual([f for f in citations.check(self.ws, self.con) if f.key == "S7"], [])
        self.assertEqual(sourcedb.keys_by_note(self.con, ["01_northbridge.md"], {})["01_northbridge.md"]["S7"], [done.address])

    def test_two_files_of_one_name_from_two_places_stay_two_sources(self):
        self.add_to_note("- Deck A (S7). Deck B (S8).", "- **S7.** Deck from room A.\n- **S8.** Deck from room B.\n")
        first = sourcedb.import_file(self.ws, self.con, self.local("deck.txt", b"Room A: 95.4"), "S7")
        second = sourcedb.import_file(self.ws, self.con, self.local("deck.txt", b"Room B: 67.5"), "S8")
        self.assertNotEqual(first.address, second.address)
        text = dict(self.con.execute("SELECT url, text FROM documents"))
        self.assertEqual((text[first.address], text[second.address]), ("Room A: 95.4", "Room B: 67.5"))

    def test_a_key_imported_again_stands_on_the_new_file_alone(self):
        self.add_to_note("- The deck (S7).", "- **S7.** Investor deck.\n")
        sourcedb.import_file(self.ws, self.con, self.local("deck.txt", b"old: 95.4"), "S7")
        newer = sourcedb.import_file(self.ws, self.con, self.local("deck_v2.txt", b"new: 67.5"), "S7")
        self.assertEqual(sourcedb.keys_by_note(self.con, ["01_northbridge.md"], {})["01_northbridge.md"]["S7"], [newer.address])

    def test_an_email_in_a_charset_python_doesnt_know_is_still_read(self):
        message = (b"From: ir@northbridge.example\r\nSubject: Update\r\nContent-Type: text/plain; charset=unknown-8bit\r\n\r\n"
                   b"The order book stood at $95.4 million.\r\n")
        self.add_to_note("- The email (S7).", "- **S7.** An email. file:update.eml\n")
        done = sourcedb.import_file(self.ws, self.con, self.local("update.eml", message), "S7")
        self.assertIn("$95.4 million", self.con.execute("SELECT text FROM documents WHERE url=?", (done.address,)).fetchone()[0])

    def test_a_file_address_inside_a_web_address_is_part_of_it(self):
        self.add_to_note("- A filing (S7).", "- **S7.** A filing. https://registry.example.gov/view?doc=file:annual-2025.pdf\n")
        sourcedb.record_sources(self.ws, self.con)
        urls = [url for (url,) in self.con.execute("SELECT url FROM sources WHERE source_key='S7'")]
        self.assertEqual(urls, ["https://registry.example.gov/view?doc=file:annual-2025.pdf"])

    def test_an_email_is_read_with_its_headers_and_plain_body(self):
        message = EmailMessage()
        message["From"] = "Investor Relations <ir@northbridge.example>"
        message["Subject"] = "Order book update"
        message["Date"] = "Tue, 3 Mar 2026 09:00:00 +0000"
        message.set_content("The order book stood at $95.4 million.")
        message.add_alternative("<p>The order book stood at <b>$95.4 million</b>.</p>", subtype="html")
        self.add_to_note("- The email (S7).", "- **S7.** An email from investor relations. file:update.eml\n")
        done = sourcedb.import_file(self.ws, self.con, self.local("update.eml", bytes(message)), "S7")
        title, text, how = self.con.execute("SELECT title, text, extractor FROM documents WHERE url=?", (done.address,)).fetchone()
        self.assertEqual((title, how), ("Order book update", "email"))
        self.assertIn("Subject: Order book update", text)
        self.assertIn("The order book stood at $95.4 million.", text)

    def test_what_cant_be_imported_says_why(self):
        with self.assertRaisesRegex(sourcedb.NotImported, "no file"):
            sourcedb.import_file(self.ws, self.con, self.outside / "missing.pdf", "S7")
        path = self.local("deck.txt", b"x")
        with self.assertRaisesRegex(sourcedb.NotImported, "no note called"):
            sourcedb.import_file(self.ws, self.con, path, "S7", note="99_none.md")
        (self.ws.root / "research" / "02_more.md").write_text("# More\n", encoding="utf-8")
        with self.assertRaisesRegex(sourcedb.NotImported, "--note"):
            sourcedb.import_file(self.ws, self.con, path, "S7")
        self.assertEqual(sourcedb.import_file(self.ws, self.con, path, "S7", note="02_more.md").notes, ("02_more.md",))

    def test_a_file_of_a_kind_nothing_reads_is_kept_without_text(self):
        self.add_to_note("", "- **S7.** A picture. file:chart.png\n")
        done = sourcedb.import_file(self.ws, self.con, self.local("chart.png", b"\x89PNG\r\n"), "S7")
        self.assertIsNone(done.text_chars)
        self.assertEqual(self.con.execute("SELECT bytes FROM local_files").fetchone(), (6,))

    def test_the_command_imports_and_reports(self):
        self.add_to_note("- The deck (S7).", DECK_ENTRY)
        out, _, code = self.run_here("import-file", str(self.local("deck.txt", b"Order book 95.4")), "--key", "S7")
        self.assertEqual(code, 0)
        self.assertIn("as file:deck.txt, source S7 of 01_northbridge.md", out)
        _, err, code = self.run_here("import-file", str(self.outside / "none.pdf"), "--key", "S7")
        self.assertEqual(code, 1)
        self.assertIn("no file", err)


class Inventory(Kept):
    def test_every_source_is_listed_with_its_status_and_the_lines_that_cite_it(self):
        self.add_to_note("- The deck (S7).", DECK_ENTRY)
        self.fetch()
        sourcedb.import_file(self.ws, self.con, self.local("deck.txt", b"Order book 95.4"), "S7")
        entries = {entry.key: entry for entry in inventory.inventory(self.ws, self.con)}
        self.assertEqual({key: entry.status for key, entry in entries.items()}, {"S1": "fetched", "S2": "refused", "S7": "imported file"})
        lines = self.note.read_text(encoding="utf-8").splitlines()
        self.assertIn(("01_northbridge.md", lines.index("- A figure no source holds: $999.9M (S1).") + 1), entries["S1"].cited_at)
        self.assertEqual(entries["S7"].cited_at, (("01_northbridge.md", lines.index("- The deck (S7).") + 1),))
        self.assertEqual(entries["S1"].text_chars, len("Revenue was 551,102 thousand. Research spending was $77.3 million."))
        self.assertTrue(entries["S1"].sha256 and entries["S1"].fetched_at)

    def test_text_gathered_by_hand_and_a_source_never_fetched_are_told_apart(self):
        self.fetch()
        capture = self.ws.data / "raw" / "browser_capture.jsonl"
        capture.write_text(f'{{"url": "{ORDERS}", "text": "Order book 95.4", "method": "by hand"}}\n', encoding="utf-8")
        sourcedb.import_text(self.ws, self.con)
        self.add_to_note("", "- **S3.** Another page. https://example.com/later.html\n")
        statuses = {entry.key: entry.status for entry in inventory.inventory(self.ws, self.con)}
        self.assertEqual(statuses, {"S1": "fetched", "S2": "gathered by hand", "S3": "not fetched"})

    def test_primary_comes_from_a_tag_a_registry_or_a_domain_the_workspace_lists(self):
        self.assertEqual(inventory.kind_of("https://www.sec.gov/Archives/x.htm", "", ()), "primary")
        self.assertEqual(inventory.kind_of("https://news.example/story", "- **S4.** A story. [secondary]", ()), "secondary")
        self.assertEqual(inventory.kind_of("https://www.sec.gov/x", "- **S4.** [Secondary] commentary", ()), "secondary")
        self.assertEqual(inventory.kind_of("https://ir.northbridge.example/r", "", ("northbridge.example",)), "primary")
        self.assertEqual(inventory.kind_of("https://notnorthbridge.example/r", "", ("northbridge.example",)), "")
        self.assertEqual(inventory.kind_of("file:deck.pdf", "- **S7.** Deck. [primary] file:deck.pdf", ()), "primary")
        self.assertEqual(inventory.kind_of("https://news.example/story", "", ()), "")

    def test_the_command_prints_and_writes_the_list(self):
        self.ws.config_path.write_text(self.ws.config_path.read_text(encoding="utf-8") + '\n[sources]\nprimary = ["example.com"]\n',
                                       encoding="utf-8")
        out, _, code = self.run_here("inventory")
        self.assertEqual(code, 0)
        self.assertIn("2 not fetched", out)
        with (self.ws.data / inventory.REPORT).open(encoding="utf-8", newline="") as report:
            rows = list(csv.DictReader(report))
        self.assertEqual([(row["source_key"], row["status"], row["kind"]) for row in rows],
                         [("S1", "not fetched", "primary"), ("S2", "not fetched", "primary")])
        self.assertTrue(rows[0]["cited_at"].startswith("01_northbridge.md:"))


class Search(Kept):
    def test_each_hit_shows_its_words_around_it_and_the_lines_that_cite_its_document(self):
        self.fetch({ORDERS: (200, "text/plain", b"Order book 95.4 million.")})
        self.add_to_note("", "- **S5.** A page nothing cites. https://example.com/uncited.html\n")
        sourcedb.record_sources(self.ws, self.con)
        self.con.execute("INSERT INTO documents VALUES (?,?,?,?,?)",
                         ("https://example.com/uncited.html", None, "Research spending was $77.3 million here too.", 45, "html"))
        sourcedb.build_index(self.con)
        found = {hit.url: hit for hit in sourcedb.search(self.con, ["77.3"], sourcedb.citing(self.ws, self.con))}
        self.assertEqual(set(found), {ANNUAL, "https://example.com/uncited.html"})
        self.assertIn("Research spending was $[77.3] million.", found[ANNUAL].passages[0])
        lines = self.note.read_text(encoding="utf-8").splitlines()
        self.assertIn(("01_northbridge.md", lines.index("- Research spending fell to $77.3M (S1).") + 1), found[ANNUAL].cited_at)
        self.assertEqual(found["https://example.com/uncited.html"].cited_at, ())

    def test_passages_mark_each_hit_and_say_where_text_was_cut(self):
        text = "a " * 100 + "Revenue 551,102 here, and revenue again." + " b" * 100
        shown = sourcedb.passages(text, "revenue")
        self.assertEqual(len(shown), 2)
        self.assertTrue(shown[0].startswith("... ") and shown[0].endswith(" ..."))
        self.assertIn("[Revenue] 551,102", shown[0])
        self.assertIn("[revenue] again", shown[1])
        self.assertEqual(sourcedb.passages("short", "missing"), [])

    def test_the_command_says_when_no_note_cites_a_hit(self):
        self.fetch()
        self.con.execute("INSERT INTO documents VALUES (?,?,?,?,?)", ("https://example.com/stray.html", None, "551,102 again", 13, "html"))
        sourcedb.build_index(self.con)
        out, _, code = self.run_here("search", "551,102")
        self.assertEqual(code, 0)
        self.assertIn("listed as: 01_northbridge.md S1", out)
        self.assertIn("no note cites this document", out)
        self.assertIn("[551,102]", out)
        self.assertIn("2 document(s) matched", out)


if __name__ == "__main__":
    unittest.main()
