"""The workspace's own record, and the figures a draft gives about it.

A report usually ends with the evidence behind it: how many sources the notes cite, how many were fetched, what the
last `check` judged and what it couldn't. Those figures describe this workspace, so they can be held to it exactly.
`proof`'s check "workspace figures" reads the sections `[proof] workspace_sections` names (a heading such as
"Appendix C", in a draft or a companion file; a section runs to the next heading of its level or above) and holds each
figure there that names a measure of the record to the measure's value:

- from the database now: source entries and distinct source addresses, fetches, documents with stored text,
  companies, tagged SEC facts, the filings those facts were drawn from, and the entries of the companies' filing lists;
- from the last `claims` run, as the database keeps it: figures compared, matching, mismatched, and with no fact;
- from the last `check` run, which keeps its counts for this (`keep`): judged, failed, waived, warnings, not judged,
  inputs to derived figures, and lines that cite no source.

A figure is read with the words right after it ("412 judged", "9 waived", "none mismatch", "31 distinct source
addresses"), or for the filings behind the facts, the words before it as well ("tagged facts from 25 filings"). A
figure no measure's words follow isn't judged, and neither is a day of a date or a year, nor a part of a measure: the
words "whose", "that", "with" and the like after its name, "13 source entries whose copy is a data file", make it one. A figure that differs from its
measure fails, giving the value, and naming the measure it is the value of, if any: the filing-list entries given as
the filings the facts were drawn from. One that an earlier `check` run gave is a warning naming that run, since a draft
may report a dated run, though it rarely means to.

Some words name two measures. "Inputs to derived figures" are counted twice by `check`: those not judged, for want of
a source, and those warned of, traced to no row; either passes. "Sources" alone is read as distinct addresses, and the
count of entries, which counts a source again for each note that cites it, is a warning. "Filings" alone passes as the
filings the facts were drawn from or as the filing-list entries. Those two, and "companies", are judged only on a line
that gives another measure too, so "three filings of 12 November" in a sentence about the cut-off is passed over.

A line labelled "Not judged:" or "Warnings:" gives a breakdown, and its counts must add up to the last `check` run's
total: a list that leaves some out is a warning naming how many, and one that adds up to more fails. Counts in
brackets break one part down further, "83 workings and totals (69 workings, 14 totals)", and aren't parts.

A count can be the right number and still be called the wrong thing, so a run also keeps what its counts are made of
(`parts`), and the words a draft puts right after a count, or for "judged" the label before it, must name that: a
count of quotations and figures called "figures", results that stand on fewer lines called "lines", workings and
totals called "sums". A count is held to this when it is the run's count of a measure, or in a breakdown, of one
status alone.

When the notes have changed since the last `check` run, or no run has kept its counts, the section gets one warning
saying to run `check` first, since a run's figures describe the notes it read.
"""
import hashlib
import re
import sqlite3
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from . import research
from .drafts import HEADING
from .sourcedb import note_files
from .workspace import Workspace

SCHEMA = """
CREATE TABLE IF NOT EXISTS run_counts (
    run INTEGER NOT NULL,           -- a run of `runs`
    measure TEXT NOT NULL,          -- judged, failed, waived, warnings, not judged, "not judged: <status>",
                                    -- "warning: <status>", "notes", or what one is made of (`parts`)
    value TEXT NOT NULL             -- a count, or for "notes" the digest of the notes the run read
);
CREATE INDEX IF NOT EXISTS ix_run_counts ON run_counts(run);
"""
NOTES = "notes"
PASS, WARN, FAIL = "pass", "warn", "fail"


