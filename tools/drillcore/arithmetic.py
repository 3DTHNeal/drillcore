"""The arithmetic check: a figure the notes say was worked out must come out of its own working.

It reads the notes only, never the database, and the Sources and Gaps and cautions sections not at all. It reads two
kinds of working.

**Brackets after a figure.** A row (a table row or a "- " bullet) is worked out when it, its section's heading, or the
paragraph of prose just before it carries one of the markers `check_figures` skips: COMPUTED, derived, implied and the
rest of `sourcedb.WORKED_OUT`. Such a row shows its working in brackets straight after the figure, in one of these forms:

    -3.7% (551.1 against 572.5)    a change, new against old: 551.1 / 572.5 - 1. "vs" and "versus" read the same.
    -3.7% (from 572.5 to 551.1)    the same change, written old first.
    70.8% (67.5 of 95.4)           a share: 67.5 / 95.4.
    4.1% (from 450.0 to 551.1 over 5 years)
                                   a compound annual rate: (551.1 / 450.0) ^ (1 / 5) - 1. "CAGR" may lead it, and
                                   "from" may be left out.
    $27.9M (= 95.4 - 67.5)         a formula, written after "=": + - * / ^, brackets, functions such as avg(...) and
                                   cagr(...), and figures the notes' tables state, named in braces as {Revenue 2025}.
                                   `formula` says what one may hold, and `stated` how a name finds its figure.

    -0.4pp (2.7 against 3.1)       a change in a rate, in percentage points: 2.7 - 3.1. Basis points, "+25bp (from
                                   4.25% to 4.50%)", are hundredths of a point. The rates may carry a percent sign.

A change and a share are percentages, so the figure in front of them ends in %, unless the change is in points. The numbers in a working may carry
thousands commas, and in a sum a percent sign means hundredths wherever it's written, so "70.8% (= 67.5 / 95.4)" and
"1.2 (= 3% * 40)" both hold. A unit on the figure, such as $, M or bn, is a label: the working's numbers are taken to be
in the same units. Anything after a semicolon inside the brackets is a remark and isn't read. The working is what was
computed, so its numbers are exact: the figure holds when the working, rounded to the figure's decimal places, gives
it, half a unit in the last place either way. A figure written without a sign is held against the working's size,
since the words around it ("fell", "down") carry the direction; one written with + or - must match in sign as well.

**Equations.** Anywhere in a note's body, worked out or not, an equation written as `a + b = c` or `c = a + b`, such as
`150.4 + 43.2 = $193.6 million`, and a table row with a Result column and an Arithmetic column. One side is arithmetic
and the other a single number; a chain such as `2013-2015 = 11 + 9 + 4 = 24` holds each expression to the number after
it, and words such as "about" before a number are passed over. The arithmetic may use a power (`1.05 ^ 3`), a function
touching its bracket (`avg(4.1, 3.9)`) and a figure named in braces, so `{Gross profit 2025} / {Revenue 2025} = 41.2%`
holds the notes' own figures to the margin, and `{Revenue 2025} = 551.1` holds a figure to the one the table states.
Here the inputs are figures copied from elsewhere, so each is read as rounded to its last digit (a whole number
without a scale, such as a count of 24, is exact, unless it's a figure named in braces), and the result must agree to
the precision it's written to, allowing for that rounding. When no input states its scale and the result does, the
inputs are in a unit the result names; a signed percentage after one division (`6.063 / 5.165 = +17.4%`) is read as
the change the ratio gives.

**Conversions.** Anywhere in a note's body, a figure in one currency with the amount it converts and the rate in
brackets after it, as `$510M (RMB 3.7bn at 7.25)`, `€5.0M (£4.3M @ 0.86)` or `$510M (RMB 3.7bn at a rate of 7.25)`.
The rate is read as units of the bracketed currency to one unit of the figure's, so the figure is the amount divided by
the rate; a rate written the other way says so, as `at 0.138 $/RMB` or `at 0.138 USD per RMB`, and is multiplied. The
figure must agree to the precision it's written to, allowing for the rounding of the amount and the rate. A figure
followed by an amount in another currency with no rate is "unparsed": the conversion can't be checked until the rate is
written. The rate is a figure like any other, so a sourced row's numbers check holds it to the source; the converted
figure is set aside there, since no source states it.

**Footing.** In a table with a total row, one whose label starts with Total, or reads Consolidated, Group or Group
total, each column of figures must add up to the total, allowing for the rounding of every cell. The rows added are
those since the total row before it, or those with the totals just above them, as `Total assets` adds `Total current
assets` to the rows after it; any of those readings will do. A row labelled "of which" or "including" isn't added.
Columns of changes, margins, rates, ratios, averages, prices and multiples aren't added, and a column of percentages
only when its total is 100%. A column headed as a share or mix in a table without a total row mustn't add to more than
100%, beyond its rounding, nor to less when one of its rows is "Other". A cell that isn't a number this reads (a blank, a
footnote mark, words) makes its column "unparsed", never guessed at; a dash is nil.

**Rules.** A workspace can set formulas the notes' figures must keep to, wherever the notes state them all, with no
working written:

    [[arithmetic.rules]]
    name = "Gross margin"                                   # optional: how its results are labelled
    formula = "{Gross margin} = {Gross profit} / {Revenue}"

    [[arithmetic.rules]]
    formula = "{Revenue growth} = {Revenue} / {Revenue, prior} - 1"

One side names the figure the rule gives, and the other is a formula over figures it names. For each figure a table in
the notes states on the first side's line, the rule is worked out in that figure's period, with each name read in that
period too (or, with "prior", the year before), looking in the same note first, as `stated` describes. A period for
which the notes don't state every figure the rule names isn't judged; a name that matches two figures is "unparsed".
The figure must agree to the precision it's written to, allowing for the rounding of the figures it's worked out from.
A rule that can't be read stops the run, saying why.

Each working gives a result: "ok", or "wrong" with what the working gives. A worked-out row that has a figure but no
working this reads is "unparsed", a warning that the working could be written in. A working that can't be read, such
as one that divides by zero, is "unparsed" too. The notes are never changed.

Workings are read and worked out by the math engine in `formula`, which knows numbers, operators, brackets, the
functions it lists and nothing else. Text from the notes is never run.
"""
import argparse
import re
import sqlite3
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any

