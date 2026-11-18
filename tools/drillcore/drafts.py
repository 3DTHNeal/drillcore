"""Drafts kept in other formats, read as text. A report kept in a document tool is exported as a Word document or a PDF
more easily than as Markdown, so a `.docx` or `.pdf` in the drafts folder is a draft like a `.md` one: every command that
reads drafts reads it as the text below, and the line numbers its findings give count that text.

- A Word document is read from its own XML with the standard library: each paragraph a line, a heading written with
  as many #s as its level, a list item with "- " before it, and each table as a Markdown table, so the checks that read
  tables and headings read them as they would in Markdown. Text in a text box or a footnote isn't read.
- A PDF is read with `pdftotext`, as `fetch` reads one, page by page. A PDF has no headings or tables to keep, so the
  checks that read those find less in it than in the same draft as Markdown or a Word document.

Nothing in a draft is run, and nothing it links to is opened.
"""
import re
import shutil
import subprocess
import zipfile
from collections.abc import Sequence
from pathlib import Path
from xml.etree import ElementTree

# What a drafts folder holds that is read as a draft, and what is read as Markdown.
SUFFIXES = (".md", ".docx", ".pdf")
MARKDOWN = (".md", ".markdown", ".txt")
# Word's XML namespace, which every element of a document's body is in.
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# A paragraph style that makes a heading, and its level: Heading1 to Heading9, or Title, which is level 1.
HEADING_STYLE = re.compile(r"(?i)^(?:heading\s?(?P<level>[1-9])|title)$")
LIST_STYLE = re.compile(r"(?i)list")
# A document's body is read whole, so a corrupt or hostile one can't be made to cost more than this to read.
MOST_BYTES = 64 * 1024 * 1024


class Unreadable(ValueError):
    """A draft that can't be read as text, saying why."""


def is_draft(path: Path) -> bool:
    """Whether a file in the drafts folder is a draft: Markdown, a Word document or a PDF, and not the lock file Word
    keeps beside a document it has open (~$name.docx)."""
    return path.is_file() and path.suffix.lower() in SUFFIXES and not path.name.startswith("~$")


def read_draft(path: Path) -> str:
    """A draft's text, as the checks read it. Raises `Unreadable` for a Word document or PDF that can't be read. A
    Markdown draft is read as its reader sees it, without the backslashes that escape punctuation (`unescaped`)."""
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return docx_text(path)
    if suffix == ".pdf":
        return pdf_text(path)
    return unescaped(path.read_text(encoding="utf-8-sig"))


# A backslash before punctuation, as a document tool writes R\&D or 10\. when it exports Markdown. An escaped bar is
# kept, since unescaped it would split a table's cell in two, and so is a backslash before anything else, as in a path.
ESCAPED = re.compile(r"\\([!-/:-@\[\]^_`{}~\\])")


# An in-text citation: brackets holding a year, or "n.d.", as author-date citations do. `assay` reads names allowed in
# citations by it, and sets aside the year letters inside it; `overlap` leaves citations out.
CITATION = re.compile(r"\((?:[^()]|\([^()]*\))*?(?:\b(?:1[5-9]|20)\d{2}[a-z]?\b|\bn\.d\.)(?:[^()]|\([^()]*\))*\)")


def unescaped(text: str) -> str:
    """Markdown text with its escaped punctuation written plain: R\\&D is R&D, \\*not\\* is *not*. Lines keep their
    numbers."""
    return ESCAPED.sub(r"\1", text)


def _text(paragraph: ElementTree.Element) -> str:
    """A paragraph's text: its runs' text, tabs and breaks, in order."""
    pieces = []
    for element in paragraph.iter():
        if element.tag == f"{W}t" and element.text:
            pieces.append(element.text)
        elif element.tag == f"{W}tab":
            pieces.append("\t")
        elif element.tag in (f"{W}br", f"{W}cr"):
            pieces.append(" ")
    return "".join(pieces)


def _paragraph(paragraph: ElementTree.Element) -> str:
    """A paragraph as a line of Markdown: a heading with its #s, a list item with "- ", anything else as written."""
    text = _text(paragraph).strip()
    if not text:
        return ""
    style = paragraph.find(f"{W}pPr/{W}pStyle")
    name = style.get(f"{W}val", "") if style is not None else ""
    heading = HEADING_STYLE.match(name)
    if heading:
        return "#" * int(heading.group("level") or 1) + " " + text
    if LIST_STYLE.search(name) or paragraph.find(f"{W}pPr/{W}numPr") is not None:
        return "- " + text
    return text


