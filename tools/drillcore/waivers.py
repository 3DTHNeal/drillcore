"""Waivers: a finding a researcher has looked at and accepted, with the reason, so later runs don't raise it again.

Every check has findings a person has judged and accepted: a source that rounds differently, a figure confirmed by
phone, a quotation of a translation. Without a way to say so, the notes must change, or `check` fails forever and the
exit code stops meaning anything. A waiver is a row of `checks/waivers.csv`, written by hand:

    check,note_file,line_no,item,reason,accepted_by,accepted_on
    numbers,01_northbridge.md,,$999.9M,Confirmed by phone with the company's press office,J. Doe,2026-11-11

- `check` is the check that raised it: citations, quotations, arithmetic, numbers or sections. `quotes` and `figures`
  are read as quotations and numbers, so a waiver written for `drillcore figures` holds for `check` as well.
- `note_file` and `item` say which finding: the note, and what was judged as the report writes it (the key, the
  quotation, the working, the figure). Spaces and capitals don't count, and for a figure only its digits do, so
  `$999.9M` waives the 999.9 that `figures` reports. `line_no` narrows it to one line and may be left blank, since lines
  move as a note is edited.
- `reason`, `accepted_by` and `accepted_on` (a date, as 2026-11-11) say why, who and when. Each is required.

A waived finding is reported as waived, not failed, and doesn't make a command exit 1. A waiver holds only for what it
was judged against: the first run that finds its finding records the hash of the line in the notes and of the text of
the sources that line cites. When either changes, the waiver lapses, and the finding is reported as it would be with
no waiver, saying what changed, so nothing is accepted against new evidence without a person looking again. To accept
it again, change `accepted_on`: a waiver with a new date is a new waiver. A waiver of a section (`sections`, with the
heading as its item) is held to every line of the section, not its heading alone, since what's under a heading is what
changes. A waiver that matches nothing is a warning,
as a Sources entry nothing cites is: the finding may have been fixed, and the waiver can go.

The file is data. It's read, never run, and nothing in it changes the notes.
"""
import csv
import hashlib
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .sourcedb import keys_by_note, note_files, note_lines, now
from .workspace import Workspace, WorkspaceError

FILE = Path("checks") / "waivers.csv"
COLUMNS = ("check", "note_file", "line_no", "item", "reason", "accepted_by", "accepted_on")
REQUIRED = tuple(column for column in COLUMNS if column != "line_no")
CHECKS = ("citations", "quotations", "arithmetic", "numbers", "sections")
# The standalone commands' own names for two of the checks.
ALIASES = {"quotes": "quotations", "figures": "numbers"}
FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?")

SCHEMA = """
CREATE TABLE IF NOT EXISTS waiver_pins (
    waiver TEXT NOT NULL,          -- the waiver's identity: its check, note, line, item and date
    line_sha TEXT NOT NULL,        -- the hash of the note's line when the waiver was first applied to it
    source_sha TEXT NOT NULL,      -- the hash of the text of the sources that line cites, then
    pinned_at TEXT NOT NULL,
    PRIMARY KEY (waiver, line_sha)
);
"""


@dataclass(frozen=True)
class Waiver:
    """One row of the waivers file. `row` is its line in the file, for saying where it is."""
    row: int
    check: str
    note: str
    line_no: int | None
    item: str
    reason: str
    accepted_by: str
    accepted_on: str

    @property
    def ident(self) -> str:
        """What makes this waiver itself. The reason and who accepted it can be reworded without a new waiver; a new
        date, a different line or a different item is one."""
        parts = (self.check, self.note, str(self.line_no or ""), squeeze(self.item), self.accepted_on)
        return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:20]

    def said(self) -> str:
        """The waiver as a report gives it: why, who and when."""
        return f"{self.reason} (accepted by {self.accepted_by} on {self.accepted_on})"

    def where(self) -> str:
        return f"{FILE.as_posix()}:{self.row}"


@dataclass(frozen=True)
class Decision:
    """What a waiver does for one finding: waives it, or has lapsed, saying what changed."""
    waiver: Waiver
    lapsed: str = ""


def squeeze(text: str) -> str:
    return " ".join(text.split()).casefold()


def figure_digits(text: str) -> str:
    """A figure's digits without its thousands commas, as 999.9 for "$999.9M", or "" when it has none."""
    found = FIGURE.search(text)
    return found.group(0).replace(",", "") if found else ""


def same_item(check: str, waived: str, found: str) -> bool:
    """Whether a waiver's item names what a check found: the same digits for a figure, the same words otherwise."""
    if check == "numbers":
        digits = figure_digits(waived)
        return bool(digits) and digits == figure_digits(found)
    return squeeze(waived) == squeeze(found)


