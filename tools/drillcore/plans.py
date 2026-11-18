"""Plans and expectations for a period that had begun by the data cut-off.

A draft written after its data were closed can still say what a company "plans" or "expects" for a period that was
under way, or over, when the data were closed: "the Harbor plant is planned to open in the second half of 2026", with a
cut-off of 31 October 2026. By then the plan had partly happened, or slipped, and a reader can't tell which. `assay`
warns of each such sentence when the workspace sets its cut-off:

    [assay]
    cutoff = 2026-10-31

A sentence is about a plan when it has a verb such as "plans to", "planned", "expects", "expected to", "intends to",
"aims to", "scheduled", "due to be", "on track" or "will"; "the plan" and "expected growth" aren't. Only dates after that
word are read, so in "announced in March 2025 that it plans to move in 2026" the announcement's date isn't the plan's.

A date is a day or a month ("1 March 2026", "March 2026"), a quarter ("the third quarter of 2026", "Q3 2026"), a half
("the second half of 2026", "H2 2026"), part of a year ("early 2026", "mid-2026", "late 2026", "the end of 2026") or a
year after "in", "during", "for", "throughout" or "by". One that starts on or before the cut-off is a warning. "By"
names a deadline, so "by 2026" is judged by the year's end, and only a deadline already past is a warning. Citations are passed over: their years date a source.
"""
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta

from assay import claims as assay_claims
from assay import text as assay_text

# What makes a sentence one about a plan or an expectation, rather than what happened.
# Each is a verb, so "the materials plan" or "lower expected growth" isn't one.
PLAN = re.compile(r"\b(?:plan(?:s|ning)?\s+to|planned|intend(?:s|ed)?\s+to|expects|expect(?:ed)?\s+to|aim(?:s|ed)?\s+to|"
                  r"targets?\s+(?:to|for)|scheduled|due\s+to\s+(?:be|close|complete|start|begin|open|move|end|launch|take)|"
                  r"on\s+track|set\s+to\s+(?:be|close|complete|start|begin|open|move|end|launch|take)|anticipates|"
                  r"anticipated\s+to|forecasts|projected\s+to|will)\b", re.I)
# A year, unnamed, since a pattern may give it in either of two forms; `_year_of` reads it.
_YEAR = r"(?:19|20)\d{2}"
_YEARS = re.compile(_YEAR)
_FISCAL = r"(?:(?:fiscal|calendar)\s+(?:year\s+)?)?"
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
# Month names are read with their capital, so the verb "may" is never May.
DAY_MONTH = re.compile(r"\b(?:(?P<day>\d{1,2})\s+)?(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|"
                       r"July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+"
                       rf"(?:(?P<day2>\d{{1,2}}),?\s+)?{_YEAR}\b")
QUARTER = re.compile(rf"\b(?:the\s+)?(?P<word>first|second|third|fourth)\s+quarter\s+(?:of\s+)?{_FISCAL}{_YEAR}\b"
                     rf"|\bQ(?P<number>[1-4])\s*(?:of\s+)?{_FISCAL}{_YEAR}\b", re.I)
HALF = re.compile(rf"\b(?:the\s+)?(?P<word>first|second)\s+half\s+(?:of\s+)?{_FISCAL}{_YEAR}\b"
                  rf"|\bH(?P<number>[12])\s*(?:of\s+)?{_FISCAL}{_YEAR}\b|\b(?P<before>[12])H\s*{_YEAR}\b", re.I)
PART = re.compile(rf"\b(?P<part>early|mid|late)[-\s]+(?:in\s+)?{_FISCAL}{_YEAR}\b"
                  rf"|\b(?:the\s+)?(?P<end>end|close)\s+of\s+(?:the\s+year\s+)?{_FISCAL}{_YEAR}\b", re.I)
