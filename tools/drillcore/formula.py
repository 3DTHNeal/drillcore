"""The math engine: a formula read, and worked out over the rounding of the figures it's written with.

Everything that recomputes what the notes write goes through here: the arithmetic check's workings, equations,
conversions and footings, and the rules a workspace sets. A formula is read as data and worked out by this module
alone. Text from the notes is never run, and nothing beyond what's listed below is read.

**What a formula may hold.**

- Numbers, with thousands commas, and a percent sign, which makes them hundredths. In running text a number may also
  carry a sign, a currency, a scale and a multiple's x: `-$1.5M`, `RMB 3.7bn`, `12.3x`.
- `+ - * /` (and `× ÷ −`), brackets, and `^` for a power, as `(551.1 / 450.0) ^ (1 / 5) - 1`. A power binds tighter than
  a sign, so `-2 ^ 2` is -4, and runs right to left, so `2 ^ 3 ^ 2` is 2 ^ 9.
- Functions of one figure: `sqrt`, `ln`, `log10`, `exp`, `abs`. Functions of any number: `sum`, `avg` (or `average`,
  `mean`), `median`, `min`, `max`. Arguments are separated by a comma and a space, since `1,757` is one number.
- Named formulas, each defined in the engine's own terms in `NAMED`: `cagr(start, end, years)`, the compound annual
  rate; `change(new, old)`, new over old less one; `share(part, whole)`.
- A reference in braces, `{Revenue 2025}`, to a figure the notes state. The engine doesn't know what one names: a caller
  `bind`s each to a figure before the formula is worked out.

**Two ways of reading.** `parse` reads a formula that is arithmetic through and through, such as the working in "(=
95.4 - 67.5)": operators may stand without spaces, and anything it doesn't know is refused with a ValueError that says
what. `lex` reads a line of running text, where arithmetic stops at the first word: an operator other than `^` needs a
space each side, so a range (2013-2015), a date or a ratio of words (R&D/revenue) isn't read as one, and a function's
name must touch its bracket. `Parser` reads the tokens of either.

**Rounding.** A figure carries the half-unit of its last digit (`Figure.half`), so 551.1 stands for anything from 551.05
to 551.15. Working a formula out gives an `Interval`: its value as written, and the lowest and highest values the
rounding of its inputs allows. `+ - * /` and whole powers are worked out exactly, as fractions. A root, a log, an
exponential or a power that isn't whole is worked out in floating point and its bounds are widened by a trillionth, so
the interval still holds the true value. A formula that can't be worked out, one that divides by a figure that could be
zero or takes the log of one that could be negative, raises `Undefined`, which says why.
"""
import math
import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import cache

NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
# A number as running text writes it: a sign, a currency, the digits, a scale, and a percent sign or a multiple's x.
AMOUNT = re.compile(
    r"(?P<sign>[+\-−])?(?P<currency>US\$|HK\$|\$|€|£|(?:USD|EUR|JPY|RMB|CHF|GBP)\s?)?"
    r"(?P<digits>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s?(?P<word>thousand|million|billion|trillion|bn)\b|(?P<letter>[kMB])\b)?(?P<percent>%)?(?P<times>x\b|×(?!\s))?")
SCALE = {"thousand": 3, "k": 3, "million": 6, "M": 6, "billion": 9, "bn": 9, "B": 9, "trillion": 12}
Interval = tuple[Fraction, Fraction, Fraction]  # the value as written, and the lowest and highest the rounding allows
DIVIDES_BY_ZERO = "it divides by a figure that could be zero"
# How deep brackets and signs may nest, and how many operators a formula may hold, before it's refused as too long.
DEEPEST = 100
MOST_OPERATORS = 400
# Past this many bits an exact whole power is worked out in floating point instead.
LARGEST_POWER = 4096
# How far the bounds of a value worked out in floating point are widened: a trillionth of it, and a little more.
WIDEN = Fraction(1, 10 ** 12)
WIDEN_NEAR_ZERO = Fraction(1, 10 ** 15)


