"""Names spelled one way: the proper names in the notes and drafts, grouped with the other ways they're spelled.

A long report spells a company, a person or a product several ways: NorthBridge and Northbridge, Jane Doe and Jane
Do, Zoë and Zoe. This gathers every proper name the notes and drafts write, a run of capitalised words or a ticker in
capitals, and puts together the spellings that differ only by spacing, hyphenation, accents or case, or by a letter in
a name of six letters or more, or two in one of ten or more. Each group with more than one spelling is listed with
where each spelling is written. A plural or a possessive is the same spelling. The other parts of the report that
`[proof] companions` names, such as an appendix kept beside the drafts, are read as drafts are.

What isn't the writer's own spelling is left out: the Sources and Gaps and cautions sections, a reference list (its
titles keep each source's own spelling), code, web addresses,
domains and emails, source keys, quotations and blockquotes. A word that opens a sentence or a table cell is capitalised
because of where it is, so it counts as a name only when it's capitalised somewhere else too, and "The", "In" and the
like are dropped from the front of a run. A single word of fewer than four letters counts only as a ticker in capitals,
and a word of six or more in capitals is a heading's styling, not a name.

A workspace can name the spellings it wants, in its settings file:

    [names]
    preferred = ["Northbridge Robotics", "Jane Doe"]

Each is then held to: any other way of writing it is listed against it, including one split or joined differently,
found as the assay finds a confidential name. This reads the notes and drafts; it never
changes them.
"""
import argparse
import csv
import re
import sqlite3
import unicodedata
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from assay import names as assay_names

from .drafts import REFERENCE_HEADING, read_draft
from .overlap import BLOCKQUOTE, QUOTED, draft_files
from .sourcedb import NOT_NOTES, URL, note_files
from .workspace import Workspace

REPORT = "names.csv"
# A word: a letter, then letters and digits, with apostrophes and hyphens inside it, as "O'Neil" and "Mary-Ann".
WORD = re.compile(r"[^\W\d_]\w*(?:['’\-]\w+)*")
POSSESSIVE = re.compile(r"['’]s$")
# Lowercase words that sit inside a name: "Bank of America", "Vincent van Gogh".
INSIDE = frozenset({"of", "de", "van", "von", "der", "den", "la", "le", "du", "da", "di", "del"})
# Words that are capitalised because they open a sentence, never because they're names.
OPENERS = frozenset({
    "The", "A", "An", "In", "On", "At", "For", "From", "To", "By", "With", "Of", "And", "But", "Or", "Nor", "If", "As", "It",
    "Its", "This", "That", "These", "Those", "There", "Their", "They", "We", "Our", "He", "She", "His", "Her", "I", "You",
    "Your", "What", "When", "Where", "Which", "Who", "Why", "How", "All", "Some", "Each", "Every", "No", "Not", "After",
    "Before", "During", "Since", "Until", "While", "Also", "Both", "Over", "Under", "Against", "About", "Between", "Into",
    "Through", "Per", "Note", "See", "So", "Yet", "Then", "Than", "Here", "Most", "Many", "More", "Less", "Such", "Only",
    "Even", "Just", "One", "Two", "Three", "Any", "Other", "Another"})
# What a line opens with in Markdown, before its words: a heading's marks, a bullet, a number, a blockquote's mark.
LEAD = re.compile(r"^\s*(?:#+|[-*+]|\d+[.)]|>)?\s*")
# What ends a sentence, a clause that opens like one, or a table cell.
OPENS_AFTER = re.compile(r"[.!?:;|(\[]\s*$")
# A source key, as S1 or AB12a: letters and a number, never a name.
KEY = re.compile(r"\b[A-Z]{1,2}\d{1,3}[a-z]?\b")
CODE_SPAN = re.compile(r"`[^`]*`")
FENCE = re.compile(r"^\s*(```|~~~)")
EMPHASIS = re.compile(r"\*+|(?<!\w)_+|_+(?!\w)")
DOMAIN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+|\b(?:www\.)?[\w-]+(?:\.[\w-]+)*\.(?:com|org|net|io|gov|edu|co|uk|de|fr|"
                    r"cn|jp|hk|info|biz)\b(?:/\S*)?", re.I)
