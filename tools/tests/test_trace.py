"""Tests for `trace`, which follows a figure from a draft to the passage in a stored source, and the evidence pack built
on it. Each works on a copy of the fictional example, with its sources answered by a stand-in for the network."""
import contextlib
import csv
import io
import shutil
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

from support import CODE_ROOT

from drillcore import cli, evidence, sourcedb, trace, workspace

ANNUAL = "https://example.com/northbridge/annual-2025.html"
ORDERS = "https://example.com/northbridge/orders.html"
ANNUAL_PAGE = b"""<html><head><title>Annual Report 2025</title></head><body><p>In thousands of dollars.</p>
<table><tr><th>Revenue</th><td>551,102</td><td>572,514</td></tr><tr><th>Staff</th><td>1,757</td><td>1,820</td></tr></table>
<p>Research spending was $77.3 million. The year called for "discipline before growth".</p>
<p>&lt;script&gt;alert(1)&lt;/script&gt; 41.2%</p></body></html>"""


class Traced(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        self.ws = workspace.Workspace(root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)

    def fetch(self, orders=True):
        pages = {ANNUAL: (200, "text/html", ANNUAL_PAGE)}
        if orders:
            pages[ORDERS] = (200, "text/plain", b"Order book 95.4 million, 67.5 million due.")

        def get(url):
            status, kind, body = pages.get(url, (404, "text/html", b""))
            return status, kind, url, body, None if status == 200 else f"HTTP {status}"

        sourcedb.record_sources(self.ws, self.con)
        sourcedb.fetch(self.ws, self.con, get=get, say=lambda _: None)

    def run_here(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(workspace, "find", return_value=self.ws):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(list(argv))
        return out.getvalue(), err.getvalue(), code


class Trace(Traced):
    def test_a_figure_is_followed_to_the_passage_that_holds_it_at_its_scale(self):
        self.fetch()
        found = trace.Tracer(self.ws, self.con).trace(trace.asked_figure("$551.1M"))
        self.assertEqual([(m.draft, m.line_no) for m in found.mentions], [("01_northbridge.md", 6)])
        sourced = [chain for chain in found.chains if not chain.missing]
        self.assertEqual([(c.note, c.line_no, c.keys) for c in sourced], [("01_northbridge.md", 10, ("S1",))])
        address = sourced[0].addresses[0]
        self.assertEqual(address.url, ANNUAL)
        self.assertEqual(len(address.sha256), 64)
        self.assertTrue(address.fetched_at)
        self.assertEqual((address.passage.match, address.passage.kind), ("551,102", "x1000"))
        self.assertIn("Revenue", address.passage.before)
        self.assertTrue(found.complete)

    def test_a_figure_written_as_the_source_writes_it_is_preferred(self):
        self.fetch()
        found = trace.passage("1757 people, or 1,757.0 in all, then 1,757", trace.asked_figure("1,757"))
        self.assertEqual(found.kind, "exact")
        self.assertEqual(found.match, "1757")

    def test_each_missing_link_says_where_the_chain_stops(self):
        self.fetch(orders=False)
        tracer = trace.Tracer(self.ws, self.con)
        self.assertEqual(tracer.trace(trace.asked_figure("123.4")).chains, [])
        orders = tracer.trace(trace.asked_figure("95.4"))
        self.assertIn("HTTP 404", orders.chains[0].addresses[0].missing)
        self.assertFalse(orders.complete)
        absent = tracer.trace(trace.asked_figure("999.9"))
        self.assertIn("doesn't hold 999.9", absent.chains[0].addresses[0].missing)
        worked = [chain for chain in tracer.trace(trace.asked_figure("572.5")).chains if chain.missing]
        self.assertIn("worked out", worked[0].missing)

    def test_a_row_that_cites_nothing_says_so(self):
        note = self.ws.root / "research" / "01_northbridge.md"
        note.write_text(note.read_text(encoding="utf-8").replace("## 1. Results (S1)", "## 1. Results"), encoding="utf-8")
        self.fetch()
        chains = trace.Tracer(self.ws, self.con).trace(trace.asked_figure("1,757")).chains
        self.assertEqual(chains[0].missing, "the row cites no source")

    def test_the_command_traces_a_figure_and_exits_by_whether_a_chain_is_complete(self):
        self.fetch()
        out, _, code = self.run_here("trace", "$77.3M")
        self.assertIn("[[77.3]]", out)
        self.assertIn("draft 01_northbridge.md:10", out)
        self.assertEqual(code, 0)
        out, _, code = self.run_here("trace", "999.9")
        self.assertIn("missing:", out)
        self.assertEqual(code, 1)
        _, err, code = self.run_here("trace", "revenue")
        self.assertIn("no number", err)
        self.assertEqual(code, 1)

    def test_a_draft_line_traces_every_figure_on_it(self):
        self.fetch()
        out, _, code = self.run_here("trace", "01_northbridge.md:6")
        self.assertIn("\n572.5\n", out)
        self.assertIn("\n551.1\n", out)
        self.assertEqual(code, 0)
        out, _, _ = self.run_here("trace", "01_northbridge.md:7")
        self.assertIn("\n41.2\n", out)
        _, err, code = self.run_here("trace", "01_northbridge.md:400")
        self.assertIn("no line 400", err)
        self.assertEqual(code, 1)
        _, err, code = self.run_here("trace", "nothing.md:1")
        self.assertIn("No such draft", err)


class Evidence(Traced):
    def read_page(self):
        return (self.ws.data / "evidence" / "01_northbridge.html").read_text(encoding="utf-8")

    def test_every_figure_and_quotation_links_to_its_passage(self):
        self.fetch()
        with mock.patch.object(sourcedb, "http_get", side_effect=AssertionError("the pack fetched")):
            _, _, code = self.run_here("evidence")
        self.assertEqual(code, 0)
        page = self.read_page()
        self.assertIn('<a href="#f6-1">551.1</a>', page)
        self.assertIn('id="f6-1"', page)
        self.assertIn("<mark>551,102</mark>", page)
        self.assertIn('<a href="#q13-0">', page)
        self.assertIn("<mark>discipline before growth</mark>", page)
        self.assertIn("no stored copy the notes cite holds this quotation", page)  # The draft's blockquote.
        self.assertIn("nothing was fetched", page)
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_the_checks_last_findings_stand_beside_their_lines_with_any_waiver(self):
        self.fetch()
        self.ws.data.mkdir(exist_ok=True)
        with (self.ws.data / evidence.CHECKS).open("w", newline="", encoding="utf-8") as out:
            writer = csv.writer(out)
            writer.writerow(["check", "verdict", "status", "note_file", "line_no", "source_keys", "item", "detail", "row_text", "waiver"])
            writer.writerow(["numbers", "waived", "not_in_source", "01_northbridge.md", "10", "S1", "551.1", "absent", "", "confirmed by phone"])
        with (self.ws.data / evidence.ASSAY).open("w", newline="", encoding="utf-8") as out:
            writer = csv.writer(out)
            writer.writerow(["draft", "line_no", "check", "verdict", "item", "detail"])
            writer.writerow(["01_northbridge.md", "8", "numbers", "fail", "sixty", "not in the notes"])
            writer.writerow(["01_northbridge.md", "0", "verdict", "fail", "abc", "1 failure"])
        evidence.build(self.ws, self.con)
        page = self.read_page()
        self.assertIn("Waived: confirmed by phone", page)
        self.assertIn("<code>sixty</code>: not in the notes", page)
        self.assertIn("1 failure", page)

    def test_a_pack_without_the_checks_says_they_havent_been_run(self):
        evidence.build(self.ws, self.con)
        page = self.read_page()
        self.assertIn("hasn't been run", page)
        self.assertIn("not fetched yet", page)

    def test_a_draft_that_isnt_there_is_refused(self):
        _, err, code = self.run_here("evidence", "no-such-draft.md")
        self.assertIn("No such draft", err)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