class Undefined(ValueError):
    """A formula that can't be worked out. The message says why, as "it divides by a figure that could be zero"."""


@dataclass(frozen=True)
class Figure:
    """A number in a formula: its value, how far its rounding lets it be off, and what it's written with. `text` is
    the number as written, or "" for a constant of a named formula, which no note writes."""
    value: Fraction
    half: Fraction
    scaled: bool
    percent: bool
    signed: bool
    text: str


def figure(match: re.Match[str], as_result: bool = False) -> Figure:
    """A number `AMOUNT` matched, with the half-unit of its last digit. An input written as a whole number without a
    scale, such as a count of 24 or a total of 59,253, is taken as exact; one with decimals or a scale is rounded. A
    result is rounded whatever it's written as."""
    digits = match.group("digits").replace(",", "")
    decimals = len(digits.split(".")[1]) if "." in digits else 0
    scale = Fraction(10) ** SCALE.get(match.group("word") or match.group("letter") or "", 0)
    if match.group("percent"):
        scale /= 100
    sign = -1 if match.group("sign") in ("-", "−") else 1
    rounded = as_result or decimals > 0 or bool(match.group("word") or match.group("letter"))
    half = Fraction(1, 2) * Fraction(10) ** -decimals * scale if rounded else Fraction(0)
    return Figure(sign * Fraction(digits) * scale, half, bool(match.group("word") or match.group("letter")),
                  bool(match.group("percent")), bool(match.group("sign")), match.group(0))


def exact(value: Fraction | int, text: str = "") -> Figure:
    """A figure known exactly, such as a constant or a count of years."""
    return Figure(Fraction(value), Fraction(0), False, False, False, text)


EMPHASIS_MARKS = re.compile(r"\*+|(?<!\w)_+|_+(?!\w)")
NIL = ("-", "–", "—", "−", "nil")


def label(cell: str) -> str:
    """A table cell without its Markdown emphasis, so `**Total**` reads as Total."""
    return EMPHASIS_MARKS.sub("", cell).strip()


def cell_figure(cell: str) -> Figure | None:
    """A table cell as one figure, rounded to its last digit, or None when it isn't one. An accounting negative, (12.4),
    is read as -12.4, and a dash as nil. A multiple, 12.3x, isn't read."""
    text = label(cell)
    if text.lower() in NIL:
        return Figure(Fraction(0), Fraction(0), False, False, False, text)
    negative = re.fullmatch(r"\((.+)\)", text)
    if negative:
        text = "-" + negative.group(1).strip()
    match = AMOUNT.fullmatch(text)
    if not match or match.group("times"):
        return None
    return figure(match, as_result=True)


# ---------------------------------------------------------------- formulas as trees

@dataclass(frozen=True)
class Node:
    """A parsed formula. `op` is "" for a figure (in `leaf`), one of + - * / ^ over `left` and `right`, "neg" for a
    minus sign over `left`, "call" for a function `name` over `args`, or "ref" for a reference whose words are `name`."""
    op: str = ""
    left: "Node | None" = None
    right: "Node | None" = None
    leaf: Figure | None = None
    name: str = ""
    args: tuple["Node", ...] = ()

    def children(self) -> Iterator["Node"]:
        yield from (child for child in (self.left, self.right, *self.args) if child is not None)

    def figures(self) -> list[Figure]:
        """Every figure the formula is written with, in order."""
        if self.leaf:
            return [self.leaf]
        return [found for child in self.children() for found in child.figures()]

    def operators(self) -> set[str]:
        """What the formula does beyond stating one figure: its operators, the functions it calls, and "{}" for a
        reference. Empty for a lone figure."""
        if self.leaf:
            return set()
        own = {self.name if self.op == "call" else "{}" if self.op == "ref" else self.op}
        return own.union(*(child.operators() for child in self.children()))

    def references(self) -> list[str]:
        """The words of each reference the formula makes, in order."""
        if self.op == "ref":
            return [self.name]
        return [found for child in self.children() for found in child.references()]

    def evaluate(self) -> Interval:
        """The value as written, and the lowest and highest the rounding of its figures allows. Raises Undefined when
        it can't be worked out."""
        try:
            return _evaluate(self)
        except ZeroDivisionError:
            raise Undefined(DIVIDES_BY_ZERO) from None
        except (OverflowError, RecursionError):
            raise Undefined("it's too large to work out") from None

    def written(self) -> str:
        """The formula as a person would write it, with the figures in it and only the brackets it needs."""
        return _written(self, 0, "")


