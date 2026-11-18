### Changed

- `drillcore proof` holds a narrative citation to the reference list as it holds one in brackets. When the list has the author of "Roe et al. (2023) argue" or "Poe's (2019) frame" but not that year, it's a warning that names the years the list does give, and so is "Doe et al. (2024)" when the list has no Doe. A citation that names an entry counts as citing it, so the figures in its sentence are held to that entry's source as a bracketed citation's are. Names the list doesn't have, as in "Revenue (2024)" or "Smith and Jones (2023)", are passed over.

### Fixed

- A comparative in brackets, as UK and European reports give the prior year, "£551.1m (2024: £572.5m)", is read as a clause of its own. `figures` no longer reports this year's figure as beside the prior year, in a source or in the notes, and `consistency` reads this year's figure from a sentence that gives both, where before it read neither.
