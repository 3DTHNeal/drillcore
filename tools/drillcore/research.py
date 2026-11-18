"""The research checks: what the notes say, held against the sources they cite.

- `citations`: every source key a line cites has an address, from its note's Sources list, the note it borrows from,
  or another note's list it names outright; and every entry in a list has an address that something cites.
- `quotations`: words in quotation marks appear exactly in the text of a source the line cites.
- `arithmetic`: a worked-out figure recomputes from its working, written in brackets after it or as a sum such as
  `150.4 + 43.2 = $193.6 million`. A worked-out row whose arithmetic can't be read is reported as such, never guessed at.
- `numbers`: the assay's number check, with its `MEASURED` policy, judges each row against the text of the sources it
  cites, never against the pool of everything fetched. Three things are read for it first. A figure a Chinese page
  counts in 万 or 亿 is written out in full (`cjk`), in the note and in the source alike. A table that states its unit
  once, in its first heading or the line leading into it, has each bare cell judged in that unit as well. And a
  source's line ends are read as one character each, so a figure a PDF wrapped is still one figure. Two things are
  read after. A figure the source holds only away from every word the row describes it by is a warning, since it may
  be the source's figure for something else. And on a worked-out row, each input of its working must be traced to a
  row of the notes this check judged, another working, or a source the row cites: the arithmetic can be right and its
  inputs made up.

A key cited with a pinpoint, as `S1 p.47` or `S1 §Note 12`, holds a quotation or a figure to that page or section of
its source (`pages`). One the source holds elsewhere fails as not on the page, or not in the section, cited.

The first three are the standalone commands `drillcore citations`, `quotes` and `arithmetic`, whose modules do the
work; this one turns what they find into results, so `check` reports what they report. The fourth is here alone.

A fifth, `sections`, runs only for a workspace whose settings name sections of the notes (`sections`). It reads what
the quotations and numbers checks judged, and says whether each named section has enough lines held to a source.

Each check gives a `Result` for each thing it looked at. A result passes, fails, wasn't judged, or is a warning, and
says why: a source whose text was never fetched, or a row that names no source, is neither a pass nor a failure, and
neither is a Sources entry nothing cites, though that's worth a look. A failure or a warning that a row of
checks/waivers.csv accepts is waived instead, with the waiver's reason; a waiver that has lapsed or matches nothing is
a warning of the check "waivers" (see `waivers`).

The assay is the deterministic fact checker in tools/assay, kept in this repository and mirrored into Pyrite. The
number check here is its `MEASURED` policy, and `quotes` reads text the way it does.
"""
import csv
import re
import sqlite3
from bisect import bisect_left
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation

from assay import numbers as assay_numbers
from assay import text as assay_text
from assay.findings import Finding

from . import arithmetic as arithmetic_check
from . import citations as citation_check
from . import cjk, formula, pages, sections, waivers
from . import quotes as quote_check
from .measures import MONEY, unit_stated
from .sourcedb import CJK, URL, NoteLine, doc_numbers, find_number, keys_by_note, note_files, note_lines, record_sources, table_headers, without_keys
from .workspace import Workspace

# The policy for evidence nobody wrote as a list of facts: a filing states its unit once in a table's heading and rounds
# as it pleases. Nothing is worked out under it, as under the default.
POLICY = assay_numbers.MEASURED
CHECKS = ("citations", "quotations", "arithmetic", "numbers")
PASS, FAIL, NOT_JUDGED, WARN = "pass", "FAIL", "not judged", "warning"
# A failure or a warning a person has accepted, by a row of checks/waivers.csv (see `waivers`).
WAIVED = "waived"
VERDICT = {
    # waivers: one that lapsed because what it was judged against changed, and one that matched nothing
    "lapsed_waiver": WARN, "unused_waiver": WARN,
    # citations: a key cited, then an entry in a Sources list and the fetching of its address
    "resolves": PASS, "unresolved": FAIL, "no_url": FAIL, "no_lender": FAIL, "unused": WARN,
    "not_fetched": NOT_JUDGED, "fetch_failed": NOT_JUDGED, "no_text": NOT_JUDGED,
    # quotations
    "exact": PASS, "not_in_source": FAIL, "quotes_a_non_source": NOT_JUDGED, "not_near_speaker": WARN,
    # quotations and numbers cited at a page or section
    "not_on_cited_page": FAIL, "not_in_cited_section": FAIL,
    # arithmetic
    "recomputes": PASS, "does_not_recompute": FAIL, "not_parsed": NOT_JUDGED,
    # numbers: a figure the source holds, and one it holds only away from every word the row describes it by
    "supported": PASS, "not_near_label": WARN,
    # numbers, on a worked-out row: the figures its working starts from, traced to the notes or a source
    "inputs_traced": PASS, "input_not_traced": WARN, "input_not_judged": NOT_JUDGED,
    # any check that needs a source
    "source_text_unavailable": NOT_JUDGED, "no_source_key": NOT_JUDGED,
    # sections a workspace names: enough lines under the heading held to a source, too few, none matching, or too few
    # until a source is fetched; and a rule that covers no note
    "covered": PASS, "thin": FAIL, "section_missing": FAIL, "section_not_judged": NOT_JUDGED, "unused_rule": WARN,
}
REPORT = "research_checks.csv"
# The checks that judge a line against the text of a source. When none of their results was judged, a run has shown
# nothing about the notes, however few failures it counts.
AGAINST_SOURCES = ("quotations", "numbers")
# Statuses that aren't judged by the workspace's own say-so, so even a strict run leaves them be.
DECLARED = frozenset({"quotes_a_non_source"})
# Where a line ends in a source, with the blanks around it. A PDF's text wraps a sentence wherever its page did, and on
# Windows ends each line with two characters, so "$31" at the end of one line and "million" at the start of the next
# were read as 31 and a stray word. Read as one line end, they're the one figure the sentence wrote.
LINE_END = re.compile(r"[ \t]*\r?\n[ \t]*")


