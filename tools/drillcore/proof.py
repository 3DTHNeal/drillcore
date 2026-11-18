"""Proofing the drafts: what holds a report together besides its figures, read from the drafts themselves and the
workspace. `assay` holds each figure of a draft to the notes; this holds the draft to itself and to its sources.

- `citations`: each in-text author-date citation, "(Stratus Ltd. 2026a)", "(A 2026a, 2026b; B n.d.-m)" or "(Roe et
  al. 2024, 45)", must name an entry of the reference list: the same author and year, or for a person's name, the same
  surnames. A name may have brackets or another script in it, as "Hunan Ltd. (湖南公司) 2026" does. Text in the
  brackets that isn't a citation, such as "author's estimate" or "sold in 2018", is passed over. A narrative citation,
  "Roe et al. (2024) argue" or "Poe's (2019) frame", is held to the list too when the list has its author: a year the
  list doesn't give that author is a warning, as is "Doe et al. (2024)" when the list has no Doe. Other names before
  a year in brackets, "Revenue (2024)", are passed over.
- `references`: the list itself. Two entries for one author and year fail, as an entry written twice does. An entry no
  draft cites, and one whose web address is no source the notes cite, are warnings, unless `[assay.accept_addresses]`
  accepts that address, which passes with the reason it gives. An entry is cited by a narrative citation or a label
  too, "Poe (2019) argues" or "Framework: Poe 2019", as well as by brackets.
- `year letters`: an author's works in one year are lettered a, b, c in the order the list gives them, and a work alone
  in its year takes no letter, so "2024k" for an author's only work of 2024 fails, and says it should be 2024 and how
  often the drafts cite it. The findings together are the mapping that fixes the list.
- `cited figures`: each figure of three digits or more in a sentence that cites a source the notes hold must be in the
  text of that source, at any scale or precision a filing might give it (the assay's measured policy). A warning, since
  a sentence may give a figure worked out from the source rather than stated by it. A figure the sentence labels as the
  author's working ("author's calculation from Roe 2024", "summed by the author") is traced to the notes instead: it
  passes, naming the line, when a worked-out line of the notes gives it and shares a describing word with the sentence.
- `dates`: a date in a sentence ("since April 2025") later than every work the sentence cites, by the dates its
  reference list gives (filed, published; not accessed), is a warning unless a cited source's stored text gives that
  date, as a filing does a lock-up's end in advance: the fact came from a later source the sentence doesn't cite. A
  sentence about what is expected or planned is passed over. And a sentence that states the cut-off as an absolute,
  "nothing published after 30 June 2025", is a warning when the drafts cite works the list dates after that day,
  unless it names its exceptions.
- `filings`: a line that names a company's periodic report for fiscal years, "Northbridge Robotics Ltd., annual reports on Form
  20-F for fiscal 2010 to 2025", fails when the filing list `sec` loaded for that company has no such report for some
  of those years. A company whose list isn't loaded, or a name given another kind ("Northbridge Robotics, Inc."), isn't judged.
- `cross-references`: "section 5.3", "Exhibit E12", "Table 4", "Appendix B" and "entry 50" must name a heading, a
  caption or an entry ("**Entry 50.**") that the drafts or their companion files give. Where they give lettered
  appendices, "the Appendix" is a warning, since it could mean any of them; with "entry 50" beside it, the finding
  names the appendix that holds entry 50. "That date" and "that day" are warnings too where their sentence and the
  one before give two different dates: "Data runs to 11 November. Filings of 12 November are kept for facts as of
  that date" reads as 12 November, the nearer.
- `numbering`: the entries of a record, a section `[drafts] records` names or a companion file, are numbered once each
  and in order ("**Entry 12.**" or a list's "12."), through the whole record. A number used twice or out of order
  fails; one that skips numbers is a warning.
- `records`: a record held to the log it's compiled from, for each `[[proof.record_logs]]`: each entry of the log in
  the record and the other way round, each entry's date and address the log's, each quotation in the log's entry word
  for word ("…" or a bracketed note standing for words left out), each prompt the log quotes as the author's quoted
  in the record unless a `cuts` file says why not, and each "entry 12" one the record has. With `sessions`, a folder
  of the sessions' own transcripts, each prompt typed in them must be in the log or a cuts file (a session with none
  there is one with no entry), and each prompt the record quotes must be the whole of a typed message or mark its
  cuts. See `record_log` and `sessions`.
- `exhibits`: each exhibit, figure, table or chart captioned once, and mentioned in the text outside its caption.
- `summary`: each figure of the executive summary (a heading such as "Executive summary", "Summary" or "Abstract")
  must be given in another part of the drafts too, on a line that shares two describing words with the summary's
  sentence, at any scale or precision, as the measured policy reads a source: a 6.8% hurdle elsewhere doesn't give a
  summary's 6.8% growth.
- `pointers`: each figure of a sentence that points to sections or appendices, "(sections 2.1 and 4)" or "see
  Appendix A", must be given in one of them, on such a line; the finding names the part that does give it, if any. A
  section holds its subsections. A sentence that cites nothing and points there for a figure the line there gives with
  no source either (no citation, no label of the author's working, no source line under its table) is a warning too: a
  chain of pointers that ends nowhere supports nothing. Both this and `summary` are warnings: a summary may add up
  what the body gives, and a pointer may name where the method is rather than the figure.
- `sums`: in a draft's tables, a column headed "Total" must be the sum of the bare figures before it in its row, and a
  row labelled "Total" the sum of the column above it, within the rounding they're written to. In prose, a sentence
  that says figures "total" an amount must add up: from the amounts before the word, or else from the table just above,
  a column of single amounts ("Up to $18M"). "About" allows 5%. A table that fails is a failure; prose, a warning.
- `tables`: a framework's table must keep the rules `[[proof.table_rules]]` sets: what a column may hold (Ansoff's four
  quadrants), and an outcome derived from the other columns (a VRIO grid, in Barney's order). See `framework`.
- `personal data`: a local path that names an account (C:\\Users\\name\\..., /home/name/...), an email address, an
  account handle (@name), and any personal term the settings list. Those the settings allow pass.
- `workspace figures`: in the sections `[proof] workspace_sections` names, in the drafts or the companion files, each
  figure about the workspace's own record ("30 documents with stored text", "412 judged", "18 match") must be
  the database's value now or the last `check` or `claims` run's; a breakdown labelled "Not judged:" must add up to the
  run's total; and a count must be called what it counts ("412 figures judged" fails when quotations are among the
  412, "12 lines" when the 12 results stand on fewer lines). See `record`.

The reference list is the drafts' own, under a heading such as "References" or "Works cited", or else the files the
settings name. Companion files are other parts of the report that aren't drafts to judge, such as an appendix kept
elsewhere: they're read for the targets of cross-references and for reference lists, and nothing else.

A draft's own reference list, and each section `[drafts] records` names (a log of prompts quoted word for word, say),
is read for its entries and its headings, the numbering of a record's entries and personal data, but not for
citations, cross-references, exhibits, the summary's figures, pointers, sums or tables: an entry's "Exhibit 99" is the
title of a filing, not a cross-reference.

    [proof]
    references = ["report/references.md"]   # reference lists, from the workspace's root
    companions = ["report/appendix_b.md"]   # other parts of the report, read for cross-reference targets
    personal = ["Jane Roe"]                  # terms that must not appear in a draft
    allow = ["press@example.com"]            # emails, handles and paths that may
    workspace_sections = ["Appendix C"]      # headings over figures about the workspace's own record

    [[proof.table_rules]]                    # a framework's table: see `framework`
    column = "Ansoff"
    values = ["Market penetration", "Market development", "Product development", "Diversification"]

    [[proof.record_logs]]                    # a record held to its log: see `record_log`
    record = "Appendix B"                    # a heading [drafts] records names, or a companions file
    log = "ai_use_log.md"                    # the log it's compiled from
    cuts = ["report/left_out.md"]            # what was left out on purpose, under headings naming the entry
    sessions = "~/.claude/projects/my-folder" # the sessions' transcripts, to hold both to what was typed (optional)

Results go in data/proof.csv, passes with a reason among them; `--all` prints those too. This reads the drafts; it
never changes one.
"""
import argparse
import csv
import re
import sqlite3
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from assay import numbers as assay_numbers
from assay import text as assay_text

from . import arithmetic, framework, record, record_log, research, sessions
from .drafts import HEADING, read_draft, set_aside
from .judge import ADDRESS, BOUND_WORDS, NOTES_POLICY, Row, address, note_rows, rules, sec_companies, sec_data, sentence_at
from .overlap import draft_files, drafts_folder, records
from .sourcedb import table_headers
from .workspace import Workspace

CHECKS = ("citations", "references", "year letters", "cited figures", "dates", "filings", "cross-references", "numbering",
          "records", "exhibits", "summary", "pointers", "sums", "tables", "spelling", "personal data", "workspace figures")
PASS, WARN, FAIL = "pass", "warn", "fail"
REPORT = "proof.csv"


@dataclass(frozen=True)
class Result:
    """One thing the proof found, in a draft or in a reference list or companion file."""
    file: str       # the file's name
    line: int
    check: str      # one of CHECKS
    verdict: str    # WARN or FAIL; PASS for a check that found nothing
    item: str
    detail: str


@dataclass(frozen=True)
class Settings:
    """The `[proof]` settings, read and checked."""
    references: tuple[Path, ...] = ()
    companions: tuple[Path, ...] = ()
    personal: tuple[str, ...] = ()
    allow: tuple[str, ...] = ()
    # The rules for a framework's tables (`[[proof.table_rules]]`).
    tables: tuple[framework.Rule, ...] = ()
    # The headings over figures about the workspace's own record (`record`).
    workspace_sections: tuple[str, ...] = ()
    # Records held to the logs they're compiled from (`[[proof.record_logs]]`).
    record_logs: tuple["RecordLog", ...] = ()


@dataclass(frozen=True)
class RecordLog:
    """A record, a section `[drafts] records` names or a companion file, and the log it's compiled from; and the
    folder of the sessions' own transcripts, when there is one to hold both to (`sessions`)."""
    record: str
    log: Path
    cuts: tuple[Path, ...] = ()
    sessions: Path | None = None


def record_logs(found: object, where: str, root: Path) -> tuple[RecordLog, ...]:
    """`[[proof.record_logs]]`, read and checked. Raises ValueError, saying what to fix, for one that can't be used."""
    if found is None:
        return ()
    if not isinstance(found, list) or not all(isinstance(entry, dict) for entry in found):
        raise ValueError(f"[[proof.record_logs]] in {where} must be tables, each with a record and a log.")
    given = []
    for entry in found:
        # `record` is a module here, so the setting of that name is read as `heading`.
        heading, log, cuts = entry.get("record"), entry.get("log"), entry.get("cuts", [])
        sessions = entry.get("sessions")
        unknown = sorted(set(entry) - {"record", "log", "cuts", "sessions"})
        if unknown:
            raise ValueError(f"[[proof.record_logs]] in {where} has a setting it doesn't know: {', '.join(unknown)}")
        if not isinstance(heading, str) or not heading.strip() or not isinstance(log, str) or not log.strip():
            raise ValueError(f"[[proof.record_logs]] in {where} needs a record (a heading or a file) and a log (a file).")
        if not isinstance(cuts, list) or not all(isinstance(path, str) and path.strip() for path in cuts):
            raise ValueError(f"[[proof.record_logs]] cuts in {where} must be a list of files, none of them blank.")
        paths = [root / log, *(root / path for path in cuts)]
        missing = [str(path) for path in paths if not path.is_file()]
        if missing:
            raise ValueError(f"[[proof.record_logs]] in {where} names files that don't exist: {', '.join(missing)}")
        folder = None
        if sessions is not None:
            if not isinstance(sessions, str) or not sessions.strip():
                raise ValueError(f"[[proof.record_logs]] sessions in {where} must name a folder of session transcripts.")
            folder = root / Path(sessions.strip()).expanduser()
            if not folder.is_dir():
                raise ValueError(f"[[proof.record_logs]] sessions in {where} names a folder that doesn't exist: {folder}")
        given.append(RecordLog(heading.strip(), paths[0], tuple(paths[1:]), folder))
    return tuple(given)


