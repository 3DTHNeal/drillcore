"""The review: each claim the notes make against a source, set beside that source, for a person to look at in turn.

`check` judges every line of the notes against the stored text of the sources it cites, and its verdicts are where a
review starts, not where it ends. A figure the source holds may be the source's figure for something else, a quotation
that fails may be one word off, and a pass is a pass only as far as the check can see. So this module turns what
`check` finds into claims a person can step through: each figure, quotation, worked-out figure and citation that
didn't pass, where it stands on its line, its verdict and why, and for each source its line cites, where the stored
text holds it (the passage), the words near it that the row describes it by, and the page or section a pinpoint names.

Where a finding has a correction that the source or the working itself gives, the claim carries it as a suggestion
for the person to take or leave:

- a quotation that isn't in its source, with the words the source has at the passage closest to it;
- a worked-out figure that doesn't recompute, with what its working gives, to the places written;
- a figure or quotation the source holds on another page than the one cited, with that page.

Nothing is suggested from anywhere else, since the tool checks what a person wrote and doesn't write it for them. Each
suggestion is a whole line as it would read, and nothing is written to a note but by the person's say-so (`edit_line`).

A person's judgment of a claim is a mark, kept in checks/review.csv: the claim matches its source, or it disagrees with
it, with what the source says. A mark holds for what it was made against. It records the hash of the line and of the
text of the sources the claim cites, and when either changes, the mark is shown as needing another look. A finding the
person accepts becomes a waiver, a row of checks/waivers.csv like one written by hand (`accept`).

Everything a note or a source holds is data: it's carried as text and shown as text, never run.
"""
import csv
import hashlib
import io
import math
import os
import re
import sqlite3
import tempfile
from array import array
from bisect import bisect_left
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher
from itertools import islice
from pathlib import Path
from typing import Any

from assay import numbers as assay_numbers

from . import arithmetic as arithmetic_check
from . import cjk, inventory, pages, research, waivers
from .quotes import GAP, INLINE
from .sourcedb import KEY_TOKEN, URL, Held, NoteLine, clean_url, doc_numbers, find_number, note_files, note_lines, record_sources, table_headers
from .workspace import Workspace

FILE = Path("checks") / "review.csv"
COLUMNS = ("note_file", "line_no", "check", "item", "mark", "comment", "marked_by", "marked_on", "line_sha", "source_sha")
AGREES, DISAGREES = "agrees", "disagrees"
MARKS = (AGREES, DISAGREES)
# How many places in a source a claim's passage is shown at. A figure a long filing writes more often says little more.
MOST_HITS = 200
# How many of the row's describing words are marked in a source that doesn't hold the figure, to show where it talks
# about the thing the row names.
MOST_LABELS = 60
# What a figure's match says, by the way `figures` found it (`find_number`).
HOW = {
    "exact": "as written",
    "x1000": "a thousand times larger, as a table in thousands writes it",
    "x1e6": "a million times larger, as a table in units writes it",
    "x1e9": "a billion times larger",
    "/1000": "a thousand times smaller",
    "rounded": "with more decimal places, which round to the note's",
}
WORD = re.compile(r"\w+")
DIGITS = re.compile(r"\d[\d,]*(?:\.\d+)?")
# A word a source uses more often than this says little about where a quotation of it stands.
COMMON = 400


# ---------------------------------------------------------------- what a review holds

@dataclass(frozen=True)
class Source:
    """One stored source, as the inventory lists it."""
    id: int
    url: str
    title: str
    keys: tuple[str, ...]
    status: str
    fetched_at: str
    sha256: str
    chars: int | None
    kind: str


@dataclass(frozen=True)
class View:
    """What a claim shows of one source: where the stored text holds what the claim states, as (start, end, how), the
    words near it the row describes it by, the stretches a pinpoint names, and in words what was found."""
    source: int
    hits: tuple[tuple[int, int, str], ...] = ()
    labels: tuple[tuple[int, int], ...] = ()
    region: tuple[tuple[int, int], ...] = ()
    said: str = ""


@dataclass(frozen=True)
class Suggestion:
    """A line as a correction the source or the working gives would leave it, with why, and the words that change."""
    line_no: int
    old: str
    new: str
    why: str
    diff: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Mark:
    """One row of checks/review.csv: a person's judgment of a claim, and what it was made against."""
    note: str
    line_no: int
    check: str
    item: str
    mark: str
    comment: str
    by: str
    on: str
    line_sha: str
    source_sha: str


@dataclass
class Claim:
    """One thing the notes state that a check judged: where it stands (the line and the characters on it, or -1 for
    the whole line), the verdict and why, and what each source it cites shows of it."""
    note: str
    line_no: int
    start: int
    end: int
    check: str
    status: str
    verdict: str
    item: str
    detail: str
    keys: tuple[str, ...]
    waiver: str = ""
    views: list[View] = field(default_factory=list)
    suggestion: Suggestion | None = None
    # For a worked-out figure: what the working gives, and each input with the claims that state it.
    working: dict[str, Any] | None = None
    line_sha: str = ""
    source_sha: str = ""
    mark: Mark | None = None
    # Why the mark needs another look, or "" when it holds.
    stale: str = ""
    # The claim as its line writes it, where the check names it otherwise: "551.1 百万" for 551100000.
    written: str = ""

    def same(self, note: str, line_no: int, check: str, item: str) -> bool:
        return (self.note, self.line_no, self.check, squeeze(self.item)) == (note, line_no, check, squeeze(item))


@dataclass
class Review:
    """Everything the review page shows: each note's lines, the sources, the links from a line to a source, and the
    claims, in the order the notes make them."""
    notes: dict[str, list[str]]
    sources: list[Source]
    links: list[dict[str, Any]]
    claims: list[Claim]

    def find(self, note: str, line_no: int, check: str, item: str, status: str = "") -> Claim | None:
        """The claim named, and of two on the same item, such as a Sources entry both unused and not fetched, the one
        with this status."""
        same = [claim for claim in self.claims if claim.same(note, line_no, check, item)]
        return next((claim for claim in same if claim.status == status), same[0] if same else None)

    def to_json(self) -> dict[str, Any]:
        return {
            "notes": [{"file": name, "lines": lines} for name, lines in self.notes.items()],
            "sources": [{"id": s.id, "url": s.url, "title": s.title, "keys": list(s.keys), "status": s.status,
                         "fetchedAt": s.fetched_at, "sha256": s.sha256, "chars": s.chars, "kind": s.kind} for s in self.sources],
            "links": self.links,
            "claims": [claim_json(number, claim) for number, claim in enumerate(self.claims)],
        }