from . import identity, waivers
from .formula import AMOUNT, SCALE, Figure, Interval, Node, Parser, Token, Undefined, bind, call, cell_figure, exact, figure, lex, parse, show
from .formula import label as _label
from .measures import differ
from .sourcedb import NOT_NOTES, URL, WORKED_OUT, cells, note_files, numbers_in, table_headers
from .stated import Ambiguous, Book, NotStated, Reference, Stated, Table, reference, tables
from .workspace import Workspace, WorkspaceError

_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_MINUS = ("-", "−")
Resolve = Callable[[str], Figure]
# A figure followed by the bracket that may hold its working: "-3.7% (", "$27.9M (".
FIGURE = re.compile(rf"(?<![\w.,])(?P<sign>[-+−]?)[$€£¥]?(?P<number>{_NUM})(?!\d)"
                    r"\s?(?P<unit>%|pp\b|bps?\b|x\b|bn\b|billion\b|million\b|thousand\b|[MBk]\b)?\s*\(")


def _amount(name: str) -> str:
    """A number in a change or a share, which may carry a currency sign and a unit, as "$551.1M"."""
    return rf"[$€£¥]?(?P<{name}>{_NUM})(?:\s?(?:bn|billion|million|thousand|[MBk]))?%?"


CHANGE = re.compile(rf"{_amount('new')}\s+(?:against|vs\.?|versus)\s+{_amount('old')}", re.IGNORECASE)
CHANGE_FROM = re.compile(rf"from\s+{_amount('old')}\s+to\s+{_amount('new')}", re.IGNORECASE)
SHARE = re.compile(rf"{_amount('part')}\s+of\s+{_amount('whole')}", re.IGNORECASE)
# A compound annual rate: "from 450.0 to 551.1 over 5 years", "CAGR 450.0 to 551.1 in 5 years".
COMPOUND = re.compile(rf"(?:CAGR\s*,?\s+(?:of\s+)?)?(?:from\s+)?{_amount('old')}\s+to\s+{_amount('new')}\s*,?\s+"
                      r"(?:over|across|in)\s+(?P<years>\d+(?:\.\d+)?)\s+years?", re.IGNORECASE)
# A change in a rate is written in points: percentage points, or basis points, a hundredth of one. What a value that
# is a fraction (0.004) is multiplied by to give the figure in each.
POINTS = {"pp": 100, "bp": 10000, "bps": 10000}
# The kinds of `Result.kind`.
WORKING, TOTAL = "working", "total"


@dataclass(frozen=True)
class Result:
    """One working's verdict. `stated` is the figure as written; `computed` is what its working gives, in the figure's
    own units (so -3.74 for a percentage), or None when there's no working to compute. `detail` is the working, or for
    an unparsed row, what's missing. `item` is what was judged as the note writes it, such as "-3.7% (551.1 against
    572.5)" or "12 + 8 = 21", and `why` says how it came out. `inputs` are the figures the working starts from, as
    written, such as ("551.1", "572.5"): a working can be right and its inputs still come from nowhere, so `check`
    traces each one to the notes or a source."""
    note: str
    line: int
    status: str  # ok | wrong | unparsed
    stated: str
    computed: float | None
    text: str
    detail: str = ""
    item: str = ""
    why: str = ""
    inputs: tuple[str, ...] = ()
    rule: str = ""  # the workspace rule that gave it, by its name or formula
    # What was worked: a row's own "working", or a table's "total" (a total row, or a column of shares that should
    # make 100%). A report that counts these says "workings" or "totals", and the two aren't the same.
    kind: str = WORKING

    def shown(self) -> str:
        """What the working gives, written like the figure: to four places at most, with its percent sign."""
        if self.computed is None:
            return ""
        number = f"{self.computed:,.4f}".rstrip("0").rstrip(".")
        ending = re.search(r"(pp|bps?|%)$", self.stated)
        return number + (ending.group(1) if ending else "")


# ---------------------------------------------------------------- workings in brackets

def _closing(text: str, opening: int) -> int | None:
    """Where the bracket opened at `opening` closes, counting the brackets inside it, or None if it never does."""
    depth = 0
    for at in range(opening, len(text)):
        depth += {"(": 1, ")": -1}.get(text[at], 0)
        if depth == 0:
            return at
    return None


def _number(written: str) -> Fraction:
    return Fraction(written.replace(",", ""))


