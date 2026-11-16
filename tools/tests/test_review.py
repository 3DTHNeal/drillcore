"""Tests for `review`, which sets each claim the notes make beside the source it cites, and the page that serves it.

Each works on a copy of the fictional example with notes of its own, its source answered by a stand-in for the network.
"""
import contextlib
import csv
import http.client
import http.server
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from support import CODE_ROOT

from drillcore import research, review, review_server, sourcedb, workspace

ANNUAL = "https://example.com/northbridge/annual-2025.html"
# The token the page would be given, fixed for the tests.
TOKEN = "secret-for-tests"
NOTES = """# Notes: Northbridge Robotics

## 1. Results (S1)

| Item | 2025 | 2024 |
|---|---|---|
| Revenue, $M | 551.1 | 572.5 |
| Staff at year end | 1,757 | 1,820 |

- Research spending fell to $77.3M (S1).
- A figure no source holds: $999.9M (S1).
- The year called for "discipline ahead of growth" (S1).
- Net income was $12.4M (S1 p.1).
- It was a year of "Discipline before Growth" (S1).
- The brief asks for "a full account of the year" (S1).

## 2. Worked out

COMPUTED from the table above:

- Revenue change: -3.9% (551.1 against 572.5).

## Sources

- **S1.** Northbridge Robotics. 2026. *Annual Report 2025.* https://example.com/northbridge/annual-2025.html
"""
PAGE = b"""<html><head><title>Annual Report 2025</title></head><body><p>In thousands of dollars.</p>
<table><tr><th>Revenue</th><td>551,102</td><td>572,514</td></tr><tr><th>Staff</th><td>1,757</td><td>1,820</td></tr></table>
<p>Research spending was $77.3 million. The year called for discipline before growth, and it came.</p>
<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>
<p>The company recorded a net loss of $12.4 million.</p></body></html>"""


class Reviewed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        self.note = root / "research" / "01_northbridge.md"
        self.note.write_bytes(NOTES.replace("\n", "\r\n").encode("utf-8"))
        with (root / "workspace.toml").open("a", encoding="utf-8") as settings:
            settings.write('\n[check.quotations]\nnot_sources = ["brief"]\n')
        self.ws = workspace.Workspace(root, "test")
        with self.connected() as con:
            sourcedb.record_sources(self.ws, con)
            sourcedb.fetch(self.ws, con, get=lambda url: (200, "text/html", url, PAGE, None), say=lambda _: None)
            # The stored text as two pages, the second starting at the net loss, as a PDF's would be kept.
            text = con.execute("SELECT text FROM documents WHERE url=?", (ANNUAL,)).fetchone()[0]
            second = text.index("The company recorded")
            con.executemany("INSERT INTO document_pages(url, page, start, end_at, folio) VALUES (?,?,?,?,?)",
                            [(ANNUAL, 1, 0, second, ""), (ANNUAL, 2, second, len(text), "")])
            con.commit()

    def connected(self):
        return contextlib.closing(sourcedb.connect(self.ws))

    def gathered(self) -> review.Review:
        with self.connected() as con:
            return review.gather(self.ws, con)

    def text(self) -> str:
        with self.connected() as con:
            return con.execute("SELECT text FROM documents WHERE url=?", (ANNUAL,)).fetchone()[0]

    def claim(self, found: review.Review, check: str, item: str) -> review.Claim:
        return next(c for c in found.claims if c.check == check and c.item == item)

    def line(self, number: int) -> str:
        return self.note.read_bytes().decode("utf-8").splitlines()[number - 1]


