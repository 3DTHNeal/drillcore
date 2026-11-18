"""Tests for sources that are JSON, and for what `import-text` records about a fetch. Each test works on a copy of the
fictional example with a note of its own added, and sources answered by a stand-in for the network."""
import contextlib
import json
import shutil
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

from support import CODE_ROOT, run_cli

from assay import numbers as assay_numbers
from assay import text as assay_text
from drillcore import citations, identity, inventory, references, research, sourcedb, workspace

ANNUAL = "https://example.com/northbridge/annual-2025.html"
ORDERS = "https://example.com/northbridge/orders.html"
PRICES = "https://example.com/northbridge/prices.json"
# One address of a made-up data service, given as the source of figures the service serves from many files.
ASSETS = "https://data.example.com/api/concept/NBR/Assets.json"
ANNUAL_PAGE = (b"<html><body><p>In thousands of dollars.</p><table><tr><th>Revenue</th><td>551,102</td></tr></table>"
               b"</body></html>")
PRICES_FILE = (b'{"meta": {"symbol": "NBR", "currency": "USD", "regularMarketPrice": 13.25},\n'
               b' "prices": [{"date": "2026-01-02", "close": 12.5}, {"date": "2026-01-05", "close": 12.300000190734863}],\n'
               b' "volume": [1250000, null, 3.1e5]}')
ASSETS_FILE = b'{"tag": "Assets", "units": {"USD": [{"end": "2025-12-31", "val": 1204600000, "form": "10-K"}]}}'
JSON_KIND = "application/json; charset=utf-8"

NOTE = f"""# Share price

Fictional, for the tests.

## 1. Closing prices (P1)

| Day | Close |
|---|---|
| 2 January 2026 | $12.50 |
| 5 January 2026 | $12.30 |
| A close the file doesn't hold | $99.75 |

## 2. From the data service (D1)

- Total assets were $1,204.6M (D1).
- Revenue was $551.1M (D1).

## 3. A filing and the price file together

- Revenue was $551.1M and the latest price was $13.25 (S1, P1).

## Sources

- **P1.** Example Exchange. n.d. Daily closes for Northbridge Robotics (NBR). {PRICES}
- **D1.** Example Data Service. n.d. "Company concept data: Northbridge Robotics." {ASSETS} (replace the last path element with the concept name for the others).
- **S1.** Northbridge Robotics. 2026. *Annual Report 2025.* {ANNUAL}
"""
PAGES = {ANNUAL: (200, "text/html", ANNUAL_PAGE), PRICES: (200, JSON_KIND, PRICES_FILE), ASSETS: (200, "application/json", ASSETS_FILE)}


class Kept(unittest.TestCase):
    """A copy of the example with the note above in place of its own, its database open, and the network stood in for."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        (root / "research" / "01_northbridge.md").unlink()
        self.note = root / "research" / "03_prices.md"
        self.note.write_text(NOTE, encoding="utf-8")
        self.ws = workspace.Workspace(root, "test")
        self.settings = self.ws.config_path.read_text(encoding="utf-8")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)
        self.asked: list[str] = []

    def read_json(self, *addresses):
        """Have the workspace list these addresses, and no others, as JSON to read."""
        listed = ", ".join(json.dumps(address) for address in addresses)
        self.ws.config_path.write_text(f"{self.settings}\n[sources]\nread_json = [{listed}]\n", encoding="utf-8")

    def get(self, pages):
        def get(url):
            self.asked.append(url)
            status, kind, body = pages.get(url, (404, "text/html", b""))
            return status, kind, url, body, None if status == 200 else f"HTTP {status}"
        return get

    def fetch(self, **answers):
        sourcedb.record_sources(self.ws, self.con)
        return sourcedb.fetch(self.ws, self.con, get=self.get({**PAGES, **answers}), say=lambda _: None)

    def document(self, url):
        return self.con.execute("SELECT text, extractor FROM documents WHERE url=?", (url,)).fetchone()

    def numbers(self):
        """Each row of the note the numbers check judged, by its text, as (status, what wasn't found, why)."""
        return {r.row_text: (r.status, r.item, r.detail) for r in research.run(self.ws, self.con)
                if r.check == "numbers" and r.note == "03_prices.md"}

    def run_here(self, *argv, pages=None):
        self.con.commit()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(workspace.os.environ, {identity.HOME_VARIABLE: str(self.ws.root)}))
            stack.enter_context(mock.patch.object(sourcedb, "http_get", self.get(pages or {})))
            return run_cli(*argv)


