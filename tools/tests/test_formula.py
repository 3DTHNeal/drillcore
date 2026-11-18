"""Tests for the math engine: reading a formula, working it out over the rounding of its figures, its functions and
named formulas, references, and what it refuses."""
import math
import unittest
from fractions import Fraction

import support  # noqa: F401

from drillcore import formula


def value(text: str) -> float:
    return float(formula.evaluate(text))


def bounds(node: formula.Node) -> tuple[float, float, float]:
    worked, low, high = node.evaluate()
    return float(worked), float(low), float(high)


def rounded(text: str) -> formula.Node:
    """A figure as running text writes it, rounded to its last digit."""
    match = formula.AMOUNT.fullmatch(text)
    assert match
    return formula.Node(leaf=formula.figure(match, as_result=True))


class Order(unittest.TestCase):
    def test_powers_bind_tightest_and_run_right_to_left(self):
        self.assertEqual(formula.evaluate("2 ^ 3 ^ 2"), 512)
        self.assertEqual(formula.evaluate("-2 ^ 2"), -4)
        self.assertEqual(formula.evaluate("(-2) ^ 2"), 4)
        self.assertEqual(formula.evaluate("2 * 3 ^ 2"), 18)
        self.assertEqual(formula.evaluate("2 ^ -1"), Fraction(1, 2))
        self.assertEqual(formula.evaluate("4^0.5"), 2)

    def test_whole_powers_are_exact(self):
        self.assertEqual(formula.evaluate("1.1 ^ 2"), Fraction("1.21"))
        self.assertEqual(formula.evaluate("(1 + 5%) ^ 3"), Fraction("1.157625"))


class Functions(unittest.TestCase):
    def test_functions_of_one_figure(self):
        self.assertEqual(value("sqrt(16)"), 4)
        self.assertAlmostEqual(value("ln(exp(2))"), 2)
        self.assertAlmostEqual(value("log10(1,000)"), 3)
        self.assertEqual(value("abs(-3.5)"), 3.5)

    def test_functions_of_many(self):
        self.assertEqual(formula.evaluate("sum(1.5, 2.5, 3)"), 7)
        self.assertEqual(formula.evaluate("avg(1, 2, 6)"), 3)
        self.assertEqual(formula.evaluate("average(1, 2)"), Fraction(3, 2))
        self.assertEqual(formula.evaluate("MEAN(1, 2)"), Fraction(3, 2))
        self.assertEqual(formula.evaluate("median(3, 1, 2, 10)"), Fraction(5, 2))
        self.assertEqual(formula.evaluate("min(4, -1, 2)"), -1)
        self.assertEqual(formula.evaluate("max(1,757, 1,820)"), 1820)  # A comma with no space is a thousands comma.

    def test_named_formulas(self):
        self.assertAlmostEqual(value("cagr(450.0, 551.1, 5)"), (551.1 / 450.0) ** 0.2 - 1)
        self.assertAlmostEqual(value("change(551.1, 572.5)"), 551.1 / 572.5 - 1)
        self.assertAlmostEqual(value("share(67.5, 95.4)"), 67.5 / 95.4)
        # A named formula is put in its own terms, and its constants aren't figures anyone wrote.
        node = formula.parse("cagr(450.0, 551.1, 5)")
        self.assertEqual(node.written(), "(551.1 / 450.0) ^ (1 / 5) - 1")
        self.assertEqual([f.text for f in node.figures() if f.text], ["551.1", "450.0", "5"])

    def test_the_wrong_number_of_figures_cant_be_worked_out(self):
        for text, said in (("cagr(1, 2)", "cagr takes 3 figures, start, end, years, and it's given 2"),
                           ("sqrt(1, 2)", "sqrt takes one figure, and it's given 2")):
            with self.subTest(text=text), self.assertRaises(formula.Undefined) as caught:
                formula.evaluate(text)
            self.assertEqual(str(caught.exception), said)


class Undefined(unittest.TestCase):
    def test_what_cant_be_worked_out_says_why(self):
        for text, said in (("1 / (2 - 2)", "divides by a figure that could be zero"),
                           ("sqrt(-1)", "square root of a figure that could be negative"),
                           ("ln(0)", "log of a figure that could be zero or negative"),
                           ("(-8) ^ (1 / 3)", "isn't a whole number"),
                           ("0 ^ -1", "divides by a figure that could be zero"),
                           ("10 ^ 5000", "too large"),
                           ("exp(1,000,000)", "too large")):
            with self.subTest(text=text), self.assertRaises(formula.Undefined) as caught:
                formula.evaluate(text)
            self.assertIn(said, str(caught.exception))

    def test_anything_but_a_formula_is_refused(self):
        for bad in ("__import__('os')", "os.system('echo hi')", "2 ** 3", "x + 1", "log(100)", "eval(1)", "1e3", "avg()",
                    "avg(1 2)", "sqrt 4", "(" * 200 + "1" + ")" * 200, "-" * 200 + "1", " + ".join(["1"] * 500),
                    "2" + " ^ 2" * 200, "{Revenue 2025}"):
            with self.subTest(bad=bad[:40]), self.assertRaises(ValueError):
                formula.evaluate(bad)