class Claims(Reviewed):
    def test_each_figure_of_a_row_is_a_claim_where_it_stands_with_its_passage(self):
        found = self.gathered()
        revenue = self.claim(found, "numbers", "551.1")
        self.assertEqual((revenue.verdict, revenue.status), (research.PASS, "supported"))
        line = found.notes["01_northbridge.md"][revenue.line_no - 1]
        self.assertEqual(line[revenue.start:revenue.end], "551.1")
        view = revenue.views[0]
        text = self.text()
        self.assertEqual(found.sources[view.source].url, ANNUAL)
        self.assertEqual([(text[s:e], how) for s, e, how in view.hits], [("551,102", "x1000")])
        self.assertIn("thousand", view.said)
        # The row's own word stands beside the figure in the source, and is marked there.
        self.assertIn("Revenue", [text[s:e] for s, e in view.labels])

    def test_a_figure_no_source_holds_fails_with_no_passage(self):
        found = self.gathered()
        missing = self.claim(found, "numbers", "$999.9M")
        self.assertEqual(missing.verdict, research.FAIL)
        self.assertEqual(missing.views[0].hits, ())
        self.assertIn("doesn't hold", missing.views[0].said)

    def test_a_passing_citation_is_a_link_not_a_claim(self):
        found = self.gathered()
        self.assertFalse([c for c in found.claims if c.check == "citations"])
        line = found.notes["01_northbridge.md"]
        keys = [link for link in found.links if line[link["line"] - 1][link["start"]:link["end"]] == "S1"]
        self.assertTrue(keys)
        self.assertEqual({found.sources[link["sources"][0]].url for link in keys}, {ANNUAL})

    def test_the_review_writes_no_report(self):
        self.gathered()
        self.assertFalse((self.ws.data / research.REPORT).exists())

    def test_the_review_is_json_and_carries_source_text_only_on_request(self):
        found = self.gathered().to_json()
        self.assertEqual(set(found), {"notes", "sources", "links", "claims"})
        self.assertNotIn("alert(1)", json.dumps(found))
        with self.connected() as con:
            self.assertIn("<script>alert(1)</script>", review.source_text(con, ANNUAL)["text"])


