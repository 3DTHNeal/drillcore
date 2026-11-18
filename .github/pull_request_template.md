## What changed

<!-- What this does and why, in a few lines. For anything bigger than a small fix, link the issue it was agreed in
(see CONTRIBUTING.md). -->

## Changelog

- [ ] Someone running Drillcore would notice this, and it has a note in `changelog.d/<branch>.md`
- [ ] Nobody would notice it, so it needs no note

## Checks run

- [ ] `.venv/Scripts/python.exe -m unittest discover -s tools/tests`
- [ ] `.venv/Scripts/python.exe -m ruff check tools`
- [ ] `.venv/Scripts/python.exe -m mypy`
- [ ] `.venv/Scripts/python.exe tools/check_public.py`

Nothing here comes from a private workspace: fixtures use the fictional material in `example/`.