def settings(ws: Workspace) -> Settings:
    """The workspace's `[proof]` settings. Raises ValueError, saying what to fix, for one that can't be used."""
    found = ws.config().get("proof", {})
    if not isinstance(found, dict):
        raise ValueError(f"[proof] in {ws.config_path} must be a table of settings.")

    def strings(key: str) -> tuple[str, ...]:
        given = found.get(key, [])
        if not isinstance(given, list) or not all(isinstance(entry, str) and entry.strip() for entry in given):
            raise ValueError(f"[proof] {key} in {ws.config_path} must be a list, none of it blank.")
        return tuple(given)

    def files(key: str) -> tuple[Path, ...]:
        paths = tuple(ws.root / entry for entry in strings(key))
        missing = [str(path) for path in paths if not path.is_file()]
        if missing:
            raise ValueError(f"[proof] {key} in {ws.config_path} names files that don't exist: {', '.join(missing)}")
        return paths

    return Settings(files("references"), files("companions"), strings("personal"), strings("allow"),
                    framework.rules(found.get("table_rules"), str(ws.config_path)), strings("workspace_sections"),
                    record_logs(found.get("record_logs"), str(ws.config_path), ws.root))


def _line(text: str, at: int) -> int:
    return text.count("\n", 0, at) + 1


# ---------------------------------------------------------------- citations and the reference list

# A year as an author-date citation gives one: 2026, 2026a, n.d., or n.d.-m where one author has several undated works.
YEAR = r"(?:(?:1[5-9]|20)\d{2}[a-z]?|n\.d\.(?:-[a-z]{1,3})?)"
# Brackets holding a year: what an in-text citation is written in. One level of brackets inside is allowed, for a
# name such as "Hunan Ltd. (湖南公司)".
BRACKETED = re.compile(rf"\((?P<inside>(?:[^()]|\([^()]*\))*?\b{YEAR}(?:[^()]|\([^()]*\))*)\)")
# One work within a citation: its author, its years, and a page or other place after them.
WORK = re.compile(rf"^(?P<author>.+?),?\s+(?P<years>{YEAR}(?:\s*,\s*{YEAR})*)(?:\s*,\s*(?P<place>[^;]{{0,40}}))?\.?$")
# Brackets with no brackets inside, holding a year: a citation inside other brackets, as in "(data (Roe 2024))".
INNERMOST = re.compile(rf"\((?P<inside>[^()]*\b{YEAR}[^()]*)\)")
# What may open a work without being its author: "see Roe 2024", "cf. Roe 2024".
LEAD = re.compile(r"^(?:see(?: also)?|cf\.|e\.g\.,?|i\.e\.,?|as in|after|per|following|quoted in|cited in)\s+", re.I)
# Words that open brackets holding a year but no citation: "(Q3 2026)", "(fiscal 2025)", "(up from 2024)".
NOT_AUTHORS = frozenset({
    "q1", "q2", "q3", "q4", "h1", "h2", "fy", "cy", "fiscal", "calendar", "year", "years", "since", "from", "in", "to", "by",
    "at", "up", "down", "about", "around", "before", "after", "until", "through", "end", "mid", "early", "late", "est",
    "estimated", "approx", "approximately", "nine", "six", "three", "twelve", "first", "second", "third", "fourth", "half",
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
    "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "as", "of", "and",
})
# Words that end a clause before a year, and never an author's name: "(Osprey, sold in 2018)", "(listed since
# 2012)". An author ends in a name, "et al." or a company's word.
LINKING = frozenset({
    "in", "since", "from", "by", "to", "of", "until", "till", "after", "before", "during", "through", "around", "about",
    "than", "at", "on", "for", "and", "or", "between", "as", "into", "over", "under", "within", "circa", "ca", "c",
})
# An entry of a reference list in author-date form: its author, then its year, each followed by a full stop.
ENTRY = re.compile(r"^(?P<author>.+?)\.?\s+(?P<year>(?:1[5-9]|20)\d{2}[a-z]?|n\.d(?:\.-[a-z]{1,3})?)\.(?:\s|$)")
# What would be an entry's author ends so when its year closes a full date, as a log's "Helper AI. helper.example. November
# 10, 2026." does. That's a record of a session, such as an AI-use log under an "Entries" heading, and no author-date
# entry: it's neither held to citations nor lettered.
DATED = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?$")
REFERENCE_HEADING = re.compile(r"^#+\s*(?:[A-Z]?\d*[.)]?\s*)?(?:References|Bibliography|Works cited|Reference list|Entries)\b", re.I)
ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def _norm(text: str) -> str:
    """A name or year as it's compared: one case, one kind of apostrophe, single spaces, no full stop at the end."""
    return " ".join(text.replace("’", "'").replace("（", "(").replace("）", ")").split()).rstrip(".").casefold()


def _surnames(author: str) -> list[str]:
    """The surnames an in-text author gives: "Roe et al." gives Roe, "Roe and Poe" gives both."""
    plain = re.sub(r"\bet al\.?", "", author)
    return [_norm(part.split()[-1]) for part in re.split(r",\s*|\s+and\s+|\s*&\s*", plain) if part.strip()]


@dataclass(frozen=True)
class Entry:
    """An entry of a reference list."""
    file: str
    line: int
    author: str
    year: str
    text: str

    @property
    def key(self) -> tuple[str, str]:
        return _norm(self.author), _norm(self.year)

    def names(self, surnames: list[str]) -> bool:
        """Whether a person's surnames, the first leading, are this entry's authors': "Roe et al." of "Roe, Jane,
        and Al Poe"."""
        first = _norm(self.author.split(",")[0])
        words = set(re.findall(r"[^\W\d_][\w'-]*", _norm(self.author)))
        return bool(surnames) and surnames[0] == first and all(name in words for name in surnames[1:])


@dataclass(frozen=True)
class Cited:
    """One work an in-text citation names."""
    file: str
    line: int
    at: int             # where its brackets start in the draft
    author: str
    year: str
    written: str        # the work as written in the brackets


# A source line, as a caption or a table gives one: "Source: Roe 2024; Poe n.d." Its works are cited as the brackets'
# are, without the brackets.
SOURCE_LIST = re.compile(r"\bSources?:\s*(?P<list>[^\n]*)")
# A figure standing alone in what would be an author, "33.5%" or "12 November": no author's name holds one, so the
# brackets aren't a citation.
BARE_FIGURE = re.compile(r"(?<![\w.])[−-]?[$€£]?\d[\d.,]*%?(?![\w])")
# An author's name starts with a capital, or in a script that has none.
CAPITAL = re.compile(r"[^\W\d_a-z]")


def _author(written: str) -> str:
    """The author of a work as a citation writes it, or "" for words that aren't one. Words before the name are
    dropped, as in "see Roe 2024" or "author's calculation from Roe 2024"."""
    author = LEAD.sub("", written).strip()
    if author and not CAPITAL.match(author):
        named = re.search(r"(?<=\s)[^\W\d_a-z]", author)
        author = author[named.start():] if named else ""
    first = author.split()[0].casefold().strip(",.") if author.split() else ""
    last = author.split()[-1].strip(",.;:") if author.split() else ""
    unbalanced = author.count("(") != author.count(")")  # A citation in brackets inside the words, read on its own.
    if (not author or unbalanced or first in NOT_AUTHORS or last in LINKING or BARE_FIGURE.search(author)
            or re.search(r"\band others\b", author)):
        return ""
    return author


def mentioned(entry: Entry, drafts: list[tuple[str, str]]) -> Iterator[Cited]:
    """Each place a draft names an entry as an in-text citation would, outside brackets: "Poe 2019", "Poe (2019)
    argues", "Roe and Poe (2024)" or "Framework: Poe 2019". A narrative citation or a label cites the work as surely as
    brackets."""
    name = (entry.author.split(",")[0] if "," in entry.author else entry.author).strip().rstrip(".")
    if not name:
        return
    year = re.escape(entry.year.rstrip("."))
    pattern = re.compile(rf"(?<![\w-]){re.escape(name)}\.?(?:\s+(?:and|&)\s+[^\W\d_][\w'’-]*|\s+et\s+al\.?)?(?:['’]s)?,?\s+"
                         rf"\(?{year}\.?\)?(?![\w-])")
    for file, text in drafts:
        for found in pattern.finditer(text):
            yield Cited(file, _line(text, found.start()), found.start(), entry.author, entry.year, found.group(0))


def citations_in(name: str, text: str) -> Iterator[Cited]:
    """Each work each in-text citation of a draft names: in brackets, or in a source line."""
    seen: set[tuple[int, str, str]] = set()  # A bracket both patterns find is read once.
    lists = [(bracket.start(), bracket.group("inside")) for bracket in BRACKETED.finditer(text)]
    lists += [(bracket.start(), bracket.group("inside")) for bracket in INNERMOST.finditer(text)]
    lists += [(found.start(), found.group("list").strip().rstrip("*_ ")) for found in SOURCE_LIST.finditer(text)]
    for at, listed in sorted(lists):
        for part in listed.split(";"):
            if part.count("(") != part.count(")"):
                continue  # Part of a citation in brackets inside it, read on its own.
            work = WORK.match(" ".join(part.split()))
            author = _author(work.group("author")) if work else ""
            if not work or not author:
                continue
            for year in re.split(r"\s*,\s*", work.group("years")):
                if (at, author, year) not in seen:
                    seen.add((at, author, year))
                    yield Cited(name, _line(text, at), at, author, year, part.strip())


# A narrative citation names its author in the sentence and gives the year after it in brackets: "Roe et al. (2024)
# argue", "Roe and Poe (2024, 45)", "Poe's (2019) frame". The brackets hold years alone, perhaps with a page after a
# comma. A colon isn't read, since "(2024: 1,820)" is a prior year's figure.
NARRATIVE_YEARS = re.compile(rf"\((?P<years>{YEAR}(?:\s*,\s*{YEAR})*)(?:\s*,\s*(?:pp?\.\s*)?\d[\d–-]*)?\)")
# A word of a name as prose writes it: capitalized, perhaps abbreviated, as Roe, O'Neil, Smith-Jones or Ltd.
_NAME = r"[^\W\d_a-z][\w'’-]*\.?"
# The names that end a stretch of text, just before a year in brackets: "Roe", "Roe et al.", "Roe and Poe", "Roe, Poe
# and Doe", "Northbridge Robotics", "Poe's".
NAMES_BEFORE = re.compile(rf"(?<![\w'’.-])(?:{_NAME}(?:,?\s+(?:and|&)\s+|,\s+|\s+))*?{_NAME}(?:\s+et\s+al\.?)?(?:['’]s)?\s*$")
NAME_START = re.compile(rf"(?<![\w'’.-]){_NAME}")
POSSESSIVE = re.compile(r"['’]s\s*$")


def narrative_in(name: str, text: str, entries: list[Entry]) -> Iterator[Cited]:
    """Each work a narrative citation names: an author the reference list has, then a year in brackets, whether or not
    the list has that year. The author is read as the fewest of the names before the brackets that name the same
    entries as all of them, so "As Roe et al. (2024)" is Roe et al. Names no entry has are passed over, since
    "Revenue (2024)" is no citation, unless they're "et al.", which is never anything else."""
    for bracket in NARRATIVE_YEARS.finditer(text):
        before = text[max(0, bracket.start() - 150):bracket.start()]
        run = NAMES_BEFORE.search(before)
        if not run:
            continue
        written = POSSESSIVE.sub("", run.group(0)).strip()
        offset = bracket.start() - len(before) + run.start()
        named: list[tuple[int, frozenset[Entry]]] = []
        for start in NAME_START.finditer(written):
            author = written[start.start():]
            named.append((start.start(), frozenset(entry for entry in entries if _norm(entry.author) == _norm(author)
                                                   or entry.names(_surnames(author)))))
        first = next((i for i, (_, found) in enumerate(named) if found), None)
        if first is not None:
            while first + 1 < len(named) and named[first + 1][1] == named[first][1]:
                first += 1
            begin = named[first][0]
        elif re.search(r"\set\s+al\.?$", written) and named:
            begin = named[-1][0]
        else:
            continue
        author = written[begin:]
        for year in re.split(r"\s*,\s*", bracket.group("years")):
            yield Cited(name, _line(text, offset + begin), offset + begin, author, year, f"{author} ({bracket.group('years')})")