class Suggestions(Reviewed):
    def test_a_quotation_a_word_off_is_offered_the_words_the_source_has(self):
        quote = self.claim(self.gathered(), "quotations", "discipline ahead of growth")
        self.assertEqual(quote.verdict, research.FAIL)
        self.assertEqual(self.text()[quote.views[0].hits[0][0]:quote.views[0].hits[0][1]], "discipline before growth")
        self.assertEqual(quote.suggestion.new, '- The year called for "discipline before growth" (S1).')
        self.assertEqual(quote.suggestion.diff, (("equal", "discipline"), ("delete", "ahead of"), ("insert", "before"), ("equal", "growth")))

    def test_a_quotation_in_other_capitals_is_offered_the_sources_own(self):
        quote = self.claim(self.gathered(), "quotations", "Discipline before Growth")
        self.assertEqual(quote.verdict, research.FAIL)
        self.assertIn("capitals", quote.views[0].said)
        # The first letter may be fitted to the sentence, so the note's is kept.
        self.assertEqual(quote.suggestion.new, '- It was a year of "Discipline before growth" (S1).')

    def test_a_quotation_of_a_document_that_isnt_a_source_isnt_looked_for(self):
        quote = self.claim(self.gathered(), "quotations", "a full account of the year")
        self.assertEqual((quote.verdict, quote.status), (research.NOT_JUDGED, "quotes_a_non_source"))
        self.assertEqual([view.hits for view in quote.views], [()])
        self.assertIn("isn't a source", quote.views[0].said)
        self.assertIsNone(quote.suggestion)

    def test_no_passage_is_offered_when_none_is_close(self):
        with self.connected() as con:
            texts = review.Texts(con)
            self.assertIsNone(review.closest_passage(texts, ANNUAL, "an entirely different thing altogether"))
            self.assertIsNotNone(review.closest_passage(texts, ANNUAL, "the year called for discipline after growth"))
        self.assertIsNone(review.quote_suggestion('He said "a thing" (S1).', 3, "a thing", " ", "S1"))
        self.assertIsNone(review.quote_suggestion('He said "a ... thing" (S1).', 3, "a ... thing", "a big thing", "S1"))

    def test_a_quotation_is_found_however_the_source_breaks_or_capitalizes_it(self):
        self.assertEqual(review.quote_spans("A year of Discipline\nbefore growth.", "discipline before growth"), [(10, 34)])
        self.assertEqual(review.quote_spans("first, then later, last", "first ... last"), [(0, 5), (19, 23)])
        self.assertEqual(review.quote_spans("first only", "first ... last"), [])

    def test_a_working_that_does_not_recompute_is_offered_what_it_gives(self):
        found = self.gathered()
        working = self.claim(found, "arithmetic", "-3.9% (551.1 against 572.5)")
        self.assertEqual(working.suggestion.new, "- Revenue change: -3.7% (551.1 against 572.5).")
        self.assertEqual(working.working["gives"], "-3.738%")
        held = [found.claims[index].item for given in working.working["inputs"] for index in given["claims"]]
        self.assertEqual(held, ["551.1", "572.5"])

    def test_a_figure_on_another_page_is_offered_that_page(self):
        loss = self.claim(self.gathered(), "numbers", "$12.4M")
        self.assertEqual(loss.status, "not_on_cited_page")
        self.assertEqual(loss.suggestion.new, "- Net income was $12.4M (S1 p.2).")
        self.assertIn("away from page 1", loss.views[0].hits[0][2])
        self.assertTrue(loss.views[0].region)

    def test_a_figure_in_another_section_is_offered_that_section(self):
        text = "Note 12 Segment information\nSegment revenue 300.5\n\nNote 13 Other income\nOther income 12.9\n"
        line = "- Other income was 12.9 (S1 §Note 12)."
        found = review.section_suggestion(line, 4, review.pages.Pin("S1", section="Note 12"), text, text.index("12.9"))
        self.assertEqual(found.new, "- Other income was 12.9 (S1 §Note 13).")
        self.assertEqual(found.diff, (("equal", "S1 §Note"), ("delete", "12"), ("insert", "13")))
        # Before any heading numbered that way, nothing is offered.
        self.assertIsNone(review.section_suggestion(line, 4, review.pages.Pin("S1", section="Note 12"), "Other income 12.9\n", 13))

    def test_a_figure_a_line_writes_in_chinese_units_is_placed_as_written(self):
        line = "- 收入 551.1 百万美元 (S1)."
        start, end = review.cjk_place(line, "551100000")
        self.assertEqual(line[start:end], "551.1 百万")
        self.assertIsNone(review.cjk_place(line, "551100001"))

    def test_a_figure_is_written_again_as_the_working_gives_it(self):
        self.assertEqual(review.figure_written("-3.9%", -3.738), "-3.7%")
        self.assertEqual(review.figure_written("+12.0%", -1.04), "-1.0%")
        self.assertEqual(review.figure_written("$1,204.5M", 1210.04), "$1,210.0M")
        self.assertEqual(review.figure_written("3.9%", -3.738), "3.7%")