class Written(unittest.TestCase):
    def test_every_value_is_written_as_the_file_writes_it(self):
        text = sourcedb.json_text(
            chr(0xFEFF) + '{"name": "Northbridge", "close": 12.300000190734863, "shares": 12345678901234567890123, "rate": 1.10,'
            ' "change": -0.5, "tiny": 3.1e-5, "listed": true, "note": null,'
            ' "days": [{"date": "2026-01-02", "close": 12.5, "split": {"ratio": "2:1"}}, {"date": "2026-01-05", "close": 12.75}],'
            ' "volume": [1250000, null, "n/a"], "empty": [], "nothing": {}}')
        self.assertEqual(text.splitlines(), [
            "name: Northbridge | close: 12.300000190734863 | shares: 12345678901234567890123 | rate: 1.10 | change: -0.5 | "
            "tiny: 3.1e-5 | listed: true | note: null;",
            "days | date: 2026-01-02 | close: 12.5;",
            "days.split | ratio: 2:1;",
            "days | date: 2026-01-05 | close: 12.75;",
            "volume: 1250000;",
            "volume: null;",
            "volume: n/a;",
            "empty: [];",
            "nothing: {};"])

    def test_a_file_that_is_one_value_or_a_bare_list_is_read_too(self):
        self.assertEqual(sourcedb.json_text("41.2"), "41.2;")
        self.assertEqual(sourcedb.json_text('[1.5, [2.5, {"x": 3.5}]]'), "1.5;\n2.5;\nx: 3.5;")
        self.assertEqual(sourcedb.json_text('{"x": 1, "x": 2}'), "x: 1 | x: 2;")  # Both are in the file.

    def test_a_place_in_a_list_is_never_a_figure(self):
        # 300 closes, none of them 299: the text mustn't hold a count or an index the file doesn't write.
        closes = [f"{1000 + day}.25" for day in range(300)]
        text = sourcedb.json_text('{"chart": {"close": [' + ", ".join(closes) + "]}}")
        self.assertEqual(sourcedb.doc_numbers(text), sorted(float(close) for close in closes))
        self.assertEqual(text.splitlines()[299], "chart.close: 1299.25;")

    def test_a_number_isnt_read_with_the_name_that_starts_the_next_line(self):
        # Read as a wrapped sentence, "5" over "million" would be five million, which the file doesn't say.
        for body in ('{"count": [5], "million": {"shares": 3}}', '{"count": [5], "thousand": [3]}', '{"count": [5], "percent": [3]}'):
            with self.subTest(body=body):
                held = assay_numbers.evidence(assay_text.matchable(sourcedb.json_text(body)), policy=research.POLICY)
                self.assertEqual({str(number) for number in held.numbers}, {"5", "3"})
                self.assertEqual(held.percents, frozenset())

    def test_what_isnt_json_has_no_text(self):
        for body in ("", "<html><body>Access denied</body></html>", '{"close": 12.5', "[" * 200_000):
            with self.subTest(body=body[:20]):
                self.assertIsNone(sourcedb.json_text(body))

    def test_what_a_reader_cant_see_is_taken_out_as_for_any_source(self):
        self.assertEqual(sourcedb.json_text('{"note": "Sales\\u001b[2J rose\\u202e 4.1%"}'), "note: Sales[2J rose 4.1%;")


