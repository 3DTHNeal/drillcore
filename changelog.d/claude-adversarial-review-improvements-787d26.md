### Added

- `check` warns when a figure is in its source, but none of the row's words, or its table header's, is within 250 characters of any place the source gives it (`not_near_label`). "Net income was $12.4M" against a source whose $12.4 million is a net loss now gets a warning, not a quiet pass.
- `check` traces the inputs of each worked-out figure. Each must be in a row of the notes the number check judged, be the result of another working that recomputes, or be held by a source the row cites. One that's none of these is a warning (`input_not_traced`), since a working can recompute from figures nobody can find. One written only in a row that wasn't judged isn't judged either.
- `check --strict`, or `[check] strict = true` in `workspace.toml`, exits 1 on any warning or anything not judged, as well as a failure, unless a waiver accepts it, and lists each one.

### Changed

- `check` says how much of the notes it held to a source, as `held to a source: 41 judged, not judged: 6 no source key`, and lists every warning, not only the waivers'.
- `check` exits 1 when nothing in the notes was judged against a source, as before the first `fetch`. It used to report "0 failed" and exit 0.
