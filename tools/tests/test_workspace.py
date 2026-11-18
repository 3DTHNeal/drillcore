"""Tests for finding and making a workspace, and for the commands that do it."""
import tempfile
import tomllib
import unittest
import unittest.mock as mock
from pathlib import Path

from support import CODE_ROOT, WORKSPACE, run_cli

import drillcore
from drillcore import identity, workspace


class Temp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name).resolve()
        # No test reads the clone's own pointer file, which names whatever this machine really uses.
        self.pointer = self.dir / identity.HOME_POINTER
        patcher = mock.patch.object(workspace, "HOME_POINTER", self.pointer)
        patcher.start()
        self.addCleanup(patcher.stop)

    def made(self, name="ws") -> Path:
        return workspace.create(self.dir / name).root


class Find(Temp):
    def test_the_suite_runs_on_a_copy_of_the_example(self):
        found = workspace.find()
        self.assertEqual(found.root, WORKSPACE.resolve())
        self.assertFalse(found.is_example)
        self.assertEqual(found.config()["name"], "Example")

    def test_nothing_named_means_the_example(self):
        found = workspace.find({})
        self.assertTrue(found.is_example)
        self.assertEqual(found.origin, "")
        self.assertEqual(found.database_path, CODE_ROOT / "example" / "data" / identity.DATABASE)

    def test_the_variable_wins_over_the_pointer(self):
        first, second = self.made("first"), self.made("second")
        self.pointer.write_text(f"# where my work lives\n\n{second}\n", encoding="utf-8")
        self.assertEqual(workspace.find({}).root, second)
        self.assertEqual(workspace.find({}).origin, str(self.pointer))
        found = workspace.find({identity.HOME_VARIABLE: f"  {first}  "})
        self.assertEqual((found.root, found.origin), (first, identity.HOME_VARIABLE))

    def test_a_relative_pointer_starts_from_its_own_folder(self):
        made = self.made("beside")
        self.pointer.write_text("beside\n", encoding="utf-8")
        self.assertEqual(workspace.find({}).root, made)

    def test_an_empty_pointer_names_nothing(self):
        self.pointer.write_text("# nothing yet\n", encoding="utf-8")
        self.assertTrue(workspace.find({}).is_example)

    def test_a_named_workspace_that_cant_be_used_stops_with_why(self):
        missing = self.dir / "gone"
        plain = self.dir / "plain"
        plain.mkdir()
        for folder, says in ((missing, "doesn't exist"), (plain, "isn't a Drillcore workspace"),
                             (CODE_ROOT / "tools", "inside the code repository")):
            with self.subTest(folder=folder.name), self.assertRaises(workspace.WorkspaceError) as stopped:
                workspace.find({identity.HOME_VARIABLE: str(folder)})
            self.assertIn(says, str(stopped.exception))
            self.assertIn(identity.HOME_VARIABLE, str(stopped.exception))

    def test_a_database_alone_marks_a_workspace(self):
        folder = self.dir / "old"
        (folder / "data").mkdir(parents=True)
        (folder / "data" / identity.DATABASE).write_bytes(b"")
        found = workspace.find({identity.HOME_VARIABLE: str(folder)})
        self.assertEqual(found.config(), {})

    def test_a_git_bash_path_is_read_on_windows(self):
        with mock.patch.object(workspace.os, "name", "nt"):
            self.assertEqual(workspace._windows_path("/d/work/notes"), "D:/work/notes")
            self.assertEqual(workspace._windows_path("/d"), "D:/")
            self.assertEqual(workspace._windows_path("C:/work"), "C:/work")
        with mock.patch.object(workspace.os, "name", "posix"):
            self.assertEqual(workspace._windows_path("/d/work"), "/d/work")