class Fetched(Kept):
    def test_json_is_kept_but_not_read_unless_its_address_is_listed(self):
        self.assertEqual(self.fetch(), {"ok": 3, "failed": 0, "skipped": 0})
        status, raw = self.con.execute("SELECT http_status, raw_path FROM fetches WHERE url=?", (PRICES,)).fetchone()
        self.assertEqual((status, (self.ws.root / raw).read_bytes()), (200, PRICES_FILE))
        self.assertTrue(raw.endswith(".json"))
        self.assertIsNone(self.document(PRICES))
        self.assertIsNone(self.document(ASSETS))
        self.assertEqual(sourcedb.extract_text(self.ws, raw, ".json", JSON_KIND, PRICES), (None, None, sourcedb.JSON_NOT_LISTED))

    def test_a_listed_address_is_read_as_it_is_fetched(self):
        self.read_json(PRICES + ".")  # As a sentence might end it; it's read as a Sources entry's address is.
        self.fetch()
        text, how = self.document(PRICES)
        self.assertEqual(how, "json")
        self.assertEqual(text.splitlines()[:3], ["meta | symbol: NBR | currency: USD | regularMarketPrice: 13.25;",
                                                 "prices | date: 2026-01-02 | close: 12.5;",
                                                 "prices | date: 2026-01-05 | close: 12.300000190734863;"])
        self.assertIn("volume: 3.1e5;", text)
        self.assertIsNone(self.document(ASSETS))  # Listing one address reads that one only.

    def test_json_already_fetched_is_read_from_its_copy_once_listed_and_dropped_once_unlisted(self):
        self.fetch()
        self.asked.clear()
        self.con.execute("UPDATE documents SET text='As an older version read it.' WHERE url=?", (ANNUAL,))
        self.read_json(PRICES)
        self.assertEqual(self.fetch(), {"ok": 0, "failed": 0, "skipped": 3, "json_read": 1})
        self.assertEqual(self.document(PRICES)[1], "json")
        self.assertEqual(self.fetch(), {"ok": 0, "failed": 0, "skipped": 3})  # Read once, not on every fetch.
        self.read_json()
        self.assertEqual(self.fetch(), {"ok": 0, "failed": 0, "skipped": 3, "json_dropped": 1})
        self.assertIsNone(self.document(PRICES))
        self.assertEqual(self.asked, [])  # Nothing was fetched again,
        self.assertEqual(self.document(ANNUAL)[0], "As an older version read it.")  # and no other source's text was read again.

    def test_reading_every_copy_again_reads_json_as_the_list_now_stands(self):
        self.fetch()
        self.asked.clear()
        self.assertEqual(sourcedb.reread(self.ws, self.con), {"read": 1, "kept": 2})  # The annual report alone.
        self.read_json(PRICES)
        self.assertEqual(sourcedb.reread(self.ws, self.con), {"read": 2, "kept": 1})
        self.assertEqual(self.document(PRICES)[1], "json")
        self.read_json()
        self.assertEqual(sourcedb.reread(self.ws, self.con), {"read": 1, "kept": 1, "dropped": 1})
        self.assertIsNone(self.document(PRICES))
        self.assertEqual(self.asked, [])

    def test_text_supplied_by_hand_for_a_json_source_stands_until_its_address_is_listed(self):
        self.fetch()
        capture = self.ws.data / "raw" / "browser_capture.jsonl"
        capture.write_text(json.dumps({"url": PRICES, "text": "01/02/2026 12.5", "method": "from the stored copy"}) + "\n", encoding="utf-8")
        sourcedb.import_text(self.ws, self.con)
        self.assertEqual(sourcedb.reread(self.ws, self.con), {"read": 1, "kept": 2, "by_hand": 1})
        self.assertEqual(self.fetch(), {"ok": 0, "failed": 0, "skipped": 3})
        self.assertEqual(self.document(PRICES), ("01/02/2026 12.5", "from the stored copy"))
        self.read_json(PRICES)
        self.assertEqual(self.fetch(), {"ok": 0, "failed": 0, "skipped": 3, "json_read": 1})
        self.assertEqual(self.document(PRICES)[1], "json")

    def test_a_listed_address_whose_body_isnt_json_has_no_text(self):
        self.read_json(PRICES)
        self.fetch(**{PRICES: (200, JSON_KIND, b"<html><body>Access denied</body></html>")})
        self.assertIsNone(self.document(PRICES))
        raw = self.con.execute("SELECT raw_path FROM fetches WHERE url=?", (PRICES,)).fetchone()[0]
        self.assertEqual(sourcedb.extract_text(self.ws, raw, ".json", JSON_KIND, PRICES), (None, None, sourcedb.JSON_UNREADABLE))

    def test_each_listed_address_says_how_it_stands(self):
        later = "https://example.com/northbridge/later.json"
        self.note.write_text(NOTE + f"- **P2.** Later closes. {later}\n", encoding="utf-8")
        self.fetch(**{ASSETS: (200, JSON_KIND, b"{not json")})
        self.read_json(PRICES, ASSETS, ANNUAL, later, "https://example.com/northbridge/price.json")
        sourcedb.reread(self.ws, self.con)
        self.assertEqual(sourcedb.listed_json(self.ws, self.con), {
            PRICES: "read", ASSETS: "unread", ANNUAL: "not_json", later: "pending",
            "https://example.com/northbridge/price.json": "uncited"})

    def test_a_local_json_file_is_read_when_its_address_is_listed(self):
        self.note.write_text(NOTE + "- **P3.** Closes from the data room. file:closes.json\n", encoding="utf-8")
        path = Path(self.tmp.name) / "closes.json"
        path.write_bytes(b'{"closes": [12.5, 12.75]}')
        done = sourcedb.import_file(self.ws, self.con, path, "P3")
        self.assertEqual((done.address, done.text_chars, done.how), ("file:closes.json", None, sourcedb.JSON_NOT_LISTED))
        self.assertTrue(self.con.execute("SELECT raw_path FROM fetches WHERE url='file:closes.json'").fetchone()[0].endswith(".json"))
        self.read_json("file:closes.json")
        self.assertEqual(self.fetch()["json_read"], 1)  # From the copy kept: it needn't be imported again.
        self.assertEqual(self.con.execute("SELECT title, text, extractor FROM documents WHERE url='file:closes.json'").fetchone(),
                         ("closes.json", "closes: 12.5;\ncloses: 12.75;", "json"))
        self.assertEqual(sourcedb.import_file(self.ws, self.con, path, "P3").how, "json")
        self.read_json()
        self.assertEqual(sourcedb.reread(self.ws, self.con)["dropped"], 1)
        self.assertIsNone(self.document("file:closes.json"))


