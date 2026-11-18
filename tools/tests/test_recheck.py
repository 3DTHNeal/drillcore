"""Tests for `drillcore recheck`: each stored source fetched again and compared, the stored copy kept. Nothing here
reaches the network: each fetch is answered by a stand-in."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from support import CODE_ROOT, run_cli

from drillcore import recheck, sourcedb, workspace

ANNUAL = "https://example.com/northbridge/annual-2025.html"
ORDERS = "https://example.com/northbridge/orders.html"
ANNUAL_PAGE = b"<html><body><p>Revenue was 551.1 million.</p><p>Staff 1,757.</p></body></html>"
ORDERS_PAGE = b"Order book 95.4 million, 67.5 million due."


class Recheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        self.ws = workspace.Workspace(root, "test")
        self.con = sourcedb.connect(self.ws)
        self.addCleanup(self.con.close)
        self.said: list[str] = []
        sourcedb.record_sources(self.ws, self.con)
        sourcedb.fetch(self.ws, self.con, get=self.web({ANNUAL: (200, "text/html", ANNUAL_PAGE),
                                                        ORDERS: (200, "text/plain", ORDERS_PAGE)}), say=self.said.append)

    def web(self, pages):
        self.asked: list[str] = []

        def get(url):
            self.asked.append(url)
            status, kind, body = pages.get(url, (404, "text/html", b""))
            return status, kind, url, body, None if status == 200 else f"HTTP {status}"
        return get

    def again(self, pages):
        return {r.url: r for r in recheck.recheck(self.ws, self.con, get=self.web(pages), say=self.said.append)}

    def test_an_unchanged_source_says_so_and_each_is_asked_for_once(self):
        found = self.again({ANNUAL: (200, "text/html", ANNUAL_PAGE), ORDERS: (200, "text/plain", ORDERS_PAGE)})
        self.assertEqual({url: r.status for url, r in found.items()}, {ANNUAL: "unchanged", ORDERS: "unchanged"})
        self.assertEqual(sorted(self.asked), [ANNUAL, ORDERS])

    def test_a_changed_source_is_shown_as_a_diff_and_the_stored_copy_is_kept(self):
        before = self.con.execute("SELECT sha256, raw_path FROM fetches WHERE url=?", (ANNUAL,)).fetchone()
        edited = ANNUAL_PAGE.replace(b"551.1", b"549.0")
        found = self.again({ANNUAL: (200, "text/html", edited), ORDERS: (200, "text/plain", ORDERS_PAGE)})
        self.assertEqual(found[ANNUAL].status, "changed")
        self.assertIn("-Revenue was 551.1 million.", found[ANNUAL].diff)
        self.assertIn("+Revenue was 549.0 million.", found[ANNUAL].diff)
        # The copy the notes were checked against is untouched, and the new one is kept beside it.
        self.assertEqual(self.con.execute("SELECT sha256, raw_path FROM fetches WHERE url=?", (ANNUAL,)).fetchone(), before)
        self.assertIn("551.1", self.con.execute("SELECT text FROM documents WHERE url=?", (ANNUAL,)).fetchone()[0])
        new = self.con.execute("SELECT raw_path FROM rechecks WHERE url=?", (ANNUAL,)).fetchone()[0]
        self.assertNotEqual(new, before[1])
        self.assertEqual((self.ws.root / new).read_bytes(), edited)
        self.assertEqual((self.ws.root / before[1]).read_bytes(), ANNUAL_PAGE)

    def test_new_markup_around_the_same_text_is_not_a_change(self):
        found = self.again({ANNUAL: (200, "text/html", ANNUAL_PAGE.replace(b"<p>", b"<p class='x'>")),
                            ORDERS: (200, "text/plain", ORDERS_PAGE)})
        self.assertEqual(found[ANNUAL].status, "markup_changed")

    def test_a_page_that_is_gone_is_looked_up_in_the_archive(self):
        lookup = recheck.ARCHIVE + "https%3A%2F%2Fexample.com%2Fnorthbridge%2Forders.html"
        snapshot = "https://web.archive.org/web/20260101000000/https://example.com/northbridge/orders.html"
        answer = json.dumps({"archived_snapshots": {"closest": {"available": True, "url": snapshot}}}).encode()
        found = self.again({ANNUAL: (200, "text/html", ANNUAL_PAGE), lookup: (200, "application/json", answer)})
        self.assertEqual((found[ORDERS].status, found[ORDERS].archived_url), ("gone", snapshot))
        self.assertIn(lookup, self.asked)
        self.assertEqual(self.con.execute("SELECT archived_url FROM rechecks WHERE url=?", (ORDERS,)).fetchone(), (snapshot,))

    def test_an_archive_that_refuses_is_recorded(self):
        found = self.again({ANNUAL: (200, "text/html", ANNUAL_PAGE)})
        self.assertEqual(found[ORDERS].status, "gone")
        self.assertIn("the archive's lookup failed (HTTP 404)", found[ORDERS].detail)

    def test_a_refusal_is_recorded_and_nothing_is_tried_in_its_place(self):
        found = self.again({ANNUAL: (200, "text/html", ANNUAL_PAGE), ORDERS: (403, "text/html", b"")})
        self.assertEqual(found[ORDERS].status, "refused")
        self.assertFalse(any(url.startswith(recheck.ARCHIVE) for url in self.asked))

    def test_the_diff_is_cut_short(self):
        lines = recheck.text_diff("\n".join(map(str, range(200))), "\n".join(str(n + 1000) for n in range(200)), limit=10)
        self.assertEqual(len(lines), 11)
        self.assertTrue(lines[-1].endswith("more lines of difference"))


class Command(unittest.TestCase):
    def test_nothing_to_recheck_before_a_fetch(self):
        _, err, code = run_cli("recheck")
        self.assertIn("Nothing to recheck", err)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