def entries_in(name: str, text: str, whole: bool) -> list[Entry]:
    """The entries of a reference list: in a draft, those under a References heading; in a file the settings name as
    one, every line that reads as an entry, up to a heading that isn't the file's title or a References heading."""
    found: list[Entry] = []
    inside = whole
    for line_no, line in enumerate(text.split("\n"), 1):
        if line.lstrip().startswith("#"):
            title = whole and line.lstrip().startswith("# ") and not found
            inside = title or bool(REFERENCE_HEADING.match(line.strip()))
            continue
        if not inside:
            continue
        written = ITEM.sub("", line).strip()
        entry = ENTRY.match(written)
        if entry and not DATED.search(entry.group("author")):
            found.append(Entry(name, line_no, entry.group("author"), entry.group("year"), written))
    return found


def resolve(work: Cited, entries: list[Entry]) -> list[Entry]:
    """The entries a cited work names: by author and year, or failing that by surnames and year."""
    year = _norm(work.year)
    exact = [entry for entry in entries if entry.key == (_norm(work.author), year)]
    if exact:
        return exact
    surnames = _surnames(work.author)
    return [entry for entry in entries if _norm(entry.year) == year and entry.names(surnames)]


# How many years before an author's first listed work a year in brackets after their name is read as a date, not a
# work: a company's founding, as an origins row gives it.
LONG_BEFORE = 10


def _long_before(year: str, others: list[str]) -> bool:
    """Whether a year is more than `LONG_BEFORE` years before every year the list gives the author."""
    listed = [int(other[:4]) for other in others if other[:4].isdigit()]
    return year[:4].isdigit() and bool(listed) and int(year[:4]) < min(listed) - LONG_BEFORE


def check_citations(drafts: list[tuple[str, str]], entries: list[Entry], listed: bool) -> tuple[list[Result], dict[Entry, list[Cited]]]:
    """Each cited work with no entry, and for each entry the works that cite it. A narrative citation is held to the
    list as one in brackets is, but what it gets wrong is a warning, since a name before a year in brackets may be a
    company in that year rather than a work."""
    found: list[Result] = []
    cited: dict[Entry, list[Cited]] = {entry: [] for entry in entries}
    for name, text in drafts:
        works = [(work, FAIL) for work in citations_in(name, text)] + [(work, WARN) for work in narrative_in(name, text, entries)]
        for work, verdict in works:
            named = resolve(work, entries)
            for entry in named:
                cited[entry].append(work)
            if named or not listed:
                continue
            others = sorted({entry.year for entry in entries if _norm(entry.author) == _norm(work.author)
                             or entry.names(_surnames(work.author))})
            if verdict == WARN and _long_before(work.year, others):
                continue  # "Acme, Inc. (1979)": a company and the year it was founded, not a work of the list's author.
            if others:
                found.append(Result(name, work.line, "citations", verdict, f"{work.author} {work.year}",
                                    f"the list has {work.author} for {', '.join(others)}, not {work.year}"))
            else:
                # Brackets can hold a name and a year without being a citation, as "(LTE 2008)" does, so a name the
                # list doesn't have at all is a warning.
                found.append(Result(name, work.line, "citations", WARN, f"{work.author} {work.year}",
                                    "reads as a citation, but no entry of the reference list has this author"))
    return found, cited


def check_references(entries: list[Entry], cited: dict[Entry, list[Cited]], sources: set[str],
                     companies: frozenset[int] = frozenset(), accepted: dict[str, str] | None = None) -> Iterator[Result]:
    """Entries written twice or given one author and year twice, entries cited nowhere, and entries whose address is
    no source the notes cite. The SEC's structured data for a company the settings load counts as one: `claims`
    holds the notes to it. An address `[assay.accept_addresses]` accepts (`accepted`, as `address` writes each) passes,
    with the reason the settings give."""
    sources = sources | {found for entry in entries for match in ADDRESS.finditer(entry.text)
                         if sec_data(found := address(match.group(0)), companies)}
    by_key: dict[tuple[str, str], list[Entry]] = {}
    for entry in entries:
        by_key.setdefault(entry.key, []).append(entry)
    for same in by_key.values():
        for entry in same[1:]:
            what = "the same entry twice" if entry.text == same[0].text else "two entries for one author and year"
            yield Result(entry.file, entry.line, "references", FAIL, f"{entry.author} {entry.year}",
                         f"{what}: also at {same[0].file}:{same[0].line}")
    for entry in entries:
        if not cited[entry]:
            yield Result(entry.file, entry.line, "references", WARN, f"{entry.author} {entry.year}", "in the reference list, but no draft cites it")
        addresses = [address(match.group(0)) for match in ADDRESS.finditer(entry.text)]
        if sources and addresses and not any(found in sources for found in addresses):
            why = next(((found, (accepted or {})[found]) for found in addresses if found in (accepted or {})), None)
            if why is not None:
                yield Result(entry.file, entry.line, "references", PASS, f"{entry.author} {entry.year}",
                             f"its web address is no source the notes cite, and [assay.accept_addresses] accepts {why[0]}: {why[1]}")
            else:
                yield Result(entry.file, entry.line, "references", WARN, f"{entry.author} {entry.year}",
                             "its web address is no source the notes cite, so nothing checks what it's cited for")


# ---------------------------------------------------------------- the letters after a year

# A year as an entry gives it, split into the year and the letter after it: "2026m", "2023", "n.d" or "n.d.-p".
LETTERED = re.compile(r"^(?P<base>(?:1[5-9]|20)\d{2}|n\.d)(?:\.?-?(?P<letter>[a-z]{1,3}))?$")

def _letter(index: int) -> str:
    """The letter of an author's work in a year, counted from 0: a to z, then aa, ab and on."""
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(ord("a") + rest) + letters
    return letters


def _year(base: str, letter: str) -> str:
    """A year with its letter, as a reader sees it: 2026k, 2023, n.d. or n.d.-b."""
    if base == "n.d":
        return f"n.d.-{letter}" if letter else "n.d."
    return base + letter


def check_year_letters(entries: list[Entry], cited: dict[Entry, list[Cited]]) -> Iterator[Result]:
    """Each entry whose year carries the wrong letter. An author's works in one year are lettered a, b, c in the order
    the list gives them, and a work alone in its year has no letter; so "2024k" for an author's one work of 2024, or
    "2026m" for the eleventh of eleven, fails. Each finding gives the year it should have, so the findings together are
    the mapping that fixes the list, and says how often the drafts cite it, since each citation changes with it."""
    groups: dict[tuple[str, str, str], list[tuple[Entry, str]]] = {}
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        parts = LETTERED.match(_norm(entry.year))
        if not parts or (entry.file, entry.text) in seen:
            continue  # An entry written twice is the references check's to find.
        seen.add((entry.file, entry.text))
        groups.setdefault((entry.file, _norm(entry.author), parts.group("base")), []).append((entry, parts.group("letter") or ""))
    for (_, _, base), group in groups.items():
        for index, (entry, letter) in enumerate(group):
            wanted = _letter(index) if len(group) > 1 else ""
            if letter == wanted:
                continue
            if len(group) > 1:
                why = (f"the list has {len(group)} works of {entry.author} dated {_year(base, '')}, lettered a to "
                       f"{_letter(len(group) - 1)} in the order listed, and this is number {index + 1}")
            else:
                why = f"it's the list's only work of {entry.author} dated {_year(base, '')}, so it takes no letter"
            uses = len(cited.get(entry, []))
            also = f"; the drafts cite it {uses} time{'' if uses == 1 else 's'}, each to change with it" if uses else ""
            yield Result(entry.file, entry.line, "year letters", FAIL, f"{entry.author} {_year(base, letter)}",
                         f"should be {entry.author} {_year(base, wanted)}: {why}{also}")


# What labels figures as the author's own working from a source, rather than figures the source states: "author's
# calculation from Roe 2024", "author's sums", "summed by the author", "computed by the author". An estimate is a
# judgment, not a working anyone can trace, so "author's estimate" isn't one.
WORKED_BY_AUTHOR = re.compile(r"\bauthor['’]s\s+(?:own\s+)?(?:calculations?|computations?|sums?|arithmetic|workings?)\b"
                              r"|\b(?:calculated|computed|summed|added\s+up|worked\s+out|derived)\s+by\s+the\s+author\b", re.I)
# How many describing words a worked-out line of the notes must share with the sentence to be its working: one, as
# `assay` binds a draft's figure to a line of the notes.
WORKED_WORDS = 1


def labelled(sentence: str) -> list[tuple[int, int]]:
    """The stretches of a sentence whose figures it labels as the author's working (`WORKED_BY_AUTHOR`). A label in
    brackets covers the figures before them, back to the citation before it in the sentence: in "rose 4.6% (author's
    calculation from Roe 2024), against 6% (Poe 2025)", it covers 4.6% and not 6%. A label outside brackets covers
    the sentence."""
    citations = [match.end() for match in BRACKETED.finditer(sentence)]
    spans = []
    for label in WORKED_BY_AUTHOR.finditer(sentence):
        opened = sentence.rfind("(", 0, label.start())
        if opened < 0 or ")" in sentence[opened:label.start()]:
            spans.append((0, len(sentence)))
        else:
            spans.append((max((end for end in citations if end <= opened), default=0), opened))
    return spans


def closed(text: str, start: int, sentence: str) -> str:
    """A sentence of a text, from `start`, with the rest of a bracket it leaves open: "... a year (Roe Ltd." is cut at
    the abbreviation's full stop, inside the citation, and the label after it is the sentence's too. A bracket that
    doesn't close before a blank line is left as it is."""
    depth, at = 0, start + len(sentence)
    for char in sentence:
        depth = max(0, depth + (char == "(") - (char == ")"))
    if not depth:
        return sentence
    while depth and at < len(text) and not text.startswith("\n\n", at):
        depth += (text[at] == "(") - (text[at] == ")")
        at += 1
    return sentence if depth else sentence + text[start + len(sentence):at]


def cited_clauses(sentence: str) -> list[tuple[int, int]]:
    """The stretches of a sentence its in-text citations cover: each citation's clause, from the semicolon before its
    brackets to the one after them, or the sentence's ends. "Costs $1M each (Doe 2024); restores the 20% cut" covers
    $1M and not 20%. Semicolons inside the brackets separate works, not clauses."""
    spans = []
    for match in BRACKETED.finditer(sentence):
        after = sentence.find(";", match.end())
        spans.append((sentence.rfind(";", 0, match.start()) + 1, len(sentence) if after < 0 else after))
    return spans


def check_cited_figures(drafts: dict[str, str], cited: dict[Entry, list[Cited]], ws: Workspace, con: sqlite3.Connection,
                        sources: set[str]) -> Iterator[Result]:
    """Each figure of a sentence that cites a source the notes hold, where that source's text doesn't hold it. One the
    sentence labels as the author's working (`labelled`) is traced instead to the notes' working: it passes, naming
    the line, when a worked-out line of the notes ("COMPUTED"), which `check` recomputes and whose inputs it traces to
    their sources, gives it at any scale or precision and shares a describing word with the sentence. A labelled figure
    no worked-out line gives stays a warning, and says so."""
    held = research.Sources(ws, con)
    by_address = {address(url): url for (url,) in con.execute("SELECT DISTINCT url FROM sources")}
    read: dict[str, assay_numbers.Evidence | None] = {}
    worked: list[Row] | None = None

    def evidence(url: str) -> assay_numbers.Evidence | None:
        if url not in read:
            text = held.text(url)
            read[url] = assay_numbers.evidence(assay_text.matchable(text), policy=assay_numbers.MEASURED) if text else None
        return read[url]

    def working(claim: assay_numbers.Quantity, sentence: str) -> Row | None:
        """The worked-out line of the notes that gives a figure for what its sentence says, the most words shared first."""
        nonlocal worked
        if worked is None:
            worked = [row for row in note_rows(ws, con)[1] if row.worked_out]
        words = set(research.describing_words(_said(sentence)))
        about = [(shared, row) for row in worked if (shared := len(set(row.labels) & words)) >= WORKED_WORDS
                 and assay_numbers.holds(row.figures, claim, assay_numbers.MEASURED)]
        return max(about, key=lambda found: found[0])[1] if about else None

    # The sources each sentence cites, by draft and where the sentence starts.
    sentences: dict[tuple[str, int], tuple[str, set[str]]] = {}
    for entry, works in cited.items():
        urls = {by_address[found] for match in ADDRESS.finditer(entry.text) if (found := address(match.group(0))) in by_address}
        for work in works:
            text = drafts[work.file]
            sentence = sentence_at(text, work.at)
            start = text.rfind(sentence, 0, work.at + len(sentence))
            sentences.setdefault((work.file, start), (sentence, set()))[1].update(urls)
    for (name, start), (sentence, urls) in sorted(sentences.items()):
        known = [read_here for url in sorted(urls) if (read_here := evidence(url)) is not None]
        if not known:
            continue
        said = assay_text.matchable(sentence)
        plain = BRACKETED.sub(lambda match: " " * len(match.group(0)), said)
        spans = labelled(assay_text.matchable(closed(drafts[name], start, sentence)))
        covered = cited_clauses(said)
        for claim in assay_numbers.quantities(plain, assay_numbers.MEASURED):
            if claim.kind not in ("number", "percent") or claim.figures < (2 if claim.kind == "percent" else 3):
                continue
            if covered and not any(begin <= claim.start < end for begin, end in covered):
                continue  # In a clause of its own, after a semicolon: the citation is for the clause it stands in.
            if any(assay_numbers.holds(each, claim, assay_numbers.MEASURED) for each in known):
                continue
            line = _line(drafts[name], start) + said.count("\n", 0, claim.start)
            missing = f"not in the text of the source this sentence cites ({', '.join(sorted(urls))[:200]})"
            if not any(begin <= claim.start < end for begin, end in spans):
                yield Result(name, line, "cited figures", WARN, claim.text, missing)
            elif (row := working(claim, said)) is not None:
                yield Result(name, line, "cited figures", PASS, claim.text,
                             f"labelled as the author's working, not the source's figure: the notes work it out at {row.where}")
            else:
                yield Result(name, line, "cited figures", WARN, claim.text,
                             f"{missing}; it's labelled as the author's working, but no worked-out line of the notes gives it")


