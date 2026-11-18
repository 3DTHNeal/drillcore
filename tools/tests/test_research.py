"""Tests for the research checks: citations, quotations, arithmetic and the assay's number check. Each test works on a
copy of the fictional example with a note of its own added, and sources answered by a stand-in for the network."""
import csv
import shutil
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

from support import CODE_ROOT, run_cli

from assay import numbers as assay_numbers
from drillcore import citations, record, research, sourcedb, workspace

ANNUAL = "https://example.com/northbridge/annual-2025.html"
ORDERS = "https://example.com/northbridge/orders.html"
ANNUAL_PAGE = """<html><head><title>Annual Report 2025</title></head><body>
<h1>Northbridge Robotics</h1><p>In thousands of dollars.</p>
<table><tr><th>Revenue</th><td>551,102</td><td>572,514</td></tr></table>
<p>“We shipped our 1,000th robot,” the chief executive said. Revenue fell in 2025.</p>
<p>Operating loss was (12,400) thousand.</p>
<p>Legal and other expenses rose.</p>
<p>ORDER BOOK REVIEW</p></body></html>""".encode()
ORDERS_PAGE = b"Order book 95.4 million, 67.5 million due."

NOTE = """# Checks

Fictional, for the tests.

## 1. Quotes and figures (S1)

| Item | 2025 | Source |
|---|---|---|
| Revenue, $M | 551.1 | S1 |
| A figure no source holds | $999.9M | S1 |
| Operating loss | $(12,400) thousand | S1 |

- The chief executive said "We shipped our 1,000th robot." (S1)
- He said “we shipped ... robot” (S1).
- The release calls it "legal and other expenses" (S1).
- The release says "Order Book Review" (S1).
- The release says "we sold more robots than ever" (S1).
- The order book stood at $95.4M on 3 March 2026 (S2).
- In 9M 2025 the order book was steady (S2).
- A key listed without an address: S3. A key listed nowhere: S9. A printer model: F370.

Prose that names no key of its own, quoting "a phrase" all the same.

The same order book is in the other note (file 01 sources S2).

## 2. Worked out

COMPUTED from the table above:

- Sum: 150.4 + 43.2 = $193.6 million.
- Chained: 6.063 x 1.21 = 7.34, and 7.34 x 1.335 = 9.79.
- Wrong: 12 + 8 = 21 transactions.
- Range, then a sum: 2013-2015 = 11 + 9 + 4 = 24 transactions.
- Labels, then a sum: 2022 + 2023 = 498.8 + 112.9 = $611.7M.
- Growth: 6.063 / 5.165 = +17.4%.
- Revenue change about -3.7% from 551.1 and 572.5.

| Measure | Result | Arithmetic |
|---|---|---|
| Revenue change | -3.7% | (551.1 - 572.5) / 572.5 |
| Share of revenue | 31.0% | R&D / revenue |

## Sources

- **S1.** Northbridge Robotics. 2026. *Annual Report 2025.* https://example.com/northbridge/annual-2025.html
- **S2.** Northbridge Robotics. 2026. "Order book update." https://example.com/northbridge/orders.html
- **S3.** A report not yet found.
"""