@dataclass(frozen=True)
class Result:
    check: str
    note: str
    line_no: int
    status: str
    keys: tuple[str, ...]
    # What was judged: the key, the quotation, the arithmetic or the number, as the note writes it.
    item: str
    detail: str
    row_text: str
    # The waiver that accepts this finding, as the report gives it: why, who and when. "" when none does.
    waiver: str = ""
    # For arithmetic, what was worked: a row's own working or a table's total (`arithmetic.Result.kind`).
    part: str = ""

    @property
    def verdict(self) -> str:
        return WAIVED if self.waiver else VERDICT[self.status]

    @property
    def kind(self) -> str:
        """What one result counts, as a report would name it: a quotation, a source entry, a working or a table's
        total, a row of figures, one figure of a row, or an input of a worked-out row."""
        if self.check == "quotations":
            return "quotation"
        if self.check == "citations":
            return "entry"
        if self.check == "arithmetic":
            return self.part or arithmetic_check.WORKING
        if self.check == "numbers":
            if self.status.startswith("input"):
                return "input"
            return "figure" if self.status == "not_near_label" else "row"
        return self.check


class Sources:
    """The text behind each source key, read from the database once."""

    def __init__(self, ws: Workspace, con: sqlite3.Connection) -> None:
        self.con = con
        names = [path.name for path in note_files(ws)]
        self.borrows: dict[str, str] = ws.config().get("notes", {}).get("borrows", {})
        self.urls = keys_by_note(con, names, self.borrows)
        self._text: dict[str, str | None] = {}
        self._readable: dict[str, str] = {}
        self._numbers: dict[str, list[float]] = {}
        self._evidence: dict[tuple[str, pages.Pin | None], assay_numbers.Evidence] = {}
        self._joined: dict[tuple[tuple[str, pages.Pin | None], ...], assay_numbers.Evidence] = {}
        self._regions: dict[tuple[str, pages.Pin], tuple[pages.Region | None, str]] = {}
        self._places: dict[str, dict[str, tuple[list[Decimal], list[int]]]] = {}

    def text(self, url: str) -> str | None:
        if url not in self._text:
            row = self.con.execute("SELECT text FROM documents WHERE url=?", (url,)).fetchone()
            self._text[url] = row[0] if row and row[0] else None
        return self._text[url]

    def readable(self, note: str, keys: tuple[str, ...]) -> list[str]:
        """The addresses behind the keys whose text was fetched, in the order the keys are cited."""
        urls = dict.fromkeys(url for key in keys for url in self.urls[note].get(key, []))
        return [url for url in urls if self.text(url) is not None]

    def textless(self, note: str, keys: tuple[str, ...]) -> list[str]:
        """The keys cited that give an address but have no text behind any of theirs, so nothing was judged by them."""
        return [key for key in dict.fromkeys(keys)
                if self.urls[note].get(key) and all(self.text(url) is None for url in self.urls[note][key])]

    def numbers(self, url: str) -> list[float]:
        """Every number a source's text holds, in order of size, as `figures` reads them."""
        if url not in self._numbers:
            self._numbers[url] = doc_numbers(self.text(url) or "")
        return self._numbers[url]

    def chinese(self, url: str) -> bool:
        return len(CJK.findall((self.text(url) or "")[:20000])) > 50

    def matchable(self, url: str) -> str:
        """A source's text as the assay reads it, with figures counted in 万 or 亿 written out in full. Reading a long
        filing this way takes a moment, so it's done once."""
        if url not in self._readable:
            self._readable[url] = as_assay_reads(self.text(url) or "")
        return self._readable[url]

    def region(self, url: str, pin: pages.Pin) -> tuple[pages.Region | None, str]:
        """The stretches of a source's text a pinpoint names, or None and why they can't be read."""
        if (url, pin) not in self._regions:
            self._regions[url, pin] = pages.region(self.con, url, self.text(url) or "", pin)
        return self._regions[url, pin]

    def evidence(self, urls: list[str], pinned: dict[str, pages.Pin] | None = None) -> assay_numbers.Evidence:
        """What the sources state between them, each read only at the page or section `pinned` holds it to. Each is
        read on its own, so a number at the end of one and a scale word at the start of the next aren't read as one
        figure."""
        key = tuple((url, (pinned or {}).get(url)) for url in urls)
        if key not in self._joined:
            for url, pin in key:
                if (url, pin) not in self._evidence:
                    stretches = self.region(url, pin)[0] if pin else None
                    if stretches is None:
                        # The whole source: read once, for what it holds and where each figure stands.
                        self._read(url)
                        self._evidence[url, pin] = self._evidence[url, None]
                    else:
                        text = as_assay_reads(pages.region_text(self.text(url) or "", stretches))
                        self._evidence[url, pin] = assay_numbers.evidence(text, policy=POLICY)
            self._joined[key] = combined([self._evidence[part] for part in key])
        return self._joined[key]

    def _read(self, url: str) -> None:
        """Read every quantity a source states, once: what it holds, as the assay's `evidence` gives it under the
        measured policy, and where each figure stands. Reading a long filing takes seconds, so both come from one read."""
        if url in self._places:
            return
        found = assay_numbers.quantities(self.matchable(url), POLICY)
        self._evidence[url, None] = evidence_of(found)
        index: dict[str, list[tuple[Decimal, int]]] = {"number": [], "percent": []}
        for quantity in found:
            if quantity.kind in index and quantity.amount is not None:
                index[quantity.kind].append((quantity.amount, quantity.start))
        self._places[url] = {}
        for kind, held in index.items():
            held.sort()
            self._places[url][kind] = ([amount for amount, _ in held], [start for _, start in held])

    def places(self, url: str, claim: assay_numbers.Quantity) -> list[int]:
        """Where in a source's readable text the figure a claim states stands, as the assay would find it: the same
        value to the claim's precision, at any scale the measured policy allows a figure of its length. A percentage is
        found as a percentage, or as a bare number, as the policy reads one."""
        if url not in self._places:
            self._read(url)
        if claim.amount is None or claim.kind not in ("number", "percent"):
            return []
        slack = Decimal(5).scaleb(claim.exponent - 1)
        if claim.kind == "percent":
            readings = [("percent", 0), ("number", 0)]
        else:
            shifts = POLICY.shifts if claim.figures >= POLICY.figures else (0,)
            readings = [("number", shift) for shift in shifts]
        starts: list[int] = []
        for kind, shift in readings:
            amounts, at = self._places[url][kind]
            low, high = (claim.amount - slack).scaleb(-shift), (claim.amount + slack).scaleb(-shift)
            i = bisect_left(amounts, low)
            while i < len(amounts) and amounts[i] <= high:
                starts.append(at[i])
                i += 1
        return starts


