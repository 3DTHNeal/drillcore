"""Workings against the facts as filed: a figure the notes work out from figures that `claims` matched to the SEC's
structured facts, worked again from those facts as the company filed them.

A note may work its ratios from figures rounded to one decimal place, so that each can be recomputed from the note
alone: "-84.3% (= -31.6 / 37.5)". `arithmetic` holds the working to its own inputs, and it holds. But the company filed
37,482 and -31,571 thousand, and from those the margin is -84.23%, so the note's -84.3% is a rounding of rounded
figures, one place off. A draft that copies it is one place off too.

Each worked-out figure that `arithmetic` finds right is read again here when every input to its working is a figure
that `checks/xbrl_claims.csv` gives for one company, in the same note, and that `claims` matched to a fact. Each such
input is put back as the fact's value, and the working is judged again by `arithmetic`. A figure that no longer comes
out of it, at the precision it's written to, is listed with what the facts as filed give.

What it takes, and what it won't guess:

- An input is matched by its size to a claim of the same note. Every input must match one, all of one company, and
  each a single value for that company; an input two of that company's claims share with different facts, or one
  that matches claims of two companies and nothing settles which, leaves the working unread.
- The year a table row names settles which of a company's claims an input is, when two of them share its size: the
  2022 row's 29.0 is 2022's net loss, not 2011's operating income of the same size. A row whose first cell names a
  span ("net income, 2010 to 2025") with one input to each year takes them in order. The year only breaks such a tie:
  an input one claim gives is that claim's, whatever the row's year, since a ratio takes last year's balance too.
- A plain sum on a row that names its year (15.2 + 35.6 - 2.1 = 48.7, the makers of 2012 added together) may add
  figures of several companies: each input is then settled on its own, by the year, to a single fact.
- An input that is the figure another working on the same line comes to (the 48.7 of "9.6% (= 4.7 / 48.7)" beside
  the sum above) takes what that working comes to as filed. So does one that only one working on an earlier line of
  the note comes to, where no claim gives it. A working that takes such a figure carries a rounding the notes already
  made, so its other inputs that no claim gives, an outlook or a stated sum, stay as written. Without one, a figure
  no claim gives leaves the working unread, as does a percentage.
- A whole number of one or two digits, such as the 2 that averages two balances or the 3 years of a rate, is a
  constant and stays as written.
- A working that names a figure in braces ({Revenue 2025}) isn't read: `stated` finds those, not `claims`.
- The facts are the values `claims` stored, so run `claims` first. The working's sign is kept as the note writes it.

`claims` lists what this finds, as warnings, and writes them to data/workings_as_filed.csv. `assay` warns about a
draft's figure when every line of the notes that gives it for what the draft's sentence names is a working listed here.
"""
from __future__ import annotations

import csv
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass

from . import arithmetic
from .sourcedb import note_files, table_headers
from .workspace import Workspace

REPORT = "workings_as_filed.csv"
# A whole number this short is a constant of the working (the 2 of an average, the 3 of three years), not a figure.
CONSTANT = re.compile(r"\d{1,2}")
# How many decimal places of a fact are written into the working: more than any filing gives in millions.
PLACES = 6
# A table row's first cell that names its year, or a span of years ("net income, 2010 to 2025").
ROW_YEAR = re.compile(r"(?:19|20)\d\d")
ROW_SPAN = re.compile(r"\b((?:19|20)\d\d) to ((?:19|20)\d\d)\b")
# A working that only adds and takes away: figures, signs and blanks, and nothing that multiplies, divides or groups.
SUM = re.compile(r"[\s\d.,+\-−$€£¥]+")


@dataclass(frozen=True)
class Refiled:
    """One worked-out figure that the facts as filed don't give. `item` is the working as the note writes it, `filed`
    the same working with each input put back as filed, and `gives` what that comes to, written like the figure.
    `claims` are the claims whose facts went in, and `via` the lines of other workings whose results went in."""
    note: str
    line: int
    stated: str
    item: str
    filed: str
    gives: str
    claims: tuple[str, ...]
    via: tuple[str, ...] = ()

    @property
    def where(self) -> str:
        return f"{self.note}:{self.line}"


@dataclass(frozen=True)
class Fact:
    """A matched claim as a working's input can take it: its company, its size as filed, the claim, and its year."""
    company: int
    value: float
    claim: str
    year: int | None


@dataclass(frozen=True)
class Worked:
    """What a working of the notes comes to with its inputs as filed, for a later working that takes its figure."""
    line: int
    size: float
    value: float


