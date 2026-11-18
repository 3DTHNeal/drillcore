"""The evidence pack: one page for each draft that a reviewer can check without running anything.

Each draft is written out line by line, and every figure and quotation in it links to what backs it. A figure links to
its trace, as `drillcore trace` gives it: the note rows that hold it, the source keys they cite, each address with the
date it was fetched and the hash of what came back, and the passage in the stored copy with the figure highlighted. A
quotation links to the passage of a stored copy that holds it, read the way `quotes` reads a source, so curly marks,
dashes and line breaks are evened out in what's shown. Where a link is missing, the page says which.

Beside each line are the findings `drillcore assay` last wrote for it, from data/assay.csv, and beside each note row
the findings `drillcore check` last wrote for it, from data/research_checks.csv, with a waiver's reason where one was
accepted. Those files are read as they are, so the page says when each was written; a stale one is the reviewer's cue
to run the check again.

The page is built from the stored copies only. Nothing is fetched, nothing outside the page is loaded, and everything
from a draft, a note or a source is escaped as text: it's shown, never run. The pack says nothing the notes, the
sources and the checks don't. Each page is written to data/evidence/, named after its draft.
"""
import argparse
import csv
import html
import re
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from . import identity
from .drafts import read_draft
from .overlap import draft_files, drafts_folder
from .quotes import INLINE, pieces, source_forms
from .sourcedb import now
from .trace import CONTEXT, Address, Chain, Passage, Store, Trace, Tracer, figures_in
from .workspace import Workspace

FOLDER = "evidence"
CHECKS = "research_checks.csv"
ASSAY = "assay.csv"

STYLE = """
:root { --bg: #fbfaf7; --fg: #1d1d1b; --muted: #6b6b66; --line: #e2e0d8; --link: #1f5fa8; --mark: #ffe58a;
  --fail: #b3261e; --warn: #8a5a00; --ok: #2e6b30; --panel: #f2f0ea; }
@media (prefers-color-scheme: dark) { :root { --bg: #18181a; --fg: #e8e6e1; --muted: #a09d96; --line: #34332f;
  --link: #8ab8f0; --mark: #6b5a12; --fail: #f0a29b; --warn: #e6c27a; --ok: #9fd3a1; --panel: #222225; } }
body { background: var(--bg); color: var(--fg); font: 16px/1.55 system-ui, sans-serif; margin: 0 auto; max-width: 60rem;
  padding: 1.5rem 1rem 4rem; }
h1 { font-size: 1.5rem; margin-bottom: .25rem; } h2 { font-size: 1.15rem; margin-top: 2.5rem; border-bottom: 1px solid var(--line); }
h3 { font-size: 1rem; margin: 0 0 .5rem; }
.meta, .no, .small { color: var(--muted); font-size: .85rem; }
.line { display: grid; grid-template-columns: 3rem 1fr; gap: .5rem; margin: .15rem 0; }
.no { text-align: right; user-select: none; }
a { color: var(--link); } mark { background: var(--mark); color: inherit; padding: 0 .1em; }
.finding { font-size: .85rem; margin: .1rem 0 .1rem 3.5rem; }
.fail { color: var(--fail); } .warn, .warning { color: var(--warn); } .waived { color: var(--muted); } .pass { color: var(--ok); }
.item { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; margin: 1rem 0; padding: .75rem 1rem; }
.item:target { outline: 2px solid var(--link); }
.passage { font-family: ui-monospace, monospace; font-size: .85rem; overflow-wrap: anywhere; white-space: pre-wrap; }
.missing { color: var(--fail); }
code { overflow-wrap: anywhere; }
"""


@dataclass(frozen=True)
class Finding:
    """One finding a check last wrote, as its report file has it."""
    check: str
    verdict: str
    item: str
    detail: str
    waiver: str = ""


@dataclass(frozen=True)
class Found:
    """A quotation from a draft and the stored copy that holds it."""
    url: str
    keys: str
    passage: Passage | None


# ---------------------------------------------------------------- the checks' last findings