class Checked(unittest.TestCase):
    """A copy of the example with the note above added, its sources fetched from stand-ins, and the checks run."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        (root / "research" / "02_checks.md").write_text(NOTE, encoding="utf-8")
        self.ws = workspace.Workspace(root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)

    def fetch(self, pages=None):
        pages = {ANNUAL: ANNUAL_PAGE, ORDERS: ORDERS_PAGE} if pages is None else pages

        def get(url):
            body = pages.get(url)
            return (200, "text/html", url, body, None) if body else (404, "", url, b"", "HTTP 404")
        sourcedb.record_sources(self.ws, self.con)
        sourcedb.fetch(self.ws, self.con, get=get, say=lambda _: None)

    def results(self, check, pages=None):
        self.fetch(pages)
        return [r for r in research.run(self.ws, self.con) if r.check == check and r.note == "02_checks.md"]

    def by_item(self, check, pages=None):
        return {r.item: (r.status, r.detail) for r in self.results(check, pages)}


class Lines(Checked):
    def test_each_line_knows_its_section_its_keys_and_whether_it_was_worked_out(self):
        self.fetch()
        read = [line for line in sourcedb.note_lines(self.ws, self.con) if line.note == "02_checks.md"]
        line = lambda start: next(found for found in read if found.text.startswith(start))
        self.assertEqual((line("| Revenue").keys, line("| Revenue").basis, line("| Revenue").kind), (("S1",), "row", "row"))
        self.assertEqual(line("- The order book stood").keys, ("S2",))
        self.assertEqual((line("Prose that names").keys, line("Prose that names").basis), (("S1",), "section"))
        self.assertEqual(line("Prose that names").kind, "prose")
        self.assertTrue(line("- Sum:").worked_out)
        self.assertTrue(line("| Share of revenue").worked_out)  # The prose above the table says so.
        self.assertFalse(line("| Revenue").worked_out)
        self.assertEqual(line("- **S1.**").section, "sources")
        self.assertEqual(line("## 2. Worked out").kind, "heading")
        self.assertNotIn("|---|---|---|", [found.text for found in read])


class Citations(Checked):
    def cited(self, pages=None):
        """The results for each key a line cites, leaving out those about a Sources entry."""
        return [r for r in self.results("citations", pages) if r.status in ("resolves", "unresolved")]

    def test_every_key_a_line_cites_has_an_address(self):
        found = {}
        for r in self.cited():
            found.setdefault(r.item, set()).add((r.status, r.detail))
        self.assertEqual(found["S1"], {("resolves", "1 address(es)")})
        self.assertEqual(found["S3"], {("unresolved", "the Sources list names it without an address")})
        self.assertEqual(found["S9"], {("unresolved", "no Sources list this note can use names it")})
        self.assertNotIn("F370", found)  # Not shaped like this note's keys.
        self.assertIn(("resolves", "1 address(es) in 01_northbridge.md"), found["S2"])

    def test_a_sources_list_is_not_read_for_citations_but_its_entries_are_checked(self):
        results = self.results("citations")
        sources_section = set(range(NOTE.splitlines().index("## Sources") + 1, len(NOTE.splitlines()) + 1))
        self.assertFalse({r.line_no for r in results if r.status in ("resolves", "unresolved")} & sources_section)
        # What `drillcore citations` says of the list itself: S3's entry gives no address.
        entries = [(r.status, r.line_no, r.item, r.verdict) for r in results if r.status not in ("resolves", "unresolved")]
        self.assertEqual(entries, [("no_url", NOTE.splitlines().index("- **S3.** A report not yet found.") + 1, "S3", research.FAIL)])

    def test_a_source_not_yet_fetched_isnt_judged_here_but_is_an_error_for_the_citations_command(self):
        sourcedb.record_sources(self.ws, self.con)
        results = [r for r in research.run(self.ws, self.con) if r.check == "citations" and r.note == "02_checks.md"]
        unfetched = {(r.status, r.verdict) for r in results if r.item in ("S1", "S2") and r.status not in ("resolves", "unresolved")}
        self.assertEqual(unfetched, {("not_fetched", research.NOT_JUDGED)})
        cited = [r.status for r in results if r.item == "S1" and r.status in ("resolves", "unresolved")]
        self.assertEqual(set(cited), {"resolves"})  # It has an address all the same.
        self.assertIn("not_fetched", {f.kind for f in citations.check(self.ws, self.con) if f.severity == "error"})

    def test_an_entry_nothing_cites_is_a_warning(self):
        note = self.ws.root / "research" / "02_checks.md"
        note.write_text(NOTE.replace("A key listed without an address: S3.", "A key listed without an address."), encoding="utf-8")
        unused = [(r.item, r.verdict) for r in self.results("citations") if r.status == "unused"]
        self.assertEqual(unused, [("S3", research.WARN)])


class Quotations(Checked):
    def test_a_quotation_must_appear_word_for_word_in_a_source_it_cites(self):
        found = self.by_item("quotations")
        self.assertEqual(found["We shipped our 1,000th robot."], ("exact", ANNUAL))  # A full stop inside the mark is fine.
        self.assertEqual(found["we shipped ... robot"][0], "exact")  # Each side of an ellipsis, in order.
        self.assertEqual(found["legal and other expenses"][0], "exact")  # The first letter's case may change.
        self.assertEqual(found["we sold more robots than ever"][0], "not_in_source")
        self.assertNotIn("capital letters", found["we sold more robots than ever"][1])
        self.assertEqual(found["Order Book Review"][0], "not_in_source")
        self.assertIn("capital letters are ignored", found["Order Book Review"][1])

    def test_a_quotation_isnt_judged_without_a_source_to_judge_it_by(self):
        found = self.by_item("quotations", pages={})
        self.assertEqual(found["We shipped our 1,000th robot."][0], "source_text_unavailable")
        self.assertEqual(research.VERDICT["source_text_unavailable"], research.NOT_JUDGED)

    def test_a_quotation_of_a_document_the_workspace_says_isnt_a_source_isnt_judged(self):
        (self.ws.root / "research" / "03_brief.md").write_text(
            "# Against the brief\n\n| Brief said | What the report shows | Source |\n|---|---|---|\n"
            '| "sales doubled" | "Revenue fell in 2025" | S1 |\n| Sales "doubled" again | "Sales doubled" | S1 |\n\n'
            'The brief calls it "a record year". The report says "Revenue fell in 2025" (S1). A note says "a record year" (S1).\n'
            'Revenue fell (the brief has it up); the report calls it "Revenue fell in 2025" (S1).\n\n'
            f"## Sources\n\n- **S1.** Annual report. {ANNUAL}\n", encoding="utf-8")
        self.fetch()

        def statuses():
            return [(r.item, r.status) for r in research.run(self.ws, self.con) if r.check == "quotations" and r.note == "03_brief.md"]
        self.assertNotIn("quotes_a_non_source", {status for _, status in statuses()})  # Without the setting, all judged.
        config = self.ws.config_path
        config.write_text(config.read_text(encoding="utf-8") + '\n[check.quotations]\nnot_sources = ["brief"]\n', encoding="utf-8")
        self.assertEqual(statuses(), [
            ("sales doubled", "quotes_a_non_source"),  # In the column headed by the brief.
            ("Revenue fell in 2025", "exact"),  # The next column on the same row is still judged.
            ("doubled", "quotes_a_non_source"),
            ("Sales doubled", "not_in_source"),
            ("a record year", "quotes_a_non_source"),  # In the sentence that names the brief.
            ("Revenue fell in 2025", "exact"),
            ("a record year", "not_in_source"),  # A sentence later, it's the note's own claim again.
            ("Revenue fell in 2025", "exact"),  # And so after a semicolon.
        ])
        self.assertEqual(research.VERDICT["quotes_a_non_source"], research.NOT_JUDGED)


class Arithmetic(Checked):
    def test_worked_out_figures_recompute_from_their_inputs(self):
        found = {r.item: (r.status, r.detail) for r in self.results("arithmetic") if r.item}
        self.assertEqual(found["150.4 + 43.2 = $193.6 million"][0], "recomputes")  # The result alone states the unit.
        self.assertEqual(found["6.063 x 1.21 = 7.34"][0], "recomputes")
        self.assertIn("within the rounding of its inputs", found["7.34 x 1.335 = 9.79"][1])
        self.assertEqual(found["12 + 8 = 21"], ("does_not_recompute", "computes to 20, not 21"))
        self.assertEqual(found["11 + 9 + 4 = 24"][0], "recomputes")
        self.assertEqual(found["498.8 + 112.9 = $611.7M"][0], "recomputes")
        self.assertNotIn("2022 + 2023 = 498.8 + 112.9", found)  # Labels added up aren't an equation.
        self.assertEqual(found["6.063 / 5.165 = +17.4%"], ("recomputes", "recomputes as a change: 17.3863%"))
        self.assertEqual(found["(551.1 - 572.5) / 572.5 = -3.7%"][0], "recomputes")  # From a Result and an Arithmetic column.

    def test_worked_out_figures_whose_arithmetic_cant_be_read_are_reported_not_guessed(self):
        unread = [r.row_text for r in self.results("arithmetic") if r.status == "not_parsed"]
        self.assertEqual(unread, ["- Revenue change about -3.7% from 551.1 and 572.5.", "| Share of revenue | 31.0% | R&D / revenue |"])
        self.assertEqual(research.VERDICT["not_parsed"], research.NOT_JUDGED)


class Numbers(Checked):
    def test_each_row_is_judged_by_the_assay_against_the_sources_it_cites(self):
        found = {r.item: (r.status, r.detail) for r in self.results("numbers") if r.status == "not_in_source"}
        self.assertEqual(list(found), ["$999.9M"])
        self.assertEqual(found["$999.9M"][1], "number 999900000: absent from the cited source text")
        passed = [r.row_text for r in self.results("numbers") if r.status == "supported"]
        self.assertIn("| Revenue, $M | 551.1 | S1 |", passed)  # At the filing's scale, in thousands.
        self.assertIn("| Operating loss | $(12,400) thousand | S1 |", passed)  # An accounting negative keeps its scale.
        self.assertIn("- The order book stood at $95.4M on 3 March 2026 (S2).", passed)  # The date isn't a figure.

    def test_what_isnt_a_measurement_is_set_aside_by_the_assays_policy(self):
        def kinds(text):
            return [kind for kind, _, _ in assay_numbers.not_measured(text, research.POLICY)]
        self.assertEqual(kinds("9M 2025 on 2026-07-28, 3 March 2026 and July 13, 2023"), ["period", "year", "date", "date", "date"])
        self.assertEqual(kinds("Regulation (EU) 2024/1781; CAS 75980-60-8 (million yen)"), ["identifier", "identifier", "unit label"])
        self.assertEqual(kinds("$(103,567) thousand and 2,024 units"), ["negative"])

    def test_rows_without_a_source_or_its_text_arent_judged(self):
        statuses = {r.status for r in self.results("numbers", pages={}) if not r.status.startswith("input")}
        self.assertEqual(statuses, {"source_text_unavailable"})
        worked = {r.status for r in self.results("numbers") if "150.4" in r.row_text}
        # A worked-out row's figures are the arithmetic check's; only the inputs its working starts from are traced.
        self.assertEqual(worked, {"input_not_traced"})

    def test_a_miss_says_what_the_looser_test_makes_of_it(self):
        sources = research.Sources(self.ws, self.con)
        finding = research.Finding("numbers", "number", "4900000", "$4.9M", 0, 5)
        pages = {"scale": "Investments 4,912 (in thousands).", "kind": "Margin 4.9%.", "chinese": "收入" * 60 + " 49",
                 "absent": "Nothing to see."}
        for name, text in pages.items():
            sources._text[name] = text
        why = {name: research.why_missing(finding, [name], sources) for name in pages}
        self.assertIn("measured policy shifts scale only for a figure written to 3", why["scale"])
        self.assertIn("digits are in the cited source", why["kind"])
        self.assertIn("in Chinese", why["chinese"])
        self.assertEqual(why["absent"], "absent from the cited source text")


LABELLED_PAGE = ("<html><body><p>Revenue was $551.1 million, against $572.5 million.</p><p>Net loss was $12.4 million.</p>"
                 f"<p>{'Nothing else of note happened here. ' * 12}</p><p>Cash at year end was $45.0 million. "
                 "The company opened 3 plants.</p></body></html>").encode()
LABELLED = f"""# Labelled

