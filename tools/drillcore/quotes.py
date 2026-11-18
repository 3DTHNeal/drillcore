"""Quotations are exact: each direct quotation in the notes is looked for, word for word, in the text of a source it
cites.

A quotation is text in double quotes, straight or curly, of any length, or a Markdown blockquote (`> ...`). Code and web
addresses aren't read, nor are the Sources and Gaps and cautions sections. Before comparing, only what doesn't change
the meaning is evened out on both sides: the text is read the way the assay reads it (accents, compatibility forms
such as ligatures and full-width digits, invisible characters, HTML comments, Markdown emphasis and look-alike
letters folded), then runs of whitespace, curly and straight quotes and apostrophes, the kinds of
dash and the spaces around one, and a word a PDF split across a line with a hyphen. An ellipsis or words in square
brackets mark words left out or put in, so the parts either side are each looked for, in order. Two changes quoting
allows are undone: punctuation closing a part, such as a full stop the writer's sentence put inside the closing mark,
and the case of the first letter, changed to fit the sentence the quotation sits in. Nothing else is forgiven: case,
wording and numbers must match. A quotation that would match if capital letters didn't count says so.

A row cites its sources the way `figures` reads it: by naming a key, or by sitting under a heading or lead-in that
names one. A blockquote with no key of its own takes the keys of the line that introduces it or the one that
attributes it.

Many quotation errors get the words right and the speaker wrong. When the words around a quotation say who said it, a
role ("the chief executive said") or a name ("Jane Doe said", "according to Jane Doe"), and the words are found, the
source must name that person, in any way of writing the role or by the name or its last word, within a few hundred
characters of the passage. One it names only further away is "not_near_speaker", a warning. A quotation with no
attribution, or attributed to someone the source never names at all, is judged on its words alone.

Notes sometimes quote a document that isn't one of their sources, such as a brief they answer. A workspace names such
documents with `[check.quotations] not_sources = ["brief"]`, and a quotation whose sentence or clause names one, or
that sits in a table column whose heading names one, or a blockquote whose lead-in or attribution names one, isn't
looked for: the sources cited beside it were never meant to hold it.
"""
import argparse
import csv
import re
import sqlite3
from collections.abc import Collection, Iterator
from dataclasses import dataclass, replace

from assay import text as assay_text

from . import pages, waivers
from .sourcedb import KEY_TOKEN, NOT_NOTES, URL, keys_by_note, note_files, table_headers
from .workspace import Workspace

SCHEMA = """
CREATE TABLE IF NOT EXISTS note_quotes (
    id INTEGER PRIMARY KEY,
    note_file TEXT, line_no INTEGER, form TEXT,       -- inline | blockquote
    source_keys TEXT, key_basis TEXT, quote TEXT,
    status TEXT, matched_url TEXT, detail TEXT        -- exact | not_found | not_on_cited_page | not_in_cited_section
);                                                    -- | no_text | no_source | not_a_source
"""
# A quotation the source holds, but not at the page or section a pinpoint cites, is a failure like one it doesn't hold.
FAILURES = ("not_found", "not_on_cited_page", "not_in_cited_section")
MISSES = (*FAILURES, "no_text", "no_source")
# Found, but not near the person the note says said it. A warning: the words are right.
ELSEWHERE_IN_SOURCE = "not_near_speaker"
# What the report lists: every quotation not confirmed, and every one confirmed only in part.
REPORTED = (*MISSES, ELSEWHERE_IN_SOURCE)
# What a waiver can accept: a finding, not a quotation that couldn't be judged.
WAIVABLE = (*FAILURES, ELSEWHERE_IN_SOURCE)
REPORT = "quotes_not_found.csv"