def _written(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_findings(ws: Workspace) -> tuple[dict[tuple[str, int], list[Finding]], str]:
    """What `check` last wrote, by (note, line), and when it was written, or "" when it never was."""
    path = ws.data / CHECKS
    found: dict[tuple[str, int], list[Finding]] = defaultdict(list)
    if not path.is_file():
        return found, ""
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            if (row.get("line_no") or "").isdigit():
                found[row["note_file"], int(row["line_no"])].append(
                    Finding(row.get("check", ""), row.get("verdict", ""), row.get("item", ""), row.get("detail", ""), row.get("waiver") or ""))
    return found, _written(path)


def assay_findings(ws: Workspace) -> tuple[dict[tuple[str, int], list[Finding]], str]:
    """What `assay` last wrote, by (draft, line), with each draft's verdict at line 0, and when it was written."""
    path = ws.data / ASSAY
    found: dict[tuple[str, int], list[Finding]] = defaultdict(list)
    if not path.is_file():
        return found, ""
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            line = row.get("line_no") or ""
            if line.isdigit() and (row.get("verdict") != "pass" or row.get("check") == "verdict"):
                found[row["draft"], int(line)].append(Finding(row.get("check", ""), row.get("verdict", ""), row.get("item", ""),
                                                              row.get("detail", "")))
    return found, _written(path)


# ---------------------------------------------------------------- quotations

def _quote_at(parts: list[str], text: str) -> tuple[int, int] | None:
    """Where a quotation's parts stand in a text, in order, from the start of the first to the end of the last. The
    first letter may be in either case, as `quotes` allows."""
    at, start = 0, -1
    for number, part in enumerate(parts):
        found = text.find(part, at)
        if found < 0 and number == 0 and part[:1].isalpha():
            found = text.find(part[0].swapcase() + part[1:], at)
        if found < 0:
            return None
        start = found if number == 0 else start
        at = found + len(part)
    return (start, at) if parts else None


def quoted_in(quotation: str, store: Store, cited: dict[str, str]) -> Found | None:
    """The first stored copy the notes cite that holds a quotation, with the passage, or None when none does."""
    parts = pieces(quotation)
    for url, keys in cited.items():
        text = store.text(url)
        for form in source_forms(text) if text else ():
            span = _quote_at(parts, form)
            if span:
                start, end = span
                before, after = form[max(0, start - CONTEXT):start], form[end:end + CONTEXT]
                return Found(url, keys, Passage(("... " if start > CONTEXT else "") + before, form[start:end],
                                                after + (" ..." if end + CONTEXT < len(form) else ""), "exact"))
    return None


def quotations_in(text: str) -> list[tuple[int, int, str]]:
    """Each quotation on a draft's line, as (start, end, its words): text in double quotes, or the whole of a
    blockquote."""
    if text.lstrip().startswith(">"):
        marker = re.match(r"\s*>\s?", text)
        words = text[marker.end() if marker else 0:].strip()
        return [(marker.end() if marker else 0, len(text), words)] if words else []
    return [(match.start(), match.end(), " ".join(match.group(1).split())) for match in INLINE.finditer(text) if match.group(1).strip()]


# ---------------------------------------------------------------- the page

def esc(text: str) -> str:
    return html.escape(text, quote=True)


def _finding(found: Finding) -> str:
    verdict = found.verdict.lower().replace(" ", "-")
    waiver = f" Waived: {esc(found.waiver)}" if found.waiver else ""
    item = f" <code>{esc(found.item[:120])}</code>" if found.item else ""
    return (f'<p class="finding {esc(verdict)}"><strong>{esc(found.verdict.upper())}</strong> {esc(found.check)}{item}: '
            f"{esc(found.detail)}{waiver}</p>")


def _passage(found: Passage) -> str:
    return f'<div class="passage">{esc(found.before)}<mark>{esc(found.match)}</mark>{esc(found.after)}</div>'


def _source(address: Address) -> str:
    fetched = f"fetched {esc(address.fetched_at or '-')}, sha256 <code>{esc(address.sha256 or '-')}</code>"
    head = f'<p><strong>{esc(address.key)}</strong> <a href="{esc(address.url)}">{esc(address.url)}</a><br><span class="small">{fetched}</span></p>'
    if address.passage:
        return head + f'<p class="small">found ({esc(address.passage.kind)}) in the stored copy:</p>' + _passage(address.passage)
    return head + f'<p class="missing">Missing: {esc(address.missing)}</p>'


def _chain(chain: Chain, checks: dict[tuple[str, int], list[Finding]]) -> str:
    out = [f'<p>Note <code>{esc(chain.note)}:{chain.line_no}</code>: {esc(chain.row)}</p>']
    out += [_finding(found) for found in checks.get((chain.note, chain.line_no), [])]
    if chain.missing:
        out.append(f'<p class="missing">Missing: {esc(chain.missing)}</p>')
    out += [_source(address) for address in chain.addresses]
    return "".join(out)


def _figure_item(anchor: str, line_no: int, found: Trace, checks: dict[tuple[str, int], list[Finding]]) -> str:
    out = [f'<div class="item" id="{anchor}"><h3>{esc(found.figure.written)} <span class="small">on line '
           f'<a href="#L{line_no}">{line_no}</a></span></h3>']
    if not found.chains:
        out.append(f'<p class="missing">Missing: no note row holds {esc(found.figure.written)}.</p>')
    out += [_chain(chain, checks) for chain in found.chains]
    return "".join(out) + "</div>"


def _quote_item(anchor: str, line_no: int, words: str, found: Found | None, store: Store) -> str:
    out = [f'<div class="item" id="{anchor}"><h3>&ldquo;{esc(words[:200])}&rdquo; <span class="small">on line '
           f'<a href="#L{line_no}">{line_no}</a></span></h3>']
    if found and found.passage:
        fetched_at, digest, _ = store.fetch_record(found.url)
        out.append(_source(Address(found.keys, found.url, fetched_at, digest, found.passage, "")))
    else:
        out.append('<p class="missing">Missing: no stored copy the notes cite holds this quotation.</p>')
    return "".join(out) + "</div>"


def _marked(text: str, spans: list[tuple[int, int, str]]) -> str:
    """A line escaped, with each span made a link to its anchor."""
    out, at = [], 0
    for start, end, anchor in sorted(spans):
        if start < at:
            continue
        out += [esc(text[at:start]), f'<a href="#{anchor}">{esc(text[start:end])}</a>']
        at = end
    return "".join(out) + esc(text[at:])


def page(ws: Workspace, draft: Path, tracer: Tracer) -> str:
    """The evidence page for one draft."""
    checks, checks_written = check_findings(ws)
    assayed, assay_written = assay_findings(ws)
    cited: dict[str, str] = {}
    for url, note, key in tracer.store.con.execute(
            "SELECT url, note_file, source_key FROM sources WHERE source_key IS NOT NULL ORDER BY id"):
        cited[url] = ", ".join(dict.fromkeys([*filter(None, cited.get(url, "").split(", ")), f"{note} {key}"]))
    lines, items = [], []
    for line_no, raw in enumerate(read_draft(draft).splitlines(), 1):
        text = raw.rstrip()
        spans: list[tuple[int, int, str]] = []
        for number, (start, end, words) in enumerate(quotations_in(text)):
            anchor = f"q{line_no}-{number}"
            spans.append((start, end, anchor))
            items.append(_quote_item(anchor, line_no, words, quoted_in(words, tracer.store, cited), tracer.store))
        quoted = [(start, end) for start, end, _ in spans]
        for number, figure in enumerate(figures_in(text)):
            if any(start <= figure.start < end for start, end in quoted):
                continue
            anchor = f"f{line_no}-{number}"
            spans.append((figure.start, figure.end, anchor))
            items.append(_figure_item(anchor, line_no, Trace(figure, [], tracer.chains(figure)), checks))
        lines.append(f'<div class="line" id="L{line_no}"><span class="no">{line_no}</span><span>{_marked(text, spans) or "&nbsp;"}</span></div>')
        lines += [_finding(found) for found in assayed.get((draft.name, line_no), [])]
    verdict = "".join(_finding(found) for found in assayed.get((draft.name, 0), []))
    said = [f"Built {now()} from the stored copies only; nothing was fetched."]
    said.append(f"Findings from <code>assay</code> as written {assay_written}." if assay_written else
                f"<code>{identity.SLUG} assay</code> hasn't been run, so no draft findings are shown.")
    said.append(f"Findings from <code>check</code> as written {checks_written}." if checks_written else
                f"<code>{identity.SLUG} check</code> hasn't been run, so no note findings are shown.")
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>Evidence: {esc(draft.name)}</title><style>{STYLE}</style></head><body>"
            f"<h1>{esc(draft.name)}</h1><p class=\"meta\">{' '.join(said)}</p>{verdict}"
            f"<h2>The draft</h2>{''.join(lines)}"
            f"<h2>The evidence</h2>{''.join(items) or '<p>No figures or quotations in this draft.</p>'}</body></html>\n")


