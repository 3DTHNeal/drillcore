### Changed

- The assay now lives in Drillcore, in `tools/assay`, so `check` and `assay` need nothing installed: `tools/requirements.txt` no longer installs Pyrite. If you installed it before, `python -m pip uninstall pyrite-jobs` and run `python -m pip install -e .` again; `drillcore` says so if it finds that old copy first.
- The assay is at version 1.3.0. A word or number split by an HTML comment (`<!-- -->`) is read whole, as it prints, and a comment's own text is left out, in drafts, notes and sources alike. A verdict sealed before this names the checker as changed until `assay` is run again.