# Text in double quotes. Either kind opens and either closes, since notes mix them.
INLINE = re.compile("[\"“]([^\"“”]+)[\"”]")
CODE_SPAN = re.compile(r"`[^`]*`")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
FENCE = re.compile(r"^\s*(```|~~~)")
# A word a PDF broke across two lines with a hyphen: "eco-\nnomic".
WRAP_HYPHEN = re.compile(r"(?<=[^\W\d_])-[ \t]*\n\s*(?=[^\W\d_])")
# Words left out (an ellipsis) or put in (square brackets, as in [sic] or [the company]).
GAP = re.compile(r"\s*(?:\.\.\.|\[[^\]]*\])\s*")
# What's the same character for this check. Soft hyphens and zero-width spaces are dropped.
SAME = str.maketrans({"“": '"', "”": '"', "„": '"', "‟": '"', "‘": "'", "’": "'", "‚": "'", "‛": "'",
                      "′": "'", "″": '"',
                      "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
                      "\xa0": " ", " ": " ", " ": " ", "\xad": "", "​": "", "…": "...",
                      "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"})
# A semicolon ends the clause too: in `(the brief says so); "a quotation"`, the quotation has a clause of its own.
SENTENCE_END = re.compile(r"[.!?;](?=\s|$)")
CAPITALS = "; it matches if capital letters are ignored"


@dataclass(frozen=True)
class Quote:
    """One quotation in a note, and once checked, what became of it."""
    note_file: str
    line_no: int
    form: str               # inline | blockquote
    text: str               # as the note writes it
    keys: tuple[str, ...]
    key_basis: str          # row | lead-in | attribution | section
    status: str = ""        # exact | not_near_speaker | not_found | not_on_cited_page | not_in_cited_section | no_text | no_source | not_a_source
    matched_url: str | None = None
    detail: str = ""
    # Who the note says said it, a role such as "chief executive" or a name, or "" when it doesn't say.
    speaker: str = ""
    # The page or section a key is cited at, where the keys' line gives one: `S1 p.47`.
    pins: tuple[pages.Pin, ...] = ()


def readable(text: str) -> str:
    """Text as a reader sees it, as the assay reads it: compatibility forms folded, accents, invisible characters, HTML
    comments and Markdown emphasis gone, and look-alike letters read as the plain letter."""
    return assay_text.matchable(text)


def normalise(text: str) -> str:
    """Text with only what doesn't change its meaning evened out: quote marks, dashes, ligatures and whitespace."""
    text = re.sub(r"\s+", " ", text.translate(SAME))
    return re.sub(r" ?-+ ?", "-", text).strip()


def source_forms(text: str) -> tuple[str, ...]:
    """A source's text as it's searched: read and normalised, and again with any word a line break hyphenated put back
    together, since "well-\\nknown" and "eco-\\nnomic" can't be told apart."""
    joined = WRAP_HYPHEN.sub("", text)
    whole = normalise(readable(text))
    return (whole,) if joined == text else (whole, normalise(readable(joined)))


def pieces(quote: str) -> list[str]:
    """What must appear in the source, in order: the quotation read and normalised, split at each ellipsis or
    bracketed insertion, without the punctuation at either end of a part."""
    parts = (part.strip(" .,;:") for part in GAP.split(normalise(readable(quote))))
    return [part for part in parts if part]


def located(parts: list[str], text: str) -> tuple[int, int] | None:
    """Where in the text every part is, each after the one before it, as (where the first starts, where the last ends),
    or None. The first letter of the first part may be in either case, since a quotation is fitted to the sentence it
    opens or continues."""
    at = 0
    start = -1
    for number, part in enumerate(parts):
        found = text.find(part, at)
        if found < 0 and number == 0 and part[:1].isalpha():
            found = text.find(part[0].swapcase() + part[1:], at)
        if found < 0:
            return None
        start = found if number == 0 else start
        at = found + len(part)
    return (start, at) if parts else None


def appears_in(parts: list[str], text: str) -> bool:
    """Whether every part is in the text, each after the one before it, as `located` finds them."""
    return located(parts, text) is not None