PRECEDENCE = {"+": 1, "-": 1, "*": 2, "/": 2, "neg": 3, "^": 4}


def _written(node: Node, outer: int, side: str) -> str:
    if node.leaf:
        return node.leaf.text or show(node.leaf.value)
    if node.op == "ref":
        return "{" + node.name + "}"
    if node.op == "call":
        return f"{node.name}({', '.join(_written(arg, 0, '') for arg in node.args)})"
    assert node.left is not None
    own = PRECEDENCE[node.op]
    if node.op == "neg":
        text = "-" + _written(node.left, own, "right")
    else:
        assert node.right is not None
        text = f"{_written(node.left, own, 'left')} {node.op} {_written(node.right, own, 'right')}"
    # Brackets where the order would otherwise change: a lower operator inside a higher, the right of - or / (and of
    # + or *, which is harmless), and the left of a power, which runs right to left.
    bracket = own < outer or (own == outer and (side == "left") == (node.op == "^") and side != "")
    return f"({text})" if bracket else text


def show(value: Fraction) -> str:
    """A value to six significant figures, with thousands commas."""
    return f"{float(value):,.6g}"


def _evaluate(node: Node) -> Interval:
    if node.leaf:
        value, half = node.leaf.value, node.leaf.half
        return value, value - half, value + half
    if node.op == "ref":
        raise Undefined(f"{{{node.name}}} names a figure, and nothing here looks one up")
    if node.op == "call":
        return _call(node.name, [_evaluate(arg) for arg in node.args])
    assert node.left is not None
    a = _evaluate(node.left)
    if node.op == "neg":
        return -a[0], -a[2], -a[1]
    assert node.right is not None
    b = _evaluate(node.right)
    if node.op == "+":
        return a[0] + b[0], a[1] + b[1], a[2] + b[2]
    if node.op == "-":
        return a[0] - b[0], a[1] - b[2], a[2] - b[1]
    if node.op == "^":
        return _power(a, b)
    if node.op == "/":
        if b[1] <= 0 <= b[2]:
            raise Undefined(DIVIDES_BY_ZERO)
        b = (1 / b[0], 1 / b[2], 1 / b[1])
    ends = [a[1] * b[1], a[1] * b[2], a[2] * b[1], a[2] * b[2]]
    return a[0] * b[0], min(ends), max(ends)


def _fraction(value: float) -> Fraction:
    if not math.isfinite(value):
        raise Undefined("it's too large to work out")
    return Fraction(value)


def _widened(low: Fraction, high: Fraction) -> tuple[Fraction, Fraction]:
    return low - abs(low) * WIDEN - WIDEN_NEAR_ZERO, high + abs(high) * WIDEN + WIDEN_NEAR_ZERO


def _whole_power(base: Fraction, power: int) -> Fraction:
    if max(base.numerator.bit_length(), base.denominator.bit_length()) * abs(power) <= LARGEST_POWER:
        return base ** power
    return _fraction(math.pow(float(base), power))