# What can sit between the letters of a name without making it another word, as the assay reads a confidential name.
JOIN = r"(?:[\s\-_/·‐-―−]|\.(?=\w)){0,3}"


@dataclass(frozen=True)
class Mention:
    """One place a name is written: as written, and where."""
    spelling: str
    file: str       # from the workspace's root, as research/01_northbridge.md
    line: int
    # Whether it's a single word that opens a sentence or a cell, which is capitalised because of where it stands.
    opening: bool = False


@dataclass(frozen=True)
class Group:
    """The spellings of one name. `held_to` is the preferred spelling the workspace names, or "" when it names none."""
    held_to: str
    mentions: tuple[Mention, ...]

    @property
    def spellings(self) -> list[str]:
        """Each spelling, the most written first, and of those written as often, the first written first."""
        counts = Counter(mention.spelling for mention in self.mentions)
        return sorted(counts, key=lambda spelling: -counts[spelling])

    @property
    def label(self) -> str:
        return self.held_to or self.spellings[0]

    @property
    def variants(self) -> list[str]:
        """The spellings that aren't the one held to, or for a name nobody prefers, every spelling but the commonest."""
        return [spelling for spelling in self.spellings if spelling != self.label]


def fold(name: str) -> str:
    """A name with what doesn't make it another name taken away: case, accents, and the spaces, hyphens and other
    marks between its letters."""
    name = unicodedata.normalize("NFKD", POSSESSIVE.sub("", name))
    return "".join(ch for ch in name if ch.isalnum() and not unicodedata.combining(ch)).casefold()


# The words that end a company's legal name: "Kestrel Arms Co" and "Kestrel Arms Ltd" spell "Kestrel Arms" as prose
# does, with its kind after it, not another way.
LEGAL_FORM = re.compile(r"(?<=\S)(?:,?\s+(?:Co|Ltd|Inc|LLC|LLP|LP|AG|NV|SA|SE|Corp|GmbH|plc|BV|Limited|Incorporated|Corporation)\.?)+$")


def spelling(name: str) -> str:
    """A name as written, without a possessive or the legal form after it."""
    return LEGAL_FORM.sub("", POSSESSIVE.sub("", name.strip()))


def _blank(match: re.Match[str]) -> str:
    return " " * len(match.group(0))


def written_lines(path: Path) -> Iterator[tuple[int, str]]:
    """A note's or a draft's lines as the writer wrote them: no code, Sources or Gaps and cautions sections, web
    addresses, domains, source keys, quotations or blockquotes, and no emphasis marks."""
    text = read_draft(path)
    text = BLOCKQUOTE.sub(_blank, text)
    text = QUOTED.sub(lambda match: re.sub(r"[^\n]", " ", match.group(0)), text)
    in_fence = skipped = False
    for line_no, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.strip().startswith("#"):
            skipped = bool(NOT_NOTES.match(line.strip()) or REFERENCE_HEADING.match(line.strip()))
        if skipped:
            continue
        line = DOMAIN.sub(_blank, URL.sub(_blank, CODE_SPAN.sub(_blank, line)))
        yield line_no, EMPHASIS.sub("", KEY.sub(_blank, line))