def _judge(note: str, line: int, row: str, figure: re.Match[str], inside: str, resolve: Resolve | None = None) -> Result | None:
    """The verdict on one figure and the brackets after it, or None when the brackets don't hold a working."""
    working = inside.split(";", 1)[0].strip()
    stated_text = figure.group(0)[:-1].strip()
    item = f"{stated_text} ({working})"
    sign, number, unit = figure["sign"], figure["number"].replace(",", ""), figure["unit"] or ""
    decimals = len(number.split(".")[1]) if "." in number else 0
    stated = Fraction(number) * (-1 if sign in _MINUS else 1)

    def unparsed(why: str) -> Result:
        return Result(note, line, "unparsed", stated_text, None, row, why, item)

    change = CHANGE.fullmatch(working) or CHANGE_FROM.fullmatch(working)
    share = SHARE.fullmatch(working)
    compound = COMPOUND.fullmatch(working)
    shown_from = ""
    if working.startswith("="):
        try:
            formula = parse(working[1:])
            bound = bind(formula, resolve)
            value = bound.evaluate()[0]
        except ValueError as problem:
            return unparsed(str(problem))
        written = bound.figures()
        inputs = tuple(f.text for f in written if f.text)
        shown_from = f" from {bound.written()}" if formula.references() else ""
        if unit in POINTS and not any(f.percent for f in written):
            # A sum of rates written without percent signs is in points already: "0.4pp (= 3.1 - 2.7)".
            value /= 100
    elif compound:
        inputs = (compound["old"], compound["new"])
        if unit != "%":
            return unparsed("a compound rate is a percentage, so the figure before it should end in %")
        try:
            value = call("cagr", [Node(leaf=exact(_number(compound[name]))) for name in ("old", "new", "years")]).evaluate()[0]
        except Undefined as problem:
            return unparsed(str(problem))
    elif change and unit in POINTS:
        # A change in a rate, in points: the new rate less the old, as "-0.4pp (2.7 against 3.1)".
        inputs = (change["new"], change["old"])
        value = (_number(change["new"]) - _number(change["old"])) / 100
    elif change or share:
        inputs = (change["new"], change["old"]) if change else (share["part"], share["whole"]) if share else ()
        if unit != "%":
            return unparsed(f"a {'change' if change else 'share'} is a percentage, so the figure before it should end in %")
        top, bottom = (change["new"], change["old"]) if change else (share["part"], share["whole"]) if share else ("", "")
        if _number(bottom) == 0:
            return unparsed("the working divides by zero")
        value = _number(top) / _number(bottom) - (1 if change else 0)
    else:
        return None
    in_units = value * POINTS.get(unit, 100 if unit == "%" else 1)
    compared = in_units if sign else abs(in_units)
    holds = abs(compared - stated) <= Fraction(1, 2 * 10 ** decimals)
    result = Result(note, line, "ok" if holds else "wrong", stated_text, float(in_units), row, working, item, inputs=inputs)
    return replace(result, why=f"gives {result.shown()}{shown_from}")


# ---------------------------------------------------------------- equations in running text

Parsed = tuple[Node, list[Token]]


def leading(run: list[Token]) -> Parsed | None:
    """The longest expression the run starts with, after any "about", and the tokens it takes."""
    while run and run[0].kind == "approx":
        run = run[1:]
    parser = Parser(run)
    node = parser.expression()
    return (node, run[:parser.at]) if node else None


def trailing(run: list[Token]) -> Parsed | None:
    """The longest expression the run ends with, and the tokens it takes."""
    for start in range(len(run)):
        parser = Parser(run[start:])
        node = parser.expression()
        if node and parser.at == len(run) - start:
            return node, run[start:]
    return None


@dataclass(frozen=True)
class Equation:
    expression: Node
    result: Node
    text: str


def _spelled(tokens: list[Token]) -> str:
    """Tokens spaced out, as an equation is named in a report and a waiver: a reference in its braces, a call against
    its bracket and a comma against the figure before it."""
    out = ""
    calls: list[bool] = []  # for each bracket open, whether it holds a call's figures
    for at, token in enumerate(tokens):
        text = "{" + token.text + "}" if token.kind == "ref" else token.text
        after = tokens[at - 1] if at else None
        opens_call = token.kind == "(" and after is not None and after.kind == "call"
        glued = (token.kind == "," or opens_call or (token.kind == ")" and calls and calls[-1])
                 or (after is not None and after.kind == "(" and calls and calls[-1]))
        if token.kind == "(":
            calls.append(opens_call)
        elif token.kind == ")" and calls:
            calls.pop()
        out += text if glued or not out else " " + text
    return out


def equations(text: str) -> list[Equation]:
    """The equations a line writes, as `a + b = c` or `c = a + b`. One side must be arithmetic, with at least one
    operator, function or reference, and the other a number. In a chain such as `2013-2015 = a + b + c = d`, an
    expression is held to the number after it."""
    found: list[Equation] = []
    run: list[Token] = []
    for token in [*lex(text), Token("other", "")]:
        if token.kind != "other":
            run.append(token)
            continue
        sides: list[list[Token]] = [[]]
        for item in run:
            if item.kind == "=":
                sides.append([])
            else:
                sides[-1].append(item)
        # Each side that holds an expression is judged once, by the number after it if there is one, else the one before.
        by_side: dict[int, Equation] = {}
        for i in range(len(sides) - 1):
            before, after = trailing(sides[i]), leading(sides[i + 1])
            if not (before and after):
                continue
            (left, left_tokens), (right, right_tokens) = before, after
            # One side is arithmetic and the other one number. `2022 + 2023 = 498.8 + 112.9` adds up labels, not figures.
            if bool(left.operators()) == bool(right.operators()):
                continue
            as_text = _spelled(left_tokens) + " = " + _spelled(right_tokens)
            if left.operators():
                by_side[i] = Equation(left, _as_result(right), as_text)
            elif i + 1 not in by_side:
                by_side[i + 1] = Equation(right, _as_result(left), as_text)
        found += [by_side[i] for i in sorted(by_side)]
        run = []
    return found