def case_only(parts: list[str], forms: Collection[str]) -> bool:
    """Whether a quotation that isn't in a source would be, if capital letters didn't count."""
    lowered = [part.lower() for part in parts]
    return any(appears_in(lowered, form.lower()) for form in forms)


def closest(parts: list[str], texts: dict[str, tuple[str, ...]]) -> str:
    """How much of a quotation that wasn't found is there: the most of its opening words any one source holds."""
    words = " ".join(parts).split(" ")
    best, where = 0, ""
    for url, forms in texts.items():
        low, high = best, len(words)
        while low < high:  # Each opening that's there has every shorter one there too.
            middle = (low + high + 1) // 2
            if any(" ".join(words[:middle]) in form for form in forms):
                low = middle
            else:
                high = middle - 1
        if low > best:
            best, where = low, url
    if not best:
        return "no run of its opening words is in the cited text"
    return f'the first {best} of {len(words)} words are in {where}; it parts at "{words[best]}"'


# ---------------------------------------------------------------- documents that aren't sources

def not_sources(ws: Workspace) -> re.Pattern[str] | None:
    """The workspace's words for documents its notes quote that aren't sources in the database, such as a brief the
    notes are answering: `[check.quotations] not_sources = ["brief"]`. None when it names none."""
    words = [str(word) for word in ws.config().get("check", {}).get("quotations", {}).get("not_sources", []) if str(word).strip()]
    return re.compile(r"\b(?:" + "|".join(re.escape(word.strip()) for word in words) + r")\b", re.I) if words else None


def surroundings(text: str, start: int, end: int, header: list[str]) -> str:
    """The words a quotation is attributed by: in a table row, its own cell and that column's heading; elsewhere, the
    sentence or clause it stands in."""
    if text.startswith("|"):
        left, right = text.rfind("|", 0, start), text.find("|", end)
        column = text[:left].count("|")
        return text[left + 1:right if right >= 0 else len(text)] + " | " + (header[column] if column < len(header) else "")
    ends = [m.end() for m in SENTENCE_END.finditer(text, 0, start)]
    after = SENTENCE_END.search(text, end)
    return text[ends[-1] if ends else 0:after.start() if after else len(text)]


def _attributed(elsewhere: re.Pattern[str] | None, words: str) -> str:
    """The detail for a quotation attributed to a document that isn't a source, or "" when the words name none."""
    named = elsewhere.search(words) if elsewhere else None
    return f"attributed to the {named.group(0).lower()}, which the workspace lists as not a source" if named else ""


# ---------------------------------------------------------------- who said it

# Roles a note attributes a quotation to, each with the other ways a source writes the same role.
ROLES = (("chief executive officer", "chief executive", "CEO"),
         ("chief financial officer", "finance director", "CFO"),
         ("chief operating officer", "COO"),
         ("chief technology officer", "CTO"),
         ("chairman", "chairwoman", "chairperson", "chair"),
         ("managing director",),
         ("president",),
         ("co-founder", "founder"),
         ("spokesperson", "spokesman", "spokeswoman"))
ROLE = re.compile(r"\b(?:" + "|".join(re.escape(word) for group in ROLES for word in group) + r")\b", re.I)
# The words that say someone said it. "According to" comes before the speaker, the rest either side.
SAYS = r"(?:said|says|told|tells|wrote|writes|added|adds|stated|states|noted|notes|explained|explains|remarked|recalled)"
# A name as a note writes one: up to four capitalised words, as "Jane Doe" or "Mary-Ann van Dijk" without the "van".
_NAME = r"[A-Z][\w'’.\-]*[a-z][\w'’\-]*(?:\s+[A-Z][\w'’.\-]*[a-z][\w'’\-]*){0,3}"
# Only the name must be capitalised: "Said Jane Doe" and "According to Jane Doe" open sentences.
NAMED = re.compile(rf"(?P<before>{_NAME})\s*,?\s+(?i:{SAYS})\b|\b(?i:{SAYS})\s+(?P<after>{_NAME})|\b(?i:according to)\s+(?P<per>{_NAME})")
# Capitalised words that open a sentence or stand for someone without naming them.
NOT_NAMES = frozenset({"The", "A", "An", "He", "She", "It", "They", "We", "I", "You", "This", "That", "These", "Those", "Its",
                       "Their", "His", "Her", "Our", "Who", "Which", "And", "But", "As", "In", "On", "At", "For", "Then",
                       "Also", "Release", "Report", "Letter", "Filing", "Statement", "Company", "Management", "Board",
                       "Analysts", "Investors", "Officials", "Executives", "Annual", "Sources", "Critics"})