def names_in(line: str) -> Iterator[tuple[str, bool]]:
    """The proper names a line writes, as (the name, whether it's one word opening a sentence or a cell)."""
    words = list(WORD.finditer(line))
    start = LEAD.match(line)
    lead_end = start.end() if start else 0
    at = 0
    while at < len(words):
        word = words[at]
        if not word.group(0)[0].isupper():
            at += 1
            continue
        run = [word]
        ahead = at + 1
        while ahead < len(words):
            gap = line[run[-1].end():words[ahead].start()]
            if gap.strip(" ") and gap.strip() != "-":
                break
            following = words[ahead].group(0)
            if following[0].isupper():
                run.append(words[ahead])
            # "Bank of America", but not "Jane Doe of Northbridge": a word such as "of" joins only onto a single word.
            elif (following in INSIDE and sum(w.group(0) not in OPENERS for w in run) == 1 and ahead + 1 < len(words)
                  and words[ahead + 1].group(0)[0].isupper() and not line[words[ahead].end():words[ahead + 1].start()].strip()):
                run += [words[ahead], words[ahead + 1]]
                ahead += 1
            else:
                break
            ahead += 1
        at = ahead
        opening = word.start() <= lead_end or bool(OPENS_AFTER.search(line[:word.start()]))
        while run and run[0].group(0) in OPENERS:
            run, opening = run[1:], False
        while run and run[-1].group(0) in INSIDE:
            run = run[:-1]
        if not run:
            continue
        name = spelling(line[run[0].start():run[-1].end()])
        letters = sum(ch.isalpha() for ch in name)
        if len(run) == 1 and name.isupper() and letters >= 6:
            continue  # A heading in capitals, or a marker such as COMPUTED.
        if len(run) == 1 and letters < 4 and not (name.isupper() and letters >= 2):
            continue
        yield name, opening and len(run) == 1


# ---------------------------------------------------------------- grouping

def within(a: str, b: str, most: int) -> bool:
    """Whether two folded names are at most `most` letters apart: a letter changed, added or left out."""
    if abs(len(a) - len(b)) > most:
        return False
    previous = list(range(len(b) + 1))
    for i, letter in enumerate(a, 1):
        current = [i]
        for j, other in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (letter != other)))
        if min(current) > most:
            return False
        previous = current
    return previous[-1] <= most


def alike(a: str, b: str) -> bool:
    """Whether two folded names are one name spelled two ways: a letter apart in a name of six letters or more, two in
    one of ten or more. Not when they differ in their first letter, their digits, or only by a plural's s."""
    if a == b:
        return True
    shorter = min(len(a), len(b))
    if shorter < 6 or a[0] != b[0] or re.sub(r"\D", "", a) != re.sub(r"\D", "", b):
        return False
    if a.rstrip("s") == b.rstrip("s") or a + "es" == b or b + "es" == a:
        return False
    return within(a, b, 2 if shorter >= 10 else 1)


def preferred(ws: Workspace) -> list[str]:
    """The spellings the workspace prefers, from `[names] preferred`. Raises ValueError for a setting it can't use."""
    given = ws.config().get("names", {}).get("preferred", [])
    if not isinstance(given, list) or not all(isinstance(name, str) and name.strip() for name in given):
        raise ValueError(f"[names] preferred in {ws.config_path} must be a list of names, none of them blank.")
    return [name.strip() for name in given]


def variant_pattern(name: str) -> re.Pattern[str]:
    """What finds a name however it's split or joined, in any case and as a plural: the assay's pattern for a
    confidential name, or its letters in order with anything that splits a word allowed between any two of them, so
    "North bridge Robotics" and "NorthBridge-Robotics" are both found for "Northbridge Robotics"."""
    letters = [char for char in name if not char.isspace()]
    plural = "s?" if name[-1].isalpha() and name[-1].lower() != "s" else ""
    own = rf"\b{JOIN.join(re.escape(char) for char in letters)}{plural}\b"
    return re.compile(rf"(?:{assay_names.flexible(name)})|(?:{own})", re.I)


def companions(ws: Workspace) -> list[Path]:
    """The other parts of the report `[proof] companions` names, those that exist. `proof` checks the setting itself."""
    given = ws.config().get("proof", {})
    listed = given.get("companions", []) if isinstance(given, dict) else []
    paths = [ws.root / entry for entry in listed if isinstance(entry, str) and entry.strip()] if isinstance(listed, list) else []
    return [path for path in paths if path.is_file()]


def written_files(ws: Workspace) -> list[Path]:
    """What the writer wrote: the notes, the drafts and the report's companion parts."""
    return [*note_files(ws), *draft_files(ws), *companions(ws)]


def gather(ws: Workspace) -> list[Mention]:
    """Every proper name the notes and drafts write, with where. A single word that opens a sentence or a cell is kept
    only when the same name is capitalised somewhere it doesn't open one."""
    found: list[Mention] = []
    for path in written_files(ws):
        where = path.relative_to(ws.root).as_posix() if path.is_relative_to(ws.root) else path.name
        for line_no, line in written_lines(path):
            found += [Mention(name, where, line_no, opening) for name, opening in names_in(line)]
    named = {fold(mention.spelling) for mention in found if not mention.opening}
    return [mention for mention in found if not mention.opening or fold(mention.spelling) in named]


