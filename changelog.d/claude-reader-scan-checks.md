### Added

- `proof` checks the letters after a reference's year: an author's works in one year are lettered a, b, c in the order the list gives them, and a work alone in its year takes none. "2024k" for an author's only work of 2024 fails, saying it should be 2024 and how often the drafts cite it, so the findings together are the mapping that fixes the list.
- `proof` holds a source line that names a company's periodic report for fiscal years ("Northbridge Robotics Ltd., annual reports on Form 20-F for fiscal 2010 to 2025") to the filing list `sec` loaded for that company, and fails it when a year has no such report. A company whose list isn't loaded, or a name given another kind ("Northbridge Robotics, Inc."), isn't judged.
- `proof` checks that the entries of a record, a section `[drafts] records` names or a `[proof] companions` file, are numbered once each and in order, "**Entry 12.**" or a list's "12.", through the whole record and across its headings. A number used twice or out of order fails; one that skips numbers is a warning.
- `[[proof.table_rules]]` holds a framework's tables in the drafts to rules the workspace sets: `values`, what a column may hold (Ansoff's four quadrants), and `derive`, an outcome given by the first case whose cells match (a VRIO grid in Barney's order, where a resource not rated rare can't be "Sustained"). A cell that breaks one fails.
- `[assay] cutoff = 2026-10-31` gives the day the workspace's data were closed. `assay` then warns of a plan or expectation ("is planned to open", "expects", "will") dated to a day, month, quarter, half or year already begun by that day ("in the second half of 2026"), since by then it had partly happened or slipped. "By 2026" is a deadline, warned of only once it's past. The setting is part of the seal.

### Fixed

- `proof` no longer reads a log's entries as a reference list: an "entry" whose year closes a full date, as an AI-use log's "helper.example. November 10, 2026." does under an "Entries" heading, isn't held to citations or lettered. Naming such a log under `[proof] companions`, for the numbering of its entries, added a failure for each date two of its entries shared.