## 1. Results (S1)

- Revenue was $551.1M (S1).
- Net income was $12.4M (S1).
- Cash at year end was $45.0M (S1).
- Debt stood at $12.4M (S1).
- Northbridge opened 3 plants (S1).

| Region | Revenue |
|---|---|
| North | 572.5 |

## Sources

- **S1.** Northbridge Robotics. 2026. *Annual Report 2025.* {ANNUAL}
- **S2.** Northbridge Robotics. 2026. "Order book update." {ORDERS}
"""


class Labelled(Checked):
    """A figure the source holds, but said there of something else."""

    def setUp(self):
        super().setUp()
        (self.ws.root / "research" / "02_checks.md").write_text(LABELLED, encoding="utf-8")

    def warned(self):
        return {(r.row_text, r.item) for r in self.results("numbers", {ANNUAL: LABELLED_PAGE}) if r.status == "not_near_label"}

    def test_a_figure_far_from_every_word_its_row_names_is_a_warning(self):
        # The source gives $12.4 million as a net loss: neither "income" nor "debt" is anywhere near it.
        self.assertEqual(self.warned(), {("- Net income was $12.4M (S1).", "$12.4M"), ("- Debt stood at $12.4M (S1).", "$12.4M")})

    def test_a_row_word_near_the_figure_a_short_figure_or_a_header_word_is_enough(self):
        rows = {row for row, _ in self.warned()}
        self.assertNotIn("- Revenue was $551.1M (S1).", rows)
        self.assertNotIn("- Cash at year end was $45.0M (S1).", rows)  # Far from the rest of the page, but by "cash".
        self.assertNotIn("- Northbridge opened 3 plants (S1).", rows)  # A figure of one digit stands everywhere.
        self.assertNotIn("| North | 572.5 |", rows)  # The table's header says it's revenue.

    def test_an_abbreviation_binds_a_draft_to_the_notes_but_isnt_looked_for_in_a_source(self):
        self.assertEqual(research.describing_words("R&D, M&A and P&L costs, but not r&d or AT&Tx"),
                         {"costs": "costs", "r&d": "R&D", "m&a": "M&A", "p&l": "P&L"})
        self.assertEqual(research.label_words("R&D, M&A and P&L costs"), {"costs": "costs"})
        # A filing spells it out, "Research and development", so a row whose only describing word is R&D isn't judged
        # for words beside its figure, as before.
        page = (f"<html><body><p>Research and development was $64.2 million.</p><p>{'Nothing else of note happened here. ' * 12}"
                "</p></body></html>").encode()
        (self.ws.root / "research" / "02_checks.md").write_text(
            LABELLED.replace("- Revenue was $551.1M (S1).", "- R&D, net: $64.2M (S1)."), encoding="utf-8")
        warned = {r.row_text for r in self.results("numbers", {ANNUAL: page}) if r.status == "not_near_label"}
        self.assertNotIn("- R&D, net: $64.2M (S1).", warned)

    def test_a_source_is_read_once_and_holds_what_the_assay_says_it_holds(self):
        text = LABELLED_PAGE.decode() + RELEASE_PAGE.decode() + LAKESIDE_PAGE.decode() + " 9M 2025, (12,400) and 3x."
        found = assay_numbers.quantities(text, research.POLICY)
        self.assertEqual(research.evidence_of(found), assay_numbers.evidence(text, policy=research.POLICY))

    def test_the_warning_is_a_warning_and_a_waiver_accepts_it(self):
        found = [r for r in self.results("numbers", {ANNUAL: LABELLED_PAGE}) if r.status == "not_near_label"]
        self.assertEqual({r.verdict for r in found}, {research.WARN})
        self.assertIn("(Debt)", next(r.detail for r in found if r.row_text.startswith("- Debt")))
        (self.ws.root / "checks" / "waivers.csv").write_text(
            "check,note_file,line_no,item,reason,accepted_by,accepted_on\n"
            "numbers,02_checks.md,,$12.4M,The report gives debt in its notes,A. Researcher,2026-11-11\n", encoding="utf-8")
        found = [r for r in self.results("numbers", {ANNUAL: LABELLED_PAGE}) if r.status == "not_near_label"]
        self.assertEqual({r.verdict for r in found}, {research.WAIVED})


TRACED = f"""# Traced