def _table(table: ElementTree.Element) -> list[str]:
    """A table as Markdown rows, its first row the heading and a divider after it. A bar in a cell's text is written
    as a slash, so it can't split the cell."""
    rows = []
    for row in table.findall(f"{W}tr"):
        cells = [" ".join(_text(paragraph).strip() for paragraph in cell.iter(f"{W}p")).strip().replace("|", "/")
                 for cell in row.findall(f"{W}tc")]
        rows.append("| " + " | ".join(cells) + " |")
        if len(rows) == 1:
            rows.append("|" + "---|" * len(cells))
    return rows


def docx_text(path: Path) -> str:
    """A Word document's body as Markdown text: paragraphs, headings, list items and tables, in order, with a blank
    line between blocks."""
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MOST_BYTES:
                raise Unreadable(f"{path.name} is too large to read as a draft ({info.file_size:,} bytes of text).")
            # The user's own document, read with expat, which doesn't fetch entities from outside the file.
            root = ElementTree.fromstring(archive.read(info))  # noqa: S314
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, OSError) as problem:
        raise Unreadable(f"{path.name} can't be read as a Word document: {problem}") from None
    body = root.find(f"{W}body")
    blocks: list[str] = []
    for element in body if body is not None else []:
        if element.tag == f"{W}p":
            line = _paragraph(element)
            if line:
                blocks.append(line)
        elif element.tag == f"{W}tbl":
            blocks.append("\n".join(_table(element)))
    return "\n\n".join(blocks) + "\n"


# ---------------------------------------------------------------- what in a draft is analysis

# A Markdown heading: its marks, which give its level, and its title.
HEADING = re.compile(r"^ {0,3}(?P<marks>#{1,6})[ \t]+(?P<title>.*?)[ \t]*#*[ \t]*$")
# A heading that opens a draft's reference list. What the list gives is the works cited, as `proof` reads them: its
# years, page ranges, filing numbers and titles are no claims of the draft's own.
REFERENCE_HEADING = re.compile(r"^#+\s*(?:[A-Z]?\d*[.)]?\s*)?(?:References|Bibliography|Works cited|Reference list)\b", re.I)
# A section's number before its title: "2.1 ", "3b-2. ", "A1. ", "B. ".
NUMBERED = re.compile(r"^(?:[A-Z]?\d+[a-z]?(?:[.-]\d+)*|[A-Z])[.)]?\s+")


def _is_record(title: str, records: Sequence[str]) -> bool:
    """Whether a heading's title opens one of the sections named as records: the name as the title starts, in any
    case, with or without the section's number before it, and not the start of a longer word."""
    plain = NUMBERED.sub("", title, count=1)
    return any(re.match(rf"{re.escape(name.strip())}(?!\w)", candidate, re.I) for name in records for candidate in (title, plain))


def set_aside(text: str, records: Sequence[str] = (), references: bool = True) -> str:
    """A draft as the checks that judge what it says read it: its reference list, under a heading such as
    "References", and each section that a heading named in `records` opens, such as a log of prompts quoted word for
    word, left blank. A section runs to the next heading of its level or above. Every line is kept, empty, so the line
    numbers a finding gives are the draft's own. With `references` false, the reference list is kept."""
    lines = text.split("\n")
    level = 0  # The level of the section being set aside, or 0 while none is.
    for at, line in enumerate(lines):
        heading = HEADING.match(line)
        if heading:
            marks = len(heading.group("marks"))
            if level and marks > level:
                lines[at] = ""
                continue
            level = 0
            if (references and REFERENCE_HEADING.match(line.strip())) or _is_record(heading.group("title"), records):
                level = marks
        if level:
            lines[at] = ""
    return "\n".join(lines)


def pdf_text(path: Path) -> str:
    """A PDF's text, read with pdftotext page by page, the pages a blank line apart."""
    program = shutil.which("pdftotext")
    if not program:
        raise Unreadable(f"{path.name} is a PDF, and reading one needs pdftotext (from Poppler) on the path.")
    try:
        done = subprocess.run([program, "-layout", "-enc", "UTF-8", str(path), "-"], capture_output=True, timeout=180, check=True)
    except (OSError, subprocess.SubprocessError) as problem:
        raise Unreadable(f"{path.name} can't be read as a PDF: {problem}") from None
    leaves = [leaf.rstrip() for leaf in done.stdout.decode("utf-8", "replace").split("\f")]
    return "\n\n".join(leaf for leaf in leaves if leaf.strip()) + "\n"