def claim_json(number: int, claim: Claim) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": f"c{number}", "note": claim.note, "line": claim.line_no, "start": claim.start, "end": claim.end,
        "check": claim.check, "status": claim.status, "verdict": claim.verdict, "item": claim.item, "detail": claim.detail,
        "keys": list(claim.keys), "waiver": claim.waiver,
        "views": [{"source": v.source, "hits": [list(h) for h in v.hits], "labels": [list(s) for s in v.labels],
                   "region": [list(s) for s in v.region], "said": v.said} for v in claim.views],
        "suggestion": None, "working": claim.working, "mark": None, "stale": claim.stale, "written": claim.written,
    }
    if claim.suggestion:
        s = claim.suggestion
        out["suggestion"] = {"line": s.line_no, "old": s.old, "new": s.new, "why": s.why, "diff": [list(d) for d in s.diff]}
    if claim.mark:
        m = claim.mark
        out["mark"] = {"mark": m.mark, "comment": m.comment, "by": m.by, "on": m.on}
    return out


def squeeze(text: str) -> str:
    return " ".join(text.split()).casefold()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- where a claim stands on its line

def blank_keys(text: str, known: dict[str, list[str]]) -> str:
    """A line with its source keys and their pinpoints blanked, keeping its length, so places in it are the line's own."""
    text = pages.without_pins(text, known)
    return KEY_TOKEN.sub(lambda match: " " * len(match.group(0)) if match.group(1) in known else match.group(0), text)


def place(line: str, written: str, at: int = 0) -> tuple[int, int] | None:
    """Where a figure stands on a line, at or after `at`: as written, or failing that, its digits standing alone."""
    found = line.find(written, at) if written else -1
    if found >= 0:
        return found, found + len(written)
    digits = DIGITS.search(written)
    if not digits:
        return None
    match = re.compile(rf"(?<![\w.,]){re.escape(digits.group(0))}(?![\d]|[.,]\d)").search(line, at)
    return match.span() if match else None


def key_place(line: str, key: str) -> tuple[int, int] | None:
    match = next((m for m in KEY_TOKEN.finditer(line) if m.group(1) == key), None)
    return match.span(1) if match else None


def quote_place(line: str, quote: str) -> tuple[int, int] | None:
    """Where a quotation stands on a line, with its quote marks: the inline quotation whose words are these, or the
    words after a blockquote's marker."""
    for match in INLINE.finditer(line):
        if squeeze(match.group(1)) == squeeze(quote):
            return match.span()
    marker = re.match(r"\s*>\s?", line)
    if marker and line[marker.end():].strip():
        return marker.end(), len(line.rstrip())
    first = INLINE.search(line)
    return first.span() if first else None


def working_place(line: str, item: str, stated: str) -> tuple[int, int] | None:
    """Where a worked-out figure and its working stand on a line: the item as `arithmetic` writes it, or the stated
    figure to the bracket that closes its working."""
    found = line.find(item) if item else -1
    if found >= 0:
        return found, found + len(item)
    at = place(line, stated) if stated else None
    if not at:
        return None
    close = line.find(")", at[1])
    return (at[0], close + 1) if 0 <= close - at[1] < 160 else at


# ---------------------------------------------------------------- where a source holds it

class Texts:
    """The stored sources, read once for one review: their text, the numbers in it, where its words start and end for
    finding the passage closest to a quotation, and what's worked out from each text more than once. A filing's text
    runs to megabytes, so each is read once whatever the number of claims that cite it."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con
        self.held = Held(con)
        self._words: dict[str, tuple[array[int], array[int]]] = {}
        self._word: dict[tuple[str, str], list[int]] = {}
        self._anywhere: dict[tuple[str, frozenset[str]], tuple[tuple[int, int], ...]] = {}
        self._sha: dict[tuple[str, ...], str] = {}

    def bind(self, con: sqlite3.Connection) -> None:
        """Read through another connection to the same database from now on, keeping what was read."""
        self.con = self.held.con = con

    def text(self, url: str) -> str | None:
        return self.held.text(url)

    def word_at(self, url: str, word: str) -> list[int]:
        """Where a word stands among a source's words, in any case: at most `COMMON` + 1 places, since a word the source
        uses more often than `COMMON` says little about where a quotation stands."""
        if (url, word) not in self._word:
            starts, _ = self.words(url)
            found = re.finditer(rf"(?<!\w){re.escape(word)}(?!\w)", self.text(url) or "", re.IGNORECASE)
            self._word[url, word] = [bisect_left(starts, match.start()) for match in islice(found, COMMON + 1)]
        return self._word[url, word]

    # Quoted: array is generic only from Python 3.12, and 3.11 evaluates a signature's annotations when it loads this.
    def words(self, url: str) -> tuple["array[int]", "array[int]"]:
        """Where each of a source's words starts and ends, in order."""
        if url not in self._words:
            starts, ends = array("q"), array("q")
            for match in WORD.finditer(self.text(url) or ""):
                starts.append(match.start())
                ends.append(match.end())
            self._words[url] = (starts, ends)
        return self._words[url]

    def anywhere(self, url: str, stems: frozenset[str]) -> tuple[tuple[int, int], ...]:
        """The first places a source uses any word with these first letters: the rows of a table share their words,
        so each set is looked for once."""
        if (url, stems) not in self._anywhere:
            self._anywhere[url, stems] = tuple(stem_spans(self.text(url) or "", stems, [(0, len(self.text(url) or ""))], MOST_LABELS))
        return self._anywhere[url, stems]

    def sha(self, urls: Iterable[str]) -> str:
        """One hash of the text of each of these sources, in the order of their addresses, as a mark records them."""
        key = tuple(sorted(set(urls)))
        if key not in self._sha:
            self._sha[key] = sha("\x1e".join(f"{url}\x1f{self.text(url) or ''}" for url in key)) if key else ""
        return self._sha[key]


