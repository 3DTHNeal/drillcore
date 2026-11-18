"""What changed since the last run: on a long report, re-reading every finding after each edit wastes time.

Each run of `check`, `figures` and `assay` keeps its findings in the database. The next run compares its own with
them and says which are new, which are fixed (the last run had them and this one doesn't) and which are unchanged, and
lists the new ones first. A finding is known by what it is, never by its line number, since lines move whenever a note
is edited: by its check, its note or draft, its status and what was judged. The same finding twice in one note counts
twice. A finding a waiver now accepts isn't fixed, so it's left out of the fixed ones; the command lists it as waived.

A command's `--all` lists every finding as it did before this existed. Without it the unchanged ones are counted and
not listed, unless this is the command's first run, when every finding is new.

Only the last few runs of each command are kept: the comparison needs one.
"""
import sqlite3
from collections import Counter
from collections.abc import Callable, Collection
from dataclasses import dataclass, field

from .sourcedb import now

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    command TEXT NOT NULL,          -- check, figures, or assay with the draft it judged
    ran_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_findings (
    run INTEGER NOT NULL REFERENCES runs(id),
    fingerprint TEXT NOT NULL,      -- what the finding is, without where it is
    shown TEXT NOT NULL             -- the finding as a report lists it
);
CREATE INDEX IF NOT EXISTS ix_run_findings ON run_findings(run);
"""
KEEP = 10


@dataclass(frozen=True)
class Finding:
    """One finding as a run keeps it: what it is (`fingerprint`, which leaves out the line number) and how a report
    lists it."""
    fingerprint: str
    shown: str


@dataclass
class Changes:
    """How one run's findings compare with the last run of the same command. `new` and `unchanged` are positions in
    the findings given; `fixed` are the last run's findings this one doesn't have, as that run listed them."""
    since: str | None
    new: list[int] = field(default_factory=list)
    unchanged: list[int] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)

    @property
    def first(self) -> bool:
        return self.since is None

    def summary(self) -> str:
        """One line: how many are new, unchanged and fixed since when."""
        if self.first:
            return "first run recorded; the next one will say what changed"
        return f"{len(self.new)} new, {len(self.unchanged)} unchanged, {len(self.fixed)} fixed since the last run ({self.since})"


def fingerprint(*parts: object) -> str:
    """A finding's identity from its parts, such as its check, note, status and item. Blanks don't count."""
    return "\x1f".join(" ".join(str(part).split()) for part in parts)


def compare(con: sqlite3.Connection, command: str, findings: list[Finding], waived: Collection[str] = ()) -> Changes:
    """Compare this run's findings with the last run of the same command, then record this run in its place.
    `waived` are the fingerprints of findings a waiver accepts this run: one the last run had isn't fixed, only
    accepted, so it isn't counted as fixed."""
    con.executescript(SCHEMA)
    last = con.execute("SELECT id, ran_at FROM runs WHERE command=? ORDER BY id DESC LIMIT 1", (command,)).fetchone()
    changes = Changes(last[1] if last else None)
    before: Counter[str] = Counter()
    shown: dict[str, str] = {}
    if last:
        for print_, said in con.execute("SELECT fingerprint, shown FROM run_findings WHERE run=?", (last[0],)):
            before[print_] += 1
            shown.setdefault(print_, said)
    remaining = before.copy()
    for at, finding in enumerate(findings):
        if remaining[finding.fingerprint] > 0:
            remaining[finding.fingerprint] -= 1
            changes.unchanged.append(at)
        else:
            changes.new.append(at)
    for print_ in waived:
        if remaining[print_] > 0:
            remaining[print_] -= 1
    changes.fixed = [shown[print_] for print_, count in remaining.items() for _ in range(count)]
    run = con.execute("INSERT INTO runs(command, ran_at) VALUES (?,?)", (command, now())).lastrowid
    con.executemany("INSERT INTO run_findings VALUES (?,?,?)", [(run, f.fingerprint, f.shown) for f in findings])
    old = [row[0] for row in con.execute("SELECT id FROM runs WHERE command=? ORDER BY id DESC LIMIT -1 OFFSET ?", (command, KEEP))]
    con.executemany("DELETE FROM run_findings WHERE run=?", [(id_,) for id_ in old])
    con.executemany("DELETE FROM runs WHERE id=?", [(id_,) for id_ in old])
    con.commit()
    return changes


def report(changes: Changes, findings: list[Finding], show_all: bool, say: Callable[[str], None] = print) -> None:
    """Print a run's findings: the new ones first, then the unchanged ones when `show_all` or on a first run (else only
    their count), then the fixed ones."""
    if changes.first:
        for finding in findings:
            say(finding.shown)
        return
    if changes.new:
        say(f"New since the last run ({len(changes.new)}):")
        for at in changes.new:
            say(findings[at].shown)
    if changes.unchanged:
        if show_all:
            say(f"Unchanged since the last run ({len(changes.unchanged)}):")
            for at in changes.unchanged:
                say(findings[at].shown)
        else:
            say(f"{len(changes.unchanged)} unchanged since the last run, not listed; --all lists them.")
    if changes.fixed:
        say(f"Fixed since the last run ({len(changes.fixed)}):")
        for shown in changes.fixed:
            say(shown)
