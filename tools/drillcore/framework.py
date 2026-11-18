"""Rules for a framework's table, set in the workspace: what a column may hold, and an outcome derived from the others.

A report that applies a framework in a table, Ansoff's quadrants or a VRIO grid, can say in a cell what the framework
doesn't allow: a quadrant Ansoff never named, or an outcome the other columns rule out. `proof` holds each table of the
drafts to the rules `[[proof.table_rules]]` sets, as `[[arithmetic.rules]]` sets the workings `check` recomputes:

    [[proof.table_rules]]
    name = "Ansoff"                                  # optional: how its findings are labelled
    column = "Ansoff"                                # the heading of the column it judges
    values = ["Market penetration", "Market development", "Product development", "Diversification", "n/a"]

    [[proof.table_rules]]
    name = "VRIO, in Barney's order"
    column = "Outcome"
    derive = [                                       # the first case whose cells all match gives the outcome
        { when = { Valuable = "No" }, then = "disadvantage" },
        { when = { Rare = ["No", "Partly"] }, then = "parity" },
        { when = { "Hard to imitate" = ["No", "Partly"] }, then = "temporary" },
        { when = { Organized = ["No", "Partly"] }, then = "unused" },
        { when = {}, then = "sustained" },
    ]

A rule judges every table of the drafts with a column headed `column`, and for `derive`, a column headed by each
column its cases name, compared without regard to case or emphasis; any other table is no table of that framework.
`values` lists what a cell of the column may hold, whole; a blank cell passes. In `derive`, a condition holds when the
cell starts with one of the words it gives ("Yes" holds for "Yes, in industrial"), and the outcome cell must hold one of
the words `then` gives ("parity" for "Eroding parity"). A row no case matches, or whose outcome cell is blank, isn't
judged. Each finding is a failure: the rule is the workspace's own.
"""
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

EXAMPLE = '{ when = { Rare = ["No", "Partly"] }, then = "parity" }'
KEYS = {"name", "column", "values", "derive"}


@dataclass(frozen=True)
class Case:
    """One case of a derived outcome: the cells it asks for, by column, and the outcome they give."""
    when: tuple[tuple[str, tuple[str, ...]], ...]
    then: tuple[str, ...]


@dataclass(frozen=True)
class Rule:
    name: str
    column: str
    values: tuple[str, ...] = ()
    derive: tuple[Case, ...] = ()


@dataclass(frozen=True)
class Finding:
    line: int
    item: str
    detail: str


def _words(given: Any) -> tuple[str, ...] | None:
    """A word or a list of words, as a setting gives either; None when it's neither, or blank."""
    listed = [given] if isinstance(given, str) else given
    if not isinstance(listed, list) or not listed or not all(isinstance(word, str) and word.strip() for word in listed):
        return None
    return tuple(word.strip() for word in listed)


def rules(found: Any, where: str) -> tuple[Rule, ...]:
    """The rules `[[proof.table_rules]]` sets (`found`). Raises ValueError, saying which and why, for one that can't be
    read; `where` names the settings file."""
    if found is None:
        return ()
    if not isinstance(found, list) or not all(isinstance(entry, dict) for entry in found):
        raise ValueError(f"The table rules in {where} must each be a table of their own, under [[proof.table_rules]].")
    read = []
    for number, entry in enumerate(found, 1):
        at = f"Rule {number} under [[proof.table_rules]] in {where}"
        unknown = sorted(set(entry) - KEYS)
        if unknown:
            raise ValueError(f"{at} has settings it doesn't know: {', '.join(unknown)}. It takes {', '.join(sorted(KEYS))}.")
        column, name = entry.get("column"), entry.get("name", entry.get("column"))
        if not isinstance(column, str) or not column.strip() or not isinstance(name, str):
            raise ValueError(f"{at} must name the column it judges: column = \"Outcome\".")
        values = _words(entry["values"]) if "values" in entry else ()
        if values is None:
            raise ValueError(f"{at}: values must be a list of what the column may hold, none of it blank.")
        cases = entry.get("derive", [])
        if not isinstance(cases, list):
            raise ValueError(f"{at}: derive must be a list of cases, each as {EXAMPLE}.")
        derived = []
        for case in cases:
            when = case.get("when") if isinstance(case, dict) else None
            then = _words(case.get("then")) if isinstance(case, dict) else None
            asked = {key: _words(value) for key, value in when.items()} if isinstance(when, dict) else None
            if then is None or asked is None or any(value is None for value in asked.values()) or set(case) - {"when", "then"}:
                raise ValueError(f"{at}: each case of derive must be written as {EXAMPLE}; when = {{}} matches any row.")
            derived.append(Case(tuple((key.strip(), value) for key, value in asked.items() if value), then))
        if not values and not derived:
            raise ValueError(f"{at} must give values, derive or both.")
        read.append(Rule(name.strip() or column.strip(), column.strip(), values, tuple(derived)))
    return tuple(read)


def plain(cell: str) -> str:
    """A cell as it's compared: no emphasis, single spaces, one case."""
    return " ".join(re.sub(r"[*_`]", "", cell).split()).casefold()


def _starts(cell: str, word: str) -> bool:
    return re.match(rf"{re.escape(plain(word))}(?!\w)", plain(cell)) is not None


def _holds(cell: str, word: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(plain(word))}(?!\w)", plain(cell)) is not None


def check(rule: Rule, header: list[str], rows: list[tuple[int, list[str]]]) -> Iterator[Finding]:
    """What a table breaks of a rule, row by row; nothing for a table that isn't one of the rule's framework."""
    heads = [plain(cell) for cell in header]
    named = {column for case in rule.derive for column, _ in case.when}
    if plain(rule.column) not in heads or any(plain(column) not in heads for column in named):
        return
    at = heads.index(plain(rule.column))
    allowed = {plain(value) for value in rule.values}
    for line, cells in rows:
        cell = cells[at].strip() if at < len(cells) else ""
        if not plain(cell):
            continue
        label = re.sub(r"[*_`]", "", cells[0]).strip() if cells else ""
        if allowed and plain(cell) not in allowed:
            yield Finding(line, cell, f"{label}: the {header[at]!r} column may hold only {', '.join(rule.values)} "
                                      f"([[proof.table_rules]] {rule.name!r})")
        for case in rule.derive:
            given = [(column, words, cells[heads.index(plain(column))] if heads.index(plain(column)) < len(cells) else "")
                     for column, words in case.when]
            if all(any(_starts(found, word) for word in words) for _, words, found in given):
                if not any(_holds(cell, word) for word in case.then):
                    because = ", ".join(f"{column}: {re.sub(r'[*_`]', '', found).strip()}" for column, _, found in given)
                    yield Finding(line, cell, f"{label}: by [[proof.table_rules]] {rule.name!r}, "
                                              f"{because + ' makes' if because else 'its cells make'} it {' or '.join(case.then)}, "
                                              f"but the {header[at]!r} column says {cell!r}")
                break