def stem_spans(text: str, stems: frozenset[str], windows: list[tuple[int, int]], most: int) -> list[tuple[int, int]]:
    """The words within the windows of a text whose first letters are one of the stems, up to `most`."""
    found: dict[tuple[int, int], None] = {}
    for low, high in windows:
        for match in research.LABEL_WORD.finditer(text, low, high):
            if match.group(0).lower()[:research.STEM] in stems:
                found[match.span()] = None
                if len(found) >= most:
                    return list(found)
    return list(found)


def label_spans(texts: Texts, url: str, stems: Iterable[str], around: list[tuple[int, int, str]]) -> tuple[tuple[int, int], ...]:
    """The words of a source near each place it holds a figure, within `research.NEAR` characters, that a row describes
    its figure by: matched on their first letters, as `check` matches them. With no place to be near, or none of those
    words near any, the first places the source uses one, so a reader can see where it talks about the thing the row
    names."""
    wanted = frozenset(stems)
    text = texts.text(url) or ""
    if not wanted:
        return ()
    windows = [(max(0, start - research.NEAR), min(len(text), end + research.NEAR)) for start, end, _ in around[:30]]
    near = stem_spans(text, wanted, windows, MOST_HITS)
    return tuple(sorted(set(near))) if near else texts.anywhere(url, wanted)


def figure_view(texts: Texts, source: int, url: str, written: str, pin: pages.Pin | None, stems: Iterable[str]) -> View:
    """Where a source holds a figure, the way `figures` finds it: as written, at another scale, or with more decimal
    places. Held to the page or section a pinpoint names, where it holds it there, and otherwise shown wherever it is."""
    text = texts.text(url)
    if text is None:
        return View(source, said="No text is held for this source, so the figure wasn't looked for in it.")
    digits = DIGITS.search(written)
    if not digits:
        return View(source, labels=label_spans(texts, url, stems, []), said="A figure written in words isn't looked for in a source's text.")
    plain = digits.group(0).replace(",", "")
    value, decimals = float(plain), len(plain.split(".")[1]) if "." in plain else 0
    held = texts.held
    chinese = held.chinese(url)
    region: list[tuple[int, int]] = []
    where = ""
    if pin:
        stretches, why = pages.region(texts.con, url, text, pin)
        region = stretches or []
        where = pin.where if stretches else f"{pin.shown()} can't be read: {why}"
    kind, matched = find_number(held.numbers(url), value, decimals, chinese)
    if region:
        inside_kind, inside_matched = find_number(doc_numbers(pages.region_text(text, region)), value, decimals, chinese)
        if inside_kind:
            kind, matched = inside_kind, inside_matched
    if not kind or matched is None:
        said = f"The stored text doesn't hold {written} at any scale `figures` tries."
        return View(source, (), label_spans(texts, url, stems, []), tuple(region), said + (f" Pinpoint: {where}." if where else ""))
    places = held.places(url, matched)
    inside = [(s, e, kind) for s, e in places if not region or pages.within(region, s)]
    outside = [(s, e, f"{kind}, away from {pin.where}") for s, e in places if region and pin and not pages.within(region, s)]
    hits = (inside + outside)[:MOST_HITS]
    count = len(places)
    said = f"Found {HOW.get(kind, kind)}, at {count} place{'' if count == 1 else 's'}"
    if region and pin:
        if not inside:
            said += f", none at {pin.where}"
        elif len(inside) == count:
            said += f", {'all ' if count > 1 else ''}at {pin.where}"
        else:
            said += f", {len(inside)} of them at {pin.where}"
    elif where:
        said += f". Pinpoint: {where}"
    return View(source, tuple(hits), label_spans(texts, url, stems, hits), tuple(region), said + ".")


def quote_spans(text: str, quote: str) -> list[tuple[int, int]]:
    """Where a quotation's words stand in a source's text, each part after an ellipsis or a bracketed insertion after
    the one before it. The words are matched in any case and with any marks between them, so this finds the passage a
    reader would; whether the words are exact is `quotes`'s to say. [] when a part isn't there."""
    spans: list[tuple[int, int]] = []
    at = 0
    for part in GAP.split(quote):
        words = WORD.findall(part)
        if not words:
            continue
        pattern = re.compile(r"(?<!\w)" + r"[\W_]{1,12}".join(re.escape(word) for word in words) + r"(?!\w)", re.IGNORECASE)
        match = pattern.search(text, at)
        if not match:
            return []
        spans.append(match.span())
        at = match.end()
    return spans


def closest_passage(texts: Texts, url: str, quote: str) -> tuple[int, int] | None:
    """The passage of a source closest to a quotation it doesn't hold: the run of the source's words that keeps the
    most of the quotation's words in order, starting and ending on one of them, and no longer than twice the quotation.
    None when no passage keeps at least half its words, and two."""
    wanted = [word.casefold() for word in WORD.findall(quote)]
    text = texts.text(url) or ""
    if len(wanted) < 2 or not text:
        return None
    starts, ends = texts.words(url)
    places = {word: texts.word_at(url, word) for word in dict.fromkeys(wanted)}
    enough = max(2, math.ceil(len(wanted) / 2))

    def best_from(words: list[tuple[int, str]]) -> tuple[int, int] | None:
        """The closest passage among those the places of these words propose, as (first word, word after the last)."""
        # Each place a word of the quotation stands proposes where the quotation would start, counted in words.
        proposed: dict[int, int] = {}
        for k, word in words:
            for position in places[word][:COMMON]:
                proposed[position - k] = proposed.get(position - k, 0) + 1
        best: tuple[tuple[int, int], int, int] | None = None
        for start, _ in sorted(proposed.items(), key=lambda item: -item[1])[:200]:
            low, high = max(0, start - 2), min(len(starts), start + len(wanted) + 2)
            window = [text[starts[at]:ends[at]].casefold() for at in range(low, high)]
            blocks = [block for block in SequenceMatcher(None, wanted, window, autojunk=False).get_matching_blocks() if block.size]
            if not blocks:
                continue
            first, last = low + blocks[0].b, low + blocks[-1].b + blocks[-1].size
            score = (sum(block.size for block in blocks), -(last - first))
            if best is None or score > best[0]:
                best = (score, first, last)
        if best is None or best[0][0] < enough or best[2] - best[1] > 2 * len(wanted):
            return None
        return best[1], best[2]

    # The words the source uses seldom say best where the quotation would stand. When they propose nothing close, as
    # when the word that differs is the only seldom one, every word's first places are tried.
    seldom = [(k, word) for k, word in enumerate(wanted) if 0 < len(places[word]) <= COMMON]
    found = (best_from(seldom) if seldom else None) or best_from(list(enumerate(wanted)))
    return (starts[found[0]], ends[found[1] - 1]) if found else None