class Judged(Kept):
    def test_a_row_citing_only_json_that_isnt_read_isnt_judged_and_doesnt_fail(self):
        self.fetch()
        rows = self.numbers()
        for row in ("| 2 January 2026 | $12.50 |", "| A close the file doesn't hold | $99.75 |", "- Total assets were $1,204.6M (D1).",
                    "- Revenue was $551.1M (D1)."):
            with self.subTest(row=row):
                self.assertEqual(rows[row][0], "source_text_unavailable")
        self.assertEqual(research.VERDICT["source_text_unavailable"], research.NOT_JUDGED)

    def test_a_listed_json_source_is_judged_as_text_and_a_figure_it_doesnt_hold_fails(self):
        self.read_json(PRICES)
        self.fetch()
        rows = self.numbers()
        self.assertEqual(rows["| 2 January 2026 | $12.50 |"][0], "supported")
        self.assertEqual(rows["| 5 January 2026 | $12.30 |"][0], "supported")  # The file's 12.300000190734863, to two places.
        self.assertEqual(rows["| A close the file doesn't hold | $99.75 |"][:2], ("not_in_source", "$99.75"))
        self.assertEqual(rows["- Revenue was $551.1M and the latest price was $13.25 (S1, P1)."][0], "supported")

    def test_an_address_that_stands_for_many_files_keeps_its_verdicts_until_it_is_listed(self):
        # The note gives one file of a data service as the source of figures the service serves from many. Unlisted,
        # its rows aren't judged, with or without another source being read. Listed, the one file is all they're
        # judged by, and the figure from another file fails: which is why reading JSON is the workspace's choice.
        self.read_json(PRICES)
        self.fetch()
        before = self.numbers()
        self.assertEqual({before[row][0] for row in before if "(D1)" in row}, {"source_text_unavailable"})
        self.read_json(PRICES, ASSETS)
        sourcedb.reread(self.ws, self.con)
        after = self.numbers()
        self.assertEqual(after["- Total assets were $1,204.6M (D1)."][0], "supported")
        self.assertEqual(after["- Revenue was $551.1M (D1)."][:2], ("not_in_source", "$551.1M"))

    def test_a_failure_beside_a_source_that_wasnt_read_says_so(self):
        self.fetch()
        status, item, detail = self.numbers()["- Revenue was $551.1M and the latest price was $13.25 (S1, P1)."]
        self.assertEqual((status, item), ("not_in_source", "$13.25"))
        self.assertEqual(research.VERDICT[status], research.FAIL)  # Still a failure: it isn't waved through.
        self.assertTrue(detail.endswith("; P1 is cited here too, but no text is held for it, so the figure wasn't looked for there"), detail)

    def test_citations_say_what_to_do_about_json_and_check_holds_it_as_not_judged(self):
        self.fetch()
        found = {f.key: f for f in citations.check(self.ws, self.con)}
        self.assertEqual({key: (f.severity, f.kind) for key, f in found.items()}, {"P1": ("warning", "no_text"), "D1": ("warning", "no_text")})
        self.assertIn("list its address under [sources] read_json in workspace.toml and run `drillcore fetch`, which reads the copy kept",
                      found["P1"].message)
        self.assertIn("`drillcore claims`", found["P1"].message)
        self.assertEqual(research.VERDICT["no_text"], research.NOT_JUDGED)
        self.read_json(PRICES)
        self.assertIn("It's listed under [sources] read_json", {f.key: f for f in citations.check(self.ws, self.con)}["P1"].message)
        self.fetch()
        self.assertEqual([f.key for f in citations.check(self.ws, self.con)], ["D1"])

    def test_the_inventory_counts_json_read_by_the_tool_as_fetched(self):
        self.read_json(PRICES)
        self.fetch()
        statuses = {entry.key: entry.status for entry in inventory.inventory(self.ws, self.con)}
        self.assertEqual(statuses, {"P1": "fetched", "D1": "fetched, no text", "S1": "fetched"})


