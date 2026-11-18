"""Whether a draft shares a long passage with a fetched source.

A draft that repeats a run of a source's words, unquoted, has copied it. This finds every run of `min_words` or more
consecutive words (12 unless the workspace or the command says otherwise) that a draft in the workspace's drafts folder
shares with the text of any fetched source. Words are compared without regard to case, punctuation or the spacing
between them, so a copied passage that was re-wrapped or re-capitalised is still found.

Text inside double quotation marks (straight, curly or angled), inside curly single quotation marks, and in Markdown
blockquotes is left out, since quoting a source and saying whose it is isn't copying. Straight single quotes are too
easily confused with apostrophes to be read as quotation marks. An in-text citation, brackets holding a year or "n.d.",
is left out too: it names the source, as a court's or an agency's full name does, and a source prints its own name. A
run never crosses a quotation or a citation, so the words either side of one aren't joined into a passage.

The settings, in the workspace's settings file:

    [drafts]
    folder = "drafts"   # where the drafts are, from the workspace's root
    min_words = 12      # how long a shared run must be to count
    records = ["Appendix B"]   # headings of sections that are records, such as a log of prompts quoted word for word

A draft's reference list, and each section `records` names, is left out: a reference list gives the titles of the very
sources it would be found in, and a record is kept word for word on purpose. `assay` and `proof` leave them out too.

Each source is read once, and only a draft's runs are held in memory, so a large source costs time in proportion to
its length and nothing more. This reads the drafts; it never changes them.
"""
import argparse
import csv
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from . import drafts
from .sourcedb import URL
from .workspace import Workspace

MIN_WORDS = 12
EXCERPT_CHARS = 100
# A word: letters and digits, with any apostrophe inside it, so "don't" stays one word.
WORD = re.compile(r"\w+(?:['’]\w+)*")
APOSTROPHE = re.compile(r"['’]")
# Quotations may run across a wrapped line, but not across a blank one, so an unclosed mark can't hide the rest of a draft.
QUOTED = re.compile(r'"(?:[^"\n]|\n(?![ \t]*\n))*"'
                    r"|“(?:[^”\n]|\n(?![ \t]*\n))*”"
                    r"|«(?:[^»\n]|\n(?![ \t]*\n))*»"
                    r"|‘(?:[^’\n]|\n(?![ \t]*\n))*’")
BLOCKQUOTE = re.compile(r"^[ \t]{0,3}>.*$", re.M)
# What stands in for left-out text. It's no word, so it breaks a run, and it keeps every other character where it was.
GAP = "\x00"
PIECE = re.compile(GAP + "+|" + WORD.pattern)

# A word of a draft: its compared form, and where it starts and ends in the draft's text.
Word = tuple[str, int, int]


@dataclass(frozen=True)
class Passage:
    """A run of words a draft shares with a source."""
    draft: str      # the draft's file name
    line: int       # the line the passage starts on
    words: int      # how many words long it is
    url: str        # the source it's found in; the one sharing most of it when more than one does
    excerpt: str    # the start of the passage, as the draft writes it


def normalise(word: str) -> str:
    """A word as it's compared: in one case and without apostrophes."""
    return APOSTROPHE.sub("", word).casefold()


def source_words(text: str) -> list[str]:
    """A source's words, as they're compared."""
    return [normalise(match.group(0)) for match in WORD.finditer(text)]


def _blank(match: re.Match[str]) -> str:
    """Left-out text, as gaps the same length, keeping its line breaks."""
    return re.sub(r"[^\n]", GAP, match.group(0))


def draft_stretches(text: str) -> list[list[Word]]:
    """A draft's words, in stretches broken wherever something is left out: a quotation, a blockquote or an address."""
    kept = BLOCKQUOTE.sub(_blank, text)
    kept = URL.sub(_blank, kept)
    kept = QUOTED.sub(_blank, kept)
    kept = drafts.CITATION.sub(_blank, kept)
    stretches: list[list[Word]] = [[]]
    for match in PIECE.finditer(kept):
        if match.group(0).startswith(GAP):
            if stretches[-1]:
                stretches.append([])
        else:
            stretches[-1].append((normalise(match.group(0)), match.start(), match.end()))
    return [stretch for stretch in stretches if stretch]


def settings(ws: Workspace) -> dict[str, object]:
    """The `[drafts]` settings, or {} when there are none."""
    found = ws.config().get("drafts", {})
    return found if isinstance(found, dict) else {}


def drafts_folder(ws: Workspace) -> Path:
    return ws.root / str(settings(ws).get("folder", "drafts"))


def records(ws: Workspace) -> tuple[str, ...]:
    """The headings of the sections of a draft that are records rather than its analysis, such as a log of prompts
    quoted word for word (`[drafts] records`). Raises ValueError, saying what to fix, for a setting that can't be used."""
    given = settings(ws).get("records", [])
    if not isinstance(given, list) or not all(isinstance(entry, str) and entry.strip() for entry in given):
        raise ValueError(f"[drafts] records in {ws.config_path} must be a list of headings, none of them blank.")
    return tuple(given)