class Marks(Reviewed):
    def test_a_mark_is_kept_and_found_again(self):
        found = self.gathered()
        staff = self.claim(found, "numbers", "1,757")
        review.set_mark(self.ws, staff, "agrees", "", "A. Reviewer", today="2026-11-15")
        again = self.claim(self.gathered(), "numbers", "1,757")
        self.assertEqual((again.mark.mark, again.mark.by, again.mark.on, again.stale), ("agrees", "A. Reviewer", "2026-11-15", ""))
        with (self.ws.root / review.FILE).open(encoding="utf-8", newline="") as kept:
            self.assertEqual(next(csv.reader(kept)), list(review.COLUMNS))

    def test_a_mark_needs_another_look_when_its_line_or_source_changes(self):
        loss = self.claim(self.gathered(), "numbers", "$12.4M")
        review.set_mark(self.ws, loss, "disagrees", "The source gives a net loss, not income.", "AR")
        review.edit_line(self.ws, "01_northbridge.md", loss.line_no, self.line(loss.line_no), "- Net income was $12.4M (S1 p.2).")
        moved = self.claim(self.gathered(), "numbers", "$12.4M")
        self.assertIn("the line has changed", moved.stale)
        staff = self.claim(self.gathered(), "numbers", "1,757")
        review.set_mark(self.ws, staff, "agrees", "", "AR")
        with self.connected() as con:
            con.execute("UPDATE documents SET text = text || ' Restated.' WHERE url=?", (ANNUAL,))
            con.commit()
        self.assertIn("the text of a source", self.claim(self.gathered(), "numbers", "1,757").stale)

    def test_a_mark_keeps_every_other_row_of_the_file_as_written(self):
        path = self.ws.root / review.FILE
        path.parent.mkdir(exist_ok=True)
        path.write_text("note_file,line_no,check,item,mark,comment,marked_by,marked_on,line_sha,source_sha,ticket\n"
                        "01_northbridge.md,7,numbers,551.1,agree,typed by hand,AR,2026-11-14,,,T-12\n"
                        "# a comment row,,,,,,,,,,\n", encoding="utf-8")
        review.set_mark(self.ws, self.claim(self.gathered(), "numbers", "1,757"), "agrees", "", "AR", today="2026-11-15")
        with path.open(encoding="utf-8", newline="") as kept:
            rows = list(csv.DictReader(kept))
        self.assertEqual([row["item"] for row in rows], ["551.1", "", "1,757"])
        self.assertEqual((rows[0]["mark"], rows[0]["ticket"], rows[1]["note_file"]), ("agree", "T-12", "# a comment row"))

    def test_a_marks_file_without_its_columns_is_left_alone(self):
        path = self.ws.root / review.FILE
        path.parent.mkdir(exist_ok=True)
        path.write_text("not,a,marks,file\n1,2,3,4\n", encoding="utf-8")
        with self.assertRaisesRegex(review.ReviewError, "columns"):
            review.set_mark(self.ws, self.claim(self.gathered(), "numbers", "1,757"), "agrees", "", "AR")
        self.assertEqual(path.read_text(encoding="utf-8"), "not,a,marks,file\n1,2,3,4\n")
        self.assertEqual(review.read_marks(self.ws), [])

    def test_two_claims_on_one_item_are_told_apart_by_status(self):
        unused = review.Claim("01_northbridge.md", 9, 3, 5, "citations", "unused", research.WARN, "S5", "", ("S5",))
        unfetched = review.Claim("01_northbridge.md", 9, 3, 5, "citations", "not_fetched", research.NOT_JUDGED, "S5", "", ("S5",))
        found = review.Review({}, [], [], [unfetched, unused])
        self.assertIs(found.find("01_northbridge.md", 9, "citations", "S5", "unused"), unused)
        self.assertIs(found.find("01_northbridge.md", 9, "citations", "S5"), unfetched)

    def test_a_disagreement_says_what_the_source_says_and_who_says_so(self):
        claim = self.claim(self.gathered(), "numbers", "$77.3M")
        with self.assertRaises(review.ReviewError):
            review.set_mark(self.ws, claim, "disagrees", " ", "AR")
        with self.assertRaises(review.ReviewError):
            review.set_mark(self.ws, claim, "agrees", "", "")
        review.set_mark(self.ws, claim, "agrees", "", "AR")
        review.set_mark(self.ws, claim, "", "", "")
        self.assertEqual(review.read_marks(self.ws), [])


