"""The source inventory: one list of what a workspace's notes rest on.

Each source a note's Sources list gives, and each document a cited filing brought in, is listed with its key, its
address, when it was fetched, how that went, the hash of the bytes kept, how much text was read from it, and the lines
of the notes that cite it. The status is one of:

- `fetched`: downloaded, and text was read from it. `fetched, no text` when none could be.
- `gathered by hand`: its text was loaded with `import-text`, because the site refused or the fetch gave nothing this
  reads.
- `imported file`: a local file, loaded with `import-file`.
- `refused`: the site answered 401, 403 or 429, and no text was gathered by hand.
- `failed`: any other failure.
- `not fetched`: nothing has been tried yet.

A source is marked primary (the company's own filing or release, a registry) or secondary (a report about it). A
Sources entry can say which by writing `[primary]` or `[secondary]`. Otherwise an address on a filings registry, such as
the SEC's, is primary, and so is one on a domain the workspace lists:

    [sources]
    primary = ["northbridge.example"]

and anything else is left unmarked rather than guessed. The list is printed and written to data/inventory.csv.
"""
import argparse
import csv
import re
import sqlite3
import urllib.parse
from collections import Counter
from dataclasses import dataclass

from . import sourcedb
from .workspace import Workspace

REPORT = "inventory.csv"
TAG = re.compile(r"\[(primary|secondary)\]", re.I)
# Registries where companies file. An address on one of these is the company's own filing.
REGISTRIES = ("sec.gov", "companieshouse.gov.uk", "company-information.service.gov.uk", "hkexnews.hk", "cninfo.com.cn",
              "sedarplus.ca", "edinet-fsa.go.jp", "dart.fss.or.kr", "filings.xbrl.org", "asx.com.au")
REFUSED = (401, 403, 429)
EXTRACTORS = sourcedb.EXTRACTORS


@dataclass(frozen=True)
class Entry:
    note: str
    key: str
    address: str
    origin: str
    fetched_at: str
    status: str
    sha256: str
    text_chars: int | None
    kind: str  # primary | secondary | ""
    # Each (note, line) whose body cites it.
    cited_at: tuple[tuple[str, int], ...]

    def cited(self) -> str:
        """Where it's cited, as `01_northbridge.md:9,15; 02_more.md:4`, or "-" when nothing cites it."""
        by_note: dict[str, list[str]] = {}
        for note, line in self.cited_at:
            by_note.setdefault(note, []).append(str(line))
        return "; ".join(f"{note}:{','.join(lines)}" for note, lines in by_note.items()) or "-"


def primary_domains(ws: Workspace) -> tuple[str, ...]:
    return tuple(str(domain).lower().strip() for domain in ws.config().get("sources", {}).get("primary", []) if str(domain).strip())


def kind_of(address: str, citation: str, domains: tuple[str, ...]) -> str:
    """Primary, secondary, or "" when neither the entry nor the address says."""
    tagged = TAG.search(citation or "")
    if tagged:
        return tagged.group(1).lower()
    host = urllib.parse.urlparse(address).netloc.lower()
    on = lambda domain: host == domain or host.endswith("." + domain)
    return "primary" if host and any(on(domain) for domain in (*REGISTRIES, *domains)) else ""


def status_of(fetched: tuple[int | None, str | None] | None, extractor: str | None, chars: int | None, local: bool) -> str:
    if local:
        return "imported file" if fetched else "not fetched"
    if extractor is not None and extractor not in EXTRACTORS:
        return "gathered by hand"
    if fetched is None:
        return "not fetched"
    status, error = fetched
    if status == 200 and not error:
        return "fetched" if chars else "fetched, no text"
    return "refused" if status in REFUSED else "failed"


def inventory(ws: Workspace, con: sqlite3.Connection) -> list[Entry]:
    """Every source the notes give, read afresh from the notes, with what's known of each."""
    sourcedb.record_sources(ws, con)
    cited = sourcedb.citing(ws, con)
    domains = primary_domains(ws)
    fetches = {url: row for url, *row in con.execute("SELECT url, http_status, error, fetched_at, sha256 FROM fetches")}
    documents = {url: (how, chars) for url, how, chars in con.execute("SELECT url, extractor, text_chars FROM documents")}
    entries: list[Entry] = []
    seen: set[tuple[str, str, str]] = set()
    for note, key, url, origin, citation in con.execute(
            "SELECT note_file, source_key, url, origin, citation FROM sources ORDER BY note_file, id").fetchall():
        if (note, key or "", url) in seen:
            continue
        seen.add((note, key or "", url))
        status_code, error, fetched_at, digest = fetches.get(url, (None, None, None, None))
        how, chars = documents.get(url, (None, None))
        status = status_of((status_code, error) if url in fetches else None, how, chars, url.startswith(sourcedb.LOCAL))
        lines = tuple(dict.fromkeys((n, line) for n, k, line in cited.get(url, []) if k == key))
        entries.append(Entry(note, key or "", url, origin, fetched_at or "", status, digest or "", chars, kind_of(url, citation, domains),
                             lines))
    return entries


def run(ws: Workspace, con: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Print the inventory and a count of each status, and write data/inventory.csv."""
    entries = inventory(ws, con)
    for entry in entries:
        size = "-" if entry.text_chars is None else f"{entry.text_chars:,}"
        print(f"{entry.note[:28]:<28} {entry.key or '-':<5} {entry.status:<17} {entry.kind or '-':<9} {size:>10}  {entry.address}")
        print(f"{'':<34} fetched {entry.fetched_at[:10] or '-'}  sha256 {entry.sha256[:12] or '-'}  cited at {entry.cited()}")
    counts = Counter(entry.status for entry in entries)
    print(", ".join(f"{count} {status}" for status, count in sorted(counts.items())) or "no sources in the notes")
    ws.data.mkdir(parents=True, exist_ok=True)
    with (ws.data / REPORT).open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["note_file", "source_key", "address", "origin", "fetched_at", "status", "sha256", "text_chars", "kind", "cited_at"])
        writer.writerows([e.note, e.key, e.address, e.origin, e.fetched_at, e.status, e.sha256,
                          "" if e.text_chars is None else e.text_chars, e.kind, e.cited()] for e in entries)
    print(f"wrote {ws.data / REPORT}")
    return 0