def digest(ws: Workspace) -> str:
    """One digest of every note's name and text, which changes whenever a note does."""
    found = hashlib.sha256()
    for path in note_files(ws):
        found.update(path.name.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return found.hexdigest()


def counts(judged: int, verdicts: Counter[tuple[str, str]]) -> dict[str, int]:
    """A `check` run's counts, from how many it judged against a source and how many results it gave by (verdict,
    status): failed, waived, warnings and not judged, and each status of the last two."""
    found = {"judged": judged}
    for verdict, measure in ((research.FAIL, "failed"), (research.WAIVED, "waived"), (research.WARN, "warnings"),
                             (research.NOT_JUDGED, "not judged")):
        found[measure] = sum(n for (each, _), n in verdicts.items() if each == verdict)
    for (verdict, status), n in verdicts.items():
        if verdict in (research.WARN, research.NOT_JUDGED):
            # Named as a reader says them: "warning: input_not_traced", "not judged: no_source_key".
            found[f"{verdict}: {status}"] = found.get(f"{verdict}: {status}", 0) + n
    return found


MADE_OF, LINES_OF = "part: ", "lines: "


def parts(results: Iterable[research.Result]) -> dict[str, int]:
    """What some of a run's counts are made of, kept beside `counts`: those judged against a source, and each status
    warned of or not judged, by what one result counts (`research.Result.kind`): "part: judged: quotation", "part: not
    judged: no_source_key: row". And for each status, the lines of the notes its results stand on, "lines: not judged:
    no_source_key", since one line can hold two quotations."""
    found: Counter[str] = Counter()
    lines: dict[str, set[tuple[str, int]]] = {}
    for r in results:
        verdict = r.verdict
        if r.check in research.AGAINST_SOURCES and r.status not in research.DECLARED and verdict != research.NOT_JUDGED:
            found[f"{MADE_OF}judged: {r.kind}"] += 1
        if verdict in (research.WARN, research.NOT_JUDGED):
            status = f"{verdict}: {r.status}"
            found[f"{MADE_OF}{status}: {r.kind}"] += 1
            lines.setdefault(status, set()).add((r.note, r.line_no))
    return dict(found) | {f"{LINES_OF}{status}": len(at) for status, at in lines.items()}


def keep(con: sqlite3.Connection, ws: Workspace, command: str, kept: dict[str, int]) -> None:
    """Keep a run's counts beside the run `history` recorded last for `command`, with the digest of the notes it
    read. Counts of runs `history` no longer keeps go with them."""
    con.executescript(SCHEMA)
    found = con.execute("SELECT id FROM runs WHERE command=? ORDER BY id DESC LIMIT 1", (command,)).fetchone()
    if not found:
        return
    con.executemany("INSERT INTO run_counts VALUES (?,?,?)",
                    [(found[0], measure, str(value)) for measure, value in kept.items()] + [(found[0], NOTES, digest(ws))])
    con.execute("DELETE FROM run_counts WHERE run NOT IN (SELECT id FROM runs)")
    con.commit()


@dataclass(frozen=True)
class Run:
    """A run's kept counts, by measure, and when it ran."""
    ran_at: str
    kept: dict[str, str]

    def values(self) -> dict[str, int]:
        """The counts, without the notes' digest."""
        return {measure: int(value) for measure, value in self.kept.items() if measure != NOTES}


def runs(con: sqlite3.Connection, command: str = "check") -> list[Run]:
    """The runs of `command` that kept counts, the latest first."""
    con.executescript(SCHEMA)
    kept: dict[int, Run] = {}
    for run, ran_at, measure, value in con.execute(
            "SELECT runs.id, runs.ran_at, measure, value FROM run_counts JOIN runs ON runs.id = run_counts.run"
            " WHERE runs.command=? ORDER BY runs.id DESC", (command,)):
        kept.setdefault(run, Run(ran_at, {})).kept[measure] = value
    return list(kept.values())


# ---------------------------------------------------------------- the measures

@dataclass(frozen=True)
class Measure:
    """A measure of the record: what a draft calls it, read in the words after a figure (and, for some, before it).
    `keys` are what it may be, the first the one it is read as; a figure that gives another passes, with `other` as
    the verdict when that isn't a pass."""
    keys: tuple[str, ...]
    after: re.Pattern[str]
    before: re.Pattern[str] | None = None
    from_run: bool = False          # kept by the last `check` run, rather than read from the database now
    alone: bool = True              # judged on a line that gives no other measure
    other: str = PASS


# Words after a measure's own that make the figure a part of it: "13 source entries whose copy is a data file".
PART = r"whose|that|which|where|with|without|not|nothing|no|except|other\s+than|of\s+which|among"


def _after(words: str) -> re.Pattern[str]:
    return re.compile(rf"^[\s*_]*(?:{words})\b(?![\s*_]+(?:{PART})\b)", re.I)


SAID = {
    "judged": "quotations and figures judged against a source", "not judged": "not judged", "failed": "failed",
    "waived": "waived", "warnings": "warnings",
    "not judged: input_not_judged": "inputs to derived figures not judged",
    "warning: input_not_traced": "inputs to derived figures traced to no row (warnings)",
    "not judged: no_source_key": "rows of figures and quotations citing no source",
    "compared": "figures compared with tagged facts", "match": "figures matching a tagged fact",
    "mismatch": "figures that mismatch a tagged fact", "no_fact": "figures with no tagged fact",
    "facts": "tagged facts", "fact filings": "filings the tagged facts were drawn from",
    "filing list": "entries of the companies' filing lists", "companies": "companies", "fetches": "fetches",
    "documents": "documents with stored text", "addresses": "distinct source addresses",
    "entries": "source entries (a source two notes cite counts twice)",
}
# The order matters: the first measure whose words fit is the one a figure is read as.
MEASURES = (
    Measure(("judged",), _after(r"(?:figures?\s+)?judged"), from_run=True),
    Measure(("not judged",), _after(r"(?:figures?\s+|items?\s+|results?\s+)?not\s+judged"), from_run=True),
    Measure(("failed",), _after(r"(?:figures?\s+)?failed|failures?"), from_run=True),
    Measure(("waived",), _after(r"(?:figures?\s+)?waived|waivers?"), from_run=True),
    Measure(("warnings",), _after(r"warnings?|(?:figures?\s+)?warned"), from_run=True),
    Measure(("not judged: input_not_judged", "warning: input_not_traced"),
            _after(r"inputs?\s+(?:to|of)\s+(?:derived|worked[- ]out|computed)"), from_run=True),
    Measure(("not judged: no_source_key",), _after(r"(?:lines?|rows?)\s+(?:that\s+|which\s+)?(?:cites?|citing|with)\s+no\s+source"),
            from_run=True),
    Measure(("compared",), _after(r"(?:[\w,()'’-]+\s+){0,5}?compared")),
    Measure(("mismatch",), _after(r"mismatch(?:es|ed)?")),
    Measure(("match",), _after(r"match(?:es|ed|ing)?")),
    Measure(("no_fact",), _after(r"(?:have\s+|with\s+)?no\s+tagged\s+facts?")),
    Measure(("facts",), _after(r"(?:tagged\s+|SEC\s+)?facts")),
    Measure(("filing list",), _after(r"entries"), re.compile(r"filing[- ]lists?\b[^.;]{0,20}$", re.I)),
    Measure(("filing list",), _after(r"filing[- ]list\s+entries|filings\s+listed|entries\s+in\s+(?:the\s+)?(?:\w+'\s+)?filing\s+lists?")),
    Measure(("fact filings",), _after(r"(?:of\s+(?:their|the|its)\s+)?filings"), re.compile(r"\bfacts?\b[^.;]{0,30}\bfrom\s+$", re.I)),
    Measure(("fetches",), _after(r"fetch(?:es)?|(?:sources?\s+|addresses\s+)?fetched")),
    Measure(("documents",), _after(r"(?:stored\s+)?documents?\s+(?:with|holding)\s+(?:stored\s+)?text|stored\s+documents")),
    Measure(("addresses",), _after(r"(?:distinct\s+)?(?:source\s+)?addresses")),
    Measure(("entries",), _after(r"source\s+entries(?!\s+(?:that\s+)?(?:nothing|nobody|no\s+\w+)\s+cites?)")),
    Measure(("companies",), _after(r"companies"), alone=False),
    Measure(("addresses", "entries"), _after(r"(?:distinct\s+)?sources"), alone=False, other=WARN),
    Measure(("fact filings", "filing list"), _after(r"filings"), alone=False),
)

WORDS = {word: n for n, word in enumerate((
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
    "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"))} | {"none": 0}
# A count: digits, with commas between thousands, and not part of a decimal, a percentage, an amount or a path; or a
# number word up to twenty, or "none".
COUNT = re.compile(r"(?<![\w.,$€£/-])(?P<digits>\d{1,3}(?:,\d{3})+|\d+)(?![\w%]|[.,]\d)"
                   rf"|(?<![\w-])(?P<word>{'|'.join(WORDS)})(?![\w-])", re.I)
_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
MONTH_AFTER = re.compile(rf"^\s+{_MONTH}(?!\w)", re.I)
MONTH_BEFORE = re.compile(rf"\b{_MONTH}\s+$", re.I)
BREAKDOWN = re.compile(r"^[\s>*_-]*(?P<label>Not judged|Warnings)[\s*_]*:(?P<rest>.*)$", re.I)


def counts_in(line: str) -> Iterator[tuple[int, int, int]]:
    """Each count in a line: (value, start, end). A day of a date and a year aren't counts."""
    for match in COUNT.finditer(line):
        if match.group("word"):
            yield WORDS[match.group("word").lower()], match.start(), match.end()
            continue
        digits = match.group("digits")
        value = int(digits.replace(",", ""))
        if (1900 <= value <= 2100 and "," not in digits) or MONTH_AFTER.match(line[match.end():]) \
                or MONTH_BEFORE.search(line[:match.start()]):
            continue
        yield value, match.start(), match.end()


def measure_of(line: str, start: int, end: int) -> Measure | None:
    """The measure a count names by the words around it, or None."""
    after, before = line[end:end + 80], line[max(0, start - 60):start]
    for measure in MEASURES:
        if measure.after.match(after) and (measure.before is None or measure.before.search(before)):
            return measure
    return None


# ---------------------------------------------------------------- what a count is said to count

# A count can be the right number and still be called the wrong thing. `check` judges quotations as well as figures,
# so "Figures held to their source: 412 judged" calls quotations figures; a row can hold two quotations, so "12 lines
# that cite no source" can be lines that number fewer; and a working the arithmetic couldn't read isn't a sum. A run
# keeps what each of its counts is made of (`parts`), and the words a draft puts right after a count ("83 sums",
# "126 lines", "20 quotations and 9 totals" for the first, quotations) name the kinds of result they count: the
# figure must be the count of those. Words naming none of these say nothing about it, and nor do counts of a run
# that kept no makeup.
LINES = "lines"
NUMERIC = frozenset({"row", "figure", "input", "working", "total"})
NOUNS: tuple[tuple[re.Pattern[str], frozenset[str] | str], ...] = (
    (re.compile(r"quot(?:ations?|es?)\b", re.I), frozenset({"quotation"})),
    (re.compile(r"(?:table\s+)?(?:totals?|sums?)\b", re.I), frozenset({"total"})),
    (re.compile(r"(?:worked[- ]out|computed|derived)\s+figures?\b|workings?\b|calculations?\b", re.I), frozenset({"working"})),
    (re.compile(r"inputs?\b", re.I), frozenset({"input"})),
    (re.compile(r"(?:source\s+)?entries\b", re.I), frozenset({"entry"})),
    (re.compile(r"rows?\s+of\s+figures\b", re.I), frozenset({"row"})),
    (re.compile(r"figures?\b|numbers\b", re.I), NUMERIC),
    (re.compile(r"lines?\b|rows?\b", re.I), LINES),
)
JOINED_NOUN = re.compile(r"\s*(?:,\s*)?(?:and|or|&)\s+|\s*,\s*", re.I)
KIND_SAID = {"quotation": "quotations", "row": "rows of figures", "figure": "single figures warned about",
             "input": "inputs of worked-out rows", "working": "workings", "total": "table totals",
             "entry": "source entries"}


def kinds_after(words: str) -> frozenset[str] | str | None:
    """The kinds of result the words right after a count name, or LINES for lines of the notes; None for none. Nouns
    joined by "and" or "or" are read together, "workings and totals", but a count after the comma ends them:
    "20 quotations, 9 totals" names quotations alone for the 20."""
    at = len(words) - len(words.lstrip(" *_"))
    kinds: set[str] = set()
    while noun := _noun(words, at):
        found, kind = noun
        if isinstance(kind, str):
            return LINES if not kinds else frozenset(kinds)
        kinds |= kind
        joined = JOINED_NOUN.match(words, found.end())
        if not joined:
            break
        at = joined.end()
    return frozenset(kinds) or None


def _noun(words: str, at: int) -> tuple[re.Match[str], frozenset[str] | str] | None:
    """The first noun of NOUNS that the words start with at `at`, and what it names."""
    for pattern, kind in NOUNS:
        if found := pattern.match(words, at):
            return found, kind
    return None


def kinds_in_label(before: str) -> frozenset[str] | None:
    """The kinds of result a label before a count names, "Quotations and figures held to their source: 412 judged":
    every kind any of its nouns names. Lines aren't read from a label."""
    clause = re.split(r"[.;]\s", before)[-1]
    kinds: set[str] = set()
    for pattern, kind in NOUNS:
        if isinstance(kind, frozenset) and re.search(rf"(?<!\w)(?:{pattern.pattern})", clause, pattern.flags):
            kinds |= kind
    return frozenset(kinds) or None


def misnamed(value: int, key: str, words: frozenset[str] | str | None, latest: dict[str, int]) -> str | None:
    """Why `value`, the last run's count of `key` ("judged", "not judged: no_source_key"), isn't a count of what
    `words` name; None when it is, when the words name nothing, or when the run kept no makeup of that count."""
    makeup = {name[len(f"{MADE_OF}{key}: "):]: n for name, n in latest.items()
              if name.startswith(f"{MADE_OF}{key}: ") and ": " not in name[len(f"{MADE_OF}{key}: "):]}
    if not words or not makeup or sum(makeup.values()) != value:
        return None
    made = ", ".join(f"{_n(n)} {KIND_SAID.get(kind, kind)}" for kind, n in sorted(makeup.items(), key=lambda kv: (-kv[1], kv[0])))
    if words == LINES:
        on = latest.get(f"{LINES_OF}{key}")
        if on is None or on == value:
            return None
        return f"{_n(value)} counts results ({made}), and they stand on {_n(on)} lines of the notes"
    given = sum(n for kind, n in makeup.items() if kind in words)
    if given == value:
        return None
    return f"{_n(value)} counts {made}; the words after it name {_n(given)} of them"


# ---------------------------------------------------------------- the values now

QUERIES = {
    "entries": "SELECT count(*) FROM sources", "addresses": "SELECT count(DISTINCT url) FROM sources",
    "fetches": "SELECT count(*) FROM fetches", "documents": "SELECT count(*) FROM documents",
    "companies": "SELECT count(*) FROM companies", "facts": "SELECT count(*) FROM xbrl_facts",
    "fact filings": "SELECT count(DISTINCT accession) FROM xbrl_facts", "filing list": "SELECT count(*) FROM filings",
    "compared": "SELECT count(*) FROM xbrl_claims",
}


def values(con: sqlite3.Connection) -> dict[str, int]:
    """Each measure the database gives now, with the last `claims` run's counts. A table that isn't there gives none."""
    found: dict[str, int] = {}
    for key, query in QUERIES.items():
        try:
            found[key] = con.execute(query).fetchone()[0]
        except sqlite3.OperationalError:
            pass
    if found.get("compared"):
        statuses = Counter(dict(con.execute("SELECT status, count(*) FROM xbrl_claims GROUP BY status").fetchall()))
        found["match"], found["mismatch"], found["no_fact"] = statuses["match"], statuses["MISMATCH"], statuses["no_fact"]
    return found


# ---------------------------------------------------------------- the sections

def sections(text: str, named: tuple[str, ...]) -> Iterator[tuple[int, int, str]]:
    """The lines of each section a heading in `named` opens: (line number, the heading's line number, line). A
    heading names a section when its title starts with one of `named`, in any case."""
    level = heading_at = 0
    wanted = tuple(name.casefold() for name in named)
    for line_no, line in enumerate(text.split("\n"), 1):
        heading = HEADING.match(line)
        if heading:
            depth = len(heading.group("marks"))
            if level and depth <= level:
                level = 0
            if not level and wanted and heading.group("title").strip("*_ ").casefold().startswith(wanted):
                level, heading_at = depth, line_no
            continue
        if level:
            yield line_no, heading_at, line


@dataclass(frozen=True)
class Found:
    """What the check found at one line: a verdict, the figure as the draft gives it, and why."""
    line: int
    verdict: str
    item: str
    detail: str


def _n(value: int) -> str:
    return f"{value:,}"


def _item(line: str, start: int) -> str:
    """The figure and the words after it, to the end of the clause."""
    return re.split(r"[,.;:(]\s|[;(]|\*\*|[.,]$", line[start:start + 60])[0].strip(" *_")


def judge(text: str, named: tuple[str, ...], now: dict[str, int], kept: list[Run], notes_now: str) -> Iterator[Found]:
    """Every finding for the sections of one text that `named` opens, against the values `now` and the `check` runs
    `kept`, the latest first. `notes_now` is the notes' digest today."""
    said_of_run: set[int] = set()
    for line_no, heading_at, line in sections(text, named):
        read = [(value, start, end, measure) for value, start, end in counts_in(line) if (measure := measure_of(line, start, end))]
        firm = any(measure.alone for _, _, _, measure in read)
        for value, start, end, measure in read:
            if not (measure.alone or firm):
                continue
            if measure.from_run:
                if heading_at not in said_of_run:
                    said_of_run.add(heading_at)
                    if not kept:
                        yield Found(heading_at, WARN, "", "no `check` run has kept its counts, so the figures from one "
                                    "aren't judged: run `check`, then `proof`")
                    elif kept[0].kept.get(NOTES) != notes_now:
                        yield Found(heading_at, WARN, "", f"the notes have changed since the last `check` run "
                                    f"({kept[0].ran_at}), so its figures describe the notes as they were: run `check` again")
                if kept:
                    yield _named(_judged(line_no, _item(line, start), value, measure, kept[0].values(), kept),
                                 line, start, end, value, measure, kept[0].values())
            elif measure.keys[0] in now:
                yield _judged(line_no, _item(line, start), value, measure, now, [])
        if kept and (breakdown := BREAKDOWN.match(line)):
            yield from _breakdown(line_no, breakdown, kept, {start for _, start, _, _ in read})


def _named(found: Found, line: str, start: int, end: int, value: int, measure: Measure, latest: dict[str, int]) -> Found:
    """A figure that is the last run's count, held to what the words around it call it: a pass stays one only when
    they name what the count is made of. A figure called lines passes as the lines the count's results stand on."""
    after = kinds_after(line[end:end + 80])
    if found.verdict != PASS:
        on = next((key for key in measure.keys if after == LINES and latest.get(f"{LINES_OF}{key}") == value), None)
        return Found(found.line, PASS, found.item, f"the last `check` run's {SAID[on]} stand on {_n(value)} lines of the "
                     "notes") if on else found
    key = next((key for key in measure.keys if latest.get(key, 0) == value), measure.keys[0])
    words = after or (kinds_in_label(line[:start]) if key == "judged" else None)
    why = misnamed(value, key, words, latest)
    return Found(found.line, FAIL, found.item, why) if why else found


def _unbracketed(text: str) -> str:
    """The text with what brackets hold blanked out in place: "83 workings and totals (69 workings, 14 totals)" breaks
    down one part of a breakdown, and adds no part of its own."""
    while (blanked := re.sub(r"\([^()]*\)", lambda match: " " * len(match.group()), text)) != text:
        text = blanked
    return text


def _breakdown(line_no: int, breakdown: re.Match[str], kept: list[Run], measured: set[int]) -> Iterator[Found]:
    """A line labelled "Not judged:" or "Warnings:" against the last run: its counts must add up to the run's total, and
    each count that is the run's count of one status must be called what that count is made of. Counts in brackets
    break a part down further, so they're no parts; counts a measure read (`measured`, by where they start in the
    line) were held to their measure already."""
    label, latest = breakdown.group("label").lower(), kept[0].values()
    total = latest["not judged" if label == "not judged" else "warnings"]
    rest, offset = _unbracketed(breakdown.group("rest")), breakdown.start("rest")
    found = list(counts_in(rest))
    parts = [value for value, _, _ in found]
    if parts and total not in parts and sum(parts) != total:
        short = sum(parts) < total
        yield Found(line_no, WARN if short else FAIL, breakdown.group("label"),
                    f"its counts add up to {_n(sum(parts))}, but the last `check` run ({kept[0].ran_at}) has "
                    f"{_n(total)} {label}" + (f": {_n(total - sum(parts))} are left out" if short else ""))
    prefix = "not judged: " if label == "not judged" else f"{research.WARN}: "
    statuses = {key: n for key, n in latest.items() if key.startswith(prefix) and ": " not in key[len(prefix):]}
    for value, start, end in found:
        matching = [key for key, n in statuses.items() if n == value]
        if offset + start not in measured and len(matching) == 1 \
                and (why := misnamed(value, matching[0], kinds_after(rest[end:end + 80]), latest)):
            yield Found(line_no, FAIL, _item(rest, start), why)


def _judged(line_no: int, item: str, value: int, measure: Measure, have: dict[str, int], kept: list[Run]) -> Found:
    """One figure held to its measure, in `have`: the latest run's counts, or the database's values now."""
    # A status no result of the run had is a count of none.
    given = {key: have.get(key, 0) if measure.from_run else have.get(key) for key in measure.keys}
    whose = f"the last `check` run ({kept[0].ran_at}) gives" if measure.from_run else "the database gives"
    main = measure.keys[0]
    if value == given[main]:
        return Found(line_no, PASS, item, f"{whose} {_n(value)} {SAID[main]}")
    for key in measure.keys[1:]:
        if value == given[key]:
            return Found(line_no, measure.other, item, f"{_n(value)} is the count of {SAID[key]}" + (
                f"; {SAID[main]}: {_n(given[main] or 0)}" if measure.other != PASS else ""))
    for run in kept[1:]:
        earlier = run.values()
        if any(value == earlier.get(key, 0) for key in measure.keys):
            return Found(line_no, WARN, item, f"{_n(value)} is what the `check` run of {run.ran_at} gave; the last run "
                         f"({kept[0].ran_at}) gives {_n(given[main] or 0)} {SAID[main]}")
    instead = "; ".join(f"{_n(n)} {SAID[key]}" for key, n in given.items() if n is not None)
    other = next((key for key, n in have.items() if n == value and key not in measure.keys and key in SAID), None)
    return Found(line_no, FAIL, item, f"{whose} {instead}" + (f"; {_n(value)} is the count of {SAID[other]}" if other else ""))