def evidence_of(found: list[assay_numbers.Quantity]) -> assay_numbers.Evidence:
    """What `assay_numbers.evidence(text, policy=POLICY)` gives, from the quantities it would read in that text. The
    tests hold the two equal, so a change in the assay shows there."""
    def held(kind: str) -> frozenset[str]:
        return frozenset(q.value for q in found if q.kind == kind)

    def amounts(kind: str) -> tuple[Decimal, ...]:
        return tuple(sorted({q.amount for q in found if q.kind == kind and q.amount is not None}))

    return assay_numbers.Evidence(held("number"), held("percent"), held("spelled"), held("multiple"),
                                  amounts("number"), amounts("percent"), frozenset(q.form() for q in found if q.spaced))


def as_assay_reads(text: str) -> str:
    """A source's text as the assay reads it, with its line ends evened out and figures counted in 万 or 亿 written out."""
    return cjk.in_digits(assay_text.matchable(LINE_END.sub("\n", text)))


def combined(parts: list[assay_numbers.Evidence]) -> assay_numbers.Evidence:
    """Several sources' evidence as one."""
    if len(parts) == 1:
        return parts[0]
    return assay_numbers.Evidence(
        frozenset().union(*(p.numbers for p in parts)), frozenset().union(*(p.percents for p in parts)),
        frozenset().union(*(p.spelled for p in parts)), frozenset().union(*(p.multiples for p in parts)),
        tuple(sorted(set().union(*(p.number_amounts for p in parts)))),
        tuple(sorted(set().union(*(p.percent_amounts for p in parts)))), frozenset().union(*(p.spaced for p in parts)))


def body_of(line: NoteLine, known: dict[str, list[str]]) -> str:
    """A line as the checks read it: its web addresses gone, and its source keys blanked so "S11" isn't a number."""
    return without_keys(URL.sub(" ", line.text), known)


# ---------------------------------------------------------------- the standalone checks, as results

def citations(ws: Workspace, lines: list[NoteLine], sources: Sources) -> Iterator[Result]:
    """`drillcore citations`, as results: each key a line cites, then each problem with a Sources entry. A source not
    yet fetched, or whose fetch failed or gave no text, is an error there and not judged here: a citation stands on its
    key having an address."""
    texts = {(line.note, line.line_no): line.text for line in lines}
    found, findings = citation_check.examine(ws, sources.con)
    for cited in found:
        yield Result("citations", cited.note, cited.line, "resolves" if cited.status == "resolves" else "unresolved",
                     (cited.key,), cited.key, cited.detail, cited.text)
    for finding in findings:
        if finding.kind == "no_entry":
            continue  # Each is a citation above.
        yield Result("citations", finding.note, finding.line, finding.kind, (finding.key,) if finding.key else (), finding.key,
                     finding.message, texts.get((finding.note, finding.line), ""))


QUOTE_STATUS = {"exact": "exact", "not_near_speaker": "not_near_speaker", "not_found": "not_in_source", "no_text": "source_text_unavailable",
                "no_source": "no_source_key", "not_a_source": "quotes_a_non_source",
                "not_on_cited_page": "not_on_cited_page", "not_in_cited_section": "not_in_cited_section"}


def quotations(ws: Workspace, lines: list[NoteLine], sources: Sources) -> Iterator[Result]:
    """`drillcore quotes`, as results: each quotation, and the source that holds it or why none was found to."""
    texts = {(line.note, line.line_no): line.text for line in lines}
    for quote in quote_check.examine(ws, sources.con):
        yield Result("quotations", quote.note_file, quote.line_no, QUOTE_STATUS[quote.status], quote.keys, quote.text,
                     (quote.matched_url or "") if quote.status == "exact" else quote.detail,
                     texts.get((quote.note_file, quote.line_no), ""))


ARITHMETIC_STATUS = {"ok": "recomputes", "wrong": "does_not_recompute", "unparsed": "not_parsed"}


def arithmetic(workings: list[arithmetic_check.Result], lines: list[NoteLine]) -> Iterator[Result]:
    """`drillcore arithmetic`, as results: each working, and how it came out."""
    keys = {(line.note, line.line_no): line.keys for line in lines}
    for worked in workings:
        yield Result("arithmetic", worked.note, worked.line, ARITHMETIC_STATUS[worked.status], keys.get((worked.note, worked.line), ()),
                     worked.item, worked.why or worked.detail, worked.text, part=worked.kind)


# ---------------------------------------------------------------- numbers, by the assay

# What research notes write in digits that measures nothing (dates, years, period labels such as 9M 2025, identifiers
# and unit labels) is set aside by the measured policy itself, and an accounting negative, $(103,567) thousand, is
# read as that number. Before the assay's version 1.1 Drillcore did both here.