## 1. Results (S1)

| Item | 2025 | 2024 |
|---|---|---|
| Revenue, $M | 551.1 | 572.5 |

## 2. Worked out

COMPUTED from the table above:

- Change: -3.7% (551.1 against 572.5).
- Invented: +12.0% (640.2 against 571.6).
- Monthly: 45.9 (= 551.1 / 12).
- Then: 4.59 (= 45.9 / 10).
- Due within a year: 70.8% (67.5 of 95.4) (S2).

## Sources

- **S1.** Northbridge Robotics. 2026. *Annual Report 2025.* {ANNUAL}
- **S2.** Northbridge Robotics. 2026. "Order book update." {ORDERS}
"""


class Inputs(Checked):
    """The figures a worked-out row's working starts from, traced to the notes or a source."""

    def setUp(self):
        super().setUp()
        (self.ws.root / "research" / "02_checks.md").write_text(TRACED, encoding="utf-8")

    def traced(self, pages=None):
        return {(r.row_text.split(":")[0], r.status, r.item) for r in self.results("numbers", pages) if r.status.startswith("input")}

    def test_an_input_from_a_checked_row_a_working_or_its_own_source_is_traced(self):
        traced = self.traced()
        self.assertIn(("- Change", "inputs_traced", "-3.7% (551.1 against 572.5)"), traced)
        self.assertIn(("- Monthly", "inputs_traced", "45.9 (= 551.1 / 12)"), traced)  # 12 is a constant.
        self.assertIn(("- Then", "inputs_traced", "4.59 (= 45.9 / 10)"), traced)  # 45.9 is a working's result.
        self.assertIn(("- Due within a year", "inputs_traced", "70.8% (67.5 of 95.4)"), traced)  # Held by S2 itself.

    def test_an_input_from_nowhere_is_a_warning_though_the_arithmetic_recomputes(self):
        traced = self.traced()
        self.assertIn(("- Invented", "input_not_traced", "640.2"), traced)
        self.assertIn(("- Invented", "input_not_traced", "571.6"), traced)
        arithmetic = {r.item: r.status for r in self.results("arithmetic")}
        self.assertEqual(arithmetic["+12.0% (640.2 against 571.6)"], "recomputes")

    def test_an_input_from_a_row_that_couldnt_be_judged_isnt_judged(self):
        traced = self.traced(pages={})
        self.assertIn(("- Change", "input_not_judged", "551.1"), traced)
        self.assertIn(("- Invented", "input_not_traced", "640.2"), traced)


