"""The two ways in: the script a clone runs, and the `run()` that `python -m` and the installed command call."""
import contextlib
import io
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

from support import CODE_ROOT, WORKSPACE

from drillcore import __main__ as entry
from drillcore import __version__, identity

SCRIPT = CODE_ROOT / "tools" / f"{identity.SLUG}.py"


def run_script(*argv: str) -> subprocess.CompletedProcess[str]:
    # The throwaway workspace is named outright, so the child can never fall back on a pointer file in this clone.
    env = {**os.environ, identity.HOME_VARIABLE: str(WORKSPACE), "PYTHONUTF8": "1"}
    return subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True, encoding="utf-8",
                          env=env, cwd=CODE_ROOT, timeout=60, check=False)


class TheScript(unittest.TestCase):
    def test_version(self):
        done = run_script("--version")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), f"{identity.SLUG} {__version__}")

    def test_where_names_the_workspace_it_was_given(self):
        done = run_script("where")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(Path(done.stdout.strip()).resolve(), WORKSPACE.resolve())
        self.assertIn(identity.HOME_VARIABLE, done.stderr)

    def test_in_this_process_too(self):
        # A child process isn't measured for coverage, so the script also runs here once.
        out = io.StringIO()
        with mock.patch.object(sys, "argv", [str(SCRIPT), "--version"]), contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as stop:
                runpy.run_path(str(SCRIPT), run_name="__main__")
        self.assertEqual(stop.exception.code, 0)
        self.assertEqual(out.getvalue().strip(), f"{identity.SLUG} {__version__}")


class Run(unittest.TestCase):
    def test_outside_a_clone_it_says_to_install_from_one(self):
        with tempfile.TemporaryDirectory() as bare:
            with mock.patch.object(entry, "CODE_ROOT", Path(bare)):
                with self.assertRaises(SystemExit) as stop:
                    entry.run()
        self.assertIsInstance(stop.exception.code, str)
        self.assertIn("runs from a clone", str(stop.exception.code))
        self.assertIn("pip install -e .", str(stop.exception.code))

    def test_in_a_clone_it_exits_with_the_command_line_status(self):
        with mock.patch("drillcore.cli.main", return_value=3):
            with self.assertRaises(SystemExit) as stop:
                entry.run()
        self.assertEqual(stop.exception.code, 3)

    def printed(self, text: str, environ: dict[str, str]) -> tuple[bytes, int]:
        """What `run` writes to a pipe Windows opened with cp1252, as bytes, with the environment given."""
        raw = io.BytesIO()
        pipe = io.TextIOWrapper(raw, encoding="cp1252")

        def report() -> int:
            print(text)
            return 1
        with mock.patch.object(sys, "stdout", pipe), mock.patch("drillcore.cli.main", side_effect=report), \
                mock.patch.dict(os.environ, environ):
            if not environ:
                os.environ.pop("PYTHONIOENCODING", None)
            with self.assertRaises(SystemExit) as stop:
                entry.run()
            pipe.flush()
        return raw.getvalue(), int(stop.exception.code or 0)

    def test_a_pipe_is_written_as_utf8(self):
        # Git Bash, Windows Terminal and editors read a pipe as UTF-8, so a name written in cp1252 came out garbled.
        written, code = self.printed("Osterfeld Büro and 营收", {})
        self.assertEqual(code, 1)
        self.assertEqual(written.decode("utf-8").strip(), "Osterfeld Büro and 营收")

    def test_what_the_encoding_asked_for_cant_write_is_shown_as_its_escape(self):
        # Named by PYTHONIOENCODING, cp1252 is kept, and it has no Chinese. A finding that quotes some still has to be
        # printed.
        written, code = self.printed("FAIL '营收' and the rest", {"PYTHONIOENCODING": "cp1252"})
        self.assertEqual(code, 1)
        escaped = "营收".encode("ascii", "backslashreplace").decode("ascii")
        self.assertEqual(written.decode("cp1252").strip(), f"FAIL '{escaped}' and the rest")


if __name__ == "__main__":
    unittest.main()