# ---------------------------------------------------------------- dates against the works cited

_MONTH_WORD = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?"
               r"|Nov(?:ember)?|Dec(?:ember)?)")
# A date to the day or the month, as prose and reference lists write them: 7 October 2025, October 7, 2025, April 2025.
DAY_FIRST = re.compile(rf"\b(?P<day>\d{{1,2}})\s+(?P<month>{_MONTH_WORD})\.?,?\s+(?P<year>(?:19|20)\d{{2}})\b")
MONTH_FIRST = re.compile(rf"\b(?P<month>{_MONTH_WORD})\.?\s+(?:(?P<day>\d{{1,2}})(?:st|nd|rd|th)?,?\s+)?(?P<year>(?:19|20)\d{{2}})\b")
# The day a reference list says a work was looked at: no date of the work's own.
ACCESSED = re.compile(r"\bAccessed\s+[^.]*\.", re.I)
# A sentence about what was expected or planned may name a later day: that's its point.
FORWARD = re.compile(r"\b(?:expect\w*|plan(?:s|ned|ning)?|will|schedul\w*|due|intend\w*|forecast\w*|target\w*|aim\w*|outlook)\b", re.I)
# A sentence that states the data's cut-off as an absolute: "nothing published after 30 June 2025".
CUTOFF_STATED = re.compile(r"\b(?:nothing|no\s+(?:data|sources?|documents?|filings?|figures?|facts?))\s+(?:(?:was|is|were)\s+)?"
                           r"(?:published|dated|issued|filed|released|used|included)?\s*after\b", re.I)
# Words by which such a sentence names its exceptions.
EXCEPTION = re.compile(r"\b(?:except|other than|apart from|save for|but|kept)\b", re.I)


def _month(word: str) -> int:
    return ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec").index(word[:3].casefold()) + 1


def dates_in(text: str) -> list[tuple[int, int, tuple[int, int, int | None]]]:
    """Each date to the day or the month in a text, as (start, end, (year, month, day or None)), in order."""
    found: list[tuple[int, int, tuple[int, int, int | None]]] = [
        (m.start(), m.end(), (int(m.group("year")), _month(m.group("month")), int(m.group("day")))) for m in DAY_FIRST.finditer(text)]
    for m in MONTH_FIRST.finditer(text):
        if not any(start <= m.start() < end for start, end, _ in found):
            found.append((m.start(), m.end(), (int(m.group("year")), _month(m.group("month")),
                                               int(m.group("day")) if m.group("day") else None)))
    return sorted(found)


Day = tuple[int, int, int | None]


def _last(day: Day) -> tuple[int, int, int]:
    """The last day a date may mean: the day itself, or a month's end."""
    return day[0], day[1], day[2] or 31


def _first(day: Day) -> tuple[int, int, int]:
    """The first day a date may mean: the day itself, or a month's start."""
    return day[0], day[1], day[2] or 1


def entry_date(entry: Entry, year_only: bool = True) -> Day | None:
    """The latest date an entry gives for the work itself (filed, published, dated, posted), its access date left out.
    An entry giving only its year is dated December of that year, unless `year_only` is false; an undated one, None."""
    days = [day for _, _, day in dates_in(ACCESSED.sub("", entry.text))]
    if days:
        return max(days, key=_last)
    year = re.match(r"\d{4}", entry.year)
    return (int(year.group()), 12, None) if year and year_only else None


def _shown_date(day: Day) -> str:
    names = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December")
    year, month, on = day
    return f"{names[month - 1]} {on}, {year}" if on else f"{names[month - 1]} {year}"


def _written_in(text: str, day: Day) -> bool:
    """Whether a source's text gives a date: the same day, or for a month, any day in it or the month itself."""
    year, month, on = day
    word = ("Jan(?:uary)?", "Feb(?:ruary)?", "Mar(?:ch)?", "Apr(?:il)?", "May", "June?", "July?", "Aug(?:ust)?",
            "Sept?(?:ember)?", "Oct(?:ober)?", "Nov(?:ember)?", "Dec(?:ember)?")[month - 1]
    day_part = rf"0?{on}" if on else r"\d{1,2}"
    optional = "" if on else "?"
    pattern = (rf"\b{word}\.?\s+(?:{day_part}(?:st|nd|rd|th)?,?\s+){optional}{year}\b|\b{day_part}\s+{word}\.?,?\s+{year}\b"
               rf"|\b{year}-{month:02d}-" + (f"{on:02d}\\b" if on else r"\d{2}\b"))
    return re.search(pattern, text, re.I) is not None


def check_dates(drafts: dict[str, str], cited: dict[Entry, list[Cited]], ws: Workspace, con: sqlite3.Connection) -> Iterator[Result]:
    """Two checks of a draft's dates against the dates of the works it cites.

    A date in a sentence later than every work the sentence cites, when no cited source's stored text gives it: the
    fact came from a later source the sentence doesn't cite. A sentence about what was expected or planned is passed
    over, and so is a date inside the citation's own brackets.

    A sentence that states the cut-off as an absolute, "nothing published after 30 June 2025", against the cited
    works the reference list dates after that day: one of the two is wrong, unless the sentence names its exceptions."""
    held = research.Sources(ws, con)
    by_address = {address(url): url for (url,) in con.execute("SELECT DISTINCT url FROM sources")}
    texts: dict[str, str] = {}

    def text_of(url: str) -> str:
        if url not in texts:
            texts[url] = held.text(url) or ""
        return texts[url]

    sentences: dict[tuple[str, int], tuple[str, set[Entry]]] = {}
    for entry, works in cited.items():
        for work in works:
            text = drafts.get(work.file)
            if text is None:
                continue
            sentence = sentence_at(text, work.at)
            start = text.rfind(sentence, 0, work.at + len(sentence))
            sentences.setdefault((work.file, start), (sentence, set()))[1].add(entry)
    for (name, start), (sentence, entries) in sorted(sentences.items(), key=lambda item: item[0]):
        dated = [(day, entry) for entry in entries if (day := entry_date(entry)) is not None]
        if len(dated) < len(entries) or not dated or FORWARD.search(sentence):
            continue
        latest, last = max(dated, key=lambda found: _last(found[0]))
        plain = BRACKETED.sub(lambda match: " " * len(match.group(0)), sentence)
        urls = {by_address[found] for entry in entries for match in ADDRESS.finditer(entry.text)
                if (found := address(match.group(0))) in by_address}
        for begin, end, day in dates_in(plain):
            if _first(day) <= _last(latest):
                continue
            if any(_written_in(text_of(url), day) for url in urls):
                continue
            line = _line(drafts[name], start) + sentence.count("\n", 0, begin)
            yield Result(name, line, "dates", WARN, plain[begin:end],
                         f"later than every work the sentence cites (the latest, {last.author} {last.year}, is dated "
                         f"{_shown_date(latest)}), and no cited source's text gives it: cite the source that does")
    # Only entries that give the work's own date: one dated by its year alone may fall either side of the cut-off.
    when = {entry: day for entry, works in cited.items() if works and (day := entry_date(entry, year_only=False)) is not None}
    for name, text in drafts.items():
        for stated in CUTOFF_STATED.finditer(text):
            sentence = sentence_at(text, stated.start())
            after = sentence[sentence.find(stated.group(0)) + len(stated.group(0)):] if stated.group(0) in sentence else ""
            days = dates_in(after)
            if not days or EXCEPTION.search(sentence):
                continue
            cutoff = _last(days[0][2])
            later = sorted(((day, entry) for entry, day in when.items() if _first(day) > cutoff),
                           key=lambda found: (_first(found[0]), found[1].author, found[1].year))
            if later:
                listed = "; ".join(f"{entry.author} {entry.year} ({_shown_date(day)})" for day, entry in later[:5])
                more = f" and {len(later) - 5} more" if len(later) > 5 else ""
                yield Result(name, _line(text, stated.start()), "dates", WARN, " ".join(stated.group(0).split()),
                             f"the drafts cite {len(later)} work(s) dated after {_shown_date(days[0][2])}: {listed}{more}; "
                             "name the exception here, or drop the works")


# ---------------------------------------------------------------- authors a source line names

# Works a caption's or a table's source line names by their authors, in prose: "annual reports of Acme Corp. and Beta
# Ltd.", "annual reports on Forms 10-K and 20-F of Acme and Beta", "filings and notices of Acme, Beta and Gamma".
NAMED_WORKS = re.compile(r"\b(?:annual|quarterly|interim)?\s*(?:reports?|filings?|releases?|notices?|statements?|announcements?)"
                         r"(?:\s+on\s+Forms?\s+[\w-]+(?:\s+and\s+[\w-]+)?)?\s+of\s+(?P<names>[^;\n]+)")
# A part of such a list that names an author: it opens with a capital or a digit and a capital ("2Ridge Robotics").
AUTHOR_LIKE = re.compile(r"^(?:[^\W\d_a-z]|\d+[A-Z])")


def check_named_authors(drafts: list[tuple[str, str]], entries: list[Entry]) -> Iterator[Result]:
    """Each author a source line names in prose ("Source: annual reports of Acme Corp. and Beta Ltd.") that no entry
    of the reference list gives, in its author or anywhere in its text, as an SEC data entry names the company it's for.
    A name is compared without its kind ("Corp.", "Inc."), and the list's words that aren't names end it."""
    if not entries:
        return
    listed = "\n".join(entry.text for entry in entries)
    for name, text in drafts:
        for line_no, line in enumerate(text.split("\n"), 1):
            source = SOURCE_LIST.search(line)
            if not source:
                continue
            for works in NAMED_WORKS.finditer(source.group("list")):
                for part in re.split(r",\s*|\s+and\s+", works.group("names")):
                    written = part.strip().strip("*_").strip()
                    if not written or not AUTHOR_LIKE.match(written):
                        break  # "the acquirers named", "accessed ...": the list of authors has ended.
                    short = re.sub(rf"(?:\s+{SUFFIX})+$", "", written).strip(" ,.")
                    if short and not re.search(rf"(?<![\w-]){re.escape(short)}(?![\w-])", listed):
                        yield Result(name, line_no, "references", WARN, written,
                                     "a source line names it as an author, but no entry of the reference list gives it")


# ---------------------------------------------------------------- filings a source line names

