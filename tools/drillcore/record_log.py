"""A record held to the log it's compiled from: an appendix of AI-use citations, say, against the log of prompts kept
day by day. `proof` runs this as its `records` check for each `[[proof.record_logs]]` the workspace sets.

The log is a numbered list at the margin, each entry in the form a citation guide asks for: "12. Helper AI.
helper.example. November 10, 2026. "The prompt, word for word."", with any follow-up after "exact wording:". An
entry runs to the next entry or the next heading. The record gives each entry under "**Entry 12.**", with "URL:" and
"Date:" lines and the prompts in quotation marks.

- Each entry of the log has an entry of the record, and each entry of the record one of the log.
- The record's "Date:" is the date the log entry opens with, and its "URL:" is on the log entry's first line.
- Each quotation in a record's entry is in the log's entry of the same number, word for word, apart from spacing,
  curly quotes and Markdown's escapes. "…" or a bracketed note in a quotation stands for words left out, so what is
  on either side of it must be there, in order.
- Each prompt the log quotes as the author's is quoted in the record: the quotation straight after an entry's date,
  each one after "exact wording:" and those joined to it by "and", "then", a comma or a semicolon, and a block quote
  after "exact wording:". A quotation of the record that leaves words out with "…" covers it. So does a file the
  settings name under `cuts`, kept to say what was left out on purpose, when a heading of it names that entry
  ("## Entry 5: ...") and the section under it gives the prompt.
- "entry 12" in a record's entry names an entry the record has, and "that entry" follows an "entry 12" in the same
  entry, or else it points nowhere (a warning, since the entry may be named some other way).

With the sessions' own records (`sessions`, which reads an assistant's transcripts), both are held to what was typed:

- Each prompt typed in a session is in the log or a cuts file, word for word apart from spacing. A message that quotes
  the assistant's words first and then answers them counts as logged when its answer is: the paragraphs after the
  quoted ones. A session none of whose prompts is anywhere in them is reported once, as a session with no entry. This
  is how a session that never logged itself shows, and so does a follow-up a log entry summed up rather than quoted, or
  a reworded prompt said to be "the same".
- Each prompt the record quotes (a quotation on a line that names a prompt or a follow-up, "Exact final prompt:" or
  "Follow-up:") is the whole of a message typed, or else leaves its cuts marked with "…" or a bracketed note. One that
  is only part of what was typed fails, saying what came before or after it, and so does one message given as two
  quotations. A quotation no typed message holds is passed over: a button's label or a question the assistant asked
  isn't typed, and a session kept elsewhere can't be read. So is a message that holds it in quotation marks of its own,
  since that message quotes the prompt rather than being it.

What a record says about the work done is the author's to check: whether an entry gives all that the log says, or
says more, isn't read here, and nor is which session of an entry a follow-up belongs to.
"""
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from .sessions import Prompt

MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
DATE = re.compile(rf"\b{MONTH} \d{{1,2}}, \d{{4}}\b|\b\d{{4}}-\d{{2}}-\d{{2}}\b")
LOG_ENTRY = re.compile(r"^(?P<number>\d{1,4})\.\s+\S")
HEADING = re.compile(r"^#{1,6}\s")
RECORD_ENTRY = re.compile(r"^[\s*_#>]*Entry\s+(?P<number>\d+)\s*[.:*]", re.I)
QUOTATION = re.compile(r"[\"“](?P<words>[^\"“”]+?)[\"”]")
OPENING = re.compile(r"[\"“](?P<words>[^\"“”]+?)[\"”]")
# Words left out of a quotation: an ellipsis, or a note in square brackets in their place.
GAP = re.compile(r"\s*(?:…|\.\.\.|\[[^\]]*\])\s*")
EXACT = re.compile(r"exact wording:\s*", re.I)
JOINED = re.compile(r"\s*(?:;|,|and|then|,\s*then|;\s*then|,\s*and)\s*(?=[\"“])")
BLOCK = re.compile(r"(?:[ \t]*>.*(?:\n|$))+")
URL_LINE = re.compile(r"^\W*URL:\s*(?P<url>\S+)", re.M)
DATE_LINE = re.compile(rf"^\W*Date:\s*(?P<date>{DATE.pattern})", re.M)
ENTRY_REF = re.compile(r"\b[Ee]ntr(?:y|ies)\s+(?P<number>\d+)")
THAT_ENTRY = re.compile(r"\bthat entry\b", re.I)
# A line of a record that gives a prompt: its label, before the colon, names a prompt or starts with a follow-up.
PROMPT_LINE = re.compile(r"^[\s>*_-]*(?:[^:\"“\n]*\bprompt\b[^:\"“\n]*|follow-ups?\b[^:\"“\n]*):", re.I)
PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")
# A quotation held to the message it comes from needs this many words: a short one, "Yes, fix it", is often said
# again inside a longer message, and is too short to be cut.
WHOLE_WORDS = 5


