"""Tests for the Sources lists to and from a reference manager. Every reference is fictional, and nothing reaches the
network: each fetch is answered by a stand-in."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from support import CODE_ROOT, run_cli

from drillcore import references, sourcedb, workspace

ANNUAL = "https://example.com/northbridge/annual-2025.html"
SECOND = """# A second note

## Sales (S1)

- Sales rose (S1).

## Sources

- **S1.** Example Wire. 2026. "Northbridge sales & margins." https://example.com/wire/northbridge.html
- **S2.** A note on the founder's interview, no title given. https://example.com/wire/interview.html
"""
BIB = r"""
@string{wire = "Example {W}ire"}
@comment{ anything at all, even @misc{x, title = {Not read}} }
@article{doe2025,
  author = {Doe, Jane and {Northbridge Robotics} and M{\"u}ller, Zo{\"e}},
  title = {{Warehouse} robots \& the order book},
  journal = wire,
  year = 2025,
  month = mar,
  doi = {10.0000/example.1},
}
@misc(release2026,
  title = "Order book update",
  howpublished = {\url{https://example.com/northbridge/orders.html}},
  urldate = {2026-03-04}
)
"""
CSL_EXPORT = [{"id": "item-1", "type": "report", "title": "Annual *Report* 2025",
               "author": [{"family": "Robotics", "given": "Northbridge"}], "issued": {"date-parts": [[2026, 2]]},
               "URL": "https://example.com/northbridge/annual-2025.html", "accessed": {"date-parts": [[2026, 11, 10]]}},
              {"id": "item-2", "title": "No address", "author": [{"literal": "Example Wire"}, {"family": "Doe", "given": "Jane"}]}]


class Export(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        (root / "research" / "02_second.md").write_text(SECOND, encoding="utf-8")
        self.ws = workspace.Workspace(root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)

    def test_an_entry_is_read_only_when_its_written_the_usual_way(self):
        self.assertEqual(references.read_entry("Northbridge Robotics. 2026. *Annual Report 2025.* "),
                         ("Annual Report 2025", "Northbridge Robotics", "2026", ""))
        self.assertEqual(references.read_entry('Example Wire. 2026. "Sales rose." Page 3.'), ("Sales rose", "Example Wire", "2026", "Page 3"))
        self.assertEqual(references.read_entry("A note with no title, 2026."), ("", "", "", "A note with no title, 2026"))

    def test_each_entry_is_exported_with_its_fetch_date_and_a_key_of_its_own_note(self):
        sourcedb.record_sources(self.ws, self.con)
        sourcedb.fetch(self.ws, self.con, get=lambda url: (200, "text/html", url, b"<p>Revenue</p>", None) if url == ANNUAL
                       else (404, "text/html", url, b"", "HTTP 404"), say=lambda _: None)
        count, written = references.export(self.ws, self.con)
        self.assertEqual(count, 4)
        self.assertEqual([path.name for path in written], [references.BIBTEX, references.CSL])
        items = {item["id"]: item for item in json.loads((self.ws.data / references.CSL).read_text(encoding="utf-8"))}
        self.assertEqual(sorted(items), ["01_northbridge:S1", "01_northbridge:S2", "02_second:S1", "02_second:S2"])
        annual = items["01_northbridge:S1"]
        self.assertEqual((annual["title"], annual["author"], annual["issued"], annual["URL"]),
                         ("Annual Report 2025", [{"literal": "Northbridge Robotics"}], {"date-parts": [[2026]]}, ANNUAL))
        self.assertEqual(len(annual["accessed"]["date-parts"][0]), 3)
        self.assertNotIn("accessed", items["01_northbridge:S2"])  # Its fetch failed.
        self.assertNotIn("title", items["02_second:S2"])  # Never guessed.
        self.assertIn("A note on the founder's interview", items["02_second:S2"]["note"])
        bib = (self.ws.data / references.BIBTEX).read_text(encoding="utf-8")
        self.assertIn("@misc{02_second:S1,", bib)
        self.assertIn(r"title = {Northbridge sales \& margins},", bib)
        self.assertIn("author = {{Example Wire}},", bib)
        self.assertEqual(bib.count("{"), bib.count("}"))

    def test_the_command_writes_the_format_asked_for(self):
        out, _, code = run_cli("export-sources", "--format", "csl")
        self.assertEqual(code, 0)
        self.assertIn(references.CSL, out)
        self.assertNotIn(references.BIBTEX, out)


class Import(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        self.ws = workspace.Workspace(root, "test")
        self.exports = Path(self.tmp.name) / "exports"
        self.exports.mkdir()

    def test_bibtex_is_read_with_its_braces_strings_and_accents(self):
        entries = references.parse_bibtex(BIB)
        self.assertEqual([entry["@key"] for entry in entries], ["doe2025", "release2026"])
        self.assertEqual(entries[0]["journal"], "Example {W}ire")
        found = references.from_bibtex(BIB)
        self.assertEqual(found[0].author, "Jane Doe, Northbridge Robotics and Zoë Müller")
        self.assertEqual((found[0].title, found[0].year, found[0].url), ("Warehouse robots & the order book", "2025",
                                                                          "https://doi.org/10.0000/example.1"))
        self.assertEqual((found[1].url, found[1].accessed), ("https://example.com/northbridge/orders.html", "2026-03-04"))

    def test_an_address_is_read_as_written_not_as_latex_prose(self):
        found = references.from_bibtex("@misc{a, title={A}, url={\\url{https://example.com/~doe/q--3\\_final.pdf}}}\n")
        self.assertEqual(found[0].url, "https://example.com/~doe/q--3_final.pdf")

    def test_an_entry_that_never_closes_is_refused(self):
        broken = self.exports / "broken.bib"
        broken.write_text("@misc{a, title = {Open", encoding="utf-8")
        with self.assertRaises(ValueError):
            references.read_export(broken)

    def test_proposals_are_written_to_a_file_and_never_to_the_notes(self):
        export = self.exports / "library.json"
        export.write_text(json.dumps(CSL_EXPORT), encoding="utf-8")
        notes = {path: path.read_text(encoding="utf-8") for path in (self.ws.root / "research").glob("*.md")}
        count, written = references.propose(self.ws, export)
        self.assertEqual(count, 2)
        proposed = written.read_text(encoding="utf-8")
        self.assertIn(f"- **S?.** Northbridge Robotics. 2026. *Annual Report 2025.* {ANNUAL}", proposed)
        self.assertIn("- **S?.** Example Wire and Jane Doe. *No address.* (the export gives no address: add one before citing it)",
                      proposed)
        self.assertEqual(notes, {path: path.read_text(encoding="utf-8") for path in (self.ws.root / "research").glob("*.md")})

    def test_the_command_reads_bibtex_and_refuses_what_it_cant_read(self):
        export = self.exports / "library.bib"
        export.write_text(BIB, encoding="utf-8")
        out, _, code = run_cli("import-sources", str(export))
        self.assertEqual(code, 0)
        self.assertIn("proposed 2 Sources entries", out)
        missing = self.exports / "missing.bib"
        out, _, code = run_cli("import-sources", str(missing))
        self.assertEqual(code, 1)
        self.assertIn("can't be read", out)


if __name__ == "__main__":
    unittest.main()