def _power(a: Interval, b: Interval) -> Interval:
    """A to the power B. A whole power known exactly is worked out exactly; any other needs a base above zero."""
    if b[1] == b[2] and b[0].denominator == 1:
        power = int(b[0])
        if power < 0 and a[1] <= 0 <= a[2]:
            raise Undefined(DIVIDES_BY_ZERO)
        ends = [_whole_power(a[1], power), _whole_power(a[2], power)]
        if power > 0 and power % 2 == 0 and a[1] < 0 < a[2]:
            ends.append(Fraction(0))
        return _whole_power(a[0], power), min(ends), max(ends)
    if a[1] <= 0:
        raise Undefined("it raises a figure that could be zero or negative to a power that isn't a whole number")
    # A power of a base above zero rises or falls with each of the two, so its extremes are at the corners.
    corners = [_fraction(math.pow(float(x), float(y))) for x in (a[1], a[2]) for y in (b[1], b[2])]
    low, high = _widened(min(corners), max(corners))
    return _fraction(math.pow(float(a[0]), float(b[0]))), low, high


def _through(function: Callable[[float], float], a: Interval) -> Interval:
    """A rising function of one figure, worked out at the value and at each bound."""
    low, high = _widened(_fraction(function(float(a[1]))), _fraction(function(float(a[2]))))
    return _fraction(function(float(a[0]))), low, high


def _absolute(a: Interval) -> Interval:
    if a[1] >= 0:
        return abs(a[0]), a[1], a[2]
    if a[2] <= 0:
        return abs(a[0]), -a[2], -a[1]
    return abs(a[0]), Fraction(0), max(-a[1], a[2])


def _median(values: list[Fraction]) -> Fraction:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _each(function: Callable[[list[Fraction]], Fraction], values: list[Interval]) -> Interval:
    """A function that rises with each of its figures, worked out at the values and at each end."""
    return function([v[0] for v in values]), function([v[1] for v in values]), function([v[2] for v in values])


def _root(a: Interval) -> Interval:
    if a[1] < 0:
        raise Undefined("it takes the square root of a figure that could be negative")
    return _through(math.sqrt, a)


def _log(function: Callable[[float], float]) -> Callable[[Interval], Interval]:
    def worked(a: Interval) -> Interval:
        if a[1] <= 0:
            raise Undefined("it takes the log of a figure that could be zero or negative")
        return _through(function, a)
    return worked


# Functions of one figure.
ONE: dict[str, Callable[[Interval], Interval]] = {
    "sqrt": _root,
    "ln": _log(math.log),
    "log10": _log(math.log10),
    "exp": lambda a: _through(math.exp, a),
    "abs": _absolute,
}
# Functions of any number of figures, each rising with every figure, so worked out at the values and at each end.
MANY: dict[str, Callable[[list[Fraction]], Fraction]] = {
    "sum": lambda values: sum(values, Fraction(0)),
    "avg": lambda values: sum(values, Fraction(0)) / len(values),
    "median": _median,
    "min": min,
    "max": max,
}
ALIASES = {"average": "avg", "mean": "avg"}
# Named formulas, each defined in the engine's own terms: the figures it takes, and what it does with them.
NAMED: dict[str, tuple[tuple[str, ...], str]] = {
    "cagr": (("start", "end", "years"), "({end} / {start}) ^ (1 / {years}) - 1"),
    "change": (("new", "old"), "{new} / {old} - 1"),
    "share": (("part", "whole"), "{part} / {whole}"),
}
CALLABLE = frozenset(ONE) | frozenset(MANY) | frozenset(ALIASES) | frozenset(NAMED)


def _arity(name: str) -> str:
    if name in NAMED:
        return f"{name} takes {len(NAMED[name][0])} figures, {', '.join(NAMED[name][0])}"
    return f"{name} takes one figure" if name in ONE else f"{name} takes one figure or more"


def _call(name: str, values: list[Interval]) -> Interval:
    if name in ONE and len(values) == 1:
        return ONE[name](values[0])
    if name in MANY and values:
        return _each(MANY[name], values)
    raise Undefined(f"{_arity(name)}, and it's given {len(values)}")


