### Added

- `drillcore proof` holds a draft's summary and its pointers to the body. Each figure of the executive summary (a heading such as "Executive summary", "Summary" or "Abstract") must be given in another part of the drafts, and each figure of a sentence that points to "(sections 2.1 and 4)" or "see Appendix A" must be given in one of the parts it names, which hold their subsections. In a sentence that lists three or more clauses with semicolons, a pointer covers its own clause. A part gives a figure when one of its lines holds it, at any scale or to more places, and shares two describing words with the sentence, so a 6.8% hurdle doesn't give a summary's 6.8% growth. Both are warnings, and a pointer's names the part that does give the figure.
- `[drafts] records` names, by heading, the sections of a draft that are records rather than analysis, such as a log of prompts quoted word for word. `assay` judges them for forbidden names alone, `proof` reads them for personal data and as targets of cross-references alone, and `overlap` leaves them out.
- `drillcore proof` counts an entry cited by a narrative citation or a label, "Roe and Poe (2024) measured" or "Framework: Poe 2019", as well as by brackets.

### Changed

- A draft's reference list isn't read as what the draft says. `assay` doesn't judge its figures, titles, claims or judgments (its years, page ranges and filing numbers are no claims of the draft's), but still judges its addresses and reads it for forbidden names. `overlap` leaves it out, since its titles are in the very sources they name, and `proof` reads it for its entries, not for citations or cross-references, so "Exhibit 99.1" in a filing's title isn't a reference to an exhibit.
- A table's unit can be stated in a heading above it, "### Costs (US$ millions; S1)", for every table under that heading until the next heading of its level. `check` and `assay` read it as they read a unit in the table's first heading cell or lead-in.
- When the notes give a draft's figure only bare in a table that states no unit, or written another way ("41 000", "18.2m"), on a line sharing two describing words with the draft's sentence, `assay`'s finding names that line and says to state the unit there, in place of a source that happens to hold the figure or the notes' lines about other things. Its verdict is what it would have been.
- `assay` holds the SEC's structured-data address for a company `[[sec.company]]` lists (`data.sec.gov/.../CIK0001234567/`) as a source the workspace has, as `proof` already did: `claims` holds the notes to it.
- The assay's seal covers the code that reads a draft (`drafts.py`), the `[drafts] records` setting and the companies `[[sec.company]]` lists, so a change to any of them leaves an old seal stale.

### Fixed

- `proof` no longer reads "(Osprey, sold in 2018)" or "(listed since 2012)" as a citation: an author's name never ends in a word such as "in", "since" or "by".
