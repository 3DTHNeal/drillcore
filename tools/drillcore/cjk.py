"""Figures as a page in Chinese writes them, put into the digits every check reads.

Chinese counts in ten-thousands (万) and hundred-millions (亿), so 37亿元 is 3.7 billion yuan and 912.56万元 is
9,125,600. Those aren't powers of a thousand, and a check that only shifts a number by thousands, millions or billions
can find such a figure only by the digits it happens to share with something else. `in_digits` writes each one out in
full instead, so the unit beside the number is what gives it its scale: `37亿` becomes `3700000000`, and a note's
"RMB 3.7bn" is held to that and to nothing else on the page.

It also puts a space wherever a Chinese character touches a digit or a Latin letter. A reader of numbers looks for one
that starts a word, and in 出货260万台 or 工业级3D打印 the characters before the digits are letters too.

Nothing is worked out and nothing is guessed: a number is rewritten only when a unit stands against it, and a round
amount written without digits is read only as 十亿, 百亿 or 千亿, which can't be anything else. 千万 alone is as often
"be sure to" as ten million, so it's left as it is. The same reading is given to a note's line and to its source, so a
note that repeats a page's own characters is held to them like any other figure.
"""
import re
from decimal import Decimal, InvalidOperation

HAN = "一-鿿"
POWER = {"万": 4, "亿": 8}
TENS = {"十": 1, "百": 2, "千": 3}
_NUMBER = r"\d[\d,]*(?:\.\d+)?"
# A number against its unit, as 260万, 7.25亿, 3千万 or 100万亿, with a space between them allowed. A range may give the
# unit once, after its second figure, as in 46-52亿元: both are in that unit.
FIGURE = re.compile(rf"(?<![\d.,])(?P<a>{_NUMBER})\s*(?:(?P<to>[-–—~至到])\s*(?P<b>{_NUMBER})\s*)?(?P<unit>万亿|[十百千]?[万亿])")
# A round amount with no digits: 破百亿 is "past ten billion". Not after another numeral, since 三百亿 is thirty billion,
# nor after 数, 几 or 多, which make it "several".
ROUND = re.compile(r"(?<![\d.,一二两三四五六七八九十百千万亿数几多半])(?P<tens>[十百千])亿")
# Where a Chinese character touches a digit, a Latin letter or a currency sign, on either side.
EDGE = re.compile(rf"(?<=[{HAN}])(?=[0-9A-Za-z$€£¥])|(?<=[0-9A-Za-z%])(?=[{HAN}])")


def _power(unit: str) -> int:
    """The power of ten a unit stands for: 万 is 4, 千万 is 7, 亿 is 8 and 万亿 is 12."""
    if unit == "万亿":
        return 12
    return TENS.get(unit[0], 0) + POWER[unit[-1]]


def _written_out(digits: str, power: int) -> str:
    """A number at its unit's scale, in plain digits: 912.56 and 4 is 9125600."""
    try:
        amount = Decimal(digits.replace(",", "")).scaleb(power)
    except InvalidOperation:
        return digits
    text = format(amount, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _figure(match: re.Match[str]) -> str:
    power = _power(match.group("unit"))
    first = _written_out(match.group("a"), power)
    if match.group("b") is None:
        return first
    return f"{first}-{_written_out(match.group('b'), power)}"


def in_digits(text: str) -> str:
    """The text with each figure counted in 万 or 亿 written out in full, and Chinese characters set apart from the
    digits and Latin letters they touch. Text with no Chinese in it comes back as it was."""
    if not re.search(f"[{HAN}]", text):
        return text
    text = FIGURE.sub(_figure, text)
    text = ROUND.sub(lambda match: "1" + "0" * (TENS[match.group("tens")] + POWER["亿"]), text)
    return EDGE.sub(" ", text)
