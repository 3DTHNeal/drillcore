"""What a figure measures: the label it stands beside and the period it covers.

The commonest error in a set of notes isn't a wrong number but the right number for the wrong thing: the third quarter
against nine months, a fiscal year against a calendar one, restated against as first reported, gross against net. This
reads the words that say what a figure measures, around it in a note and around the same number in a source, so the
two can be compared.

- A period is read from words such as "Q3 2025", "3Q25", "nine months ended September 30, 2025", "FY2025", "H1 2025",
  "fiscal 2025", "calendar 2025" or a bare year, and as economic data names one, "October 2025", "Oct-25", "2025Q3" or
  "2025M10". It has a length in months where the words give one, which quarter, half or month where they say, whether
  a year is fiscal or calendar where they say, and a year. A date, such as "September 30, 2025", isn't a month.
- A label is the words that name the line: a table row's first cell, or in prose the clause the figure stands in. A
  qualifier tells apart two lines that share a noun: gross, operating or net; basic or diluted; restated or as reported;
  adjusted or not; before or after tax; and in economic data, real or nominal; core or headline; seasonally adjusted
  or not; a change on the year, the quarter or the month; a forecast or an outturn. A source that calls a figure a
  forecast, where the note states it without saying so, names another line too.

In a source, a figure in a table is read with its row's label and its column's heading; elsewhere, with the clause
around it. A comparative in brackets, "£551.1m (2024: £572.5m)", is a clause of its own, so the prior year is the
bracketed figure's and not the one before it. Nothing is guessed: what can't be read comes back empty, and an empty
reading never disagrees with anything.

This module reads text only. It needs nothing installed and imports nothing else from Drillcore.
"""
import functools
import re
from collections.abc import Iterable
from dataclasses import dataclass

YEAR = r"(?P<year>(?:19|20)\d{2})(?![\d,.]\d)"
# A year written after a quarter, a half or a length of months: "Q3 2025", "Q3 FY2025", "Q3 of fiscal 2025", "3Q25".
YEAR_AFTER = (r"(?:\s*(?:of\s+)?(?:(?P<fy>fiscal|FY)\s*(?:year\s*)?)?(?P<year>(?:19|20)\d{2})(?![\d,.]\d)"
              r"|['’]?(?P<yy>\d{2})(?![\d.,%]))?")
WORD_NUMBER = {"three": 3, "six": 6, "nine": 9, "twelve": 12, "first": 1, "second": 2, "third": 3, "fourth": 4}
MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December")
MONTH_NUMBER = {name[:3].lower(): number for number, name in enumerate(MONTH_NAMES, 1)}
# A month and its year, as economic data names a period: "October 2026", "Oct. 2026", "Oct-26", "Oct '26". The name
# starts with a capital, so "may" is a verb. A month with a day before it ("28 October 2026") or after it ("October 28,
# 2026") is a date, not a month, and a month after "ended" or "to" closes a longer period, so neither is read as one.
MONTH = re.compile(
    r"(?<!\d )(?<!\d\w\w )(?<!ended )(?<!ending )(?<!\bto )(?<!through )"
    r"\b(?=(?-i:[A-Z]))(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
    r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
    r"(?:\s+|\s*[-'’]\s*)(?:(?P<year>(?:19|20)\d{2})(?![\d,.]\d)|(?<=[-'’])(?P<yy>\d{2})(?![\d.,%]))", re.I)