def groups(ws: Workspace) -> list[Group]:
    """Every name with its spellings, the ones held to a preferred spelling first. Raises ValueError for a `[names]`
    setting that can't be used."""
    mentions = gather(ws)
    wanted = preferred(ws)
    seen = {(mention.spelling, mention.file, mention.line) for mention in mentions}
    # A preferred name split or joined in a way the run of capitals doesn't read, such as "North bridge", is found too.
    for name in wanted:
        pattern = variant_pattern(name)
        for path in written_files(ws):
            where = path.relative_to(ws.root).as_posix() if path.is_relative_to(ws.root) else path.name
            for line_no, line in written_lines(path):
                for match in pattern.finditer(line):
                    written = spelling(match.group(0))
                    if written not in (name, name + "s") and (written, where, line_no) not in seen:
                        seen.add((written, where, line_no))
                        mentions.append(Mention(written, where, line_no))
    by_key: dict[str, list[Mention]] = {}
    for mention in mentions:
        by_key.setdefault(fold(mention.spelling), []).append(mention)
    keys = sorted(by_key)
    parent = {key: key for key in keys}

    def root(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    # Only names that start with the same letter and are close in length can be one name, so each is compared with few.
    by_start: dict[str, list[str]] = {}
    for key in keys:
        by_start.setdefault(key[:1], []).append(key)
    for bucket in by_start.values():
        for i, key in enumerate(bucket):
            for other in bucket[i + 1:]:
                if alike(key, other):
                    parent[root(other)] = root(key)
    # Every spelling close to a preferred one is held to it, even when the preferred spelling itself is written nowhere.
    for name in wanted:
        close = [key for key in keys if alike(key, fold(name))]
        for key in close[1:]:
            parent[root(key)] = root(close[0])
    joined: dict[str, list[Mention]] = {}
    for key in keys:
        joined.setdefault(root(key), []).extend(by_key[key])
    # Each name's places in the order they're read, so of two spellings written as often, the first written leads.
    order = {mention: at for at, mention in reversed(list(enumerate(mentions)))}
    result = []
    for members in (sorted(members, key=order.__getitem__) for members in joined.values()):
        held = next((name for name in wanted if any(fold(m.spelling) == fold(name) or alike(fold(m.spelling), fold(name))
                                                     for m in members)), "")
        result.append(Group(held, tuple(members)))
    return sorted(result, key=lambda group: (not group.held_to, group.label.casefold()))


def check(ws: Workspace) -> list[Group]:
    """The names spelled more than one way, or another way than the workspace prefers. Writes data/names.csv with each
    place a spelling of one of them is written."""
    found = [group for group in groups(ws) if group.variants]
    ws.data.mkdir(parents=True, exist_ok=True)
    with (ws.data / REPORT).open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["name", "preferred", "spelling", "file", "line_no"])
        writer.writerows([group.label, "yes" if group.held_to else "", mention.spelling, mention.file, mention.line]
                         for group in found for mention in group.mentions)
    return found


def run(ws: Workspace, _con: sqlite3.Connection, args: argparse.Namespace) -> int:
    """List each name spelled more than one way, with where each spelling is written. Exits 1 when there is one."""
    try:
        found = check(ws)
    except ValueError as problem:
        print(problem)
        return 1
    for group in found:
        print(f"{group.label}" + (" (preferred)" if group.held_to else ""))
        for written in group.spellings:
            places = [f"{m.file}:{m.line}" for m in group.mentions if m.spelling == written]
            shown = ", ".join(places[:6]) + (f" and {len(places) - 6} more" if len(places) > 6 else "")
            mark = "  " if written == group.label else "! "
            print(f"  {mark}{written:<34} {len(places):>4}  {shown}")
    print(f"{len(found)} name(s) spelled more than one way")
    print(f"wrote {ws.data / REPORT}")
    return 1 if found else 0