class Gathered(Kept):
    """What `import-text` leaves on a fetch's record, by how the fetch itself went."""

    def load(self, **record):
        capture = self.ws.data / "raw" / "browser_capture.jsonl"
        capture.write_text(json.dumps({"text": "Closes 12.5 and 12.75", "captured_at": "2026-11-11T09:00:00Z", **record}) + "\n",
                           encoding="utf-8")
        return sourcedb.import_text(self.ws, self.con)

    def note_on(self, url):
        return self.con.execute("SELECT error FROM fetches WHERE url=?", (url,)).fetchone()

    def test_a_fetch_that_succeeded_isnt_recorded_as_refused(self):
        self.fetch()
        self.assertEqual(self.load(url=PRICES, method="from the stored JSON copy"), 1)
        self.assertEqual(self.note_on(PRICES), (None,))
        self.assertEqual(self.document(PRICES), ("Closes 12.5 and 12.75", "from the stored JSON copy"))
        # The source is one whose text is in hand, read on the day it was fetched.
        self.assertEqual([f.key for f in citations.check(self.ws, self.con)], ["D1"])
        statuses = {entry.key: entry.status for entry in inventory.inventory(self.ws, self.con)}
        self.assertEqual(statuses["P1"], "gathered by hand")
        fetched_on = self.con.execute("SELECT fetched_at FROM fetches WHERE url=?", (PRICES,)).fetchone()[0][:10]
        self.assertEqual(references.accessed(self.con, PRICES), fetched_on)

    def test_a_note_an_earlier_version_left_on_a_fetch_that_succeeded_is_cleared(self):
        self.fetch()
        self.con.execute("UPDATE fetches SET error='refused the automated fetch; text gathered by hand at 2026-11-10' WHERE url=?", (PRICES,))
        self.load(url=PRICES)
        self.assertEqual(self.note_on(PRICES), (None,))

    def test_a_refusal_and_any_other_failure_are_each_recorded_as_what_they_were(self):
        refused, missing, silent = PRICES, ASSETS, ANNUAL
        sourcedb.record_sources(self.ws, self.con)
        pages = {refused: (403, "text/html", b""), missing: (404, "text/html", b"")}

        def get(url):
            if url == silent:
                return None, "", url, b"", "TimeoutError: slow"
            return self.get(pages)(url)
        sourcedb.fetch(self.ws, self.con, get=get, say=lambda _: None)
        for url in (refused, missing, silent):
            self.load(url=url, method="in a browser")
        self.assertEqual(self.note_on(refused), ("refused the automated fetch; text gathered in a browser at 2026-11-11T09:00:00Z",))
        self.assertEqual(self.note_on(missing), ("the fetch failed (HTTP 404); text gathered in a browser at 2026-11-11T09:00:00Z",))
        self.assertEqual(self.note_on(silent), ("the fetch failed; text gathered in a browser at 2026-11-11T09:00:00Z",))
        self.assertEqual(references.accessed(self.con, refused), "2026-11-11")
        self.assertEqual(citations.check(self.ws, self.con), [])

    def test_an_address_never_fetched_gets_its_text_and_no_fetch_record(self):
        sourcedb.record_sources(self.ws, self.con)
        self.load(url=PRICES, captured_at="")
        self.assertIsNone(self.note_on(PRICES))
        self.assertEqual(self.document(PRICES)[1], "by hand")
        self.assertEqual(sourcedb.gathered_note(429, "by hand", ""), "refused the automated fetch; text gathered by hand")