class Writing(Reviewed):
    def test_an_edit_writes_one_line_and_keeps_the_line_endings(self):
        before = self.note.read_bytes()
        review.edit_line(self.ws, "01_northbridge.md", 11, "- A figure no source holds: $999.9M (S1).", "- A figure: $99.9M (S1).")
        after = self.note.read_bytes()
        self.assertEqual(after, before.replace(b"A figure no source holds: $999.9M", b"A figure: $99.9M"))
        self.assertEqual(after.count(b"\r\n"), before.count(b"\r\n"))

    def test_an_edit_is_refused_when_the_line_has_changed_or_would_be_two(self):
        old = self.line(13)
        with self.assertRaisesRegex(review.ReviewError, "changed since"):
            review.edit_line(self.ws, "01_northbridge.md", 13, old + " ", "anything")
        for broken in ("one\ntwo", "one\rtwo", "one two"):
            with self.assertRaisesRegex(review.ReviewError, "line break"):
                review.edit_line(self.ws, "01_northbridge.md", 13, old, broken)
        with self.assertRaisesRegex(review.ReviewError, "isn't a note"):
            review.edit_line(self.ws, "../workspace.toml", 1, "", "x")
        self.assertEqual(self.line(13), old)

    def test_accepting_a_finding_writes_a_waiver_check_honours(self):
        missing = self.claim(self.gathered(), "numbers", "$999.9M")
        review.accept(self.ws, missing, "Confirmed by phone, with a comma", "A. Reviewer", today="2026-11-15")
        with (self.ws.root / "checks" / "waivers.csv").open(encoding="utf-8", newline="") as kept:
            rows = [row for row in csv.DictReader(kept) if not row["check"].startswith("#")]
        self.assertEqual(rows, [{"check": "numbers", "note_file": "01_northbridge.md", "line_no": str(missing.line_no), "item": "$999.9M",
                                 "reason": "Confirmed by phone, with a comma", "accepted_by": "A. Reviewer", "accepted_on": "2026-11-15"}])
        self.assertEqual(self.claim(self.gathered(), "numbers", "$999.9M").verdict, research.WAIVED)

    def test_only_a_failure_or_a_warning_is_accepted(self):
        with self.assertRaises(review.ReviewError):
            review.accept(self.ws, self.claim(self.gathered(), "numbers", "551.1"), "fine", "AR")

    def test_the_example_workspace_is_never_changed(self):
        example = workspace.Workspace(workspace.EXAMPLE_ROOT)
        claim = self.claim(self.gathered(), "numbers", "$999.9M")
        for change in (lambda: review.edit_line(example, "01_northbridge.md", 1, "x", "y"),
                       lambda: review.accept(example, claim, "why", "who")):
            with self.assertRaisesRegex(review.ReviewError, "example"):
                change()