# What the words for a period look like, most particular first. Each match is taken out of the text before the next
# pattern reads it, so "Q3 2025" is one period, not a quarter and a year.
PERIODS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # The year first, as statistics offices write a quarter or a month: "2026Q3", "2026:Q3", "2026 Q3", "2026M10".
    ("quarter", re.compile(r"(?<![\d.,$£€¥#/])(?:(?P<fy>FY)\s*)?(?P<year>(?:19|20)\d{2})\s?[:-]?\s?Q(?P<n>[1-4])\b", re.I)),
    ("month", re.compile(r"(?<![\d.,$£€¥#/])(?P<year>(?:19|20)\d{2})-?M(?P<number>0?[1-9]|1[0-2])\b", re.I)),
    ("quarter", re.compile(rf"\b(?:Q(?P<n>[1-4])|(?P<m>[1-4])Q)(?=[\s'’]|\d{{2}}|\b){YEAR_AFTER}", re.I)),
    ("quarter", re.compile(rf"\b(?P<word>first|second|third|fourth)\s+(?:fiscal\s+)?quarter\b{YEAR_AFTER}", re.I)),
    ("half", re.compile(rf"\b(?:H(?P<n>[12])|(?P<m>[12])H)(?=[\s'’]|\d{{2}}|\b){YEAR_AFTER}", re.I)),
    ("half", re.compile(rf"\b(?P<word>first|second)\s+half\b{YEAR_AFTER}", re.I)),
    ("months", re.compile(r"\b(?P<n>3|6|9|12|three|six|nine|twelve)(?:\s*M(?=\b|\d)|[\s-]+months?\b)"
                          r"(?:[^.;|\n]{0,30}?\b(?P<year>(?:19|20)\d{2})(?![\d,.]\d)|['’]?(?P<yy>\d{2})(?![\d.,%]))?", re.I)),
    ("year", re.compile(r"\b(?P<fy>fiscal|financial)?\s*years?\s+(?:ended|ending|to(?!\s+date))\b"
                        r"(?:[^.;|\n]{0,30}?\b(?P<year>(?:19|20)\d{2})(?![\d,.]\d))?", re.I)),
    ("year", re.compile(r"\b(?:full[\s-]year|annual)\b(?:\s+(?P<year>(?:19|20)\d{2})(?![\d,.]\d))?", re.I)),
    ("month", MONTH),
    ("fiscal", re.compile(r"\bFY\s*['’]?(?:(?P<year>(?:19|20)\d{2})|(?P<yy>\d{2}))(?![\d.,%])", re.I)),
    ("fiscal", re.compile(rf"\b(?:fiscal|financial)\s+(?:year\s+)?{YEAR}", re.I)),
    ("calendar", re.compile(r"\bCY\s*['’]?(?:(?P<year>(?:19|20)\d{2})|(?P<yy>\d{2}))(?![\d.,%])", re.I)),
    ("calendar", re.compile(rf"\bcalendar\s+(?:year\s+)?{YEAR}", re.I)),
    ("year", re.compile(rf"(?<![\d.,$£€¥#/-]){YEAR}(?![%\d])")),
)


@dataclass(frozen=True)
class Period:
    """What a figure covers. Each part is None or "" when the words don't say."""
    months: int | None = None
    part: str = ""        # Q1 to Q4, H1 or H2, or a month as M1 to M12
    basis: str = ""       # fiscal or calendar
    year: int | None = None

    def shown(self) -> str:
        """The period as a person writes it: "Q3 2025", "9M 2025", "FY2025", "Oct 2025", "2025"."""
        if self.part.startswith("M"):
            head = MONTH_NAMES[int(self.part[1:]) - 1][:3]
        elif self.part:
            head = self.part
        elif self.basis == "fiscal":
            head = "FY"
        elif self.basis == "calendar":
            head = "CY"
        elif self.months and self.months != 12:
            head = f"{self.months}M"
        elif self.months == 12:
            head = "full year"
        else:
            head = ""
        year = str(self.year) if self.year else ""
        if head in ("FY", "CY"):
            return f"{head}{year}" if year else head
        return " ".join(part for part in (head, year) if part) or "a period"

    def filled_from(self, other: "Period") -> "Period":
        """This period with what it doesn't say taken from another that doesn't contradict it."""
        if differ(self, other):
            return self
        return Period(self.months or other.months, self.part or other.part, self.basis or other.basis, self.year or other.year)