# A table often states its unit once: "US$M" as its first heading, "US$ millions except per share" as the line
# leading into it, or "(US$ millions; S1)" in the heading of the section it's in. A bare cell there, 6.2, claims $6.2
# million, and a release that says "$6.2 million" in a sentence supports it. So a cell the assay doesn't find as
# written is judged again in the table's unit, and passes on either reading: a per-share figure or a count in the same
# table is still found as written. Nothing else about the check moves, and a short figure still isn't matched across
# scales.
BARE = re.compile(r"\(?\d[\d,]*(?:\.\d+)?\)?")


@dataclass(frozen=True)
class Stated:
    """The units a table states for the figures in one of its rows: once for the whole table, in its first heading cell
    or the line leading into it, and for each column, in that column's heading, as "Cost ($M)" does. Then whether its
    first heading cell, and each column's heading, names a currency, as "Line (EUR)" does (`CURRENCY_NAMED`)."""
    table: str = ""
    columns: tuple[str, ...] = ()
    money: bool = False
    money_columns: tuple[bool, ...] = ()


# A currency named in a table's first heading cell, a column's heading or a row's label, as "Line (EUR)" or "Price
# (US$)" name one: the figures there are amounts of it, so a lowercase m or bn written against one is its scale, as it
# is after a currency sign ("EUR 46.3m"). Anywhere else 46.3m may be metres or minutes, and is read bare as before. A
# line leading into a table names a currency in passing too often to count.
CURRENCY_NAMED = re.compile(rf"{MONEY}(?![A-Za-z])")
CASH_SCALE = re.compile(r"(?P<letter>m|mn|bn)(?![A-Za-z\d²³])")
CASH_WORD = {"m": "million", "mn": "million", "bn": "billion"}


def currency_named(text: str) -> bool:
    return bool(CURRENCY_NAMED.search(text))


HEADING_MARKS = re.compile(r"^(#{1,6})\s")


def stated_units(text: str) -> dict[int, Stated]:
    """For each row of a note's or draft's tables, below its heading row, the units its table states, by line number:
    in its first heading cell, else the line leading into it, else the nearest heading above it that states one, as
    "### Inputs (US$ millions unless stated)" does for every table under it until the next heading of its level. A row
    whose table states no unit and names no currency isn't given."""
    units: dict[int, Stated] = {}
    lead_in = ""
    stated: Stated | None = None
    headings: list[tuple[int, str]] = []  # The headings above, as (level, the unit each states).
    for line_no, line in enumerate(text.splitlines(), 1):
        row = line.strip()
        if row.startswith("|"):
            if stated is None:
                heads = [cell.strip() for cell in row.strip("|").split("|")]
                above = next((unit for _, unit in reversed(headings) if unit), "")
                stated = Stated(unit_stated(heads[0]) or unit_stated(lead_in) or above, tuple(unit_stated(cell) for cell in heads),
                                currency_named(heads[0]), tuple(currency_named(cell) for cell in heads))
            elif stated.table or any(stated.columns) or stated.money or any(stated.money_columns):
                units[line_no] = stated
            continue
        if stated is not None or row.startswith("#"):
            stated, lead_in = None, ""
        if marks := HEADING_MARKS.match(row):
            level = len(marks.group(1))
            headings = [(above, unit) for above, unit in headings if above < level] + [(level, unit_stated(row))]
        elif row and not row.startswith("#"):
            lead_in = row
    return units


def table_units(ws: Workspace) -> dict[tuple[str, int], str]:
    """For each row of a table that states its unit once, that unit, by (note, line number). The unit is read from the
    table's first heading cell, or failing that from the line of prose that leads into the table, or from a heading
    above it (`stated_units`)."""
    return {(path.name, line_no): stated.table for path in note_files(ws)
            for line_no, stated in stated_units(path.read_text(encoding="utf-8")).items() if stated.table}


# A line that opens with a label ending in a colon, as "COMPUTED, US$ millions: 377.2 to 418.6" does. A unit the label
# states is the unit of the bare figures after it.
LABELLED = re.compile(r"^[-*+]?\s*(?P<label>[^:|\n]{1,80}):")


def unit_spans(text: str, stated: Stated | None) -> list[tuple[int, int, str]]:
    """The stretches of one line of a note or draft whose bare figures are in a unit stated elsewhere, as (start, end,
    unit): each cell of a table row past its label, in the unit its row's label states, else its column's heading,
    else its table; or the rest of a line after a label that states a unit."""
    if not text.lstrip().startswith("|"):
        labelled = LABELLED.match(text)
        unit = unit_stated(labelled.group("label")) if labelled else ""
        return [(labelled.end(), len(text), unit)] if labelled and unit else []
    bars = [at for at, char in enumerate(text) if char == "|"]
    spans = []
    label = text[bars[0] + 1:bars[1]] if len(bars) > 1 else ""
    for index in range(1, len(bars) - 1):
        column = stated.columns[index] if stated and index < len(stated.columns) else ""
        unit = unit_stated(label) or column or (stated.table if stated else "")
        if unit:
            spans.append((bars[index] + 1, bars[index + 1], unit))
    return spans


def unit_at(spans: list[tuple[int, int, str]], at: int) -> str:
    """The unit stated for a figure at a place in a line, or ""."""
    return next((unit for start, end, unit in spans if start <= at < end), "")


def money_spans(text: str, stated: Stated | None) -> list[tuple[int, int, str]]:
    """The cells of a table row, past its label, that hold amounts of a currency the row's label, the column's heading
    or the table's first heading cell names (`CURRENCY_NAMED`), as (start, end, "money")."""
    if not text.lstrip().startswith("|"):
        return []
    bars = [at for at, char in enumerate(text) if char == "|"]
    label = text[bars[0] + 1:bars[1]] if len(bars) > 1 else ""
    spans = []
    for index in range(1, len(bars) - 1):
        column = stated.money_columns[index] if stated and index < len(stated.money_columns) else False
        if currency_named(label) or column or (stated.money if stated else False):
            spans.append((bars[index] + 1, bars[index + 1], "money"))
    return spans