def _as_result(node: Node) -> Node:
    """A result number is read as rounded to its last digit, whole numbers included."""
    if node.leaf and node.leaf.half == 0:
        match = AMOUNT.fullmatch(node.leaf.text)
        if match:
            return Node(leaf=figure(match, as_result=True))
    return node


def recompute(equation: Equation) -> tuple[bool, str]:
    """Whether the expression gives the result, to the precision the result is written to, allowing for the rounding of
    the inputs. When no input states its scale and the result does (`150.4 + 43.2 = $193.6 million`), the inputs are
    in a unit the result names: a thousand, a million or a billion, whichever the result is written in. A signed
    percentage after one division (`6.063 / 5.165 = +17.4%`) is read as the change the ratio gives. The equation's
    references must be bound."""
    try:
        stated = equation.result.evaluate()
        value = equation.expression.evaluate()
    except Undefined as problem:
        return False, str(problem)
    leaf = equation.result.leaf
    # A value is shown as the result is written: as a percentage when the result is one.
    shown = (lambda value: show(value * 100) + "%") if leaf and leaf.percent else show
    units = [Fraction(1)]
    if leaf and leaf.scaled and not any(f.scaled for f in equation.expression.figures()):
        units += [Fraction(10) ** power for power in (3, 6, 9)]
    readings: list[tuple[Interval, str]] = [(value, "")]
    if leaf and leaf.percent and leaf.signed and equation.expression.op == "/":
        readings.append(((value[0] - 1, value[1] - 1, value[2] - 1), " as a change"))
    for unit in units:
        result, low_result, high_result = (end / unit for end in stated)
        for (worked, low, high), how in readings:
            if abs(worked - result) <= high_result - result:
                return True, f"recomputes{how}: {shown(worked)}"
            if low <= high_result and low_result <= high:
                return True, f"recomputes{how} within the rounding of its inputs: {shown(worked)} as written"
    return False, f"computes to {shown(value[0])}, not {leaf.text if leaf else 'the result'}"


def table_equation(row: str, header: list[str]) -> Equation | None:
    """A row of a table with a Result column and an Arithmetic column, when the result is one number and the
    arithmetic starts with an expression."""
    names = [name.lower() for name in header]
    if "result" not in names or "arithmetic" not in names:
        return None
    row_cells = cells(row)
    if len(row_cells) != len(names):
        return None
    result_run = [t for t in lex(row_cells[names.index("result")]) if t.kind != "approx"]
    if not result_run or any(t.kind == "other" for t in result_run):
        return None
    parser = Parser(result_run)
    result = parser.expression()
    if not result or result.operators() or parser.at != len(result_run):
        return None
    # The arithmetic may go on in words, as in "(244.5 - 150.7) - 119.3 net proceeds"; what comes before them is read.
    work = lex(row_cells[names.index("arithmetic")])
    work = work[:next((i for i, t in enumerate(work) if t.kind == "other"), len(work))]
    parsed = leading(work)
    if not parsed or not parsed[0].operators():
        return None
    return Equation(parsed[0], _as_result(result), f"{row_cells[names.index('arithmetic')]} = {row_cells[names.index('result')]}")


def _recomputed(note: str, line: int, row: str, equation: Equation, resolve: Resolve | None = None) -> Result:
    """The verdict on one equation, its references bound with `resolve`."""
    references = equation.expression.references() + equation.result.references()
    try:
        equation = Equation(bind(equation.expression, resolve), bind(equation.result, resolve), equation.text)
        value = equation.expression.evaluate()
        equation.result.evaluate()
    except Undefined as problem:
        stated = equation.result.leaf.text if equation.result.leaf else ""
        return Result(note, line, "unparsed", stated, None, row, str(problem), equation.text)
    stated = equation.result.leaf.text if equation.result.leaf else ""
    holds, why = recompute(equation)
    if references and not equation.expression.leaf:
        why += f", from {equation.expression.written()} = {equation.result.written()}"
    return Result(note, line, "ok" if holds else "wrong", stated, float(value[0]), row, equation.text, equation.text, why,
                  tuple(f.text for f in equation.expression.figures() if f.text))


# ---------------------------------------------------------------- conversions between currencies

CURRENCY = r"US\$|HK\$|\$|€|£|¥|(?:USD|EUR|GBP|JPY|RMB|CNY|HKD|CHF)(?![A-Za-z])"
_SCALED = r"(?:\s?(?:thousand|million|billion|trillion|bn)\b|[kMB]\b)?"
_MONEY = rf"[-−]?(?:{CURRENCY})\s?(?:{_NUM}){_SCALED}"
# A sum of money with the groups `figure` reads. It's never a percentage, so that group never matches.
MONEY = re.compile(rf"(?P<sign>[-−])?(?P<currency>{CURRENCY})\s?(?P<digits>{_NUM})"
                   r"(?:\s?(?P<word>thousand|million|billion|trillion|bn)\b|(?P<letter>[kMB])\b)?(?P<percent>(?!))?")
