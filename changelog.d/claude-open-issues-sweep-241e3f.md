### Added

- `drillcore figures` reads the label and period beside a figure it finds, in the source and in the note: a table's row label and column heading, or the clause around it. A figure the source holds only beside another period (Q3 against nine months, fiscal against calendar year, 2024 against 2025) is reported as `beside_another_period`, and one held only beside another line (gross against net, basic against diluted, restated against as reported) as `beside_another_label`. A figure whose surroundings can't be read is found, and not judged further. `data/figures_not_found.csv` gains a `detail` column saying why.
- Pinpoint citations: `S1 p.47`, `S1 pp.47-48` and `S1 §Note 12` hold a row's figures and quotations to that page or section in `figures`, `quotes` and `check`. One the source holds only elsewhere is `not_on_cited_page` or `not_in_cited_section`, a failure for `quotes` and `check`. A PDF's pages are now kept as it's read; run `drillcore fetch --reread` for PDFs fetched before.
- `drillcore conflicts` lists each figure a note takes from one source that another source in the workspace states differently for the same label and period, naming both sources and choosing neither. It reads the sources' tables, writes `data/conflicts.csv`, and exits 1 when it finds one.
- `drillcore consistency` lists each measure the notes and drafts state two ways, by label and period, beyond the rounding each is written to, with where each is. It reads tables and plain sentences such as "Revenue for 2025 was $551.1M", writes `data/consistency.csv`, and exits 1 when it finds one.

### Changed

- A table's unit stated as "In thousands" or "In millions", with a capital, is now read, as the lowercase form was.
