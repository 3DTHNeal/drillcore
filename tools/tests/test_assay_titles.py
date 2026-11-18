"""The assay's titles check: a title or credential must be one the evidence gives, read whole, so one put together from
real words is found. Everything here is made up."""
import unittest

import support  # noqa: F401

from assay import titles
from assay.findings import Finding

EVIDENCE = """## Experience
- Senior Firmware Engineer, Acme, 2019-2022
- Principal Engineer at Globex
- Promoted to director of engineering in 2021.
- Assistant Vice President, Initech
- Co-Founder of Hooli
- Product Manager
- Certified Kubernetes Administrator
- Sr. Software Engineer
"""


class Titles(unittest.TestCase):
    held = titles.held_titles(EVIDENCE)

    def flagged(self, text: str) -> list[str]:
        return [finding.text for finding in titles.title_findings(text, self.held)]

    def test_letters_joined_by_an_ampersand_are_one_word(self):
        held = titles.held_titles("She was appointed Head of R&D in 2020, and he ran M&A.")
        self.assertIn("head of r&d", [title.named() for title in held.titles])
        self.assertEqual([f.text for f in titles.title_findings("Jo Roe, Head of R&D, left.", held)], [])
        self.assertEqual([f.text for f in titles.title_findings("Jo Roe, Head of P&L, left.", held)], ["Head of P&L"])

    def test_a_degree_or_course_isnt_a_title(self):
        for text in ("Jo Roe · Northbridge Executive MBA, final report", "An Executive Education course.",
                     "She took the Executive Program in 2020."):
            with self.subTest(text):
                self.assertEqual(self.flagged(text), [])
        self.assertEqual(self.flagged("Jo Roe, Northbridge Executive Director, said so."), ["Northbridge Executive Director"])

    def test_the_evidence_gives_its_titles_in_any_case(self):
        self.assertEqual([title.named() for title in self.held.titles], [
            "senior firmware engineer", "principal engineer", "director of engineering", "assistant vice president",
            "co founder of hooli", "product manager", "certified kubernetes administrator", "senior software engineer"])

    def test_a_title_the_evidence_gives_passes_whole_or_in_part(self):
        for text in ("Senior Firmware Engineer", "Senior Engineer", "Principal Engineer", "Director of Engineering",
                     "Promoted to Director in 2021.", "Co-Founder of Hooli", "Assistant Vice President of nothing",
                     "Sr Software Engineer", "Certified Kubernetes Administrator", "Worked as Principal Engineer."):
            with self.subTest(text):
                self.assertEqual(self.flagged(text), [])

    def test_a_title_put_together_from_two_is_found(self):
        for text, found in (("Senior Principal Firmware Engineer", "Senior Principal Firmware Engineer"),
                            ("Director of Product Engineering", "Director of Product Engineering"),
                            ("Senior Product Manager at Acme", "Senior Product Manager"),
                            ("Worked as Principal Firmware Engineer.", "Principal Firmware Engineer")):
            with self.subTest(text):
                self.assertEqual(self.flagged(text), [found])

    def test_leaving_out_a_word_that_lessens_a_title_isnt_allowed(self):
        self.assertEqual(self.flagged("Was Vice President, Initech"), ["Vice President"])
        self.assertEqual(self.flagged("Then Founder of Hooli"), ["Founder of Hooli"])
        self.assertEqual(self.flagged("Then AVP at Initech, never SVP."), ["SVP"])

    def test_a_credential_must_be_given_word_for_word(self):
        self.assertEqual(self.flagged("Certified Kubernetes Security Administrator"), ["Certified Kubernetes Security Administrator"])
        self.assertEqual(self.flagged("Certified Cloud Practitioner"), ["Certified Cloud Practitioner"])

    def test_the_first_word_of_a_sentence_is_capitalized_anyway(self):
        self.assertEqual(self.flagged("Led Senior Engineer hiring."), [])
        self.assertEqual(self.flagged("Engineers fixed it."), [])
        # A word that ranks a title is part of it there too.
        self.assertEqual(self.flagged("Senior Manager of Hooli."), ["Senior Manager of Hooli"])

    def test_a_title_can_run_into_a_name_and_a_dash_sets_it_apart(self):
        self.assertEqual(self.flagged("Then Principal Engineer Jane Roe said so."), [])
        self.assertEqual(self.flagged("Then Chief Engineer Jane Roe said so."), ["Chief Engineer"])
        self.assertEqual(self.flagged("Senior Engineer - Acme"), [])
        self.assertEqual(self.flagged("The Head Office moved, and the Executive Summary says so."), [])

    def test_findings_are_data_with_their_place(self):
        text = "Jane, Senior Principal Engineer, wrote it."
        [found] = titles.title_findings(text, EVIDENCE)
        self.assertEqual(found, Finding("titles", "title", "senior principal engineer", "Senior Principal Engineer", 6, 31))
        self.assertEqual(text[found.start:found.end], found.text)
        self.assertEqual(titles.title_errors("Draft", text, EVIDENCE, "not in the sources"), [
            "Draft gives titles not in the sources, put together from words that are: 'Senior Principal Engineer'. "
            "Use a title as the sources give it."])
        self.assertEqual(titles.title_errors("Draft", "Principal Engineer", EVIDENCE, "not in the sources"), [])


if __name__ == "__main__":
    unittest.main()