@dataclass(frozen=True)
class Entry:
    number: int
    line: int       # the line of the file it starts on
    text: str


@dataclass(frozen=True)
class Finding:
    line: int
    verdict: str    # "fail" or "warn"
    item: str
    detail: str


def plain(text: str) -> str:
    """Text as a quotation is compared: Markdown's escapes dropped, curly apostrophes straight, spacing single."""
    text = re.sub(r"\\(?=[\[\]()*_`#>\\.-])", "", text).replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text).strip()


def log_entries(text: str) -> dict[int, Entry]:
    """The log's entries: the run of numbers at the margin that starts with its first, each entry to the next one,
    and the last to the next heading. A numbered list under a later heading, such as the log's own notes, isn't one."""
    found: dict[int, Entry] = {}
    lines = text.split("\n")
    open_at: tuple[int, int] | None = None

    def close(end: int) -> None:
        if open_at is not None:
            number, start = open_at
            found.setdefault(number, Entry(number, start + 1, "\n".join(lines[start:end])))

    end = len(lines)
    for at, line in enumerate(lines):
        if HEADING.match(line) and open_at is not None:
            end = at
            break
        entry = LOG_ENTRY.match(line)
        if entry:
            close(at)
            open_at = (int(entry.group("number")), at)
    close(end)
    return found


def record_entries(text: str) -> dict[int, Entry]:
    """The record's entries, each from its "**Entry 12.**" to the next one or the next heading."""
    found: dict[int, Entry] = {}
    lines = text.split("\n")
    open_at: tuple[int, int] | None = None

    def close(end: int) -> None:
        if open_at is not None:
            number, start = open_at
            found.setdefault(number, Entry(number, start + 1, "\n".join(lines[start:end])))

    for at, line in enumerate(lines):
        entry = RECORD_ENTRY.match(line.strip())
        if entry:
            close(at)
            open_at = (int(entry.group("number")), at)
        elif HEADING.match(line) and open_at is not None:
            close(at)
            open_at = None
    close(len(lines))
    return found


def _pieces(quotation: str) -> list[str]:
    return [piece for piece in GAP.split(plain(quotation)) if piece]


def found_in(quotation: str, text: str, whole: bool = False) -> bool:
    """Whether a quotation's words are in the text, in order, with "…" or a bracketed note standing for words left
    out. Whole, they must be all of it: from its start, unless the quotation opens with a cut, to its end, unless it
    closes with one."""
    said, pieces, text = plain(quotation), _pieces(quotation), plain(text)
    at = 0
    for index, piece in enumerate(pieces):
        place = text.find(piece, at)
        if place < 0 or (whole and index == 0 and place != 0 and not GAP.match(said)):
            return False
        at = place + len(piece)
    return not whole or at == len(text) or bool(re.search(r"(?:…|\.\.\.|\])$", said))


