"""Tests for drafts kept as Word documents or PDFs, read as text. Everything here is made up."""
import shutil
import tempfile
import unittest
import unittest.mock
import zipfile
from pathlib import Path

from support import write_docx

from drillcore import drafts


class WhatADraftSays(unittest.TestCase):
    """A draft's reference list and the sections named as records, left blank where they stand."""

    DRAFT = ("# Report\n\n## 1. Results\n\nRevenue was $551.1M.\n\n## 13. Reflective statement\n\nI learned a lot.\n\n"
             "## References\n\n- Roe, Jane. 2024. *Arms.* Exhibit 99.\n\n## Appendix\n\n### Appendix A. Worksheet\n\n"
             "The margin was 41.2%.\n\n### Appendix B. Prompts\n\n#### Entry 1\n\nWrite 500 words.\n\n"
             "### Appendix Bx. Not a record\n\nKept.\n")

    def test_the_reference_list_and_the_records_are_blank_and_every_line_keeps_its_number(self):
        kept = drafts.set_aside(self.DRAFT, ["Appendix B", "Reflective statement"])
        self.assertEqual(len(kept.split("\n")), len(self.DRAFT.split("\n")))
        lines = self.DRAFT.split("\n")
        self.assertEqual(kept.split("\n")[lines.index("The margin was 41.2%.")], "The margin was 41.2%.")
        for stays in ("Revenue was $551.1M.", "## Appendix", "### Appendix A. Worksheet", "### Appendix Bx. Not a record", "Kept."):
            self.assertIn(stays, kept.split("\n"))
        for goes in ("I learned a lot.", "## References", "Exhibit 99", "### Appendix B. Prompts", "#### Entry 1", "Write 500"):
            self.assertNotIn(goes, kept)

    def test_the_reference_list_can_be_kept(self):
        self.assertIn("Roe, Jane", drafts.set_aside(self.DRAFT, references=False))
        self.assertNotIn("Roe, Jane", drafts.set_aside(self.DRAFT))
        self.assertIn("Write 500", drafts.set_aside(self.DRAFT))


class Drafts(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)

    def test_a_word_document_reads_as_markdown(self):
        path = write_docx(self.folder / "report.docx", [
            ("Title", "Northbridge Robotics"), ("Heading2", "1. Results"), "Revenue was $551.1M | in 2025.",
            ("ListParagraph", "Orders doubled."), [["Item", "2025"], ["Revenue, $M", "551.1"], ["Margin", "41|2%"]], ""])
        self.assertEqual(drafts.read_draft(path), "# Northbridge Robotics\n\n## 1. Results\n\nRevenue was $551.1M | in 2025.\n\n"
                                                  "- Orders doubled.\n\n| Item | 2025 |\n|---|---|\n| Revenue, $M | 551.1 |\n"
                                                  "| Margin | 41/2% |\n")

    def test_markdown_is_read_without_its_escapes(self):
        # As a document tool exports it: R\&D, \*, 10\. and \$; an escaped bar stays, and so does a path's backslash.
        (self.folder / "report.md").write_text(r"Head of R\&D, \*not\* 10\. \$5M | a \| b | C:\Reports\x.md", encoding="utf-8")
        self.assertEqual(drafts.read_draft(self.folder / "report.md"), r"Head of R&D, *not* 10. $5M | a \| b | C:\Reports\x.md")

    def test_what_counts_as_a_draft(self):
        for name, counts in (("a.md", True), ("b.docx", True), ("c.pdf", True), ("~$b.docx", False), ("d.txt", False), ("e.html", False)):
            (self.folder / name).write_bytes(b"")
            with self.subTest(name):
                self.assertEqual(drafts.is_draft(self.folder / name), counts)

    def test_a_document_that_cant_be_read_says_why(self):
        (self.folder / "broken.docx").write_bytes(b"not a zip")
        with self.assertRaises(drafts.Unreadable) as raised:
            drafts.read_draft(self.folder / "broken.docx")
        self.assertIn("can't be read as a Word document", str(raised.exception))
        with zipfile.ZipFile(self.folder / "empty.docx", "w") as archive:
            archive.writestr("other.xml", "<x/>")
        with self.assertRaises(drafts.Unreadable):
            drafts.read_draft(self.folder / "empty.docx")

    def test_a_pdf_needs_pdftotext(self):
        (self.folder / "report.pdf").write_bytes(b"%PDF-1.4")
        with unittest.mock.patch.object(drafts.shutil, "which", return_value=None):
            with self.assertRaises(drafts.Unreadable) as raised:
                drafts.read_draft(self.folder / "report.pdf")
        self.assertIn("needs pdftotext", str(raised.exception))

    @unittest.skipUnless(shutil.which("pdftotext"), "pdftotext isn't on the path")
    def test_a_pdf_reads_as_its_text(self):
        # A one-page PDF with one line of text, written out by hand.
        stream = b"BT /F1 12 Tf 72 720 Td (Revenue was 551.1) Tj ET"
        objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                   b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
                   b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream), b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
        body, offsets = b"%PDF-1.4\n", []
        for number, content in enumerate(objects, 1):
            offsets.append(len(body))
            body += b"%d 0 obj\n%s\nendobj\n" % (number, content)
        xref = len(body)
        body += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % at for at in offsets)
        body += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref
        (self.folder / "report.pdf").write_bytes(body)
        self.assertIn("Revenue was 551.1", drafts.read_draft(self.folder / "report.pdf"))


if __name__ == "__main__":
    unittest.main()
