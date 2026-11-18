### Added

- `drillcore citations` checks that every citation in the notes resolves: each cited key has a Sources entry, each entry a URL, and each URL fetched text or text gathered by hand.
- `drillcore quotes` checks that each quotation in the notes appears word for word in a source it cites, and lists the ones that don't in `data/quotes_not_found.csv`.
- `drillcore arithmetic` checks that each worked-out figure in the notes reproduces from its working: a change, a share, or a sum after "=".
- `drillcore overlap` finds passages a draft shares word for word with a fetched source, leaving out what it quotes, and writes them to `data/overlap.csv`.

### Changed

- The package and project descriptions now say what Drillcore does instead of describing the template it was made from.