@cache
def _definition(name: str) -> Node:
    return parse(NAMED[name][1])


def _substitute(node: Node, given: dict[str, Node]) -> Node:
    """A named formula's definition with its figures put in, and its own constants left without text, since no note
    writes them."""
    if node.op == "ref":
        return given[node.name]
    if node.leaf:
        return replace(node, leaf=replace(node.leaf, text=""))
    return replace(node, left=_substitute(node.left, given) if node.left else None,
                   right=_substitute(node.right, given) if node.right else None,
                   args=tuple(_substitute(arg, given) for arg in node.args))


def call(name: str, args: Sequence[Node]) -> Node:
    """A call of a function or a named formula. A named formula is put in its own terms; a call with the wrong number
    of figures is kept as written and can't be worked out."""
    name = ALIASES.get(name.lower(), name.lower())
    if name in NAMED and len(args) == len(NAMED[name][0]):
        return _substitute(_definition(name), dict(zip(NAMED[name][0], args, strict=True)))
    return Node("call", name=name, args=tuple(args))


def bind(node: Node, resolve: Callable[[str], Figure] | None) -> Node:
    """The formula with each reference replaced by the figure it names. `resolve` takes a reference's words and gives
    the figure, or raises Undefined to say why it can't; with no `resolve`, a reference can't be worked out."""
    if node.op == "ref":
        if resolve is None:
            raise Undefined(f"{{{node.name}}} names a figure, and nothing here looks one up")
        return Node(leaf=resolve(node.name))
    if node.leaf or not any(True for _ in node.children()):
        return node
    return replace(node, left=bind(node.left, resolve) if node.left else None,
                   right=bind(node.right, resolve) if node.right else None,
                   args=tuple(bind(arg, resolve) for arg in node.args))


# ---------------------------------------------------------------- reading a formula

@dataclass(frozen=True)
class Token:
    kind: str  # "num", "op", "(", ")", ",", "=", "call", "ref", "approx" or "other"
    text: str
    figure: Figure | None = None


REFERENCE = re.compile(r"\{(?P<name>[^{}\n]{1,120})\}")
# Operators in running text stand between spaces, so a range (2013-2015), a date (2026-07-28) or a ratio of words
# (R&D/revenue) isn't one. A power is the exception: nothing else in running text writes ^.
OPERATOR = re.compile(r"(?<=\s)(?:[+\-−–*/÷×]|x)(?=\s)")
APPROX = re.compile(r"(?:about|roughly|approximately|approx\.|around|nearly|c\.|~|≈)(?=\s|\$|\d|-)", re.I)
# A function's name touching its bracket, as running text writes a call: "avg(1.2, 3.4)".
CALL = re.compile(r"(?P<name>[A-Za-z_]\w*)(?=\()")
WORD = re.compile(r"[^\s()=]+")