# A figure in one currency with brackets after it that may convert another.
CONVERSION = re.compile(rf"(?<![\w.,$€£¥])(?P<figure>{_MONEY})\s*\((?P<inside>[^()]*)\)")
WITH_RATE = re.compile(rf"(?P<amount>{_MONEY})\s*,?\s*(?:at(?:\s+an?\s+(?:exchange\s+)?rate\s+of)?|@)\s*(?P<rate>{_NUM})"
                       rf"(?:\s*(?P<top>{CURRENCY})\s*(?:/|\s+per\s+|\s+to\s+(?:the\s+|one\s+|1\s+)?)\s*(?P<bottom>{CURRENCY}))?",
                       re.IGNORECASE)
# The currencies each way of writing one can mean. A bare ¥ is a yen or a yuan.
ISO = {"$": {"USD"}, "US$": {"USD"}, "HK$": {"HKD"}, "€": {"EUR"}, "£": {"GBP"}, "¥": {"JPY", "CNY"}, "RMB": {"CNY"}}


def _currencies(written: str) -> set[str]:
    written = written.strip()
    return ISO.get(written, ISO.get(written.upper(), {written.upper()}))


def _same(one: str, other: str) -> bool:
    return bool(_currencies(one) & _currencies(other))


def _in_its_scale(value: Fraction, written: re.Match[str]) -> str:
    """A value written the way a sum of money was: its currency, to four places at most, and its scale."""
    scale = written.group("word") or written.group("letter") or ""
    number = f"{float(value / Fraction(10) ** SCALE.get(scale, 0)):,.4f}".rstrip("0").rstrip(".")
    return f"{written.group('currency')}{number}{' ' + scale if written.group('word') else scale}"


def _conversion(note: str, line: int, row: str, found: re.Match[str]) -> Result | None:
    """The verdict on a figure and a conversion in brackets after it, or None when the brackets don't convert another
    currency."""
    working = found["inside"].split(";", 1)[0].strip()
    item = f"{found['figure']} ({working})"
    stated = MONEY.fullmatch(found["figure"])
    rated = WITH_RATE.fullmatch(working)
    amount = MONEY.fullmatch(rated["amount"] if rated else working)
    if not (stated and amount) or _same(stated["currency"], amount["currency"]):
        return None
    if not rated:
        return Result(note, line, "unparsed", found["figure"], None, row,
                      f"{item}: a conversion with no rate written beside it, so it can't be recomputed", item)
    divide = True
    if rated["top"]:
        if _same(rated["top"], amount["currency"]) and _same(rated["bottom"], stated["currency"]):
            divide = True
        elif _same(rated["top"], stated["currency"]) and _same(rated["bottom"], amount["currency"]):
            divide = False
        else:
            return Result(note, line, "unparsed", found["figure"], None, row,
                          f"{item}: the rate is written in {rated['top']} per {rated['bottom']}, but the conversion is from "
                          f"{amount['currency']} to {stated['currency']}", item)
    rate = AMOUNT.fullmatch(rated["rate"])
    assert rate is not None
    expression = Node("/" if divide else "*", Node(leaf=figure(amount)), Node(leaf=figure(rate)))
    equation = Equation(expression, Node(leaf=figure(stated, as_result=True)), item)
    try:
        value = expression.evaluate()
    except Undefined as problem:
        return Result(note, line, "unparsed", found["figure"], None, row, str(problem), item)
    holds, why = recompute(equation)
    per = (f"{rated['top']} per {rated['bottom']}" if rated["top"] else f"{amount['currency']} to the {stated['currency']}")
    if holds:
        why = f"recomputes at {rated['rate']} {per}: {_in_its_scale(value[0], stated)}"
    else:
        why = f"computes to {_in_its_scale(value[0], stated)} at {rated['rate']} {per}, not {found['figure']}"
        if not rated["top"]:
            why += f"; if the rate is {stated['currency']} per {amount['currency']}, write it as {rated['rate']} {stated['currency']}/{amount['currency']}"
    return Result(note, line, "ok" if holds else "wrong", found["figure"], float(value[0]), row, working, item, why,
                  (rated["amount"], rated["rate"]))


def conversions(note: str, line: int, text: str) -> list[tuple[Result, tuple[int, int]]]:
    """Each conversion a line writes, with where it stands in the line, figure and brackets together."""
    found: list[tuple[Result, tuple[int, int]]] = []
    for match in CONVERSION.finditer(text):
        result = _conversion(note, line, text, match)
        if result:
            found.append((result, match.span()))
    return found


def without_conversions(text: str) -> str:
    """A line with each figure that a conversion with its rate gives blanked out, the same length as before. No source
    states that figure: the amount and the rate are what a source can hold, and the conversion is checked here."""
    for result, (start, _) in conversions("", 0, text):
        if result.computed is not None:
            text = text[:start] + " " * len(result.stated) + text[start + len(result.stated):]
    return text


# ---------------------------------------------------------------- footing a table

