"""Pinpoint citations: a source key with the page or section it's read at, as `S1 p.47`, `S1 pp.47-48` or
`S1 §Note 12`. A reviewer needs the pinpoint to check anything by hand, so a figure or a quotation is held to it.

- A PDF's text is kept with where each page starts and ends, and with the number printed on the page where one stands
  alone on its first or last lines. `p.47` means page 47 counted from the front, or the page printed 47: annual reports
  number their pages after a cover and contents, and a citation may follow either. What's on either counts.
- A section is found by its heading: a line starting with the words cited, such as "Note 12", "Item 7" or "2.3". It
  runs to the next line that starts a section numbered the same way. A contents page lists the same headings, so each
  line that starts with them begins a stretch, and what's in any of them counts.
- A pinpoint that can't be read is not judged, never guessed: a page on a source with no pages, a section cited by
  words alone, a heading the source doesn't have, or a PDF read before its pages were kept (`fetch --reread` reads it
  again).

This module reads the database and the notes' text. It needs nothing installed.
"""
import re
import sqlite3
from collections.abc import Container
from dataclasses import dataclass

# A key, then its pinpoint: "S1 p.47", "S1, p. 47", "S1 pp.47-48", "S1 §Note 12", "S1 § 2.3".
PIN = re.compile(r"(?<![\w.\-/])(?P<key>[A-Z]{1,2}\d{1,3}[a-z]?)\s*,?\s*"
                 r"(?:(?P<pp>pp?)\.?\s?(?P<first>\d{1,4})(?:\s?[-–]\s?(?P<last>\d{1,4}))?(?![\w.,]\d)"
                 r"|§\s?(?P<section>(?:[A-Z][A-Za-z]*\.?\s?)?\d+(?:\.\d+)*[A-Za-z]?(?![\w.])"
                 r"|[^,;)\]|\n]{1,60}?(?=\s*(?:[,;)\]|]|$))))")
# A line that's only a page's number: "47", "- 47 -", "Page 47", "47 of 120".
FOLIO = re.compile(r"[\s\-–—]*(?:page\s+)?(\d{1,4})(?:\s*(?:of|/)\s*\d+)?[\s\-–—]*", re.I)
NUMBERED = re.compile(r"(?P<word>[A-Za-z]+\.?)?\s?(?P<number>\d+(?:\.\d+)*[A-Za-z]?)")


@dataclass(frozen=True)
class Pin:
    """Where a source key is cited at: pages `first` to `last`, or a section."""
    key: str
    first: int = 0
    last: int = 0
    section: str = ""

    def shown(self) -> str:
        if self.section:
            return f"§{self.section}"
        return f"p.{self.first}" if self.first == self.last else f"pp.{self.first}-{self.last}"

    @property
    def where(self) -> str:
        """What the pinpoint names, in words: "page 47", "pages 47 to 48" or "section Note 12"."""
        if self.section:
            return f"section {self.section}"
        return f"page {self.first}" if self.first == self.last else f"pages {self.first} to {self.last}"


def pins_in(text: str, known: Container[str]) -> dict[str, Pin]:
    """The pinpoints a line gives the keys it cites, by key. `known` holds the keys the note can use; a word shaped
    like a key that isn't one has no pinpoint."""
    found: dict[str, Pin] = {}
    for match in PIN.finditer(text):
        key = match.group("key")
        if key not in known:
            continue
        if match.group("section"):
            found.setdefault(key, Pin(key, section=" ".join(match.group("section").split())))
        else:
            first = int(match.group("first"))
            last = int(match.group("last") or first)
            found.setdefault(key, Pin(key, min(first, last), max(first, last)))
    return found


def without_pins(text: str, known: Container[str]) -> str:
    """A line with each pinpoint after a key it can use blanked, keeping the key, so "p.147" isn't read as a figure."""
    def blank(match: re.Match[str]) -> str:
        if match.group("key") not in known:
            return match.group(0)
        return match.group("key") + " " * (len(match.group(0)) - len(match.group("key")))
    return PIN.sub(blank, text)


# ---------------------------------------------------------------- pages, as a PDF is read

def folio(page: str) -> str:
    """The number printed on a page, when a line of its own on the page's first two or last two lines is only that."""
    lines = [line for line in page.split("\n") if line.strip()]
    for line in lines[-2:][::-1] + lines[:2]:
        printed = FOLIO.fullmatch(line)
        if printed:
            return printed.group(1)
    return ""