def word_diff(old: str, new: str) -> tuple[tuple[str, str], ...]:
    """How one run of words becomes another, as ("equal" | "delete" | "insert", the words)."""
    a, b = old.split(), new.split()
    out: list[tuple[str, str]] = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(("equal", " ".join(a[i1:i2])))
            continue
        if i2 > i1:
            out.append(("delete", " ".join(a[i1:i2])))
        if j2 > j1:
            out.append(("insert", " ".join(b[j1:j2])))
    return tuple(out)


# ---------------------------------------------------------------- suggestions the source or the working gives

def quote_suggestion(line: str, line_no: int, quote: str, passage: str, key: str) -> Suggestion | None:
    """The line with an inline quotation replaced by the words the source has at its closest passage. None for a
    quotation with an ellipsis or an insertion, one this can't place on its line, or a passage holding a double quote."""
    if not passage.strip() or GAP.search(quote) or any(mark in passage for mark in "\"“”"):
        return None
    inline = next((m for m in INLINE.finditer(line) if squeeze(m.group(1)) == squeeze(quote)), None)
    if not inline:
        return None
    words = " ".join(passage.split())
    if words[:1].isalpha() and quote[:1].isalpha():
        # Quoting may change the case of the first letter to fit the sentence, so the note's is kept.
        words = (words[0].upper() if quote[0].isupper() else words[0].lower()) + words[1:]
    if words == inline.group(1):
        return None
    new = line[:inline.start(1)] + words + line[inline.end(1):]
    return Suggestion(line_no, line, new, f"These are the words {key} has at that passage, as it writes them.",
                      word_diff(inline.group(1), words))


def figure_written(stated: str, value: float) -> str | None:
    """A worked-out figure written again with a new value: its sign, currency and unit kept, its places the same, and
    its thousands grouped if they were."""
    number = DIGITS.search(stated)
    if not number:
        return None
    digits = number.group(0)
    places = len(digits.split(".")[1]) if "." in digits else 0
    shown = f"{abs(value):,.{places}f}" if "," in digits else f"{abs(value):.{places}f}"
    lead = stated[:number.start()]
    signs = [char for char in lead if char in "+-−"]
    if signs:
        minus = "−" if "−" in lead else "-"
        sign = minus if value < 0 else "+" if value > 0 else ""
        lead = lead.replace(signs[0], sign, 1)
    return lead + shown + stated[number.end():]


def working_suggestion(line: str, line_no: int, worked: arithmetic_check.Result) -> Suggestion | None:
    """The line with a worked-out figure written as its working gives it, for a figure with its working in brackets
    after it. None for an equation or a table's total, where which figure is wrong is the person's to say, and for a
    figure written more than once on its line."""
    if worked.status != "wrong" or worked.computed is None or worked.item != f"{worked.stated} ({worked.detail})":
        return None
    if line.count(worked.stated) != 1:
        return None
    figure = figure_written(worked.stated, worked.computed)
    if figure is None or figure == worked.stated:
        return None
    new = line.replace(worked.stated, figure, 1)
    return Suggestion(line_no, line, new, f"The working ({worked.detail}) gives {worked.shown()}, which is {figure} to the places written.",
                      word_diff(worked.stated, figure))


def page_suggestion(con: sqlite3.Connection, line: str, line_no: int, pin: pages.Pin, url: str, at: int) -> Suggestion | None:
    """The line with a page pinpoint giving the page the source holds the figure or quotation on, counted from the front.
    None for a section, or a pinpoint that isn't on this line."""
    if pin.section:
        return None
    page = con.execute("SELECT page, folio FROM document_pages WHERE url=? AND start<=? AND ?<end_at ORDER BY page LIMIT 1",
                       (url, at, at)).fetchone()
    cited = next((m for m in pages.PIN.finditer(line) if m.group("key") == pin.key and m.group("pp")), None)
    if not page or not cited:
        return None
    new = line[:cited.start("pp")] + f"p.{page[0]}" + line[cited.end():]
    printed = f" (printed {page[1]})" if page[1] and page[1] != str(page[0]) else ""
    return Suggestion(line_no, line, new, f"The stored copy holds it on page {page[0]}{printed}, counted from the front.",
                      word_diff(line[cited.start():cited.end()], f"{pin.key} p.{page[0]}"))


