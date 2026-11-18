# Changelog

What changed in each release that you'd notice when running Drillcore. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The project, made from the Headframe template.
- The core shed: `drillcore sources`, `fetch`, `sec`, `index` and `search` build a local database of the raw sources a workspace's research notes cite, with SEC structured facts and filing lists for the companies the workspace names.
- `drillcore figures` looks for each figure in the notes in the text of the source its row cites, and `drillcore claims` compares a list of headline figures with the SEC's tagged facts.
