"""Statements of a measure: a figure with the label and period that say what it measures, read where they can be.

`conflicts` holds a note's figure against what the other sources in the workspace state for the same label and period,
and `consistency` holds the statements in the notes and drafts against each other. Both read statements the same way:

- In a table, each cell that's a figure, with its row's label and its column's period (as `measures` reads them), and
  the unit its cell, its row's label, the table's first heading or the line leading into the table states.
- In prose (in the notes and drafts, never in a source), a clause holding one figure, one period and words that
  name nothing but the line, as in "Revenue for 2025 was $551.1M". A clause that says more than that isn't read.

Two statements are of the same measure when their labels come to the same words (`measures.label_words`, so "Net
sales" and "Revenue" don't, and "Sales" and "Revenue" do) and their periods are the same: the same year, and the
same length and part of the year, where both say. A percentage is only compared with a percentage. Two figures agree
when they're within the rounding each is written to, at the scale each states, or, when either states none, at any
scale (551.1 and 551,102 agree). Nothing is guessed: a statement whose label or period can't be read isn't one.
"""
import re
from collections.abc import Iterator
from dataclasses import dataclass

from . import measures
from .measures import MONEY, Period, unit_stated

# One figure: a currency before it, accounting brackets round it, a percent sign or a scale after it.
AMOUNT = re.compile(rf"(?P<money>{MONEY})?\s?(?P<open>\()?(?P<number>[-+]?\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|[-+]?\d+(?:\.\d+)?)\)?"
                    r"\s?(?P<scale>%|bn\b|billion\b|million\b|mn\b|thousand\b|[MBKk]\b)?")
# A cell giving one figure for each of several years, as "+3.1% (2024); +41.6% (2025) with the deals" does: each figure
# with its year in brackets straight after it.
YEARLY = re.compile(r"(?P<figure>[-+]?[$€£]?\d[\d,]*(?:\.\d+)?\s?(?:%|bn\b|million\b|[MBK]\b)?)\s*\((?P<year>(?:19|20)\d{2})\)")
SCALE = {"bn": 1e9, "billion": 1e9, "b": 1e9, "million": 1e6, "mn": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3}
UNIT_SCALE = {"thousand": 1e3, "million": 1e6, "billion": 1e9}
# The scales two figures are tried at when either doesn't state its own.
SHIFTS = (1.0, 1e3, 1e6, 1e9, 1e-3, 1e-6, 1e-9)


@dataclass(frozen=True)
class Statement:
    """A figure, and what it measures. `scale` is what its unit multiplies it by, or None when nothing says."""
    where: str          # a note's or draft's file name, or a source's address
    line_no: int        # 0 for a source, whose lines aren't numbered
    label: str
    words: frozenset[str]
    period: Period
    written: str        # the figure as written
    value: float
    decimals: int
    percent: bool
    scale: float | None
    text: str           # the line it's in
    # The company or other entity it's a figure of, as `entity_of` reads it, or "" when nothing says or more than one could be.
    entity: str = ""
    # Whether the entity is what its row names, its label being a measure only by its column ("Revenue growth" for the
    # row "Acme"): such a figure is compared only with the same entity's, since its label alone says nothing of whose.
    by_entity: bool = False

    @property
    def measure(self) -> tuple[frozenset[str], int | None, int | None, str]:
        """What two statements must share to be of the same measure."""
        return self.words, self.period.year, self.period.months or 12, self.period.part


def same_period(a: Period, b: Period) -> bool:
    """Whether two periods are the same, as far as either says: a year each, the same one, and the same length and
    part. A bare year is read as the full year it names, never as a part of it."""
    lengths = {a.months or 12, b.months or 12}
    return bool(a.year) and a.year == b.year and len(lengths) == 1 and a.part == b.part and not measures.differ(a, b)