class Commands(Kept):
    def test_fetch_reads_a_copy_it_already_holds_once_its_address_is_listed(self):
        self.run_here("sources")
        self.run_here("fetch", pages=PAGES)
        self.read_json(PRICES)
        self.asked.clear()
        out, err, code = self.run_here("fetch", pages=PAGES)
        self.assertEqual((code, self.asked, err), (0, [], ""))
        self.assertEqual(out.strip(), "fetched 0, failed 0, already had 3, read 1 JSON source from the copy kept")
        self.read_json()
        out, _, _ = self.run_here("fetch", pages=PAGES)
        self.assertEqual(out.strip(), "fetched 0, failed 0, already had 3, dropped the text of 1 whose JSON is no longer listed to be read")
        self.read_json(PRICES)
        out, err, code = self.run_here("fetch", "--reread")
        self.assertEqual((out.strip(), err, code), ("read the text of 2 pages again from its copy, kept 1 as it was", "", 0))
        self.read_json()
        out, _, _ = self.run_here("fetch", "--reread")
        self.assertIn("kept 1 as it was, dropped the text of 1 whose JSON is no longer listed to be read", out)

    def test_a_listed_address_that_does_nothing_is_named(self):
        self.run_here("sources")
        self.run_here("fetch", pages={**PAGES, PRICES: (200, JSON_KIND, b"Access denied")})
        self.read_json(PRICES, ANNUAL, "https://example.com/northbridge/price.json")
        _, err, _ = self.run_here("fetch", pages=PAGES)
        self.assertIn(f"{PRICES} is listed under [sources] read_json in workspace.toml, but its stored copy isn't JSON that can be read.", err)
        self.assertIn(f"{ANNUAL} is listed under [sources] read_json in workspace.toml, but what's stored for it isn't JSON", err)
        self.assertIn("price.json is listed under [sources] read_json in workspace.toml, but no note gives that address.", err)

    def test_check_passes_or_fails_on_the_json_it_was_told_to_read(self):
        self.note.write_text(NOTE.replace("| A close the file doesn't hold | $99.75 |\n", ""), encoding="utf-8")
        self.read_json(PRICES)
        self.run_here("sources")
        self.run_here("fetch", pages=PAGES)
        out, _, code = self.run_here("check")
        self.assertEqual(code, 0, out)
        self.assertIn("numbers     2 source text unavailable, 3 supported", out)
        self.note.write_text(NOTE, encoding="utf-8")
        out, _, code = self.run_here("check")
        self.assertEqual(code, 1)
        self.assertIn("FAIL numbers 03_prices.md:11 [P1] '$99.75': number 99.75: absent from the cited source text", out)

    def test_import_file_says_why_a_json_file_has_no_text(self):
        self.note.write_text(NOTE + "- **P3.** Closes from the data room. file:closes.json\n", encoding="utf-8")
        path = Path(self.tmp.name) / "closes.json"
        path.write_bytes(b'{"closes": [12.5, 12.75]}')
        _, err, code = self.run_here("import-file", str(path), "--key", "P3")
        self.assertEqual(code, 0)
        self.assertIn("No text could be read from it (JSON, which is read as text only when the workspace lists its address under "
                      "[sources] read_json)", err)


if __name__ == "__main__":
    unittest.main()
