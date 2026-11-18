"""The citations check: every source key a note cites has an entry in a Sources list, every entry gives an address,
and every address was fetched, or had its text gathered by hand.

A key counts as cited wherever the note's body writes it: in a row, a bullet, a heading or the prose that leads into a
table, the places `check_figures` reads to decide which source a row cites. Web addresses aren't read for keys. A note
may also cite the keys of the one note its workspace says it borrows from, under `[notes.borrows]`, unless it defines
the same key itself, and a line can name another note's list outright: `(file 04 sources S41, S44)` cites S41 and S44
from the note whose file name starts with 04.

Not every capital letter and number is a key: "Q3" is a quarter, "R18" a filing's note page and "F370" a printer. A
word counts as a key only when its letters are those of a key the note can use, from its own Sources list or the one it
borrows from, or are "S", the letter the usual `- **S1.**` uses. A note with no Sources list to use can only be citing
another note's keys, so for it the letters of every key the workspace's notes define count.

`drillcore citations` reports every problem here. `drillcore check` reports the same, but holds a source that hasn't
been fetched, or whose fetch failed or gave no text, as not judged rather than failed: there, a citation stands or
falls on whether its key has an address, and whether the address's text is in hand is the fetch's business.
"""
import argparse
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from . import identity, sourcedb, waivers
from .workspace import Workspace

Severity = Literal["error", "warning"]
LETTERS = re.compile(r"[A-Z]+")
USUAL_LETTERS = "S"
# Another note's list, named outright: "file 04 sources S41, S44" or "file 04 source S41".
ELSEWHERE = re.compile(r"\bfile (\d{2}) sources? ((?:[A-Z]{1,2}\d{1,3}[a-z]?(?:,\s*|\s+and\s+)?)+)")


@dataclass(frozen=True)
class Finding:
    """One thing wrong with a note's citations. `line` is 0 when it's about the note as a whole, and `key` is the
    source key it's about, if any."""
    note: str
    line: int
    severity: Severity
    kind: str  # no_entry, no_url, unused, not_fetched, fetch_failed, no_text, no_lender
    message: str
    key: str = ""


@dataclass(frozen=True)
class Citation:
    """One source key a line cites, and what it comes to: "resolves" when the list it's cited from gives it an address,
    "no_url" when that list names it without one, and "no_entry" when no list the line can use names it."""
    note: str
    line: int
    key: str
    status: str
    detail: str
    text: str