def amount(match: re.Match[str], stated: float | None) -> tuple[float, int, bool, float | None]:
    """A figure's value, decimal places, whether it's a percentage, and its scale, given the scale its table states."""
    number = match.group("number").replace(",", "")
    value = float(number)
    if match.group("open") and ")" in match.group(0)[match.end("number") - match.start():]:
        value = -value  # (12.4), and (12.7)% with its sign after the bracket
    decimals = len(number.split(".")[1]) if "." in number else 0
    written = (match.group("scale") or "").lower()
    if written == "%":
        return value, decimals, True, 1.0
    if written:
        return value, decimals, False, SCALE[written]
    return value, decimals, False, stated if stated else (1.0 if match.group("money") else None)


def agree(a: Statement, b: Statement) -> bool:
    """Whether two figures are the same, within the rounding each is written to, at the scales they state or, when
    either states none, at any scale. Two figures a whole step apart in their last place, 18.4% and 18.5%, disagree:
    both are roundings only of 18.45 exactly, and a reader sees two figures for one thing."""
    if a.percent != b.percent:
        return True  # Not comparable, so not a disagreement.
    shifts = (a.scale / b.scale,) if a.scale and b.scale else SHIFTS
    for shift in shifts:
        gap = abs(a.value * shift - b.value)
        if gap < 0.5 * 10 ** -a.decimals * shift + 0.5 * 10 ** -b.decimals - 1e-9 * max(abs(b.value), 1):
            return True
    return False


def comparable(a: Statement, b: Statement) -> bool:
    """Whether two statements are of the same measure: the same label and period, and the same entity where both say."""
    if (a.by_entity or b.by_entity) and not (a.entity and a.entity == b.entity):
        return False
    return (a.percent == b.percent and a.words == b.words and same_period(a.period, b.period)
            and (not a.entity or not b.entity or a.entity == b.entity))


# ---------------------------------------------------------------- whose figure it is

# What a company's legal name ends in, and isn't written in a report's prose: "Stratus Ltd." is "Stratus".
SUFFIXES = frozenset({"ltd", "limited", "inc", "incorporated", "corp", "corporation", "co", "company", "holding", "holdings", "nv",
                      "plc", "sa", "ag", "se", "llc", "lp", "llp", "gmbh", "bv", "ab", "asa", "oyj", "spa", "the"})


def short_name(name: str) -> str:
    """A company's name as prose writes it: without anything in brackets or the words that make it a legal name."""
    words = re.sub(r"\([^)]*\)", " ", name).replace(",", " ").split()
    while words and words[-1].lower().replace(".", "") in SUFFIXES:
        words.pop()
    while words and words[0].lower() == "the":
        words.pop(0)
    return " ".join(words)


def _named(text: str, entities: tuple[str, ...]) -> list[tuple[int, str]]:
    """The entities a text names, with where each is first named, citations in brackets aside: "(Stratus Ltd. 2026a)"
    says where a figure is from, not whose it is."""
    plain = re.sub(r"\((?:[^()]|\([^()]*\))*?\b(?:1[5-9]|20)\d{2}[a-z]?\b(?:[^()]|\([^()]*\))*\)", " ", text)
    return sorted((found.start(), entity) for entity in entities
                  if (found := re.search(rf"(?<![\w-]){re.escape(entity)}(?![\w-])", plain)))


# What may stand before the name a heading, label or lead-in opens with: Markdown's marks, a number, "The".
OPENING = re.compile(r"^[\s#*_>|\-]*(?:[A-Z]?\d+(?:\.\d+)*[.)]?\s+)?(?:The\s+)?")


def entity_of(levels: list[str], entities: tuple[str, ...]) -> str:
    """Whose figure a statement gives: the one entity the nearest of its levels of context names, from its own label
    out to the document's title. A level that names more than one gives the one it opens with, as "Nano (owner of
    Kestrel) - USD:" gives Nano, and otherwise leaves it unknown. A level that names none passes to the next."""
    for text in levels:
        named = _named(text, entities)
        if len(named) == 1:
            return named[0][1]
        if named:
            opens = OPENING.match(text)
            return named[0][1] if opens and named[0][0] == opens.end() else ""
    return ""


