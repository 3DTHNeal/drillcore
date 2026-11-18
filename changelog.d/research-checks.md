### Added

- `drillcore check` holds the notes to the sources they cite: every source key resolves to an address, every quotation appears word for word, every worked-out figure written as arithmetic recomputes, and every number in a sourced row passes the assay's number check with its measured policy. What didn't pass is written to `data/research_checks.csv`, and any failure exits 1. A workspace can name documents its notes quote that aren't sources, under `[check.quotations] not_sources`: a quotation whose sentence or table column names one is then not judged.
- `drillcore assay` judges each draft in `drafts/` against the notes with the assay: every figure must be in the notes as written (one only a cited source holds is a warning), every web address one the notes write, no name `[assay] forbidden` lists however it's split, and no claim `[assay] unsupported` lists unless the sentence denies it. Each verdict is sealed to the exact draft, notes, sources and rules, and written to `data/assay.csv`.

### Changed

- `drillcore check` and the standalone `citations`, `quotes` and `arithmetic` commands now share one implementation of each check. `quotes` judges quotations of any length, forgives the case of the first letter and honours `[check.quotations] not_sources`; `arithmetic` also reads equations and a table's Result and Arithmetic columns; `citations` reads `file NN sources K1, K2`.
- The assay is pinned to the commit that reads dates, years, period labels, identifiers and unit labels as measuring nothing, and accounting negatives as their numbers, under its measured policy. Drillcore no longer does that itself. A year after a comma ("In 2023, revenue") and a capitalized unit label ("(Millions)") are now set aside too.