def differ(a: Period, b: Period) -> str:
    """How two periods differ, as a few words, or "" when nothing either says contradicts the other."""
    if a.year and b.year and a.year != b.year:
        return "year"
    if a.months and b.months and a.months != b.months:
        return "length"
    if a.part and b.part and a.part != b.part:
        return "part of the year"
    if a.basis and b.basis and a.basis != b.basis:
        return "fiscal against calendar year"
    return ""


def _year(match: re.Match[str]) -> int | None:
    found = match.groupdict()
    if found.get("year"):
        return int(found["year"])
    if found.get("yy"):
        return 2000 + int(found["yy"])
    return None


def _period(kind: str, match: re.Match[str]) -> Period:
    found = match.groupdict()
    fiscal = "fiscal" if found.get("fy") else ""
    if kind in ("quarter", "half"):
        number = found.get("n") or found.get("m") or str(WORD_NUMBER[found["word"].lower()])
        months = 3 if kind == "quarter" else 6
        return Period(months, f"{'Q' if kind == 'quarter' else 'H'}{number}", fiscal, _year(match))
    if kind == "month":
        number = int(found["number"]) if found.get("number") else MONTH_NUMBER[found["month"][:3].lower()]
        return Period(1, f"M{number}", "", _year(match))
    if kind == "months":
        written = found["n"].lower()
        return Period(int(WORD_NUMBER.get(written, written)), "", "", _year(match))
    if kind == "fiscal":
        return Period(12, "", "fiscal", _year(match))
    if kind == "calendar":
        return Period(12, "", "calendar", _year(match))
    # "year": a year ended, a full year, or a bare year, which says nothing of its length.
    whole = match.group(0).lower()
    length = 12 if ("year" in whole or "annual" in whole) else None
    return Period(length, "", fiscal, _year(match))


@functools.lru_cache(maxsize=1 << 16)
def period_spans(text: str) -> tuple[tuple[int, int, Period], ...]:
    """Every period the words of a text name, with where each is, in order. A table's heading row is read for every
    cell under it, so what's read is kept."""
    found: list[tuple[int, int, Period]] = []
    rest = text
    for kind, pattern in PERIODS:
        for match in pattern.finditer(rest):
            period = _period(kind, match)
            if period != Period():
                found.append((match.start(), match.end(), period))
        rest = pattern.sub(lambda m: " " * len(m.group(0)), rest)
    return tuple(sorted(found, key=lambda item: item[0]))


def periods(text: str) -> list[Period]:
    """The distinct periods a text names, in the order it names them."""
    return list(_distinct_periods(text))


@functools.lru_cache(maxsize=1 << 16)
def _distinct_periods(text: str) -> tuple[Period, ...]:
    return tuple(dict.fromkeys(period for _, _, period in period_spans(text)))


def one(found: Iterable[Period]) -> Period | None:
    """The period a list agrees on, when it names one and only one; None otherwise."""
    distinct = list(dict.fromkeys(found))
    return distinct[0] if len(distinct) == 1 else None


# ---------------------------------------------------------------- labels

