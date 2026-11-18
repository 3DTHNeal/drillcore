"""Tests for names spelled one way. Every name is fictional."""
import argparse
import contextlib
import csv
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from support import CODE_ROOT, run_cli

from drillcore import names, workspace

NOTE = """# More on NorthBridge

Everything here is fictional.

## People (S1)

- Jane Doe runs Northbridge Robotics, and Zoë Marchetti chairs it.
- The Bank of America loan was repaid. NBR shares rose.
- Revenue fell, and Revenues isn't a name. COMPUTED rows are worked out.
- The company quoted "North Bridge Robotics" in its letter, and `NorthBridge` is code.
- Jane Do said so, and Zoe Marchetti agreed. Northbridge's staff grew.
- https://example.com/northbridge-robotics is an address, as is northbridgerobotics.com.

## Sources

- **S1.** North-Bridge Robotics. 2026. *Annual Report 2025.* https://example.com/northbridge/annual-2025.html
"""


class Names(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve() / "ws"
        shutil.copytree(CODE_ROOT / "example", root, ignore=shutil.ignore_patterns("data"))
        self.ws = workspace.Workspace(root, "test")

    def add_note(self):
        (self.ws.root / "research" / "02_more.md").write_text(NOTE, encoding="utf-8")

    def test_runs_of_capitals_are_names_and_openers_are_dropped(self):
        found = list(names.names_in("- The Bank of America loan, led by Jane Doe of Northbridge Robotics. NBR rose. Revenue fell."))
        self.assertEqual(found, [("Bank of America", False), ("Jane Doe", False), ("Northbridge Robotics", False),
                                 ("NBR", True), ("Revenue", True)])
        self.assertEqual(list(names.names_in("COMPUTED from the table: Q3 and It.")), [])

    def test_spellings_that_differ_only_in_what_doesnt_make_another_name_are_one(self):
        self.assertEqual(names.fold("North-Bridge Robotics's"), names.fold("northbridge robotics"))
        self.assertEqual(names.fold("Zoë"), names.fold("Zoe"))
        self.assertTrue(names.alike(names.fold("Jane Doe"), names.fold("Jane Do")))
        self.assertTrue(names.alike(names.fold("Northbridge Robotics"), names.fold("Northbrige Robotcs")))
        self.assertFalse(names.alike(names.fold("Revenue"), names.fold("Revenues")))  # A plural is the same spelling.
        self.assertFalse(names.alike(names.fold("SkyLift 900"), names.fold("SkyLift 901")))  # Another model.
        self.assertFalse(names.alike(names.fold("Dane"), names.fold("Jane")))  # Too short to tell.

    def test_the_example_spells_each_name_one_way(self):
        out, _, code = run_cli("names")
        self.assertIn("0 name(s) spelled more than one way", out)
        self.assertEqual(code, 0)

    def test_variants_are_listed_with_where_each_is_written(self):
        self.add_note()
        found = {group.label: group for group in names.check(self.ws)}
        self.assertEqual(found["NorthBridge"].spellings, ["NorthBridge", "Northbridge"])  # Northbridge's is Northbridge.
        self.assertEqual(found["Jane Doe"].variants, ["Jane Do"])
        marchetti = next(group for label, group in found.items() if "Marchetti" in label)
        self.assertEqual(sorted(marchetti.spellings), ["Zoe Marchetti", "Zoë Marchetti"])
        # Quoted, coded, addressed and listed spellings are someone else's, so none of them is a variant.
        every = {spelling for group in found.values() for spelling in group.spellings}
        self.assertFalse(every & {"North Bridge Robotics", "North-Bridge Robotics", "Revenues", "COMPUTED"})
        with (self.ws.data / names.REPORT).open(encoding="utf-8", newline="") as report:
            rows = list(csv.DictReader(report))
        self.assertIn({"name": "Jane Doe", "preferred": "", "spelling": "Jane Do", "file": "research/02_more.md", "line_no": "11"}, rows)

    def test_a_preferred_name_is_found_split_inside_a_word(self):
        pattern = names.variant_pattern("Northbridge Robotics")
        for written in ("North bridge Robotics", "NorthbridgeRobotics", "Northbridge Robotics"):
            self.assertTrue(pattern.search(written), written)
        self.assertFalse(pattern.search("Northbridge Robots"))

    def test_a_preferred_spelling_is_held_to(self):
        self.add_note()
        with self.ws.config_path.open("a", encoding="utf-8") as settings:
            settings.write('\n[names]\npreferred = ["Northbridge Robotics", "Zoë Marchetti"]\n')
        found = {group.label: group for group in names.check(self.ws)}
        self.assertEqual(found["Zoë Marchetti"].held_to, "Zoë Marchetti")
        self.assertEqual(found["Zoë Marchetti"].variants, ["Zoe Marchetti"])
        self.assertNotIn("Northbridge Robotics", found)  # Its other spellings are quoted or in the Sources list.
        (self.ws.root / "drafts" / "02_split.md").write_text("Northbridge-Robotics sold less, as northbridge robotics said.\n",
                                                             encoding="utf-8")
        found = {group.label: group for group in names.check(self.ws)}
        self.assertEqual(found["Northbridge Robotics"].variants, ["Northbridge-Robotics", "northbridge robotics"])
        self.assertEqual(found["NorthBridge"].spellings, ["NorthBridge", "Northbridge"])  # Another name: no Robotics.
        out, _, code = run_cli_in(self.ws)
        self.assertIn("Zoë Marchetti (preferred)", out)
        self.assertIn("! Zoe Marchetti", out)
        self.assertEqual(code, 1)

    def test_a_setting_that_isnt_a_list_of_names_is_refused(self):
        with self.ws.config_path.open("a", encoding="utf-8") as settings:
            settings.write('\n[names]\npreferred = "Northbridge"\n')
        with self.assertRaises(ValueError):
            names.check(self.ws)


def run_cli_in(ws: workspace.Workspace) -> tuple[str, str, int]:
    """Run `names` against a workspace of the test's own."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = names.run(ws, None, argparse.Namespace())
    return out.getvalue(), "", code


if __name__ == "__main__":
    unittest.main()