def entries(path: Path) -> list[tuple[int, str]]:
    """A note's Sources entries, as (line number, key): each line written `- **S1.** ...`."""
    found: list[tuple[int, str]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        listed = sourcedb.KEY_LINE.match(line)
        if listed:
            found.append((line_no, listed.group(1)))
    return found


def letters(key: str) -> str:
    match = LETTERS.match(key)
    return match.group(0) if match else ""


def json_advice(ws: Workspace, url: str) -> str:
    """What to do about a JSON source with no text. `fetch` reads a listed copy it already holds, without fetching."""
    if url in sourcedb.json_addresses(ws):
        return (f"It's listed under {sourcedb.READ_JSON} in {ws.config_path.name}, but no text is held from it: run "
                f"`{identity.SLUG} fetch`, and if that changes nothing, the copy isn't JSON that can be read.")
    return (f"JSON is kept but not read as text, so nothing is checked against it. If the notes take figures from this very file, "
            f"list its address under {sourcedb.READ_JSON} in {ws.config_path.name} and run `{identity.SLUG} fetch`, which reads "
            f"the copy kept. Figures a data service serves from other files stay with `{identity.SLUG} claims`.")


def url_problem(ws: Workspace, con: sqlite3.Connection, url: str) -> tuple[Severity, str, str] | None:
    """What stands between a cited URL and its text, as (severity, kind, message), or None when its text is stored,
    whether fetched or gathered by hand."""
    if con.execute("SELECT 1 FROM documents WHERE url=? AND text_chars > 0", (url,)).fetchone():
        return None
    fetched = con.execute("SELECT http_status, error, raw_path FROM fetches WHERE url=?", (url,)).fetchone()
    is_json = bool(fetched and fetched[2] and fetched[2].endswith(".json"))
    if url.startswith(sourcedb.LOCAL):
        if fetched is None:
            return "error", "not_fetched", f"{url} is a local file that hasn't been imported. Run `{identity.SLUG} import-file PATH --key KEY`."
        if is_json:
            return "warning", "no_text", f"{url} was imported, and is JSON. {json_advice(ws, url)}"
        return "warning", "no_text", f"{url} was imported, but no text was read from it, so nothing can be checked against it."
    if fetched is None:
        return "error", "not_fetched", f"{url} hasn't been fetched. Run `{identity.SLUG} fetch`."
    status, error, _ = fetched
    if status == 200 and not error:
        if is_json:
            return "warning", "no_text", f"{url} was fetched, and is JSON. {json_advice(ws, url)}"
        return "warning", "no_text", f"{url} was fetched, but no text was read from it, so nothing can be checked against it."
    return ("error", "fetch_failed", f"{url} failed when last fetched ({error or f'HTTP {status}'}). If the site refuses, "
            f"gather the text by hand and run `{identity.SLUG} import-text`.")


def examine(ws: Workspace, con: sqlite3.Connection) -> tuple[list[Citation], list[Finding]]:
    """Every citation in the workspace's notes with what it resolves to, and every problem, by note and line. Reads
    the sources table as `sources` last recorded it; `check` records it afresh first.

    Errors: a cited key no Sources list defines, an entry with no URL, a borrowed note that isn't there, and a cited
    URL never fetched or whose last fetch failed. Warnings: an entry nothing cites, and a page fetched without any text
    read from it."""
    paths = sourcedb.note_files(ws)
    names = [path.name for path in paths]
    borrows: dict[str, str] = ws.config().get("notes", {}).get("borrows", {})
    listed = {path.name: entries(path) for path in paths}
    defined = {name: {key for _, key in found} for name, found in listed.items()}
    addresses = sourcedb.keys_by_note(con, names, borrows)
    by_number = {name.split("_", 1)[0]: name for name in names}
    every_letter = {letters(key) for keys in defined.values() for key in keys}
    cited: dict[str, set[str]] = {name: set() for name in names}
    # Keys another note cites from this one by naming it: "file 01 sources S2".
    named_from: dict[str, set[str]] = {name: set() for name in names}
    found: list[Citation] = []
    findings: list[Finding] = []

    def add(note: str, line: int, severity: Severity, kind: str, message: str, key: str = "") -> None:
        findings.append(Finding(note, line, severity, kind, message, key))

    for path in paths:
        name = path.name
        lender = borrows.get(name, "")
        if lender and lender not in defined:
            add(name, 0, "error", "no_lender", f"The workspace says this note borrows source keys from {lender}, which isn't a note here.")
        usable = defined[name] | defined.get(lender, set())
        families = {USUAL_LETTERS} | ({letters(key) for key in usable} if usable else every_letter)
        for line_no, row in sourcedb.note_body(path):
            text = sourcedb.URL.sub(" ", row)
            for elsewhere in ELSEWHERE.finditer(text):
                other = by_number.get(elsewhere.group(1), "")
                there = addresses.get(other, {})
                for key in sourcedb.KEY_TOKEN.findall(elsewhere.group(2)):
                    if other:
                        named_from[other].add(key)
                    if key in there:
                        found.append(Citation(name, line_no, key, "resolves", f"{len(there[key])} address(es) in {other}", row))
                    else:
                        found.append(Citation(name, line_no, key, "no_entry", f"{other or 'that file'} gives no address for it", row))
                        add(name, line_no, "error", "no_entry",
                            f"{key} is cited from {other or f'file {elsewhere.group(1)}'}, which gives no address for it.", key)
                text = text.replace(elsewhere.group(0), " ")
            for key in dict.fromkeys(sourcedb.KEY_TOKEN.findall(text)):
                if key in addresses[name]:
                    found.append(Citation(name, line_no, key, "resolves", f"{len(addresses[name][key])} address(es)", row))
                elif key in usable:
                    found.append(Citation(name, line_no, key, "no_url", "the Sources list names it without an address", row))
                elif letters(key) in families:
                    found.append(Citation(name, line_no, key, "no_entry", "no Sources list this note can use names it", row))
                    elsewhere_too = sorted(other for other in defined if other != name and key in defined[other])
                    hint = (f" {', '.join(elsewhere_too)} defines it; if this note means that one, say so under [notes.borrows]."
                            if elsewhere_too else "")
                    add(name, line_no, "error", "no_entry", f"{key} is cited, but no Sources list this note can use defines it.{hint}", key)
                else:
                    continue
                cited[name].add(key)

    for path in paths:
        name = path.name
        with_url = {(key, line) for key, line in con.execute(
            "SELECT source_key, line_no FROM sources WHERE note_file=? AND origin='cited' AND source_key IS NOT NULL", (name,))}
        # A local file imported under a key stands in for an address its entry doesn't write.
        imported = {key for (key,) in con.execute(
            "SELECT source_key FROM sources WHERE note_file=? AND origin='imported' AND source_key IS NOT NULL", (name,))}
        borrowers = [other for other, source in borrows.items() if source == name and other in cited]
        for line, key in listed[name]:
            if (key, line) not in with_url and key not in imported:
                add(name, line, "error", "no_url", f"The entry for {key} gives no URL.", key)
            if key not in cited[name] and key not in named_from[name] and not any(
                    key in cited[other] and key not in defined[other] for other in borrowers):
                add(name, line, "warning", "unused", f"Nothing cites {key}.", key)

        for url, line, key in con.execute(
                "SELECT url, line_no, source_key FROM sources WHERE note_file=? AND origin IN ('cited', 'r_page')"
                " AND source_key IS NOT NULL ORDER BY id", (name,)).fetchall():
            problem = url_problem(ws, con, url)
            if problem:
                add(name, line, *problem, key=key)
    return found, sorted(findings, key=lambda finding: (finding.note, finding.line, finding.severity))


def check(ws: Workspace, con: sqlite3.Connection) -> list[Finding]:
    """Check that every citation in the workspace's notes resolves, and return what doesn't, by note and line. Reads
    the notes afresh first, recording their URLs as `sources` does, so the answer is about the notes as they are now."""
    sourcedb.record_sources(ws, con)
    return examine(ws, con)[1]


def run(ws: Workspace, con: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Print each citation that doesn't resolve, then a count. Returns 1 when there's an error, else 0."""
    findings = check(ws, con)
    # A finding a row of checks/waivers.csv accepts, by its key, is listed as waived and counts as neither.
    ledger = waivers.Ledger(ws, con)
    errors = warnings = waived = 0
    for finding in findings:
        decision = ledger.decide("citations", finding.note, finding.line, finding.key, (finding.key,)) if finding.key else None
        if decision and not decision.lapsed:
            print(f"{finding.note}:{finding.line}: waived: {finding.message} {decision.waiver.said()}")
            waived += 1
            continue
        print(f"{finding.note}:{finding.line}: {finding.severity}: {finding.message}")
        if decision:
            print(f"  {waivers.lapsed_message(decision)}")
        errors += finding.severity == "error"
        warnings += finding.severity == "warning"
    for waiver in ledger.unused(("citations",)):
        print(f"{waivers.FILE.as_posix()}:{waiver.row}: warning: {waivers.unused_message(waiver)}")
        warnings += 1
    notes = len(sourcedb.note_files(ws))
    print(f"{errors} error(s), {warnings} warning(s)" + (f", {waived} waived" if waived else "") +
          f" in {notes} note{'' if notes == 1 else 's'}")
    return 1 if errors else 0