# Phrases read as one word before a label is split, so "order book" and "backlog" are the same line.
PHRASES = (
    (r"\bearnings per (?:common )?share\b|\beps\b", " eps "),
    (r"\bresearch (?:and|&) development\b|\br\s?&\s?d\b", " research "),
    (r"\border ?book\b|\bbacklog\b", " orderbook "),
    (r"\b(?:as )?(?:previously|originally|first) reported\b|\bas reported\b", " asreported "),
    (r"\bas restated\b", " restated "),
    (r"\b(?:before|pre)[\s-]?(?:income )?tax(?:es|ation)?\b", " pretax "),
    (r"\b(?:after|net of)[\s-]?(?:income )?tax(?:es|ation)?\b", " aftertax "),
    (r"\bnon[\s-]current\b", " noncurrent "),
    (r"\bnon[\s-](?:gaap|ifrs)\b", " adjusted "),
    (r"\bper share\b", " pershare "),
    # Economic data: whether a series is seasonally adjusted, and what a change is measured against.
    (r"\b(?:not|non)[\s-]seasonally[\s-]adjusted\b|\bseasonally[\s-]unadjusted\b|\bnsa\b", " notseasadj "),
    (r"\bseasonally[\s-]adjusted\b|\bsaar\b", " seasadj "),
    (r"\byear[\s-](?:on|over)[\s-]year\b|\by/y\b|\byoy\b|\by-o-y\b|\bfrom a year (?:earlier|ago|before)\b", " yoy "),
    (r"\bquarter[\s-](?:on|over)[\s-]quarter\b|\bq/q\b|\bqoq\b|\bq-o-q\b|\bfrom the (?:previous|prior) quarter\b", " qoq "),
    (r"\bmonth[\s-](?:on|over)[\s-]month\b|\bm/m\b|\bmom\b|\bm-o-m\b|\bfrom the (?:previous|prior) month\b", " mom "),
    (r"\breal[\s-]estate\b", " realestate "),
)
SAME_WORD = {"sale": "revenue", "turnover": "revenue", "revenu": "revenue", "income": "profit", "earning": "profit",
             "employee": "staff", "headcount": "staff", "people": "staff", "workforce": "staff", "personnel": "staff",
             "underlying": "adjusted", "statutory": "unadjusted", "gaap": "unadjusted", "ifrs": "unadjusted",
             "projection": "forecast", "projected": "forecast", "forecasted": "forecast", "outturn": "actual"}
# Each group holds qualifiers that tell apart lines sharing a noun. A label with one, beside a label with another of the
# same group and not its own, names a different line.
QUALIFIERS = (
    frozenset({"gross", "operating", "net"}),
    frozenset({"basic", "diluted"}),
    frozenset({"restated", "asreported"}),
    frozenset({"adjusted", "unadjusted"}),
    frozenset({"pretax", "aftertax"}),
    frozenset({"current", "noncurrent"}),
    frozenset({"real", "nominal"}),
    frozenset({"core", "headline"}),
    frozenset({"seasadj", "notseasadj"}),
    frozenset({"yoy", "qoq", "mom"}),
    frozenset({"forecast", "actual"}),
)
# A note can say a figure is a forecast in more ways than a source is taken to: "the IMF expects", "sees growth at".
# A source is held to the plain words alone, since "higher than expected" beside a result doesn't make it a forecast,
# and "project" only as a verb, since a capital project is no forecast either.
SOURCE_FORECAST = re.compile(r"\b(?:forecast(?:s|ed|ing)?|projections?|projected)\b"
                             r"|\b(?:we|it|they|staff) projects?\b|\bprojects?\s+(?:that|growth|inflation)\b", re.I)
NOTE_FORECAST = re.compile(r"\b(?:forecast|project|expect|anticipat|predict|outlook|guid|estimat|sees?\b|seen\b|will\b"
                           r"|(?:is|are|was|were) (?:set|due|likely) to\b)", re.I)
# Words that say nothing about which line a figure is on.
_GENERIC_WORDS = """
a about above after against also an and approximately are as at be been below by came compared down during end ended
ending fell for from grew had has have in increased decreased is it its item line measure metric million billion
thousand mn bn m k of on or over rose same stood the their this to total totalled totaled under up us usd was were
which with year years quarter quarters month months half fiscal calendar full annual period q h fy cy reached around
roughly some nearly almost per cent percent pct eur gbp jpy rmb cny chf hkd
"""
GENERIC = frozenset(_GENERIC_WORDS.split())
WORD = re.compile(r"[a-z][a-z&]*")


