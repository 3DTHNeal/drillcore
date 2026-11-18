"""Where the data lives.

The code and the data are separate on purpose, so that nothing private can be committed from the code's repository. A
workspace is a folder holding a `workspace.toml`. It's named by an environment variable or by a pointer file in the
clone, and when neither names one, the fictional example that ships with the code stands in.

Nothing here runs when the module is imported. `find()` is called by whatever needs the workspace, so a test can name
one without having to load in a certain order.
"""
import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from . import identity

CODE_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ROOT = CODE_ROOT / "example"
HOME_POINTER = CODE_ROOT / identity.HOME_POINTER


class WorkspaceError(Exception):
    """A workspace was named and can't be used. The message says why and what to do."""


@dataclass(frozen=True)
class Workspace:
    root: Path
    # What named it: the environment variable, the pointer file's path, or "" for the example.
    origin: str = ""

    @property
    def is_example(self) -> bool:
        return self.root == EXAMPLE_ROOT

    @property
    def config_path(self) -> Path:
        return self.root / identity.CONFIG

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def database_path(self) -> Path:
        return self.data / identity.DATABASE

    def config(self) -> dict[str, Any]:
        """The workspace's settings, or {} when it has no settings file yet. Raises WorkspaceError, saying where, for a
        settings file that isn't valid TOML."""
        if not self.config_path.is_file():
            return {}
        try:
            return tomllib.loads(self.config_path.read_text(encoding="utf-8-sig"))
        except tomllib.TOMLDecodeError as problem:
            raise WorkspaceError(f"{self.config_path} can't be read: {problem}. Fix it and run the command again.") from None


def _windows_path(chosen: str) -> str:
    """A path as Git Bash writes it, such as /d/work, in the form Windows reads, D:/work. Elsewhere, unchanged."""
    match = re.fullmatch(r"/([A-Za-z])(/.*)?", chosen) if os.name == "nt" else None
    return f"{match[1].upper()}:{match[2] or '/'}" if match else chosen


def _resolve(chosen: str, base: Path) -> Path:
    """The folder a name means. A relative one is relative to where it was written: the pointer file's own folder, or
    the starting folder for the environment variable."""
    return (base / Path(_windows_path(chosen)).expanduser()).resolve()


def _read_pointer(pointer: Path) -> str:
    """The first line of a pointer file that isn't blank or a comment."""
    for line in pointer.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return ""


def inside_code(folder: Path) -> bool:
    """Whether a folder is the clone or somewhere in it, where `git add` would pick its files up."""
    folder = folder.resolve()
    return folder == CODE_ROOT or CODE_ROOT in folder.parents


def _problem(folder: Path, origin: str) -> str:
    """Why a folder can't be the workspace, with what to do about it, or "" when it can be."""
    said = f"That path comes from {origin}."
    make = f"make one with `{identity.SLUG} init {folder}`."
    if not folder.is_dir():
        return f"The {identity.NAME} workspace doesn't exist: {folder}\n{said} Fix the path, or {make}"
    if inside_code(folder):
        return (f"The {identity.NAME} workspace {folder} is inside the code repository, where its files could be "
                f"committed.\n{said} Move it outside {CODE_ROOT} and point that at it.")
    if not (folder / identity.CONFIG).is_file() and not (folder / "data" / identity.DATABASE).is_file():
        # Used as it is, the first command would start an empty database there, and that looks exactly like a lost one.
        return (f"{folder} isn't a {identity.NAME} workspace: it has no {identity.CONFIG} and no data/{identity.DATABASE}."
                f"\n{said} Fix the path, or {make}")
    return ""


def named(environ: Mapping[str, str] | None = None) -> tuple[str, str, Path] | None:
    """What names a workspace, as (the name, what said it, the folder a relative name starts from), or None."""
    environ = os.environ if environ is None else environ
    chosen = environ.get(identity.HOME_VARIABLE, "").strip()
    if chosen:
        return chosen, identity.HOME_VARIABLE, Path.cwd()
    if HOME_POINTER.exists():
        chosen = _read_pointer(HOME_POINTER)
        if chosen:
            return chosen, str(HOME_POINTER), HOME_POINTER.parent
    return None


def find(environ: Mapping[str, str] | None = None) -> Workspace:
    """The workspace in use: the environment variable's, then the pointer file's, then the example.

    A workspace that was named but can't be used raises WorkspaceError, because quietly using another one, or starting
    an empty one, would look exactly like lost data."""
    choice = named(environ)
    if choice is None:
        return Workspace(EXAMPLE_ROOT)
    chosen, origin, base = choice
    folder = _resolve(chosen, base)
    if folder == EXAMPLE_ROOT:
        return Workspace(folder, origin)
    problem = _problem(folder, origin)
    if problem:
        raise WorkspaceError(problem)
    return Workspace(folder, origin)


def create(folder: Path, name: str = "") -> Workspace:
    """Make a new workspace: the folder, its settings file, its data folder and an empty research folder for the notes.
    Refuses a folder inside the clone and one that already holds anything, so nothing is ever written over."""
    folder = folder.expanduser().resolve()
    if inside_code(folder):
        raise WorkspaceError(f"{folder} is inside the code repository, where a workspace's files could be committed. "
                             f"Choose a folder outside {CODE_ROOT}.")
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise WorkspaceError(f"{folder} already has something in it. Choose a new or empty folder.")
    (folder / "data").mkdir(parents=True, exist_ok=True)
    (folder / "research").mkdir()
    title = (name or folder.name).replace("\\", "\\\\").replace('"', '\\"')
    (folder / identity.CONFIG).write_text(
        f'# A {identity.NAME} workspace. The code lives elsewhere; everything of yours lives here.\n'
        f'name = "{title}"\ncreated = {date.today().isoformat()}\n', encoding="utf-8", newline="\n")
    return Workspace(folder, "init")


def point_at(folder: Path) -> Path:
    """Write the pointer file, so this clone uses that workspace from now on. Returns the pointer's path."""
    HOME_POINTER.write_text(f"{folder}\n", encoding="utf-8", newline="\n")
    return HOME_POINTER