# A periodic report and the fiscal years it's named for, as a source line gives them: "annual reports on Form 20-F for
# fiscal 2010 to 2025", "Form 10-K for fiscal years 2019 through 2021", "Form 20-F for fiscal 2025".
FORM_YEARS = re.compile(r"\bForms?\s+(?P<form>10-K|20-F|40-F)(?:/A)?\b[^.;\n]{0,40}?\bfiscal(?:\s+years?)?\s+"
                        r"(?P<first>(?:19|20)\d{2})(?:\s*(?:to|through|[-–])\s*(?:fiscal\s+)?(?P<last>(?:19|20)\d{2}))?\b")
# The periodic reports a source line may name for fiscal years.
FORMS = ("10-K", "20-F", "40-F")
# The words that end a company's name and say what kind it is: "Ltd.", "Inc.", "Holding Corp".
SUFFIX = r"(?:Ltd|Limited|Inc|Incorporated|Corp|Corporation|Co|Company|N\.?V|plc|S\.?A|AG|SE|LLC|L\.?P|Holdings?)\.?"
SAME_SUFFIX = {"limited": "ltd", "incorporated": "inc", "corporation": "corp", "company": "co", "holdings": "holding"}
# The most fiscal years a range is read for: a longer one is no list of reports.
MOST_YEARS = 60


@dataclass(frozen=True)
class Filer:
    """A company whose filing list `sec` loaded, as a draft may name it."""
    cik: int
    name: str                  # as the settings or the list give it
    short: str                 # without its kind: "Northbridge Robotics" for "Northbridge Robotics Ltd."
    kinds: frozenset[str]      # its kind, each word as compared: {"ltd"}


def _kind(words: str) -> set[str]:
    return {SAME_SUFFIX.get(word, word) for word in re.findall(r"[a-z]+", words.casefold().replace(".", ""))}


def filers(ws: Workspace, con: sqlite3.Connection) -> list[Filer]:
    """The companies with a filing list loaded, each under every name the settings and the list give it."""
    loaded = {cik for (cik,) in con.execute("SELECT DISTINCT cik FROM filings")}
    named = [(int(company["cik"]), str(company.get("name", ""))) for company in ws.config().get("sec", {}).get("company", [])
             if isinstance(company, dict) and str(company.get("cik", "")).isdigit()]
    named += [(cik, entity or "") for cik, entity in con.execute("SELECT DISTINCT cik, entity FROM filings")]
    found: dict[tuple[int, str], set[str]] = {}
    for cik, name in named:
        plain = re.sub(r"\s*\([^)]*\)", "", name).strip()
        plain = re.sub(r"^The\s+", "", plain, flags=re.I)
        kind = re.search(rf"(?:,?\s+{SUFFIX})+\s*$", plain, re.I)
        short = (plain[:kind.start()] if kind else plain).strip(" ,")
        if cik in loaded and short:
            found.setdefault((cik, short.casefold()), set()).update(_kind(kind.group(0)) if kind else set())
    names = {cik: name for cik, name in reversed(named) if name}
    return [Filer(cik, names.get(cik, short), short, frozenset(kinds)) for (cik, short), kinds in found.items()]


def _spans(years: list[int]) -> str:
    """Years as runs: "2012 to 2025", or "2010, 2012 to 2014"."""
    runs: list[list[int]] = []
    for year in sorted(set(years)):
        if runs and year == runs[-1][-1] + 1:
            runs[-1].append(year)
        else:
            runs.append([year])
    return ", ".join(str(run[0]) if len(run) == 1 else f"{run[0]} to {run[-1]}" for run in runs)


def check_filings(drafts: list[tuple[str, str]], ws: Workspace, con: sqlite3.Connection) -> Iterator[Result]:
    """Each line that names a company's periodic report for fiscal years ("Northbridge Robotics Ltd., annual reports on Form 20-F
    for fiscal 2010 to 2025") where the filing list `sec` loaded for that company holds no such report for some of the
    years. The company is the one the line names last before the form, in the same clause; a line that gives it another
    kind ("Northbridge Robotics, Inc." for Northbridge Robotics Ltd.) names another filer, and isn't judged. A fiscal year is the year its
    period ends, or the year before for one that ends by March."""
    known = filers(ws, con)
    if not known:
        return
    filed: dict[tuple[int, str], set[int]] = {}
    for cik, form, ended in con.execute("SELECT cik, form, report_date FROM filings WHERE report_date LIKE '____-__-__%'"):
        year, month = int(ended[:4]), int(ended[5:7])
        filed.setdefault((cik, form.removesuffix("/A")), set()).update({year, year - 1} if month <= 3 else {year})
    for name, text in drafts:
        for line_no, line in enumerate(text.split("\n"), 1):
            for match in FORM_YEARS.finditer(line):
                clause = re.split(r";|\bSources?:", line[:match.start()])[-1]
                named: tuple[int, Filer] | None = None
                for filer in known:
                    for found in re.finditer(rf"(?<![\w-]){re.escape(filer.short)}(?P<kind>(?:,?\s+{SUFFIX})+)?(?![\w-])", clause, re.I):
                        given = _kind(found.group("kind")) if found.group("kind") else set()
                        if given and filer.kinds and not given & filer.kinds:
                            continue  # Another filer of that name.
                        if named is None or found.start() > named[0]:
                            named = (found.start(), filer)
                if named is None:
                    continue
                filer, form = named[1], match.group("form")
                first, last = int(match.group("first")), int(match.group("last") or match.group("first"))
                if not 0 <= last - first < MOST_YEARS:
                    continue
                has = filed.get((filer.cik, form), set())
                missing = [year for year in range(first, last + 1) if year not in has]
                if not missing:
                    continue
                others = sorted({kind for (cik, kind), years in filed.items()
                                 if cik == filer.cik and kind in FORMS and kind != form and set(missing) & years})
                listed = f"its {form}s are for fiscal {_spans(sorted(has))}" if has else f"it has no {form} at all"
                instead = f", and its {' and '.join(others)} covers some of those years" if others else ""
                yield Result(name, line_no, "filings", FAIL, match.group(0),
                             f"{filer.name} filed no {form} for fiscal {_spans(missing)}: in the filing list `sec` loaded, "
                             f"{listed}{instead}")


# ---------------------------------------------------------------- cross-references and exhibits

KINDS = ("Exhibit", "Figure", "Table", "Chart")
HEADING_NUMBER = re.compile(r"^#+\s*(?:Section\s+)?(?P<number>\d+(?:\.\d+)*)[.)]?\s")
APPENDIX_HEADING = re.compile(r"^#+\s*Appendix\s+(?P<id>[A-Z]|\d+)\b", re.I)
CAPTIONED = re.compile(rf"^[\s*_>]*(?P<kind>{'|'.join(KINDS)})\s+(?P<id>[A-Z]?\d+[a-z]?)\s*[.:]")
IMAGE = re.compile(rf"^[\s*_>]*(?:&#91;|\[)\s*image:\s*(?P<kind>{'|'.join(KINDS)})\s+(?P<id>[A-Z]?\d+[a-z]?)", re.I)
ENTRY_BLOCK = re.compile(r"^[\s*_#>]*Entry\s+(?P<number>\d+)\s*[.:*]", re.I)
_NUMBER_LIST = r"\d+(?:\.\d+)*(?:(?:\s*,\s*|\s+and\s+|\s+or\s+|\s*[-–]\s*|\s+to\s+)\d+(?:\.\d+)*)*"
SECTION_REF = re.compile(rf"\b[Ss]ections?\s+(?P<list>{_NUMBER_LIST})(?![\d.]*\d)(?!\s+of\s+(?:the\s+)?[A-Z])")
KIND_REF = re.compile(rf"\b(?P<kind>{'|'.join(KINDS)})s?\s+(?P<id>[A-Z]?\d+[a-z]?)\b")
APPENDIX_REF = re.compile(r"\bAppendi(?:x|ces)\s+(?P<id>[A-Z])(?=\b|\d)")
ENTRY_REF = re.compile(r"\b[Ee]ntr(?:y|ies)\s+(?P<list>\d+(?:(?:\s*,\s*|\s+and\s+|\s*[-–]\s*)\d+)*)")
# "the Appendix" with no letter or number after it, as a pointer to one part of an appendix that has several.
THE_APPENDIX = re.compile(r"\b[Tt]he\s+[Aa]ppendix\b(?!\s+(?:[A-Z]|\d+)\b)")
# "that date" and "that day" point back to a date. With two dates before them, in their sentence or the one before,
# the nearest is the one a reader takes, and often not the one meant: "Data runs to 11 November. Filings of 12
# November are kept, as they report facts as of that date." A date is read with or without its year, day first or
# month first, or as 2026-11-12; the same day and month with a year and without are one date.
THAT_DATE = re.compile(r"\b[Tt]hat\s+(?:date|day)\b")
_DAY_MONTH = re.compile(rf"\b(?P<day>\d{{1,2}})\s+(?P<month>{_MONTH_WORD})\.?(?:,?\s+(?P<year>(?:19|20)\d{{2}}))?\b")
_MONTH_DAY = re.compile(rf"\b(?P<month>{_MONTH_WORD})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\b(?:,\s+(?P<year>(?:19|20)\d{{2}}))?")
_ISO_DAY = re.compile(r"\b(?P<year>(?:19|20)\d{2})-(?P<month>\d{2})-(?P<day>\d{2})\b")
SENTENCE_END = re.compile(r"(?<=[.!?])[\"'”’)]*\s+(?=[\"“(]?[A-Z0-9])")


@dataclass
class Targets:
    """What a cross-reference may point at, read from every draft and companion file. `holds` gives, for each entry
    number, the appendix whose section it stands in, where one does."""
    sections: set[str]
    appendices: set[str]
    captions: dict[tuple[str, str], list[tuple[str, int]]]
    images: set[tuple[str, str]]
    entries: set[str]
    holds: dict[str, str] = field(default_factory=dict)


def targets(files: list[tuple[str, str]]) -> Targets:
    found = Targets(set(), set(), {}, set(), set())
    for name, text in files:
        within = ""  # The appendix whose section this line stands in; a heading of its level or above ends it.
        level = 0
        for line_no, line in enumerate(text.split("\n"), 1):
            row = line.strip()
            if (marked := HEADING.match(row)) and within and len(marked.group("marks")) <= level:
                within = ""
            if heading := HEADING_NUMBER.match(row):
                found.sections.add(heading.group("number"))
            if appendix := APPENDIX_HEADING.match(row):
                found.appendices.add(appendix.group("id").upper())
                within, level = appendix.group("id").upper(), len(row) - len(row.lstrip("#"))
            if image := IMAGE.match(row):
                found.images.add((image.group("kind").title(), image.group("id")))
            elif caption := CAPTIONED.match(row):
                found.captions.setdefault((caption.group("kind").title(), caption.group("id")), []).append((name, line_no))
            if entry := ENTRY_BLOCK.match(row):
                found.entries.add(entry.group("number"))
                if within:
                    found.holds.setdefault(entry.group("number"), within)
    return found


def _numbers(listed: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)*", listed)


def _outside_citations(line: str) -> str:
    """A line with its in-text citations blanked: "(Roe 2024, section 4)" points into a source, not the draft."""
    return BRACKETED.sub(lambda match: " " * len(match.group(0)), line)


def check_cross_references(drafts: list[tuple[str, str]], found: Targets) -> Iterator[Result]:
    """Each cross-reference that names a heading, caption, appendix or entry the drafts and companions don't give."""
    hint = "; add the part that holds it to the drafts, or name it under [proof] companions"
    for name, text in drafts:
        for line_no, line in enumerate(text.split("\n"), 1):
            row = line.strip()
            if row.startswith("#") or CAPTIONED.match(row) or IMAGE.match(row):
                continue
            plain = _outside_citations(line)
            for match in SECTION_REF.finditer(plain):
                for number in _numbers(match.group("list")):
                    if int(number.split(".")[0]) < 100 and number not in found.sections:
                        yield Result(name, line_no, "cross-references", FAIL, f"section {number}", "no heading is numbered so" + hint)
            for match in KIND_REF.finditer(plain):
                kind, given = match.group("kind").title(), match.group("id")
                if (kind, given) not in found.captions and (kind, given) not in found.images:
                    yield Result(name, line_no, "cross-references", FAIL, f"{kind} {given}", "no caption gives it" + hint)
            for match in APPENDIX_REF.finditer(plain):
                if match.group("id") not in found.appendices:
                    yield Result(name, line_no, "cross-references", FAIL, f"Appendix {match.group('id')}", "no heading names it" + hint)
            for match in ENTRY_REF.finditer(plain):
                for number in _numbers(match.group("list")):
                    if number not in found.entries:
                        yield Result(name, line_no, "cross-references", FAIL, f"entry {number}", "no entry is numbered so" + hint)
            if len(found.appendices) > 1:
                # Read on the whole line: "(Helper AI, 2025; AI citation in the Appendix)" points into the report.
                yield from _the_appendix(name, line_no, line, found)
            yield from _that_date(name, line_no, plain)


