### Added

- A math engine behind `drillcore arithmetic` and `drillcore check`. A working written after "=" may use powers (`(551.1 / 450.0) ^ (1 / 5) - 1`), functions (`sqrt`, `ln`, `log10`, `exp`, `abs`, `sum`, `avg`, `median`, `min`, `max`) and named formulas (`cagr(start, end, years)`, `change(new, old)`, `share(part, whole)`), and an equation in running text may too, as `avg(4.1, 3.9) = 4.0` or `1.05^3 = 1.158`. Each is worked out allowing for the rounding of the figures it's written with, and one that can't be, such as the log of a figure that could be negative, is reported as unparsed with the reason.
- A compound annual rate written in words recomputes: `4.1% (from 450.0 to 551.1 over 5 years)`, or `(CAGR 450.0 to 551.1 in 5 years)`.
- A working can name a figure the notes' tables state instead of copying it: `41.2% (= {Gross profit 2025} / {Revenue 2025})`. A name is a row's label and, if needed, a period. It's looked up in the same note first, and a name that matches two figures is unparsed, listing both. The figures it names are traced to their sources like any other input.
- Rules a workspace sets under `[[arithmetic.rules]]`, such as `formula = "{Gross margin} = {Gross profit} / {Revenue}"` or `"{Revenue growth} = {Revenue} / {Revenue, prior} - 1"`, are checked in every period for which the notes' tables state each figure the rule names, with no working written. A rule that judges nothing is a warning, and one that can't be read stops the run, saying why.

### Changed

- An equation whose result is a percentage reports what it computes to as a percentage: "recomputes as a change: 17.3863%", where it said 0.173863.
