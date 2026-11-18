"""The name is said in one place, and the rest of the repository agrees with it. A project made from the template
changes identity.py, and these fail on whatever was left behind."""
import re
import tomllib
import unittest

from support import CODE_ROOT

import check_public as cp
from drillcore import identity


class OneName(unittest.TestCase):
    def test_the_names_follow_from_the_slug(self):
        self.assertRegex(identity.SLUG, r"^[a-z][a-z0-9_]*$")
        self.assertEqual(identity.HOME_VARIABLE, f"{identity.SLUG.upper()}_HOME")
        self.assertEqual(identity.HOME_POINTER, f".{identity.SLUG}-home")
        self.assertEqual(identity.DATABASE, f"{identity.SLUG}.db")
        self.assertTrue(1024 <= identity.PORT <= 65535)

    def test_the_package_and_its_command_carry_the_slug(self):
        project = tomllib.loads((CODE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(project["project"]["name"], identity.SLUG)
        self.assertEqual(project["project"]["scripts"], {identity.SLUG: f"{identity.SLUG}.__main__:run"})
        self.assertEqual(project["tool"]["setuptools"]["packages"], [identity.SLUG, "assay"])
        self.assertTrue((CODE_ROOT / "tools" / identity.SLUG / "__init__.py").is_file())
        self.assertTrue((CODE_ROOT / "tools" / f"{identity.SLUG}.py").is_file())

    def test_git_ignores_the_pointer_and_the_databases(self):
        ignored = (CODE_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(f"/{identity.HOME_POINTER}", ignored)
        self.assertIn("*.db", ignored)
        self.assertIn("/data/", ignored)

    def test_the_privacy_check_refuses_the_pointer_and_the_database(self):
        for path in (identity.HOME_POINTER, f"data/{identity.DATABASE}", f"backup/{identity.DATABASE}"):
            with self.subTest(path):
                self.assertTrue(cp.FORBIDDEN_PATH.search(path))

    def test_the_hook_and_ci_use_the_slug(self):
        hook = (CODE_ROOT / ".githooks" / "pre-push").read_text(encoding="utf-8")
        self.assertIn(f"git config {identity.SLUG}.python", hook)
        workflow = (CODE_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn(f"python tools/{identity.SLUG}.py --version", workflow)
        self.assertEqual(re.findall(r"tools/(\w+)\.py --version", workflow), [identity.SLUG])


if __name__ == "__main__":
    unittest.main()