def scale_at(text: str, stated: Stated | None, start: int, end: int) -> str:
    """The unit a bare figure at text[start:end] of one line is in: written against it as a lowercase m or bn where
    the line holds amounts of a named currency (`money_spans`), as 46.3m under "Line (EUR)" is million; else the
    unit its line's label or its table states (`unit_spans`); else ""."""
    written = CASH_SCALE.match(text, end) if unit_at(money_spans(text, stated), start) else None
    return CASH_WORD[written.group("letter")] if written else unit_at(unit_spans(text, stated), start)


def bare_cell(finding: Finding, body: str) -> bool:
    """Whether what wasn't found is a bare figure in a cell past the row's label: one a table's unit could apply to."""
    return finding.kind == "number" and bool(BARE.fullmatch(finding.text)) and finding.start > body.find("|", 1) > 0


def in_stated_unit(finding: Finding, unit: str, held: assay_numbers.Evidence) -> bool:
    """Whether a bare figure the sources don't hold as written is one they hold in the unit its table states."""
    return not assay_numbers.number_findings(f"{finding.text} {unit}", held, POLICY)


def why_missing(finding: Finding, urls: list[str], sources: Sources) -> str:
    """What Drillcore's looser figure test makes of a number the assay didn't find: at another scale, in the digits of
    a page that counts in ten-thousands, or nowhere in the cited text."""
    written = re.search(r"\d[\d,]*(?:\.\d+)?", finding.text)
    if not written:
        return "absent from the cited source text as written"
    # The digits as written, without the scale the assay applied: `figures` tries the scales itself.
    digits = written.group(0).replace(",", "")
    value, decimals = float(digits), len(digits.split(".")[1]) if "." in digits else 0
    for url in urls:
        chinese = sources.chinese(url)
        kind, _ = find_number(sources.numbers(url), value, decimals, chinese)
        if kind:
            if kind.startswith("cjk"):
                return (f"the cited page is in Chinese and holds these digits ({kind}), but not as this figure: no unit of "
                        "ten thousand or a hundred million beside them gives it this scale")
            if kind == "exact":
                return "the digits are in the cited source, but not read there as this kind of figure or at this scale"
            return (f"the cited source holds it at another scale or precision ({kind}); the measured policy shifts scale "
                    f"only for a figure written to {POLICY.figures} or more digits")
    return "absent from the cited source text"


def unfound(body: str, held: assay_numbers.Evidence, unit: str) -> list[Finding]:
    """What the assay doesn't find of a row's figures in what the sources hold, a bare cell passing as written or in
    the unit its table states."""
    found = assay_numbers.number_findings(body, held, POLICY)
    if unit:
        found = [finding for finding in found if not (bare_cell(finding, body) and in_stated_unit(finding, unit, held))]
    return found


def row_body(line: NoteLine, sources: Sources) -> str:
    """A row as the number check reads it. A figure converted at a rate written beside it, as $510M in "$510M (RMB
    3.7bn at 7.25)", is in no source: the arithmetic check recomputes it, and the amount and the rate are still held to
    the source here. A figure named in braces, as {Revenue 2025}, is a name, not a figure the row states."""
    body = formula.without_references(arithmetic_check.without_conversions(body_of(line, sources.urls[line.note])))
    return cjk.in_digits(assay_text.matchable(body))


# ---------------------------------------------------------------- a figure in the source, but said of something else

# A figure the source holds isn't yet a figure the source says of the thing the row names: an annual report that gives
# a competitor's revenue of $910.0 million holds the 910.0 a row writes as the company's own. So each figure a row
# writes to three digits or more is found in the source, and the words around it are read: when none of the row's
# words is within NEAR characters of any place the source states the figure, it's a warning (`not_near_label`). A short
# figure stands in a long source in too many places to say anything, and a row whose words are all common ones has
# nothing to look for, so neither is warned about. A word matches on its first five letters, so "spending" finds "spend".
#
# A percentage is placed from two digits: economic figures are rates such as 3.1% or 4.3%, and a release that gives an
# unemployment rate of 4.3% often gives other rates of 4.3% too. It's found as a percentage or as the bare number, and
# holds when any place it stands is near a word of the row. "Rate", "percent" and "points" are left out of those words,
# since in a statistical release they stand beside every figure.
NEAR = 250
STEM = 5
PERCENT_FIGURES = 2
LABEL_WORD = re.compile(r"[^\W\d_]{4,}")
# An abbreviation joined by an ampersand, R&D, M&A or P&L, names a line as much as "research" does, so a draft's sentence
# and a line of the notes are bound by it (`describing_words`). It's read as capitals, as a report writes it. A row of the
# notes isn't held to it beside its figure in a source (`unlabelled`): a filing as often spells it out, "Research and
# development, net", and a row whose only describing word is R&D would be warned about wrongly.
JOINED = re.compile(r"(?<![\w&])[A-Z]{1,2}&[A-Z]{1,2}(?![\w&])")
NOT_LABELS = frozenset((
    "about", "above", "according", "across", "after", "again", "against", "along", "also", "among", "approximately",
    "around", "based", "because", "been", "before", "being", "below", "between", "both", "came", "come", "compared",
    "could", "down", "during", "each", "else", "even", "ever", "every", "fell", "from", "further", "gained", "grew",
    "grow", "growth", "have", "having", "here", "higher", "increase", "increased", "decrease", "decreased", "into", "item",
    "items", "just", "less", "lower", "made", "make", "many", "more", "most", "much", "near", "nearly", "only", "other",
    "over", "owing", "previous", "prior", "reached", "reaching", "roughly", "rose", "same", "some", "such", "than", "that",
    "their", "them", "then", "there", "these", "they", "this", "those", "through", "total", "under", "until", "upon",
    "versus", "very", "were", "what", "when", "where", "which", "while", "will", "with", "within", "would", "year",
    "years", "yearly", "figure", "figures", "source", "sources", "note", "notes", "said", "says", "stated", "stood",
    "company", "january", "february", "march", "april", "june", "july", "august", "september", "october", "november",
    "december", "quarter", "quarters", "half", "first", "second", "third", "fourth", "full", "fiscal", "period", "ended",
    "ending", "rate", "rates", "percent", "percentage", "points", "basis",
))