RELEASE = "https://example.com/northbridge/q4-release.html"
LAKESIDE = "https://example.com/northbridge/lakeside.html"
RELEASE_PAGE = (b"Adjusted EBITDA of $6.2 million, compared to $3.7 million. Cash used in operations of $1.4 million. "
                b"In thousands: Capital spending 2,612. Diluted loss per share (0.52).")
LAKESIDE_PAGE = ("北桥机器人2025年营收突破37亿元，同比增长超40%；出货260万台。净利润912.56万元，去年营收预计达到 46-52 亿元。"
                 "公司估值破百亿，工业级3D打印设备市占率约18%。上半年营收7.25亿元，订单6831台。" + "北桥机器人发布财报。" * 12).encode()
READING = f"""# Reading

Fictional, for the tests.

## 1. A unit stated once

| US$M | Q4 2025 | Q4 2024 | Source |
|---|---|---|---|
| Adjusted EBITDA | 6.2 | 3.7 | S1 |
| Cash from operations | (1.4) | 7.7 | S1 |
| Capital spending | 2.6 | 9.9 | S1 |
| Diluted loss per share | (0.52) | (0.51) | S1 |

US$ millions except per share. From S1.

| | Q4 2025 |
|---|---|
| Adjusted EBITDA | 6.2 |

No unit is stated for this one (S1).

| Measure | Q4 2025 |
|---|---|
| Adjusted EBITDA | 6.2 |

## 2. A page in Chinese (S2)

- 2025 revenue over RMB 3.7bn, up 40%; about 2.6 million units shipped.
- Net profit of 9.13 million; a valuation above RMB 10bn; revenue the year before of RMB 4.6bn to RMB 5.2bn.
- The page's own words: "营收突破37亿元".
- First in industrial 3D printing with about 18%; first-half revenue 725 million.
- Revenue of 3.8bn yuan and 683 million, which the page doesn't hold.

## Sources

- **S1.** Northbridge Robotics. 2026. "Fourth quarter results." {RELEASE}
- **S2.** Lakeside Daily. 2026. "Northbridge results." {LAKESIDE}
"""


