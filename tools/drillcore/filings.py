"""Newer filings: whether the filings a note cites have been overtaken since.

`drillcore sec` loads each company's filing list and tagged facts. From those, `drillcore newer` warns of two things:

- **A newer periodic filing.** A note cites a periodic report (10-Q, 10-K, 20-F or 40-F, or an amendment to one) by
  an address in its EDGAR folder, and the company has filed another periodic report since. The note may want the newer
  figures, or may mean the older ones: it's a warning, never a failure.
- **A restatement.** A fact the notes take from a filing has a different value, for the same concept, unit and period,
  in a filing made later. The facts looked at are those tagged in a cited filing whose value a line citing that filing
  writes (at the scale written, or in thousands, millions or billions), and those `checks/xbrl_claims.csv` names. Both
  values and both filings are given, and the choice is left to the researcher.

Nothing is fetched here; it reads what `sources` and `sec` stored. It always exits 0.
"""
import argparse
import csv
import re
import sqlite3
import sys
from collections.abc import Iterator
from dataclasses import dataclass

from . import identity, sourcedb
from .workspace import Workspace

# The filing a cited address sits in: the company's number and the accession number without its dashes.
EDGAR_FOLDER = re.compile(r"https://www\.sec\.gov/Archives/edgar/data/(\d+)/(\d{18})/")
PERIODIC = ("10-Q", "10-K", "20-F", "40-F")
REPORT = "newer_filings.csv"
SCALES = (1.0, 1e3, 1e6, 1e9)


@dataclass(frozen=True)
class Notice:
    kind: str       # newer_filing | restated
    note: str
    line_no: int
    key: str
    detail: str


@dataclass(frozen=True)
class Filing:
    cik: int
    accession: str
    form: str
    filed: str


def periodic(form: str) -> bool:
    """Whether a form is a periodic report or an amendment to one."""
    return form.removesuffix("/A") in PERIODIC


def bare(accession: str) -> str:
    return accession.replace("-", "")


def described(filing: Filing) -> str:
    return f"the {filing.form} filed {filing.filed} ({filing.accession})"


def cited_filings(con: sqlite3.Connection) -> dict[Filing, list[tuple[str, int, str]]]:
    """Each filing the notes cite an address in, with every (note, line, key) that cites it."""
    known = {(cik, bare(accession)): Filing(cik, accession, form, filed) for cik, accession, form, filed in
             con.execute("SELECT cik, accession, form, filing_date FROM filings")}
    cited: dict[Filing, list[tuple[str, int, str]]] = {}
    for note, line_no, key, url in con.execute("SELECT note_file, line_no, source_key, url FROM sources ORDER BY id"):
        folder = EDGAR_FOLDER.match(url)
        filing = known.get((int(folder[1]), folder[2])) if folder else None
        if filing:
            place = (note, line_no or 0, key or "")
            if place not in cited.setdefault(filing, []):
                cited[filing].append(place)
    return cited


def newer_filings(con: sqlite3.Connection, cited: dict[Filing, list[tuple[str, int, str]]]) -> Iterator[Notice]:
    """A warning for each place a note cites a periodic report that a later one from the same company follows."""
    for filing, places in cited.items():
        if not periodic(filing.form):
            continue
        later = [Filing(filing.cik, accession, form, filed) for accession, form, filed in con.execute(
            "SELECT accession, form, filing_date FROM filings WHERE cik=? AND filing_date > ? ORDER BY filing_date",
            (filing.cik, filing.filed)) if periodic(form)]
        if not later:
            continue
        also = f", and {len(later) - 1} more after it" if len(later) > 1 else ""
        for note, line_no, key in places:
            yield Notice("newer_filing", note, line_no, key,
                          f"cites {described(filing)}; the company has since filed {described(later[0])}{also}")


def written_values(ws: Workspace, con: sqlite3.Connection, filing: Filing,
                   places: list[tuple[str, int, str]]) -> list[tuple[float, int]]:
    """The figures, as (value, decimal places), on the lines of the notes that cite a filing by its key."""
    keys = {(note, key) for note, _, key in places if key}
    values: list[tuple[float, int]] = []
    for line in sourcedb.note_lines(ws, con):
        if line.section == "notes" and any((line.note, key) in keys for key in line.keys):
            values += [(value, decimals) for _, value, decimals, _ in sourcedb.numbers_in(line.text)]
    return values


def written(value: float, figures: list[tuple[float, int]]) -> bool:
    """Whether a fact's value is a figure the notes write, at the scale written or in thousands, millions or billions."""
    return any(abs(value / scale - figure) <= 0.5 * 10 ** -decimals + 1e-9 for figure, decimals in figures for scale in SCALES)