def section_suggestion(line: str, line_no: int, pin: pages.Pin, text: str, at: int) -> Suggestion | None:
    """The line with a section pinpoint naming the section the source holds the figure or quotation in: the last heading
    numbered the cited section's way before it, as "Note 13" for "Note 12", offered only when `pages` reads that
    section as holding the place. None for a section named by words alone, or a pinpoint that isn't on this line."""
    numbered = pages.NUMBERED.fullmatch(pin.section)
    if not numbered:
        return None
    word = (numbered.group("word") or "").rstrip(".")
    if word:
        heading = re.compile(rf"^[ \t]*{re.escape(word)}\.?\s*(\d+(?:\.\d+)*[A-Za-z]?)(?![\w.]?\d)", re.IGNORECASE | re.MULTILINE)
    else:
        depth = numbered.group("number").count(".")
        heading = re.compile(rf"^[ \t]*(\d+(?:\.\d+){{{depth}}})[.)]?\s+(?=[A-Z])", re.MULTILINE)
    before = list(heading.finditer(text, 0, at))
    last = before[-1] if before else None
    cited = next((m for m in pages.PIN.finditer(line) if m.group("key") == pin.key and m.group("section")), None)
    if last is None or cited is None:
        return None
    section = f"{word} {last.group(1)}" if word else last.group(1)
    stretches, _ = pages.section_region(text, pages.Pin(pin.key, section=section))
    if not stretches or not pages.within(stretches, at) or section == pin.section:
        return None
    new = line[:cited.start("section")] + section + line[cited.end("section"):]
    return Suggestion(line_no, line, new, f"The stored copy holds it in section {section}.",
                      word_diff(line[cited.start():cited.end()], line[cited.start():cited.start("section")] + section))


def pin_suggestion(con: sqlite3.Connection, line: str, line_no: int, pin: pages.Pin, url: str, text: str, at: int) -> Suggestion | None:
    """The line with its pinpoint naming the page or section the source holds the figure or quotation in."""
    return section_suggestion(line, line_no, pin, text, at) if pin.section else page_suggestion(con, line, line_no, pin, url, at)


def cjk_place(line: str, written: str, at: int = 0) -> tuple[int, int] | None:
    """Where a line writes, in a unit of ten-thousands or hundred-millions, a figure `cjk` wrote out in full: "551.1 百万"
    for 551100000. A check reads the figure written out, so its finding names that, and not what the line shows."""
    digits = DIGITS.search(written)
    if not digits:
        return None
    wanted = digits.group(0).replace(",", "")
    for match in cjk.FIGURE.finditer(line, at):
        if wanted in cjk.in_digits(match.group(0)).replace(",", "").split("-"):
            return match.span()
    return None


# ---------------------------------------------------------------- marks

def mark_of(row: dict[str, str]) -> Mark | None:
    """A row of the marks file as a mark, or None for one that isn't: a row that starts with #, as in the waivers file,
    or one whose mark or line can't be read."""
    values = {column: (row.get(column) or "").strip() for column in COLUMNS}
    if values["note_file"].startswith("#") or values["mark"] not in MARKS or not values["line_no"].isdigit():
        return None
    return Mark(values["note_file"], int(values["line_no"]), values["check"], values["item"], values["mark"], values["comment"],
                values["marked_by"], values["marked_on"], values["line_sha"], values["source_sha"])


def marks_file(ws: Workspace) -> tuple[list[str], list[dict[str, str]]]:
    """The marks file's columns and rows as written, or the columns a new one has and no rows."""
    path = ws.root / FILE
    if not path.is_file():
        return list(COLUMNS), []
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
        return list(reader.fieldnames or COLUMNS), rows


def read_marks(ws: Workspace) -> list[Mark]:
    """The workspace's marks, or [] when it has none. A row that isn't one (`mark_of`) is passed over."""
    return [mark for mark in map(mark_of, marks_file(ws)[1]) if mark is not None]


def write_atomically(path: Path, text: str) -> None:
    """Write a file whole, so a reader never sees half of it: to a file beside it, then put in its place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(text.encode("utf-8"))
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def write_marks(ws: Workspace, columns: list[str], rows: list[dict[str, str]]) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n", restval="", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    write_atomically(ws.root / FILE, buffer.getvalue())


def mark_for(claim: Claim, marks: list[Mark]) -> tuple[Mark | None, str]:
    """The mark a person made on a claim, and why it needs another look, or "" when it holds. A mark is found by its
    note, check and item, on the claim's line, or on another line that reads as the claim's does, since lines move."""
    same = [m for m in marks if m.note == claim.note and m.check == claim.check and squeeze(m.item) == squeeze(claim.item)]
    mark = next((m for m in same if m.line_no == claim.line_no), None) or next((m for m in same if m.line_sha == claim.line_sha), None)
    if mark is None:
        return None, ""
    if mark.line_sha != claim.line_sha:
        return mark, f"the line has changed since it was marked on {mark.on}"
    if mark.source_sha != claim.source_sha:
        return mark, f"the text of a source it cites has changed since it was marked on {mark.on}"
    return mark, ""


def apply_marks(review: Review, marks: list[Mark]) -> None:
    for claim in review.claims:
        claim.mark, claim.stale = mark_for(claim, marks)


def set_mark(ws: Workspace, claim: Claim, mark: str, comment: str, by: str, today: str | None = None) -> list[Mark]:
    """Record a person's mark on a claim, in place of any mark it had, or with mark "" take its mark away. Returns the
    marks as written. Every other row is kept as it was, a row that isn't a mark (`mark_of`) and any column of the
    file's own among them, since the file is plain text a person may edit by hand too. A file whose first line doesn't
    name the columns isn't written to."""
    writable(ws)
    if mark and mark not in MARKS:
        raise ReviewError(f"A mark is one of {', '.join(MARKS)}, not {mark!r}.")
    if mark == DISAGREES and not comment.strip():
        raise ReviewError("Say what the source says instead, so whoever fixes the note knows.")
    if mark and not by.strip():
        raise ReviewError("Say who's marking it: a name or initials.")
    columns, rows = marks_file(ws)
    if not set(COLUMNS) <= set(columns):
        raise ReviewError(f"{FILE.as_posix()} doesn't start with the columns {', '.join(COLUMNS)}, so the mark wasn't written. "
                          "Put that line back at its top, or move the file away.")

    def this_claims(row: dict[str, str]) -> bool:
        found = mark_of(row)
        return found is not None and found.note == claim.note and found.check == claim.check and \
            squeeze(found.item) == squeeze(claim.item) and (found.line_no == claim.line_no or found.line_sha == claim.line_sha)

    kept = [row for row in rows if not this_claims(row)]
    if mark:
        made = Mark(claim.note, claim.line_no, claim.check, claim.item, mark, one_line(comment), one_line(by),
                    today or date.today().isoformat(), claim.line_sha, claim.source_sha)
        kept.append(dict(zip(COLUMNS, (made.note, str(made.line_no), made.check, made.item, made.mark, made.comment, made.by,
                                       made.on, made.line_sha, made.source_sha), strict=True)))
    write_marks(ws, columns, kept)
    return [found for found in map(mark_of, kept) if found is not None]