TOTAL_ROW = re.compile(r"(?:total\b|consolidated\b|group(?:\s+total)?$)", re.IGNORECASE)
# A total row that says nothing but that it's the total, perhaps with its unit: "Total", "Totals, $M", "Group total".
# Only such a row is held to be the sum of the rows above it. "Total debt" in a table of key figures is a figure of its
# own, so a row labelled that way that doesn't add up is left not parsed, never called wrong.
BARE_TOTAL = re.compile(r"(?:totals?|consolidated(?:\s+total)?|group(?:\s+total)?)\s*(?:[,(:].*)?", re.IGNORECASE)
# A total that leaves something out, "Total (excl. B)", or is adjusted, isn't the plain sum either.
PART_TOTAL = re.compile(r"\b(?:excl|excluding|ex|less|before|after|adjusted|underlying|pro forma)\b", re.IGNORECASE)
NOT_ADDED = re.compile(r"(?:of which|of that|incl(?:uding|\.)?\b|memo\b)", re.IGNORECASE)
# Columns whose figures don't add: a change, a margin, a rate, a ratio, an average, a price, a multiple.
NOT_SUMMED = re.compile(r"change|growth|margin|yoy|y/y|average|\bavg\b|per share|price|rate\b|ratio|multiple|yield|cagr|"
                        r"return|\bvs\b|\bx\b", re.IGNORECASE)
SHARE_COLUMN = re.compile(r"\bshare\b|% of|\bmix\b|\bsplit\b|\bproportion\b|\bweight", re.IGNORECASE)
OTHER_ROW = re.compile(r"(?:all\s+)?(?:others?|rest|remainder)\b", re.IGNORECASE)
HUNDRED = Figure(Fraction(1), Fraction(0), False, True, False, "100%")
def _add(figures: list[Figure], texts: list[str], total: Figure, how: str) -> Equation:
    """The sum of a column's figures, held to its total."""
    node = Node(leaf=figures[0])
    for leaf in figures[1:]:
        node = Node("+", node, Node(leaf=leaf))
    return Equation(node, Node(leaf=total), f"{how}: {' + '.join(texts)} = {total.text}")


def _footing(note: str, table: Table, column: int, total_at: int) -> Result | None:
    """The verdict on one column of one total row, or None when that column isn't one to add."""
    line, row, total_cells = table.rows[total_at]
    heading = table.header[column] if column < len(table.header) else ""
    if column >= len(total_cells) or NOT_SUMMED.search(heading) or NOT_SUMMED.search(_label(total_cells[0])):
        return None
    bare = bool(BARE_TOTAL.fullmatch(_label(total_cells[0]))) and not PART_TOTAL.search(_label(total_cells[0]))
    total = cell_figure(total_cells[column])
    if total is None or (total.percent and total.value != 1):
        return None
    label = f"{_label(total_cells[0])}, {_label(heading) or f'column {column + 1}'}"
    totals = [i for i in range(total_at) if TOTAL_ROW.match(_label(table.rows[i][2][0]))]
    since = [i for i in range(totals[-1] + 1 if totals else 0, total_at) if not NOT_ADDED.match(_label(table.rows[i][2][0]))]
    # The rows since the last total, then those with the totals just above them, nearest first.
    readings = [since] + [totals[-k:] + since for k in range(1, len(totals) + 1)]
    readings = [reading for reading in readings if reading]
    if not readings:
        return None
    # The verdict on the first reading stands unless another one adds up.
    first: Result | None = None
    for number, reading in enumerate(readings):
        written = [table.rows[i][2][column] if column < len(table.rows[i][2]) else "" for i in reading]
        figures = [cell_figure(cell) for cell in written]
        # Nil is nil in a column of percentages too.
        unread = next((at for at, f in enumerate(figures) if f is None or (f.percent != total.percent and f.value != 0)), None)
        if unread is not None:
            if number == 0:
                first = Result(note, line, "unparsed", total.text, None, row,
                               f"{label} can't be footed: line {table.rows[reading[unread]][0]}'s cell {written[unread]!r} "
                               "isn't a figure this adds", label)
            continue
        equation = _add([f for f in figures if f is not None], [_label(cell) for cell in written], total, label)
        holds, why = recompute(equation)
        value = equation.expression.evaluate()
        if total.percent and value:
            why = f"adds to {show(value[0] * 100)}%" + ("" if holds else ", not 100%")
        result = Result(note, line, "ok" if holds else "wrong", total.text, float(value[0]) if value else None, row,
                        equation.text, equation.text, why)
        if holds:
            return result
        if number == 0:
            first = replace(result, why=why + ("; nor with the totals above it" if len(readings) > 1 else ""))
    if first and first.status == "wrong" and not bare:
        first = replace(first, status="unparsed", detail=f"{label} doesn't add up from the rows above it ({first.why}), and its "
                        f"label doesn't say it's their total, so it isn't judged", why="")
    return first