def restatements(con: sqlite3.Connection, cik: int, concept: str, start: str | None, end: str,
                 since: str = "") -> Iterator[tuple[tuple[float, str, str, str], tuple[float, str, str, str], str]]:
    """Each later filing that gives a concept a different value for one period, as ((first value, form, filed,
    accession), (later value, form, filed, accession), unit). With `since`, the first is the value filed then."""
    period = "period_start=?" if start else "period_start IS NULL"
    facts = con.execute(
        f"SELECT unit, value, form, filed, accession FROM xbrl_facts WHERE cik=? AND concept=? AND period_end=? AND {period}"  # noqa: S608
        " ORDER BY unit, filed, accession", [cik, concept, end, *([start] if start else [])]).fetchall()
    by_unit: dict[str, list[tuple[float, str, str, str]]] = {}
    for unit, value, form, filed, accession in facts:
        if value is not None:
            by_unit.setdefault(unit, []).append((float(value), form, filed, accession))
    for unit, reported in by_unit.items():
        first = next((fact for fact in reported if fact[2] == since), None) if since else reported[0]
        if first is None:
            continue
        seen: set[float] = {first[0]}
        for fact in reported:
            if fact[2] > first[2] and fact[0] not in seen and abs(fact[0] - first[0]) > 1e-9 * max(1.0, abs(first[0])):
                seen.add(fact[0])
                yield first, fact, unit


def amount(value: float) -> str:
    """A tagged value as a reader writes it: 131,200,000, or 0.25."""
    return f"{value:,.0f}" if value == int(value) else f"{value:,}"


def period_of(start: str | None, end: str) -> str:
    return f"{start} to {end}" if start else f"at {end}"


def restated_from_citations(ws: Workspace, con: sqlite3.Connection,
                            cited: dict[Filing, list[tuple[str, int, str]]]) -> Iterator[Notice]:
    """A warning for each fact a cited filing tagged, at a value a line citing it writes, that a later filing restates."""
    for filing, places in cited.items():
        figures = written_values(ws, con, filing, places)
        if not figures:
            continue
        facts = con.execute("SELECT DISTINCT concept, unit, period_start, period_end, value FROM xbrl_facts"
                            " WHERE cik=? AND REPLACE(accession, '-', '')=?", (filing.cik, bare(filing.accession))).fetchall()
        for concept, unit, start, end, value in facts:
            if value is None or not written(float(value), figures):
                continue
            for first, later, fact_unit in restatements(con, filing.cik, concept, start, end, since=filing.filed):
                if fact_unit != unit or first[0] != value:
                    continue
                note, line_no, key = places[0]
                yield Notice("restated", note, line_no, key,
                              f"{concept} for {period_of(start, end)} ({unit}) is {amount(first[0])} in {described(filing)}, and "
                              f"{amount(later[0])} in the {later[1]} filed {later[2]} ({later[3]})")


def restated_claims(ws: Workspace, con: sqlite3.Connection) -> Iterator[Notice]:
    """A warning for each concept and period in checks/xbrl_claims.csv that a later filing gives another value."""
    path = ws.root / "checks" / "xbrl_claims.csv"
    if not path.is_file():
        return
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = [row for row in csv.DictReader(source) if row.get("claim_id") and not row["claim_id"].startswith("#")]
    for row in rows:
        try:
            cik = int(row.get("cik") or "")
        except ValueError:
            continue  # `claims` says what's wrong with the row.
        start, end = (row.get("period_start") or "").strip() or None, (row.get("period_end") or "").strip()
        for concept in (c.strip() for c in (row.get("concepts") or "").split("|") if c.strip()):
            for first, later, unit in restatements(con, cik, concept, start, end):
                yield Notice("restated", row.get("note_file") or "", 0, row["claim_id"],
                              f"{concept} for {period_of(start, end)} ({unit}) is {amount(first[0])} in the {first[1]} filed "
                              f"{first[2]} ({first[3]}), and {amount(later[0])} in the {later[1]} filed {later[2]} ({later[3]})")


def check(ws: Workspace, con: sqlite3.Connection) -> list[Notice]:
    """Every newer-filing and restatement warning, and data/newer_filings.csv with each."""
    cited = cited_filings(con)
    warnings = [*newer_filings(con, cited), *restated_from_citations(ws, con, cited), *restated_claims(ws, con)]
    ws.data.mkdir(parents=True, exist_ok=True)
    with (ws.data / REPORT).open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["kind", "note_file", "line_no", "source_key_or_claim", "detail"])
        writer.writerows([w.kind, w.note, w.line_no, w.key, w.detail] for w in warnings)
    return warnings


def run(ws: Workspace, con: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Print each warning and a count. Always exits 0: the older figure may be the one the note means."""
    if not con.execute("SELECT 1 FROM filings LIMIT 1").fetchone():
        print(f"No SEC filing lists are loaded. Run `{identity.SLUG} sources` and `{identity.SLUG} sec` first.", file=sys.stderr)
    warnings = check(ws, con)
    for w in warnings:
        where = f"{w.note}:{w.line_no}" if w.line_no else (w.note or "-")
        print(f"{w.kind.replace('_', ' '):<13} {where} [{w.key or '-'}] {w.detail}")
    newer = sum(w.kind == "newer_filing" for w in warnings)
    print(f"{newer} newer filing warning(s), {len(warnings) - newer} restatement warning(s)")
    print(f"wrote {ws.data / REPORT}")
    return 0