def prompts(entry: str) -> list[str]:
    """The prompts a log entry quotes as the author's, in order."""
    found = []
    date = DATE.search(entry)
    if date:
        first = re.match(r"\.\s*" + OPENING.pattern, entry[date.end():])
        if first:
            found.append(first.group("words"))
    # "exact wording:" inside a quotation is the log talking about the phrase, not marking a prompt.
    spans = [(match.start(), match.end()) for match in QUOTATION.finditer(entry)]
    for mark in EXACT.finditer(entry):
        if any(start < mark.start() < end for start, end in spans):
            continue
        rest = entry[mark.end():]
        block = BLOCK.match(rest.lstrip("\n")) if rest[:1] in ("\n", ">") else None
        if block:
            found.append(re.sub(r"^[ \t]*> ?", "", block.group(0), flags=re.M))
            continue
        while quoted := OPENING.match(rest):
            found.append(quoted.group("words"))
            rest = rest[quoted.end():]
            joined = JOINED.match(rest)
            if not joined:
                break
            rest = rest[joined.end():]
    return found


def cut_sections(texts: list[str]) -> dict[int, str]:
    """What the files kept on purpose say for each entry: the sections under a heading naming "Entry 12", joined."""
    found: dict[int, str] = {}
    for text in texts:
        number = None
        for line in text.split("\n"):
            if HEADING.match(line):
                named = re.search(r"\bEntry\s+(\d+)\b", line, re.I)
                number = int(named.group(1)) if named else None
            elif number is not None:
                found[number] = found.get(number, "") + "\n" + re.sub(r"^[ \t]*> ?", "", line)
    return found


def flat(text: str) -> str:
    """Text as a typed message is compared: as `plain`, with curly double quotation marks straight too."""
    return plain(text).replace("“", '"').replace("”", '"')


def answers(text: str) -> list[str]:
    """A message, and each run of its last paragraphs: what a person wrote after quoting the assistant's words."""
    parts = PARAGRAPH_BREAK.split(text.strip())
    return ["\n\n".join(parts[at:]) for at in range(len(parts))]


def _when(at: str) -> str:
    return f"{at[:10]} {at[11:16]} UTC" if len(at) >= 16 else at or "an unknown time"


def unlogged(typed: Sequence[Prompt], log: str, cuts: list[str], log_name: str) -> Iterator[Finding]:
    """Each prompt typed in a session that neither the log nor a cuts file quotes; a session with none of its prompts
    there, once."""
    said = " ".join(flat(re.sub(r"^[ \t]*> ?", "", text, flags=re.M)) for text in (log, *cuts))
    sessions: dict[str, list[Prompt]] = {}
    for prompt in typed:
        sessions.setdefault(prompt.session, []).append(prompt)
    for session, prompts in sessions.items():
        missing = [prompt for prompt in prompts if not any(flat(answer) in said for answer in answers(prompt.text))]
        if not missing:
            continue
        if len(missing) == len(prompts):
            count = f"{len(prompts)} prompt" + ("s" if len(prompts) > 1 else "")
            yield Finding(0, "fail", f"session {session[:8]} ({_when(prompts[0].at)})",
                          f"none of its {count} is in {log_name} or a cuts file, so it has no entry; the first is "
                          f"\"{flat(prompts[0].text)[:80]}\"")
            continue
        for prompt in missing:
            yield Finding(0, "fail", f"\"{flat(prompt.text)[:80]}\"",
                          f"typed in session {session[:8]} on {_when(prompt.at)}, and neither {log_name} nor a cuts "
                          "file quotes it")


def _quoting(words: str, message: str) -> bool:
    """Whether a message holds the words inside quotation marks of its own: it quotes them rather than being them."""
    text, pieces = flat(message), [flat(piece) for piece in _pieces(words)]
    start = text.find(pieces[0])
    end = text.find(pieces[-1], start) + len(pieces[-1])
    return start > 0 and text[start - 1] == '"' and end < len(text) and text[end] == '"'


