"""The assay as the judge of a draft. The notes are the draft's fact bank: a draft may state only what they support.

Each draft in the workspace's drafts folder (or each draft named) is held to the assay's checks. A draft is a Markdown
file, or a Word document or PDF that `drafts.read_draft` reads as text:

- `numbers`: every number, percentage, multiple and spelled-out number in the draft must be in the notes, with the
  same value and scale (the assay's `EXACT` policy). The notes are read without their Sources and Gaps and cautions
  sections, their web addresses and their source keys. A figure the notes don't hold, but the text of a source they
  cite does (the assay's `MEASURED` policy, which allows another scale or more decimal places), is a warning: it's
  supported by a source, not by the notes. Dates, years and identifiers are set aside first, as `check` sets them aside.
  A bare figure is read in the unit a line's label or its table states ("COMPUTED, US$ millions: 418.6", a table under
  "US$ millions" or a column headed "Cost ($M)"), in the notes and in the draft, and passes as written or in that unit.
  In a table that names its currency ("Line (EUR)"), a figure written with a lowercase m, 46.3m, is in millions.
  Thousands grouped by spaces, as a note quoting a source writes "58 000", are one number.
  A figure that rounds one the notes give more exactly, at the same scale and to the precision it's written to (7.4%
  for 7.36%), passes, and says so: it's listed with `--all` and in data/assay.csv as a pass with its reason. So does a
  bare figure that rounds one in the unit its own table states: (8.4) under "US$ millions" for the notes' (8,437)
  thousand.
  A figure the notes hold is held to what they hold it for, too: when every line of the notes that states it shares no
  word with the draft's sentence (its heading and its table's header count as the line's), it's a warning, since the
  figure may be one the notes give for something else, and it names the notes' lines most like the sentence. This is
  `check`'s test of a row against its source, here of a draft against its notes.
  When the notes give a figure the draft states only in another form, bare in a table that states no unit, or written
  another way, on a line that shares two words with the draft's sentence, the finding names that line and says to
  state the unit there, rather than naming a source that happens to hold the figure. Its verdict is what it was.
  A figure the notes hold is held to what they say it is, too, on the lines that give it for what the draft's sentence
  names (one describing word in common, or two for a figure as short as $3.8M or tenfold). Each of these is a warning:
  - when one of those lines works it out from figures `claims` matched to the SEC's facts, and the facts as filed
    don't give it to the place written (`filed`), and none of those lines states it from a source it cites: the draft
    copies a rounding of rounded figures, and the finding says what the facts as filed give;
  - when every one of those lines gives an amount as a change, near the figure ("$3.8M of incremental duty cost",
    "$2.1 million higher costs"), and the draft's sentence has no word of change: it states a change as a level;
  - when every one of those lines gives the figure as someone's estimate or claim ("a 10x estimated cost saving", "a
    vendor's claim"), and the draft's sentence neither says whose ("estimates", "says", "expects") nor names a source
    in brackets: it states an estimate as a fact.
- `titles`: a title or credential in the draft must be one the notes give, read whole. A title made of the notes' words
  but given by none of them, such as "Senior Vice President" from a senior engineer and a vice president, is a warning.
- `links`: every web address, domain or email in the draft must be one the notes write, Sources lists included, or the
  SEC's structured data for a company `[[sec.company]]` lists, which `claims` holds the notes to. An address the author
  knows the notes won't write, such as an article's DOI cited for a framework, passes when `[assay.accept_addresses]`
  names it whole and says why: a pass with that reason, and part of the seal.
- `names`: no confidential name listed in the settings may appear, however it's split, joined or pluralized, except
  where `[assay.allowed]` lets it stand: in a caption, a source line, a reference list or an in-text citation.
- `claims`: a sentence matching a pattern listed as unsupported fails, unless it names the claim only to deny it.
- `judgments`: a sentence matching a pattern listed as a judgment fails unless it says whose judgment it is ("in the
  author's view") or cites a source.
- `plans`: with `[assay] cutoff` set, a sentence about a plan or an expectation ("is planned to open", "expects")
  that dates it, after that word, to a period already begun by the data cut-off ("the second half of 2026", with a
  cut-off of 2026-10-31) is a warning: by then the plan had partly happened or slipped (`plans`).

A draft's reference list, under a heading such as "References", isn't judged for numbers, titles, claims or judgments:
its years, page ranges and filing numbers are no claims of the draft's, and `proof` reads its entries. Its addresses are
judged, and it's read for confidential names. Nor is a section that `[drafts] records` names, such as a log of prompts
quoted word for word, judged for anything but confidential names.

Every verdict is sealed: a hash of the draft's exact text, of the notes, of the fetched sources' text and of the rules
(the settings and the code that judged), so a recorded pass no longer vouches for a draft once any of them changes.
Each draft's verdict and seal go in the `assay_verdicts` table, and every result in data/assay.csv.

The settings, in the workspace's settings file:

    [assay]
    forbidden = ["Kestrel", "Project Osprey"]   # confidential names
    unsupported = ["record (?:year|quarter)"]   # claims the notes don't support, as regular expressions
    disclaimers = ["\\\\bnot\\\\b", "\\\\bnever\\\\b"]  # what opens a denial; a short list of negatives if left out
    judgments = ["\\\\bshould\\\\b"]               # opinions that must be attributed or cited, as regular expressions
    attributions = ["in the author's view"]     # what attributes one; `ATTRIBUTIONS` if left out
    cutoff = 2026-10-31                          # the day the data were closed: plans dated before it are warned of

    [assay.allowed]                             # where a confidential name may stand, any of: "captions",
    "Kestrel" = ["captions", "sources"]         # "sources", "references" and "citations"

    [assay.accept_addresses]                    # addresses the notes don't write, each with why it's accepted
    "https://doi.org/10.0000/frames.2019" = "a framework article; the notes hold none of its figures"

This reads the drafts and judges them. It never changes or writes one: the tool checks what a person wrote.
"""
import argparse
import csv
import dataclasses
import json
import re
import sqlite3
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import assay
from assay import claims as assay_claims
from assay import links as assay_links
from assay import names as assay_names
from assay import numbers as assay_numbers
from assay import seal as assay_seal
from assay import text as assay_text
from assay import titles as assay_titles
from assay.findings import Finding

from . import drafts, filed, history, plans, research
from .overlap import draft_files, drafts_folder, records
from .sourcedb import WORKED_OUT, cells, keys_by_note, note_files, note_lines, now, table_headers
from .workspace import Workspace, WorkspaceError

# The notes are the draft's fact bank, written for this purpose, so a figure must be there at the same value and scale,
# as under the assay's exact policy. What measures nothing (a date, a year, a period label, an identifier, a unit label)
# is set aside on both sides, as the measured policy does, and an accounting negative is read as its number. Thousands
# grouped by spaces, as a note quoting a source may write them ("58 000 or fewer"), are one number, as 58,000 is.
NOTES_POLICY = dataclasses.replace(assay_numbers.EXACT, set_aside=assay_numbers.MEASURED.set_aside, negatives=True,
                                   spaced_thousands=True)

CHECKS = ("numbers", "titles", "links", "names", "claims", "judgments", "plans")
PASS, WARN, FAIL = "pass", "warn", "fail"
# The row that gives a draft's verdict, with its seal as the item.
VERDICT = "verdict"
REPORT = "assay.csv"
# The parts of a note that are evidence. A Sources list gives addresses and a Gaps and cautions section says what the
# notes couldn't establish, so neither approves a figure.
EVIDENCE_SECTIONS = ("notes",)
# What opens a denial when the settings name nothing else: "has not set a record", "no record year", "never a record".
DISCLAIMERS = (r"\bnot\b", r"\bno\b", r"\bnever\b", r"n['’]t\b", r"\bwithout\b", r"\bneither\b", r"\bnor\b")
# What says whose a judgment is, when the settings name nothing else: "in the author's view", "the author's judgment",
# "in my view", "we estimate".
ATTRIBUTIONS = (r"\b(?:in|by) (?:the author['’]s|my|our) (?:view|judg(?:e)?ment|opinion|reading|estimate)",
                r"\bthe author['’]s (?:view|judg(?:e)?ment|opinion|reading|estimate|choice)",
                r"\b(?:chosen|judged|estimated|rated|read) by the author\b", r"\bthe author (?:judges|thinks|estimates|reads|chose)\b",
                r"\b(?:I|we) (?:judge|think|believe|estimate|consider|read|recommend)\b")