def joined(pages: list[str]) -> tuple[str, list[tuple[int, int, str]]]:
    """Pages of text as one text, a line break between each, with where each page starts and ends in it and the number
    printed on it. A page with no text has a start and end of its own, at the same place."""
    text, spans = "", []
    for page in pages:
        if page and text:
            text += "\n"
        start = len(text)
        text += page
        spans.append((start, len(text), folio(page)))
    return text, spans


def record(con: sqlite3.Connection, url: str, spans: list[tuple[int, int, str]] | None) -> None:
    """Keep where a document's pages start and end, replacing what was kept for it. None keeps nothing: the document
    has no pages."""
    con.execute("DELETE FROM document_pages WHERE url=?", (url,))
    if spans:
        con.executemany("INSERT INTO document_pages(url, page, start, end_at, folio) VALUES (?,?,?,?,?)",
                        [(url, number, start, end, printed) for number, (start, end, printed) in enumerate(spans, 1)])


# ---------------------------------------------------------------- where a pinpoint is

Region = list[tuple[int, int]]


def page_region(con: sqlite3.Connection, url: str, pin: Pin) -> tuple[Region | None, str]:
    """The stretches of a document's text a page pinpoint names, or None and why it can't be read."""
    pages = con.execute("SELECT page, start, end_at, folio FROM document_pages WHERE url=? ORDER BY page", (url,)).fetchall()
    if not pages:
        how = con.execute("SELECT extractor FROM documents WHERE url=?", (url,)).fetchone()
        if how and how[0] == "pdftotext":
            return None, "its pages weren't kept when it was read; `fetch --reread` reads it again with them"
        return None, f"the source has no pages to find {pin.shown()} on"
    wanted = range(pin.first, pin.last + 1)
    region = [(start, end) for page, start, end, printed in pages
              if page in wanted or (printed.isdigit() and int(printed) in wanted)]
    return region, "" if region else f"the source has {len(pages)} pages"


def section_region(text: str, pin: Pin) -> tuple[Region | None, str]:
    """The stretches of a document's text a section pinpoint names, each from a line that starts with the section's
    words to the next line starting a section numbered the same way, or None and why it can't be read."""
    numbered = NUMBERED.fullmatch(pin.section)
    if not numbered:
        return None, f"only a numbered section, such as Note 12, Item 7 or 2.3, is found by its heading, not {pin.section!r}"
    word, number = numbered.group("word") or "", numbered.group("number")
    if word:
        lead = rf"{re.escape(word.rstrip('.'))}\.?\s*"
        starts = re.compile(rf"^[ \t]*{lead}{re.escape(number)}(?![\w.]?\d)", re.I | re.M)
        others = re.compile(rf"^[ \t]*{lead}(?!{re.escape(number)}(?![\w.]?\d))\d", re.I | re.M)
    else:
        depth = number.count(".")
        starts = re.compile(rf"^[ \t]*{re.escape(number)}[.)]?\s+(?=[A-Z])", re.M)
        others = re.compile(rf"^[ \t]*(?!{re.escape(number)}[.)]?\s)\d+(?:\.\d+){{{depth}}}[.)]?\s+(?=[A-Z])", re.M)
    region: Region = []
    for begins in starts.finditer(text):
        ends = others.search(text, begins.end())
        region.append((begins.start(), ends.start() if ends else len(text)))
    if not region:
        return None, f"no line of the source starts with {pin.section!r}"
    return region, ""


def region(con: sqlite3.Connection, url: str, text: str, pin: Pin) -> tuple[Region | None, str]:
    """The stretches of a document's text a pinpoint names, or None and why it can't be read."""
    return section_region(text, pin) if pin.section else page_region(con, url, pin)


def region_text(text: str, stretches: Region) -> str:
    """The text of the stretches a pinpoint names, one after another."""
    return "\n".join(text[start:end] for start, end in stretches)


def within(stretches: Region, start: int) -> bool:
    return any(low <= start < high for low, high in stretches)


def status_for(pin: Pin) -> str:
    """The status of a figure or quotation a source holds, but not where the pinpoint says."""
    return "not_in_cited_section" if pin.section else "not_on_cited_page"