class Read(Checked):
    """What `check` reads before the assay judges a row: a unit a table states once, and a Chinese page's 万 and 亿."""

    def setUp(self):
        super().setUp()
        (self.ws.root / "research" / "03_reading.md").write_text(READING, encoding="utf-8")
        self.fetch({ANNUAL: ANNUAL_PAGE, ORDERS: ORDERS_PAGE, RELEASE: RELEASE_PAGE, LAKESIDE: LAKESIDE_PAGE})
        self.found = [(r.line_no, r.item, r.detail) for r in research.run(self.ws, self.con)
                      if r.check == "numbers" and r.note == "03_reading.md" and r.status == "not_in_source"]
        self.lines = (self.ws.root / "research" / "03_reading.md").read_text(encoding="utf-8").splitlines()

    def missing(self, text):
        """What wasn't found on the lines that hold `text`."""
        return [item for line_no, item, _ in self.found if text in self.lines[line_no - 1]]

    def test_a_table_states_its_unit_in_its_first_heading_or_its_lead_in(self):
        units = {line_no: unit for (note, line_no), unit in research.table_units(self.ws).items() if note == "03_reading.md"}
        rows = [(self.lines[line_no - 1], unit) for line_no, unit in sorted(units.items()) if "---" not in self.lines[line_no - 1]]
        self.assertEqual(rows, [("| Adjusted EBITDA | 6.2 | 3.7 | S1 |", "million"), ("| Cash from operations | (1.4) | 7.7 | S1 |", "million"),
                                ("| Capital spending | 2.6 | 9.9 | S1 |", "million"), ("| Diluted loss per share | (0.52) | (0.51) | S1 |", "million"),
                                ("| Adjusted EBITDA | 6.2 |", "million")])  # The third table states no unit, so its row isn't here.
        for text, unit in (("US$M", "million"), ("$ thousands", "thousand"), ("Figures in thousands of dollars", "thousand"),
                           ("RMB bn", "billion"), ("EUR MM", "million"), ("Revenue", ""), ("It raised $5M in May", ""), ("USD", "")):
            with self.subTest(text):
                self.assertEqual(research.unit_stated(text), unit)

    def test_a_heading_states_the_unit_of_the_tables_under_it_until_a_heading_of_its_level(self):
        text = ("# Note\n\n## Costs (US$ millions; S1)\n\n| Item | 2025 |\n|---|---|\n| Arms | 31.8 |\n\n### Detail\n\n"
                "| Item | 2025 |\n|---|---|\n| Grippers | 4.2 |\n\nTools, in US$ thousands:\n\n| Item | 2025 |\n|---|---|\n"
                "| Tools | 950 |\n\n## Staff\n\n| Item | 2025 |\n|---|---|\n| Heads | 120 |\n")
        lines = text.split("\n")
        rows = [(lines[line_no - 1], stated.table) for line_no, stated in sorted(research.stated_units(text).items())
                if "---" not in lines[line_no - 1]]
        # The table's own lead-in outranks the heading, and "## Staff" ends what "## Costs" states.
        self.assertEqual(rows, [("| Arms | 31.8 |", "million"), ("| Grippers | 4.2 |", "million"), ("| Tools | 950 |", "thousand")])

    def test_a_bare_cell_passes_as_written_or_in_the_unit_its_table_states(self):
        # 6.2 and 3.7 are the release's "$6.2 million" and "$3.7 million", and (1.4) its "$1.4 million". 7.7 is nowhere.
        self.assertEqual(self.missing("| Adjusted EBITDA | 6.2 | 3.7 |"), [])
        self.assertEqual(self.missing("Cash from operations"), ["7.7"])
        # 2.6 is 2,612 in a table of thousands: a figure this short still isn't matched across scales.
        self.assertEqual(self.missing("Capital spending"), ["2.6", "9.9"])
        # A per-share figure is found as written, and the unit never fails what's there.
        self.assertEqual(self.missing("Diluted loss per share"), ["(0.51)"])
        # The second table takes its unit from the line leading into it. The third states none, so its 6.2 is bare.
        self.assertEqual(self.missing("| Adjusted EBITDA | 6.2 |"), ["6.2"])
        detail = next(detail for _, item, detail in self.found if item == "7.7")
        self.assertIn("nor as 7.7 million, the unit its table states", detail)

    def test_a_figure_wrapped_onto_the_next_line_is_one_figure(self):
        sources = research.Sources(self.ws, self.con)
        sources._text["wrapped"] = "a loss of approximately $31 \r\nmillion to $38\r\n  million for the half"
        held = sources.evidence(["wrapped"])
        self.assertEqual(assay_numbers.number_findings("A loss of $31 million to $38 million.", held, research.POLICY), [])
        missed = assay_numbers.number_findings("A loss of $32 million.", held, research.POLICY)
        self.assertEqual([finding.text for finding in missed], ["$32 million"])

    def test_a_chinese_page_is_read_by_the_units_it_writes(self):
        self.assertEqual(self.missing("over RMB 3.7bn"), [])
        self.assertEqual(self.missing("Net profit of 9.13 million"), [])
        self.assertEqual(self.missing("The page's own words"), [])
        self.assertEqual(self.missing("First in industrial 3D printing"), [])
        # 38亿 and 6.83亿 aren't on the page. Its 6831 shares digits with 683 million, and that's all it shares.
        self.assertEqual(self.missing("which the page doesn't hold"), ["3.8bn", "683 million"])
        detail = next(detail for _, item, detail in self.found if item == "683 million")
        self.assertIn("in Chinese and holds these digits", detail)