YEAR_ALONE = re.compile(rf"\b(?P<word>in|during|for|throughout|by)\s+(?:the\s+)?{_FISCAL}{_YEAR}\b", re.I)
# An in-text citation: its year dates a source, not a plan.
CITATION = re.compile(r"\((?:[^()]|\([^()]*\))*?(?:\b(?:1[5-9]|20)\d{2}[a-z]?\b|\bn\.d\.)(?:[^()]|\([^()]*\))*\)")
ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4}
PARTS = {"early": (1, 4), "mid": (5, 8), "late": (9, 12)}


@dataclass(frozen=True)
class Period:
    written: str
    start: date
    end: date
    deadline: bool      # "by 2026": only its end matters
    at: int             # where it's written in the sentence


def _year_of(match: re.Match[str]) -> int:
    """The year a date gives: the last a match holds, since a day or a quarter's number is never four digits."""
    return int(_YEARS.findall(match.group(0))[-1])


def _month_end(year: int, month: int) -> date:
    return (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) - timedelta(days=1)


def _months(year: int, first: int, last: int) -> tuple[date, date]:
    return date(year, first, 1), _month_end(year, last)


def periods(sentence: str) -> list[Period]:
    """The dates a sentence gives, each as the period it names; where two overlap, the more precise one."""
    found: list[Period] = []
    taken: list[tuple[int, int]] = []

    def add(match: re.Match[str], start: date, end: date, deadline: bool = False) -> None:
        if any(match.start() < right and left < match.end() for left, right in taken):
            return
        taken.append((match.start(), match.end()))
        found.append(Period(match.group(0), start, end, deadline, match.start()))

    for match in DAY_MONTH.finditer(sentence):
        year, month = _year_of(match), MONTHS.index(match.group("month")[:3].casefold()) + 1
        day = match.group("day") or match.group("day2")
        try:
            add(match, *((date(year, month, int(day)),) * 2 if day else _months(year, month, month)))
        except ValueError:
            continue  # No such day.
    for match in QUARTER.finditer(sentence):
        quarter = ORDINAL[match.group("word").casefold()] if match.group("word") else int(match.group("number"))
        add(match, *_months(_year_of(match), 3 * quarter - 2, 3 * quarter))
    for match in HALF.finditer(sentence):
        half = (ORDINAL[match.group("word").casefold()] if match.group("word")
                else int(match.group("number") or match.group("before")))
        add(match, *_months(_year_of(match), 6 * half - 5, 6 * half))
    for match in PART.finditer(sentence):
        first, last = PARTS[match.group("part").casefold()] if match.group("part") else (12, 12)
        add(match, *_months(_year_of(match), first, last))
    for match in YEAR_ALONE.finditer(sentence):
        add(match, *_months(_year_of(match), 1, 12), deadline=match.group("word").casefold() == "by")
    return sorted(found, key=lambda period: period.at)


def check(draft: str, cutoff: date) -> Iterator[tuple[int, str, str]]:
    """Each date a sentence about a plan or an expectation gives, after the word that makes it one, for a period that
    had begun by the cut-off (or a deadline that had passed): as its line, the date as written, and why."""
    text = assay_text.matchable(draft)
    at = 0
    for sentence in assay_claims.SENTENCE.split(text):
        at = text.index(sentence, at)
        plain = CITATION.sub(lambda match: " " * len(match.group(0)), sentence)
        plan = PLAN.search(plain)
        if plan:
            for period in periods(plain[plan.end():]):
                if period.deadline and period.end >= cutoff or not period.deadline and period.start > cutoff:
                    continue
                when = "had ended" if period.end < cutoff else "was under way"
                line = text.count("\n", 0, at + plan.end() + period.at) + 1
                yield (line, period.written, f"a plan or expectation ({plan.group(0)!r}) for a period that {when} by the "
                       f"data cut-off of {cutoff.isoformat()} ([assay] cutoff): say what had happened by then, or when "
                       "the plan was stated")
        at += len(sentence)
