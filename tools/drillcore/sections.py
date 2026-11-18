"""Section coverage: the sections of the notes a workspace names, and how much of each must be held to a source.

`check` says how much of the notes as a whole was held to a source, not where the rest is: a note can pass with forty
sourced rows in its results table and nothing under the heading that carries its argument. A workspace can name the
sections that must rest on something a source holds:

    [[check.sections]]
    notes = ["*_industry.md"]
    headings = ["Rivalry", "New entrants", "Substitutes", "Buyer power", "Supplier power"]
    min_sourced = 2

- `headings` is one heading or a list of them, each naming a section in every note the rule covers.
- `notes` is which notes those are, as file names or patterns. Left out, the rule covers every note.
- `min_sourced` is how many lines under each heading must be held to a source. It defaults to 1.

A heading matches when its words are the rule's, once its `#`s, a leading section number (`2.`, `2.3`, `3)`, `IV.`) and
source keys in brackets at its end (`(S3 p.12)`) are taken off, with case and runs of spaces left aside. Nothing looser:
`Buyer power in Asia` is another section. A section runs from its heading to the next heading at its level or above,
so its sub-headings belong to it. The Sources and Gaps and cautions sections are never matched.

This module reads the rules and finds the sections. What counts as held to a source is `research`'s to say, from the
results of the checks that read the sources. The rules are the person's own: nothing is written into the notes.
"""
import fnmatch
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from .sourcedb import KEY_TOKEN, NoteLine
from .workspace import Workspace, WorkspaceError

FIELDS = ("headings", "notes", "min_sourced")
# A section number leading a heading: 2. or 2.3 or 3) or IV., or a bare 2 or 12. A bare number of more digits is
# kept, so a heading that starts with a year keeps it.
NUMBERED = re.compile(r"^(?:\d+(?:\.\d+)+\.?|\d+[.)]|\d{1,2}|[IVXLC]+[.)])\s+")
TRAILING_BRACKETS = re.compile(r"\s*\(([^()]*)\)\s*$")


@dataclass(frozen=True)
class Rule:
    """One `[[check.sections]]` table. `number` is its place among them, from 1, for saying which one."""
    number: int
    headings: tuple[str, ...]
    notes: tuple[str, ...]
    min_sourced: int

    def covers(self, note: str) -> bool:
        return not self.notes or any(fnmatch.fnmatchcase(note.casefold(), pattern.casefold()) for pattern in self.notes)

    def said(self) -> str:
        return f"[[check.sections]] rule {self.number}"


@dataclass(frozen=True)
class Section:
    """A section of a note that a rule names: its heading, and every line under it to where it ends."""
    note: str
    heading: NoteLine
    lines: tuple[NoteLine, ...]

    @property
    def body(self) -> list[NoteLine]:
        """The lines a check could judge: rows and prose, not headings, in the notes rather than a Sources list."""
        return [line for line in self.lines if line.kind in ("row", "prose") and line.section == "notes"]

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(key for line in (self.heading, *self.lines) for key in line.keys))

    @property
    def text(self) -> str:
        """The section as written, heading and all: what a waiver of it is held to."""
        return "\n".join(line.text for line in (self.heading, *self.lines))


def heading_words(text: str) -> str:
    """A heading's words, without what varies between writers: its #s, a leading section number, source keys in
    brackets at its end, case and runs of spaces."""
    words = NUMBERED.sub("", text.lstrip("#").strip())
    while (bracket := TRAILING_BRACKETS.search(words)) and KEY_TOKEN.search(bracket.group(1)):
        words = words[:bracket.start()]
    return " ".join(words.split()).casefold()


def level(heading: NoteLine) -> int:
    return len(heading.text) - len(heading.text.lstrip("#"))


def _strings(value: Any, where: str, field: str) -> tuple[str, ...]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list) or not values or not all(isinstance(v, str) and v.strip() for v in values):
        raise WorkspaceError(f"{where}: `{field}` must be a name or a list of them, none of them blank.")
    return tuple(v.strip() for v in values)


def rules(ws: Workspace) -> list[Rule]:
    """The workspace's `[[check.sections]]` rules, or [] when it has none. Raises WorkspaceError, naming the rule, for
    one that can't be used."""
    tables = ws.config().get("check", {}).get("sections", [])
    if not isinstance(tables, list) or not all(isinstance(table, dict) for table in tables):
        raise WorkspaceError(f"{ws.config_path}: `check.sections` must be written as [[check.sections]] tables, one for each rule.")
    found: list[Rule] = []
    for number, table in enumerate(tables, 1):
        where = f"{ws.config_path}, [[check.sections]] rule {number}"
        unknown = sorted(set(table) - set(FIELDS))
        if unknown:
            raise WorkspaceError(f"{where}: {', '.join(unknown)} isn't a setting of a rule. A rule takes {', '.join(FIELDS)}.")
        if "headings" not in table:
            raise WorkspaceError(f"{where}: a rule needs `headings`, the sections it names.")
        headings = _strings(table["headings"], where, "headings")
        notes = _strings(table["notes"], where, "notes") if "notes" in table else ()
        least = table.get("min_sourced", 1)
        if isinstance(least, bool) or not isinstance(least, int) or least < 1:
            raise WorkspaceError(f"{where}: `min_sourced` must be a whole number of 1 or more, not {least!r}.")
        found.append(Rule(number, headings, notes, least))
    return found


def find(lines: list[NoteLine], note: str, heading: str) -> list[Section]:
    """Every section of a note whose heading matches, each with the lines under it to the next heading at its level or
    above. `lines` are the note lines `note_lines` reads, in order."""
    wanted = heading_words(heading)
    mine = [line for line in lines if line.note == note]
    found: list[Section] = []
    for at, line in enumerate(mine):
        if line.kind != "heading" or line.section != "notes" or heading_words(line.text) != wanted:
            continue
        under: list[NoteLine] = []
        for after in mine[at + 1:]:
            if after.kind == "heading" and level(after) <= level(line):
                break
            under.append(after)
        found.append(Section(note, line, tuple(under)))
    return found


def sections(rule: Rule, notes: list[str], lines: list[NoteLine]) -> Iterator[tuple[str, str, list[Section]]]:
    """For each note the rule covers and each heading it names, the sections that match: none when the note hasn't
    the section."""
    for note in notes:
        if rule.covers(note):
            for heading in rule.headings:
                yield note, heading, find(lines, note, heading)