# How far either side of a quotation, in characters of the source, its speaker must be named.
NEAR = 300


def speaker_of(words: str, at: int | None = None) -> str:
    """Who some words say said a quotation: a role ("the chief executive said"), or a name next to a word of saying
    ("Jane Doe said", "said Jane Doe", "according to Jane Doe"). `at` is where the quotation stands in the words; when
    they name more than one person, the one nearest it said it, so "Doe said "...", and the founder added "..."" gives
    each quotation its own speaker. "" when they name nobody, as with "he said"."""
    found: list[tuple[int, int, str]] = []
    if re.search(rf"\b{SAYS}\b|:|\baccording to\b", words, re.I):
        found += [(role.start(), role.end(), role.group(0)) for role in ROLE.finditer(words)]
    for match in NAMED.finditer(words):
        group = "before" if match.group("before") else "after" if match.group("after") else "per"
        kept = match.group(group).split()
        while kept and kept[0] in NOT_NAMES:
            kept = kept[1:]
        if kept:
            found.append((match.start(group), match.end(group), " ".join(kept)))
    if not found:
        return ""
    if at is None:
        return min(found)[2]
    return min(found, key=lambda span: (max(span[0] - at, at - span[1], 0), span[0]))[2]


def speaker_pattern(speaker: str) -> re.Pattern[str]:
    """What names a speaker in a source's text: any way of writing their role, or for a name, the name itself or its
    last word, the surname a source uses after the first mention."""
    for group in ROLES:
        if speaker.lower() in (word.lower() for word in group):
            return re.compile(r"\b(?:" + "|".join(re.escape(normalise(readable(word))) for word in group) + r")\b", re.I)
    name = normalise(readable(speaker))
    words = [re.escape(name)] + ([re.escape(name.split()[-1])] if len(name.split()) > 1 and len(name.split()[-1]) > 2 else [])
    return re.compile(r"\b(?:" + "|".join(words) + r")\b")


def speaker_detail(speaker: str, form: str, span: tuple[int, int], url: str) -> str:
    """Why a quotation found in a source isn't near the person the note attributes it to, or "" when it is, or when the
    source names that person nowhere and so can't say."""
    pattern = speaker_pattern(speaker)
    if not pattern.search(form):
        return ""
    start, end = span
    if pattern.search(form, max(0, start - NEAR), min(len(form), end + NEAR)):
        return ""
    return (f"the words are in {url}, but the note says {speaker!r} said them, and the source names them only more "
            f"than {NEAR} characters away from the passage")


# ---------------------------------------------------------------- finding quotations