def _size(written: str) -> float | None:
    """A working's input as a number without its sign, or None when it isn't a plain figure (a percentage, a name)."""
    plain = written.strip().replace(",", "").lstrip("+-−$€£¥")
    try:
        return abs(float(plain))
    except ValueError:
        return None


def _facts(con: sqlite3.Connection) -> dict[tuple[str, float], list[Fact]]:
    """Each matched claim's fact, by its note and its size as the note writes it."""
    found: dict[tuple[str, float], list[Fact]] = defaultdict(list)
    for note, cik, expected, value, claim, end in con.execute(
            "SELECT note_file, cik, expected, found_value, claim_id, period_end FROM xbrl_claims"
            " WHERE status = 'match' AND found_value IS NOT NULL"):
        year = int(end[:4]) if end and str(end)[:4].isdigit() else None
        found[(note, round(abs(expected), PLACES))].append(Fact(int(cik), abs(float(value)), claim, year))
    return found


def _years(result: arithmetic.Result, count: int) -> list[int | None]:
    """The year each of a working's `count` figures is for, as the row names it: the year of a row whose first cell is
    one, or for a row whose first cell names a span with one figure to each year, each year in turn. None where the row
    says nothing."""
    text = result.text.strip()
    if not text.startswith("|"):
        return [None] * count
    first = text.strip("|").split("|")[0].strip()
    if ROW_YEAR.fullmatch(first):
        return [int(first)] * count
    span = ROW_SPAN.search(first)
    if span and int(span.group(2)) - int(span.group(1)) + 1 == count:
        return list(range(int(span.group(1)), int(span.group(2)) + 1))
    return [None] * count


def _is_sum(result: arithmetic.Result) -> bool:
    """Whether a working only adds and takes away, written "a + b - c = d" or "d (= a + b - c)"."""
    item = result.item
    if item.startswith(result.stated) and item[len(result.stated):].startswith(" (="):
        working = item[len(result.stated) + 3:].rstrip(")")
    else:
        working = item.rpartition(" = ")[0]
    return bool(working) and bool(SUM.fullmatch(working))


def _one(facts: list[Fact], year: int | None) -> Fact | None:
    """The one fact of several an input could be, or None. Facts of one value are one fact (a claim the notes list
    twice); facts of several values are settled by the year, when exactly one value is for it."""
    if len({fact.value for fact in facts}) > 1 and year is not None:
        facts = [fact for fact in facts if fact.year == year]
    return facts[0] if facts and len({fact.value for fact in facts}) == 1 else None


def _earlier(worked: list[Worked], size: float, line: int, same_line: bool) -> Worked | None:
    """The one working this input is the result of: on the same line, or on an earlier line of the note."""
    found = {w.value: w for w in worked if w.size == size and (w.line == line if same_line else w.line < line)}
    return next(iter(found.values())) if len(found) == 1 else None


def _as_filed(result: arithmetic.Result, facts: dict[tuple[str, float], list[Fact]], worked: list[Worked]
              ) -> tuple[list[tuple[str, float]], tuple[str, ...], tuple[str, ...]] | None:
    """Each input of a working that something settles, with the value it goes back in as, then the claims and the
    lines of other workings that gave them; None when the working can't be read again as filed."""
    figures = [written for written in result.inputs if not CONSTANT.fullmatch(written.strip())]
    years = _years(result, len(figures))
    chained: dict[int, Worked] = {}
    matched: dict[int, list[Fact]] = {}
    unknown: list[int] = []
    for at, written in enumerate(figures):
        size = _size(written)
        if size is None:
            return None
        size = round(size, PLACES)
        if here := _earlier(worked, size, result.line, same_line=True):
            chained[at] = here
        elif candidates := facts.get((result.note, size)):
            matched[at] = candidates
        elif before := _earlier(worked, size, result.line, same_line=False):
            chained[at] = before
        else:
            unknown.append(at)
    # Without a figure the notes already worked out, a figure no claim gives leaves the working unread.
    if (unknown and not chained) or not (matched or chained):
        return None
    settled: dict[int, Fact] = {}
    if matched:
        companies = set.intersection(*({fact.company for fact in candidates} for candidates in matched.values()))
        if len(companies) == 1:
            company = companies.pop()
            for at, candidates in matched.items():
                fact = _one([fact for fact in candidates if fact.company == company], years[at])
                if fact is None:
                    return None
                settled[at] = fact
        elif _is_sum(result) and all(year is not None for year in years):
            for at, candidates in matched.items():
                fact = _one([fact for fact in candidates if fact.year == years[at]], years[at])
                if fact is None:
                    return None
                settled[at] = fact
        else:
            return None
    values = [(figures[at], settled[at].value) for at in sorted(settled)]
    values += [(figures[at], chained[at].value) for at in sorted(chained)]
    claims = tuple(settled[at].claim for at in sorted(settled))
    via = tuple(sorted({f"{result.note}:{chained[at].line}" for at in chained if chained[at].line != result.line}))
    return values, claims, via