class Served(Reviewed):
    def setUp(self):
        super().setUp()
        self.app = review_server.App(self.ws, 8801, token=TOKEN)

    def ask(self, method, path, body=None, token=None, host="127.0.0.1:8801", kind="application/json"):
        headers = {"Host": host, "Content-Type": kind}
        token = TOKEN if token is None else token
        if token:
            headers["X-Review-Token"] = token
        status, sent, raw = self.app.respond(method, path, headers, json.dumps(body).encode() if body is not None else b"")
        return status, sent, raw

    def test_the_page_carries_its_token_and_a_strict_policy(self):
        status, sent, raw = self.ask("GET", "/", token="")
        self.assertEqual(status, 200)
        self.assertIn(f'content="{TOKEN}"'.encode(), raw)
        self.assertIn("script-src 'self'", sent["Content-Security-Policy"])
        self.assertEqual(sent["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.ask("GET", "/review.js", token="")[0], 200)

    def test_data_needs_the_token_and_this_computer_as_host(self):
        self.assertEqual(self.ask("GET", "/api/state", token="")[0], 403)
        self.assertEqual(self.ask("GET", "/api/state", token="wrong")[0], 403)
        self.assertEqual(self.ask("GET", "/api/state", host="attacker.example:8801")[0], 421)
        self.assertEqual(self.ask("GET", "/../workspace.toml")[0], 404)
        self.assertEqual(self.ask("POST", "/api/recheck", {}, kind="text/plain")[0], 415)
        status, _, raw = self.ask("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(raw)["claims"])

    def test_a_source_is_sent_by_its_id(self):
        state = json.loads(self.ask("GET", "/api/state")[2])
        status, _, raw = self.ask("GET", f"/api/source?id={state['sources'][0]['id']}")
        self.assertEqual((status, json.loads(raw)["url"]), (200, ANNUAL))
        self.assertEqual(self.ask("GET", "/api/source?id=99")[0], 404)
        self.assertEqual(self.ask("GET", "/api/source?id=x")[0], 404)

    def test_a_suggestion_is_applied_and_undone(self):
        state = json.loads(self.ask("GET", "/api/state")[2])
        quote = next(c for c in state["claims"] if c["check"] == "quotations")
        s = quote["suggestion"]
        status, _, raw = self.ask("POST", "/api/edit", {"note": quote["note"], "line": s["line"], "old": s["old"], "new": s["new"]})
        self.assertEqual(status, 200)
        after = json.loads(raw)
        self.assertTrue(after["canUndo"])
        self.assertEqual(next(c for c in after["claims"] if c["check"] == "quotations")["verdict"], research.PASS)
        self.assertEqual(self.line(s["line"]), s["new"])
        self.assertEqual(self.ask("POST", "/api/undo", {})[0], 200)
        self.assertEqual(self.line(s["line"]), s["old"])
        self.assertEqual(self.ask("POST", "/api/undo", {})[0], 409)

    def test_an_undo_finds_its_line_after_lines_move_and_leaves_one_changed_again(self):
        state = json.loads(self.ask("GET", "/api/state")[2])
        s = next(c for c in state["claims"] if c["check"] == "quotations")["suggestion"]
        self.assertEqual(self.ask("POST", "/api/edit", {"note": "01_northbridge.md", "line": s["line"], "old": s["old"], "new": s["new"]})[0], 200)
        # A line added above it from outside the page: the line to put back is one further down.
        self.note.write_bytes(b"Added above.\r\n" + self.note.read_bytes())
        status, _, raw = self.ask("POST", "/api/undo", {})
        self.assertEqual(status, 200)
        self.assertEqual(self.line(s["line"] + 1), s["old"])
        self.assertFalse(json.loads(raw)["canUndo"])
        # Changed again since the page changed it: left as it is, and no longer offered to undo.
        self.ask("POST", "/api/edit", {"note": "01_northbridge.md", "line": s["line"] + 1, "old": s["old"], "new": s["new"]})
        self.note.write_bytes(self.note.read_bytes().replace(s["new"].encode(), b"- Rewritten by hand."))
        status, _, raw = self.ask("POST", "/api/undo", {})
        self.assertEqual(status, 409)
        self.assertIn("changed again", json.loads(raw)["error"])
        self.assertFalse(json.loads(self.ask("GET", "/api/state")[2])["canUndo"])

    def test_a_mark_is_made_and_a_stale_page_is_told(self):
        state = json.loads(self.ask("GET", "/api/state")[2])
        staff = next(c for c in state["claims"] if c["item"] == "1,757")
        ref = {key: staff[key] for key in ("note", "line", "check", "item")}
        status, _, raw = self.ask("POST", "/api/mark", {"claim": ref, "mark": "agrees", "by": "AR"})
        self.assertEqual(status, 200)
        self.assertEqual(next(c for c in json.loads(raw)["claims"] if c["item"] == "1,757")["mark"]["mark"], "agrees")
        status, _, raw = self.ask("POST", "/api/mark", {"claim": {**ref, "item": "9,999"}, "mark": "agrees", "by": "AR"})
        self.assertEqual(status, 409)
        self.assertIn("Recheck", json.loads(raw)["error"])
        self.assertEqual(self.ask("POST", "/api/mark", {"claim": {**ref, "line": "x"}, "mark": "agrees", "by": "AR"})[0], 400)

    def test_a_port_another_server_holds_is_left_to_it(self):
        # On Windows, two servers that each ask to reuse an address, as the standard library's does, could share a port,
        # and a request would reach either one. Here the port is held by such a server, as an earlier review would hold it.
        taken = http.server.HTTPServer(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
        self.addCleanup(taken.server_close)
        port = taken.server_address[1]
        server = review_server.serve(self.app, port)
        server.server_close()
        self.assertNotEqual(self.app.port, port)

    def test_the_server_answers_on_this_computer(self):
        server = review_server.serve(self.app, 0)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        self.assertEqual(server.server_address[0], "127.0.0.1")
        connection = http.client.HTTPConnection("127.0.0.1", self.app.port, timeout=10)
        self.addCleanup(connection.close)
        connection.request("GET", "/api/state", headers={"X-Review-Token": TOKEN})
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertTrue(json.loads(response.read())["claims"])


if __name__ == "__main__":
    unittest.main()