def heading_chain(text: str) -> dict[int, list[str]]:
    """For each line of a note or draft, by line number, the headings it sits under, the nearest first and the
    document's title last."""
    chain: list[tuple[int, str]] = []
    found: dict[int, list[str]] = {}
    for line_no, line in enumerate(text.split("\n"), 1):
        heading = re.match(r"^(#+)\s", line.strip())
        if heading:
            level = len(heading.group(1))
            chain = [(depth, said) for depth, said in chain if depth < level] + [(level, line.strip())]
        found[line_no] = [said for _, said in reversed(chain)]
    return found


# ---------------------------------------------------------------- reading them

def _is_table_line(line: str) -> bool:
    return "|" in line


def table_statements(where: str, text: str, markdown: bool, headings: dict[int, str] | None = None,
                     entities: tuple[str, ...] = (), chains: dict[int, list[str]] | None = None) -> Iterator[Statement]:
    """Each figure in a text's tables that names its label and period, with the unit the table states. `markdown`
    says the tables are a note's or draft's, whose rows start with a bar and whose second row is a divider; otherwise
    they're a source's, as its text keeps them, a row a line with its cells between bars.

    In a note's or draft's table, a column whose heading names a measure and no period ("Gross margin", not "2025")
    makes its cells a measure of their own: two cells of one row under "Gross margin" and "Net margin" aren't one
    measure stated twice. Each figure's entity is read from its row's label, then the line leading into its table, then
    its headings (`entity_of`)."""
    lines = text.split("\n")
    lead_in = ""
    table_unit = ""
    header: list[str] = []
    repeated: set[str] = set()
    start = 0
    for at, line in enumerate(lines):
        row = line.strip()
        if not _is_table_line(row) or (markdown and not row.startswith("|")):
            if row:
                lead_in = row
            start = at + 1
            header = []
            continue
        if markdown and re.fullmatch(r"\|[\s\-:|]+\|", row):
            continue
        if at == start:
            first = row.strip("|").split("|")[0]
            table_unit = unit_stated(first) or unit_stated(lead_in)
            if markdown:
                header = [cell.strip() for cell in row.strip("|").split("|")]
                # The entities that open more than one row: a deal table's acquirer, say. Such a row isn't the one
                # measure of its company, so it isn't read as one.
                labels: list[str] = []
                for each in lines[at + 1:]:
                    if not each.strip().startswith("|"):
                        break
                    labels.append(each.strip().strip("|").split("|")[0])
                named = [entity_of([label], entities) for label in labels] if entities else []
                repeated = {entity for entity in named if entity and named.count(entity) > 1}
                continue
        cells = row.split("|")
        offset = 0
        # The one year the line leading into the table names, for a table whose rows and columns name none:
        # "Cross-section: 2025, the latest full year" over a table of companies and measures.
        led = {period.year for period in measures.periods(lead_in) if period.year} if markdown else set()
        lead_period = measures.one([period for period in measures.periods(lead_in) if period.year]) if len(led) == 1 else None
        for index, cell in enumerate(cells):
            figure = AMOUNT.fullmatch(cell.strip()) if cell.strip() else None
            yearly = list(YEARLY.finditer(cell)) if markdown and not figure and cell.strip() else []
            if (figure or yearly) and index > (1 if markdown else 0):
                place = offset + cell.index(cell.strip())
                if markdown:
                    context = measures.note_context(row, place, place + len(cell.strip()), header, (headings or {}).get(at + 1, ""))
                else:
                    context = measures.table_context(lines, at, place)
                label_unit = unit_stated(context.label)
                stated = UNIT_SCALE.get(label_unit or table_unit)
                words = measures.label_words(context.label)
                label = context.label
                column = header[index - 1] if markdown and 0 < index <= len(header) else ""
                entity = entity_of([context.label, lead_in, *(chains or {}).get(at + 1, [])], entities) if markdown else ""
                measured = bool(words and column and not measures.periods(column) and measures.label_words(column))
                # A row labelled by the company it's for, under a column naming a measure, is that measure of that
                # company. Its year may come from the line leading into the table, and a cell may give several years.
                company_row = measured and bool(entity and _named(context.label, entities)) and entity not in repeated
                period = measures.one(context.periods) or (lead_period if company_row else None)
                # Only a row whose own label says what it measures is read so. A row labelled by a date alone, as a price
                # series' is, says nothing to compare, with or without its column's heading.
                if company_row:
                    words, label = measures.label_words(column), f"{entity}: {column}"
                elif measured:
                    words, label = words | measures.label_words(column), f"{label}: {column}"
                found: list[tuple[re.Match[str] | None, Period | None]]
                if figure:
                    found = [(figure, period)]
                elif company_row:
                    found = [(AMOUNT.fullmatch(each.group("figure").strip()), measures.one(measures.periods(each.group("year"))))
                             for each in yearly]
                else:
                    found = []
                for match, when in found:
                    if match and when and words and when.year:
                        value, decimals, percent, scale = amount(match, stated)
                        yield Statement(where, at + 1 if markdown else 0, label, words, when, match.group(0).strip(), value,
                                        decimals, percent, scale, row, entity, company_row)
            offset += len(cell) + 1