def lex(text: str) -> list[Token]:
    """A line of running text as the parser sees it. Anything that isn't a number, an operator, a bracket, an equals
    sign, a call, a reference or a word like "about" is "other", and arithmetic doesn't reach across it. A comma is
    one only between a call's brackets."""
    found: list[Token] = []
    opened: list[bool] = []  # for each bracket open, whether it holds a call's figures
    at = 0
    while at < len(text):
        char = text[at]
        if char.isspace():
            at += 1
            continue
        in_call = bool(opened) and opened[-1]
        before = text[at - 1] if at else " "
        if char in "()=":
            if char == "(":
                opened.append(bool(found) and found[-1].kind == "call" and before != " ")
            elif char == ")" and opened:
                opened.pop()
            found.append(Token(char, char))
            at += 1
            continue
        if char == "^" or (char == "," and in_call):
            found.append(Token("op" if char == "^" else ",", char))
            at += 1
            continue
        reference = REFERENCE.match(text, at)
        if reference:
            found.append(Token("ref", reference["name"].strip()))
            at = reference.end()
            continue
        named = CALL.match(text, at)
        if named and named["name"].lower() in CALLABLE and not (before.isalnum() or before in "_."):
            found.append(Token("call", named["name"]))
            at = named.end()
            continue
        operator = OPERATOR.match(text, at)
        if operator:
            found.append(Token("op", operator.group(0)))
            at = operator.end()
            continue
        approx = APPROX.match(text, at)
        if approx and not before.isalnum():
            found.append(Token("approx", approx.group(0)))
            at = approx.end()
            continue
        amount = AMOUNT.match(text, at)
        after_comma = before == "," and in_call
        glued = (before.isalnum() or before in "._" or (before == "," and not in_call)
                 or (amount is not None and amount.group("sign") and not (before.isspace() or before in "(=~^" or after_comma)))
        if amount and not glued and not (amount.end() < len(text) and (text[amount.end()].isalnum() or text[amount.end()] == "_")):
            found.append(Token("num", amount.group(0), figure(amount)))
            at = amount.end()
            continue
        word = WORD.match(text, at)
        assert word is not None
        found.append(Token("other", word.group(0)))
        at = word.end()
    return found


STRICT = re.compile(rf"(?P<number>{NUM}|\.\d+)(?P<percent>%?)|(?P<op>[-+*/^×÷−])|(?P<mark>[(),])"
                    r"|\{(?P<ref>[^{}\n]{1,120})\}|(?P<name>[A-Za-z_]\w*)")


def lex_formula(text: str) -> list[Token]:
    """A formula that is arithmetic through and through, as tokens. Its numbers are exact: they're what was computed
    with. Raises ValueError, saying where, at anything else."""
    found: list[Token] = []
    at = 0
    while at < len(text):
        if text[at].isspace():
            at += 1
            continue
        match = STRICT.match(text, at)
        if not match:
            raise ValueError(f"the working can't be read from {text[at:at + 20]!r}")
        if match["number"]:
            value = Fraction(match["number"].replace(",", ""))
            percent = bool(match["percent"])
            written = match["number"] + match["percent"]
            found.append(Token("num", written, Figure(value / 100 if percent else value, Fraction(0), False, percent, False, written)))
        elif match["op"]:
            found.append(Token("op", match["op"]))
        elif match["mark"]:
            found.append(Token(match["mark"], match["mark"]))
        elif match["ref"]:
            found.append(Token("ref", match["ref"].strip()))
        elif match["name"].lower() in CALLABLE:
            found.append(Token("call", match["name"]))
        else:
            raise ValueError(f"the working can't be read from {text[at:at + 20]!r}: {match['name']!r} isn't a function this knows")
        at = match.end()
    return found


def _op(text: str) -> str:
    return {"−": "-", "–": "-", "x": "*", "×": "*", "÷": "/"}.get(text, text)


