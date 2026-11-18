"""What every test module shares: a throwaway copy of the example workspace, and a check that nothing is left open.

Import this before anything from drillcore. It points DRILLCORE_HOME at the copy, so no test can read or change
anyone's real workspace, whatever this machine normally uses.
"""
import atexit
import contextlib
import gc
import io
import os
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

# A file, socket or database left open fails the run. Python reports one only as a warning, often from the garbage
# collector after the test that leaked it has passed, so they're gathered here and judged once every test has run.
_leaks: list[str] = []
_show_warning = warnings.showwarning


def _note_leak(message, category, filename, lineno, file=None, line=None):
    if issubclass(category, ResourceWarning):
        _leaks.append(str(message))
    _show_warning(message, category, filename, lineno, file, line)


def _fail_on_leaks():
    # A database connection sits in a reference cycle, so it's reported only when the collector runs. By now the test
    # runner has put back Python's default filters, which hide ResourceWarning, so they're turned on again for this.
    with warnings.catch_warnings():
        warnings.simplefilter("always", ResourceWarning)
        gc.collect()
    if _leaks:
        sys.stdout.flush()
        print(f"\nFAILED: resources left open: {len(_leaks)}. The warnings above say which; "
              "run with -X tracemalloc=20 to see where each was opened.", file=sys.stderr, flush=True)
        os._exit(1)


warnings.showwarning = _note_leak
atexit.register(_fail_on_leaks)  # Registered before the workspace's cleanup below, so it runs after it.

CODE_ROOT = Path(__file__).resolve().parents[2]
_workspace = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
atexit.register(_workspace.cleanup)
WORKSPACE = Path(_workspace.name) / "workspace"
shutil.copytree(CODE_ROOT / "example", WORKSPACE, ignore=shutil.ignore_patterns("data"))
os.environ["DRILLCORE_HOME"] = str(WORKSPACE)  # Before anything loads: no test may find a real workspace.

sys.path.insert(0, str(CODE_ROOT / "tools"))

from drillcore import cli  # noqa: E402


def run_cli(*argv: str) -> tuple[str, str, int]:
    """Run a command in this process, and return what it printed, what it said on stderr, and its exit status."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as stop:
            code = stop.code if isinstance(stop.code, int) else (0 if stop.code is None else 1)
    return out.getvalue(), err.getvalue(), code


def write_docx(path: Path, blocks: list[object]) -> Path:
    """A minimal Word document: each block a paragraph's text, a (style, text) pair such as ("Heading1", "Results"), or
    a list of rows, each a list of cells, for a table."""
    import zipfile
    from xml.sax.saxutils import escape

    def paragraph(text: str, style: str = "") -> str:
        styled = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        return f"<w:p>{styled}<w:r><w:t xml:space=\"preserve\">{escape(text)}</w:t></w:r></w:p>"

    body = []
    for block in blocks:
        if isinstance(block, str):
            body.append(paragraph(block))
        elif isinstance(block, tuple):
            body.append(paragraph(block[1], block[0]))
        elif isinstance(block, list):
            rows = "".join("<w:tr>" + "".join(f"<w:tc>{paragraph(cell)}</w:tc>" for cell in row) + "</w:tr>" for row in block)
            body.append(f"<w:tbl>{rows}</w:tbl>")
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                + "".join(body) + "</w:body></w:document>")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        archive.writestr("word/document.xml", document)
    return path