def _shares(note: str, table: Table, column: int) -> Result | None:
    """The verdict on a column of shares in a table with no total row: more than 100% is wrong, and so is less when a
    row is the Other that makes the rest up. Anything else says nothing."""
    heading = table.header[column] if column < len(table.header) else ""
    if not SHARE_COLUMN.search(heading) or NOT_SUMMED.search(heading):
        return None
    figures = [cell_figure(row_cells[column]) if column < len(row_cells) else None for _, _, row_cells in table.rows]
    if len(figures) < 2 or not all(f is not None and f.percent for f in figures):
        return None
    shares = [f for f in figures if f is not None]
    equation = _add(shares, [f.text for f in shares], HUNDRED, f"{_label(heading)}, every row")
    worked, low, high = equation.expression.evaluate()
    other = any(OTHER_ROW.match(_label(row_cells[0])) for _, _, row_cells in table.rows)
    line, row, _ = table.rows[-1]
    if low > 1 or (other and high < 1):
        return Result(note, line, "wrong", "100%", float(worked * 100), row, equation.text, equation.text,
                      f"adds to {show(worked * 100)}%, not 100%")
    if high < 1:
        return None
    return Result(note, line, "ok", "100%", float(worked * 100), row, equation.text, equation.text,
                  f"adds to {show(worked * 100)}%")


def footings(note: str, text: str) -> list[Result]:
    """The verdicts on every table in a note that has a total row, or a column of shares."""
    results: list[Result] = []
    for table in tables(text):
        names = [name.lower() for name in table.header]
        if "result" in names and "arithmetic" in names:
            continue
        width = max(len(table.header), *(len(row_cells) for _, _, row_cells in table.rows))
        totals = [i for i, (_, _, row_cells) in enumerate(table.rows) if TOTAL_ROW.match(_label(row_cells[0]))]
        for column in range(1, width):
            if totals:
                results += [replace(r, kind=TOTAL) for at in totals if (r := _footing(note, table, column, at))]
            elif share := _shares(note, table, column):
                results.append(replace(share, kind=TOTAL))
    return results


# ---------------------------------------------------------------- the notes

def check_row(note: str, line: int, row: str, header: list[str] | None = None, worked_out: bool = True,
              resolve: Resolve | None = None) -> list[Result]:
    """The verdicts on one line of a note: each figure with a working in brackets after it, when the line is a
    worked-out row, then each equation it writes, and its Result and Arithmetic columns when its table has them. A
    worked-out row with a figure and none of these gets a single "unparsed". `resolve` finds the figure a reference
    names; with none, a working that names one is "unparsed"."""
    body = URL.sub(" ", row)
    results: list[Result] = []
    # A conversion is read on any line, and once read isn't seen again as a working or an equation.
    for converted, (start, end) in conversions(note, line, body):
        results.append(replace(converted, text=row))
        body = body[:start] + " " * (end - start) + body[end:]
    position = 0
    while worked_out and (found := FIGURE.search(body, position)):
        close = _closing(body, found.end() - 1)
        if close is None:
            break
        verdict = _judge(note, line, row, found, body[found.end():close], resolve)
        if verdict:
            results.append(verdict)
            # A working is read once: the equation reader doesn't see it again.
            body = body[:found.start()] + " " * (close + 1 - found.start()) + body[close + 1:]
        position = close + 1
    results += [_recomputed(note, line, row, equation, resolve) for equation in equations(body)]
    table = table_equation(body, header or []) if body.startswith("|") else None
    if table:
        results.append(_recomputed(note, line, row, table, resolve))
    if worked_out and not results and next(numbers_in(body), None):
        results.append(Result(note, line, "unparsed", "", None, row,
                              "no working this reads: neither brackets after the figure nor an equation"))
    return results


def check_text(note: str, text: str, book: Book | None = None) -> list[Result]:
    """The verdicts on one note, line by line. Which rows are worked out is decided as `check_figures` decides it: a
    marker on the row, in its section's heading, or in the prose just before it. Every table is footed too. The Sources
    section is skipped. A figure a working names is looked up in `book`, or with none, in this note's own tables."""
    marked = lambda row: any(word in row for word in WORKED_OUT)
    headers = table_headers(text)
    resolve = (book or Book.of([(note, text)])).resolver(note)
    results: list[Result] = []
    in_sources = heading_marked = lead_in_marked = False
    for line, raw in enumerate(text.splitlines(), 1):
        row = raw.strip()
        if row.startswith("#"):
            in_sources, heading_marked, lead_in_marked = bool(NOT_NOTES.match(row)), marked(row), False
            continue
        if in_sources or not row or re.fullmatch(r"\|[\s\-:|]+\|", row):
            continue
        is_row = row.startswith(("|", "- "))
        if not is_row:
            lead_in_marked = marked(row)
        worked_out = is_row and (heading_marked or lead_in_marked or marked(row))
        results += check_row(note, line, row, headers.get(line), worked_out, resolve)
    # A footing is given on its total row, after whatever else that row's own working gave.
    return sorted(results + footings(note, text), key=lambda result: result.line)


# ---------------------------------------------------------------- rules a workspace sets

@dataclass(frozen=True)
class Rule:
    """A formula the notes' figures must keep to: the figure it gives, and the formula that gives it."""
    name: str
    gives: Reference
    expression: Node
    formula: str


EXAMPLE_RULE = 'formula = "{Gross margin} = {Gross profit} / {Revenue}"'