@functools.lru_cache(maxsize=1 << 16)
def label_words(text: str) -> frozenset[str]:
    """The words of a label that say which line it is: lower case, a trailing s dropped, phrases and words that mean
    the same read as one, and words that name a period, a unit or nothing in particular left out."""
    lowered = " " + text.lower() + " "
    for pattern, word in PHRASES:
        lowered = re.sub(pattern, word, lowered)
    words: set[str] = set()
    for word in WORD.findall(lowered):
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        word = SAME_WORD.get(word, word)
        if word not in GENERIC and len(word) > 1:
            words.add(word)
    return frozenset(words)


def qualifier_clash(note: frozenset[str], source: frozenset[str]) -> str:
    """How two labels name different lines by their qualifiers, as "net where the note says gross", or ""."""
    for group in QUALIFIERS:
        said, there = note & group, source & group
        if said and there and not said & there:
            return f"{'/'.join(sorted(there))} where the note says {'/'.join(sorted(said))}"
    return ""


# ---------------------------------------------------------------- units

# A currency, as a sign or a code.
MONEY = r"(?:US\$|HK\$|[$€£¥]|(?<![A-Za-z])(?:USD|EUR|GBP|JPY|RMB|CNY|CHF|HKD|ILS|NIS))"
UNIT_STATED = re.compile(rf"{MONEY}\s?(?:(?P<word>(?i:thousand|million|billion))s?|(?P<letter>[KkMmBb]|MM|bn|mn))(?![A-Za-z])"
                         r"|\b(?i:in) (?P<plain>(?i:thousand|million|billion))s\b")
UNIT_WORD = {"k": "thousand", "m": "million", "mm": "million", "mn": "million", "b": "billion", "bn": "billion"}


@functools.lru_cache(maxsize=1 << 16)
def unit_stated(text: str) -> str:
    """The unit a table's heading or lead-in states for its figures, as thousand, million or billion, or "" for none."""
    stated = UNIT_STATED.search(text)
    if not stated:
        return ""
    word = stated.group("word") or stated.group("plain")
    return word.lower() if word else UNIT_WORD[stated.group("letter").lower()]


# ---------------------------------------------------------------- a figure's surroundings

@dataclass(frozen=True)
class Context:
    """What the words around a figure say it measures. `label` is "" and `periods` empty when they can't be read.
    `row` says the label is a table row's own, a clear name for the line rather than the words of a sentence."""
    label: str = ""
    periods: tuple[Period, ...] = ()
    row: bool = False


# Where a clause ends, so the period a figure is read with is the one in its own clause: at a semicolon, at a comma
# not inside a date or a number, and before a word that brings in a second figure to compare.
CLAUSE_END = re.compile(r";|,(?!\s?\d)|\s(?=(?:against|compared (?:with|to)|versus|vs\.?|from|up from|down from)\s)|"
                        r"(?<=[.!?])\s+(?=[A-Z])|\n")
# A comparative in brackets, as UK and European reports give the prior year beside this year's figure: "£551.1m (2024:
# £572.5m)", "1,757 staff (FY24: 1,820)". It's read only when what comes before its colon names a period and what
# comes after holds a figure.
COMPARATIVE = re.compile(r"\((?P<head>[^():;\n]{1,30}?)\s*:\s*(?P<body>[^()\n]{1,60})\)")


def comparatives(text: str) -> list[tuple[int, int]]:
    """Where each comparative in brackets stands in a text, its brackets included."""
    return [(found.start(), found.end()) for found in COMPARATIVE.finditer(text)
            if periods(found.group("head")) and re.search(r"\d", found.group("body"))]


def clause(text: str, start: int, end: int) -> tuple[int, int]:
    """The bounds of the clause around a span of text. A comparative in brackets is a clause of its own: its period is
    the figure's inside it, and never the one's before it."""
    brackets = comparatives(text)
    for low, high in brackets:
        if low < start and end < high:
            return low + 1, high - 1
    begins = [m.end() for m in CLAUSE_END.finditer(text, 0, start)] + [high for _, high in brackets if high <= start]
    after = CLAUSE_END.search(text, end)
    ends = ([after.start()] if after else []) + [low for low, _ in brackets if low >= end]
    return max(begins, default=0), min(ends, default=len(text))