def part_quoted(entry: Entry, typed: Sequence[Prompt]) -> Iterator[Finding]:
    """Each prompt the record's entry quotes that is only part of the message it comes from: once a message."""
    lines = [line for line in entry.text.split("\n") if PROMPT_LINE.match(line)]
    quoted = [found.group("words") for line in lines for found in QUOTATION.finditer(line)]
    reported: set[str] = set()
    for words in quoted:
        if len(plain(words).split()) < WHOLE_WORDS:
            continue
        holding = [prompt for prompt in typed if found_in(words, prompt.text) and not _quoting(words, prompt.text)]
        if not holding or any(found_in(words, answer, whole=True) for prompt in holding for answer in answers(prompt.text)):
            continue
        prompt = min(holding, key=lambda found: len(found.text))
        if prompt.text in reported:
            continue
        reported.add(prompt.text)
        text, pieces = flat(prompt.text), [flat(piece) for piece in _pieces(words)]
        start = text.find(pieces[0])
        end = text.find(pieces[-1], start) + len(pieces[-1])
        before, after = text[:start].strip(), text[end:].strip()
        where = f"session {prompt.session[:8]}, {_when(prompt.at)}"
        other = next((flat(more) for more in quoted if more is not words and flat(more) and
                      (flat(more) in before or flat(more) in after)), None)
        if other:
            detail = (f"one message ({where}) is given as two quotations; the rest of it is \"{other[:60]}\". "
                      "Quote it as one")
        else:
            said = ([f"begins \"{before[-60:]}\" before it"] if before else []) + \
                   ([f"goes on \"{after[:60]}\" after it"] if after else [])
            detail = (f"only part of what was typed ({where}): the message {' and '.join(said)}. Quote it whole, "
                      "or mark what's left out with … or a bracketed note")
        yield Finding(entry.line, "fail", f"entry {entry.number}: \"{flat(words)[:80]}\"", detail)


def check(record: str, log: str, cuts: list[str], log_name: str, typed: Sequence[Prompt] = ()) -> Iterator[Finding]:
    """Each way the record differs from the log, in the record's order, then entries the record lacks. With the
    sessions' prompts, each prompt the record quotes in part too; what the log lacks of them is `unlogged`'s."""
    logged, kept = log_entries(log), record_entries(record)
    cut = cut_sections(cuts)
    for number, entry in sorted(kept.items()):
        what = f"entry {number}"
        source = logged.get(number)
        if source is None:
            yield Finding(entry.line, "fail", what, f"{log_name} has no entry {number}")
            continue
        where = f"{log_name}:{source.line}"
        opened = DATE.search(source.text)
        dated = DATE_LINE.search(entry.text)
        if opened and dated and dated.group("date") != opened.group(0):
            yield Finding(entry.line, "fail", f"{what}: {dated.group('date')}", f"the log's entry is dated {opened.group(0)} ({where})")
        url = URL_LINE.search(entry.text)
        if url and url.group("url") not in source.text.split("\n")[0]:
            yield Finding(entry.line, "fail", f"{what}: {url.group('url')}", f"not the address the log's entry gives ({where})")
        quoted = [found.group("words") for found in QUOTATION.finditer(entry.text)]
        for words in quoted:
            if not found_in(words, source.text):
                yield Finding(entry.line, "fail", f"{what}: \"{plain(words)[:80]}\"", f"not in the log's entry word for word ({where})")
        for prompt in prompts(source.text):
            if any(found_in(words, prompt, whole=True) for words in quoted):
                continue
            if plain(prompt)[:60] and plain(prompt)[:60] in plain(cut.get(number, "")):
                continue
            yield Finding(entry.line, "fail", f"{what}: \"{plain(prompt)[:80]}\"",
                          f"the log quotes this prompt ({where}) and the record doesn't; quote it, or say in a cuts file why it's left out")
        # What the entry says under its own "**Entry 12.**", which names itself.
        body = entry.text.partition("\n")[2]
        named = [int(found.group("number")) for found in ENTRY_REF.finditer(body)]
        for other in named:
            if other not in kept:
                yield Finding(entry.line, "fail", f"{what}: entry {other}", "names an entry the record doesn't have")
        that = THAT_ENTRY.search(body)
        if that and not ENTRY_REF.search(body[:that.start()]):
            yield Finding(entry.line, "warn", f"{what}: \"that entry\"", "no entry is named before it, so it points nowhere")
        if typed:
            yield from part_quoted(entry, typed)
    last = max((entry.line for entry in kept.values()), default=0)
    for number, source in sorted(logged.items()):
        if number not in kept:
            yield Finding(last, "fail", f"entry {number}", f"{log_name}:{source.line} has it, and the record doesn't")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")