def _written(value: float) -> str:
    return f"{value:.{PLACES}f}".rstrip("0").rstrip(".")


def _expression(result: arithmetic.Result) -> str:
    """Where a working's inputs are written on its line: the working itself, or for a table with Result and
    Arithmetic columns, whose working is read across two cells, the arithmetic cell's expression."""
    if result.item in result.text:
        return result.item
    expression, equals, _ = result.item.rpartition(" = ")
    return expression if equals and expression in result.text else ""


def _rework(result: arithmetic.Result, values: list[tuple[str, float]], header: list[str]
            ) -> tuple[str, arithmetic.Result] | None:
    """The working with its inputs as filed, and how it comes out: None when an input can't be put back."""
    written_as = _expression(result)
    # Only the working changes: the figure in front of a bracket stays as written.
    head, bracket, working = written_as.partition(" (")
    if not bracket:
        head, working = "", written_as
    # The stated figure of an "a + b = c" working stays as written too.
    working, equals, total = working.rpartition(" = ") if not bracket and " = " in working else (working, "", "")
    for written, value in sorted(values, key=lambda pair: result.inputs.index(pair[0])):
        digits = re.sub(r"^[-+−$€£¥]+", "", written.strip())
        working, done = re.subn(rf"(?<![\d.,]){re.escape(digits)}(?![\d.,]?\d)", _written(value), working, count=1)
        if not done:
            return None
    again_as = head + bracket + working + equals + total
    row = result.text.replace(written_as, again_as, 1)
    item = again_as if written_as == result.item else result.item.replace(written_as, again_as, 1)
    again = [found for found in arithmetic.check_row(result.note, result.line, row, header, worked_out=True)
             if found.item == item]
    return (item, again[0]) if again else None


def refile(ws: Workspace, con: sqlite3.Connection, results: list[arithmetic.Result] | None = None) -> list[Refiled]:
    """Every worked-out figure of the notes that the facts `claims` matched, as filed, don't give. A working that
    takes another's figure is read after it, so each note's workings are read again until none more can be."""
    facts = _facts(con)
    if not facts:
        return []
    readable = [result for result in (arithmetic.check(ws) if results is None else results)
                if result.status == "ok" and result.inputs and "{" not in result.item and _expression(result)]
    by_note: dict[str, list[arithmetic.Result]] = defaultdict(list)
    for result in readable:
        by_note[result.note].append(result)
    # A table's header says which of its columns are the Result and the Arithmetic, so a row is read again with it.
    headers = {path.name: table_headers(path.read_text(encoding="utf-8")) for path in note_files(ws) if path.name in by_note}
    found = []
    for note, workings in by_note.items():
        worked: list[Worked] = []
        done: set[int] = set()
        progress = True
        while progress:
            progress = False
            for number, result in enumerate(workings):
                if number in done:
                    continue
                # A working that takes the figure of another on its line waits for it, so that a ratio of two sums
                # is read from the sums and never from claims that happen to share their sizes.
                waiting = {round(size, PLACES) for other, beside in enumerate(workings)
                           if other != number and other not in done and beside.line == result.line
                           and (size := _size(beside.stated)) is not None}
                if waiting & {round(size, PLACES) for written in result.inputs if (size := _size(written)) is not None}:
                    continue
                if (settled := _as_filed(result, facts, worked)) is None:
                    continue
                values, claims, via = settled
                reworked = _rework(result, values, headers.get(note, {}).get(result.line, []))
                done.add(number)
                progress = True
                if reworked is None:
                    continue
                item, again = reworked
                if again.computed is None:
                    continue
                if (size := _size(result.stated)) is not None:
                    worked.append(Worked(result.line, round(size, PLACES), abs(again.computed)))
                if again.status == "wrong":
                    found.append(Refiled(note, result.line, result.stated, result.item, item, again.shown(), claims, via))
    return sorted(found, key=lambda refiled: (refiled.note, refiled.line))


def write(ws: Workspace, found: list[Refiled]) -> None:
    """data/workings_as_filed.csv: each working, where it is, and what the facts as filed give."""
    ws.data.mkdir(parents=True, exist_ok=True)
    with (ws.data / REPORT).open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["note_file", "line", "stated", "working", "as_filed", "gives", "claims", "via"])
        for refiled in found:
            writer.writerow([refiled.note, refiled.line, refiled.stated, refiled.item, refiled.filed, refiled.gives,
                             " ".join(refiled.claims), " ".join(refiled.via)])
