# Contributing

Drillcore is a personal project. I use it to check my own research notes and drafts against their sources, and I share it so others can read it and run their own copy. A fork is the expected way to change it for yourself.

- **Never post real research.** No notes, drafts, fetched sources, `drillcore.db` rows or workspace paths, in an issue, a pull request or a screenshot. Show the problem on the fictional workspace in `example/`, which every command reads when nothing names another, or on a small made-up case of your own.
- **Bugs** are welcome with steps that reproduce them on the example workspace.
- **Ideas and questions** are welcome as an issue, but I may not get to them.
- **What it's for.** Drillcore checks what a person wrote against the sources they cite. It doesn't write notes or reports, and a change that has it do so won't be taken.
- **Fetching.** Each source is fetched once, under Drillcore's own declared client name, with a pause between requests to one host. When a site refuses, the refusal is recorded. A change that makes the client look like a browser, or routes around a refusal some other way, won't be taken.
- **Pull requests:** open an issue first for anything bigger than a small fix, so neither of us spends time on a change I won't take. Before opening one, run what CI runs: the tests, lint, type check and the privacy check.

  Make a venv with Python 3.11 or newer. These are the Windows paths, and elsewhere it's `.venv/bin/python`:

  ```bash
  python -m venv .venv
  .venv/Scripts/python.exe -m pip install -r tools/requirements.txt -r tools/requirements-dev.txt
  .venv/Scripts/python.exe -m unittest discover -s tools/tests
  .venv/Scripts/python.exe -m ruff check tools
  .venv/Scripts/python.exe -m mypy
  .venv/Scripts/python.exe tools/check_public.py
  ```

  The privacy check reads every commit, and reads the example PDF with pypdf or poppler's `pdftotext` (Git for Windows ships it; on macOS `brew install poppler`, on Debian or Ubuntu `apt install poppler-utils`). To have lint, the type check and the privacy check run before every push, turn on the hook once per clone. It blocks a push that CI's lint job would fail, and leaves the tests to you, since they take a couple of minutes:

  ```bash
  git config core.hooksPath .githooks
  ```

  The hook uses this checkout's venv, or the main checkout's from a `git worktree`. To use another Python, set `git config drillcore.python /path/to/python`.

  The tests use a throwaway copy of `example/`, which `tools/tests/support.py` sets up, so every test module imports `support` before anything from `drillcore`. Fixtures use the fictional company in `example/` and other made-up names, never a real company, person or place.

  The assay in `tools/assay` is the general fact checker, and [Pyrite](https://github.com/3DTHNeal/pyrite) carries a copy of it. Nothing in `tools/assay` may know about Drillcore or Pyrite (`tools/tests/test_assay_core.py` holds it to that). A fix to the assay comes with a test of the text it now judges rightly, and raises `__version__` in `tools/assay/__init__.py` when a verdict could change, since every seal records it.

  Note what changed in a file of its own under `changelog.d/`, not in CHANGELOG.md itself, as [changelog.d/README.md](changelog.d/README.md) shows, so pull requests never conflict over the changelog.

- **Security problems** go through [SECURITY.md](SECURITY.md), not an issue.
- **Conduct:** the [code of conduct](CODE_OF_CONDUCT.md) covers how we treat each other here, and how to report someone who doesn't.

Contributions are licensed under the [MIT License](LICENSE).
