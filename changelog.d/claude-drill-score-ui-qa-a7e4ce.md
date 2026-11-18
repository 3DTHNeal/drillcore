### Changed

- `drillcore --help` lists the commands in the order a workspace needs them, from `sources` and `fetch` to `check` and `assay`, and each command's own `--help` says what it does.
- `drillcore init` makes a `research/` folder for the notes and says what to run next. `sources` says where it looked when it finds no notes.
- `drillcore figures` lists each figure it couldn't find, with its row, as `quotes` and `check` list their misses. `figures`, `check` and `claims` write their statuses as words ("not in source") rather than codes.
- `drillcore sec` exits 1 when a request to the SEC fails. `claims` says to run `sec` first when no facts are loaded, and `index` says to run `fetch` when there's nothing to index.

### Fixed

- `drillcore fetch` says why each source failed, where it printed `None 0` and the address.
- A `workspace.toml` that isn't valid TOML stops every command with the file and the problem, not a traceback. One saved with a byte order mark, as Notepad can, is read.
- A row of `checks/xbrl_claims.csv` that can't be read, or a file missing a column, stops `drillcore claims` with the line and what's wrong, not a traceback. `claims` writes a missing value as `-`, not `None`.
- Counts say "1 note" and "1 document", not "1 notes".