# Where a confidential name may be allowed to stand: in a caption (a line that opens "Exhibit E1." or "Figure 2:", or an
# image's description), after "Source:" on a line, under a References heading, or inside an in-text citation.
PLACES = ("captions", "sources", "references", "citations")
CAPTION = re.compile(r"^[\s*_>]*(?:(?:&#91;|\[)?\s*image:|(?:Exhibit|Figure|Fig\.|Table|Chart|Graph|Map)\s+[A-Z]?\d+[A-Za-z]?\s*[.:])", re.I)
SOURCE_LINE = re.compile(r"\bSources?\s*:", re.I)
REFERENCE_HEADING = re.compile(r"^#+\s*(?:\d+[.)]?\s*)?(?:References|Bibliography|Works cited|Reference list|Sources)\b", re.I)
CITATION = drafts.CITATION
# A year with a work's letter, as an author-date citation labels an author's second or eleventh work of a year: 2024b,
# 2024k. Inside a citation it measures nothing, though "2024k" elsewhere reads as 2,024 thousand.
CITED_YEAR = re.compile(r"\b(?:1[5-9]|20)\d{2}[a-z]\b")
# A conditional: "doubling its weight would put C ahead" is the draft's own what-if, so its multiple claims nothing.
HYPOTHETICAL = re.compile(r"\b(?:would|if)\b", re.I)
# A web address as a draft or a note writes one, with or without its scheme.
ADDRESS = re.compile(r"(?:https?://|www\.)[^\s)>\"'`\]]+", re.I)
# The SEC's structured data for one company, as `address` writes its address. `claims` holds the notes to it as facts
# rather than text, so for a company `[[sec.company]]` lists it's a source the workspace holds.
SEC_DATA = re.compile(r"^data\.sec\.gov/.*?CIK0*(?P<cik>\d+)", re.I)
# A run of characters around something `assay.links` found, which is the address a reader sees.
TOKEN = re.compile(r"[^\s()<>\[\]\"'`]+")
# The code that judges, beside the settings: a change to it means an old seal no longer vouches for a draft.
CODE = (Path(__file__), Path(research.__file__), Path(drafts.__file__), Path(plans.__file__), Path(filed.__file__),
        *sorted(Path(assay.__file__).parent.glob("*.py")))
# What makes a figure a change, on a line of the notes, near the figure: "$3.8M of incremental duty cost", "$4.4 million
# higher costs", "an increase of 12%". And what says so in a draft's sentence, anywhere in it.
AS_CHANGE = re.compile(r"\b(?:incremental|increase[sd]?\s+(?:of|in|by)|higher|lower|additional|added|extra|rise\s+(?:of|in)|"
                       r"rose\s+by|fell\s+by|decrease[sd]?\s+(?:of|in|by)|up\s+by|down\s+by)\b", re.I)
SAYS_CHANGE = re.compile(r"\b(?:incremental|increase[sd]?|increasing|higher|lower|additional|added|adds?|extra|rises?|rose|"
                         r"grew|grow|growth|fell|falls?|drop(?:ped)?|decline[sd]?|up|down|more|less|change[sd]?|gain|cut|"
                         r"savings?|over|against)\b", re.I)
# What makes a figure someone's estimate or claim, on a line of the notes near it: "a 10x estimated cost saving", "a
# vendor's claim", "according to". And what says whose it is, in a draft's sentence: a word of saying or estimating, or a
# source named in brackets, "(CIC, in the prospectus)" or "(Roe 2024)".
AS_ESTIMATE = re.compile(r"\b(?:estimated?|estimates|claims?|according to|marketing|vendor['’]s|projected|targets?)\b", re.I)
SAYS_WHOSE = re.compile(r"\b(?:estimat\w*|claim\w*|accord\w*|says?|said|states?|project\w*|forecast\w*|expects?|expected|"
                        r"targets?|guidance|outlook|assum\w*)\b|\(\s*[A-Z][^()]*?(?:\b\d{4}[a-z]?\b|n\.d\.|,)[^()]*\)")
# How far either side of a figure, on a line of the notes, a word that qualifies it may stand.
QUALIFIER_REACH = 60
# The words that mark a line's figures as worked out ("COMPUTED"): in a heading they say how, not what it's about.
MARKER_WORDS = frozenset(research.describing_words(" ".join(WORKED_OUT)))
# A money amount: a currency or a scale on the figure, so "$3.8M" is judged though it has two figures.
MONEY = re.compile(r"[$€£¥]|\b(?:US\$|USD|EUR|GBP|RMB|CNY)\b|\d\s?(?:[MBK]|bn|million|billion)\b")

SCHEMA = """
CREATE TABLE IF NOT EXISTS assay_verdicts (
    draft TEXT NOT NULL,
    seal TEXT NOT NULL,            -- a hash of the parts below
    verdict TEXT NOT NULL,         -- pass | warn | fail
    failures INTEGER NOT NULL,
    warnings INTEGER NOT NULL,
    parts TEXT NOT NULL,           -- JSON: the hash of the draft, the notes, the sources and the rules
    judged_at TEXT NOT NULL,
    PRIMARY KEY (draft, seal)
);
"""


@dataclass(frozen=True)
class Result:
    """One thing the judge found in a draft, or that a check found nothing."""
    draft: str      # the draft's file name
    line: int       # where it is in the draft; 0 for a check's pass or the draft's verdict
    check: str      # one of CHECKS, or VERDICT
    verdict: str    # PASS, WARN or FAIL
    item: str       # what was judged, as the draft writes it; for a verdict, the seal
    detail: str


@dataclass(frozen=True)
class Rules:
    """The `[assay]` settings, read and checked."""
    forbidden: tuple[str, ...] = ()
    unsupported: tuple[str, ...] = ()
    disclaimers: tuple[str, ...] = DISCLAIMERS
    # Where each confidential name may stand, by name: some of `PLACES`.
    allowed: tuple[tuple[str, tuple[str, ...]], ...] = ()
    judgments: tuple[str, ...] = ()
    attributions: tuple[str, ...] = ATTRIBUTIONS
    # The headings of a draft's sections that are records, not analysis (`[drafts] records`).
    records: tuple[str, ...] = ()
    # Web addresses the author accepts though the notes don't write them, each as `address` compares it, with why
    # (`[assay.accept_addresses]`).
    accepted: tuple[tuple[str, str], ...] = ()
    # The day the workspace's data were closed, as YYYY-MM-DD; "" when it isn't set (`[assay] cutoff`).
    cutoff: str = ""

    def places_for(self, name: str) -> tuple[str, ...]:
        return dict(self.allowed).get(name, ())

    def accepts(self, url: str) -> str | None:
        """Why the settings accept a web address the notes don't write, or None when they don't."""
        return dict(self.accepted).get(address(url))

    def name_patterns(self) -> list[tuple[str, str]]:
        """Each confidential name, with the pattern that blocks it however it's split, joined or pluralized. Every entry
        is a name, never a regular expression: one with other characters in it is matched as written."""
        patterns = []
        for name in self.forbidden:
            plain = assay_names.PLAIN_NAME.fullmatch(name) or assay_names.PLAIN_WORDS.fullmatch(name)
            patterns.append((name, assay_names.flexible(name) if plain else assay_names.widen(assay_names.term_pattern(name))))
        return patterns

    def digestible(self) -> dict[str, list[str]]:
        return {"forbidden": list(self.forbidden), "unsupported": list(self.unsupported), "disclaimers": list(self.disclaimers),
                "allowed": [f"{name}: {', '.join(places)}" for name, places in self.allowed],
                "judgments": list(self.judgments), "attributions": list(self.attributions), "records": list(self.records),
                "accepted addresses": [f"{url}: {why}" for url, why in self.accepted],
                **({"cutoff": [self.cutoff]} if self.cutoff else {})}


