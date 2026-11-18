### Added

- A source that is JSON, such as a price series or one file of a data service, can be read as text. List its address in `workspace.toml` under `[sources] read_json`, and `drillcore fetch` writes each value in the file as a line of text, in the characters the file writes it in, for `check`, `figures`, `search` and `trace` to read. A copy fetched before the address was listed is read by the next `drillcore fetch` from where it's kept, without fetching it again or reading any other source again, and the text of an address taken off the list is dropped. A local `.json` file imported with `import-file` is read the same way. An address that isn't listed is kept and not read, as before, so a note that gives one address of a data service as the source of many figures keeps its verdicts, and those figures stay with `drillcore claims`.
- `drillcore fetch` says when an address under `[sources] read_json` does nothing: no note gives it, what's stored for it isn't JSON, or its copy isn't JSON that can be read.

### Changed

- `drillcore citations` says what to do about a JSON source with no text, in place of only saying no text was read.
- When a row cites a source with no text beside one that has it, a number `drillcore check` doesn't find still fails, and the failure now names the source that wasn't read.

### Fixed

- `drillcore import-text` no longer records every address it loads as one that refused the automated fetch. A refusal is recorded as a refusal, another failure as that failure, and a fetch that succeeded carries no note at all, losing one an earlier version left. `drillcore inventory` no longer describes text gathered by hand as always following a refusal.