def label_words(text: str) -> dict[str, str]:
    """The words a row describes its figures by, as {stem: word}: those of four letters or more that say what a figure
    is, not when it was or how it moved."""
    return {word.lower()[:STEM]: word for word in LABEL_WORD.findall(text) if word.lower() not in NOT_LABELS}


def describing_words(text: str) -> dict[str, str]:
    """The words a draft's sentence or a line of the notes describes its figures by, as {stem: word}: `label_words`,
    and each abbreviation joined by an ampersand, such as R&D (`JOINED`)."""
    return {**label_words(text), **{word.lower(): word for word in JOINED.findall(text)}}


def unlabelled(claim: assay_numbers.Quantity, labels: dict[str, str], urls: list[str], sources: Sources) -> bool:
    """Whether a figure the sources hold stands, in every one of them, away from all the row's words. False when there
    is nothing to judge: a figure too short to place, or one the locator can't find (it was matched in a table's unit)."""
    if claim.figures < (PERCENT_FIGURES if claim.kind == "percent" else 3) or not labels:
        return False
    located = False
    for url in urls:
        text = sources.matchable(url)
        for start in sources.places(url, claim):
            located = True
            near = text[max(0, start - NEAR):start + NEAR].lower()
            if any(word.lower()[:STEM] in labels for word in LABEL_WORD.findall(near)):
                return False
    return located


def numbers(lines: list[NoteLine], sources: Sources, units: dict[tuple[str, int], str] | None = None,
            headers: dict[tuple[str, int], list[str]] | None = None) -> Iterator[Result]:
    """The assay's number check on each sourced row, against the text of the sources that row cites, at the page or
    section a pinpoint names. A worked-out row is left to the arithmetic check, as `figures` leaves it, and its inputs
    to `inputs`. `units` is what `table_units` read: a bare cell in a table that states its unit passes as written or in
    that unit. `headers` are the cells of each table row's header, whose words describe its figures as much as the
    row's own label does."""
    for line in lines:
        if line.kind != "row" or line.section != "notes" or line.worked_out:
            continue
        body = row_body(line, sources)
        claims = assay_numbers.quantities(body, POLICY)
        if not claims:
            continue
        if not line.keys:
            yield Result("numbers", line.note, line.line_no, "no_source_key", line.keys, "", "the row cites no source", line.text)
            continue
        urls = sources.readable(line.note, line.keys)
        if not urls:
            yield Result("numbers", line.note, line.line_no, "source_text_unavailable", line.keys, "",
                         "no text was fetched for the sources it cites", line.text)
            continue
        unit = (units or {}).get((line.note, line.line_no), "")
        pinned, unread = {}, ""
        for pin in line.pins:
            for url in sources.urls[line.note].get(pin.key, []):
                if url in urls:
                    stretches, why = sources.region(url, pin)
                    if stretches is None:
                        unread = unread or f"{pin.shown()} not judged: {why}"
                    else:
                        pinned[url] = pin
        found = unfound(body, sources.evidence(urls, pinned), unit)
        elsewhere = {(f.start, f.text) for f in unfound(body, sources.evidence(urls), unit)} if pinned and found else None
        # A row can cite a source whose text isn't held beside one whose text is: a JSON data file not listed to be
        # read, or a page that refused. Its figures are then judged by the readable one alone, and one that came from
        # the other fails. It stays a failure, and says what wasn't read, so the cause isn't taken for a wrong figure.
        textless = sources.textless(line.note, line.keys) if found else []
        blind = (f"; {' and '.join(textless)} {'is' if len(textless) == 1 else 'are'} cited here too, but no text is held for "
                 f"{'it' if len(textless) == 1 else 'them'}, so the figure wasn't looked for there") if textless else ""
        for finding in found:
            if elsewhere is not None and (finding.start, finding.text) not in elsewhere:
                pin = next(iter(pinned.values()))
                yield Result("numbers", line.note, line.line_no, pages.status_for(pin), line.keys, finding.text,
                             f"{finding.kind} {finding.value}: in the cited source, but not at "
                             + ", ".join(f"{p.where} of {p.key}" for p in dict.fromkeys(pinned.values())), line.text)
                continue
            also = f", nor as {finding.text} {unit}, the unit its table states" if unit and bare_cell(finding, body) else ""
            yield Result("numbers", line.note, line.line_no, "not_in_source", line.keys, finding.text,
                         f"{finding.kind} {finding.value}: {why_missing(finding, urls, sources)}{also}{blind}", line.text)
        if not found:
            yield Result("numbers", line.note, line.line_no, "supported", line.keys, "", unread, line.text)
        missing = {finding.start for finding in found}
        labels = label_words(" ".join([body, *(headers or {}).get((line.note, line.line_no), [])]))
        for claim in claims:
            if claim.start not in missing and unlabelled(claim, labels, urls, sources):
                named = ", ".join(sorted(labels.values(), key=str.lower)[:5])
                yield Result("numbers", line.note, line.line_no, "not_near_label", line.keys, claim.text,
                             f"the source holds it, but none of the row's words ({named}) is within {NEAR} characters of "
                             "it there, so it may be a figure for something else", line.text)