def _days(text: str) -> list[tuple[int, str, tuple[int | None, int, int]]]:
    """Each date to the day in a text, with or without its year: (where, as written, (year or None, month, day))."""
    found: list[tuple[int, str, tuple[int | None, int, int]]] = []
    taken: list[tuple[int, int]] = []
    for pattern in (_ISO_DAY, _DAY_MONTH, _MONTH_DAY):
        for m in pattern.finditer(text):
            if any(start < m.end() and m.start() < end for start, end in taken):
                continue
            month = int(m.group("month")) if m.group("month").isdigit() else _month(m.group("month"))
            if not (1 <= month <= 12 and 1 <= int(m.group("day")) <= 31):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), m.group().strip(" ,."), (int(m.group("year")) if m.group("year") else None, month, int(m.group("day")))))
    return sorted(found)


def _that_date(name: str, line_no: int, line: str) -> Iterator[Result]:
    """A warning for each "that date" or "that day" with two different dates before it, in its own sentence and the
    one before: it names them, nearest first, since the nearest is the one a reader takes."""
    starts = [0] + [m.end() for m in SENTENCE_END.finditer(line)]
    for match in THAT_DATE.finditer(line):
        begun = [start for start in starts if start <= match.start()]
        reach = begun[-2] if len(begun) > 1 else 0
        distinct: list[tuple[str, tuple[int | None, int, int]]] = []
        for _, shown, (year, month, day) in reversed(_days(line[reach:match.start()])):
            if not any(m == month and d == day and (y is None or year is None or y == year) for _, (y, m, d) in distinct):
                distinct.append((shown, (year, month, day)))
        if len(distinct) > 1:
            could = ", ".join(shown for shown, _ in distinct[:-1]) + f" or {distinct[-1][0]}"
            yield Result(name, line_no, "cross-references", WARN, match.group(),
                         f"two dates come before it, so it could mean {could}: name the date meant")


def _the_appendix(name: str, line_no: int, line: str, found: Targets) -> Iterator[Result]:
    """A warning for each "the Appendix" on a line, where the report has lettered appendices: it names them, and the
    one holding the entries the line names, if they stand in one."""
    parts = sorted(found.appendices)
    could = ", ".join(f"Appendix {part}" for part in parts[:-1]) + f" or Appendix {parts[-1]}"
    holding = sorted({found.holds[number] for match in ENTRY_REF.finditer(line) for number in _numbers(match.group("list"))
                      if number in found.holds})
    for _ in THE_APPENDIX.finditer(line):
        detail = f"the report has lettered appendices, so this could mean {could}"
        if len(holding) == 1:
            detail += f"; the entries it names are in Appendix {holding[0]}"
        yield Result(name, line_no, "cross-references", WARN, "the Appendix", detail)


def check_exhibits(drafts: list[tuple[str, str]], found: Targets) -> Iterator[Result]:
    """Each exhibit, figure, table or chart a draft captions more than once, or never mentions outside its caption."""
    mentioned: set[tuple[str, str]] = set()
    names = {name for name, _ in drafts}
    for _, text in drafts:
        for row in text.split("\n"):
            if not (CAPTIONED.match(row.strip()) or IMAGE.match(row.strip())):
                mentioned |= {(match.group("kind").title(), match.group("id")) for match in KIND_REF.finditer(row)}
    for (kind, given), places in sorted(found.captions.items()):
        own = [(name, line) for name, line in places if name in names]
        for name, line in own[1:]:
            yield Result(name, line, "exhibits", FAIL, f"{kind} {given}", f"captioned again: first at {own[0][0]}:{own[0][1]}")
        if own and (kind, given) not in mentioned:
            yield Result(own[0][0], own[0][1], "exhibits", WARN, f"{kind} {given}", "captioned, but the text never mentions it")


# ---------------------------------------------------------------- the numbering of a record's entries

# An entry of a record numbered as an item of a list at the margin: "12. Roe ...", "**12.** ...".
NUMBERED_ITEM = re.compile(r"^(?:\*\*|__)?(?P<number>\d{1,4})[.)](?:\*\*|__)?\s+\S")
FENCE = re.compile(r"^\s*(?:```|~~~)")


def record_parts(text: str, kept: tuple[str, ...]) -> str:
    """The sections of a draft that `[drafts] records` names, each line where it was, and every other line blank."""
    aside = set_aside(text, kept, references=False).split("\n")
    return "\n".join(line if line and not aside[at] else "" for at, line in enumerate(text.split("\n")))


def check_numbering(name: str, text: str) -> Iterator[Result]:
    """Each entry of a record numbered twice, or out of order. A record's entries, "**Entry 12.**" or a list's "12."
    at the margin, run 1, 2, 3 through it and across its headings, so an entry added at the foot, after a later
    heading, is still in the run. A run that starts again at 1 is a new list. A number used before fails, and so does
    one lower than the one before it; one that skips numbers is a warning, since an entry may have been taken out."""
    last: dict[str, int] = {}
    seen: dict[str, dict[int, int]] = {}
    fenced = False
    for line_no, line in enumerate(text.split("\n"), 1):
        if FENCE.match(line):
            fenced = not fenced
        if fenced:
            continue
        found = ENTRY_BLOCK.match(line.strip()) or NUMBERED_ITEM.match(line)
        if not found:
            continue
        kind = "entry" if found.re is ENTRY_BLOCK else "item"
        number = int(found.group("number"))
        what = f"entry {number}" if kind == "entry" else f"{number}."
        if number == 1:
            seen[kind], last[kind] = {}, 0
        before = last.get(kind)
        numbers = seen.setdefault(kind, {})
        if number in numbers:
            yield Result(name, line_no, "numbering", FAIL, what, f"numbered twice: also at {name}:{numbers[number]}")
        elif before is not None and number < before:
            yield Result(name, line_no, "numbering", FAIL, what, f"out of order: it follows {before}")
        elif before is not None and number > before + 1:
            gap = str(before + 1) if number == before + 2 else f"{before + 1} to {number - 1}"
            yield Result(name, line_no, "numbering", WARN, what, f"follows {before}, so {gap} is missing or this is misnumbered")
        numbers.setdefault(number, line_no)
        last[kind] = number


def check_record_logs(whole: list[tuple[str, str]], companions: list[tuple[Path, tuple[str, str]]],
                      given: tuple[RecordLog, ...], ws: Workspace) -> Iterator[Result]:
    """Each record that `[[proof.record_logs]]` names held to its log (`record_log`). The record is a companion file
    named by its path or file name, or else the section of a draft that a heading of that name opens."""
    for setting in given:
        found: list[tuple[str, str]] = [shown for path, shown in companions
                                        if setting.record in (path.name, path.relative_to(ws.root).as_posix())]
        if not found:
            found = [(name, part) for name, text in whole if (part := record_parts(text, (setting.record,))).strip()]
        if not found:
            yield Result(setting.log.name, 0, "records", FAIL, setting.record, "no draft has a section of that heading, "
                         "and no companion file has that name, so the log can't be held to it")
            continue
        log = record_log.read(setting.log)
        cuts = [record_log.read(path) for path in setting.cuts]
        typed = sessions.read(setting.sessions) if setting.sessions else []
        findings = [(name, finding) for name, text in found
                    for finding in record_log.check(text, log, cuts, setting.log.name, typed)]
        # What the log lacks is said once, however many drafts hold the record.
        findings += [(setting.log.name, finding) for finding in record_log.unlogged(typed, log, cuts, setting.log.name)]
        for name, finding in findings:
            yield Result(name, finding.line, "records", FAIL if finding.verdict == "fail" else WARN, finding.item, finding.detail)


# ---------------------------------------------------------------- the summary, and what sentences point to

SUMMARY_HEADING = re.compile(r"^#+\s*(?:\d+[.)]?\s*)?(?:Executive summary|Summary|Abstract|Key findings)\b", re.I)
# What a pointer names that isn't a figure of the sentence: the pointer itself, and an exhibit, table or entry.
NOT_FIGURES = (SECTION_REF, APPENDIX_REF, KIND_REF, ENTRY_REF)
# How many semicolons make a sentence a list of clauses, each with its own pointer.
LISTED = 2


@dataclass(frozen=True)
class Part:
    """A numbered section or an appendix of a draft, or its summary: from its heading to the next heading of its
    level or above that isn't numbered inside it, so section 6 holds 6.1, 6.2 and an unnumbered heading under it."""
    file: str
    key: str            # "6.1" or "Appendix A"; "" for a summary that isn't numbered
    summary: bool
    first: int          # the line of its heading, and the line after its last
    end: int
    text: str


def parts(name: str, text: str) -> list[Part]:
    lines = text.split("\n")
    heads: list[tuple[int, int, str, bool]] = []  # (line index, level, key, whether it's a summary)
    for at, line in enumerate(lines):
        heading = HEADING.match(line)
        if not heading:
            continue
        row = line.strip()
        numbered = HEADING_NUMBER.match(row)
        appendix = APPENDIX_HEADING.match(row)
        key = numbered.group("number") if numbered else f"Appendix {appendix.group('id').upper()}" if appendix else ""
        heads.append((at, len(heading.group("marks")), key, bool(SUMMARY_HEADING.match(row))))
    found = []
    for index, (at, level, key, summary) in enumerate(heads):
        if not key and not summary:
            continue
        end = next((later for later, below, inner, _ in heads[index + 1:]
                    if below <= level and not (key[:1].isdigit() and inner.startswith(key + "."))), len(lines))
        found.append(Part(name, key, summary, at + 1, end + 1, "\n".join(lines[at:end])))
    return found


def _pointed(listed: str) -> list[str]:
    """The sections a pointer's list names, a range of whole sections ("5 to 7", "5-7") counted through."""
    numbers = _numbers(listed)
    if len(numbers) == 2 and re.search(r"\d\s*(?:[-–]|\bto\b)\s*\d", listed) and all(n.isdigit() for n in numbers):
        low, high = int(numbers[0]), int(numbers[1])
        if 0 < high - low < 20:
            return [str(n) for n in range(low, high + 1)]
    return numbers


def _said(sentence: str) -> str:
    """A sentence without its citations and pointers, each blanked where it stood."""
    plain = BRACKETED.sub(lambda match: " " * len(match.group(0)), sentence)
    for pattern in NOT_FIGURES:
        plain = pattern.sub(lambda match: " " * len(match.group(0)), plain)
    return plain


def _figures(sentence: str) -> list[assay_numbers.Quantity]:
    """The figures of a sentence worth tracing: amounts of three digits or more and percentages of two, outside its
    citations and pointers, with dates, years and identifiers set aside."""
    return [claim for claim in assay_numbers.quantities(_said(sentence), NOTES_POLICY)
            if claim.kind in ("number", "percent") and claim.figures >= (2 if claim.kind == "percent" else 3)]


def _named(found: list[Part]) -> str:
    """Where a figure is, as a finding names it: the most specific parts, none that holds another of them, two at
    most."""
    inner = [part for part in found if part.key and not any(
        other is not part and other.key and other.file == part.file and part.first <= other.first and other.end <= part.end
        for other in found)]
    shown = [part.key if part.key.startswith("Appendix") else f"section {part.key}"
             for part in sorted(inner, key=lambda part: (part.file, part.first))]
    return " and ".join(dict.fromkeys(shown[:2]))


def _supported(lines: list[str], line_no: int) -> bool:
    """Whether a line gives a source for what it says: a citation, a label of the author's working, or, for a table's
    row, a source line or citation in the table's caption or note just after it."""
    row = lines[line_no - 1]
    if BRACKETED.search(row) or WORKED_BY_AUTHOR.search(row) or SOURCE_LIST.search(row):
        return True
    if not row.lstrip().startswith("|"):
        return False
    at = line_no
    while at < len(lines) and lines[at].lstrip().startswith("|"):
        at += 1
    after = "\n".join(lines[at:at + 3])
    return bool(SOURCE_LIST.search(after) or BRACKETED.search(after))


