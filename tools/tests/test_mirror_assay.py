"""The assay is kept here and mirrored into Pyrite. The mirror copies it whole, stamps it, and won't overwrite an edit
made on the other side."""
import contextlib
import io
import shutil
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

from support import CODE_ROOT

import mirror_assay


class Mirror(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clone = Path(self.tmp.name) / "pyrite"
        (self.clone / "tools" / "pyrite").mkdir(parents=True)
        self.target = self.clone / "tools" / "assay"
        # Whether tools/assay here is committed is this checkout's business, not the test's.
        patcher = mock.patch.object(mirror_assay, "uncommitted", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_mirror(self, *argv: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = mirror_assay.main([str(self.clone), *argv])
        return code, out.getvalue() + err.getvalue()

    def test_it_copies_every_module_and_stamps_them(self):
        self.assertEqual(self.run_mirror()[0], 0)
        ours = sorted(path.name for path in mirror_assay.modules(mirror_assay.ASSAY))
        self.assertEqual(sorted(path.name for path in mirror_assay.modules(self.target)), ours)
        stamp = (self.target / mirror_assay.STAMP).read_text(encoding="utf-8")
        self.assertIn(f"sha256 {mirror_assay.digest(mirror_assay.ASSAY)}", stamp)
        self.assertIn(f"version {mirror_assay.version(mirror_assay.ASSAY)}", stamp)
        self.assertEqual(self.run_mirror("--check"), (0, f"Pyrite's assay matches this one, version {mirror_assay.version(mirror_assay.ASSAY)}.\n"))

    def test_a_module_dropped_here_is_dropped_there(self):
        self.run_mirror()
        (self.target / "gone.py").write_text("x = 1\n", encoding="utf-8")
        self.assertEqual(self.run_mirror("--check")[0], 1)
        self.assertEqual(self.run_mirror("--force")[0], 0)
        self.assertFalse((self.target / "gone.py").exists())

    def test_an_edit_made_in_pyrite_isnt_overwritten(self):
        self.run_mirror()
        edited = self.target / "links.py"
        edited.write_text(edited.read_text(encoding="utf-8") + "# changed in Pyrite\n", encoding="utf-8")
        code, said = self.run_mirror()
        self.assertEqual(code, 1)
        self.assertIn("changed in Pyrite since it was last mirrored", said)
        self.assertTrue(edited.read_text(encoding="utf-8").endswith("# changed in Pyrite\n"))
        self.assertEqual(self.run_mirror("--force")[0], 0)
        self.assertEqual(self.run_mirror("--check")[0], 0)

    def test_a_copy_never_mirrored_needs_force(self):
        shutil.copytree(mirror_assay.ASSAY, self.target, ignore=shutil.ignore_patterns("__pycache__"))
        code, said = self.run_mirror()
        self.assertEqual(code, 1)
        self.assertIn("never been mirrored", said)
        self.assertEqual(self.run_mirror("--force")[0], 0)

    def test_uncommitted_changes_arent_mirrored(self):
        with mock.patch.object(mirror_assay, "uncommitted", return_value=[" M tools/assay/text.py"]):
            code, said = self.run_mirror()
        self.assertEqual(code, 1)
        self.assertIn("tools/assay/text.py", said)
        self.assertFalse(self.target.exists())

    def test_only_a_pyrite_clone_is_a_target(self):
        shutil.rmtree(self.clone / "tools" / "pyrite")
        self.assertEqual(self.run_mirror()[0], 2)

    def test_line_endings_dont_change_the_digest(self):
        self.run_mirror()
        for path in mirror_assay.modules(self.target):
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.assertEqual(mirror_assay.digest(self.target), mirror_assay.digest(mirror_assay.ASSAY))

    def test_the_script_names_this_repository_assay(self):
        self.assertEqual(mirror_assay.ASSAY, CODE_ROOT / "tools" / "assay")


if __name__ == "__main__":
    unittest.main()
