"""Sources that disagree with each other: for a figure a note takes from one source, what the workspace's other sources
state for the same label and period.

A press release and the filing, or two news reports, often give different figures for the same thing, and the check
of a note against the source it cites passes as long as that one source holds the figure. This reads each statement
a note makes (`statements`: a figure in a table or a plain clause, with a label and a period that can be read) on a
line that cites a source, then each table in every other source the workspace holds, and reports each that states a
different figure for the same label and period, beyond the rounding either is written to.

A conflict names both sources and leaves the choice to the researcher. Nothing here says which is right.
"""
import argparse
import csv
import sqlite3
from dataclasses import dataclass

from . import sourcedb, statements
from .statements import Statement
from .workspace import Workspace

REPORT = "conflicts.csv"


@dataclass(frozen=True)
class Conflict:
    """A note's statement, the sources its line cites, and another source's statement of the same measure that
    doesn't agree with it."""
    said: Statement
    keys: tuple[str, ...]
    cited: tuple[str, ...]
    other: Statement


def check(ws: Workspace, con: sqlite3.Connection) -> list[Conflict]:
    """Every statement in the notes that another source contradicts. Writes data/conflicts.csv."""
    sourcedb.record_sources(ws, con)
    paths = sourcedb.note_files(ws)
    usable = sourcedb.keys_by_note(con, [path.name for path in paths], ws.config().get("notes", {}).get("borrows", {}))
    keys = {(line.note, line.line_no): line.keys for line in sourcedb.note_lines(ws, con) if line.section == "notes"}
    held: dict[tuple[frozenset[str], int | None, int | None, str], list[Statement]] = {}
    for url, text in con.execute("SELECT url, text FROM documents WHERE text IS NOT NULL ORDER BY url"):
        for stated in statements.table_statements(url, text, markdown=False):
            held.setdefault(stated.measure, []).append(stated)
    found: list[Conflict] = []
    for path in paths:
        for said in statements.written_statements(path.name, path.read_text(encoding="utf-8")):
            cited_keys = keys.get((path.name, said.line_no), ())
            cited = tuple(dict.fromkeys(url for key in cited_keys for url in usable[path.name].get(key, [])))
            if not cited:
                continue
            seen: set[str] = set()
            for other in held.get(said.measure, []):
                if other.where in cited or other.where in seen or not statements.comparable(said, other):
                    continue
                if not statements.agree(said, other):
                    seen.add(other.where)
                    found.append(Conflict(said, cited_keys, cited, other))
    ws.data.mkdir(parents=True, exist_ok=True)
    with (ws.data / REPORT).open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["note_file", "line_no", "label", "period", "figure", "source_keys", "cited", "other_source",
                         "other_figure", "other_label", "other_row"])
        writer.writerows([c.said.where, c.said.line_no, c.said.label, c.said.period.shown(), c.said.written, ",".join(c.keys),
                          " ".join(c.cited), c.other.where, c.other.written, c.other.label, c.other.text[:600]] for c in found)
    return found


def run(ws: Workspace, con: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Print each figure another source states differently, with both sources. Exits 1 when there's one."""
    found = check(ws, con)
    for conflict in found:
        said, other = conflict.said, conflict.other
        print(f"{said.where}:{said.line_no} {said.label!r} {said.period.shown()}: {said.written} "
              f"[{','.join(conflict.keys)}] from {sourcedb.shown(' '.join(conflict.cited))}")
        # The other source's words are printed as text and nothing else.
        print(f"  {sourcedb.shown(other.where)} states {sourcedb.shown(other.written)} in "
              f"{sourcedb.shown(other.text)[:120]!r}")
    print(f"{len(found)} figure(s) another source states differently")
    if found:
        print("Which is right is for you to decide. Each conflict names both sources.")
    print(f"wrote {ws.data / REPORT}")
    return 1 if found else 0