def rules(config: dict[str, Any]) -> list[Rule]:
    """The rules `[[arithmetic.rules]]` sets in a workspace's settings. Raises WorkspaceError, saying which and why, for
    one that can't be read."""
    section = config.get("arithmetic", {})
    listed = section.get("rules", []) if isinstance(section, dict) else None
    if not isinstance(listed, list):
        raise WorkspaceError(f"The arithmetic rules in {identity.CONFIG} must each be a table of their own, under "
                             f"[[arithmetic.rules]], as {EXAMPLE_RULE}.")
    found: list[Rule] = []
    for number, entry in enumerate(listed, 1):
        where = f"Rule {number} under [[arithmetic.rules]] in {identity.CONFIG}"
        formula = entry.get("formula") if isinstance(entry, dict) else None
        name = entry.get("name", "") if isinstance(entry, dict) else ""
        if not isinstance(formula, str) or not isinstance(name, str):
            raise WorkspaceError(f"{where} needs a formula, written as {EXAMPLE_RULE}, and a name only as words.")
        sides = formula.split("=")
        if len(sides) != 2:
            raise WorkspaceError(f"{where}, {formula!r}, needs one = between the figure it gives and the formula for it.")
        try:
            gives, worked = parse(sides[0]), parse(sides[1])
            if worked.op == "ref" and gives.op != "ref":
                gives, worked = worked, gives
            if gives.op != "ref":
                raise ValueError("one side must name the figure the rule gives, alone in braces")
            if not worked.references():
                raise ValueError("the other side names no figure, so there's nothing in the notes to hold it to")
            names = [reference(text) for text in (gives.name, *worked.references())]
        except ValueError as problem:
            raise WorkspaceError(f"{where}, {formula!r}, can't be read: {problem}.") from None
        found.append(Rule(name.strip() or formula.strip(), names[0], worked, formula))
    return found


def apply(rule: Rule, book: Book) -> list[Result]:
    """The verdicts on one rule: one for each figure the notes' tables state on the line it gives, in that figure's
    period, wherever the notes state every figure it names in that period. A name that matches two figures is
    "unparsed"."""
    results: list[Result] = []
    seen: set[tuple[str, object, Fraction]] = set()
    for entry in book.stating(rule.gives.words):
        if rule.gives.period and (entry.period is None or differ(entry.period, rule.gives.period)):
            continue
        if (entry.note, entry.period, entry.figure.value) in seen:
            continue
        seen.add((entry.note, entry.period, entry.figure.value))
        label = f"{rule.name}, {entry.period.shown() if entry.period else 'no period'}"
        resolve = lambda text, entry=entry: book.find(reference(text), entry.note, entry.period, in_period=True).figure

        def unparsed(why: str, entry: Stated = entry, label: str = label) -> Result:
            return Result(entry.note, entry.line, "unparsed", entry.figure.text, None, entry.row, f"{label}: {why}", label,
                          rule=rule.name)
        try:
            expression = bind(rule.expression, resolve)
            value = expression.evaluate()
        except NotStated:
            continue
        except (Ambiguous, Undefined) as problem:
            results.append(unparsed(str(problem)))
            continue
        item = f"{label}: {entry.figure.text} = {expression.written()}"
        holds, why = recompute(Equation(expression, Node(leaf=entry.figure), item))
        results.append(Result(entry.note, entry.line, "ok" if holds else "wrong", entry.figure.text, float(value[0]), entry.row,
                              item, item, why, tuple(f.text for f in expression.figures() if f.text), rule.name))
    return results


# ---------------------------------------------------------------- the workspace

def check(ws: Workspace) -> list[Result]:
    """The verdicts on every working in the workspace's notes, and on every rule it sets, note by note, line by line.
    Raises WorkspaceError for a rule that can't be read."""
    notes = [(path.name, path.read_text(encoding="utf-8")) for path in note_files(ws)]
    book = Book.of(notes)
    results = [result for note, text in notes for result in check_text(note, text, book)]
    for rule in rules(ws.config()):
        results += apply(rule, book)
    order = {note: at for at, (note, _) in enumerate(notes)}
    return sorted(results, key=lambda result: (order.get(result.note, len(order)), result.line))


def run(ws: Workspace, con: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Print each wrong or unparsed working and a count of each. Exits 1 when a working is wrong; unparsed rows are
    warnings only. A wrong working a row of checks/waivers.csv accepts is listed as waived and doesn't count as wrong."""
    results = check(ws)
    ledger = waivers.Ledger(ws, con)
    counts = Counter(result.status for result in results)
    for result in results:
        if result.status == "wrong":
            decision = ledger.decide("arithmetic", result.note, result.line, result.item)
            if decision and not decision.lapsed:
                print(f"{result.note}:{result.line}  waived    {result.item} {result.why}: {decision.waiver.said()}")
                counts["wrong"] -= 1
                counts["waived"] += 1
                continue
            print(f"{result.note}:{result.line}  wrong     {result.item} {result.why}")
            if decision:
                print(f"  {waivers.lapsed_message(decision)}")
        elif result.status == "unparsed":
            print(f"{result.note}:{result.line}  unparsed  {result.detail}: {result.text}")
    for waiver in ledger.unused(("arithmetic",)):
        print(f"warning: {waivers.unused_message(waiver)}")
    applied = {result.rule for result in results}
    for rule in rules(ws.config()):
        if rule.name not in applied:
            print(f"warning: the rule {rule.formula!r} judged nothing: no table in the notes states every figure it names "
                  "for one period")
    print(f"{counts['ok']} ok, {counts['wrong']} wrong, {counts['unparsed']} unparsed" + (f", {counts['waived']} waived" if counts["waived"] else ""))
    return 1 if counts["wrong"] else 0
