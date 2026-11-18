### Added

- **`drillcore proof`** holds each draft to itself and the workspace. Every author-date citation, "(Northbridge Robotics 2025a, 2025b; Roe et al. 2024, 45)", in brackets or in a "Source:" line, must name an entry of the reference list: the draft's own, under a References heading, or the files `[proof] references` names. An entry written twice, or two for one author and year, fails; one no draft cites, or whose address is no source the notes cite, is a warning. A figure in a sentence that cites a source the notes hold must be in that source's text (a warning). "section 5.3", "Exhibit E12", "Table 4", "Appendix B" and "entry 50" must name a heading, caption or entry the drafts or `[proof] companions` give. Each exhibit is captioned once and mentioned in the text. A table's Total column and Total row, a working written out, and a total stated in prose ("The three cash lines total about $35M") must add up. Local paths that name an account, email addresses, account handles and `[proof] personal` terms are reported. Writes `data/proof.csv`.
- **Drafts as Word documents and PDFs.** A `.docx` or `.pdf` in `drafts/` is read as text by `assay`, `proof`, `consistency`, `names`, `overlap`, `trace` and `evidence`: a Word document with its headings, list items and tables kept as Markdown, a PDF through `pdftotext`.
- `drillcore assay` passes a figure that rounds one the notes give more exactly, at the same scale and to the precision it's written to (7.4% of 7.36%, $38M of $37.6 million), and says so: `--all` lists such passes with the figure each rounds, and the run counts them. It does so too where the notes give the rounded figure exactly but only on a line about something else, when a line sharing two describing words with the sentence gives the more exact one.
- `drillcore assay` reads a unit stated once, by a line's label ("COMPUTED, US$ millions: ... 418.6"), a table's first heading or lead-in, or a column's heading ("Cost ($M)"), for the bare figures under it, in the notes and in a draft. `$418.6M` in a draft is the notes' 418.6.
- `[assay.allowed]` lets a forbidden name stand in listed places only: captions, source lines, the reference list or in-text citations. `[assay] judgments` lists opinions that pass only with an attribution ("in the author's view", `[assay] attributions`) or a citation.
- `[consistency] entities` names companies beyond those `[[sec.company]]` lists, so `consistency` can tell whose figure each is.

### Changed

- The assay is 1.5.0. "Tenfold" and "two-fold" are the multiples 10x and 2x, on either side of a check. "The seven figures accepted after review" is a count, not the idiom for a nine-digit sum; "earns six figures" and "a six-figure salary" still are. A title reads "R&D" as one word, so "Head of R&D" is read whole, and "Executive MBA" or "Executive Education" isn't a title.
- `drillcore consistency` reads a table column headed by a measure ("Gross margin", "Net margin") as a measure of its own, so cells of one row aren't paired, and pairs a figure only with figures of the same company, read from its label, its table's lead-in, its headings or the document's title.
- A warning that a figure the notes hold sits only on lines about other things names the notes' nearest lines, with where each is and the stretch around the figure, in place of five words in alphabetical order.

### Fixed

- Output to a pipe or a file is UTF-8 unless `PYTHONIOENCODING` names another encoding, so a name such as "Osterfeld Büro" or one in Chinese no longer prints garbled in Git Bash, Windows Terminal or an editor.