def build(ws: Workspace, con: sqlite3.Connection, drafts: list[Path] | None = None) -> list[Path]:
    """Write the evidence page for each draft named, or for every draft. Returns the pages written."""
    tracer = Tracer(ws, con)
    folder = ws.data / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for draft in drafts or draft_files(ws):
        out = folder / f"{draft.stem}.html"
        out.write_text(page(ws, draft, tracer), encoding="utf-8", newline="\n")
        written.append(out)
    return written


def resolve(ws: Workspace, given: str) -> Path:
    """A draft named on the command line: as a path, or failing that, a file in the drafts folder."""
    path = Path(given).expanduser()
    if path.is_file():
        return path.resolve()
    if (drafts_folder(ws) / path).is_file():
        return drafts_folder(ws) / path
    raise ValueError(f"No such draft: {given}. Name a file, or one in {drafts_folder(ws)}.")


def run(ws: Workspace, con: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Write each draft's evidence page and say where."""
    try:
        named = [resolve(ws, str(given)) for given in getattr(args, "drafts", None) or []]
    except ValueError as problem:
        print(problem, file=sys.stderr)
        return 1
    written = build(ws, con, named or None)
    if not written:
        print(f"No drafts to build a pack for: {drafts_folder(ws)} has no Markdown, Word or PDF files.", file=sys.stderr)
    for path in written:
        print(f"wrote {path}")
    return 0