@dataclass
class _Block:
    kind: str               # prose | item | table | blockquote
    line_no: int
    lines: list[str]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _blocks(text: str) -> Iterator[tuple[str, _Block | None]]:
    """A note's body in the pieces Markdown makes of it, in order: each heading as (its text, None), and each
    paragraph, list item, table row and blockquote as ("", the block). A list item takes in the lines that carry it
    on. Code blocks and the Sources section are left out."""
    current: _Block | None = None
    in_fence = in_sources = False
    for line_no, line in enumerate(text.splitlines(), 1):
        row = line.strip()
        fence = bool(FENCE.match(line))
        if current:
            if current.kind == "blockquote":
                carries_on = row.startswith(">")
            else:
                carries_on = bool(row) and not (fence or row.startswith(("#", "|", ">")) or LIST_ITEM.match(line))
            if fence or not carries_on:
                yield "", current
                current = None
        if fence:
            in_fence = not in_fence
        if in_fence or fence or not row:
            continue
        if row.startswith("#"):
            in_sources = bool(NOT_NOTES.match(row))
            yield row, None
            continue
        if in_sources:
            continue
        if row.startswith(">"):
            quoted = re.sub(r"^>\s?", "", row)
            if current:
                current.lines.append(quoted)
            else:
                current = _Block("blockquote", line_no, [quoted])
        elif row.startswith("|"):
            yield "", _Block("table", line_no, [row])
        elif current:
            current.lines.append(row)
        else:
            current = _Block("item" if LIST_ITEM.match(line) else "prose", line_no, [row])
    if current:
        yield "", current


def _blockquote_text(text: str, known: Collection[str]) -> str:
    """A blockquote's words without the citation after them, as in "(S3)" or "-- S3", or the quote marks around them."""
    key = "|".join(re.escape(k) for k in sorted(known, key=len, reverse=True)) or r"(?!)"
    cited = rf"(?:{key})(?:\s*[,;]\s*(?:{key}))*"
    text = re.sub(rf"\s*(?:[-–—]+\s*)?[(\[]?\s*{cited}\s*[)\]]?[.,]?\s*$", "", text.strip())
    if len(text) > 1 and text[0] in "\"“" and text[-1] in "\"”" and not INLINE.search(text[1:-1]):
        text = text[1:-1]
    return text.strip()


def find_quotes(note_file: str, text: str, known: Collection[str], elsewhere: re.Pattern[str] | None = None) -> list[Quote]:
    """Every quotation in a note, with the keys it cites. `known` is the keys the note can use; anything else that
    looks like a key isn't one. `elsewhere` matches the names of documents that aren't sources: a quotation attributed
    to one comes back with the status "not_a_source"."""
    found: list[Quote] = []
    blocks = list(_blocks(text))
    headers = table_headers(text) if elsewhere else {}
    section: list[str] = []
    section_pins: dict[str, pages.Pin] = {}

    def keys_in(block: _Block | None) -> list[str]:
        return [key for key in dict.fromkeys(KEY_TOKEN.findall(block.text)) if key in known] if block else []

    def pins_for(keys: list[str], *blocks: _Block | None) -> tuple[pages.Pin, ...]:
        """The pinpoints the keys are cited with, in the blocks they're read from, or under the section's heading."""
        given = {**section_pins}
        for block in blocks[::-1]:
            if block:
                given.update(pages.pins_in(block.text, known))
        return tuple(pin for key, pin in given.items() if key in keys)

    def blank(match: re.Match[str]) -> str:
        return " " * len(match.group(0))

    for at, (heading, block) in enumerate(blocks):
        if block is None:
            section = [key for key in dict.fromkeys(KEY_TOKEN.findall(heading)) if key in known]
            section_pins = pages.pins_in(heading, known)
            continue
        own = keys_in(block)
        if block.kind == "blockquote":
            before = blocks[at - 1][1] if at else None
            after = blocks[at + 1][1] if at + 1 < len(blocks) else None
            lead_in = before if before and before.kind == "prose" else None
            attribution = after if after and after.kind == "prose" else None
            keys, basis = next(((k, b) for k, b in ((own, "row"), (keys_in(lead_in), "lead-in"), (keys_in(attribution), "attribution"))
                                if k), (section, "section"))
            quoted = " ".join(_blockquote_text(block.text, own).split())
            if quoted:
                # Said by the last sentence of its lead-in, or the first of its attribution.
                said_by = (SENTENCE_END.split(lead_in.text.rstrip(" .!?;"))[-1] if lead_in else "") + " | " + (
                    SENTENCE_END.split(attribution.text)[0] if attribution else "")
                why = _attributed(elsewhere, said_by)
                found.append(Quote(note_file, block.line_no, "blockquote", quoted, tuple(keys), basis,
                                   "not_a_source" if why else "", detail=why, speaker=speaker_of(said_by, said_by.index(" | ")),
                                   pins=pins_for(keys, block, lead_in, attribution)))
            continue
        keys, basis = (own, "row") if own else (section, "section")
        pins = pins_for(keys, block) if own else pins_for(keys)
        body = URL.sub(blank, CODE_SPAN.sub(blank, block.text))
        # The words around a quotation, without any quotation's own words, say who said it: in a table, the whole row.
        unquoted = INLINE.sub(blank, body)
        for match in INLINE.finditer(body):
            quoted = " ".join(match.group(1).split())
            if quoted:
                line_no = block.line_no + body.count("\n", 0, match.start())
                why = _attributed(elsewhere, surroundings(body, match.start(), match.end(), headers.get(line_no, [])))
                if body.startswith("|"):
                    around, at = unquoted, match.start()
                else:
                    around = surroundings(unquoted, match.start(), match.end(), [])
                    opened = [end.end() for end in SENTENCE_END.finditer(unquoted, 0, match.start())]
                    at = match.start() - (opened[-1] if opened else 0)
                found.append(Quote(note_file, line_no, "inline", quoted, tuple(keys), basis, "not_a_source" if why else "",
                                   detail=why, speaker=speaker_of(around, at), pins=pins))
        if block.kind == "prose":
            # Prose under a heading can name the sources for what follows it.
            section += [key for key in own if key not in section]
            section_pins = {**pages.pins_in(block.text, known), **section_pins}
    return found