def analysed(ws: Workspace, path: Path) -> str:
    """A draft's text as the checks that judge what it says read it: without its reference list or the sections named
    as records (`drafts.set_aside`), each line where it was."""
    return drafts.set_aside(drafts.read_draft(path), records(ws))


def draft_files(ws: Workspace) -> list[Path]:
    """Every draft in the drafts folder: each Markdown file, Word document and PDF (`drafts.is_draft`)."""
    folder = drafts_folder(ws)
    return sorted(path for path in folder.iterdir() if drafts.is_draft(path)) if folder.is_dir() else []


def min_words_for(ws: Workspace, given: int | None = None) -> int:
    """How long a shared run must be: what the command says, else the workspace's setting, else 12. Raises ValueError
    for anything but a whole number of at least 2, since a run of one word would match almost everything."""
    chosen = given if given is not None else settings(ws).get("min_words", MIN_WORDS)
    if isinstance(chosen, bool) or not isinstance(chosen, int) or chosen < 2:
        raise ValueError(f"The shortest run to report must be a whole number of at least 2, not {chosen!r}.")
    return chosen


def excerpt(text: str) -> str:
    """A passage's text on one line, cut at a word near EXCERPT_CHARS."""
    flat = " ".join(text.split())
    if len(flat) <= EXCERPT_CHARS:
        return flat
    return flat[:EXCERPT_CHARS].rsplit(" ", 1)[0] + " ..."


def check(ws: Workspace, con: sqlite3.Connection, min_words: int | None = None) -> list[Passage]:
    """Every passage of `min_words` or more words that a draft shares with a fetched source, each reported once, in
    order of draft and position. Overlapping runs are merged into the longest passage they make. Writes
    data/overlap.csv."""
    n = min_words_for(ws, min_words)
    read = [(path, analysed(ws, path)) for path in draft_files(ws)]
    stretches = [draft_stretches(text) for _, text in read]

    # Every run of n words in the drafts, with where each one starts: (draft, stretch, word).
    runs: dict[tuple[str, ...], list[tuple[int, int, int]]] = {}
    for d, draft in enumerate(stretches):
        for s, stretch in enumerate(draft):
            words = [word for word, _, _ in stretch]
            for i in range(len(words) - n + 1):
                runs.setdefault(tuple(words[i:i + n]), []).append((d, s, i))
    firsts = {run[0] for run in runs}

    # For each run start a source shares, which sources share it, by their place in `urls`.
    urls: list[str] = []
    shared: dict[tuple[int, int, int], set[int]] = {}
    if runs:
        for url, text in con.execute("SELECT url, text FROM documents WHERE text IS NOT NULL ORDER BY url"):
            words = source_words(text)
            found = False
            for i in range(len(words) - n + 1):
                if words[i] in firsts:
                    for start in runs.get(tuple(words[i:i + n]), ()):
                        shared.setdefault(start, set()).add(len(urls))
                        found = True
            if found:
                urls.append(url)

    # Runs that overlap in a stretch merge into one passage: (draft, stretch, first word, end, runs each source shares).
    merged: list[tuple[int, int, int, int, dict[int, int]]] = []
    for d, s, i in sorted(shared):
        if merged and merged[-1][:2] == (d, s) and i < merged[-1][3]:
            _, _, first, _, counts = merged[-1]
            merged[-1] = (d, s, first, i + n, counts)
        else:
            counts = {}
            merged.append((d, s, i, i + n, counts))
        for u in shared[(d, s, i)]:
            counts[u] = counts.get(u, 0) + 1

    passages: list[Passage] = []
    for d, s, first, end, counts in merged:
        path, text = read[d]
        begin, finish = stretches[d][s][first][1], stretches[d][s][end - 1][2]
        best = min(counts, key=lambda u: (-counts[u], u))
        passages.append(Passage(path.name, text.count("\n", 0, begin) + 1, end - first, urls[best], excerpt(text[begin:finish])))

    ws.data.mkdir(parents=True, exist_ok=True)
    with (ws.data / "overlap.csv").open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["draft", "line_no", "words", "url", "excerpt"])
        writer.writerows((p.draft, p.line, p.words, p.url, p.excerpt) for p in passages)
    return passages


def run(ws: Workspace, con: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Print each shared passage and a summary. Exits 1 when a draft shares a passage with a source."""
    try:
        n = min_words_for(ws, getattr(args, "min_words", None))
        passages = check(ws, con, n)
    except ValueError as problem:
        print(problem, file=sys.stderr)
        return 1
    drafts = draft_files(ws)
    if not drafts:
        print(f"No drafts to check: {drafts_folder(ws)} has no Markdown, Word or PDF files.", file=sys.stderr)
    sources = con.execute("SELECT COUNT(*) FROM documents WHERE text IS NOT NULL").fetchone()[0]
    for p in passages:
        print(f"{p.draft}:{p.line}  {p.words} words  {p.url}\n    {p.excerpt}")
    print(f"{len(passages)} passage(s) of {n} or more words shared with a source, in {len(drafts)} draft(s) "
          f"checked against {sources} fetched source(s)")
    print(f"wrote {ws.data / 'overlap.csv'}")
    return 1 if passages else 0