def prose_statements(where: str, text: str, headings: dict[int, str] | None = None, entities: tuple[str, ...] = (),
                     chains: dict[int, list[str]] | None = None) -> Iterator[Statement]:
    """Each clause of a note's or draft's prose that holds one figure, one period and words naming nothing but the
    line, as "Revenue for 2025 was $551.1M". Its entity is read from the clause, then the line, then its headings."""
    for line_no, line in enumerate(text.split("\n"), 1):
        row = line.strip()
        if not row or row.startswith(("|", "#", ">")):
            continue
        spans = measures.period_spans(row)
        blanked = row
        for low, high, _ in spans:
            blanked = blanked[:low] + " " * (high - low) + blanked[high:]
        figures = [m for m in AMOUNT.finditer(blanked) if _counts(m)]
        for figure in figures:
            low, high = measures.clause(row, figure.start("number"), figure.end())
            if sum(low <= other.start("number") < high for other in figures) != 1:
                continue
            found = [period for start, _, period in spans if low <= start < high]
            period = measures.one(found)
            words = measures.label_words(measures.blank(row[low:high], AMOUNT_SPAN))
            if not (period and period.year and words):
                continue
            value, decimals, percent, scale = amount(figure, None)
            entity = entity_of([row[low:high], row, *(chains or {}).get(line_no, [])], entities)
            yield Statement(where, line_no, row[low:high].strip(" -*"), words, period, figure.group(0).strip(), value,
                            decimals, percent, scale, row, entity)


AMOUNT_SPAN = re.compile(AMOUNT.pattern)


def _counts(figure: re.Match[str]) -> bool:
    """Whether a number in prose is a figure worth comparing: one with a currency, a percent sign, a scale, a comma or
    a decimal point, or a whole number of 100 or more."""
    number = figure.group("number")
    return bool(figure.group("money") or figure.group("scale") or "," in number or "." in number or abs(float(number)) >= 100)


def headings_of(text: str) -> dict[int, str]:
    """For each line of a note or draft, by line number, the heading it sits under."""
    found: dict[int, str] = {}
    heading = ""
    for line_no, line in enumerate(text.split("\n"), 1):
        if line.strip().startswith("#"):
            heading = line.strip()
        found[line_no] = heading
    return found


def written_statements(where: str, text: str, entities: tuple[str, ...] = ()) -> list[Statement]:
    """Every statement a note or draft makes that can be read: in its tables and in its prose, outside its Sources
    section. `entities` are the companies and the like whose figures the notes and drafts give, as prose names them;
    each statement is tied to the one its context names, where one does."""
    kept = []
    skipping = False
    for line in text.split("\n"):
        if line.strip().startswith("#"):
            skipping = bool(re.match(r"#+\s*(?:Sources|Gaps and cautions)", line.strip()))
        kept.append("" if skipping else line)
    body = "\n".join(kept)
    headings = headings_of(body)
    chains = heading_chain(body) if entities else {}
    return [*table_statements(where, body, True, headings, entities, chains), *prose_statements(where, body, headings, entities, chains)]