class Rounding(unittest.TestCase):
    def test_bounds_follow_the_rounding_of_each_figure(self):
        squared = formula.Node("^", rounded("1.5"), formula.Node(leaf=formula.exact(2))).evaluate()
        self.assertEqual(squared, (Fraction("2.25"), Fraction("1.45") ** 2, Fraction("1.55") ** 2))
        # Squaring a figure that could be either side of zero can give zero, and nothing below.
        self.assertEqual(bounds(formula.Node("^", rounded("0.0"), formula.Node(leaf=formula.exact(2))))[1], 0)

    def test_a_rate_worked_out_in_floating_point_still_holds_the_true_value(self):
        node = formula.call("cagr", [rounded("450.0"), rounded("551.1"), formula.Node(leaf=formula.exact(5))])
        worked, low, high = bounds(node)
        self.assertLess(low, (551.05 / 450.05) ** 0.2 - 1)
        self.assertGreater(high, (551.15 / 449.95) ** 0.2 - 1)
        self.assertTrue(low < worked < high)
        self.assertLess(high - low, 0.0002)

    def test_functions_of_many_take_each_end(self):
        node = formula.call("median", [rounded("1.0"), rounded("2.0"), rounded("9.0")])
        self.assertEqual(bounds(node), (2.0, 1.95, 2.05))
        self.assertEqual(bounds(formula.call("abs", [rounded("-0.0")]))[1:], (0.0, 0.05))
        self.assertTrue(math.isclose(bounds(formula.call("sqrt", [rounded("4.0")]))[2], math.sqrt(4.05), rel_tol=1e-9))


class RunningText(unittest.TestCase):
    def kinds(self, text: str) -> list[tuple[str, str]]:
        return [(token.kind, token.text) for token in formula.lex(text)]

    def test_a_call_touches_its_bracket_and_its_commas_count_only_inside(self):
        self.assertEqual(self.kinds("avg(1.2, -3.4)"), [("call", "avg"), ("(", "("), ("num", "1.2"), (",", ","), ("num", "-3.4"), (")", ")")])
        self.assertEqual(self.kinds("share (67.5 of 95.4)")[0], ("other", "share"))
        self.assertEqual(self.kinds("growth, 4")[0], ("other", "growth,"))
        self.assertEqual(self.kinds("re-avg(2)")[0][0], "other")

    def test_a_power_needs_no_spaces_but_other_operators_do(self):
        self.assertEqual(self.kinds("1.05^3"), [("num", "1.05"), ("op", "^"), ("num", "3")])
        self.assertNotIn(("op", "-"), self.kinds("2013-2015"))
        self.assertNotIn(("op", "/"), self.kinds("R&D/revenue"))

    def test_a_reference_is_one_token(self):
        self.assertEqual(self.kinds("{Gross profit, Q3 2025} / {Revenue Q3 2025}"),
                         [("ref", "Gross profit, Q3 2025"), ("op", "/"), ("ref", "Revenue Q3 2025")])


class References(unittest.TestCase):
    def test_a_reference_is_bound_before_its_worked_out(self):
        node = formula.parse("{Gross profit} / {Revenue}")
        self.assertEqual(node.references(), ["Gross profit", "Revenue"])
        self.assertEqual(node.operators(), {"/", "{}"})
        named = {"Gross profit": "227.0", "Revenue": "551.1"}
        bound = formula.bind(node, lambda text: formula.figure(formula.AMOUNT.fullmatch(named[text]), as_result=True))
        self.assertEqual(bound.written(), "227.0 / 551.1")
        self.assertAlmostEqual(float(bound.evaluate()[0]), 227.0 / 551.1)
        with self.assertRaises(formula.Undefined):
            formula.bind(node, None)

    def test_references_are_blanked_for_the_number_check(self):
        line = "- Margin: 41.2% (= {Gross profit 2025} / {Revenue 2025})"
        blanked = formula.without_references(line)
        self.assertEqual(len(blanked), len(line))
        self.assertNotIn("2025", blanked)
        self.assertIn("41.2%", blanked)


class Written(unittest.TestCase):
    def test_only_the_brackets_it_needs(self):
        for text in ("2 - (3 - 4) / (5 * 6) ^ 2", "(1 + 2) * 3", "1 + 2 * 3", "(2 ^ 3) ^ 2", "2 ^ 3 ^ 2", "-(1 + 2)", "avg(1, 2 + 3)"):
            with self.subTest(text=text):
                self.assertEqual(formula.parse(text).written(), text)


if __name__ == "__main__":
    unittest.main()
