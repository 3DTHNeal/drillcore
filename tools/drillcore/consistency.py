"""Internal consistency: the same measure stated differently in two places.

A report states the same figure many times, in a table, in prose, in a summary and in a draft, and the statements
drift. This reads every statement the notes and drafts make (`statements`: a figure in a table or a plain clause,
with a label and a period that can be read), groups those of the same measure, by label, period and whether it's a
percentage, and reports each pair that disagree beyond the rounding they're written to, with where each is.
"""
import argparse
import csv
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from . import drafts, overlap, sourcedb, statements
from .statements import Statement
from .workspace import Workspace

REPORT = "consistency.csv"


@dataclass(frozen=True)
class Disagreement:
    first: Statement
    second: Statement


def place(ws: Workspace, path: Path) -> str:
    """Where a note or draft is, as its folder and name from the workspace's root."""
    try:
        return path.relative_to(ws.root).as_posix()
    except ValueError:
        return path.name


def entities(ws: Workspace) -> tuple[str, ...]:
    """The companies and other entities whose figures the notes and drafts give, as prose names them: each company the
    settings load SEC facts for, by its short name, and any `[consistency] entities` lists. A figure is compared only
    with figures of the same entity, where the context of each names one."""
    config = ws.config()
    companies = config.get("sec", {}).get("company", [])
    named = [statements.short_name(str(company.get("name", ""))) for company in companies if isinstance(company, dict)]
    extra = config.get("consistency", {}).get("entities", [])
    if not isinstance(extra, list) or not all(isinstance(name, str) and name.strip() for name in extra):
        raise ValueError(f"[consistency] entities in {ws.config_path} must be a list of names, none of them blank.")
    return tuple(dict.fromkeys(name for name in [*named, *extra] if name))


def check(ws: Workspace) -> list[Disagreement]:
    """Every pair of statements in the notes and drafts that give one measure different figures. Writes
    data/consistency.csv."""
    stated: dict[tuple[frozenset[str], int | None, int | None, str, bool], list[Statement]] = {}
    known = entities(ws)
    texts = [(path, path.read_text(encoding="utf-8-sig")) for path in sourcedb.note_files(ws)]
    texts += [(path, drafts.read_draft(path)) for path in overlap.draft_files(ws)]
    for path, text in texts:
        for one in statements.written_statements(place(ws, path), text, known):
            stated.setdefault((*one.measure, one.percent), []).append(one)
    found: list[Disagreement] = []
    for group in stated.values():
        for at, first in enumerate(group):
            for second in group[at + 1:]:
                if statements.comparable(first, second) and not statements.agree(first, second):
                    found.append(Disagreement(first, second))
    ws.data.mkdir(parents=True, exist_ok=True)
    with (ws.data / REPORT).open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["label", "period", "file", "line_no", "figure", "other_file", "other_line_no", "other_figure"])
        writer.writerows([d.first.label, d.first.period.shown(), d.first.where, d.first.line_no, d.first.written,
                          d.second.where, d.second.line_no, d.second.written] for d in found)
    return found


def run(ws: Workspace, con: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Print each pair of statements that disagree. Exits 1 when there's one, or when a setting or a draft can't be
    read."""
    try:
        found = check(ws)
    except ValueError as problem:
        print(problem, file=sys.stderr)
        return 1
    for pair in found:
        first, second = pair.first, pair.second
        print(f"{first.label!r} {first.period.shown()}: {first.written} at {first.where}:{first.line_no}, "
              f"{second.written} at {second.where}:{second.line_no}")
    print(f"{len(found)} measure(s) stated differently in two places")
    print(f"wrote {ws.data / REPORT}")
    return 1 if found else 0