def check_provenance(drafts_read: list[tuple[str, str]]) -> tuple[list[Result], list[Result]]:
    """The summary's figures that no other part of the drafts gives, and the figures of each sentence that points to
    sections or appendices ("(sections 2.1 and 4)", "see Appendix A") that none of them gives. A line gives a figure
    for what a sentence says when it holds the figure, as the measured policy compares a source (at any scale, or to
    more places), and shares two describing words with the sentence (as `assay` asks of a line about the same thing),
    its table's heading counted as its own: a 6.8% hurdle doesn't give a summary's 6.8% growth. Both are warnings: a
    summary may add up what the body gives, and a pointer may name where the method is rather than the figure."""
    texts = [(name, assay_text.matchable(text)) for name, text in drafts_read]
    every = [part for name, text in texts for part in parts(name, text)]
    rows = {name: text.split("\n") for name, text in texts}
    headers = {name: table_headers(text) for name, text in texts}
    read: dict[tuple[str, int], assay_numbers.Evidence] = {}

    def within(part: Part, name: str, line: int) -> bool:
        return part.file == name and part.first <= line < part.end

    def giving(claim: assay_numbers.Quantity, sentence: str, skip: Callable[[str, int], bool]) -> list[tuple[str, int]]:
        """The lines outside `skip` that give a figure for what its sentence says, as (file, line)."""
        words = set(research.describing_words(_said(sentence)))
        needed = min(BOUND_WORDS, len(words))
        found = []
        for name, lines in rows.items():
            for line_no, row in enumerate(lines, 1):
                if not re.search(r"\d", row) or skip(name, line_no):
                    continue
                if (name, line_no) not in read:
                    read[(name, line_no)] = assay_numbers.evidence(row, policy=assay_numbers.MEASURED)
                if not assay_numbers.holds(read[(name, line_no)], claim, assay_numbers.MEASURED):
                    continue
                if len(words & set(research.describing_words(" ".join([row, *headers[name].get(line_no, [])])))) >= needed:
                    found.append((name, line_no))
        return found

    summary: list[Result] = []
    pointers: list[Result] = []
    summaries = [part for part in every if part.summary]
    for part in summaries:
        for claim in _figures(part.text):
            said = sentence_at(part.text, claim.start)
            if not giving(claim, said, lambda name, line: any(within(each, name, line) for each in summaries)):
                summary.append(Result(part.file, part.first + part.text.count("\n", 0, claim.start), "summary", WARN, claim.text,
                                      "in the summary, but no other part of the drafts gives it for anything the sentence names"))
    for name, text in texts:
        sentences: dict[int, tuple[str, list[str]]] = {}
        plain = BRACKETED.sub(lambda match: " " * len(match.group(0)), text)
        for pattern, named_by in ((SECTION_REF, lambda match: _pointed(match.group("list"))),
                                  (APPENDIX_REF, lambda match: [f"Appendix {match.group('id')}"])):
            for match in pattern.finditer(plain):
                sentence = sentence_at(text, match.start())
                start = text.rfind(sentence, 0, match.start() + len(sentence))
                # A pointer covers the whole sentence ("...fell 4.4%; section 1.2 builds on it"), but only its own
                # clause of one that lists three or more with semicolons, "(1) ...; (2) ...; (3) ...". A semicolon
                # between citations in brackets separates nothing.
                bare = plain[start:start + len(sentence)]
                at = match.start() - start
                begin, end = 0, len(sentence)
                if bare.count(";") >= LISTED:
                    begin = bare.rfind(";", 0, at) + 1
                    end = bare.find(";", at) if bare.find(";", at) >= 0 else len(sentence)
                sentences.setdefault(start + begin, (sentence[begin:end], []))[1].extend(named_by(match))
        for start, (sentence, keys) in sorted(sentences.items()):
            targets_named = [part for part in every if part.key in keys]
            if not targets_named:
                continue  # A pointer to nothing the drafts have is a cross-reference's to find.
            named = " and ".join(dict.fromkeys(key if key.startswith("Appendix") else f"section {key}" for key in keys))
            first = _line(text, start)
            last = first + sentence.count("\n")
            def own_sentence(file: str, line: int, own: str = name, top: int = first, end: int = last) -> bool:
                return file == own and top <= line <= end

            for claim in _figures(sentence):
                found = giving(claim, sentence, own_sentence)
                there = [place for place in found if any(within(part, *place) for part in targets_named)]
                if there:
                    if not BRACKETED.search(sentence) and not any(_supported(rows[file], line) for file, line in there):
                        pointers.append(Result(name, first + sentence.count("\n", 0, claim.start), "pointers", WARN, claim.text,
                                               f"the sentence points to {named} for it and cites nothing, and the line there "
                                               f"that gives it ({there[0][0]}:{there[0][1]}) cites no source either"))
                    continue
                elsewhere = _named([part for part in every if any(within(part, *place) for place in found)])
                where = f"; it's given in {elsewhere}" if elsewhere else "; no other part of the drafts gives it either"
                pointers.append(Result(name, first + sentence.count("\n", 0, claim.start), "pointers", WARN, claim.text,
                                       f"the sentence points to {named}, but none gives it for anything the sentence names{where}"))
    return summary, pointers


# ---------------------------------------------------------------- sums

# A money figure as prose writes one, and a table cell that is a single amount: a sign or accounting brackets, a
# currency, the digits, a scale and a percent sign, each where there is one.
MONEY = r"(?:US\$|\$|€|£)\s?\d[\d,]*(?:\.\d+)?\s*(?:bn|[MBK]\b|million|billion|thousand)?"
AMOUNT = re.compile(r"^\(?(?P<sign>[-+−])?\s*(?:US\$|\$|€|£)?\s*(?P<digits>\d[\d,]*(?:\.\d+)?)\s*"
                    r"(?P<scale>bn|[MBK]|million|billion|thousand)?\)?\s*(?P<percent>%)?$", re.I)
HEDGE = re.compile(r"^(?:up to|about|around|roughly|approximately|at most|some|nearly|almost)\s+", re.I)
TOTAL_WORD = re.compile(r"^\W*(?:total|sum)\b", re.I)
PROSE_TOTAL = re.compile(r"\btotal(?:s|led|ling|ed|ing)?\b(?:\s+(?:of|to|is|was|were|are))?\s+"
                         rf"(?P<about>(?:about|around|roughly|approximately|some|nearly|almost|close to)\s+)?(?P<amount>{MONEY})", re.I)
SCALES = {"k": 3, "thousand": 3, "m": 6, "million": 6, "b": 9, "bn": 9, "billion": 9}


def _sum(parts: list[tuple[Decimal, int]]) -> str:
    """What amounts add up to, as a finding writes it."""
    return format(sum((value for value, _ in parts), Decimal(0)).normalize(), "f")


def amount_of(cell: str) -> tuple[Decimal, int] | None:
    """A table cell that is a single amount, as its value and the power of ten its last written digit stands for; or
    None. Accounting brackets make it negative."""
    plain = re.sub(r"[*_]", "", cell).strip()
    found = AMOUNT.match(plain)
    if not found or not plain:
        return None
    digits = found.group("digits").replace(",", "")
    power = SCALES.get((found.group("scale") or "").lower(), 0)
    try:
        value = Decimal(digits).scaleb(power)
    except InvalidOperation:
        return None
    negative = found.group("sign") in ("-", "−") or (plain.startswith("(") and plain.endswith(")"))
    return (-value if negative else value), power - (len(digits.split(".")[1]) if "." in digits else 0)


def _agrees(parts: list[tuple[Decimal, int]], total: tuple[Decimal, int], about: bool, counted: bool = False) -> bool:
    """Whether amounts add up to a total: exactly, for counts; allowing for the rounding of each, for measures; and
    within 5% more when the total is "about" so much."""
    gap = abs(sum((value for value, _ in parts), Decimal(0)) - total[0])
    slack = Decimal(0) if counted else sum((Decimal(5).scaleb(exponent - 1) for _, exponent in [*parts, total]), Decimal(0))
    return gap <= (abs(total[0]) * Decimal("0.05") if about else Decimal(0)) + slack


# Whole numbers written bare, as a table of scores gives them, are counts: 5 + 4 is 9, and never "about" 10.
COUNT = re.compile(r"^\s*\**\s*\d{1,3}\s*\**\s*$")


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def tables_in(text: str) -> Iterator[tuple[int, list[str], list[tuple[int, list[str]]]]]:
    """Each Markdown table of a text: the line after it, its heading's cells, and its rows with their line numbers."""
    lines = text.split("\n")
    at = 0
    while at < len(lines):
        if lines[at].strip().startswith("|") and at + 1 < len(lines) and re.fullmatch(r"\|[\s\-:|]+\|", lines[at + 1].strip()):
            header = _cells(lines[at])
            rows = []
            at += 2
            while at < len(lines) and lines[at].strip().startswith("|"):
                rows.append((at + 1, _cells(lines[at])))
                at += 1
            yield at + 1, header, rows
            continue
        at += 1


def check_sums(name: str, text: str) -> Iterator[Result]:
    """Totals in a draft's tables that aren't the sum of what they total, workings that don't recompute, and totals
    stated in prose that don't add up. A table's Total row, and a working written out in a draft, are judged by
    `arithmetic`, as it judges the notes' own; a Total column, which `arithmetic` doesn't read, is judged here."""
    for worked in arithmetic.check_text(name, text):
        if worked.status == "wrong":
            yield Result(name, worked.line, "sums", FAIL, worked.item or worked.stated, worked.why or worked.detail)
    after_table: dict[int, list[tuple[int, list[str]]]] = {}
    for end, header, rows in tables_in(text):
        after_table[end] = rows
        totals = [index for index, cell in enumerate(header) if index and TOTAL_WORD.match(cell)]
        for line_no, cells in rows:
            for column in totals:
                total = amount_of(cells[column]) if column < len(cells) else None
                written = [cell for cell in cells[1:column] if amount_of(cell)]
                parts = [found for cell in written if (found := amount_of(cell))]
                counted = all(COUNT.match(cell) for cell in [*written, cells[column]])
                if total and len(parts) >= 2 and not _agrees(parts, total, False, counted):
                    yield Result(name, line_no, "sums", FAIL, cells[column],
                                 f"the {header[column]!r} column gives {cells[column]}, but the figures before it sum to "
                                 f"{_sum(parts)}")
    yield from prose_totals(name, text, after_table)


def prose_totals(name: str, text: str, after_table: dict[int, list[tuple[int, list[str]]]]) -> Iterator[Result]:
    """Each sentence that says figures total an amount, where they don't."""
    for match in PROSE_TOTAL.finditer(text):
        total = amount_of(match.group("amount"))
        if total is None:
            continue
        sentence = sentence_at(text, match.start())
        start = text.rfind(sentence, 0, match.start() + len(sentence))
        before = text[start:match.start()]
        parts = [found for figure in re.finditer(MONEY, before)
                 if (found := amount_of(figure.group(0)))]
        source = "the amounts before it"
        if len(parts) < 2:
            line_no = _line(text, start)
            rows = next((rows for end, rows in after_table.items() if 0 <= line_no - end <= 2), None)
            parts, source = _column(rows) if rows else ([], "")
        if len(parts) >= 2 and not _agrees(parts, total, bool(match.group("about"))):
            yield Result(name, _line(text, match.start()), "sums", WARN, match.group(0),
                         f"{source} sum to {_sum(parts)}, not {match.group('amount')}")


def _column(rows: list[tuple[int, list[str]]]) -> tuple[list[tuple[Decimal, int]], str]:
    """The last column of a table with two or more cells that are each a single amount, perhaps after "Up to" or
    "About" and with a remark in brackets after it, and those amounts."""
    width = max((len(cells) for _, cells in rows), default=0)
    for column in range(width - 1, 0, -1):
        found = []
        for _, cells in rows:
            if column < len(cells):
                cell = HEDGE.sub("", re.sub(r"\s*\([^)]*\)\s*$", "", cells[column].strip()))
                if (amount := amount_of(cell)) is not None:
                    found.append(amount)
        if len(found) >= 2:
            return found, "the single amounts in the table above"
    return [], ""


