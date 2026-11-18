"""Where a figure came from: the draft line that states it, the note row that holds it, the source key that row cites,
the address behind the key with when it was fetched and the hash of what came back, and the passage in the stored text
that holds the figure.

A figure is asked for as written, such as `551.1` or `$77.3M`, or as a line of a draft, `01_northbridge.md:7`, which
traces every figure on that line. A note row holds the figure when it writes the same number, read as `figures` reads
the numbers in a row. The passage is found the way `figures` finds a number: as written, at another scale (551.1 in the
notes, 551,102 in a filing stated in thousands), with more decimal places, or for a page in Chinese, counted in
ten-thousands or hundred-millions. A figure written as written in the source is preferred to one found at a scale.

Every chain is printed. A chain is complete when it reaches a passage in a stored copy; where it stops, it says why:
no note row holds the figure, the row cites no source, the row says it was worked out, the source was never fetched or
its fetch failed, or the stored text doesn't hold the figure at any scale `figures` tries.

This reads the notes, the drafts and the stored copies. It fetches nothing and changes nothing but the record of
which addresses the notes cite, which it reads afresh first, as `check` does.
"""
import argparse
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import sourcedb
from .drafts import read_draft
from .overlap import draft_files, drafts_folder
from .sourcedb import CJK, DOC_NUMBER, NUMBER, URL, find_number, keys_by_note, note_files, note_lines, record_sources, without_keys
from .workspace import Workspace

# How much of the source either side of a figure a passage shows, in characters.
CONTEXT = 120
# A line of a draft, named as the file and the line number.
DRAFT_LINE = re.compile(r"(?P<draft>.+?):(?P<line>\d+)")


@dataclass(frozen=True)
class Figure:
    """A number as written, with where it is on its line."""
    written: str
    value: float
    decimals: int
    start: int
    end: int


@dataclass(frozen=True)
class Passage:
    """Where a stored text holds a figure: the words before it, the number as the source writes it, the words after,
    and how it matched (exact, x1000, rounded and the rest `figures` uses)."""
    before: str
    match: str
    after: str
    kind: str


@dataclass(frozen=True)
class Address:
    """One address behind a source key, as the database has it."""
    key: str
    url: str
    fetched_at: str
    sha256: str
    passage: Passage | None
    # Why the chain stops here, or "" when the passage was found.
    missing: str


@dataclass(frozen=True)
class Chain:
    """A note row that holds the figure, and each address its keys lead to."""
    note: str
    line_no: int
    row: str
    keys: tuple[str, ...]
    addresses: tuple[Address, ...]
    # Why the chain stops at the row, or "" when it goes on to the sources.
    missing: str

    @property
    def complete(self) -> bool:
        return any(address.passage for address in self.addresses)


@dataclass(frozen=True)
class Mention:
    """A draft line that states the figure."""
    draft: str
    line_no: int
    text: str


@dataclass
class Trace:
    """Everything known about one figure."""
    figure: Figure
    mentions: list[Mention] = field(default_factory=list)
    chains: list[Chain] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return any(chain.complete for chain in self.chains)


# ---------------------------------------------------------------- figures in a line

def _blank(match: re.Match[str]) -> str:
    return " " * len(match.group(0))


def figures_in(text: str) -> list[Figure]:
    """The figures in a line worth tracing, with where each stands, read as `figures` reads a row: web addresses are
    passed over, and so are years and whole numbers under 100 written without a comma."""
    text = URL.sub(_blank, text)
    found: list[Figure] = []
    for match in NUMBER.finditer(text):
        raw = match.group(1)
        plain = raw.replace(",", "")
        value = float(plain)
        decimals = len(plain.split(".")[1]) if "." in plain else 0
        if decimals == 0 and "," not in raw and (value < 100 or 1900 <= value <= 2100):
            continue
        found.append(Figure(raw, value, decimals, match.start(1), match.end(1)))
    return found