EURO = "https://example.com/northbridge/euro.html"
CONVERTED = f"""# Converted (S1)

- The order book was €87.8M ($95.4M at 0.92 €/$) (S1).
- At a rate the release doesn't give: €85.9M ($95.4M at 0.90 €/$) (S1).
- With no rate: €87.8M ($95.4M) (S1).

## Sources

- **S1.** Northbridge Robotics. 2026. "Order book in euros." {EURO}
"""


class Converted(Checked):
    def test_a_figure_converted_at_a_written_rate_isnt_looked_for_but_the_amount_and_rate_are(self):
        (self.ws.root / "research" / "04_converted.md").write_text(CONVERTED, encoding="utf-8")
        self.fetch({EURO: b"The order book was $95.4 million, translated at 0.92 euro to the dollar."})
        results = [r for r in research.run(self.ws, self.con) if r.note == "04_converted.md"]
        missing = {r.line_no: [] for r in results}
        for r in results:
            if r.check == "numbers" and r.status == "not_in_source":
                missing[r.line_no].append(r.item)
        self.assertEqual(missing[3], [])
        self.assertEqual(missing[4], ["0.90"])
        self.assertEqual(len(missing[5]), 1)
        self.assertIn("87.8", missing[5][0])
        worked = {r.line_no: r.status for r in results if r.check == "arithmetic"}
        # Line 4 recomputes from its own rate; it's the rate the source doesn't hold.
        self.assertEqual(worked, {3: "recomputes", 4: "recomputes", 5: "not_parsed"})


