"""Copies the assay, tools/assay, into a clone of Pyrite, which keeps a mirror of it.

Drillcore is where the assay is kept and changed. Pyrite is public and this repository isn't yet, so Pyrite carries a
copy, and this is the only way that copy should change. It replaces every module in the clone's tools/assay with this
one's and writes mirror.txt beside them: the assay's version and a digest of its modules. A test in Pyrite recomputes
the digest, so an edit made to the copy there fails until it's carried here and mirrored back.

    python tools/mirror_assay.py PATH/TO/PYRITE           mirror this tools/assay into that clone
    python tools/mirror_assay.py PATH/TO/PYRITE --check   only say whether the clone's copy matches this one

It won't mirror changes not yet committed here, so every copy in Pyrite is one this repository can name, and it won't
overwrite a copy that was edited in Pyrite, which would lose that edit. `--force` does both anyway.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSAY = ROOT / "tools" / "assay"
STAMP = "mirror.txt"
VERSION = re.compile(r'^__version__ = "([^"]+)"$', re.M)
HEADER = """\
# tools/assay is a mirror of the assay, which is kept and changed upstream and copied here whole by a script there.
# A test checks that the modules still match the digest below, so an edit made here fails: carry it upstream instead.
"""


def modules(folder: Path) -> list[Path]:
    """The package's modules, in name order. Caches and the stamp aren't part of it."""
    return sorted(folder.glob("*.py"), key=lambda path: path.name)


def digest(folder: Path) -> str:
    """One hash over every module's name and text. Line endings are read as \\n, so a checkout that writes \\r\\n on
    Windows gets the same digest as one on Linux."""
    whole = hashlib.sha256()
    for path in modules(folder):
        whole.update(path.name.encode() + b"\0" + path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return whole.hexdigest()


def version(folder: Path) -> str:
    found = VERSION.search((folder / "__init__.py").read_text(encoding="utf-8"))
    if not found:
        raise SystemExit(f"{folder / '__init__.py'} doesn't set __version__.")
    return found.group(1)


def stamp(folder: Path) -> str:
    return f"{HEADER}version {version(folder)}\nsha256 {digest(folder)}\n"


def recorded(folder: Path) -> str | None:
    """The digest the clone's mirror.txt records, or None when it has none."""
    path = folder / STAMP
    if not path.is_file():
        return None
    found = re.search(r"^sha256 ([0-9a-f]{64})$", path.read_text(encoding="utf-8"), re.M)
    return found.group(1) if found else None


def uncommitted() -> list[str]:
    """Changes to tools/assay here that aren't committed, as git status lists them."""
    done = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "tools/assay"],
                          capture_output=True, text=True, check=True)
    return [line for line in done.stdout.splitlines() if not line.endswith("__pycache__/")]


def mirror(target: Path) -> None:
    """Make the clone's tools/assay this one, module for module, and stamp it."""
    target.mkdir(exist_ok=True)
    wanted = {path.name for path in modules(ASSAY)}
    for path in modules(target):
        if path.name not in wanted:
            path.unlink()
    for path in modules(ASSAY):
        (target / path.name).write_bytes(path.read_bytes())
    (target / STAMP).write_text(stamp(ASSAY), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mirror tools/assay into a clone of Pyrite.")
    parser.add_argument("pyrite", type=Path, help="the Pyrite clone or worktree to copy the assay into")
    parser.add_argument("--check", action="store_true", help="only say whether the clone's copy matches this one")
    parser.add_argument("--force", action="store_true", help="mirror uncommitted changes, or over an edited copy")
    args = parser.parse_args(argv)
    clone = args.pyrite.resolve()
    if not (clone / "tools" / "pyrite").is_dir():
        print(f"{clone} isn't a clone of Pyrite: it has no tools/pyrite.", file=sys.stderr)
        return 2
    target = clone / "tools" / "assay"
    ours, theirs = digest(ASSAY), digest(target) if target.is_dir() else None
    if args.check:
        if theirs == ours and recorded(target) == ours:
            print(f"Pyrite's assay matches this one, version {version(ASSAY)}.")
            return 0
        print(f"Pyrite's assay differs from this one. Run `python tools/mirror_assay.py {args.pyrite}`.", file=sys.stderr)
        return 1
    if not args.force:
        if changes := uncommitted():
            print("tools/assay has changes not committed here, so the mirror couldn't name what it copied:\n  "
                  + "\n  ".join(changes) + "\nCommit them first, or pass --force.", file=sys.stderr)
            return 1
        if theirs is not None and recorded(target) is None:
            print(f"{target} has never been mirrored, so nothing says whether it was changed in Pyrite. Compare it with "
                  f"tools/assay here, then pass --force to mirror over it.", file=sys.stderr)
            return 1
        if theirs is not None and theirs != recorded(target):
            print(f"{target} was changed in Pyrite since it was last mirrored. Carry that change into tools/assay here "
                  f"first, or pass --force to overwrite it.", file=sys.stderr)
            return 1
    if theirs == ours and recorded(target) == ours:
        print(f"Pyrite's assay already matches this one, version {version(ASSAY)}.")
        return 0
    mirror(target)
    print(f"Mirrored the assay, version {version(ASSAY)}, into {target}.\n"
          "In that clone: run its tests, add a changelog.d note if a verdict could change, and commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
