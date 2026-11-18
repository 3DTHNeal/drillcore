"""The figures the notes state in their tables, by label and period, for a formula to name.

A formula can name a figure instead of copying it: `{Revenue 2025}`, `{Gross margin, FY2025}`, `{Revenue}`. A
reference's words are a label and, if it gives one, a period, read as `measures` reads them: "Q3 2025", "FY2025",
"nine months ended September 30, 2025", "October 2025". In a rule a workspace sets, "prior" (or "previous", "a year
earlier") names the same period a year before.

**What the notes state.** Each table in a note's body, outside its Sources and Gaps and cautions, states a figure in
every cell that reads as one, as the footing check reads a cell: rounded to its last digit, a dash as nil, (12.4) as
-12.4. Its label is the row's first cell, and its period the one its column's heading names, or failing that the one
the label itself names. Figures in running text have no label to be found by, so they aren't named this way.

**Finding one.** A reference and a label match on their words, as `measures.label_words` reads them: case, a plural's
s, a unit such as ", $M" and the words of a period don't count, and words that mean the same line ("sales" and
"revenue", "headcount" and "staff") are one. "Total" counts, so `{Revenue}` and `{Total revenue}` are two lines. A
reference with a period matches a figure in that period, or failing one, a figure in any period it doesn't contradict.
A reference with no period matches a figure in any.

The note the formula is in is searched first, and the other notes only when it states no such figure. A reference that
matches no figure, or matches figures with different values, can't be worked out, and says which it found. Nothing is
guessed.
"""
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, replace

from .formula import Figure, Undefined, cell_figure, label
from .measures import Period, differ, label_words, one, period_spans
from .sourcedb import NOT_NOTES, cells

SEPARATOR = re.compile(r"\|[\s\-:|]+\|")


@dataclass(frozen=True)
class Table:
    header: list[str]
    rows: list[tuple[int, str, list[str]]]  # line, the row as written, its cells


def tables(text: str) -> Iterator[Table]:
    """Each table in a note's body, outside the Sources and Gaps and cautions sections."""
    lines = text.splitlines()
    in_sources = False
    at = 0
    while at < len(lines):
        row = lines[at].strip()
        if row.startswith("#"):
            in_sources = bool(NOT_NOTES.match(row))
        if not row.startswith("|") or in_sources:
            at += 1
            continue
        start = at
        while at < len(lines) and lines[at].strip().startswith("|"):
            at += 1
        block = [line.strip() for line in lines[start:at]]
        if len(block) > 2 and SEPARATOR.fullmatch(block[1]):
            yield Table(cells(block[0]), [(start + 3 + i, line, cells(line)) for i, line in enumerate(block[2:])])


class NotStated(Undefined):
    """A reference that matches no figure the notes state."""


class Ambiguous(Undefined):
    """A reference that matches figures the notes state with different values."""


TOTAL = re.compile(r"\btotals?\b", re.I)
PRIOR = re.compile(r"\b(?:prior|previous|preceding)(?:\s+(?:year|period))?\b|\b(?:a\s+)?year\s+(?:earlier|before)\b", re.I)


def words(text: str) -> frozenset[str]:
    """The words a label or a reference names a line by: `measures.label_words`, with any period left out first, and
    "total" kept."""
    for start, end, _ in reversed(period_spans(text)):
        text = text[:start] + " " + text[end:]
    found = label_words(text)
    return found | {"total"} if TOTAL.search(text) else found


@dataclass(frozen=True)
class Reference:
    """What a reference in braces names: a line by its words, a period if it gives one, and whether it counts a year
    back from the period a rule is applied to."""
    text: str
    words: frozenset[str]
    period: Period | None
    prior: bool = False


def reference(text: str) -> Reference:
    """The reference that the words in braces make. Raises Undefined for one that names no line or two periods."""
    prior = bool(PRIOR.search(text))
    rest = PRIOR.sub(" ", text)
    named = {period for _, _, period in period_spans(rest)}
    if len(named) > 1:
        raise Undefined(f"{{{text}}} names more than one period")
    found = words(rest)
    if not found:
        raise Undefined(f"{{{text}}} names no line: it needs words such as a table row's label")
    return Reference(text, found, one(named), prior)


@dataclass(frozen=True)
class Stated:
    """A figure a table in the notes states: where, beside what label, for what period."""
    note: str
    line: int
    label: str
    words: frozenset[str]
    period: Period | None
    figure: Figure
    row: str

    def where(self) -> str:
        return f"{self.figure.text} at {self.note}:{self.line}" + (f" ({self.period.shown()})" if self.period else "")


def _column_period(header: list[str], column: int) -> Period | None:
    return one(period for _, _, period in period_spans(header[column])) if column < len(header) else None


def read(note: str, text: str) -> Iterator[Stated]:
    """Each figure the tables in one note state."""
    for table in tables(text):
        for line, row, row_cells in table.rows:
            name = label(row_cells[0]) if row_cells else ""
            own = one(period for _, _, period in period_spans(name))
            line_words = words(name)
            if not line_words:
                continue
            for column in range(1, len(row_cells)):
                found = cell_figure(row_cells[column])
                if found is None or not found.text:
                    continue
                period = (_column_period(table.header, column) if len(table.header) == len(row_cells) else None) or own
                yield Stated(note, line, name, line_words, period, found, row)


class Book:
    """Every figure the notes state in a table, to be looked up by label and period."""

    def __init__(self, stated: Iterable[Stated]) -> None:
        self.by_words: dict[frozenset[str], list[Stated]] = defaultdict(list)
        for entry in stated:
            self.by_words[entry.words].append(entry)

    @classmethod
    def of(cls, notes: Iterable[tuple[str, str]]) -> "Book":
        """The book of a set of notes, each given as (its name, its text)."""
        return cls(entry for note, text in notes for entry in read(note, text))

    def stating(self, line_words: frozenset[str]) -> list[Stated]:
        """Every figure stated on a line with these words, in every note."""
        return list(self.by_words.get(line_words, []))

    def find(self, wanted: Reference, note: str, period: Period | None = None, in_period: bool = False) -> Stated:
        """The figure a reference names, looked for in `note` first. A reference with no period of its own takes
        `period` when `in_period` is set, as a rule applies one, and matches a figure in any period when it isn't.
        Raises NotStated or Ambiguous, saying what it found."""
        target = wanted.period or (period if in_period else None)
        if wanted.prior:
            if target is None or target.year is None:
                raise Undefined(f"{{{wanted.text}}} names the period before, and there's no period to count back from")
            target = replace(target, year=target.year - 1)
        candidates = self.by_words.get(wanted.words, [])
        if target is not None:
            pool = [entry for entry in candidates if entry.period == target]
            pool = pool or [entry for entry in candidates if entry.period and not differ(entry.period, target)]
        elif in_period:
            pool = [entry for entry in candidates if entry.period is None]
        else:
            pool = list(candidates)
        pool = [entry for entry in pool if entry.note == note] or pool
        if not pool:
            said = f" for {target.shown()}" if target else ""
            raise NotStated(f"{{{wanted.text}}} names no figure a table of the notes states{said}")
        values = {entry.figure.value: entry for entry in pool}
        if len(values) > 1:
            shown = ", ".join(entry.where() for entry in list(values.values())[:4])
            more = "name the period" if target is None else "name the line more closely"
            raise Ambiguous(f"{{{wanted.text}}} names more than one figure: {shown}; {more}")
        return pool[0]

    def resolver(self, note: str) -> Callable[[str], Figure]:
        """What a formula in `note` binds its references with."""
        return lambda text: self.find(reference(text), note).figure