class Create(Temp):
    def test_makes_the_folder_its_settings_and_its_data(self):
        made = workspace.create(self.dir / "new" / "ws", 'My "first" one')
        self.assertTrue(made.data.is_dir())
        self.assertTrue((made.root / "research").is_dir())
        self.assertEqual(made.config()["name"], 'My "first" one')
        self.assertEqual(workspace.find({identity.HOME_VARIABLE: str(made.root)}).root, made.root)

    def test_a_settings_file_that_isnt_toml_stops_with_where_and_why(self):
        made = workspace.create(self.dir / "ws")
        made.config_path.write_text('name = "unclosed\n', encoding="utf-8")
        with self.assertRaises(workspace.WorkspaceError) as stopped:
            made.config()
        self.assertIn(str(made.config_path), str(stopped.exception))
        with mock.patch.dict(workspace.os.environ, {identity.HOME_VARIABLE: str(made.root)}):
            out, err, code = run_cli("sources")
        self.assertEqual((out, code), ("", 1))
        self.assertIn("can't be read", err)
        self.assertNotIn("Traceback", err)

    def test_a_settings_file_saved_with_a_byte_order_mark_is_read(self):
        made = workspace.create(self.dir / "ws")
        made.config_path.write_text('name = "Marked"\n', encoding="utf-8-sig")
        self.assertEqual(made.config()["name"], "Marked")

    def test_refuses_the_clone_and_a_folder_with_anything_in_it(self):
        taken = self.dir / "taken"
        taken.mkdir()
        (taken / "notes.txt").write_text("mine", encoding="utf-8")
        for folder, says in ((CODE_ROOT / "example" / "inner", "inside the code repository"), (taken, "already has something")):
            with self.subTest(folder=folder.name), self.assertRaises(workspace.WorkspaceError) as stopped:
                workspace.create(folder)
            self.assertIn(says, str(stopped.exception))
        self.assertEqual((taken / "notes.txt").read_text(encoding="utf-8"), "mine")


class Commands(Temp):
    def test_version_is_the_same_everywhere(self):
        project = tomllib.loads((CODE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertEqual(project["version"], drillcore.__version__)
        out, _, code = run_cli("--version")
        self.assertEqual((out.strip(), code), (f"{identity.SLUG} {drillcore.__version__}", 0))

    def test_where_prints_the_workspace_and_what_named_it(self):
        out, err, code = run_cli("where")
        self.assertEqual((out.strip(), code), (str(WORKSPACE.resolve()), 0))
        self.assertIn(identity.HOME_VARIABLE, err)

    def test_where_says_when_it_is_the_example(self):
        with mock.patch.dict(workspace.os.environ, {identity.HOME_VARIABLE: ""}):
            out, err, code = run_cli("where")
        self.assertEqual((out.strip(), code), (str(CODE_ROOT / "example"), 0))
        self.assertIn("example that ships with Drillcore", err)

    def test_init_makes_a_workspace_and_use_points_the_clone_at_it(self):
        target = self.dir / "mine"
        out, _, code = run_cli("init", str(target), "--name", "Mine", "--use")
        self.assertEqual(code, 0)
        self.assertIn(str(target), out)
        self.assertIn(str(target / "research"), out)
        self.assertEqual(workspace.find({}).root, target)
        self.assertEqual(workspace.find({}).config()["name"], "Mine")

    def test_init_on_a_used_folder_fails_and_says_why(self):
        target = self.made("mine")
        out, err, code = run_cli("init", str(target))
        self.assertEqual((out, code), ("", 1))
        self.assertIn("already has something", err)

    def test_no_command_prints_help(self):
        out, _, code = run_cli()
        self.assertEqual(code, 0)
        self.assertIn("where", out)
        self.assertIn("init", out)
        # Listed in the order a workspace needs them: the sources are fetched before anything is checked against them.
        listed = [line.split()[0] for line in out.splitlines() if line.startswith("    ") and line.split()]
        self.assertLess(listed.index("fetch"), listed.index("index"))
        self.assertLess(listed.index("index"), listed.index("check"))
        self.assertLess(listed.index("check"), listed.index("assay"))

    def test_each_command_says_what_it_does_in_its_own_help(self):
        out, _, code = run_cli("figures", "--help")
        self.assertEqual(code, 0)
        self.assertIn("Look for each figure in the notes", out)


if __name__ == "__main__":
    unittest.main()