def read(ws: Workspace) -> list[Waiver]:
    """The workspace's waivers, or [] when it has no waivers file. Raises WorkspaceError, naming the line, for a row
    that can't be used."""
    path = ws.root / FILE
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        missing = [column for column in REQUIRED if column not in (reader.fieldnames or [])]
        if missing:
            raise WorkspaceError(f"{path} has no {', '.join(missing)} column. Its first line must name: {', '.join(COLUMNS)}.")
        rows = [(reader.line_num, row) for row in reader]
    found: list[Waiver] = []
    for line, row in rows:
        values = {column: (row.get(column) or "").strip() for column in COLUMNS}
        if not any(values.values()) or values["check"].startswith("#"):
            continue
        check = ALIASES.get(values["check"].lower(), values["check"].lower())
        where = f"{path}:{line}"
        if check not in CHECKS:
            raise WorkspaceError(f"{where}: {values['check']!r} isn't a check. Name one of {', '.join(CHECKS)}.")
        blank = [column for column in REQUIRED if not values[column]]
        if blank:
            raise WorkspaceError(f"{where}: a waiver needs every one of {', '.join(REQUIRED)}; this one has no {', '.join(blank)}.")
        try:
            date.fromisoformat(values["accepted_on"])
        except ValueError:
            raise WorkspaceError(f"{where}: accepted_on must be a date written as 2026-11-11, not {values['accepted_on']!r}.") from None
        if values["line_no"] and not values["line_no"].isdigit():
            raise WorkspaceError(f"{where}: line_no must be a line number, or blank for any line; it's {values['line_no']!r}.")
        found.append(Waiver(line, check, values["note_file"], int(values["line_no"]) if values["line_no"] else None, values["item"],
                            values["reason"], values["accepted_by"], values["accepted_on"]))
    return found


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Ledger:
    """The workspace's waivers, applied to findings one at a time. It remembers which waivers were used, so the ones
    that matched nothing can be named, and records in the database what each waiver was first judged against."""
    ws: Workspace
    con: sqlite3.Connection
    waivers: list[Waiver] = field(default_factory=list)
    used: set[str] = field(default_factory=set)
    # Waivers first applied in this run: one that waives the same item on two lines is pinned to both.
    pinned_now: set[str] = field(default_factory=set)
    _lines: dict[str, list[str]] = field(default_factory=dict)
    _keys: dict[tuple[str, int], tuple[str, ...]] = field(default_factory=dict)
    _urls: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.waivers = self.waivers or read(self.ws)
        if not self.waivers:
            return
        self.con.executescript(SCHEMA)
        paths = note_files(self.ws)
        self._lines = {path.name: path.read_text(encoding="utf-8").splitlines() for path in paths}
        self._keys = {(line.note, line.line_no): line.keys for line in note_lines(self.ws, self.con)}
        self._urls = keys_by_note(self.con, [path.name for path in paths], self.ws.config().get("notes", {}).get("borrows", {}))

    def line_sha(self, note: str, line_no: int) -> str:
        lines = self._lines.get(note, [])
        return _sha(lines[line_no - 1].strip() if 0 < line_no <= len(lines) else "")

    def source_sha(self, note: str, line_no: int, keys: tuple[str, ...] = ()) -> str:
        """The hash of the text of every source the finding cites, in the order of their addresses: the keys the check
        read for it, such as a blockquote's from its attribution, or failing those, the keys its line cites."""
        keys = tuple(keys) or self._keys.get((note, line_no), ())
        urls = sorted({url for key in keys for url in self._urls.get(note, {}).get(key, [])})
        texts = []
        for url in urls:
            row = self.con.execute("SELECT text FROM documents WHERE url=?", (url,)).fetchone()
            texts.append(f"{url}\x1f{row[0] if row and row[0] else ''}")
        return _sha("\x1e".join(texts))

    def decide(self, check: str, note: str, line_no: int, item: str, keys: tuple[str, ...] = (),
               text: str | None = None) -> Decision | None:
        """What the waivers say about one finding: None when none matches it, else the waiver that does, and whether
        it has lapsed. A waiver applied for the first time is pinned to the line and its sources as they are now.
        `keys` are the source keys the check read for the finding; without them, those its line cites. `text`, when
        given, is what the finding is held to in place of its line, such as every line of a section."""
        check = ALIASES.get(check, check)
        matching = [w for w in self.waivers if w.check == check and w.note == note and w.line_no in (None, line_no)
                    and same_item(check, w.item, item)]
        if not matching:
            return None
        line_sha = _sha(text) if text is not None else self.line_sha(note, line_no)
        source_sha = self.source_sha(note, line_no, keys)
        lapsed: Decision | None = None
        for waiver in matching:
            self.used.add(waiver.ident)
            pins = dict(self.con.execute("SELECT line_sha, source_sha FROM waiver_pins WHERE waiver=?", (waiver.ident,)).fetchall())
            first = self.con.execute("SELECT MIN(pinned_at) FROM waiver_pins WHERE waiver=?", (waiver.ident,)).fetchone()[0]
            if line_sha not in pins and (not pins or waiver.ident in self.pinned_now):
                self.con.execute("INSERT INTO waiver_pins VALUES (?,?,?,?)", (waiver.ident, line_sha, source_sha, now()))
                self.con.commit()
                self.pinned_now.add(waiver.ident)
                return Decision(waiver)
            if line_sha not in pins:
                what = "the section" if text is not None else "the line"
                lapsed = lapsed or Decision(waiver, f"{what} in the notes has changed since the waiver was first applied on {first[:10]}")
            elif pins[line_sha] != source_sha:
                lapsed = lapsed or Decision(waiver, f"the text of a source the line cites has changed since the waiver was first "
                                                    f"applied on {first[:10]}")
            else:
                return Decision(waiver)
        return lapsed

    def unused(self, checks: tuple[str, ...] = CHECKS) -> list[Waiver]:
        """The waivers for these checks that matched no finding this run."""
        return [w for w in self.waivers if w.check in checks and w.ident not in self.used]


def unused_message(waiver: Waiver) -> str:
    where = f"{waiver.note}:{waiver.line_no}" if waiver.line_no else waiver.note
    return (f"{waiver.where()} waives {waiver.check} {waiver.item!r} in {where}, which this run didn't find. If it's been "
            "fixed, the waiver can go.")


def lapsed_message(decision: Decision) -> str:
    return f"a waiver lapsed ({decision.waiver.where()}): {decision.lapsed}. Look again, and to accept it again change its accepted_on."