class Command(Checked):
    def run_here(self, *argv):
        with mock.patch.dict("os.environ", {"DRILLCORE_HOME": str(self.ws.root)}):
            return run_cli(*argv)

    def test_check_fails_on_any_failure_and_writes_what_didnt_pass(self):
        self.fetch()
        out, _, code = self.run_here("check")
        self.assertEqual(code, 1)
        self.assertIn("arithmetic  1 does not recompute", out)
        self.assertIn("FAIL arithmetic 02_checks.md", out)
        with (self.ws.data / research.REPORT).open(encoding="utf-8", newline="") as report:
            rows = list(csv.DictReader(report))
        self.assertTrue(rows)
        self.assertNotIn("pass", {row["verdict"] for row in rows})
        self.assertIn(("arithmetic", "FAIL", "12 + 8 = 21"), {(row["check"], row["verdict"], row["item"]) for row in rows})

    def test_check_passes_a_clean_workspace(self):
        (self.ws.root / "research" / "02_checks.md").write_text(
            "# Clean\n\n## Results (S1)\n\n- Revenue was 551.1 in 2025, \"Revenue fell in 2025\" (S1).\n- COMPUTED: 150.4 + 43.2 = $193.6 million.\n\n"
            f"## Sources\n\n- **S1.** Annual report. {ANNUAL}\n", encoding="utf-8")
        (self.ws.root / "research" / "01_northbridge.md").unlink()
        self.fetch()
        out, _, code = self.run_here("check")
        self.assertEqual(code, 0, out)
        self.assertIn("0 failed", out)

    # A section of its own, so the row doesn't take the Results section's key.
    UNSOURCED = "\n## Elsewhere\n\n- Headcount 1,757 at year end.\n"

    def clean(self, extra=""):
        (self.ws.root / "research" / "02_checks.md").write_text(
            "# Clean\n\n## Results (S1)\n\n- Revenue was 551.1 in 2025, \"Revenue fell in 2025\" (S1).\n" + extra +
            f"\n## Sources\n\n- **S1.** Annual report. {ANNUAL}\n", encoding="utf-8")
        (self.ws.root / "research" / "01_northbridge.md").unlink()

    def test_check_says_how_much_was_held_to_a_source(self):
        self.clean(self.UNSOURCED)
        self.fetch()
        out, _, code = self.run_here("check")
        self.assertEqual(code, 0, out)
        self.assertIn("held to a source: 2 judged (1 quotation, 1 check of figures), not judged: 1 no source key", out)
        # And keeps what the 2 are, for a report's account of the run (`record`).
        kept = record.runs(self.con)[0].values()
        self.assertEqual((kept["part: judged: quotation"], kept["part: judged: row"]), (1, 1))
        self.assertEqual((kept["part: not judged: no_source_key: row"], kept["lines: not judged: no_source_key"]), (1, 1))

    def test_check_fails_when_nothing_was_judged_against_a_source(self):
        self.clean()
        self.fetch(pages={})
        out, err, code = self.run_here("check")
        self.assertEqual(code, 1, out)
        self.assertIn("0 failed", out)
        self.assertIn("Nothing in the notes was judged against a source", err)

    def test_strict_fails_on_a_warning_or_anything_not_judged_until_a_waiver_accepts_it(self):
        self.clean(self.UNSOURCED)
        self.fetch()
        self.assertEqual(self.run_here("check")[2], 0)
        out, err, code = self.run_here("check", "--strict")
        self.assertEqual(code, 1, out)
        self.assertIn("NOT JUDGED numbers 02_checks.md:9 [-] '- Headcount 1,757 at year end.': the row cites no source", out)
        self.assertIn("Strict: 0 warnings and 1 not judged", err)
        (self.ws.root / "research" / "02_checks.md").write_text(
            (self.ws.root / "research" / "02_checks.md").read_text(encoding="utf-8").replace(self.UNSOURCED, ""),
            encoding="utf-8")
        out, err, code = self.run_here("check", "--strict")
        self.assertEqual(code, 0, out + err)

    def test_strict_can_be_the_workspaces_setting(self):
        self.clean(self.UNSOURCED)
        self.fetch()
        config = self.ws.root / "workspace.toml"
        config.write_text(config.read_text(encoding="utf-8") + "\n[check]\nstrict = true\n", encoding="utf-8")
        self.assertEqual(self.run_here("check")[2], 1)


if __name__ == "__main__":
    unittest.main()
