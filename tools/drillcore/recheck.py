"""Recheck: whether a cited source still says what it said when the notes were checked against it.

Investor pages and press releases are edited quietly, and pages disappear. `drillcore recheck` fetches each cited source
that has a stored copy once more, under the same declared client name and with the same pause between requests to one
host as `fetch`, and compares what comes back with the stored copy by its hash:

- "unchanged": the same bytes.
- "changed": different text, shown as a short diff of the extracted text, stored copy first.
- "markup_changed": different bytes but the same extracted text, so nothing a check reads has moved.
- "gone": the address answers 404 or 410. The Internet Archive's availability service is asked for its closest copy,
  and the address of that copy is recorded as a second address. A refusal from the archive is recorded too.
- "refused": the site refuses the client (401, 403, 429 or 451). The refusal is recorded and nothing is tried in its
  place: a refused page isn't gone, and looking for it elsewhere would be routing around the refusal.
- "failed": anything else, such as a timeout or a server error.

The copy the notes were checked against is never replaced. Each new body is kept beside it in data/raw/, by its hash,
and each recheck is a row of the `rechecks` table, so both copies stay and the history of what an address served is
kept. A page whose text was gathered by hand has no stored copy to compare and isn't asked for again.

What comes back is data: it's stored and read, never run.
"""
import argparse
import difflib
import json
import sqlite3
import sys
import urllib.parse
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from . import identity, sourcedb
from .workspace import Workspace

SCHEMA = """
CREATE TABLE IF NOT EXISTS rechecks (
    id INTEGER PRIMARY KEY,
    url TEXT NOT NULL, checked_at TEXT, status TEXT,   -- unchanged | changed | markup_changed | gone | refused | failed
    http_status INTEGER, stored_sha256 TEXT, sha256 TEXT, raw_path TEXT, error TEXT,
    archived_url TEXT, detail TEXT
);
"""
ARCHIVE = "https://archive.org/wayback/available?url="
GONE = (404, 410)
REFUSED = sourcedb.REFUSED
# A failing status: the notes may no longer match what the address serves.
FAILING = ("changed", "gone")
# The longest diff shown for one source, in lines.
DIFF_LINES = 40


@dataclass(frozen=True)
class Recheck:
    url: str
    status: str
    http_status: int | None
    detail: str = ""
    archived_url: str = ""
    diff: tuple[str, ...] = ()


def text_diff(before: str, after: str, limit: int = DIFF_LINES) -> tuple[str, ...]:
    """The lines of extracted text that changed, as a unified diff with one line of context, cut to `limit` lines."""
    lines = list(difflib.unified_diff(before.splitlines(), after.splitlines(), "stored copy", "served now", n=1, lineterm=""))
    if len(lines) > limit:
        lines = [*lines[:limit], f"... {len(lines) - limit} more lines of difference"]
    return tuple(lines)


def archived(url: str, get: Callable[[str], sourcedb.Response]) -> tuple[str, str]:
    """The Internet Archive's closest copy of a page, as (its address, ""), or ("", why there's none)."""
    status, _, _, body, error = get(ARCHIVE + urllib.parse.quote(url, safe=""))
    if status != 200 or not body:
        return "", f"the archive's lookup failed ({error or f'HTTP {status}'})"
    try:
        closest = json.loads(body).get("archived_snapshots", {}).get("closest") or {}
    except (ValueError, AttributeError):
        return "", "the archive's answer couldn't be read"
    if closest.get("available") and str(closest.get("url", "")).startswith(("http://", "https://")):
        return str(closest["url"]), ""
    return "", "the archive holds no copy"


def stored_sources(con: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """Each cited source with a stored copy, as (URL, its hash, its content type), in address order."""
    return [(url, digest, kind or "") for url, digest, kind in con.execute(
        "SELECT url, sha256, content_type FROM fetches WHERE http_status = 200 AND sha256 IS NOT NULL"
        " AND url IN (SELECT url FROM sources) ORDER BY url")]


def recheck(ws: Workspace, con: sqlite3.Connection, get: Callable[[str], sourcedb.Response] | None = None,
            say: Callable[[str], None] = print) -> list[Recheck]:
    """Fetch each cited source with a stored copy once more and compare. Records each in `rechecks` and returns them."""
    get = get or sourcedb.http_get
    con.executescript(SCHEMA)
    results: list[Recheck] = []
    for url, digest, _ in stored_sources(con):
        status, content_type, _, body, error = get(url)
        new_digest = raw_path = None
        archived_url = ""
        diff: tuple[str, ...] = ()
        if status == 200 and body:
            ext = sourcedb.guess_ext(content_type, body)
            new_digest, raw_path = sourcedb.save_raw(ws, body, ext)
            if new_digest == digest:
                outcome, detail = "unchanged", ""
            else:
                _, after, _ = sourcedb.extract_text(ws, raw_path, ext, content_type, url)
                row = con.execute("SELECT text FROM documents WHERE url=?", (url,)).fetchone()
                before = row[0] if row and row[0] else None
                if before is not None and after is not None and before == after:
                    outcome, detail = "markup_changed", "the bytes differ, but the text read from them is the same"
                elif before is None or after is None:
                    outcome, detail = "changed", "the bytes differ, and the text of one copy can't be read to compare"
                else:
                    outcome, diff = "changed", text_diff(before, after)
                    detail = f"the text differs; the new copy is kept at {raw_path}"
        elif status in REFUSED:
            outcome, detail = "refused", f"the site refused the fetch (HTTP {status}); recorded, and nothing tried in its place"
        elif status in GONE:
            outcome = "gone"
            archived_url, why = archived(url, get)
            detail = f"HTTP {status}; " + (f"archived copy at {archived_url}" if archived_url else why)
        else:
            outcome, detail = "failed", error or f"HTTP {status} with an empty body"
        con.execute("INSERT INTO rechecks(url, checked_at, status, http_status, stored_sha256, sha256, raw_path, error,"
                    " archived_url, detail) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (url, sourcedb.now(), outcome, status, digest, new_digest, raw_path, error, archived_url or None, detail))
        con.commit()
        results.append(Recheck(url, outcome, status, detail, archived_url, diff))
        say(f"{outcome:<15} {sourcedb.shown(url)[:110]}" + (f"\n    {sourcedb.shown(detail)}" if detail else ""))
        # The diff is the source's own words: printed with what a terminal would act on taken out.
        for line in diff:
            say(f"    {sourcedb.shown(line)}")
    return results


def run(ws: Workspace, con: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Recheck every stored source and count each outcome. Exits 1 when a source's text changed or its page is gone."""
    results = recheck(ws, con)
    if not results:
        print(f"Nothing to recheck: no cited source has a stored copy. Run `{identity.SLUG} fetch` first.", file=sys.stderr)
        return 0
    counts = Counter(result.status for result in results)
    print(", ".join(f"{counts[status]} {status.replace('_', ' ')}" for status in
                    ("unchanged", "markup_changed", "changed", "gone", "refused", "failed") if counts[status]))
    if counts["changed"]:
        print("The stored copies the notes were checked against are kept; the new ones are beside them in data/raw/.")
    return 1 if any(counts[status] for status in FAILING) else 0