# ---------------------------------------------------------------- checking them

def examine(ws: Workspace, con: sqlite3.Connection) -> list[Quote]:
    """Look for each quotation in the notes in the text of a source it cites, and return every quotation with its
    status. Nothing is written."""
    cache: dict[str, tuple[str, ...] | None] = {}
    raw: dict[str, str] = {}

    def forms_of(url: str) -> tuple[str, ...] | None:
        if url not in cache:
            row = con.execute("SELECT text FROM documents WHERE url=?", (url,)).fetchone()
            raw[url] = row[0] if row and row[0] else ""
            cache[url] = source_forms(row[0]) if row and row[0] else None
        return cache[url]

    def at_pinpoint(quote: Quote, parts: list[str], holding: list[str], urls_by_key: dict[str, list[str]]) -> Quote:
        """The quotation, found in each of `holding`, held to the page or section its key is cited at."""
        pinned = {url: pin for pin in quote.pins for url in urls_by_key.get(pin.key, [])}
        missed: tuple[str, pages.Pin, str] | None = None
        for url in holding:
            pin = pinned.get(url)
            if not pin:
                return replace(quote, status="exact", matched_url=url)
            stretches, why = pages.region(con, url, raw[url], pin)
            if stretches is None:
                return replace(quote, status="exact", matched_url=url, detail=f"{pin.shown()} not judged: {why}")
            if any(appears_in(parts, form) for form in source_forms(pages.region_text(raw[url], stretches))):
                return replace(quote, status="exact", matched_url=url)
            missed = missed or (url, pin, why)
        assert missed
        url, pin, why = missed
        return replace(quote, status=pages.status_for(pin), matched_url=url,
                       detail=f"in {url}, but not at {pin.where}" + (f": {why}" if why else ""))

    paths = note_files(ws)
    usable = keys_by_note(con, [path.name for path in paths], ws.config().get("notes", {}).get("borrows", {}))
    elsewhere = not_sources(ws)
    results: list[Quote] = []
    for path in paths:
        urls_by_key = usable[path.name]
        for quote in find_quotes(path.name, path.read_text(encoding="utf-8"), urls_by_key, elsewhere):
            if quote.status:
                results.append(quote)
                continue
            texts = {url: forms for key in quote.keys for url in urls_by_key.get(key, []) if (forms := forms_of(url))}
            parts = pieces(quote.text)
            if not quote.keys:
                quote = replace(quote, status="no_source", detail="the line cites no source")
            elif not texts:
                quote = replace(quote, status="no_text", detail="no text was fetched for the sources it cites")
            else:
                holding = [url for url, forms in texts.items() if any(located(parts, form) for form in forms)]
                if holding:
                    quote = at_pinpoint(quote, parts, holding, urls_by_key)
                    if quote.status == "exact" and quote.speaker and quote.matched_url:
                        url = quote.matched_url
                        form, span = next((form, span) for form in texts[url] if (span := located(parts, form)))
                        away = speaker_detail(quote.speaker, form, span, url)
                        if away:
                            quote = replace(quote, status=ELSEWHERE_IN_SOURCE, detail="; ".join(filter(None, (away, quote.detail))))
                else:
                    capitals = case_only(parts, [form for forms in texts.values() for form in forms])
                    quote = replace(quote, status="not_found", detail=closest(parts, texts) + (CAPITALS if capitals else ""))
            results.append(quote)
    return results


