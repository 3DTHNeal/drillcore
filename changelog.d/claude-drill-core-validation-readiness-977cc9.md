### Added

- `figures`, `conflicts` and `consistency` read a month as a period, as economic data names one: "October 2026", "Oct. 2026", "Oct-26", "Oct '26" or "2026M10", and a quarter written year first, as "2026Q3", "2026:Q3" or "2026 Q3". An unemployment rate for September is then no longer taken for October's, nor a monthly figure for its quarter's. A date such as "28 October 2026" or "October 28, 2026", and a month after "ended" or "to", aren't read as a month.
- The words that tell apart two economic series sharing a noun are read as qualifiers, as gross and net already were: real or nominal, core or headline, seasonally adjusted or not, a change on the year, the quarter or the month (`y/y`, `q/q`, `m/m` and the words), and a forecast or an outturn. "Real estate" isn't real.
- `figures` says when a source calls a figure a forecast or projection and the note states it without saying so ("Real GDP grew 1.7% in 2027" against "We project real GDP growth of 1.7 percent in 2027"). Words such as "expects", "sees", "will" or "is projected to" in the note say so.
- `arithmetic` recomputes a change in a rate written in points: `-0.4pp (2.7 against 3.1)` or `+25bp (from 4.25% to 4.50%)` is the new rate less the old, and a sum in points, `0.4pp (= 3.1 - 2.7)`, is read in points whether or not its rates carry a percent sign.

### Changed

- A CSV source is read as a table: each record a line with its cells split as a table's are, so its heading gives each column its year and its first cell gives the row's label. `fetch --reread` reads a CSV copy kept as plain text again this way.
- `check` warns (`not_near_label`) about a percentage of two digits, such as 4.3%, that stands in its source away from every word of its row, as it already did for figures of three digits or more. "Rate", "percent" and "points" no longer count as words of a row there, since a statistical release writes them beside every figure.

### Fixed

- Two figures side by side in a CSV source, as `Revenue,551,572`, were read as one number, 551,572, so neither was found.