def nearest_period(text: str, start: int, end: int) -> tuple[Period, ...]:
    """The period named in the clause around a figure. When the clause names more than one, the one nearest the figure,
    if one is clearly nearer; otherwise none."""
    low, high = clause(text, start, end)
    spans = [(max(s - end, start - e, 0), period) for s, e, period in period_spans(text[low:high])
             for s, e in [(s + low, e + low)]]
    distinct = {period for _, period in spans}
    if len(distinct) <= 1:
        return tuple(distinct)
    spans.sort(key=lambda item: item[0])
    if spans[1][0] - spans[0][0] < 4 and spans[0][1] != spans[1][1]:
        return ()
    return (spans[0][1],)


def _split(row: str) -> list[str]:
    return row.split("|")


def _cell_at(row: str, offset: int) -> int:
    return row.count("|", 0, offset)


NUMERIC_CELL = re.compile(r"\s*[$€£¥]?\s*\(?-?[$€£¥]?\d[\d,]*(?:\.\d+)?\)?\s*%?\s*")


def column_period(header: str, row: str, column: int) -> Period | None:
    """The period a header row gives the column a figure is in. Cells line up when the two rows have as many; when
    they don't, as when a currency sign has a cell of its own, the figures in the row are matched in order to the
    header's cells that name a period, if there are as many of each; failing that, a header naming one period alone
    gives it to every column."""
    heads, cells = _split(header), _split(row)
    if len(heads) == len(cells):
        found = one(periods(heads[column]))
        if found:
            return found
    numeric = [index for index, cell in enumerate(cells) if NUMERIC_CELL.fullmatch(cell)]
    named = [one(periods(cell)) for cell in heads if periods(cell)]
    if column in numeric and len(named) == len(numeric):
        return named[numeric.index(column)]
    return one(periods(header))


def table_context(lines: list[str], at: int, offset: int) -> Context:
    """What a figure in a table row measures: the row's label, the first cell before the figure with words in it, and
    the period its column's heading gives, read from the nearest row above that names one. A heading that gives only
    a year takes the length or quarter that the rows above it, or the line before the table, name, when they name one."""
    row = lines[at]
    column = _cell_at(row, offset)
    cells = _split(row)
    label = next((cell.strip() for cell in cells[:column] if len(re.findall(r"[A-Za-z]", cell)) >= 2), "")
    own = periods(label)
    found: Period | None = None
    above = at - 1
    while above >= 0 and "|" in lines[above]:
        if periods(lines[above]):
            found = column_period(lines[above], row, column)
            break
        above -= 1
    # What the rows above the heading, and the line before the table, say of the length.
    top = above
    while top >= 0 and "|" in lines[top]:
        top -= 1
    # The heading row itself may give the length in a cell of its own: "Year ended December 31 | 2025 | 2024".
    kinds = [period for line in lines[max(top, 0):max(above, 0) + 1] for period in periods(line)]
    kinds += periods(lines[top]) if top >= 0 else []
    if found:
        lengths = one(Period(p.months, p.part, p.basis) for p in kinds if p.months)
        if lengths:
            found = found.filled_from(lengths)
        return Context(label, (found,), True)
    return Context(label, tuple(own), True)