def one_line(text: str) -> str:
    return " ".join(text.split())


# ---------------------------------------------------------------- what the person writes

class ReviewError(ValueError):
    """Something the review was asked to do and won't, with why."""


def writable(ws: Workspace) -> None:
    if ws.is_example:
        raise ReviewError("This is the example workspace that ships with the code, so the review doesn't change it. "
                          "Make a workspace of your own to review (`init`), and point at it.")


def note_path(ws: Workspace, note: str) -> Path:
    path = next((p for p in note_files(ws) if p.name == note), None)
    if path is None:
        raise ReviewError(f"{note} isn't a note in this workspace.")
    return path


def lines_reading(ws: Workspace, note: str, text: str) -> list[int]:
    """The numbers of the lines of a note that read exactly `text`."""
    lines = note_path(ws, note).read_bytes().decode("utf-8").splitlines()
    return [number for number, line in enumerate(lines, 1) if line == text]


def edit_line(ws: Workspace, note: str, line_no: int, old: str, new: str) -> None:
    """Write one line of a note anew, in place of `old`. Refuses when the line on disk isn't `old` any more, so an edit
    made elsewhere since the page was loaded is never written over, and refuses a line break in `new`."""
    writable(ws)
    path = note_path(ws, note)
    # Any character Python splits lines at would make two lines of one, and move every line after it.
    if new and new.splitlines() != [new]:
        raise ReviewError("A line can't hold a line break. Edit one line at a time.")
    lines = path.read_bytes().decode("utf-8").splitlines(keepends=True)
    if not 1 <= line_no <= len(lines):
        raise ReviewError(f"{note} has {len(lines)} lines, so there's no line {line_no}.")
    body = lines[line_no - 1].rstrip("\r\n")
    if body != old:
        raise ReviewError(f"Line {line_no} of {note} has changed since the page was loaded. Recheck, then try again.")
    lines[line_no - 1] = new + lines[line_no - 1][len(body):]
    write_atomically(path, "".join(lines))


def accept(ws: Workspace, claim: Claim, reason: str, by: str, today: str | None = None) -> None:
    """Accept a claim's finding: a row of checks/waivers.csv naming its check, note, line and item, with why, who and
    when, as one written by hand would. The line is named, since what the person accepted is the finding on it."""
    writable(ws)
    if claim.check not in waivers.CHECKS or claim.verdict not in (research.FAIL, research.WARN):
        raise ReviewError("Only a failure or a warning of citations, quotations, arithmetic, numbers or sections can be accepted.")
    if not reason.strip() or not by.strip():
        raise ReviewError("A waiver needs a reason and who accepts it.")
    path = ws.root / waivers.FILE
    values = {"check": claim.check, "note_file": claim.note, "line_no": str(claim.line_no) if claim.line_no else "",
              "item": one_line(claim.item), "reason": one_line(reason), "accepted_by": one_line(by),
              "accepted_on": today or date.today().isoformat()}
    if path.is_file():
        text = path.read_bytes().decode("utf-8")
        header = next(csv.reader(io.StringIO(text.lstrip("﻿"))), [])
        columns = [column.strip() for column in header]
        if not set(waivers.REQUIRED) <= set(columns):
            raise ReviewError(f"{waivers.FILE.as_posix()} doesn't start with the columns {', '.join(waivers.COLUMNS)}, so nothing was added to it.")
    else:
        text, columns = "", list(waivers.COLUMNS)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n" if "\r\n" in text else "\n")
    if not text:
        writer.writerow(columns)
    writer.writerow([values.get(column, "") for column in columns])
    ending = "" if not text or text.endswith(("\n", "\r")) else ("\r\n" if "\r\n" in text else "\n")
    write_atomically(path, text + ending + buffer.getvalue())


# ---------------------------------------------------------------- the review

def catalogue(ws: Workspace, con: sqlite3.Connection) -> tuple[list[Source], dict[str, int]]:
    """Every source the notes give, once each, with what the inventory knows of it, and its id by address."""
    titles = dict(con.execute("SELECT url, title FROM documents").fetchall())
    by_url: dict[str, list[inventory.Entry]] = {}
    for entry in inventory.inventory(ws, con):
        by_url.setdefault(entry.address, []).append(entry)
    found: list[Source] = []
    for number, (url, entries) in enumerate(by_url.items()):
        first = entries[0]
        keys = tuple(dict.fromkeys(f"{e.note} {e.key}" for e in entries if e.key))
        found.append(Source(number, url, titles.get(url) or "", keys, first.status, first.fetched_at, first.sha256, first.text_chars, first.kind))
    return found, {source.url: source.id for source in found}


@dataclass
class Kept:
    """What a review read of the sources, kept for the next review while their text stays as it was: `check`'s reading
    of each (which takes seconds for a long filing) and the review's own. A note edited on the review page changes no
    source, so the next review reads only the notes again. Recheck starts from nothing."""
    sources: research.Sources | None = None
    texts: Texts | None = None


def gather(ws: Workspace, con: sqlite3.Connection, kept: Kept | None = None) -> Review:
    """Run `check`'s checks and build the review of every claim they judged. Writes no report: `check` does that.
    With `kept`, what an earlier review read of the sources is used again, unless the keys leading to them changed."""
    kept = kept if kept is not None else Kept()
    workings = arithmetic_check.check(ws)
    record_sources(ws, con)
    fresh = research.Sources(ws, con)
    if kept.sources is None or kept.texts is None or kept.sources.urls != fresh.urls:
        kept.sources, kept.texts = fresh, Texts(con)
    kept.sources.con = con
    kept.texts.bind(con)
    found = research.results(ws, con, workings, kept.sources)
    builder = Builder(ws, con, workings, kept.sources, kept.texts)
    claims = builder.claims(found)
    review = Review(builder.notes, builder.sources, builder.links(), claims)
    apply_marks(review, read_marks(ws))
    return review


