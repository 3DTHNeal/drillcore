### Added

- `proof`'s `workspace figures` check holds a count to what the draft calls it, as well as to its value. `check` now keeps what its counts are made of: those judged by kind (quotations, rows of figures, single figures, inputs), each status warned of or not judged by kind, and the lines of the notes each status stands on. "Figures held to their source: 412 judged" then fails when quotations are among the 412, "12 lines that cite no source" when the 12 results stand on fewer lines (and the count of those lines passes), and "8 sums" when most of the 8 are workings the arithmetic couldn't read rather than table totals. A count in a "Not judged:" or "Warnings:" breakdown is held to this too when it is the run's count of one status. Words that name no kind say nothing, and a run that kept no makeup isn't held to it.
- `proof`'s `cross-references` check warns of "that date" or "that day" where its sentence and the one before give two different dates, naming them nearest first: "Data runs to 11 November. Filings of 12 November are kept for facts as of that date" reads as 12 November.

### Changed

- `check`'s summary line says what it judged: `held to a source: 41 judged (12 quotations, 29 checks of figures)`. It counts checks, not figures: quotations count, a row whose figures are all found counts once, and each figure warned about counts again.
- An arithmetic result says whether it is a row's own working or a table's total (`kind`), and `check` keeps the count of each it couldn't read.

### Fixed

- A "Not judged:" breakdown no longer counts the numbers in its brackets as parts of its own: "83 workings and totals (69 workings, 14 totals)" adds 83, not 166.