def source_context(text: str, start: int, end: int) -> Context:
    """What a figure found in a source's text, between `start` and `end`, measures, as the words around it say."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line_end = len(text) if line_end < 0 else line_end
    line = text[line_start:line_end]
    if "|" in line:
        # The 40 lines up to this one are enough to find a table's heading, and far cheaper than all of a long filing.
        begin = line_start
        for _ in range(40):
            if begin == 0:
                break
            begin = text.rfind("\n", 0, begin - 1) + 1
        lines = text[begin:line_end].split("\n")
        return table_context(lines, len(lines) - 1, start - line_start)
    # A clause never runs past a line's end, so only the line is read.
    at, until = start - line_start, end - line_start
    low, high = clause(line, at, until)
    return Context(line[low:high].strip(), nearest_period(line, at, until), False)


def note_context(row: str, start: int, end: int, header: list[str], heading: str) -> Context:
    """What a figure in a note measures. In a table row: the row's first cell, and the period its column's heading
    names, or failing that its row or the table's first heading. Elsewhere: the clause it stands in, with the period
    that clause names. A period that says only a year takes the length or quarter its section's heading names."""
    if row.startswith("|"):
        column = _cell_at(row, start) - 1
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        label = cells[0] if column > 0 else ""
        found = periods(header[column]) if 0 <= column < len(header) else []
        if not found:
            found = periods(label) or (periods(header[0]) if header else [])
    else:
        low, high = clause(row, start, end)
        label = row[low:high].strip(" -*")
        found = list(nearest_period(row, start, end))
    if not found:
        found = periods(heading)
    lengths = one(Period(p.months, p.part, p.basis) for p in periods(heading) if p.months)
    if lengths:
        found = [period.filled_from(lengths) for period in found]
    return Context(label, tuple(dict.fromkeys(found)), row.startswith("|"))


# ---------------------------------------------------------------- comparing them

AGREES, OTHER_PERIOD, OTHER_LABEL, UNREAD = "agrees", "other_period", "other_label", "unread"


def compare(note: Context, source: Context) -> tuple[str, str]:
    """Whether the words around a figure in a source say it measures what the note says it does: (AGREES or
    OTHER_PERIOD or OTHER_LABEL, why), or (UNREAD, "") when neither the period nor the label can be compared."""
    read = False
    if note.periods and source.periods:
        read = True
        if not any(not differ(a, b) for a in note.periods for b in source.periods):
            there = ", ".join(p.shown() for p in source.periods)
            said = ", ".join(p.shown() for p in note.periods)
            why = differ(note.periods[0], source.periods[0])
            return OTHER_PERIOD, f"beside {there} in the source where the note says {said} ({why})"
    said_words, there_words = label_words(note.label), label_words(source.label)
    clash = qualifier_clash(said_words, there_words)
    if clash:
        return OTHER_LABEL, f"beside {source.label[:60]!r}: {clash}"
    if (said_words and SOURCE_FORECAST.search(source.label) and not said_words & {"forecast", "actual"}
            and not NOTE_FORECAST.search(note.label)):
        return OTHER_LABEL, f"beside {source.label[:60]!r}: a forecast in the source, where the note doesn't say it is one"
    if said_words and there_words:
        if any(said_words & group and there_words & group for group in QUALIFIERS):
            read = True
        if source.row:
            read = True
            if not said_words & there_words:
                return OTHER_LABEL, f"in the row {source.label[:60]!r}, where the note's line reads {note.label[:60]!r}"
    return (AGREES, "") if read else (UNREAD, "")


def verdict(note: Context, sources: Iterable[Context]) -> tuple[str, str]:
    """The verdict over every place a source holds a figure. It agrees when one place agrees; it isn't judged when
    any place can't be read, since that may be the one meant; only when every place reads as another period or line is
    that the verdict, with the first place's reason."""
    outcomes = [compare(note, source) for source in sources]
    if not outcomes:
        return UNREAD, ""
    for wanted in (AGREES, UNREAD):
        if any(outcome == wanted for outcome, _ in outcomes):
            return wanted, ""
    first_period = next((o for o in outcomes if o[0] == OTHER_PERIOD), None)
    return first_period or outcomes[0]


def unreadable(note: Context) -> bool:
    """Whether a note's words say nothing a source could be compared with."""
    return not note.periods and not label_words(note.label)


def blank(text: str, pattern: re.Pattern[str]) -> str:
    """Text with every match of a pattern turned to blanks of the same length, so positions in it still hold."""
    return pattern.sub(lambda m: " " * len(m.group(0)), text)