# ---------------------------------------------------------------- a framework's tables

def check_tables(name: str, text: str, given: Settings) -> Iterator[Result]:
    """Each cell of a draft's tables that breaks a rule `[[proof.table_rules]]` sets (`framework`)."""
    for _, header, rows in tables_in(text):
        for rule in given.tables:
            for found in framework.check(rule, header, rows):
                yield Result(name, found.line, "tables", FAIL, found.item, found.detail)


# ---------------------------------------------------------------- spelling

# Spellings that belong to one variety of English and are never right in the other, as (British, American). A draft
# written in one variety that uses the other's spelling has most likely copied it from somewhere, as a source's phrase
# retyped ("consumer behaviour" for the handbook's "consumer behavior"). Only words wrong in the other variety are
# here: "-ize" is good British (Oxford) spelling and "license" a British verb, so neither is held against a British
# draft, and "programme" is British only where it isn't software. Each pair stands for its endings too.
VARIANTS = (("behaviour", "behavior"), ("colour", "color"), ("favour", "favor"), ("honour", "honor"),
            ("labour", "labor"), ("neighbour", "neighbor"), ("flavour", "flavor"), ("humour", "humor"),
            ("rumour", "rumor"), ("endeavour", "endeavor"), ("harbour", "harbor"), ("vapour", "vapor"),
            ("defence", "defense"), ("offence", "offense"), ("pretence", "pretense"), ("licence", ""),
            ("centre", "center"), ("metre", ""), ("litre", "liter"), ("fibre", "fiber"), ("calibre", "caliber"),
            ("theatre", "theater"), ("programme", ""), ("catalogue", "catalog"), ("analyse", "analyze"),
            ("organise", ""), ("recognise", ""), ("realise", ""), ("prioritise", ""), ("standardise", ""),
            ("minimise", ""), ("maximise", ""), ("specialise", ""), ("utilise", ""), ("emphasise", ""),
            ("optimise", ""), ("summarise", ""), ("characterise", ""), ("authorise", ""), ("finalise", ""),
            ("criticise", ""), ("categorise", ""), ("commercialise", ""), ("monetise", ""), ("centralise", ""),
            ("stabilise", ""), ("normalise", ""), ("capitalise", ""), ("modelling", "modeling"),
            ("travelling", "traveling"), ("labelling", "labeling"), ("ageing", ""), ("aluminium", "aluminum"),
            ("sulphur", ""), ("tyre", ""), ("cheque", ""))
# The endings each kind of word takes: "organise" gives organised, organises, organising, organisation; the others
# give behaviours, behavioural, centred, centres, defences, favourite, catalogued.
VERB_ENDINGS = r"(?:e|es|ed|ing|ation|ations|er|ers)"
ENDINGS = r"(?:s|es|d|ed|ing|al|ally|ite|ites|able)?"
# A quotation keeps the spelling of whoever is quoted.
QUOTED = re.compile(r"\"[^\"\n]*\"|“[^”\n]*”")


def _variety(words: tuple[str, ...]) -> re.Pattern[str]:
    """One variety's words, with their endings, as a pattern that finds them whole in any case."""
    verbs = sorted({word[:-1] for word in words if word.endswith(("ise", "yse", "yze"))}, key=len, reverse=True)
    # "programmed" is American too, the past of "program", so "programme" takes a plural and nothing else.
    plurals = sorted({word for word in words if word.endswith("mme")})
    others = sorted({word for word in words if word and word not in plurals and not word.endswith(("ise", "yse", "yze"))},
                    key=len, reverse=True)
    parts = [rf"(?:{'|'.join(map(re.escape, verbs))}){VERB_ENDINGS}"] if verbs else []
    parts += [rf"(?:{'|'.join(map(re.escape, plurals))})s?"] if plurals else []
    parts += [rf"(?:{'|'.join(map(re.escape, others))}){ENDINGS}"] if others else []
    return re.compile(rf"\b(?:{'|'.join(parts)})\b", re.IGNORECASE)


BRITISH = _variety(tuple(british for british, _ in VARIANTS))
AMERICAN = _variety(tuple(american for _, american in VARIANTS))


def _spellings(text: str, pattern: re.Pattern[str]) -> Iterator[tuple[int, str]]:
    """Each word of one variety in a text, outside quotations, as (line, word). A capital inside a sentence marks a
    name ("Ministry of Defence", "Centre for Coastal Robotics"), which keeps its own spelling."""
    for line_no, line in enumerate(text.split("\n"), 1):
        plain = QUOTED.sub(lambda m: " " * len(m.group(0)), line)
        for match in pattern.finditer(plain):
            word = match.group(0)
            before = plain[:match.start()].rstrip()
            if word[0].isupper() and before and not before.endswith((".", "|", ":", "-", "#", "*", "(")):
                continue
            yield line_no, word


def check_spelling(drafts: list[tuple[str, str]]) -> Iterator[Result]:
    """Each word spelled in the variety of English the drafts otherwise don't use, counted over all of them: a British
    spelling in drafts written in American English, or the other way round. With as many of one as the other, or
    neither, nothing is said."""
    british = [(name, line, word) for name, text in drafts for line, word in _spellings(text, BRITISH)]
    american = [(name, line, word) for name, text in drafts for line, word in _spellings(text, AMERICAN)]
    if len(british) == len(american):
        return
    odd, usual, kind = (british, american, "British") if len(american) > len(british) else (american, british, "American")
    for name, line, word in odd:
        yield Result(name, line, "spelling", WARN, word,
                     f"{kind} spelling in drafts that otherwise spell the other way ({len(usual)} words to "
                     f"{len(odd)}): check whether a source's wording was copied, or make it match")


# ---------------------------------------------------------------- personal data

LOCAL_PATH = re.compile(r"\b[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/][^\s\\/`'\"<>|]+|(?<![\w.])/(?:Users|home)/[^\s/`'\"<>]+"
                        r"|\\\\[A-Za-z0-9._-]+\\[^\s\\]+", re.I)
EMAIL = re.compile(r"[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
HANDLE = re.compile(r"(?<![\w.@/\\])@[A-Za-z0-9_](?:[A-Za-z0-9_.-]{0,37}[A-Za-z0-9_])?\b")


def check_personal(name: str, text: str, given: Settings) -> Iterator[Result]:
    """Local paths that name an account, email addresses, account handles and the personal terms the settings list."""
    allowed = {entry.casefold() for entry in given.allow}
    for line_no, line in enumerate(text.split("\n"), 1):
        for pattern, verdict, what in ((LOCAL_PATH, FAIL, "a local path, which names an account on a computer"),
                                       (EMAIL, FAIL, "an email address"), (HANDLE, WARN, "an account handle")):
            for match in pattern.finditer(EMAIL.sub(lambda m: " " * len(m.group(0)), line) if pattern is HANDLE else line):
                if match.group(0).casefold() not in allowed:
                    yield Result(name, line_no, "personal data", verdict, match.group(0), what)
        for term in given.personal:
            for match in re.finditer(rf"(?<!\w){re.escape(term)}(?!\w)", line, re.I):
                yield Result(name, line_no, "personal data", FAIL, match.group(0), "a personal term: [proof] personal lists it")


# ---------------------------------------------------------------- running it

def proof(ws: Workspace, con: sqlite3.Connection) -> list[Result]:
    """Every result for the drafts, each check's pass included when it found nothing. Writes data/proof.csv. Raises
    ValueError for unusable settings."""
    given = settings(ws)
    accepted = dict(rules(ws).accepted)
    kept = records(ws)
    whole = [(path.name, read_draft(path)) for path in draft_files(ws)]
    # What the drafts say, without their reference lists or the sections that are records: what a citation, a
    # cross-reference, a sum or a pointer is looked for in. The reference lists are read from the whole drafts, and so
    # is personal data, which belongs nowhere.
    drafts = [(name, set_aside(text, kept)) for name, text in whole]
    # Read as a draft is, so a list exported as Markdown, with its addresses written annual\_report.htm, gives them plain.
    companions = [(path.name, read_draft(path)) for path in given.companions]
    lists = [(path.name, read_draft(path)) for path in given.references]
    entries = [entry for name, text in whole + companions for entry in entries_in(name, text, False)]
    entries += [entry for name, text in lists for entry in entries_in(name, text, True)]
    sources = {address(url) for (url,) in con.execute("SELECT DISTINCT url FROM sources")}
    results: list[Result] = []
    found: dict[str, list[Result]] = {check: [] for check in CHECKS}
    cited_results, cited = check_citations(drafts, entries, bool(entries))
    found["citations"] = cited_results
    if not entries and any(True for name, text in drafts for _ in citations_in(name, text)):
        found["citations"].append(Result(drafts[0][0], 0, "citations", WARN, "", "the drafts cite works, but no reference list was "
                                         "found: give one a References heading, or name it under [proof] references"))
    for entry in entries:
        if not cited[entry]:
            cited[entry] = list(mentioned(entry, drafts))
    found["references"] = list(check_references(entries, cited, sources, sec_companies(ws), accepted))
    found["references"] += list(check_named_authors(drafts, entries))
    found["year letters"] = list(check_year_letters(entries, cited))
    found["cited figures"] = list(check_cited_figures(dict(drafts), cited, ws, con, sources))
    found["dates"] = list(check_dates(dict(drafts), cited, ws, con))
    found["filings"] = list(check_filings(drafts, ws, con))
    where = targets(whole + companions)
    found["cross-references"] = list(check_cross_references(drafts, where))
    for name, text in [(name, record_parts(text, kept)) for name, text in whole] + companions:
        found["numbering"] += list(check_numbering(name, text))
    found["records"] = list(check_record_logs(whole, list(zip(given.companions, companions, strict=True)), given.record_logs, ws))
    found["exhibits"] = list(check_exhibits(drafts, targets(drafts + companions)))
    found["summary"], found["pointers"] = check_provenance(drafts)
    for name, text in drafts:
        found["sums"] += list(check_sums(name, text))
        found["tables"] += list(check_tables(name, text, given))
    found["spelling"] = list(check_spelling(drafts))
    for name, text in whole:
        found["personal data"] += list(check_personal(name, text, given))
    if given.workspace_sections:
        now, ran, notes = record.values(con), record.runs(con), record.digest(ws)
        found["workspace figures"] = [Result(name, f.line, "workspace figures", f.verdict, f.item, f.detail)
                                      for name, text in whole + companions
                                      for f in record.judge(text, given.workspace_sections, now, ran, notes)]
    for check in CHECKS:
        # In the order a reader meets them, file by file; findings at one place keep the order they were found in.
        results += sorted(found[check], key=lambda r: (r.file, r.line)) or [Result("", 0, check, PASS, "", "nothing found")]
    ws.data.mkdir(parents=True, exist_ok=True)
    with (ws.data / REPORT).open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["file", "line_no", "check", "verdict", "item", "detail"])
        writer.writerows((r.file, r.line, r.check, r.verdict, r.item, r.detail) for r in results)
    return results


def run(ws: Workspace, con: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Print each failure and warning, and a count for each check. Exits 1 when anything failed."""
    if not draft_files(ws):
        print(f"No drafts to proof: {drafts_folder(ws)} has no Markdown, Word or PDF files.", file=sys.stderr)
        return 0
    try:
        results = proof(ws, con)
    except ValueError as problem:
        print(problem, file=sys.stderr)
        return 1
    # A pass with a reason, such as a figure traced to the notes' working or an address the settings accept, is listed
    # with --all and counted otherwise, so what was let through is never silent.
    listed = bool(getattr(args, "all", False))
    for r in results:
        if r.verdict != PASS or (listed and r.item):
            print(f"  {r.verdict.upper()} {r.check} {r.file}:{r.line} {r.item[:90]!r}: {r.detail}")
    reasoned = 0
    for check in CHECKS:
        failed = sum(r.check == check and r.verdict == FAIL for r in results)
        warned = sum(r.check == check and r.verdict == WARN for r in results)
        passed = sum(r.check == check and r.verdict == PASS and bool(r.item) for r in results)
        reasoned += passed
        print(f"{check:<17} {failed} failed, {warned} warned" + (f", {passed} passed with a reason given" if passed else ""))
    if reasoned and not listed:
        print("--all lists the passes with a reason")
    print(f"wrote {ws.data / REPORT}")
    return 1 if any(r.verdict == FAIL for r in results) else 0