# ---------------------------------------------------------------- the inputs of a worked-out figure

# A working can recompute and still start from figures nobody can find: "+12.0% (640.2 against 571.6)" is right
# arithmetic whatever 640.2 and 571.6 are. So each input of a worked-out row's working must be traced: written in a row
# of the notes whose number check found it in its source, the result of another worked-out row that recomputes, or held
# by a source the worked-out row cites itself. An input that is none of these is a warning (`input_not_traced`), and one
# written only in a row the number check couldn't judge, for want of a source or its text, isn't judged either
# (`input_not_judged`). A small whole number (12 or under) and a power of ten are constants of the arithmetic, such as
# months or a unit, and aren't traced. An input is matched by its digits alone, wherever in the notes they're written.
DIGITS = re.compile(r"\d[\d,]*(?:\.\d+)?")
POWER_OF_TEN = re.compile(r"10*")


def digits_of(text: str) -> Decimal | None:
    """The first number a figure writes, as its digits alone: no sign, currency, scale or percent sign."""
    found = DIGITS.search(text)
    if not found:
        return None
    try:
        return Decimal(found.group(0).replace(",", ""))
    except InvalidOperation:
        return None


def constant(written: str) -> bool:
    """Whether an input is a constant of the arithmetic rather than a figure: a small whole number or a power of ten."""
    value = digits_of(written)
    if value is None or "%" in written or value != value.to_integral_value():
        return False
    return value <= 12 or bool(POWER_OF_TEN.fullmatch(str(int(value))))


def traced_figures(lines: list[NoteLine], sources: Sources, checked: list[Result],
                   workings: list[arithmetic_check.Result]) -> tuple[set[Decimal], set[Decimal]]:
    """The figures the notes have traced: each figure of a row the number check judged, but those it didn't find, and
    the result of each worked-out row that recomputes. Then the figures of rows it couldn't judge, for want of a source
    or its text: an input taken from one of those isn't judged either."""
    # A row the check judged gave a pass, or a failure for each figure it didn't find (in the source, or at its pinpoint).
    judged = {(r.note, r.line_no) for r in checked if r.status == "supported" or r.verdict == FAIL}
    unjudged = {(r.note, r.line_no) for r in checked if r.verdict == NOT_JUDGED}
    failed: dict[tuple[str, int], set[Decimal | None]] = {}
    for r in checked:
        if r.verdict == FAIL:
            failed.setdefault((r.note, r.line_no), set()).add(digits_of(r.item))
    traced: set[Decimal] = set()
    waiting: set[Decimal] = set()
    for line in lines:
        where = (line.note, line.line_no)
        if where in judged or where in unjudged:
            for claim in assay_numbers.quantities(row_body(line, sources), POLICY):
                value = digits_of(claim.text)
                if value is not None and value not in failed.get(where, set()):
                    (traced if where in judged else waiting).add(value)
    worked_out = {(line.note, line.line_no) for line in lines if line.worked_out}
    for working in workings:
        value = digits_of(working.stated)
        if working.status == "ok" and (working.note, working.line) in worked_out and value is not None:
            traced.add(value)
    return traced, waiting - traced


def inputs(lines: list[NoteLine], sources: Sources, checked: list[Result],
           workings: list[arithmetic_check.Result]) -> Iterator[Result]:
    """Each worked-out row's working, with its inputs traced: one pass when every input is, and a warning for each one
    that isn't. `checked` are the number check's results, which say which rows' figures were found in their sources."""
    traced, waiting = traced_figures(lines, sources, checked, workings)
    by_line = {(line.note, line.line_no): line for line in lines if line.worked_out and line.section == "notes"}
    for working in workings:
        line = by_line.get((working.note, working.line))
        if line is None or not working.inputs:
            continue
        urls = sources.readable(line.note, line.keys) if line.keys else []
        held = sources.evidence(urls) if urls else None
        loose = [written for written in working.inputs if not constant(written) and digits_of(written) not in traced
                 and not (held and not assay_numbers.number_findings(written, held, POLICY))]
        if not loose:
            yield Result("numbers", line.note, line.line_no, "inputs_traced", line.keys, working.item, "", line.text)
        for written in loose:
            if digits_of(written) in waiting:
                yield Result("numbers", line.note, line.line_no, "input_not_judged", line.keys, written,
                             f"an input of {working.item}, written in a row the number check couldn't judge, for want of "
                             "a source or its text", line.text)
                continue
            cited = "nor in a source the line cites" if urls else "and the line cites no source with text to hold it"
            yield Result("numbers", line.note, line.line_no, "input_not_traced", line.keys, written,
                         f"an input of {working.item}, but not in any row of the notes the number check judged, {cited}",
                         line.text)


# ---------------------------------------------------------------- all four

# ---------------------------------------------------------------- sections

# What a line of the notes came to, from the results of the checks that read the sources, best first: held to a
# source (judged against its text, whether it passed or not), waiting on a source whose text isn't held, or citing no
# source. A line with none of these was given nothing to judge against a source.
HELD, WAITING, UNSOURCED = "held", "waiting", "unsourced"
WAITING_ON = frozenset({"source_text_unavailable", "input_not_judged"})
# A worked-out row counts once its inputs are traced. One whose inputs aren't rests on nothing a source holds.
NOT_HELD = frozenset({"input_not_traced"})