def rules(ws: Workspace) -> Rules:
    """The workspace's `[assay]` settings. Raises ValueError, saying what to fix, for one that can't be used."""
    found = ws.config().get("assay", {})
    if not isinstance(found, dict):
        raise ValueError(f"[assay] in {ws.config_path} must be a table of settings.")

    def strings(key: str, default: tuple[str, ...], regex: bool) -> tuple[str, ...]:
        given = found.get(key, list(default))
        if not isinstance(given, list) or not all(isinstance(entry, str) and entry.strip() for entry in given):
            raise ValueError(f"[assay] {key} in {ws.config_path} must be a list of words or patterns, none of them blank.")
        if regex:
            for entry in given:
                try:
                    re.compile(entry)
                except re.error as problem:
                    raise ValueError(f"[assay] {key} in {ws.config_path}: {entry!r} isn't a regular expression ({problem}).") from None
        return tuple(given)

    forbidden = strings("forbidden", (), False)
    allowed = found.get("allowed", {})
    if not isinstance(allowed, dict):
        raise ValueError(f"[assay.allowed] in {ws.config_path} must be a table: each confidential name, with a list of where it may stand.")
    places: list[tuple[str, tuple[str, ...]]] = []
    for name, given in allowed.items():
        if name not in forbidden:
            raise ValueError(f"[assay.allowed] in {ws.config_path} names {name!r}, which [assay] forbidden doesn't list.")
        if not isinstance(given, list) or not given or not all(place in PLACES for place in given):
            raise ValueError(f"[assay.allowed] {name!r} in {ws.config_path} must be a list of some of: {', '.join(PLACES)}.")
        places.append((name, tuple(given)))
    return Rules(forbidden, strings("unsupported", (), True), strings("disclaimers", DISCLAIMERS, True), tuple(places),
                 strings("judgments", (), True), strings("attributions", ATTRIBUTIONS, True), records(ws), accepted_addresses(ws, found),
                 cutoff(ws, found))


def cutoff(ws: Workspace, found: dict[str, Any]) -> str:
    """The day `[assay] cutoff` says the data were closed, as YYYY-MM-DD, or "" when it isn't set. A TOML date or a
    string in that form will do."""
    given = found.get("cutoff")
    if given is None:
        return ""
    try:
        return (given if isinstance(given, date) else date.fromisoformat(str(given).strip())).isoformat()
    except ValueError:
        raise ValueError(f"[assay] cutoff in {ws.config_path} must be a date, as cutoff = 2026-10-31.") from None