class Builder:
    """Turns `check`'s results into claims, reading each note and source once."""

    def __init__(self, ws: Workspace, con: sqlite3.Connection, workings: list[arithmetic_check.Result], checks: research.Sources,
                 texts: Texts) -> None:
        self.ws = ws
        self.con = con
        self.workings = {(w.note, w.line, squeeze(w.item)): w for w in workings}
        self.texts = texts
        self.checks = checks
        self.notes = {path.name: path.read_text(encoding="utf-8").splitlines() for path in note_files(ws)}
        self.lines: dict[tuple[str, int], NoteLine] = {(line.note, line.line_no): line for line in note_lines(ws, con)}
        self.headers = {(path.name, number): header for path in note_files(ws)
                        for number, header in table_headers(path.read_text(encoding="utf-8")).items()}
        self.sources, self.ids = catalogue(ws, con)

    def raw(self, note: str, line_no: int) -> str:
        lines = self.notes.get(note, [])
        return lines[line_no - 1] if 0 < line_no <= len(lines) else ""

    def urls(self, note: str, keys: Iterable[str]) -> list[str]:
        known = self.checks.urls.get(note, {})
        return list(dict.fromkeys(url for key in keys for url in known.get(key, [])))

    def pins(self, note: str, line_no: int) -> dict[str, pages.Pin]:
        """The pinpoint each address a line cites is held to, by address."""
        line = self.lines.get((note, line_no))
        known = self.checks.urls.get(note, {})
        return {url: pin for pin in (line.pins if line else ()) for url in known.get(pin.key, [])}

    def source_sha(self, urls: list[str]) -> str:
        return self.texts.sha(urls)

    def claim(self, r: research.Result, span: tuple[int, int] | None, item: str | None = None, status: str | None = None,
              detail: str | None = None) -> Claim:
        start, end = span or (-1, -1)
        status = status or r.status
        verdict = research.WAIVED if r.waiver and status == r.status else research.VERDICT[status]
        raw = self.raw(r.note, r.line_no)
        return Claim(r.note, r.line_no, start, end, r.check, status, verdict, r.item if item is None else item,
                     r.detail if detail is None else detail, r.keys, r.waiver if status == r.status else "", line_sha=sha(raw.strip()))

    # ---- each check's results

    def claims(self, found: list[research.Result]) -> list[Claim]:
        made: list[Claim] = []
        rows: dict[tuple[str, int], list[research.Result]] = {}
        traced: set[tuple[str, int]] = set()
        for r in found:
            if r.check == "citations":
                if r.verdict != research.PASS:
                    made.append(self.citation(r))
            elif r.check == "quotations":
                made.append(self.quotation(r))
            elif r.check == "arithmetic":
                made.append(self.arithmetic(r))
            elif r.check == "numbers" and r.status == "inputs_traced":
                traced.add((r.note, r.line_no))
            elif r.check == "numbers" and r.status.startswith("input"):
                made.append(self.claim(r, place(self.raw(r.note, r.line_no), r.item)))
            elif r.check == "numbers":
                rows.setdefault((r.note, r.line_no), []).append(r)
            else:
                made.append(self.claim(r, None))
        for (note, line_no), results in rows.items():
            made += self.figures(note, line_no, results)
        for claim in made:
            if claim.check == "arithmetic" and claim.working is not None and (claim.note, claim.line_no) in traced:
                claim.working["traced"] = True
        order = {name: number for number, name in enumerate(self.notes)}
        made.sort(key=lambda c: (order.get(c.note, len(order)), c.line_no, c.start, c.check))
        self.link_inputs(made)
        return made

    def citation(self, r: research.Result) -> Claim:
        claim = self.claim(r, key_place(self.raw(r.note, r.line_no), r.item) if r.item else None)
        urls = self.urls(r.note, r.keys)
        claim.views = [View(self.ids[url], said="The source this key gives." if self.texts.text(url) else "No text is held for this source.")
                       for url in urls if url in self.ids]
        claim.source_sha = self.source_sha(urls)
        return claim

    def quotation(self, r: research.Result) -> Claim:
        raw = self.raw(r.note, r.line_no)
        claim = self.claim(r, quote_place(raw, r.item))
        urls = self.urls(r.note, r.keys)
        matched = r.detail if r.status == "exact" and r.detail in urls else ""
        if matched:
            # The detail of a quotation found is the address it was found at, which the view says better.
            claim.detail = ""
        pins = self.pins(r.note, r.line_no)
        claim.source_sha = self.source_sha(urls)
        if r.status == "quotes_a_non_source":
            # The workspace says the quotation is of a document that isn't a source, so nothing is looked for.
            claim.views = [View(self.ids[url], said="The note attributes this quotation to a document the workspace says isn't a "
                                "source, so it isn't looked for in the sources the line cites.") for url in urls if url in self.ids]
            return claim
        for url in [matched] if matched else urls:
            if url not in self.ids:
                continue
            text = self.texts.text(url)
            if text is None:
                claim.views.append(View(self.ids[url], said="No text is held for this source, so the quotation wasn't looked for in it."))
                continue
            pin = pins.get(url)
            region: list[tuple[int, int]] = []
            if pin:
                region = pages.region(self.con, url, text, pin)[0] or []
            key = next((k for k in r.keys if url in self.checks.urls.get(r.note, {}).get(k, [])), "the source")
            spans = quote_spans(text, r.item)
            if spans:
                away = pin.where if pin and region and not pages.within(region, spans[0][0]) else ""
                hits = tuple((s, e, "quoted" + (f", away from {away}" if away else "")) for s, e in spans)
                if r.status == "not_in_source":
                    # Found in other capitals or with other marks between the words: the source's own are the fix.
                    said = "The words stand here, but not as the note writes them: the capitals or the marks between them differ."
                    if claim.suggestion is None and len(spans) == 1:
                        claim.suggestion = quote_suggestion(raw, r.line_no, r.item, text[spans[0][0]:spans[0][1]], key)
                elif away:
                    said = f"The words stand here, but not at {away}."
                    if pin and claim.suggestion is None:
                        claim.suggestion = pin_suggestion(self.con, raw, r.line_no, pin, url, text, spans[0][0])
                else:
                    said = "The quotation's words stand here."
                claim.views.append(View(self.ids[url], hits, (), tuple(region), said))
                continue
            closest = closest_passage(self.texts, url, r.item) if r.status == "not_in_source" else None
            if closest:
                start, end = closest
                claim.views.append(View(self.ids[url], ((start, end, "closest"),), (), tuple(region),
                                        "Not found word for word. This is the passage closest to it."))
                if claim.suggestion is None:
                    claim.suggestion = quote_suggestion(raw, r.line_no, r.item, text[start:end], key)
            else:
                claim.views.append(View(self.ids[url], (), (), tuple(region), "No passage of this source is close to the quotation."))
        return claim

    def arithmetic(self, r: research.Result) -> Claim:
        raw = self.raw(r.note, r.line_no)
        worked = self.workings.get((r.note, r.line_no, squeeze(r.item)))
        claim = self.claim(r, working_place(raw, r.item, worked.stated if worked else ""))
        if worked:
            claim.working = {"gives": worked.shown(), "stated": worked.stated, "working": worked.detail,
                             "inputs": [{"text": text, "claims": []} for text in worked.inputs], "traced": False}
            claim.suggestion = working_suggestion(raw, r.line_no, worked)
        return claim

    def figures(self, note: str, line_no: int, results: list[research.Result]) -> list[Claim]:
        """A claim for each figure of a row the number check judged: its own finding where it has one, else the row's."""
        line = self.lines.get((note, line_no))
        raw = self.raw(note, line_no)
        if line is None:
            return [self.claim(r, None) for r in results]
        body = research.row_body(line, self.checks)
        quantities = assay_numbers.quantities(body, research.POLICY)
        row_level = next((r for r in results if not r.item), results[0])
        urls = self.urls(note, line.keys)
        stems = research.label_words(" ".join([body, *self.headers.get((note, line_no), [])])).keys()
        pins = self.pins(note, line_no)
        line_sha = sha(raw.strip())
        source_sha = self.source_sha(urls)
        made: list[Claim] = []
        at = 0
        searchable = blank_keys(raw, self.checks.urls.get(note, {}))
        for quantity in quantities:
            own = next((r for r in results if r.item and r.item == quantity.text), None)
            span = place(searchable, quantity.text, at) or cjk_place(searchable, quantity.text, at)
            if span:
                at = span[1]
            if own:
                claim = self.claim(own, span, quantity.text)
            elif row_level.item:
                # The row's only results are other figures' findings: this one passed.
                claim = self.claim(row_level, span, quantity.text, "supported", "")
            else:
                claim = self.claim(row_level, span, quantity.text)
            if claim.status in ("supported", "not_in_source", "not_near_label", "not_on_cited_page", "not_in_cited_section"):
                claim.views = [figure_view(self.texts, self.ids[url], url, quantity.text, pins.get(url), stems)
                               for url in urls if url in self.ids]
            elif urls:
                claim.views = [View(self.ids[url], said="The row's figures weren't looked for in this source: "
                                    + (claim.detail or research.VERDICT[claim.status])) for url in urls if url in self.ids]
            if claim.status in ("not_on_cited_page", "not_in_cited_section"):
                for url in urls:
                    hits = [view.hits for view in claim.views if view.source == self.ids.get(url) and view.hits]
                    pin = pins.get(url)
                    if hits and pin:
                        claim.suggestion = pin_suggestion(self.con, raw, line_no, pin, url, self.texts.text(url) or "", hits[0][0][0])
                        break
            if span and raw[span[0]:span[1]] != claim.item:
                # The check names the figure as it read it, 551100000 for "551.1 百万": the page shows the line's own.
                claim.written = raw[span[0]:span[1]]
            claim.line_sha, claim.source_sha = line_sha, source_sha
            made.append(claim)
        if not quantities:
            made = [self.claim(r, None) for r in results]
        return made

    def link_inputs(self, claims: list[Claim]) -> None:
        """Name, for each input of a worked-out figure, the claims of figures in the same note with its digits."""
        by_digits: dict[tuple[str, Decimal], list[int]] = {}
        for number, claim in enumerate(claims):
            value = research.digits_of(claim.item) if claim.check == "numbers" and not claim.status.startswith("input") else None
            if value is not None:
                by_digits.setdefault((claim.note, value), []).append(number)
        for claim in claims:
            for given in (claim.working or {}).get("inputs", []):
                value = research.digits_of(given["text"])
                given["claims"] = by_digits.get((claim.note, value), []) if value is not None else []

    def links(self) -> list[dict[str, Any]]:
        """Each source key and address on a note's lines, with the sources it leads to, so a reader can open one."""
        found: list[dict[str, Any]] = []
        for note, lines in self.notes.items():
            known = self.checks.urls.get(note, {})
            for number, text in enumerate(lines, 1):
                for match in KEY_TOKEN.finditer(text):
                    ids = [self.ids[url] for url in known.get(match.group(1), []) if url in self.ids]
                    if ids:
                        found.append({"note": note, "line": number, "start": match.start(1), "end": match.end(1), "sources": ids})
                for match in URL.finditer(text):
                    url = clean_url(match.group(0))
                    if url in self.ids:
                        found.append({"note": note, "line": number, "start": match.start(), "end": match.end(), "sources": [self.ids[url]]})
        return found


def source_text(con: sqlite3.Connection, url: str) -> dict[str, Any]:
    """A source's stored text, with where each page starts and ends and the number printed on it, for the page to show."""
    row = con.execute("SELECT title, text FROM documents WHERE url=?", (url,)).fetchone()
    pages_kept = con.execute("SELECT page, start, end_at, folio FROM document_pages WHERE url=? ORDER BY page", (url,)).fetchall()
    return {"url": url, "title": (row[0] if row else "") or "", "text": (row[1] if row else None),
            "pages": [[page, start, end, folio or ""] for page, start, end, folio in pages_kept]}