class Parser:
    """Ordinary arithmetic over a run of tokens: brackets and calls first, then powers, then signs, then times and
    divide, then plus and minus. It stops where the arithmetic does and gives what it read, so a caller can read an
    equation out of running text. A sign standing alone before a figure (`-(2 - 5)`) is read only when `signs` is
    set, since running text writes a negative figure with its sign touching it."""

    def __init__(self, run: Sequence[Token], signs: bool = False) -> None:
        self.run, self.at, self.signs = run, 0, signs
        self.depth = self.operators = 0
        self.refused = ""

    def _is(self, kind: str, *texts: str) -> bool:
        if self.at >= len(self.run):
            return False
        token = self.run[self.at]
        return token.kind == kind and (not texts or _op(token.text) in texts)

    @contextmanager
    def _deeper(self) -> Iterator[bool]:
        self.depth += 1
        try:
            if self.depth > DEEPEST:
                self.refused = "the working is nested too deeply"
            yield self.depth <= DEEPEST
        finally:
            self.depth -= 1

    def _counted(self) -> bool:
        self.operators += 1
        if self.operators > MOST_OPERATORS:
            self.refused = "the working is too long"
        return self.operators <= MOST_OPERATORS

    def expression(self) -> Node | None:
        node = self.term()
        while node and self._is("op", "+", "-") and self._counted():
            mark = self.at
            self.at += 1
            right = self.term()
            if right is None:
                self.at = mark
                break
            node = Node(_op(self.run[mark].text), node, right)
        return node

    def term(self) -> Node | None:
        node = self.unary()
        while node and self._is("op", "*", "/") and self._counted():
            mark = self.at
            self.at += 1
            right = self.unary()
            if right is None:
                self.at = mark
                break
            node = Node(_op(self.run[mark].text), node, right)
        return node

    def unary(self) -> Node | None:
        if self.signs and self._is("op", "+", "-"):
            mark = self.at
            self.at += 1
            with self._deeper() as room:
                inner = self.unary() if room else None
            if inner is None:
                self.at = mark
                return None
            return Node("neg", inner) if _op(self.run[mark].text) == "-" else inner
        return self.power()

    def power(self) -> Node | None:
        base = self.primary()
        if base and self._is("op", "^") and self._counted():
            mark = self.at
            self.at += 1
            with self._deeper() as room:
                exponent = self.unary() if room else None
            if exponent is None:
                self.at = mark
                return base
            return Node("^", base, exponent)
        return base

    def primary(self) -> Node | None:
        if self.at >= len(self.run):
            return None
        token = self.run[self.at]
        if token.kind == "num" and token.figure:
            self.at += 1
            return Node(leaf=token.figure)
        if token.kind == "ref":
            self.at += 1
            return Node("ref", name=token.text)
        if token.kind == "call":
            return self._call()
        if token.kind == "(":
            mark = self.at
            self.at += 1
            with self._deeper() as room:
                inner = self.expression() if room else None
            if inner and self._is(")"):
                self.at += 1
                return inner
            self.at = mark
        return None

    def _call(self) -> Node | None:
        mark = self.at
        name = self.run[self.at].text
        self.at += 1
        if not self._is("("):
            self.at = mark
            return None
        self.at += 1
        args: list[Node] = []
        with self._deeper() as room:
            while room:
                arg = self.expression()
                if arg is None:
                    break
                args.append(arg)
                if not self._is(","):
                    break
                self.at += 1
        if not args or not self._is(")"):
            self.at = mark
            return None
        self.at += 1
        return call(name, args)


def parse(text: str) -> Node:
    """A formula that is arithmetic through and through, such as a working written after "=". Raises ValueError, saying
    what, when it isn't one."""
    tokens = lex_formula(text)
    parser = Parser(tokens, signs=True)
    node = parser.expression()
    if parser.refused:
        raise ValueError(parser.refused)
    if node is None:
        if not tokens:
            raise ValueError("the working is missing a number")
        raise ValueError(f"the working can't be read from {' '.join(t.text for t in tokens[parser.at:parser.at + 5])!r}")
    if parser.at < len(tokens):
        raise ValueError(f"the working has {tokens[parser.at].text!r} where it should end or go on with + - * / ^")
    return node


def evaluate(text: str, resolve: Callable[[str], Figure] | None = None) -> Fraction:
    """The value of a formula such as "95.4 - 67.5", "(1,757 - 1,820) / 1,820" or "cagr(450, 551.1, 5)", from the
    figures as written. Raises ValueError, saying what, for anything it can't read or work out."""
    return bind(parse(text), resolve).evaluate()[0]


def without_references(text: str) -> str:
    """A line with each reference blanked out, the same length as before: the words in braces name a figure, they
    don't state one."""
    return REFERENCE.sub(lambda match: " " * len(match.group(0)), text)