def accepted_addresses(ws: Workspace, found: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """The web addresses `[assay.accept_addresses]` accepts, each as `address` compares it, with why. Each is one
    address, matched whole: a domain accepts that domain written alone, never every page under it."""
    given = found.get("accept_addresses", {})
    where = f"[assay.accept_addresses] in {ws.config_path}"
    if not isinstance(given, dict):
        raise ValueError(f"{where} must be a table: each web address, with why it's accepted though the notes don't write it.")
    accepted = []
    for url, why in given.items():
        if not ADDRESS.fullmatch(url) and not assay_links.DOMAIN.fullmatch(url.split("/")[0]):
            raise ValueError(f"{where}: {url!r} isn't a web address.")
        if not isinstance(why, str) or not why.strip():
            raise ValueError(f"{where}: {url!r} must say why it's accepted, as a line of text.")
        accepted.append((address(url), why.strip()))
    return tuple(accepted)


def address(url: str) -> str:
    """A web address as it's compared: no scheme or www., the host in lowercase, no trailing punctuation or slash."""
    url = re.sub(r"^(?:https?://)?(?:www\.)?", "", url.rstrip(".,;:*!?"), flags=re.I).split("#")[0].rstrip("/")
    host, _, path = url.partition("/")
    return host.lower() + ("/" + path if path else "")


def sec_companies(ws: Workspace) -> frozenset[int]:
    """The SEC identifiers of the companies `[[sec.company]]` lists, whose structured data `claims` holds the notes to."""
    return frozenset(int(company["cik"]) for company in ws.config().get("sec", {}).get("company", [])
                     if isinstance(company, dict) and str(company.get("cik", "")).isdigit())


def sec_data(found: str, companies: frozenset[int]) -> bool:
    """Whether an address, as `address` writes it, is the SEC's structured data for one of the companies given."""
    sec = SEC_DATA.match(found)
    return sec is not None and int(sec.group("cik")) in companies


@dataclass(frozen=True)
class Row:
    """One line of the notes that states figures, as a draft's figure is bound to it."""
    figures: assay_numbers.Evidence
    # The words it describes its figures by, with its heading's and its table header's, as `research.describing_words` gives.
    labels: dict[str, str]
    # Where it is, as note:line, and its text, for a finding that points a reader at it.
    where: str = ""
    text: str = ""
    # Whether the line, its heading or the prose leading into it says its figures were worked out ("COMPUTED"), so
    # `check` recomputes it and traces its inputs to their sources.
    worked_out: bool = False
    # Whether it states its figures from a source it cites itself, rather than working them out.
    sourced: bool = False
    # The words of what the line is about rather than what it measures: its heading's, and a table row's first cell, where
    # notes name the company or the item ("Larkspur Printing: ratios", "| Ostrava Labs |"), not the column's measure.
    subject: frozenset[str] = frozenset()


def scaled(read: str, stated: research.Stated | None) -> str:
    """The bare figures of a line of the notes that a unit stated elsewhere applies to, each written out in that unit,
    as "418.6 million" for the 418.6 of "COMPUTED, US$ millions: ... 418.6", or "" for none. Read beside the line, they
    let a draft's $418.6M be the figure the notes give, as `check` reads a table's unit against a source. A figure
    written with a lowercase m in a table that names its currency, 46.3m under "Line (EUR)", is in millions too
    (`research.scale_at`)."""
    if not research.unit_spans(read, stated) and not research.money_spans(read, stated):
        return ""
    return " ".join(f"{format(q.amount, 'f')} {unit}" for q in assay_numbers.quantities(read, NOTES_POLICY)
                    if q.kind == "number" and q.amount is not None and research.BARE.fullmatch(q.text)
                    and (unit := research.scale_at(read, stated, q.start, q.end)))


def note_rows(ws: Workspace, con: sqlite3.Connection) -> tuple[list[str], list[Row]]:
    """The notes as a draft's evidence: each line outside their Sources and Gaps and cautions sections as the checks
    read it, its bare figures again in the unit its label or table states, and each line of those that states a figure,
    with the words that describe it."""
    paths = note_files(ws)
    names = [path.name for path in paths]
    known = keys_by_note(con, names, ws.config().get("notes", {}).get("borrows", {}))
    texts = {path.name: path.read_text(encoding="utf-8-sig") for path in paths}
    headers = {name: table_headers(text) for name, text in texts.items()}
    units = {name: research.stated_units(text) for name, text in texts.items()}
    lines: list[str] = []
    rows: list[Row] = []
    for line in note_lines(ws, con):
        if line.section not in EVIDENCE_SECTIONS:
            continue
        read = assay_text.matchable(research.body_of(line, known[line.note]))
        # The figures again in the unit the line's label or its table states, kept apart from its words.
        stated = "\n".join(filter(None, (read, scaled(read, units[line.note].get(line.line_no)) if line.kind != "heading" else "")))
        lines.append(stated)
        if line.kind != "heading" and assay_numbers.quantities(read, NOTES_POLICY):
            described = " ".join([read, line.heading, *headers[line.note].get(line.line_no, [])])
            rows.append(Row(assay_numbers.evidence(stated, policy=NOTES_POLICY), research.describing_words(described),
                            f"{line.note}:{line.line_no}", line.text, line.worked_out,
                            bool(line.keys) and line.basis == "row" and not line.worked_out,
                            frozenset(research.describing_words(" ".join([line.heading, *cells(line.text)[:1]])))
                            - MARKER_WORDS))
    return lines, rows


@dataclass
class FactBank:
    """What the notes give a draft to work from, read once for every draft judged."""
    # The figures the notes state, outside their Sources and Gaps and cautions sections.
    numbers: assay_numbers.Evidence
    # The web addresses the notes write, as `address` compares them, and their domains and emails as the assay reads them.
    addresses: set[str]
    links: set[str]
    # The fetched text of every source the notes cite, by address.
    sources: dict[str, str]
    # Hashes of each note's file and each source's text, for the seal.
    notes_digest: str
    sources_digest: str
    # Each line of the notes that states a figure, and the titles the notes give.
    rows: list[Row] = field(default_factory=list)
    titles: assay_titles.Held = field(default_factory=lambda: assay_titles.held_titles(""))
    # The companies whose SEC structured data the workspace loads (`sec_companies`).
    companies: frozenset[int] = frozenset()
    # The notes' worked-out figures that the facts as filed don't give to the place written (`filed`), by line.
    refiled: dict[str, list[filed.Refiled]] = field(default_factory=dict)
    _measured: dict[str, assay_numbers.Evidence] = field(default_factory=dict)

    def measured(self, url: str) -> assay_numbers.Evidence:
        """A source's figures, read for the measured policy. A long filing takes a moment to read, so it's read once."""
        if url not in self._measured:
            self._measured[url] = assay_numbers.evidence(assay_text.matchable(self.sources[url]), policy=assay_numbers.MEASURED)
        return self._measured[url]


def fact_bank(ws: Workspace, con: sqlite3.Connection) -> FactBank:
    """The notes, read as a draft's evidence."""
    paths = note_files(ws)
    names = [path.name for path in paths]
    lines, rows = note_rows(ws, con)
    body = "\n".join(lines)
    whole = "\n".join(path.read_text(encoding="utf-8-sig") for path in paths)
    sources: dict[str, str] = {}
    if names:
        held = research.Sources(ws, con)
        marks = ",".join("?" * len(names))
        for (url,) in con.execute(f"SELECT DISTINCT url FROM sources WHERE note_file IN ({marks}) ORDER BY url", names):  # noqa: S608
            text = held.text(url)
            if text is not None:
                sources[url] = text
    refiled: dict[str, list[filed.Refiled]] = {}
    try:
        for found in filed.refile(ws, con):
            refiled.setdefault(found.where, []).append(found)
    except WorkspaceError:
        pass  # A workspace rule `arithmetic` can't read: that command says so; the draft is judged without this.
    return FactBank(
        numbers=assay_numbers.evidence(body, policy=NOTES_POLICY),
        addresses={address(match.group(0)) for match in ADDRESS.finditer(whole)},
        links=assay_links.own_links(whole),
        sources=sources,
        notes_digest=assay_seal.value_digest({path.name: assay_seal.file_digest(path) for path in paths}),
        sources_digest=assay_seal.value_digest({url: assay_seal.digest(text.encode()) for url, text in sources.items()}),
        rows=rows,
        titles=assay_titles.held_titles(body),
        companies=sec_companies(ws),
        refiled=refiled,
    )


# ---------------------------------------------------------------- the checks, each on one draft

# What a check found: the line, the verdict, the item as the draft writes it, and why.
Found = tuple[int, str, str, str]


def _line(text: str, at: int) -> int:
    return text.count("\n", 0, at) + 1


def draft_unit(body: str, found: Finding | assay_numbers.Quantity, units: dict[int, research.Stated]) -> str:
    """The unit a bare figure of a draft is in, as its own table or line label states it (`research.scale_at`), or ""
    for none: a cell 418.6 under "US$ millions" is in millions."""
    if found.kind != "number" or not research.BARE.fullmatch(found.text):
        return ""
    begins = body.rfind("\n", 0, found.start) + 1
    ends = body.find("\n", found.start)
    line = body[begins:ends if ends >= 0 else len(body)]
    return research.scale_at(line, units.get(_line(body, found.start)), found.start - begins, found.end - begins)


def read_in_unit(body: str, found: Finding | assay_numbers.Quantity, units: dict[int, research.Stated]
                 ) -> tuple[assay_numbers.Quantity | None, str]:
    """A bare figure of a draft read in the unit its own table or line label states, with that unit, as a cell (8.4)
    under "US$ millions" is 8.4 million to the hundred thousand; (None, "") when none is stated."""
    unit = draft_unit(body, found, units)
    read = [q for q in assay_numbers.quantities(f"{found.text} {unit}", NOTES_POLICY) if q.kind == "number"] if unit else []
    return (read[0], unit) if len(read) == 1 else (None, "")


def in_draft_unit(body: str, found: Finding, bank: FactBank, units: dict[int, research.Stated]) -> bool:
    """Whether a bare figure of a draft that the notes don't hold as written is one they hold in the unit the draft's
    own table or line label states, as a cell 418.6 under "US$ millions" is $418.6 million."""
    unit = draft_unit(body, found, units)
    return bool(unit) and not assay_numbers.number_findings(f"{found.text} {unit}", bank.numbers, NOTES_POLICY)


# A figure written to fewer digits than this is not taken as a rounding of the notes: a lone 2% would round anything
# from 1.5% to 2.5%.
ROUNDED_FIGURES = 2
# How many describing words a line must share with a sentence before a rounding on it outweighs the same figure on a
# line about something else, or before a figure it gives in another form is taken to be the sentence's.
BOUND_WORDS = 2


def rounding(body: str, bank: FactBank, missing: list[Finding], units: dict[int, research.Stated] | None = None
             ) -> dict[Finding, tuple[Decimal, str]]:
    """Each figure the notes don't hold as written that rounds one they give more exactly, at the same scale and to the
    precision the draft writes it to, with that figure and the unit the figure was read in: 7.4% for the notes' 7.36%,
    as written (""). A bare figure that doesn't is read again in the unit its own table or label states, as `in_draft_unit`
    reads one, so a cell (8.4) under "US$ millions" rounds the notes' (8,437) in thousands ("million")."""
    claims = {(q.start, q.end): q for q in assay_numbers.quantities(body, NOTES_POLICY)}
    found: dict[Finding, tuple[Decimal, str]] = {}
    for finding in missing:
        claim = claims.get((finding.start, finding.end))
        if claim is None or claim.figures < ROUNDED_FIGURES:
            continue
        given = assay_numbers.rounds(bank.numbers, claim)
        if given is not None:
            found[finding] = given, ""
            continue
        in_unit, unit = read_in_unit(body, finding, units or {})
        given = assay_numbers.rounds(bank.numbers, in_unit) if in_unit else None
        if given is not None:
            found[finding] = given, unit
    return found


def _shown(amount: Decimal, kind: str) -> str:
    """A figure of the notes as a finding names it: 7.36%, or 37600000."""
    text = format(amount.normalize(), "f")
    return text + ("%" if kind == "percent" else "")


def without_cited_years(body: str) -> str:
    """`body` with the lettered year of each in-text citation, as in (Acme Ltd. 2024k), written as blank space of its
    length: a work's label, not a figure. Everything else keeps its place, so line numbers and offsets hold."""
    return CITATION.sub(lambda cited: CITED_YEAR.sub(lambda year: " " * len(year.group()), cited.group()), body)


def check_numbers(draft: str, bank: FactBank) -> Iterator[Found]:
    """Each figure the notes don't hold exactly: a pass, labelled, when it rounds a figure they give more exactly; a
    warning when a cited source holds it as measured; else a failure. A bare figure in a draft's table or after a label
    that states a unit passes when the notes hold it in that unit. A citation's lettered year isn't a figure."""
    body = without_cited_years(assay_text.matchable(draft))
    units = research.stated_units(body)
    missing = [found for found in assay_numbers.number_findings(body, bank.numbers, NOTES_POLICY)
               if not in_draft_unit(body, found, bank, units)]
    rounded = rounding(body, bank, missing, units)
    for found, (given, unit) in rounded.items():
        read = f"read in {unit}s, as its table or label states, it " if unit else ""
        yield (_line(body, found.start), PASS, found.text,
               f"{found.kind} {found.value}: {read}rounds {_shown(given, found.kind)}, which the notes give")
    missing = [found for found in missing if found not in rounded]
    support: dict[Any, str] = {}
    remaining = list(missing)
    for url in bank.sources:
        if not remaining:
            break
        unheld = {(found.start, found.end) for found in assay_numbers.number_findings(body, bank.measured(url), assay_numbers.MEASURED)}
        support.update({found: url for found in remaining if (found.start, found.end) not in unheld})
        remaining = [found for found in remaining if found not in support]
    claims = {(q.start, q.end): q for q in assay_numbers.quantities(body, NOTES_POLICY)}
    for found in missing:
        said = f"{found.kind} {found.value}: "
        claim = claims.get((found.start, found.end))
        sentence = sentence_at(body, found.start)
        if found.kind == "multiple" and HYPOTHETICAL.search(sentence):
            yield (_line(body, found.start), PASS, found.text,
                   said + "a multiple in a conditional sentence, the draft's own what-if, not a claim about the world")
            continue
        home = held_otherwise(bank, claim, research.describing_words(sentence)) if claim else None
        if home is not None:
            # The line the figure comes from, most likely, is a better pointer than a source that happens to hold it.
            also = f"; a source they cite holds it as written ({support[found]})" if found in support else ""
            yield (_line(body, found.start), WARN if found in support else FAIL, found.text,
                   said + otherwise(home, sentence, found.text) + also)
        elif found in support:
            yield (_line(body, found.start), WARN, found.text,
                   said + f"supported by a source, not by the notes ({support[found]})")
        elif bank.sources:
            yield _line(body, found.start), FAIL, found.text, said + "not in the notes, nor in the text of a source they cite"
        else:
            yield _line(body, found.start), FAIL, found.text, said + "not in the notes, and no source they cite has been fetched"
    yield from unbound(body, bank, {found.start for found in missing}, units)
    yield from qualifiers(body, bank)


def rounded_on(row: Row, claim: assay_numbers.Quantity, in_unit: assay_numbers.Quantity | None, unit: str
               ) -> tuple[Decimal | None, str]:
    """The figure a line of the notes gives that a draft's figure rounds, as written, or else read in the unit its
    draft's table states, with that unit ("" as written); (None, "") for none."""
    given = assay_numbers.rounds(row.figures, claim)
    if given is not None:
        return given, ""
    given = assay_numbers.rounds(row.figures, in_unit) if in_unit is not None else None
    return (given, unit) if given is not None else (None, "")


def held_otherwise(bank: FactBank, claim: assay_numbers.Quantity, words: dict[str, str]) -> Row | None:
    """The line of the notes about what a draft's sentence says (`BOUND_WORDS` describing words in common, the most
    first) that gives its figure only in another form: bare, in a table or line that states no unit, or written
    another way, as the measured policy reads a source. It's the line to give the unit on. None when there's none."""
    about = [(shared, row) for row in bank.rows if (shared := len(set(row.labels) & set(words))) >= BOUND_WORDS
             and assay_numbers.holds(row.figures, claim, assay_numbers.MEASURED)]
    return max(about, key=lambda found: found[0])[1] if about else None


def otherwise(row: Row, sentence: str, figure: str) -> str:
    """What a finding says of a figure the notes give only in another form, on a line about the same thing."""
    return (f"the notes give it only in another form, or in no unit they state, on a line about this: "
            f"{nearest([row], sentence, figure)}. State its unit there, in the line's label or its table's first cell "
            f"or a heading above it, or write it there as the draft does")


# Where a sentence ends: at a full stop, question or exclamation mark before a space, or where a new Markdown block
# starts (a blank line, a heading, a list item, a table row or a quotation). A paragraph wrapped over several lines is
# still one run of sentences, so a line break inside it ends nothing.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n(?=[ \t]*(?:\n|#|[-*+][ \t]|\||>|\d+[.)][ \t]))")


def sentence_at(text: str, at: int) -> str:
    """The sentence of a text that holds the place given."""
    start, end = 0, len(text)
    for match in SENTENCE_END.finditer(text):
        if match.end() <= at:
            start = match.end()
        elif match.start() > at:
            end = match.start()
            break
    return text[start:end]


def unbound(body: str, bank: FactBank, missing: set[int], units: dict[int, research.Stated] | None = None) -> Iterator[Found]:
    """Each figure the notes hold, where every line holding it shares no word with the draft's sentence. A figure too
    short to say anything, as `check` judges one, and a sentence or line with no word that describes a figure, have
    nothing to compare, so neither is warned about. A bare figure in a draft's table that states its unit is held, and
    rounded, in that unit too (`read_in_unit`)."""
    for claim in assay_numbers.quantities(body, NOTES_POLICY):
        if (claim.start in missing or claim.kind not in ("number", "percent")
                or claim.figures < (research.PERCENT_FIGURES if claim.kind == "percent" else 3)):
            continue
        words = research.describing_words(sentence_at(body, claim.start))
        in_unit, unit = read_in_unit(body, claim, units or {})
        holding = [row for row in bank.rows if assay_numbers.holds(row.figures, claim, NOTES_POLICY)
                   or in_unit is not None and assay_numbers.holds(row.figures, in_unit, NOTES_POLICY)]
        # One describing word in common binds a figure to a line. Asking two of a figure as short as 4.5% was tried on a
        # report a reviewer had read: it added many warnings, and none was an error the reviewer had found.
        if not words or not holding or any(not row.labels or set(row.labels) & set(words) for row in holding):
            continue
        # The same figure on a line about something else, and a more exact one on a line about this: 8.5% where the
        # notes give 8.54% for what the sentence names and 8.5% for another thing. It's that rounding. One word in
        # common is too easily chance for a figure as short as 4.5%, so the line must share two with the sentence.
        about = []
        for row in bank.rows if claim.figures >= ROUNDED_FIGURES else []:
            if len(set(row.labels) & set(words)) >= BOUND_WORDS:
                given, read = rounded_on(row, claim, in_unit, unit)
                if given is not None:
                    about.append((row, given, read))
        about.sort(key=lambda found: -len(set(found[0].labels) & set(words)))
        if about:
            row, given, read = about[0]
            said = f"read in {read}s, as its table or label states, it " if read else ""
            yield (_line(body, claim.start), PASS, claim.text,
                   f"{claim.kind} {claim.form()}: {said}rounds {_shown(given, claim.kind)}, which the notes give at {row.where}")
            continue
        home = held_otherwise(bank, claim, words)
        if home is not None:
            yield (_line(body, claim.start), WARN, claim.text,
                   f"{claim.kind} {claim.form()}: in the notes as written only on lines about other things, and "
                   + otherwise(home, sentence_at(body, claim.start), claim.text))
            continue
        yield (_line(body, claim.start), WARN, claim.text,
               f"{claim.kind} {claim.form()}: in the notes, but only on lines about other things, none of whose words "
               f"this sentence uses, so it may be a figure for something else. Nearest: "
               f"{nearest(holding, sentence_at(body, claim.start), claim.text)}")


# How far above a table its caption may stand: the line just before it, or one more with a blank between.
CAPTION_REACH = 2


def context_at(text: str, at: int) -> str:
    """The sentence of a text that holds the place given, and for a figure in a table's row, what the row leaves to
    the table: its column's header and the caption just above the table. A row of a table captioned "Larkspur Printing,
    2021 to 2025" reads "| 2022 | 651.5 | -4.5% |" and names no company; the caption and the header "Net margin" say
    what the -4.5% is, as a note's heading and table header say what its row's figures are."""
    sentence = sentence_at(text, at)
    start = text.rfind("\n", 0, at) + 1
    end = text.find("\n", at)
    row = text[start:len(text) if end < 0 else end]
    if not row.lstrip().startswith("|"):
        return sentence
    lines = text[:start].splitlines()
    above = len(lines)
    while above and lines[above - 1].lstrip().startswith("|"):
        above -= 1
    table = lines[above:]
    header = cells(table[0]) if table else []
    column = row[:at - start].count("|") - 1
    named = header[column] if 0 <= column < len(header) and not re.fullmatch(r"[\s\-:|]*", header[column]) else ""
    caption = next((line.strip() for line in reversed(lines[max(0, above - CAPTION_REACH):above]) if line.strip()), "")
    return " ".join(part for part in (sentence, named, caption) if part)


# A year a table's first cell or its caption names.
YEAR = re.compile(r"\b(?:19|20)\d\d\b")
# The scales a bare figure of a working may be in, read as a table or label states them.
SCALES = ("", " million", " billion", " thousand")


def _row_year(text: str) -> int | None:
    """The year a table row is for, when its first cell is one."""
    first = cells(text)[0] if text.lstrip().startswith("|") else ""
    return int(first) if YEAR.fullmatch(first) else None


def year_at(text: str, at: int) -> int | None:
    """The year a figure in a draft's table is for: its row's first cell when that is a year, or else the one year its
    table's caption names ("Cross-sectional: 2025"). None outside a table, or where neither says one year."""
    start = text.rfind("\n", 0, at) + 1
    end = text.find("\n", at)
    row = text[start:len(text) if end < 0 else end]
    if not row.lstrip().startswith("|"):
        return None
    if (year := _row_year(row)) is not None:
        return year
    lines = text[:start].splitlines()
    above = len(lines)
    while above and lines[above - 1].lstrip().startswith("|"):
        above -= 1
    caption = next((line for line in reversed(lines[max(0, above - CAPTION_REACH):above]) if line.strip()), "")
    years = set(YEAR.findall(caption))
    return int(years.pop()) if len(years) == 1 else None


def _bound(body: str, bank: FactBank, claim: assay_numbers.Quantity, sentence: str | None = None
           ) -> tuple[str, list[Row]]:
    """The draft's sentence around a figure, or the wider context given (`context_at`), and the lines of the notes that
    give the figure for what it names: those that share a describing word with it, or two for a figure as short as
    $3.8M or tenfold, which one word in common binds too easily by chance."""
    sentence = sentence_at(body, claim.start) if sentence is None else sentence
    words = research.describing_words(sentence)
    needed = 1 if claim.figures >= 3 else BOUND_WORDS
    return sentence, [row for row in bank.rows if assay_numbers.holds(row.figures, claim, NOTES_POLICY)
                      and len(set(row.labels) & set(words)) >= needed]


def _sign(text: str) -> str:
    """The sign a figure is written with, "+" or "-", or "" for none."""
    return {"+": "+", "-": "-", "−": "-"}.get(text[:1], "")


def _refiled(body: str, claim: assay_numbers.Quantity, sentence: str, bound: list[Row], bank: FactBank) -> str | None:
    """Why a draft's figure copies a rounding of rounded figures, or None. The notes must give it, for what the
    sentence names, as a worked-out figure the facts as filed don't give to the place written (`filed`). Percentages
    as common as 9.3% stand in many workings, so it must be one about the same thing: the sentence names what the
    working's heading or row is about (the company, not only the measure), and writes the figure with the working's
    sign, or none where it has none. A figure in a table whose row or caption names its year (`year_at`) is that year's,
    so a working on a row for another year isn't its source. Other lines may repeat it, an average that takes it in or
    a remark that quotes it, but none may state it from a source it cites itself, since the source then gives the
    figure as written."""
    if claim.kind not in ("number", "percent") or any(row.sourced for row in bound):
        return None
    words = set(research.describing_words(sentence))
    written = _sign(body[claim.start - 1:claim.start]) if claim.start else ""
    year = year_at(body, claim.start)
    for row in bound:
        if not row.subject & words:
            continue
        if year is not None and (other := _row_year(row.text)) is not None and other != year:
            continue
        for found in bank.refiled.get(row.where, []):
            if _sign(found.stated.strip()) != written:
                continue
            # A working in a table of US$ millions writes its figure bare (447.0), and the draft $447.0M: the row is
            # already bound in its unit, so the working's figure is read in the scales a table states too.
            if any(assay_numbers.holds(assay_numbers.evidence(found.stated + scale, policy=NOTES_POLICY), claim, NOTES_POLICY)
                   for scale in SCALES):
                taking = f", taking what {', '.join(found.via)} gives as filed" if found.via else ""
                return (f"the notes work it out at {found.where} from rounded figures, {found.item}; from the SEC's facts "
                        f"as filed{taking}, {found.filed} gives {found.gives}")
    return None


def _qualified_by(row: Row, claim: assay_numbers.Quantity, qualifier: re.Pattern[str]) -> str | None:
    """The word that qualifies a figure on a line of the notes, within reach of every place the line gives it, or None
    when one place stands clear of such a word, or the line gives it nowhere this can find."""
    text = " ".join(row.text.split())
    places = [q for q in assay_numbers.quantities(text, NOTES_POLICY)
              if assay_numbers.holds(assay_numbers.evidence(q.text, policy=NOTES_POLICY), claim, NOTES_POLICY)]
    words = []
    for place in places:
        near = qualifier.search(text[max(0, place.start - QUALIFIER_REACH):place.start + len(place.text) + QUALIFIER_REACH])
        if not near:
            return None
        words.append(near.group(0))
    return words[0] if words else None


def _unqualified(claim: assay_numbers.Quantity, sentence: str, bound: list[Row]) -> str | None:
    """Why a draft's figure drops what the notes say it is, or None. Every line of the notes that gives it, for what the
    sentence names, must qualify it the same way, and the sentence not at all: an amount the notes give only as a change
    ("$3.8M of incremental duty cost") stated as a level ("duties cost $3.8M"), or a figure they give only as someone's
    estimate or claim ("a 10x estimated cost saving") stated as a fact, with no word or bracketed source saying whose."""
    money = bool(MONEY.search(claim.text))
    if claim.kind == "number" and claim.figures < 3 and not money or claim.kind not in ("number", "percent", "multiple"):
        return None
    checks = [("change", AS_CHANGE, SAYS_CHANGE)] if claim.kind == "number" and money else []
    checks.append(("estimate", AS_ESTIMATE, SAYS_WHOSE))
    for kind, in_notes, in_draft in checks:
        if in_draft.search(sentence):
            continue
        words = [_qualified_by(row, claim, in_notes) for row in bound]
        if any(word is None for word in words):
            continue
        where = f"{bound[0].where} ({words[0]!r})" + (f" and {len(bound) - 1} more" if len(bound) > 1 else "")
        if kind == "change":
            return (f"the notes give it only as a change, at {where}, and this sentence states it as an amount: say what "
                    "it's a change in, or check the figure")
        return f"the notes give it only as someone's estimate or claim, at {where}, and this sentence states it as fact: say whose it is"
    return None


def qualifiers(body: str, bank: FactBank) -> Iterator[Found]:
    """Each figure of the draft that the notes hold for what its sentence names, but as something the sentence doesn't
    say: a rounding of rounded figures (`_refiled`), a change, or someone's estimate (`_unqualified`). Warnings: the
    figure may be right, and the sentence may say it in words this doesn't read."""
    for claim in assay_numbers.quantities(body, NOTES_POLICY):
        if claim.figures < 2 or claim.kind not in ("number", "percent", "multiple"):
            continue
        sentence, bound = _bound(body, bank, claim)
        refiled = _refiled(body, claim, sentence, bound, bank) if bound else None
        # A table row that names nothing ("| 2022 | 651.5 | -4.5% |") is read with its header and caption, but only
        # for this: the sentence alone is read first, so a figure it binds keeps the verdict it had.
        if refiled is None and (context := context_at(body, claim.start)) != sentence:
            _, wider = _bound(body, bank, claim, context)
            refiled = _refiled(body, claim, context, wider, bank) if wider else None
        for why in (refiled, _unqualified(claim, sentence, bound) if bound else None):
            if why:
                yield _line(body, claim.start), WARN, claim.text, f"{claim.kind} {claim.form()}: {why}"


# How many of the notes' lines a warning points to, and how much of each it shows.
NEAREST = 2
EXCERPT = 90
PLAIN_WORD = re.compile(r"[^\W_]{3,}")


def nearest(rows: list[Row], sentence: str, figure: str) -> str:
    """The lines of the notes most like a draft's sentence, by the words of three letters or more they share with it,
    each as where it is and the stretch of it around the figure: the lines a reader should look at first."""
    words = {word.lower() for word in PLAIN_WORD.findall(sentence)}
    ranked = sorted(rows, key=lambda row: -len(words & {word.lower() for word in PLAIN_WORD.findall(row.text)}))[:NEAREST]
    digits = re.search(r"\d[\d,]*(?:\.\d+)?", figure)
    shown = []
    for row in ranked:
        text = " ".join(row.text.split())
        at = text.find(digits.group(0)) if digits else -1
        start = max(0, min(at - EXCERPT // 2, len(text) - EXCERPT)) if at >= 0 else 0
        excerpt = ("..." if start else "") + text[start:start + EXCERPT] + ("..." if start + EXCERPT < len(text) else "")
        shown.append(f"{row.where} {excerpt!r}")
    return "; ".join(shown)


def check_titles(draft: str, bank: FactBank) -> Iterator[Found]:
    """Each title or credential in the draft that no title of the notes gives, read whole. A warning: its words are
    the notes' own, put together into something they don't say."""
    text = assay_text.matchable(draft)
    for found in assay_titles.title_findings(text, bank.titles):
        what = ("a credential the notes don't give word for word" if found.kind == "credential" else
                "a title no title in the notes reads as, so its words may come from two of them")
        yield _line(text, found.start), WARN, found.text, what


def check_links(draft: str, bank: FactBank, given: Rules | None = None) -> Iterator[Found]:
    """Each web address, domain or email in the draft that the notes don't write. The draft is read as written, so a
    domain spelled with a look-alike letter is a domain the notes don't write. The SEC's structured data for a company
    the workspace loads is held too: `claims` holds the notes to it. One `[assay.accept_addresses]` accepts passes,
    with the reason the settings give."""

    def held(url: str) -> bool:
        return address(url) in bank.addresses or sec_data(address(url), bank.companies)

    for line_no, line in enumerate(draft.splitlines(), 1):
        rest = ADDRESS.sub(lambda match: " " * len(match.group(0)) if held(match.group(0)) else match.group(0), line)
        while (found := assay_links.link(rest, bank.links)) is not None:
            place = re.search(rf"(?<![\w.@-]){re.escape(found)}", rest)
            at = place.start() if place else rest.find(found)
            token = next((match for match in TOKEN.finditer(rest) if match.start() <= at < match.end()), None)
            if at < 0 or token is None:
                yield line_no, FAIL, found, "a web address, domain or email the notes don't write"
                break
            written = token.group(0).rstrip(".,;:!?*")
            why = given.accepts(written) if given else None
            if why is not None:
                yield line_no, PASS, written, f"an address the notes don't write, accepted by [assay.accept_addresses]: {why}"
            else:
                yield line_no, FAIL, written, "a web address, domain or email the notes don't write"
            rest = rest[:token.start()] + " " * (token.end() - token.start()) + rest[token.end():]


def places_at(text: str, start: int, end: int) -> set[str]:
    """Which of `PLACES` a stretch of a draft stands in: a caption, a source line, a reference list or a citation."""
    begins = text.rfind("\n", 0, start) + 1
    ends = text.find("\n", end)
    line = text[begins:ends if ends >= 0 else len(text)]
    found = set()
    if CAPTION.match(line):
        found.add("captions")
    if any(match.end() <= start - begins for match in SOURCE_LINE.finditer(line)):
        found.add("sources")
    heading = next((row for row in reversed(text[:begins].split("\n")) if row.lstrip().startswith("#")), "")
    if REFERENCE_HEADING.match(heading.strip()):
        found.add("references")
    if any(match.start() <= start - begins and end - begins <= match.end() for match in CITATION.finditer(line)):
        found.add("citations")
    return found


def check_names(draft: str, given: Rules) -> Iterator[Found]:
    """Each confidential name in the draft, read as a reader sees it, so emphasis or a look-alike letter can't hide it.
    One that stands where `[assay.allowed]` lets that name stand passes, saying where."""
    text = assay_text.matchable(draft)
    for name, pattern in given.name_patterns():
        allowed = given.places_for(name)
        for match in re.finditer(pattern, text, re.I):
            if match.end() <= match.start():
                continue
            where = sorted(places_at(text, match.start(), match.end()) & set(allowed))
            if where:
                yield (_line(text, match.start()), PASS, match.group(0),
                       f"a confidential name, allowed here ({', '.join(where)}) by [assay.allowed]")
            else:
                also = f", and [assay.allowed] lets it stand only in {', '.join(allowed)}" if allowed else ""
                yield _line(text, match.start()), FAIL, match.group(0), f"a confidential name: [assay] forbidden lists {name!r}{also}"


def check_judgments(draft: str, given: Rules) -> Iterator[Found]:
    """Each sentence that makes a judgment the settings list, unless it says whose judgment it is or cites a source."""
    text = assay_text.matchable(draft)
    attributions = [re.compile(pattern, re.I) for pattern in given.attributions]
    at = 0
    for sentence in assay_claims.SENTENCE.split(text):
        at = text.index(sentence, at)
        judged = [match.group(0) for pattern in given.judgments for match in re.finditer(pattern, sentence, re.I)
                  if match.end() > match.start()]
        if judged:
            said = " ".join(sentence.split())[:140]
            if any(pattern.search(sentence) for pattern in attributions):
                yield _line(text, at), PASS, said, "a judgment, attributed"
            elif CITATION.search(sentence):
                yield _line(text, at), PASS, said, "a judgment, with a citation"
            else:
                yield (_line(text, at), FAIL, said, f"a judgment ({', '.join(repr(word) for word in dict.fromkeys(judged))}) "
                       "with no attribution, such as \"in the author's view\", and no citation")
        at += len(sentence)


def check_claims(draft: str, given: Rules) -> Iterator[Found]:
    """Each sentence that makes a claim the settings list as unsupported, and each that names one only to deny it."""
    text = assay_text.matchable(draft)
    disclaimers = list(given.disclaimers)
    at = 0
    for sentence in assay_claims.SENTENCE.split(text):
        at = text.index(sentence, at)
        claimed: list[str] = []
        for pattern in given.unsupported:
            for match in re.finditer(pattern, sentence, re.I):
                if match.end() == match.start():
                    continue
                if assay_claims.disclaimed(*assay_claims.either_side(sentence, match), disclaimers):
                    yield _line(text, at + match.start()), PASS, match.group(0), "named only to deny it"
                elif match.group(0) not in claimed:
                    claimed.append(match.group(0))
        if claimed:
            yield (_line(text, at), FAIL, " ".join(sentence.split())[:140],
                   f"makes a claim [assay] unsupported lists: {', '.join(repr(claim) for claim in claimed)}")
        at += len(sentence)


PASSED = {
    "numbers": "every figure is in the notes",
    "titles": "every title is one the notes give",
    "links": "every address is one the notes write",
    "names": "no confidential name",
    "claims": "no unsupported claim",
    "judgments": "every judgment attributed or cited",
    "plans": "no plan dated to a period begun by the cut-off",
}


# ---------------------------------------------------------------- judging and sealing

def seal_parts(path: Path, bank: FactBank, given: Rules) -> dict[str, str]:
    """What a verdict on a draft is tied to: its exact bytes, the notes, the sources' text, the rules, and the version
    of the assay that judged it."""
    code = {f"{p.parent.name}/{p.name}": assay_seal.file_digest(p) for p in CODE}
    return {str(key): str(value) for key, value in assay_seal.with_checker({
        "draft": assay_seal.digest(path.read_bytes()),
        "notes": bank.notes_digest,
        "sources": bank.sources_digest,
        "rules": assay_seal.value_digest({"settings": given.digestible(), "sections": list(EVIDENCE_SECTIONS), "code": code,
                                          "companies": sorted(bank.companies),
                                          "filed": sorted(f"{r.where} {r.item} {r.gives}" for found in bank.refiled.values()
                                                          for r in found)}),
    }).items()}


def judge_one(path: Path, bank: FactBank, given: Rules) -> tuple[list[Result], dict[str, str]]:
    """Every result for one draft, its verdict last, and the parts of its seal."""
    draft = drafts.read_draft(path)
    # What the draft says, without its reference list or the sections that are records; the reference list is kept
    # for its addresses, and the whole draft for confidential names, which may stand nowhere they aren't allowed.
    said = drafts.set_aside(draft, given.records)
    found: dict[str, list[Found]] = {
        "numbers": list(check_numbers(said, bank)),
        "titles": list(check_titles(said, bank)),
        "links": list(check_links(drafts.set_aside(draft, given.records, references=False), bank, given)),
    }
    if given.forbidden:
        found["names"] = list(check_names(draft, given))
    if given.unsupported:
        found["claims"] = list(check_claims(said, given))
    if given.judgments:
        found["judgments"] = list(check_judgments(said, given))
    if given.cutoff:
        found["plans"] = [(line, WARN, written, why) for line, written, why in plans.check(said, date.fromisoformat(given.cutoff))]
    results: list[Result] = []
    for check, items in found.items():
        results += [Result(path.name, line, check, verdict, item, detail) for line, verdict, item, detail in items]
        if not any(verdict != PASS for _, verdict, _, _ in items):
            results.append(Result(path.name, 0, check, PASS, "", PASSED[check]))
    failures = sum(r.verdict == FAIL for r in results)
    warnings = sum(r.verdict == WARN for r in results)
    parts = seal_parts(path, bank, given)
    verdict = FAIL if failures else WARN if warnings else PASS
    results.append(Result(path.name, 0, VERDICT, verdict, assay_seal.value_digest(parts),
                          f"{failures} failed, {warnings} warned, on {', '.join(found)}"))
    return results, parts


def _chosen(ws: Workspace, drafts: list[Path] | None) -> list[Path]:
    if not drafts:
        return draft_files(ws)
    missing = [str(path) for path in drafts if not path.is_file()]
    if missing:
        raise ValueError(f"No such draft: {', '.join(missing)}")
    return list(drafts)


def judge(ws: Workspace, con: sqlite3.Connection, drafts: list[Path] | None = None) -> list[Result]:
    """Judge each draft named, or with None or none named, every Markdown file in the drafts folder. Returns every
    result, each draft's verdict row last among its own. Records each verdict and its seal in `assay_verdicts`, and
    writes data/assay.csv. Raises ValueError for unusable settings or a draft that doesn't exist."""
    given = rules(ws)
    paths = _chosen(ws, drafts)
    con.executescript(SCHEMA)
    bank = fact_bank(ws, con)
    results: list[Result] = []
    for path in paths:
        found, parts = judge_one(path, bank, given)
        results += found
        verdict = found[-1]
        con.execute("INSERT OR REPLACE INTO assay_verdicts(draft, seal, verdict, failures, warnings, parts, judged_at)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (path.name, verdict.item, verdict.verdict, sum(r.verdict == FAIL for r in found),
                     sum(r.verdict == WARN for r in found), json.dumps(parts, sort_keys=True), now()))
    con.commit()
    ws.data.mkdir(parents=True, exist_ok=True)
    with (ws.data / REPORT).open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["draft", "line_no", "check", "verdict", "item", "detail"])
        writer.writerows((r.draft, r.line, r.check, r.verdict, r.item, r.detail) for r in results)
    return results


def stale(ws: Workspace, con: sqlite3.Connection, path: Path) -> list[str] | None:
    """What has changed since a draft was last judged: any of "draft", "notes", "sources" and "rules". None when it
    was never judged. An empty list means its last verdict still vouches for it."""
    con.executescript(SCHEMA)
    row = con.execute("SELECT parts FROM assay_verdicts WHERE draft=? ORDER BY judged_at DESC, rowid DESC LIMIT 1",
                      (path.name,)).fetchone()
    if row is None:
        return None
    changed: list[str] = assay_seal.changed(json.loads(row[0]), seal_parts(path, fact_bank(ws, con), rules(ws)))
    return changed


def resolve(ws: Workspace, given: str) -> Path:
    """A draft named on the command line: as a path, or failing that, a file in the drafts folder."""
    path = Path(given).expanduser()
    if path.is_file():
        return path.resolve()
    if (drafts_folder(ws) / path).is_file():
        return drafts_folder(ws) / path
    raise ValueError(f"No such draft: {given}. Name a file, or one in {drafts_folder(ws)}.")


def run(ws: Workspace, con: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Print each failure and warning and each draft's verdict with a short seal. Exits 1 when a draft fails."""
    try:
        named = [resolve(ws, str(given)) for given in getattr(args, "drafts", None) or []]
        results = judge(ws, con, named or None)
    except ValueError as problem:
        print(problem, file=sys.stderr)
        return 1
    if not results:
        print(f"No drafts to judge: {drafts_folder(ws)} has no Markdown, Word or PDF files.", file=sys.stderr)
        return 0
    # Each draft's findings are compared with the last time that draft was judged, so judging one draft alone doesn't
    # count another's findings as fixed.
    findings: list[history.Finding] = []
    # A pass with a reason, such as a figure that rounds the notes' or a name allowed where it stands, is listed with
    # --all and counted otherwise, so what was let through is never silent.
    passed: list[str] = []
    for r in results:
        if r.check != VERDICT:
            if r.verdict != PASS:
                findings.append(history.Finding(history.fingerprint(r.check, r.verdict, r.item, r.detail),
                                                f"  {r.verdict.upper()} {r.check} {r.draft}:{r.line} {r.item[:90]!r}: {r.detail}"))
            elif r.line:
                passed.append(f"  PASS {r.check} {r.draft}:{r.line} {r.item[:90]!r}: {r.detail}")
            continue
        changes = history.compare(con, f"assay {r.draft}", findings)
        history.report(changes, findings, bool(getattr(args, "all", False)))
        if getattr(args, "all", False):
            for line in passed:
                print(line)
        print(f"{r.draft}: {r.verdict.upper()} ({r.detail}), seal {r.item[:12]}")
        if passed:
            print(f"  {len(passed)} passed with a reason given (a rounding, a denial, a name where it's allowed)"
                  + ("" if getattr(args, "all", False) else "; --all lists them"))
        if not changes.first:
            print(f"  {changes.summary()}")
        findings, passed = [], []
    print(f"wrote {ws.data / REPORT}")
    return 1 if any(r.check == VERDICT and r.verdict == FAIL for r in results) else 0
