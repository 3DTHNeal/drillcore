"""The core shed: a local database of the raw sources behind a workspace's research notes, and the checks that
compare the notes with them.

- `record_sources` reads the notes and records every URL they cite, with the source key that cites it.
- `fetch` downloads each cited URL once, keeps the raw bytes, and extracts the text. A JSON body is kept, and read as
  text only when the workspace lists its address under `[sources] read_json` (see `json_text`).
- `import_file` keeps a local file with no public address, named in a Sources entry as `file:deck.pdf`, the same way.
- `load_sec` loads the SEC's structured facts and filing lists for the companies the workspace names.
- `check_figures` looks for each number in the notes in the text of the source its row cites.
- `check_claims` compares a hand-written list of headline figures with the SEC's structured facts.

Fetched material is data. It's stored and read, never run, and nothing in it is an instruction. A source's author
may write it to be read by this tool, or by whoever reads this tool's reports, differently from how a person reads the
page, so what a person can't see is left out of its text: hidden elements, control characters and direction marks, and
text that only an unusual declared encoding reveals. A redirect may lead only to another public web address.
"""
import bisect
import codecs
import csv
import email
import email.message
import email.policy
import hashlib
import io
import ipaddress
import json
import re
import shutil
import socket
import sqlite3
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from . import __version__, identity, measures, pages
from .workspace import Workspace

