"""The Sources lists, to and from a reference manager.

`export-sources` writes every entry of every note's Sources list as BibTeX (data/sources.bib) and CSL JSON
(data/sources.json), with the day each address was fetched, or its text gathered by hand, as the day it was accessed.
Each entry's key is the note's name and its own key, as `01_northbridge:S1`, so two notes' S1 never collide.

An entry is read as the notes usually write one, `- **S1.** Northbridge Robotics. 2026. *Annual Report 2025.* https://...`:
the title is the text in single asterisks or in quotation marks, the year the last year before it, and the author what
comes before the year. What can't be read that way is never guessed at: the entry's words go in its note field as they
stand, and the title, author or year is left out.

`import-sources FILE` reads a BibTeX or CSL JSON export and writes a proposed Sources entry for each reference to
data/proposed_sources.md, in the same shape, for the researcher to give a key and paste under a note's Sources heading.
It never writes to the notes. The export is read as data with a small reader of its own; nothing in it is run.
"""
import argparse
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import sourcedb
from .workspace import Workspace

BIBTEX = "sources.bib"
CSL = "sources.json"
PROPOSED = "proposed_sources.md"
# The title of an entry: in single asterisks, as *Annual Report 2025.*, or in quotation marks of either kind.
TITLE = re.compile(r"(?<!\*)\*(?!\*)(?P<starred>[^*]+?)\*(?!\*)|[\"“](?P<quoted>[^\"“”]+)[\"”]")
YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})[a-z]?(?!\d)")
GATHERED_ON = re.compile(r"\bat (\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class Reference:
    """One source, as a reference manager holds it. Anything not known is ""."""
    id: str
    title: str = ""
    author: str = ""
    year: str = ""
    url: str = ""
    accessed: str = ""      # YYYY-MM-DD
    note: str = ""


# ---------------------------------------------------------------- the notes' Sources lists, out

def _plain(text: str) -> str:
    return " ".join(text.split()).strip(" .,;:")


def read_entry(text: str) -> tuple[str, str, str, str]:
    """An entry's words, after its key and without its addresses, as (title, author, year, what's left). The title,
    author and year are "" when the entry isn't written the usual way."""
    title = TITLE.search(text)
    if not title:
        return "", "", "", _plain(text)
    before, after = text[:title.start()], text[title.end():]
    years = list(YEAR.finditer(before))
    year = years[-1].group(1) if years else ""
    author = _plain(before[:years[-1].start()]) if years else ""
    rest = _plain(after) if years or not _plain(before) else _plain(before + " " + after)
    return _plain(title.group("starred") or title.group("quoted") or ""), author, year, rest


def accessed(con: sqlite3.Connection, url: str) -> str:
    """The day a source's text was had: the day it was gathered by hand when it was, else the day it was fetched."""
    row = con.execute("SELECT fetched_at, http_status, error FROM fetches WHERE url=?", (url,)).fetchone()
    if not row:
        return ""
    fetched_at, status, error = row
    gathered = GATHERED_ON.search(error or "")
    if gathered:
        return gathered.group(1)
    has_text = con.execute("SELECT 1 FROM documents WHERE url=? AND text_chars > 0", (url,)).fetchone()
    return (fetched_at or "")[:10] if status == 200 or has_text else ""


def references(ws: Workspace, con: sqlite3.Connection) -> list[Reference]:
    """Every entry of every note's Sources list, as a reference. The notes are read afresh first."""
    sourcedb.record_sources(ws, con)
    found: list[Reference] = []
    for path in sourcedb.note_files(ws):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            listed = sourcedb.KEY_LINE.match(line)
            if not listed:
                continue
            key = listed.group(1)
            urls = [url for (url,) in con.execute("SELECT url FROM sources WHERE note_file=? AND line_no=? AND source_key=?"
                                                  " AND origin='cited' ORDER BY id", (path.name, line_no, key))]
            # A local file's `file:` address means nothing to a reference manager, which would take it for a link.
            urls = [url for url in urls if not url.startswith(sourcedb.LOCAL)]
            words = sourcedb.FILE_ADDRESS.sub(" ", sourcedb.URL.sub(" ", line[listed.end():]))
            title, author, year, rest = read_entry(words)
            note = f"Cited as {key} in {path.name}" + (f". {rest}" if rest else "") + (
                f". Also at {', '.join(urls[1:])}" if len(urls) > 1 else "")
            found.append(Reference(f"{path.stem}:{key}", title, author, year, urls[0] if urls else "",
                                   accessed(con, urls[0]) if urls else "", note))
    return found


def _bib_text(text: str) -> str:
    """Text as a BibTeX value holds it: LaTeX's special characters escaped, and braces, which BibTeX counts even when
    escaped, made round brackets."""
    text = text.replace("\\", "/").replace("{", "(").replace("}", ")")
    text = re.sub(r"([&%$#_])", r"\\\1", text)
    return text.replace("~", r"\textasciitilde{}").replace("^", r"\textasciicircum{}")


def bibtex(found: list[Reference]) -> str:
    """References as BibTeX. Every author is written in double braces, as an organisation is, since an entry doesn't
    say which part of a person's name is the family name."""
    out = []
    for ref in found:
        fields = [("author", f"{{{_bib_text(ref.author)}}}" if ref.author else ""), ("title", _bib_text(ref.title)),
                  ("year", ref.year), ("url", ref.url.replace("{", "%7B").replace("}", "%7D")), ("urldate", ref.accessed),
                  ("note", _bib_text(ref.note))]
        body = "".join(f"  {name} = {{{value}}},\n" for name, value in fields if value)
        out.append(f"@misc{{{ref.id},\n{body}}}\n")
    return "\n".join(out)


def csl(found: list[Reference]) -> list[dict[str, Any]]:
    """References as CSL JSON items."""
    items = []
    for ref in found:
        item: dict[str, Any] = {"id": ref.id, "type": "webpage"}
        if ref.title:
            item["title"] = ref.title
        if ref.author:
            item["author"] = [{"literal": ref.author}]
        if ref.year:
            item["issued"] = {"date-parts": [[int(ref.year)]]}
        if ref.url:
            item["URL"] = ref.url
        if ref.accessed:
            item["accessed"] = {"date-parts": [[int(part) for part in ref.accessed.split("-")]]}
        item["note"] = ref.note
        items.append(item)
    return items


def export(ws: Workspace, con: sqlite3.Connection, formats: tuple[str, ...] = ("bibtex", "csl")) -> tuple[int, list[Path]]:
    """Write the Sources lists in each format asked for. Returns how many entries there were and the files written."""
    found = references(ws, con)
    ws.data.mkdir(parents=True, exist_ok=True)
    written = []
    if "bibtex" in formats:
        (ws.data / BIBTEX).write_text(bibtex(found), encoding="utf-8", newline="\n")
        written.append(ws.data / BIBTEX)
    if "csl" in formats:
        (ws.data / CSL).write_text(json.dumps(csl(found), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        written.append(ws.data / CSL)
    return len(found), written


# ---------------------------------------------------------------- a reference manager's export, in

# LaTeX accents, as the combining mark each one puts on its letter.
ACCENTS = {"'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303", "=": "\u0304", ".": "\u0307",
           "c": "\u0327", "v": "\u030c", "u": "\u0306", "H": "\u030b", "k": "\u0328"}
LETTERS = {"ss": "ß", "o": "ø", "O": "Ø", "ae": "æ", "AE": "Æ", "oe": "œ", "OE": "Œ", "aa": "å", "AA": "Å", "l": "ł", "L": "Ł",
           "i": "ı"}
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def latex_text(value: str) -> str:
    """A BibTeX value as plain text: accents put on their letters, escaped characters unescaped, an address taken out
    of \\url{}, any other command and every brace dropped."""
    value = re.sub(r"\\(?:url|href)\s*\{([^{}]*)\}(?:\{[^{}]*\})?", r"\1", value)
    accent = re.compile(r"\\([`'^\"~=.]|[cvuHk](?![a-zA-Z]))\s*(?:\{\s*(\\?[A-Za-z])\s*\}|(\\?[A-Za-z]))")

    def accented(match: re.Match[str]) -> str:
        letter = (match.group(2) or match.group(3)).lstrip("\\")
        return unicodedata.normalize("NFC", letter + ACCENTS[match.group(1)])

    value = accent.sub(accented, value)
    value = re.sub(r"\\(ss|ae|AE|oe|OE|aa|AA|o|O|l|L|i)(?![a-zA-Z])\s*(?:\{\})?", lambda m: LETTERS[m.group(1)], value)
    value = re.sub(r"\\([&%$#_{}])", r"\1", value).replace("---", "—").replace("--", "–")
    value = re.sub(r"\\[a-zA-Z]+\*?\s*", "", value)
    return " ".join(value.replace("{", "").replace("}", "").replace("~", " ").split())


def _closing(text: str, at: int, opener: str) -> int:
    """Where the brace or bracket opened at `at` closes, counting braces inside it. Raises ValueError if it never does."""
    braces = 0
    for position in range(at + 1, len(text)):
        char = text[position]
        if char == "}" and braces == 0 and opener == "{":
            return position
        if char == ")" and braces == 0 and opener == "(":
            return position
        braces += {"{": 1, "}": -1}.get(char, 0)
    raise ValueError(f"an entry opened at character {at} never closes")


def _value(text: str, at: int, strings: dict[str, str]) -> tuple[str, int]:
    """One field's value starting at `at`, its parts joined by #, as (the raw value, where it ends)."""
    parts = []
    while True:
        while at < len(text) and text[at].isspace():
            at += 1
        if at >= len(text):
            raise ValueError("a field has no value")
        if text[at] == "{":
            end = _closing(text, at, "{")
            parts.append(text[at + 1:end])
            at = end + 1
        elif text[at] == '"':
            depth, end = 0, at + 1
            while end < len(text) and not (text[end] == '"' and depth == 0):
                depth += {"{": 1, "}": -1}.get(text[end], 0)
                end += 1
            if end >= len(text):
                raise ValueError("a quoted value never closes")
            parts.append(text[at + 1:end])
            at = end + 1
        else:
            word = re.compile(r"[^\s,#})]+").match(text, at)
            if not word:
                raise ValueError(f"a field's value can't be read at {text[at:at + 20]!r}")
            name = word.group(0)
            parts.append(strings.get(name.lower(), name.capitalize() if name.lower() in MONTHS else name))
            at = word.end()
        while at < len(text) and text[at].isspace():
            at += 1
        if at < len(text) and text[at] == "#":
            at += 1
            continue
        return "".join(parts), at


def parse_bibtex(text: str) -> list[dict[str, str]]:
    """The entries of a BibTeX file, each as its fields' raw values by lower-case name, with its type as "@type" and
    its key as "@key". @string macros are filled in; @comment and @preamble are passed over. Raises ValueError for an
    entry it can't read."""
    entries: list[dict[str, str]] = []
    strings: dict[str, str] = {}
    at = 0
    while (at := text.find("@", at)) >= 0:
        head = re.compile(r"@\s*([A-Za-z]+)\s*([{(])").match(text, at)
        if not head:
            at += 1
            continue
        kind, opener = head.group(1).lower(), head.group(2)
        end = _closing(text, head.end() - 1, opener)
        body = text[head.end():end]
        at = end + 1
        if kind in ("comment", "preamble"):
            continue
        if kind == "string":
            named = re.match(r"\s*([^\s=]+)\s*=", body)
            if named:
                strings[named.group(1).lower()], _ = _value(body, named.end(), strings)
            continue
        key, _, rest = body.partition(",")
        entry = {"@type": kind, "@key": key.strip()}
        position = 0
        while True:
            field = re.compile(r"\s*,?\s*([^\s=,]+)\s*=").match(rest, position)
            if not field:
                break
            entry[field.group(1).lower()], position = _value(rest, field.end(), strings)
        entries.append(entry)
    return entries


def _bib_authors(raw: str) -> str:
    """A BibTeX author list as a reader writes one: "Doe, Jane and {Northbridge Robotics}" as "Jane Doe and Northbridge
    Robotics"."""
    names, depth, current = [], 0, ""
    for word in re.split(r"(\s+)", raw):
        if depth == 0 and word.lower() == "and":
            names.append(current)
            current = ""
            continue
        current += word
        depth += word.count("{") - word.count("}")
    names.append(current)
    shown = []
    for name in (name.strip() for name in names if name.strip()):
        if name.startswith("{") and name.endswith("}"):
            shown.append(latex_text(name))
            continue
        family, comma, given = latex_text(name).partition(",")
        shown.append(f"{given.strip()} {family.strip()}".strip() if comma else family.strip())
    return shown[0] if len(shown) == 1 else ", ".join(shown[:-1]) + " and " + shown[-1] if shown else ""


def latex_address(value: str) -> str:
    """A URL or DOI as BibTeX writes it, read as written: only a \\url{} wrapper and escaped \\_ \\% \\# \\& undone. The
    rest of `latex_text` would turn ~ into a space and -- into a dash, which breaks an address."""
    value = re.sub(r"\\(?:url|href)\s*\{([^{}]*)\}(?:\{[^{}]*\})?", r"\1", value.strip())
    return re.sub(r"\\([_%#&])", r"\1", value).replace("{", "").replace("}", "").strip()


def from_bibtex(text: str) -> list[Reference]:
    found = []
    for entry in parse_bibtex(text):
        url = latex_address(entry.get("url", ""))
        if not url:
            linked = re.search(r"https?://\S+", latex_address(entry.get("howpublished", "")))
            url = linked.group(0) if linked else ""
        if not url and entry.get("doi"):
            url = "https://doi.org/" + latex_address(entry["doi"])
        year = YEAR.search(entry.get("year", "") or entry.get("date", ""))
        found.append(Reference(entry["@key"], latex_text(entry.get("title", "")),
                               _bib_authors(entry.get("author", "") or entry.get("editor", "")), year.group(1) if year else "",
                               url, latex_text(entry.get("urldate", ""))[:10]))
    return found


def _csl_name(name: Any) -> str:
    if not isinstance(name, dict):
        return str(name)
    if name.get("literal"):
        return str(name["literal"])
    return " ".join(str(name[part]) for part in ("given", "non-dropping-particle", "family") if name.get(part))


def _csl_date(date: Any) -> list[int]:
    if isinstance(date, dict):
        parts = date.get("date-parts") or [[]]
        if parts and isinstance(parts[0], list):
            return [int(part) for part in parts[0] if str(part).lstrip("-").isdigit()]
        found = YEAR.search(str(date.get("raw", "") or date.get("literal", "")))
        return [int(found.group(1))] if found else []
    return []


def from_csl(text: str) -> list[Reference]:
    data = json.loads(text)
    items = data.get("items", []) if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("a CSL JSON export is a list of items")
    found = []
    for number, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        authors = [_csl_name(name) for name in item.get("author", []) or item.get("editor", []) or []]
        issued, seen = _csl_date(item.get("issued")), _csl_date(item.get("accessed"))
        url = str(item.get("URL", "") or (f"https://doi.org/{item['DOI']}" if item.get("DOI") else ""))
        found.append(Reference(str(item.get("id", number)), str(item.get("title", "")),
                               authors[0] if len(authors) == 1 else ", ".join(authors[:-1]) + " and " + authors[-1] if authors else "",
                               str(issued[0]) if issued else "", url,
                               "-".join(f"{part:02d}" for part in seen) if len(seen) == 3 else ""))
    return found


def read_export(path: Path) -> list[Reference]:
    """The references in a BibTeX (.bib) or CSL JSON (.json) export. Raises ValueError for one it can't read."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as problem:
        raise ValueError(f"{path} can't be read: {problem}") from None
    try:
        return from_csl(text) if path.suffix.lower() == ".json" or text.lstrip().startswith(("[", "{\"")) else from_bibtex(text)
    except (ValueError, KeyError, TypeError) as problem:
        raise ValueError(f"{path} can't be read as BibTeX or CSL JSON: {problem}") from None


def proposed_entry(ref: Reference) -> str:
    """A Sources entry for a reference, in the shape the notes write, with "S?" for the researcher's own key."""
    tidy = lambda text: " ".join(text.replace("*", "").split()).strip(" .")
    parts = [part for part in (tidy(ref.author), tidy(ref.year)) if part]
    words = ". ".join(parts) + ("." if parts else "")
    if ref.title:
        words += f" *{tidy(ref.title)}.*"
    line = f"- **S?.** {words.strip()} {ref.url}".rstrip()
    return line if ref.url else line + " (the export gives no address: add one before citing it)"


def propose(ws: Workspace, path: Path) -> tuple[int, Path]:
    """Write a proposed Sources entry for each reference in an export to data/proposed_sources.md. Returns how many."""
    found = read_export(path)
    ws.data.mkdir(parents=True, exist_ok=True)
    lines = ["# Proposed Sources entries", "",
             f"Read from {path.name} on {sourcedb.now()[:10]}. Nothing here is in the notes yet: give each entry you want a "
             "key of the note's own in place of S?, and paste it under that note's Sources heading.", "",
             *(f"<!-- {ref.id} -->\n{proposed_entry(ref)}" for ref in found)]
    (ws.data / PROPOSED).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return len(found), ws.data / PROPOSED


# ---------------------------------------------------------------- the commands

def run_export(ws: Workspace, con: sqlite3.Connection, args: argparse.Namespace) -> int:
    formats = ("bibtex", "csl") if args.format == "both" else (args.format,)
    count, written = export(ws, con, formats)
    print(f"{count} Sources entr{'y' if count == 1 else 'ies'}")
    for path in written:
        print(f"wrote {path}")
    return 0


def run_import(ws: Workspace, con: sqlite3.Connection, args: argparse.Namespace) -> int:
    try:
        count, written = propose(ws, Path(args.file))
    except ValueError as problem:
        print(problem)
        return 1
    print(f"proposed {count} Sources entr{'y' if count == 1 else 'ies'}; nothing was written to the notes")
    print(f"wrote {written}")
    return 0
