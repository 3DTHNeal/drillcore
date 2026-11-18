"""Entry point for `python -m drillcore` (run from tools/) and the `drillcore` command that `pip install -e .` adds."""
import importlib.util
import io
import os
import sys
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[2]
ASSAY = CODE_ROOT / "tools" / "assay"


def assay_problem() -> str:
    """Why the fact checker, the assay package in tools/assay, wouldn't load from this clone, or "".

    The assay used to be installed from Pyrite, and that install put a package named assay in site-packages, at
    whatever version it was pinned to. An editable install made in strict mode before tools/assay was here links only
    drillcore, so Python finds that old copy instead of this one. PyPI also has an unrelated package called assay."""
    try:
        spec = importlib.util.find_spec("assay")
    except (ImportError, ValueError):
        spec = None
    origin = Path(spec.origin).resolve() if spec and spec.origin else None
    if origin and origin.parent == ASSAY.resolve():
        return ""
    script = f"`python tools/drillcore.py` from {CODE_ROOT}, which looks in the clone first and needs no install"
    reinstall = f"`python -m pip uninstall pyrite-jobs` if it's there, then `python -m pip install -e .` from {CODE_ROOT}"
    if origin:
        return (f"Python found a different package named assay, at {origin.parent}, in place of Drillcore's own in {ASSAY}. "
                f"It's most likely the copy that came with Pyrite. Run {reinstall}, or run {script}.")
    return (f"Drillcore can't find its fact checker, the assay package in {ASSAY}. An editable install made in strict mode "
            f"links only the packages there were when it was made. Run {reinstall}, or run {script}.")


def run() -> None:
    # The example workspace is read from the clone, so a copy in site-packages can't work.
    if not (CODE_ROOT / "example").is_dir():
        sys.exit("Drillcore runs from a clone of its repository. Install it with `pip install -e .` from the clone, "
                 "not `pip install .`.")
    if problem := assay_problem():
        sys.exit(problem)
    from drillcore.cli import main

    # A quotation or a name can be in any script, and Windows gives a pipe or a file its ANSI code page, cp1252, which
    # can't write most of them and which what reads the pipe (Git Bash, Windows Terminal, an editor) takes for UTF-8,
    # so "Büro" came out garbled. Output that isn't a console is written as UTF-8, as the reports' files are, unless
    # PYTHONIOENCODING names another encoding. A console is written to as text whatever its code page. What still can't
    # be written is shown as its escape, so a report never stops halfway through its findings.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            if not os.environ.get("PYTHONIOENCODING") and not stream.isatty():
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
            else:
                stream.reconfigure(errors="backslashreplace")
    sys.exit(main())


if __name__ == "__main__":
    run()
