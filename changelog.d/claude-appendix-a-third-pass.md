### Added

- **`proof`** has a `spelling` check. It warns of a word spelled in one variety of English in drafts that otherwise use the other, such as "consumer behaviour" in drafts that write "defense" and "color". Quotations and names keep their own spelling, and "-ize" and "license" are never held against British drafts.

### Changed

- **`claims`** reads more of the notes' workings again from the facts as filed:
  - When two of a company's claims share an input's size, the year a table row names settles which one it is. A "2010 to 2025" total takes its figures a year each, in order.
  - A sum on a year row may add several companies' figures.
  - An input that is another working's result takes what that working comes to as filed: from its own line, or from one earlier line that alone gives it. So a ratio of two sums is read, and so is a figure carried down a chain of workings.
  - A total read from a table's Result and Arithmetic columns is read too.
  - `data/workings_as_filed.csv` has a `via` column naming the lines a working took figures from.
- **`assay`** reads a figure in a table row that names nothing ("| 2022 | 651.5 | -4.5% |") with its column's header and the caption above the table, when its sentence alone binds no working. A figure in a row or under a caption that names its year binds only a working on that year's row.

### Fixed

- **`claims`** no longer reads an input by its size alone when another working on the same line gives it. A capital-spending total of 15.1 had been read as another year's cash from operations, and a working that took it was listed as wrong.
- **`assay`** no longer warns of a draft's figure for one year that copies a working on another year's row, such as a 2025 ratio that matched a 2013 working of the same size.