def line_states(results: list[Result]) -> dict[tuple[str, int], str]:
    """What each line of the notes came to against its sources, by note and line number."""
    rank = {HELD: 0, WAITING: 1, UNSOURCED: 2}
    states: dict[tuple[str, int], str] = {}
    for r in results:
        if r.check not in AGAINST_SOURCES or r.status in DECLARED or r.status in NOT_HELD:
            continue
        if r.status in WAITING_ON:
            state = WAITING
        elif r.status == "no_source_key":
            state = UNSOURCED
        elif VERDICT[r.status] == NOT_JUDGED:
            continue
        else:
            state = HELD
        here = (r.note, r.line_no)
        if here not in states or rank[state] < rank[states[here]]:
            states[here] = state
    return states


def under(section: sections.Section, states: dict[tuple[str, int], str]) -> Counter[str]:
    """How many lines under a section's heading came to each state, and how many to none."""
    return Counter(states.get((line.note, line.line_no), "") for line in section.body)


def said_under(counts: Counter[str]) -> str:
    total = sum(counts.values())
    parts = [f"{counts[HELD]} held to a source" if counts[HELD] else "",
             f"{counts[WAITING]} waiting on a source with no text held" if counts[WAITING] else "",
             f"{counts[UNSOURCED]} citing no source" if counts[UNSOURCED] else "",
             f"{counts['']} with nothing the checks judge against a source" if counts[""] else ""]
    return f"Under it: {total} line{'' if total == 1 else 's'}" + (": " + ", ".join(p for p in parts if p) if total else "")


def coverage(ws: Workspace, lines: list[NoteLine], results: list[Result]) -> Iterator[Result]:
    """For each section the workspace's `[[check.sections]]` rules name, whether enough lines under its heading were
    held to a source. Nothing when the workspace names none."""
    rules = sections.rules(ws)
    if not rules:
        return
    states = line_states(results)
    notes = [path.name for path in note_files(ws)]
    for rule in rules:
        covered = [note for note in notes if rule.covers(note)]
        if not covered:
            yield Result("sections", "", 0, "unused_rule", (), ", ".join(rule.notes),
                         f"{rule.said()} covers {', '.join(rule.notes)}, which match{'es' if len(rule.notes) == 1 else ''} no note", "")
            continue
        for note, heading, found in sections.sections(rule, covered, lines):
            if not found:
                yield Result("sections", note, 0, "section_missing", (), heading,
                             f"no heading in the note matches, though {rule.said()} names it for this note", "")
            for section in found:
                counts = under(section, states)
                least = rule.min_sourced
                if counts[HELD] >= least:
                    status = "covered"
                elif counts[HELD] + counts[WAITING] >= least:
                    status = "section_not_judged"
                else:
                    status = "thin"
                yield Result("sections", note, section.heading.line_no, status, section.keys, heading,
                             f"{counts[HELD]} of {least} line{'' if least == 1 else 's'} held to a source. {said_under(counts)}",
                             section.text)


def results(ws: Workspace, con: sqlite3.Connection, workings: list[arithmetic_check.Result] | None = None,
            sources: Sources | None = None) -> list[Result]:
    """Run every check and return every result, writing no report. The notes are read afresh first, their URLs
    recorded as `sources` records them, as `drillcore citations` does. `workings` are the arithmetic check's own
    results, when the caller has them already. `sources` is what an earlier run read of the sources, for a caller that
    knows their text and the keys that lead to them haven't changed since; reading a long filing takes seconds."""
    record_sources(ws, con)
    lines = list(note_lines(ws, con))
    sources = sources or Sources(ws, con)
    workings = arithmetic_check.check(ws) if workings is None else workings
    headers = {(path.name, line_no): header for path in note_files(ws)
               for line_no, header in table_headers(path.read_text(encoding="utf-8")).items()}
    checked = list(numbers(lines, sources, table_units(ws), headers))
    found = [*citations(ws, lines, sources), *quotations(ws, lines, sources), *arithmetic(workings, lines),
             *checked, *inputs(lines, sources, checked, workings)]
    found += coverage(ws, lines, found)
    return waive(found, waivers.Ledger(ws, con))


def run(ws: Workspace, con: sqlite3.Connection) -> list[Result]:
    """Run every check, write data/research_checks.csv with each result that didn't pass, and return them all."""
    found = results(ws, con)
    ws.data.mkdir(parents=True, exist_ok=True)
    with (ws.data / REPORT).open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["check", "verdict", "status", "note_file", "line_no", "source_keys", "item", "detail", "row_text", "waiver"])
        writer.writerows([r.check, r.verdict, r.status, r.note, r.line_no, ",".join(r.keys), r.item, r.detail, r.row_text[:600], r.waiver]
                         for r in found if r.verdict != PASS)
    return found


def waive(results: list[Result], ledger: waivers.Ledger) -> list[Result]:
    """The results with each failure or warning a waiver accepts marked as waived. A waiver that has lapsed leaves its
    finding as it was and adds a warning saying what changed, and one that matched nothing adds a warning of its own,
    both under the check "waivers"."""
    out: list[Result] = []
    for result in results:
        # A section's waiver is held to every line of the section, which its result carries as its text.
        text = result.row_text if result.check == "sections" else None
        decision = ledger.decide(result.check, result.note, result.line_no, result.item, result.keys, text) \
            if result.verdict in (FAIL, WARN) else None
        if decision and not decision.lapsed:
            result = replace(result, waiver=decision.waiver.said())
        out.append(result)
        if decision and decision.lapsed:
            out.append(Result("waivers", result.note, result.line_no, "lapsed_waiver", result.keys, result.item,
                              waivers.lapsed_message(decision), result.row_text))
    for waiver in ledger.unused():
        out.append(Result("waivers", waiver.note, waiver.line_no or 0, "unused_waiver", (), waiver.item,
                          waivers.unused_message(waiver), ""))
    return out


def tally(results: list[Result]) -> Counter[tuple[str, str, str]]:
    """How many results each check gave, by verdict and status."""
    return Counter((r.check, r.verdict, r.status) for r in results)