def asked_figure(text: str) -> Figure | None:
    """The figure someone asked about, as `551.1`, `$77.3M` or `1,757`: its first number, whatever its size."""
    match = re.search(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", text)
    if not match:
        return None
    plain = match.group(0).replace(",", "")
    return Figure(match.group(0), float(plain), len(plain.split(".")[1]) if "." in plain else 0, match.start(), match.end())


def same(a: Figure, b: Figure) -> bool:
    return abs(a.value - b.value) < 1e-9


# ---------------------------------------------------------------- in a stored text

def _flat(text: str) -> str:
    return " ".join(text.split())


def passage(text: str, figure: Figure, chinese: bool = False) -> Passage | None:
    """Where a stored text holds a figure, written as it is if anywhere, else at the first place `figures` would find
    it at another scale. None when it's nowhere."""
    first: tuple[re.Match[str], str] | None = None
    for match in DOC_NUMBER.finditer(text):
        kind, _ = find_number([float(match.group(1).replace(",", ""))], figure.value, figure.decimals, chinese)
        if kind == "exact":
            first = (match, kind)
            break
        if kind and first is None:
            first = (match, kind)
    if first is None:
        return None
    match, kind = first
    start, end = match.start(1), match.end(1)
    before, after = text[max(0, start - CONTEXT):start], text[end:end + CONTEXT]
    lead = "... " if start > CONTEXT else ""
    tail = " ..." if end + CONTEXT < len(text) else ""
    return Passage(lead + _flat(before) + (" " if before[-1:].isspace() else ""), match.group(1),
                   (" " if after[:1].isspace() else "") + _flat(after) + tail, kind)


class Store:
    """The stored copies and what was recorded about fetching them, read from the database once each."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con
        self._text: dict[str, str | None] = {}

    def text(self, url: str) -> str | None:
        if url not in self._text:
            row = self.con.execute("SELECT text FROM documents WHERE url=?", (url,)).fetchone()
            self._text[url] = row[0] if row and row[0] else None
        return self._text[url]

    def fetch_record(self, url: str) -> tuple[str, str, str]:
        """When the address was fetched, the hash of what came back, and what went wrong, if anything."""
        row = self.con.execute("SELECT fetched_at, sha256, http_status, error FROM fetches WHERE url=?", (url,)).fetchone()
        if row is None:
            return "", "", "never fetched"
        fetched_at, digest, status, error = row
        return fetched_at or "", digest or "", error or ("" if status == 200 else f"HTTP {status}")

    def address(self, key: str, url: str, figure: Figure) -> Address:
        fetched_at, digest, error = self.fetch_record(url)
        text = self.text(url)
        if text is None:
            why = "not fetched yet" if error == "never fetched" else f"no text stored ({error})" if error else "no text was read from it"
            return Address(key, url, fetched_at, digest, None, why)
        found = passage(text, figure, len(CJK.findall(text[:20000])) > 50)
        why = "" if found else f"the stored text doesn't hold {figure.written} at any scale `figures` tries"
        return Address(key, url, fetched_at, digest, found, why)


# ---------------------------------------------------------------- the chain

class Tracer:
    """Traces figures through one workspace's drafts, notes and stored copies."""

    def __init__(self, ws: Workspace, con: sqlite3.Connection) -> None:
        record_sources(ws, con)
        self.ws = ws
        self.store = Store(con)
        names = [path.name for path in note_files(ws)]
        self.urls = keys_by_note(con, names, ws.config().get("notes", {}).get("borrows", {}))
        self.lines = [line for line in note_lines(ws, con) if line.section == "notes" and line.kind != "heading"]
        self.drafts = {path.name: read_draft(path).splitlines() for path in draft_files(ws)}
        self._chains: dict[float, list[Chain]] = {}

    def mentions(self, figure: Figure) -> list[Mention]:
        """The draft lines that state the figure."""
        return [Mention(name, number, text.strip()) for name, lines in self.drafts.items()
                for number, text in enumerate(lines, 1) if any(same(figure, there) for there in figures_in(text))]

    def chains(self, figure: Figure) -> list[Chain]:
        """Every note row that holds the figure, each followed to its sources."""
        if figure.value not in self._chains:
            found: list[Chain] = []
            for line in self.lines:
                known = self.urls.get(line.note, {})
                if not any(same(figure, there) for there in figures_in(without_keys(line.text, known))):
                    continue
                if line.worked_out:
                    found.append(Chain(line.note, line.line_no, line.text, line.keys, (),
                                       "the row says it was worked out, not taken from a source; `arithmetic` checks its working"))
                elif not line.keys:
                    found.append(Chain(line.note, line.line_no, line.text, (), (), "the row cites no source"))
                else:
                    addresses = tuple(self.store.address(key, url, figure) for key in line.keys for url in known.get(key, []))
                    found.append(Chain(line.note, line.line_no, line.text, line.keys, addresses, ""))
            self._chains[figure.value] = found
        return self._chains[figure.value]

    def trace(self, figure: Figure) -> Trace:
        return Trace(figure, self.mentions(figure), self.chains(figure))

    def draft_line(self, draft: str, line_no: int) -> tuple[str, list[Trace]]:
        """The text of a draft's line and a trace for each figure on it. Raises ValueError for a draft or a line that
        isn't there."""
        lines = self.drafts.get(draft)
        if lines is None:
            raise ValueError(f"No such draft: {draft}. Name a file in {drafts_folder(self.ws)}.")
        if not 1 <= line_no <= len(lines):
            raise ValueError(f"{draft} has {len(lines)} lines, so there's no line {line_no}.")
        text = lines[line_no - 1]
        return text.strip(), [Trace(figure, [Mention(draft, line_no, text.strip())], self.chains(figure)) for figure in figures_in(text)]


# ---------------------------------------------------------------- the command

def shown(found: Passage) -> str:
    """A passage on one line, with the figure marked."""
    return f"{found.before}[[{found.match}]]{found.after}"


def report(found: Trace) -> list[str]:
    """A trace as the lines `drillcore trace` prints."""
    out = [found.figure.written]
    if not found.mentions:
        out.append("  no draft states it")
    out += [f"  draft {m.draft}:{m.line_no}  {m.text[:110]}" for m in found.mentions]
    if not found.chains:
        out.append(f"  missing: no note row holds {found.figure.written}")
    for chain in found.chains:
        out.append(f"  note {chain.note}:{chain.line_no}  {chain.row[:110]}")
        if chain.missing:
            out.append(f"    missing: {chain.missing}")
        for address in chain.addresses:
            out.append(f"    {address.key} {address.url}")
            if address.fetched_at or address.sha256:
                out.append(f"      fetched {address.fetched_at or '-'}, sha256 {address.sha256 or '-'}")
            if address.passage:
                out.append(f"      found ({address.passage.kind}): {shown(address.passage)}")
            else:
                out.append(f"      missing: {address.missing}")
    complete = sum(chain.complete for chain in found.chains)
    out.append(f"  {complete} of {len(found.chains)} chain{'' if len(found.chains) == 1 else 's'} reach a passage in a stored source")
    return out


def run(ws: Workspace, con: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Print every chain for the figure, or for each figure on the draft line named. Exits 1 when a figure has no
    chain that reaches a stored passage."""
    asked = str(args.figure)
    tracer = Tracer(ws, con)
    named = DRAFT_LINE.fullmatch(asked)
    if named and (named["draft"] in tracer.drafts or Path(named["draft"]).suffix == ".md"):
        draft = Path(named["draft"]).name
        try:
            text, traces = tracer.draft_line(draft, int(named["line"]))
        except ValueError as problem:
            print(problem, file=sys.stderr)
            return 1
        print(f"{draft}:{named['line']}  {text}")
        if not traces:
            print("  no figure on this line to trace")
            return 0
    else:
        figure = asked_figure(asked)
        if figure is None:
            print(f"{asked!r} has no number in it. Give a figure as written, such as 551.1, or a draft line, such as "
                  "01_northbridge.md:7.", file=sys.stderr)
            return 1
        traces = [tracer.trace(figure)]
    for found in traces:
        # Passages are a source's own words, and a copy kept by an older version may still hold what a terminal acts
        # on: each line is printed with that taken out, its indent kept.
        print("\n".join(sourcedb.unseen_removed(line).replace("\n", " ") for line in report(found)))
    return 0 if all(found.complete for found in traces) else 1