def check(ws: Workspace, con: sqlite3.Connection) -> list[Quote]:
    """Look for each quotation in the notes in the text of a source it cites. Writes the note_quotes table and
    data/quotes_not_found.csv, and returns every quotation with its status."""
    results = examine(ws, con)
    con.executescript(SCHEMA)
    con.execute("DELETE FROM note_quotes")
    con.executemany("INSERT INTO note_quotes(note_file, line_no, form, source_keys, key_basis, quote, status, matched_url, detail)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    [(quote.note_file, quote.line_no, quote.form, ",".join(quote.keys), quote.key_basis, quote.text,
                      quote.status, quote.matched_url, quote.detail) for quote in results])
    con.commit()
    ws.data.mkdir(parents=True, exist_ok=True)
    with (ws.data / REPORT).open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["note_file", "line_no", "form", "source_keys", "key_basis", "status", "quote", "detail"])
        writer.writerows([quote.note_file, quote.line_no, quote.form, ",".join(quote.keys), quote.key_basis, quote.status,
                          quote.text, quote.detail] for quote in results if quote.status in REPORTED)
    return results


def run(ws: Workspace, con: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Check the quotations and say how each note fared and which weren't confirmed. Exits 1 when a quotation isn't
    in the source it cites, or isn't at the page or section cited."""
    results = check(ws, con)
    if not results:
        print("no quotations in the notes")
    counts: dict[tuple[str, str], int] = {}
    for quote in results:
        counts[(quote.note_file, quote.status)] = counts.get((quote.note_file, quote.status), 0) + 1
    for (note, status), count in sorted(counts.items()):
        print(f"{note:<44} {status:<16} {count:>5}")
    # A quotation not found, or a warning about one, that a row of checks/waivers.csv accepts is listed as waived and
    # doesn't fail the run.
    ledger = waivers.Ledger(ws, con)
    failed = 0
    for quote in results:
        if quote.status in REPORTED:
            short = quote.text if len(quote.text) <= 100 else quote.text[:97] + "..."
            decision = ledger.decide("quotations", quote.note_file, quote.line_no, quote.text, quote.keys) if quote.status in WAIVABLE else None
            if decision and not decision.lapsed:
                print(f"  {quote.note_file}:{quote.line_no} waived [{','.join(quote.keys) or '-'}] \"{short}\"\n    {decision.waiver.said()}")
                continue
            failed += quote.status in FAILURES
            print(f"  {quote.note_file}:{quote.line_no} {quote.status} [{','.join(quote.keys) or '-'}] \"{short}\"")
            if quote.detail:
                print(f"    {quote.detail}")
            if decision:
                print(f"    {waivers.lapsed_message(decision)}")
    for waiver in ledger.unused(("quotations",)):
        print(f"  warning: {waivers.unused_message(waiver)}")
    print(f"wrote {ws.data / REPORT}")
    return 1 if failed else 0