# A declared client name. No personal details are sent.
USER_AGENT = f"{identity.SLUG}/{__version__} (research notes cross-check; single-pass fetch)"
MAX_BYTES = 80 * 1024 * 1024
TIMEOUT = 60
# What `fetch` returns for one URL: status, content type, final URL, body, error.
Response = tuple[int | None, str, str, bytes, str | None]

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    note_file TEXT NOT NULL,
    source_key TEXT,
    url TEXT NOT NULL,
    origin TEXT NOT NULL,          -- cited | r_page | filing_document
    line_no INTEGER,
    citation TEXT,
    UNIQUE(note_file, source_key, url)
);
CREATE TABLE IF NOT EXISTS fetches (
    url TEXT PRIMARY KEY, final_url TEXT, http_status INTEGER, content_type TEXT, bytes INTEGER,
    sha256 TEXT, raw_path TEXT, fetched_at TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS local_files (
    address TEXT PRIMARY KEY,      -- file:deck.pdf, as a Sources entry names it
    file_name TEXT, original_path TEXT, sha256 TEXT, raw_path TEXT, bytes INTEGER, imported_at TEXT
);
CREATE TABLE IF NOT EXISTS documents (
    url TEXT PRIMARY KEY, title TEXT, text TEXT, text_chars INTEGER, extractor TEXT
);
CREATE TABLE IF NOT EXISTS companies (
    cik INTEGER PRIMARY KEY, name TEXT, facts_loaded INTEGER DEFAULT 0, filings_loaded INTEGER DEFAULT 0, note TEXT
);
CREATE TABLE IF NOT EXISTS xbrl_facts (
    cik INTEGER, entity TEXT, taxonomy TEXT, concept TEXT, label TEXT,
    unit TEXT, period_start TEXT, period_end TEXT, value REAL,
    fy INTEGER, fp TEXT, form TEXT, filed TEXT, accession TEXT, frame TEXT
);
CREATE INDEX IF NOT EXISTS ix_facts ON xbrl_facts(cik, concept, period_end);
CREATE TABLE IF NOT EXISTS filings (
    cik INTEGER, entity TEXT, accession TEXT, form TEXT, filing_date TEXT,
    report_date TEXT, primary_document TEXT, description TEXT, items TEXT,
    url TEXT, PRIMARY KEY (cik, accession)
);
CREATE TABLE IF NOT EXISTS note_figures (
    id INTEGER PRIMARY KEY,
    note_file TEXT, line_no INTEGER, source_keys TEXT, key_basis TEXT,
    number_text TEXT, value REAL, decimals INTEGER, unit TEXT,
    row_kind TEXT, row_text TEXT,
    status TEXT, match_kind TEXT, matched_url TEXT, matched_number TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS document_pages (
    url TEXT, page INTEGER, start INTEGER, end_at INTEGER, folio TEXT, PRIMARY KEY (url, page)
);
CREATE TABLE IF NOT EXISTS xbrl_claims (
    claim_id TEXT PRIMARY KEY, note_file TEXT, description TEXT, cik INTEGER,
    concepts TEXT, period_start TEXT, period_end TEXT, expected REAL,
    scale REAL, tolerance REAL, status TEXT, found_value REAL,
    found_concept TEXT, found_form TEXT, found_filed TEXT, detail TEXT
);
"""

# Columns added to a table after a workspace may have made it, as (table, column). `connect` adds any that's missing.
ADDED_COLUMNS = (("note_figures", "detail"),)
URL = re.compile(r"https?://[^\s)>\"`\]]+")
# A file with no public address, such as a PDF from a data room or an email, named in a Sources entry as `file:deck.pdf`.
# Its bytes come from `drillcore import-file`, never from a fetch.
LOCAL = "file:"
FILE_ADDRESS = re.compile(r"(?<![\w/.:])file:[^\s)>\"`\]]+")
KEY_LINE = re.compile(r"^\s*-\s+\*{0,2}([A-Z]{1,2}\d{1,3}[a-z]?)\.\*{0,2}\s")
KEY_TOKEN = re.compile(r"(?<![\w.\-/])([A-Z]{1,2}\d{1,3}[a-z]?)(?![\w\-])")
SEC_FOLDER = re.compile(r"https://www\.sec\.gov/Archives/edgar/data/\d+/\d+/")
R_TOKEN = re.compile(r"(?<![\w])R(\d{1,3})(?:\.htm)?(?![\w])")
# A number not glued to a preceding ASCII letter or digit, so "S11", "Q3" and "F3300" are skipped, but allowed to
# carry a unit after it, as in "16.0B".
NUMBER = re.compile(r"(?<![A-Za-z0-9_.,])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![0-9]|[.,][0-9])")
# In a source a currency code can touch the number, as in "RMB107.49", so only a digit or separator before it rules a
# match out there.
DOC_NUMBER = re.compile(r"(?<![0-9.,])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![0-9]|[.,][0-9])")
UNIT = re.compile(r"^\s?(%|bn\b|billion\b|million\b|thousand\b|M\b|B\b|k\b)")
CJK = re.compile(r"[一-鿿]")
# The columns checks/xbrl_claims.csv must have.
CLAIM_COLUMNS = ("claim_id", "note_file", "description", "cik", "concepts", "period_start", "period_end", "expected", "scale",
                 "tolerance")
# Rows that say their figures were worked out rather than read from a source. They aren't looked for in one.
WORKED_OUT = ("COMPUTED", "INFERENCE", "derived", "Derived", "Arithmetic", "arithmetic", "implied", "Implied")
NOT_NOTES = re.compile(r"^#+\s*(Sources|Gaps and cautions)")
# Where a source's text breaks a line, however it writes the break. Python's own line splitting breaks at all of these,
# so each becomes a plain newline, and a line break is always one a reader sees.
LINE_BREAK = re.compile("\r\n?|[\v\f\x1c-\x1e\x85  ]")
# What a reader never sees in a source's text, but a terminal acts on or a reader's eye is misled by: control characters
# (an escape sequence can clear a screen, rewrite a line or set a clipboard), direction overrides and isolates, which
# show text in an order other than the one it's stored in, and invisible joiners and marks.
UNSEEN = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f؜​‎‏‪-‮⁠-⁤⁦-⁩﻿]")
# Encodings a page may name but a browser doesn't read it in. Each turns plain-looking bytes into other characters, so
# what this tool would read isn't what the page shows: UTF-7 makes `+ADw-` a `<`, and the escape codecs make `\x1b` an
# escape character.
UNREAD_ENCODINGS = frozenset({"utf-7", "unicode-escape", "raw-unicode-escape", "punycode", "idna"})
# An inline style that hides an element, and every element inside it, from a reader.
HIDDEN_STYLE = re.compile(r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*(?:hidden|collapse)"
                          r"|opacity\s*:\s*(?:0+(?:\.0*)?|\.0+)%?)\s*(?:!\s*important\s*)?(?:;|$)", re.I)


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(ws: Workspace) -> sqlite3.Connection:
    """The workspace's database, made if it isn't there, with the tables this module keeps."""
    (ws.data / "raw").mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ws.database_path)
    con.executescript(SCHEMA)
    for table, column in ADDED_COLUMNS:
        if column not in {row[1] for row in con.execute(f"PRAGMA table_info({table})")}:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
    return con


def clean_url(url: str) -> str:
    """A URL as it's fetched: no trailing punctuation or fragment, and the SEC's viewer address read as the file's."""
    url = url.rstrip(".,;:*").split("#")[0]
    url = url.replace("https://www.sec.gov/ix?doc=/", "https://www.sec.gov/")
    return url.replace("https://prodmod.sec.gov/", "https://www.sec.gov/")


# ---------------------------------------------------------------- the notes

def notes_folder(ws: Workspace) -> Path:
    """Where the workspace keeps its notes: `[notes] folder` in its settings, or research/."""
    return ws.root / ws.config().get("notes", {}).get("folder", "research")


def note_files(ws: Workspace) -> list[Path]:
    """The workspace's notes: every Markdown file in its notes folder, apart from any its settings say to skip."""
    folder = notes_folder(ws)
    skip = set(ws.config().get("notes", {}).get("skip", []))
    return sorted(p for p in folder.glob("*.md") if p.name not in skip) if folder.is_dir() else []


def note_body(path: Path) -> Iterator[tuple[int, str]]:
    """A note's body, as (line number, the line stripped): its headings, rows, bullets and prose, but no blank lines
    and nothing under a Sources or a Gaps and cautions heading. This is where a note cites its sources by key."""
    in_sources = False
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        row = line.strip()
        if row.startswith("#"):
            in_sources = bool(NOT_NOTES.match(row))
        if row and not in_sources:
            yield line_no, row


def cells(row: str) -> list[str]:
    """A table row's cells, each without the blanks around it."""
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def table_headers(text: str) -> dict[int, list[str]]:
    """For each table row in a note's text, by line number, the cells of its table's header."""
    lines = text.splitlines()
    headers: dict[int, list[str]] = {}
    header: list[str] = []
    for number, line in enumerate(lines, 1):
        row = line.strip()
        if not row.startswith("|"):
            header = []
            continue
        if number < len(lines) and re.fullmatch(r"\|[\s\-:|]+\|", lines[number].strip()):
            header = cells(row)
        headers[number] = header
    return headers


def record_sources(ws: Workspace, con: sqlite3.Connection) -> int:
    """Record every URL the notes cite. Returns the number of distinct URLs known afterwards."""
    con.execute("DELETE FROM sources WHERE origin IN ('cited', 'r_page')")
    insert = ("INSERT OR IGNORE INTO sources(note_file, source_key, url, origin, line_no, citation)"
              " VALUES (?,?,?,?,?,?)")
    for path in note_files(ws):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            web = [(m.start(), m.end(), clean_url(m.group(0))) for m in URL.finditer(line)]
            # A `file:` inside a web address, as in ?doc=file:annual.pdf, is part of that address, not a local file.
            local = [(m.start(), m.end(), clean_url(m.group(0))) for m in FILE_ADDRESS.finditer(line)
                     if not any(start <= m.start() < end for start, end, _ in web)]
            spans = sorted(web + local)
            if not spans:
                continue
            listed = KEY_LINE.match(line)
            key = listed.group(1) if listed else None
            citation = line.strip()[:1200]
            for _, _, url in spans:
                if not url.endswith("..."):
                    con.execute(insert, (path.name, key, url, "cited", number, citation))
            # A filing's XBRL note pages, written as "R18" or ".../R18.htm" after the filing's address.
            bases = [(m.start(), m.group(0)) for m in SEC_FOLDER.finditer(line)]
            if not (key and bases):
                continue
            for page in R_TOKEN.finditer(line):
                if any(start <= page.start() < end for start, end, _ in spans):
                    continue
                before = [base for position, base in bases if position < page.start()]
                base = before[-1] if before else bases[0][1]
                con.execute(insert, (path.name, key, f"{base}R{page.group(1)}.htm", "r_page", number, citation))
    con.commit()
    return int(con.execute("SELECT COUNT(DISTINCT url) FROM sources").fetchone()[0])


# ---------------------------------------------------------------- fetching

_last_hit: dict[str, float] = {}


def polite_wait(url: str) -> None:
    """Leave a gap between requests to one host."""
    host = urllib.parse.urlparse(url).netloc
    gap = 0.35 if host.endswith("sec.gov") else 1.5
    wait = _last_hit.get(host, 0) + gap - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.time()


def public_host(host: str) -> bool:
    """Whether every address a host name stands for is on the public internet: not this machine, not a private
    network, not a cloud's metadata service. A name that doesn't resolve is left for the fetch to fail on."""
    try:
        found = socket.getaddrinfo(host, None)
    except (OSError, UnicodeError):
        return True
    try:
        return all(ipaddress.ip_address(str(info[4][0]).split("%")[0]).is_global for info in found)
    except ValueError:
        return False


class Redirects(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only to another public web address, with the same pause before it as any request to its host.

    The address a note cites is the note's choice. Where it redirects is the site's, so a page can't send the fetch to a
    file transfer, to this machine, or into the network it runs on, and have what it finds there kept as the source."""

    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any,
                         newurl: str) -> urllib.request.Request | None:
        target = urllib.parse.urlparse(newurl)
        refusal = ("a redirect to something other than a web address" if target.scheme not in ("http", "https")
                   else "a redirect to an address that isn't on the public internet" if not public_host(target.hostname or "")
                   else None)
        if refusal:
            fp.close()
            raise urllib.error.URLError(f"refused {refusal}: {newurl[:200]}")
        polite_wait(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# Opens a web address. Its redirects are checked by `Redirects`.
OPENER = urllib.request.build_opener(Redirects)


def http_get(url: str) -> Response:
    """Fetch one web address. Anything but http and https is refused, so a note can't name a local file, and a redirect
    is followed only to another public web address."""
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        return None, "", url, b"", "not a web address"
    polite_wait(url)
    # The scheme was checked just above, and each redirect is checked by `Redirects`, so this can't open a local file.
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})  # noqa: S310
    try:
        with OPENER.open(request, timeout=TIMEOUT) as response:
            body = response.read(MAX_BYTES)
            return response.status, response.headers.get("Content-Type", ""), response.geturl(), body, None
    except urllib.error.HTTPError as refused:
        return refused.code, refused.headers.get("Content-Type", "") if refused.headers else "", url, b"", f"HTTP {refused.code}"
    except (OSError, ValueError) as failed:  # timeouts, DNS, TLS, resets, a malformed address
        return None, "", url, b"", f"{type(failed).__name__}: {failed}"


def guess_ext(content_type: str, body: bytes) -> str:
    kind = content_type.lower()
    if body[:5] == b"%PDF-" or "pdf" in kind:
        return ".pdf"
    if "json" in kind:
        return ".json"
    if "csv" in kind:
        return ".csv"
    if "html" in kind or body[:200].lstrip().lower().startswith((b"<!doctype", b"<html")):
        return ".html"
    if "xml" in kind:
        return ".xml"
    return ".txt" if kind.startswith("text/") else ".bin"


def save_raw(ws: Workspace, body: bytes, ext: str, sub: str = "raw") -> tuple[str, str]:
    """Keep a fetched body under the workspace's data folder, named by its hash. Returns the hash and the path from
    the workspace's root."""
    digest = hashlib.sha256(body).hexdigest()
    relative = Path("data") / sub / f"{digest[:20]}{ext}"
    full = ws.root / relative
    full.parent.mkdir(parents=True, exist_ok=True)
    if not full.exists():
        full.write_bytes(body)
    return digest, relative.as_posix()


def hides(attrs: list[tuple[str, str | None]]) -> bool:
    """Whether an element's own attributes hide it from a reader: the `hidden` attribute, or an inline style that
    doesn't display it, makes it invisible or makes it fully transparent. `hidden="until-found"` is shown when a reader
    searches the page, so it's read."""
    for name, value in attrs:
        if name == "hidden" and (value or "").strip().lower() != "until-found":
            return True
        if name == "style" and value and HIDDEN_STYLE.search(value):
            return True
    return False


class TextExtractor(HTMLParser):
    """A page's text as a reader sees it, with table cells kept apart. Scripts and styles are left out, and so is every
    element the page hides with an attribute or an inline style, with everything inside it: a page can't hold a figure
    or a quotation its reader never sees and have it count as what the page says. A style sheet's rules aren't read,
    so text a class hides is still read."""
    BLOCK = frozenset({"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "table", "ul",
                       "ol", "dd", "dt", "pre", "blockquote", "hr", "tr"})
    SKIP = frozenset({"script", "style", "noscript", "svg", "template"})
    # Elements that never hold anything, so never wait for an end tag.
    VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
                      "track", "wbr"})
    # Elements whose end tag a page may leave out: a new one of these, or of its kin, ends the one open.
    ENDS_SAME = {"p": {"p"}, "li": {"li"}, "dt": {"dt", "dd"}, "dd": {"dt", "dd"}, "tr": {"tr", "td", "th"},
                 "td": {"td", "th"}, "th": {"td", "th"}, "option": {"option"}}
    # What starts a block, and so ends a paragraph left open.
    ENDS_PARAGRAPH = frozenset({"address", "article", "aside", "blockquote", "div", "dl", "fieldset", "footer", "form",
                                "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "menu", "nav", "ol", "p", "pre",
                                "section", "table", "ul"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.title: list[str] = []
        self.skipping = 0
        self.in_title = False
        # The elements open now, innermost last, each with whether it hides what's in it; how many of each tag are
        # open, so an end tag for one that isn't is passed over at once; and how many open elements hide.
        self.open: list[tuple[str, bool]] = []
        self.open_count: dict[str, int] = {}
        self.hiding = 0

    def _push(self, tag: str, hidden: bool) -> None:
        self.open.append((tag, hidden))
        self.open_count[tag] = self.open_count.get(tag, 0) + 1
        self.hiding += hidden

    def _pop(self) -> None:
        tag, hidden = self.open.pop()
        self.open_count[tag] -= 1
        self.hiding -= hidden

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.in_title = self.in_title or tag == "title"
        if tag in self.SKIP:
            self.skipping += 1
        if tag not in self.VOID:
            ends = self.ENDS_SAME.get(tag, set())
            while self.open and (self.open[-1][0] in ends or (tag in self.ENDS_PARAGRAPH and self.open[-1][0] == "p")):
                self._pop()
            self._push(tag, hides(attrs))
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag in self.SKIP and self.skipping:
            self.skipping -= 1
        shown = not self.hiding
        if self.open_count.get(tag):
            while self.open[-1][0] != tag:
                self._pop()
            self._pop()
        if tag in ("td", "th") and shown:
            self.out.append(" | ")
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title.append(data)
        elif not self.skipping and not self.hiding:
            self.out.append(data)


def readable_encoding(name: str) -> bool:
    """Whether a page's named encoding is one to read it in: a text encoding Python knows, and not one of
    `UNREAD_ENCODINGS`, which a browser doesn't read a page in."""
    try:
        found = codecs.lookup(name)
    except LookupError:
        return False
    return getattr(found, "_is_text_encoding", True) and found.name not in UNREAD_ENCODINGS


def decode_bytes(body: bytes, content_type: str) -> str:
    """A body as text, by the encoding its headers or its own first lines name, then UTF-8, then Windows-1252. A named
    encoding that `readable_encoding` turns down is passed over."""
    named = re.search(r"charset=([\w\-]+)", content_type or "", re.I)
    candidates = [named.group(1)] if named else []
    meta = re.search(rb"<meta[^>]+charset=[\"']?([\w\-]+)", body[:4000], re.I)
    if meta:
        candidates.append(meta.group(1).decode("ascii", "ignore"))
    for encoding in [*(name for name in candidates if readable_encoding(name)), "utf-8", "cp1252"]:
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", "replace")


def unseen_removed(text: str) -> str:
    """Text with every line break made a newline and what `UNSEEN` matches taken out."""
    return UNSEEN.sub("", LINE_BREAK.sub("\n", text))


def shown(text: str) -> str:
    """Text from a source, or from anything else outside, made safe to print on one line: what a reader can't see is
    taken out, and line breaks and runs of blanks are one space. A terminal then shows it as text and acts on none of
    it."""
    return " ".join(unseen_removed(text).split())


def tidy(text: str) -> str:
    """A source's text as it's kept: what a reader can't see taken out, blanks evened out and empty lines dropped."""
    text = unseen_removed(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"( \| )+\n", "\n", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def email_text(body: bytes) -> tuple[str | None, str | None, str]:
    """A stored email's subject, and as its text its sender, date and subject lines over its plain body (or its HTML
    body's text when it has no plain one). Attachments aren't read."""
    message = email.message_from_bytes(body, policy=email.policy.default)
    assert isinstance(message, email.message.EmailMessage)
    head = [f"{name}: {message[name]}" for name in ("From", "To", "Date", "Subject") if message[name]]
    part = message.get_body(preferencelist=("plain", "html"))
    content = ""
    if isinstance(part, email.message.EmailMessage):
        try:
            content = str(part.get_content())
        except (LookupError, UnicodeError):
            # Mail clients write charsets Python doesn't know, such as unknown-8bit. Read the bytes as UTF-8 instead.
            raw = part.get_payload(decode=True)
            content = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw or "")
        if part.get_content_subtype() == "html":
            parser = TextExtractor()
            parser.feed(content)
            content = "".join(parser.out)
    subject = str(message["Subject"] or "")[:300] or None
    return subject, tidy("\n".join([*head, "", content])), "email"


# The ways this module reads text from a stored body itself, as the documents table records them. Any other is the method
# `import-text` was told the text was gathered by.
EXTRACTORS = ("html", "pdftotext", "text", "email", "json", "csv")
# The setting that has a JSON source read as text, as a message names it.
READ_JSON = "[sources] read_json"
JSON_NOT_LISTED = f"JSON, which is read as text only when the workspace lists its address under {READ_JSON}"
JSON_UNREADABLE = "not JSON that can be read"
# The mark some files start with to say how they're encoded. It isn't part of what the file says.
BOM = chr(0xFEFF)


class _Written(str):
    """A number in a JSON file, held as the characters the file writes it in."""
    __slots__ = ()


class _Members(list[tuple[str, Any]]):
    """A JSON object's members, in the file's order, as (name, value)."""
    __slots__ = ()


def _json_scalar(value: Any) -> str:
    return "true" if value is True else "false" if value is False else "null" if value is None else str(value)


def json_text(body: str) -> str | None:
    """A JSON file's values as lines of text, or None when it isn't JSON that can be read.

    Nothing is worked out and no value is changed. A number is written in the characters the file writes it in, long
    decimals and exponents included, never as Python would print it; a string is its own text; true, false and null are
    those words. Each line starts with where its values sit in the file, the names on the way down joined by dots:

        meta | symbol: NBR | currency: USD;
        prices | date: 2026-01-02 | close: 12.5;
        closes: 12.300000190734863;

    An object's plain values share one line, each after its own name, so a record stays together. Each plain value of
    a list has a line to itself. A place in a list has no number in the file, so none is written: text holds only
    figures the file holds. Every line ends with a semicolon, so a number ending one line is never read with a word
    starting the next, as "5" over a member named "million" would be."""
    try:
        data = json.loads(body.lstrip(BOM), parse_float=_Written, parse_int=_Written, parse_constant=_Written,
                          object_pairs_hook=_Members)
    except (ValueError, RecursionError):
        return None
    lines: list[str] = []
    todo: list[tuple[str, Any]] = [("", data)]
    while todo:
        path, node = todo.pop()
        if isinstance(node, list) and not node:
            lines.append((f"{path}: " if path else "") + ("{}" if isinstance(node, _Members) else "[]"))
        elif isinstance(node, _Members):
            cells = [f"{name}: {_json_scalar(value)}" for name, value in node if not isinstance(value, list)]
            if cells:
                lines.append(" | ".join([path, *cells] if path else cells))
            todo.extend(reversed([(f"{path}.{name}" if path else name, value) for name, value in node if isinstance(value, list)]))
        elif isinstance(node, list):
            todo.extend(reversed([(path, item) for item in node]))
        else:
            lines.append((f"{path}: " if path else "") + _json_scalar(node))
    return tidy("".join(f"{line};\n" for line in lines))


def csv_text(body: str) -> str:
    """A CSV file read as a table: each record a line, its cells joined by " | " as a table's are, so its heading row
    gives each column its period and label, and two figures in cells side by side ("551,572") are never read as one
    number. A cell is written as the file writes it, a thousands comma inside quotes kept; a bar inside a cell becomes a
    slash, so it can't split the cell. Commas, semicolons and tabs are each tried as what separates the cells."""
    body = body.lstrip(BOM)
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(body[:8192], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = csv.reader(io.StringIO(body), dialect)
    lines = [" | ".join(cell.strip().replace("|", "/") for cell in row) for row in rows if any(cell.strip() for cell in row)]
    return tidy("\n".join(lines))


def json_addresses(ws: Workspace) -> frozenset[str]:
    """The addresses whose JSON the workspace says to read as text: `[sources] read_json` in its settings, each a web
    address or a `file:` one, as a Sources entry writes it."""
    listed = ws.config().get("sources", {}).get("read_json", [])
    return frozenset(clean_url(str(address).strip()) for address in ([listed] if isinstance(listed, str) else listed))


@dataclass(frozen=True)
class Extracted:
    """What was read from a stored body: its title, its text (None when the kind isn't one this reads), how the text
    was read, and for a PDF, where each page starts and ends in the text and the number printed on it."""
    title: str | None
    text: str | None
    how: str
    pages: list[tuple[int, int, str]] | None = None


def extract(ws: Workspace, raw_path: str, ext: str, content_type: str, address: str = "") -> Extracted:
    """Read a stored body. A PDF's pages are read one by one, so a pinpoint such as `p.47` can be held to its page.

    `address` is the source's own, which decides whether a JSON body is read. A JSON address often stands for more than
    the file behind it: a note may give one address of a data service as the source of figures the service serves from
    many, and those are held by `claims`, against the structured facts. Read as text, that one file would be all its
    rows are judged by, and every figure from the others would fail. So JSON is read only when the workspace says the
    notes take their figures from that very file."""
    full = ws.root / raw_path
    if ext == ".pdf":
        program = shutil.which("pdftotext")
        if not program:
            return Extracted(None, None, "no pdftotext")
        try:
            done = subprocess.run([program, "-layout", "-enc", "UTF-8", str(full), "-"], capture_output=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as failed:
            return Extracted(None, None, f"pdftotext failed: {failed}")
        # pdftotext ends each page with a form feed.
        leaves = done.stdout.decode("utf-8", "replace").split("\f")
        if len(leaves) > 1 and not leaves[-1].strip():
            leaves.pop()
        text, spans = pages.joined([tidy(leaf) for leaf in leaves])
        return Extracted(None, text, "pdftotext", spans)
    body = full.read_bytes()
    if ext in (".html", ".xml"):
        parser = TextExtractor()
        parser.feed(decode_bytes(body, content_type))
        return Extracted(tidy(" ".join(parser.title))[:300] or None, tidy("".join(parser.out)), "html")
    if ext == ".csv" or (ext == ".txt" and "csv" in content_type.lower()):
        # A copy kept as plain text before CSV was read as a table is read as one by `fetch --reread`.
        return Extracted(None, csv_text(decode_bytes(body, content_type)), "csv")
    if ext == ".txt":
        return Extracted(None, tidy(decode_bytes(body, content_type)), "text")
    if ext == ".eml":
        return Extracted(*email_text(body))
    if ext == ".json":
        if address not in json_addresses(ws):
            return Extracted(None, None, JSON_NOT_LISTED)
        written = json_text(decode_bytes(body, content_type))
        return Extracted(None, None, JSON_UNREADABLE) if written is None else Extracted(None, written, "json")
    return Extracted(None, None, "not text")


def extract_text(ws: Workspace, raw_path: str, ext: str, content_type: str, address: str = "") -> tuple[str | None, str | None, str]:
    """A stored body's title, text and how the text was read. The text is None when the kind isn't one this reads."""
    read = extract(ws, raw_path, ext, content_type, address)
    return read.title, read.text, read.how


def keep_text(con: sqlite3.Connection, url: str, read: Extracted) -> None:
    """Store what was read from a document, with its pages."""
    assert read.text is not None
    con.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?)", (url, read.title, read.text, len(read.text), read.how))
    pages.record(con, url, read.pages)


def sec_archive(url: str) -> bool:
    """Whether an address is in the SEC's filing archive. Only an index there is read for the documents it lists: on
    any other host, an address that merely spells out "sec.gov/Archives" would choose what's added to a note's sources."""
    parts = urllib.parse.urlparse(url)
    return parts.scheme in ("http", "https") and parts.hostname == "www.sec.gov" and parts.path.startswith("/Archives/")


def filing_documents(index_html: str, index_url: str) -> list[str]:
    """The documents an EDGAR filing index page lists, apart from the index itself and the XBRL note pages."""
    folder = urllib.parse.urlparse(index_url.rsplit("/", 1)[0] + "/").path
    found: list[str] = []
    for href in re.findall(r'href="([^"]+)"', index_html):
        href = href.replace("/ix?doc=", "")
        name = href.rsplit("/", 1)[-1]
        if (href.startswith(folder) and name.lower().endswith((".htm", ".html")) and not name.endswith("-index.htm")
                and not re.fullmatch(r"R\d+\.htm", name) and f"https://www.sec.gov{href}" not in found):
            found.append(f"https://www.sec.gov{href}")
    return found[:12]


def fetch(ws: Workspace, con: sqlite3.Connection, retry_failed: bool = False,
          get: Callable[[str], Response] | None = None, say: Callable[[str], None] = print) -> dict[str, int]:
    """Download every recorded URL that hasn't been fetched, once each. A cited filing index also brings in the
    documents inside the filing. Returns how many were fetched, failed and skipped, and how many JSON sources were
    read from a copy already kept, or had their text dropped, when any were (see `sync_json`)."""
    get = get or http_get
    done = dict(con.execute("SELECT url, http_status FROM fetches").fetchall())
    queue = [row[0] for row in con.execute("SELECT DISTINCT url FROM sources ORDER BY id")]
    seen: set[str] = set()
    counts = {"ok": 0, "failed": 0, "skipped": 0}
    position = 0
    while position < len(queue):
        url = queue[position]
        position += 1
        if url in seen:
            continue
        seen.add(url)
        if url.startswith(LOCAL):
            # A local file has no address to fetch. Its bytes come from `import-file`.
            if not con.execute("SELECT 1 FROM local_files WHERE address=?", (url,)).fetchone():
                counts["local"] = counts.get("local", 0) + 1
                keys = ", ".join(sorted({key for (key,) in con.execute(
                    "SELECT source_key FROM sources WHERE url=? AND source_key IS NOT NULL", (url,))})) or "KEY"
                say(f"local   {url[:110]} (a file, not a web address: run `{identity.SLUG} import-file PATH --key {keys}`)")
            continue
        if url in done and (done[url] == 200 or not retry_failed):
            counts["skipped"] += 1
            continue
        status, content_type, final, body, error = get(url)
        digest = raw_path = None
        if status == 200 and body:
            ext = guess_ext(content_type, body)
            digest, raw_path = save_raw(ws, body, ext)
            read = extract(ws, raw_path, ext, content_type, url)
            if read.text is not None:
                keep_text(con, url, read)
            counts["ok"] += 1
            if url.endswith("-index.htm") and sec_archive(url) and sec_archive(final):
                cited_by = con.execute("SELECT note_file, source_key, line_no, citation FROM sources WHERE url=?", (url,)).fetchall()
                for document in filing_documents(decode_bytes(body, content_type), url):
                    for note_file, key, line_no, citation in cited_by:
                        con.execute("INSERT OR IGNORE INTO sources(note_file, source_key, url, origin, line_no, citation)"
                                    " VALUES (?,?,?,?,?,?)", (note_file, key, document, "filing_document", line_no, citation))
                    queue.append(document)
        else:
            counts["failed"] += 1
        con.execute("INSERT OR REPLACE INTO fetches VALUES (?,?,?,?,?,?,?,?,?)",
                    (url, final, status, content_type, len(body), digest, raw_path, now(), error))
        con.commit()
        if status == 200 and body:
            say(f"fetched {shown(url[:110])} ({len(body):,} bytes)")
        else:
            say(f"failed  {shown(url[:110])} ({shown(error or f'HTTP {status} with an empty body')})")
    # A JSON source listed to be read after it was fetched is read from the copy kept, and one taken off the list
    # loses the text read from it. Nothing is fetched for either.
    counts.update({f"json_{what}": count for what, count in sync_json(ws, con).items() if count})
    return counts


def reread(ws: Workspace, con: sqlite3.Connection) -> dict[str, int]:
    """Read the text again from the raw copy of every page fetched, as this version reads a page, without fetching
    anything. A page whose copy is missing, or whose text can't be read now (a PDF with no pdftotext on the path), keeps
    the text it has. JSON is read as `[sources] read_json` now lists it: the text read from the JSON of an address no
    longer listed is dropped (plain `fetch` does as much for JSON alone, see `sync_json`).

    Text gathered by hand and loaded by `import_text` is kept too, whatever its address's copy would read as now. It's
    there because the copy doesn't hold what the page shows its reader: a page laid out by a script keeps its words
    where this reads none, and a site that doesn't trust a client sends something else in the page's place. Only a JSON
    address the workspace now lists is read in its place, as `sync_json` reads it.

    Returns how many were read and how many kept, with how many of those kept were gathered by hand and how many were
    dropped, when any were."""
    raw = (ws.data / "raw").resolve()
    listed = json_addresses(ws)
    by_hand = {url for url, how in con.execute("SELECT url, extractor FROM documents") if how is not None and how not in EXTRACTORS}
    counts = {"read": 0, "kept": 0}
    for url, content_type, raw_path in con.execute(
            "SELECT url, content_type, raw_path FROM fetches WHERE http_status = 200 AND raw_path IS NOT NULL ORDER BY url").fetchall():
        if url in by_hand and url not in listed:
            counts["kept"] += 1
            counts["by_hand"] = counts.get("by_hand", 0) + 1
            continue
        full = (ws.root / raw_path).resolve()
        read = Extracted(None, None, "")
        if full.is_relative_to(raw) and full.is_file():
            read = extract(ws, raw_path, Path(raw_path).suffix, content_type or "", url)
        if read.text is None:
            if url not in listed and con.execute("DELETE FROM documents WHERE url=? AND extractor='json'", (url,)).rowcount:
                counts["dropped"] = counts.get("dropped", 0) + 1
            else:
                counts["kept"] += 1
            continue
        keep_text(con, url, read)
        counts["read"] += 1
    con.commit()
    # An imported file isn't in the pass above. Its JSON is read, or dropped, as the setting says.
    synced = sync_json(ws, con)
    counts["read"] += synced["read"]
    if synced["dropped"]:
        counts["dropped"] = counts.get("dropped", 0) + synced["dropped"]
    return counts


# The answers by which a site refuses a client, as against failing some other way.
REFUSED = (401, 403, 429, 451)


def gathered_note(status: int | None, method: str, captured_at: str) -> str | None:
    """What a fetch's record says once the address's text has been loaded by `import_text`: what the fetch itself came
    to, then how and when the text was gathered. None for a fetch that succeeded: nothing went wrong with it, and the
    text's own record says how the text was had."""
    if status == 200:
        return None
    outcome = ("refused the automated fetch" if status in REFUSED else
               f"the fetch failed (HTTP {status})" if status else "the fetch failed")
    return f"{outcome}; text gathered {method}" + (f" at {captured_at}" if captured_at else "")


def import_text(ws: Workspace, con: sqlite3.Connection) -> int:
    """Load page text gathered another way than by this tool's reading of a fetch, from data/raw/browser_capture.jsonl:
    one JSON object a line, with url, title, text, captured_at and method. It's for a site that refuses automated
    clients, and equally for an address that fetched but whose copy holds no text this reads.

    The fetch's own record is kept true. A refusal is noted as one, another failure as that failure, and a fetch that
    succeeded as nothing at all: its record carries no note of anything going wrong, and loses one an earlier version
    left there."""
    path = ws.data / "raw" / "browser_capture.jsonl"
    loaded = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        url, text, method = clean_url(record["url"]), tidy(record["text"]), record.get("method", "by hand")
        keep_text(con, url, Extracted(record.get("title"), text, method))
        fetched = con.execute("SELECT http_status FROM fetches WHERE url=?", (url,)).fetchone()
        if fetched:
            con.execute("UPDATE fetches SET error=? WHERE url=?", (gathered_note(fetched[0], method, record.get("captured_at", "")), url))
        loaded += 1
    con.commit()
    return loaded


def sync_json(ws: Workspace, con: sqlite3.Connection) -> dict[str, int]:
    """Bring the JSON held as text into line with `[sources] read_json`, from the copies kept and without fetching.
    Each listed address whose copy is stored but not yet read as JSON is read, a fetched one and an imported file
    alike, in place of any text gathered for it by hand; and the text read from the JSON of an address no longer listed
    is dropped, so the setting says what's read. No other source's text is touched. Returns how many were read and
    how many dropped."""
    listed = json_addresses(ws)
    counts = {"read": 0, "dropped": 0}
    for (url,) in con.execute("SELECT url FROM documents WHERE extractor='json' ORDER BY url").fetchall():
        if url not in listed:
            con.execute("DELETE FROM documents WHERE url=?", (url,))
            counts["dropped"] += 1
    raw = (ws.data / "raw").resolve()
    for address in sorted(listed):
        stored = con.execute("SELECT content_type, raw_path FROM fetches WHERE url=?", (address,)).fetchone()
        if not (stored and stored[1] and stored[1].endswith(".json")):
            continue
        full = (ws.root / stored[1]).resolve()
        if con.execute("SELECT 1 FROM documents WHERE url=? AND extractor='json'", (address,)).fetchone() or not (
                full.is_relative_to(raw) and full.is_file()):
            continue
        read = extract(ws, stored[1], ".json", stored[0] or "", address)
        if read.text is None:
            continue
        named = con.execute("SELECT file_name FROM local_files WHERE address=?", (address,)).fetchone()
        keep_text(con, address, Extracted(named[0] if named else read.title, read.text, read.how))
        counts["read"] += 1
    con.commit()
    return counts


def listed_json(ws: Workspace, con: sqlite3.Connection) -> dict[str, str]:
    """How each address under `[sources] read_json` stands, so a mistyped one isn't a setting that quietly does
    nothing: "read" when its JSON is held as text; "unread" when a copy is stored as JSON but no text is read from it,
    which after a `fetch` means it isn't JSON that can be read; "not_json" when what's stored isn't JSON; "uncited"
    when no note gives the address; and "pending" when a note does but nothing is stored for it yet."""
    found: dict[str, str] = {}
    for address in sorted(json_addresses(ws)):
        stored = con.execute("SELECT raw_path FROM fetches WHERE url=?", (address,)).fetchone()
        if not (stored and stored[0]):
            cited = con.execute("SELECT 1 FROM sources WHERE url=?", (address,)).fetchone()
            found[address] = "pending" if cited else "uncited"
        elif not stored[0].endswith(".json"):
            found[address] = "not_json"
        else:
            read = con.execute("SELECT 1 FROM documents WHERE url=? AND extractor='json'", (address,)).fetchone()
            found[address] = "read" if read else "unread"
    return found


# The kind of text each local file is read as, by its suffix. Anything else is told apart by its first bytes, as a
# fetched body is, and kept without text when it isn't one of these.
LOCAL_KINDS = {".pdf": ".pdf", ".htm": ".html", ".html": ".html", ".xml": ".xml", ".txt": ".txt", ".md": ".txt",
               ".csv": ".csv", ".eml": ".eml", ".json": ".json"}


@dataclass(frozen=True)
class Imported:
    """What `import_file` did: the address the file is held under, the notes and key it was filed under, and how much
    text was read from it (None when none could be)."""
    address: str
    notes: tuple[str, ...]
    key: str
    text_chars: int | None
    how: str
    # Whether a Sources entry already named the file, or it was filed under the key by this import alone.
    named: bool


class NotImported(ValueError):
    """A local file can't be imported as asked. The message says why and what to do."""


def local_address(ws: Workspace, con: sqlite3.Connection, path: Path, key: str, note: str = "") -> tuple[str, list[str], bool]:
    """Where an imported file belongs: the `file:` address a Sources entry gives the key, with the notes whose entry it
    is, or when no entry names a file, `file:` and the file's name, filed under the key in the one note that can take
    it (`import_file` then adds part of the file's hash, so two files of one name stay apart). The third value says
    whether an entry named it. Raises NotImported when that's ambiguous."""
    record_sources(ws, con)
    names = [p.name for p in note_files(ws)]
    if note and note not in names:
        raise NotImported(f"There's no note called {note} in {notes_folder(ws)}.")
    rows = con.execute("SELECT DISTINCT url, note_file FROM sources WHERE source_key=? AND url LIKE 'file:%' AND origin='cited'"
                       " ORDER BY note_file", (key,)).fetchall()
    rows = [(url, name) for url, name in rows if not note or name == note]
    addresses = sorted({url for url, _ in rows})
    if len(addresses) > 1:
        raise NotImported(f"{key} names more than one file ({', '.join(addresses)}). Say which note's with --note.")
    if addresses:
        return addresses[0], [name for _, name in rows], True
    folder = notes_folder(ws)
    defining = [name for name in names if any(
        (listed := KEY_LINE.match(line)) and listed.group(1) == key
        for line in (folder / name).read_text(encoding="utf-8").splitlines())]
    chosen = note or (defining[0] if len(defining) == 1 else names[0] if len(names) == 1 else "")
    if not chosen:
        raise NotImported(f"No Sources entry names a file for {key}, and it isn't clear which note it belongs to. "
                          "Say which with --note, or write the file's address in the entry, as `file:"
                          f"{path.name.replace(' ', '_')}`.")
    return LOCAL + path.name.replace(" ", "_"), [chosen], False


def import_file(ws: Workspace, con: sqlite3.Connection, path: Path, key: str, note: str = "") -> Imported:
    """Store a local file as the source behind a key: its bytes kept by their hash under data/raw/, its text read as a
    fetched file's would be, and where it came from recorded. The file is read, never run. Raises NotImported for a
    file that isn't there or is too large, or a key that doesn't say where it belongs."""
    if not path.is_file():
        raise NotImported(f"There's no file at {path}.")
    if path.stat().st_size > MAX_BYTES:
        raise NotImported(f"{path} is larger than the {MAX_BYTES // (1024 * 1024)} MB a source may be.")
    address, notes, named = local_address(ws, con, path, key, note)
    body = path.read_bytes()
    ext = LOCAL_KINDS.get(path.suffix.lower()) or guess_ext("", body)
    digest, raw_path = save_raw(ws, body, ext)
    if not named:
        # Two data rooms can each hold a deck.pdf, so an address no entry wrote carries part of the file's hash, and
        # the key's earlier file is let go: a key imported again stands on the new file alone.
        stem, dot, suffix = address.rpartition(".")
        address = f"{stem}-{digest[:8]}.{suffix}" if dot and "/" not in suffix else f"{address}-{digest[:8]}"
    # Read once the address is settled: it decides whether a JSON file is read.
    read = extract(ws, raw_path, ext, "", address)
    if not named:
        for name in notes:
            con.execute("DELETE FROM sources WHERE note_file=? AND source_key=? AND origin='imported'", (name, key))
            con.execute("INSERT OR IGNORE INTO sources(note_file, source_key, url, origin, line_no, citation) VALUES (?,?,?,?,?,?)",
                        (name, key, address, "imported", None, f"imported from {path.name}"))
    con.execute("INSERT OR REPLACE INTO local_files VALUES (?,?,?,?,?,?,?)",
                (address, path.name, str(path.resolve()), digest, raw_path, len(body), now()))
    con.execute("INSERT OR REPLACE INTO fetches VALUES (?,?,?,?,?,?,?,?,?)",
                (address, address, None, f"local file ({ext.lstrip('.')})", len(body), digest, raw_path, now(), None))
    con.execute("DELETE FROM documents WHERE url=?", (address,))
    pages.record(con, address, None)
    if read.text is not None:
        # A PDF from a data room keeps its pages, so a pinpoint such as `S7 p.12` can be held to one.
        keep_text(con, address, Extracted(read.title or path.name, read.text, read.how, read.pages))
    con.commit()
    return Imported(address, tuple(notes), key, None if read.text is None else len(read.text), read.how, named)


# ---------------------------------------------------------------- SEC structured data

def companies(ws: Workspace) -> list[tuple[int, str]]:
    """The companies whose SEC data the workspace asks for, as (CIK, name), from `[[sec.company]]` in its settings."""
    return [(int(entry["cik"]), str(entry.get("name", ""))) for entry in ws.config().get("sec", {}).get("company", [])]


def load_sec(ws: Workspace, con: sqlite3.Connection, get: Callable[[str], Response] | None = None,
             say: Callable[[str], None] = print) -> int:
    """Load each company's tagged facts and its list of filings from the SEC's data service. Returns how many of those
    requests failed."""
    get = get or http_get
    failed = 0
    for cik, name in companies(ws):
        con.execute("INSERT OR IGNORE INTO companies(cik, name) VALUES (?,?)", (cik, name))
        status, _, _, body, error = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
        if status == 200:
            save_raw(ws, body, ".json", sub="raw/xbrl")
            data = json.loads(body)
            entity = data.get("entityName", name)
            con.execute("DELETE FROM xbrl_facts WHERE cik=?", (cik,))
            rows = [(cik, entity, taxonomy, concept, info.get("label"), unit, fact.get("start"), fact.get("end"),
                     fact.get("val"), fact.get("fy"), fact.get("fp"), fact.get("form"), fact.get("filed"),
                     fact.get("accn"), fact.get("frame"))
                    for taxonomy, concepts in data.get("facts", {}).items()
                    for concept, info in concepts.items()
                    for unit, facts in info.get("units", {}).items()
                    for fact in facts]
            con.executemany("INSERT INTO xbrl_facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            con.execute("UPDATE companies SET facts_loaded=?, name=? WHERE cik=?", (len(rows), entity, cik))
            say(f"facts   {shown(entity)[:34]:<34} {len(rows):>7} rows")
        else:
            con.execute("UPDATE companies SET note=? WHERE cik=?", (f"companyfacts: {error or status}", cik))
            say(f"facts   {shown(name)[:34]:<34} FAILED {shown(str(error or status))}")
            failed += 1
        status, _, _, body, error = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
        if status != 200:
            say(f"filings {shown(name)[:34]:<34} FAILED {shown(str(error or status))}")
            failed += 1
            con.commit()
            continue
        save_raw(ws, body, ".json", sub="raw/xbrl")
        data = json.loads(body)
        entity = data.get("name", name)
        blocks = [data.get("filings", {}).get("recent", {})]
        for extra in data.get("filings", {}).get("files", []):
            more_status, _, _, more_body, _ = get("https://data.sec.gov/submissions/" + extra["name"])
            if more_status == 200:
                blocks.append(json.loads(more_body))
        loaded = 0
        for block in blocks:
            accessions = block.get("accessionNumber", [])
            blank = [""] * len(accessions)
            for i, accession in enumerate(accessions):
                document = block["primaryDocument"][i]
                folder = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/"
                con.execute("INSERT OR REPLACE INTO filings VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (cik, entity, accession, block["form"][i], block["filingDate"][i], block["reportDate"][i],
                             document, block.get("primaryDocDescription", blank)[i], block.get("items", blank)[i],
                             folder + document if document else folder))
                loaded += 1
        con.execute("UPDATE companies SET filings_loaded=? WHERE cik=?", (loaded, cik))
        con.commit()
        say(f"filings {shown(entity)[:34]:<34} {loaded:>7} rows")
    return failed


# ---------------------------------------------------------------- figures against their cited source

def figures_at(text: str) -> Iterator[tuple[int, int, str, float, int, str]]:
    """The figures in a row worth looking for, as (start, end, as written, value, decimal places, unit). Years, and
    whole numbers under 100 written without a comma, are left out: they're dates, counts and section numbers far more
    often than measurements. Web addresses are blanked first, so the places are the row's own."""
    text = measures.blank(text, URL)
    for match in NUMBER.finditer(text):
        raw = match.group(1)
        unit = UNIT.match(text[match.end():match.end() + 10])
        plain = raw.replace(",", "")
        value = float(plain)
        decimals = len(plain.split(".")[1]) if "." in plain else 0
        if decimals == 0 and "," not in raw and (value < 100 or 1900 <= value <= 2100):
            continue
        yield match.start(1), match.end(1), raw, value, decimals, unit.group(1) if unit else ""


def numbers_in(text: str) -> Iterator[tuple[str, float, int, str]]:
    """The figures in a row worth looking for, as (as written, value, decimal places, unit)."""
    for _, _, raw, value, decimals, unit in figures_at(text):
        yield raw, value, decimals, unit


def doc_numbers(text: str) -> list[float]:
    """Every number a source's text holds, in order of size."""
    return sorted({float(match.group(1).replace(",", "")) for match in DOC_NUMBER.finditer(text)})


def find_number(sorted_values: list[float], value: float, decimals: int, cjk: bool = False) -> tuple[str | None, float | None]:
    """How a source holds a figure, and the number that matched: "exact", at another scale (thousands, millions,
    billions), or "rounded" when the source writes it with more decimal places. Pages in Chinese count in ten-thousands
    and hundred-millions, so for those a shift of ten or a hundred is tried as well. (None, None) when it's absent."""
    tolerance = 0.5 * 10 ** (-decimals) + 1e-9
    scales = [("exact", 1.0), ("x1000", 1e3), ("x1e6", 1e6), ("x1e9", 1e9), ("/1000", 1e-3)]
    if cjk:
        scales += [("cjk x10", 10.0), ("cjk x100", 100.0), ("cjk /10", 0.1), ("cjk /100", 0.01), ("cjk x1e4", 1e4)]
    scales.append(("rounded", 1.0))
    for kind, scale in scales:
        low, high = (value - tolerance) * scale, (value + tolerance) * scale
        if kind == "exact":
            low, high = value - 1e-9, value + 1e-9
        at = bisect.bisect_left(sorted_values, low)
        if at < len(sorted_values) and sorted_values[at] <= high:
            return kind, sorted_values[at]
    return None, None


def keys_by_note(con: sqlite3.Connection, names: list[str], borrows: dict[str, str]) -> dict[str, dict[str, list[str]]]:
    """For each note, the URLs behind each source key it can use: its own, and for a key it doesn't define, those of
    the one note its workspace says it borrows from. Two notes may both have an S1, so nothing is guessed: without
    that setting a key the note doesn't define is no key at all."""
    own: dict[str, dict[str, list[str]]] = {name: {} for name in names}
    for note_file, key, url in con.execute("SELECT note_file, source_key, url FROM sources WHERE source_key IS NOT NULL ORDER BY id"):
        own.setdefault(note_file, {}).setdefault(key, []).append(url)
    return {name: {**own.get(borrows.get(name, ""), {}), **own[name]} for name in names}


def without_keys(row: str, known: dict[str, list[str]]) -> str:
    """A row with its source keys and their pinpoints blanked out, so the digits in "S11" or "S1 p.147" aren't read as
    a figure."""
    return KEY_TOKEN.sub(lambda match: " " if match.group(1) in known else match.group(0), pages.without_pins(row, known))


SOURCES_HEADING = re.compile(r"^#+\s*Sources")


@dataclass(frozen=True)
class NoteLine:
    """One line of a note, read the way every check reads it."""
    note: str
    line_no: int
    # The line without its surrounding blanks.
    text: str
    # "heading", "prose", or "row" for a table row or a bullet. Blank lines and a table's divider aren't given.
    kind: str
    # "notes", or "sources" and "gaps" under a Sources or a Gaps and cautions heading.
    section: str
    # The keys the line cites: its own, or when it names none, those its heading or the prose above it named.
    keys: tuple[str, ...]
    # "row" when the keys are the line's own, "section" when they're inherited.
    basis: str
    # Whether the line, its heading or the prose leading into it says its figures were worked out.
    worked_out: bool
    # The page or section each key is cited at, where the line, or the heading or prose its keys come from, gives one.
    pins: tuple[pages.Pin, ...] = ()
    # The heading the line sits under.
    heading: str = ""


def note_lines(ws: Workspace, con: sqlite3.Connection) -> Iterator[NoteLine]:
    """Every line of every note that holds anything, with the keys it cites. A key counts only when the note, or the
    one note it borrows from, defines it."""
    paths = note_files(ws)
    usable = keys_by_note(con, [path.name for path in paths], ws.config().get("notes", {}).get("borrows", {}))
    for path in paths:
        urls_by_key = usable[path.name]
        section_keys: list[str] = []
        section_pins: dict[str, pages.Pin] = {}
        heading = ""
        section = "notes"
        heading_worked_out = prose_worked_out = False
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            row = line.strip()
            row_keys = [key for key in KEY_TOKEN.findall(row) if key in urls_by_key]
            row_pins = pages.pins_in(row, urls_by_key)
            if row.startswith("#"):
                section = "sources" if SOURCES_HEADING.match(row) else "gaps" if NOT_NOTES.match(row) else "notes"
                section_keys, section_pins, heading = row_keys, row_pins, row
                heading_worked_out, prose_worked_out = any(word in row for word in WORKED_OUT), False
                yield NoteLine(path.name, line_no, row, "heading", section, tuple(row_keys), "row", heading_worked_out,
                               tuple(row_pins.values()), row)
                continue
            if not row or re.fullmatch(r"\|[\s\-:|]+\|", row):
                continue
            kind = "row" if row.startswith(("|", "- ")) else "prose"
            if kind == "prose":
                # Prose under a heading can name the sources for the rows below it, or say they're arithmetic.
                prose_worked_out = any(word in row for word in WORKED_OUT)
                section_keys += [key for key in row_keys if key not in section_keys]
                section_pins = {**row_pins, **section_pins}
            keys, basis = (row_keys, "row") if row_keys else (section_keys, "section")
            pins = row_pins if row_keys else section_pins
            worked_out = heading_worked_out or prose_worked_out or any(word in row for word in WORKED_OUT)
            yield NoteLine(path.name, line_no, row, kind, section, tuple(keys), basis, worked_out,
                           tuple(pin for key, pin in pins.items() if key in keys), heading)


class Held:
    """What the database holds of each source's text, read once: the text, the numbers in it, where each number
    stands, and whether the page is in Chinese."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con
        self._text: dict[str, str | None] = {}
        self._numbers: dict[str, list[float]] = {}
        self._places: dict[str, dict[float, list[tuple[int, int]]]] = {}

    def text(self, url: str) -> str | None:
        if url not in self._text:
            row = self.con.execute("SELECT text FROM documents WHERE url=?", (url,)).fetchone()
            self._text[url] = row[0] if row and row[0] else None
        return self._text[url]

    def numbers(self, url: str) -> list[float]:
        if url not in self._numbers:
            self._numbers[url] = doc_numbers(self.text(url) or "")
        return self._numbers[url]

    def chinese(self, url: str) -> bool:
        return len(CJK.findall((self.text(url) or "")[:20000])) > 50

    def places(self, url: str, value: float) -> list[tuple[int, int]]:
        """Where a source's text writes a number."""
        if url not in self._places:
            found: dict[float, list[tuple[int, int]]] = {}
            for match in DOC_NUMBER.finditer(self.text(url) or ""):
                found.setdefault(float(match.group(1).replace(",", "")), []).append(match.span(1))
            self._places[url] = found
        return self._places[url].get(value, [])


@dataclass(frozen=True)
class Located:
    """How a figure the cited sources hold was found: the status, how it matched, where, and why, if it's not plainly
    found."""
    status: str
    match_kind: str | None = None
    url: str | None = None
    number: float | None = None
    detail: str = ""


# How many places in a source the label and period around a figure are read at. A figure a long filing writes more
# often than this is common enough that where it stands says little.
MOST_PLACES = 60


def locate(held: Held, con: sqlite3.Connection, urls: list[str], value: float, decimals: int,
           pins: dict[str, pages.Pin], note: measures.Context) -> Located:
    """Where the cited sources hold a figure, held to the page or section a pinpoint names and to the label and period
    the note gives it. A figure found only away from its pinpoint is `not_on_cited_page` or `not_in_cited_section`;
    found only beside another period or line, `beside_another_period` or `beside_another_label`."""
    hits: list[tuple[str, float, str, list[tuple[int, int]]]] = []  # kind, number, url, places
    missed_pin: tuple[str, pages.Pin, str] | None = None
    unread_pin = ""
    for url in urls:
        kind, matched = find_number(held.numbers(url), value, decimals, held.chinese(url))
        if not kind or matched is None:
            continue
        places = held.places(url, matched)
        pin = pins.get(url)
        if pin:
            stretches, why = pages.region(con, url, held.text(url) or "", pin)
            if stretches is None:
                unread_pin = f"{pin.shown()} not judged: {why}"
            else:
                there = pages.region_text(held.text(url) or "", stretches)
                kind, matched = find_number(doc_numbers(there), value, decimals, held.chinese(url))
                if not kind or matched is None:
                    missed_pin = missed_pin or (url, pin, why)
                    continue
                places = [place for place in held.places(url, matched) if pages.within(stretches, place[0])]
        hits.append((kind, matched, url, places))
    if not hits:
        if missed_pin:
            url, pin, why = missed_pin
            return Located(pages.status_for(pin), None, url, None,
                           f"in the source, but not at {pin.where}" + (f": {why}" if why else ""))
        return Located("not_found")
    hits.sort(key=lambda hit: hit[0] != "exact")
    kind, matched, url, _ = hits[0]
    if measures.unreadable(note):
        return Located("found", kind, url, matched, unread_pin)
    around = [measures.source_context(held.text(where) or "", start, end)
              for _, _, where, places in hits for start, end in places[:MOST_PLACES]]
    outcome, why = measures.verdict(note, around)
    status = {measures.OTHER_PERIOD: "beside_another_period", measures.OTHER_LABEL: "beside_another_label"}.get(outcome, "found")
    return Located(status, kind, url, matched, why or unread_pin)


# What `figures` reports in data/figures_not_found.csv: everything but a figure plainly found, or one worked out.
UNCONFIRMED = ("not_found", "source_text_unavailable", "no_source_key", "not_on_cited_page", "not_in_cited_section",
               "beside_another_period", "beside_another_label")


def check_figures(ws: Workspace, con: sqlite3.Connection) -> dict[tuple[str, str], int]:
    """Look for each figure in the notes in the text of the source its row cites, at the page or section the row's
    pinpoint names, and read what stands around it there. Writes the note_figures table and
    data/figures_not_found.csv, and returns the count for each (note, status)."""
    from .arithmetic import without_conversions  # Here: arithmetic reads the notes with this module's own tools.

    con.execute("DELETE FROM note_figures")
    held = Held(con)
    paths = note_files(ws)
    usable = keys_by_note(con, [path.name for path in paths], ws.config().get("notes", {}).get("borrows", {}))
    headers = {path.name: table_headers(path.read_text(encoding="utf-8")) for path in paths}
    for line in note_lines(ws, con):
        if line.kind != "row" or line.section != "notes":
            continue
        urls_by_key = usable[line.note]
        # A figure a conversion with its rate gives, $76.0M (RMB 551.1M at 7.25), is in no source: `arithmetic` checks it,
        # and here, as in `check`, only the amount and the rate are looked for. Blanking keeps the line's length, so the
        # places read below are the row's own.
        body = without_conversions(without_keys(line.text, urls_by_key))
        have = [url for key in line.keys for url in urls_by_key.get(key, []) if held.text(url) is not None]
        pins = {url: pin for pin in line.pins for url in urls_by_key.get(pin.key, [])}
        for start, end, raw, value, decimals, unit in figures_at(body):
            if line.worked_out:
                found = Located("computed_not_checked")
            elif not line.keys:
                found = Located("no_source_key")
            elif not have:
                found = Located("source_text_unavailable")
            else:
                note = measures.note_context(body, start, end, headers[line.note].get(line.line_no, []), line.heading)
                found = locate(held, con, have, value, decimals, pins, note)
            con.execute(
                "INSERT INTO note_figures(note_file, line_no, source_keys, key_basis, number_text, value, decimals,"
                " unit, row_kind, row_text, status, match_kind, matched_url, matched_number, detail)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (line.note, line.line_no, ",".join(line.keys), line.basis, raw, value, decimals, unit,
                 "computed" if line.worked_out else "sourced", line.text[:600], found.status, found.match_kind,
                 found.url, None if found.number is None else repr(found.number), found.detail))
    con.commit()
    marks = ",".join("?" * len(UNCONFIRMED))
    with (ws.data / "figures_not_found.csv").open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["note_file", "line_no", "source_keys", "key_basis", "number_text", "unit", "status", "row_text", "detail"])
        writer.writerows(con.execute(
            # Only question marks are put into the statement. Every value is bound.
            "SELECT note_file, line_no, source_keys, key_basis, number_text, unit, status, row_text, detail FROM note_figures"  # noqa: S608
            f" WHERE status IN ({marks}) ORDER BY note_file, line_no", UNCONFIRMED))
    return {(note, status): count for note, status, count in
            con.execute("SELECT note_file, status, COUNT(*) FROM note_figures GROUP BY 1, 2 ORDER BY 1, 2")}


# ---------------------------------------------------------------- headline figures against SEC facts

def check_claims(ws: Workspace, con: sqlite3.Connection) -> dict[str, int]:
    """Compare each row of checks/xbrl_claims.csv with the fact a company tagged for that concept and period. A row
    names the company's CIK, one or more concepts separated by "|", the period, the expected value, the scale the
    value is written in, and how far off still counts. Returns the count for each status. Raises ValueError, naming
    the line, for a row it can't read."""
    path = ws.root / "checks" / "xbrl_claims.csv"
    con.execute("DELETE FROM xbrl_claims")
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        missing = [column for column in CLAIM_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path} has no {', '.join(missing)} column. Its first line must name: {', '.join(CLAIM_COLUMNS)}.")
        rows = [(reader.line_num, row) for row in reader if row.get("claim_id") and not row["claim_id"].startswith("#")]
    for line_no, row in rows:
        try:
            cik = int(row["cik"])
            expected, scale, tolerance = float(row["expected"]), float(row["scale"] or 1), float(row["tolerance"] or 0.05)
            if scale == 0:
                raise ValueError("a scale of 0")
        except (TypeError, ValueError):
            raise ValueError(f"{path}:{line_no}: claim {row['claim_id']!r} needs a whole-number cik, a number for expected and "
                             f"tolerance, and a scale that isn't 0; it has cik {row['cik']!r}, expected {row['expected']!r}, "
                             f"scale {row['scale']!r} and tolerance {row['tolerance']!r}.") from None
        concepts = [concept.strip() for concept in (row["concepts"] or "").split("|") if concept.strip()]
        start, end = (row["period_start"] or "").strip(), (row["period_end"] or "").strip()
        marks = ",".join("?" * len(concepts))
        period = "period_start=?" if start else "period_start IS NULL"
        # Only question marks and one of two fixed conditions are put into the statement. Every value is bound.
        facts = con.execute(
            f"SELECT concept, value, form, filed FROM xbrl_facts WHERE cik=? AND concept IN ({marks}) AND period_end=?"  # noqa: S608
            f" AND {period} ORDER BY filed", [cik, *concepts, end, *([start] if start else [])]).fetchall()
        status, found, concept, form, filed, detail = "no_fact", None, None, None, None, ""
        if facts:
            matching = [fact for fact in facts if abs(fact[1] / scale - expected) <= tolerance]
            concept, value, form, filed = (matching or facts)[0]
            found, status = value / scale, "match" if matching else "MISMATCH"
            values = sorted({fact[1] for fact in facts})
            if len(values) > 1:
                detail = "values reported for this period: " + ", ".join(f"{v / scale:g}" for v in values)
        con.execute("INSERT INTO xbrl_claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (row["claim_id"], row["note_file"], row["description"], cik, row["concepts"], start, end,
                     expected, scale, tolerance, status, found, concept, form, filed, detail))
    con.commit()
    return dict(con.execute("SELECT status, COUNT(*) FROM xbrl_claims GROUP BY 1 ORDER BY 1").fetchall())


# ---------------------------------------------------------------- search

def build_index(con: sqlite3.Connection) -> tuple[int, int]:
    """Build the full-text index over the stored text. Returns the number of documents and their characters."""
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5("
                "url UNINDEXED, title, text, content='documents', content_rowid='rowid')")
    con.execute("INSERT INTO documents_fts(documents_fts) VALUES ('rebuild')")
    con.commit()
    documents, characters = con.execute("SELECT COUNT(*), COALESCE(SUM(text_chars), 0) FROM documents").fetchone()
    return int(documents), int(characters)


@dataclass(frozen=True)
class Hit:
    """A document that holds every term searched for."""
    url: str
    # Each (note, key) whose Sources list gives this document, or names the filing it's part of.
    keys: tuple[tuple[str, str], ...]
    # The words around each place the first term is written, with the term in square brackets. The index's own snippet
    # when the term isn't written there as given, such as a number the index read as two words.
    passages: tuple[str, ...]
    # Each (note, line) whose body cites one of those keys.
    cited_at: tuple[tuple[str, int], ...]


# How many characters either side of a hit are shown, and how many hits in one document.
AROUND = 90
HITS_SHOWN = 3


def passages(text: str, term: str, around: int = AROUND, most: int = HITS_SHOWN) -> list[str]:
    """The words around each place a term is written in a text, ignoring case, with the term in square brackets."""
    found: list[str] = []
    lowered, wanted = text.lower(), term.lower()
    at = lowered.find(wanted) if wanted else -1
    while at >= 0 and len(found) < most:
        start, end = max(0, at - around), min(len(text), at + len(term) + around)
        shown = f"{text[start:at]}[{text[at:at + len(term)]}]{text[at + len(term):end]}"
        found.append(("... " if start else "") + " ".join(shown.split()) + (" ..." if end < len(text) else ""))
        at = lowered.find(wanted, at + len(term))
    return found


def citing(ws: Workspace, con: sqlite3.Connection) -> dict[str, list[tuple[str, str, int]]]:
    """For each stored address, every (note, key, line) in the notes' bodies that cites it, by a key the note can use:
    its own, one it borrows, or one its heading or lead-in names for the rows below."""
    paths = note_files(ws)
    usable = keys_by_note(con, [path.name for path in paths], ws.config().get("notes", {}).get("borrows", {}))
    found: dict[str, list[tuple[str, str, int]]] = {}
    for line in note_lines(ws, con):
        if line.section != "notes":
            continue
        for key in line.keys:
            for url in dict.fromkeys(usable[line.note].get(key, [])):
                found.setdefault(url, []).append((line.note, key, line.line_no))
    return found


def search(con: sqlite3.Connection, terms: list[str], cited: dict[str, list[tuple[str, str, int]]] | None = None) -> list[Hit]:
    """Documents holding every term, each with the words around its hits, the keys it's listed under and, from `cited`
    (what `citing` returns), the lines of the notes that cite it."""
    query = " ".join('"{}"'.format(term.replace('"', "")) for term in terms)
    found = []
    for url, text, snippet in con.execute(
            "SELECT documents_fts.url, documents.text, snippet(documents_fts, 2, '[', ']', ' ... ', 24) FROM documents_fts"
            " JOIN documents ON documents.rowid = documents_fts.rowid WHERE documents_fts MATCH ? LIMIT 25", (query,)).fetchall():
        keys = tuple(con.execute("SELECT DISTINCT note_file, source_key FROM sources WHERE url=? AND source_key IS NOT NULL"
                                 " ORDER BY note_file, source_key", (url,)).fetchall())
        shown = passages(text or "", terms[0]) or [" ".join(snippet.split())]
        lines = tuple(dict.fromkeys((note, line) for note, _, line in (cited or {}).get(url, [])))
        found.append(Hit(url, keys, tuple(shown), lines))
    return found
