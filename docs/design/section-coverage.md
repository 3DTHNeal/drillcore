# Design note: section coverage

Status: built as described, without `min_cited` or a `sections` command (the first and third open questions), and
with the rules in `workspace.toml` (the second).

## The problem

`check` says how much of the notes as a whole was held to a source: `held to a source: 41 judged, not judged: 6 no
source key`. It doesn't say where the rest is. A note can pass with forty sourced rows in its results table and nothing
under the heading that carries its argument.

Notes written to an analytical framework show this most. In a Five Forces note, each force is a heading with a
judgment under it ("buyer power is high"). When the evidence under one force is thin, the rest of the note can still
pass, and the run doesn't show the gap.

Templates for these frameworks were considered and left out. They structure the writing, and the tool checks writing
rather than doing it. What a framework adds that the tool can check is an expectation: each part of the argument rests
on something a source holds. This note proposes a check for that.

## What it does

A workspace names sections of its notes and how much of each must be held to a source. `check` counts, in each named
section, the lines it judged against a source, and fails a section with fewer than that.

```toml
# A note on an industry rests each force on at least two lines held to a source.
[[check.sections]]
notes = ["*_industry.md"]
headings = ["Rivalry", "New entrants", "Substitutes", "Buyer power", "Supplier power"]
min_sourced = 2
```

```
sections    4 covered, 1 thin
  FAIL sections 03_industry.md:41 [-] 'Supplier power': 0 of 2 lines held to a source. Under it: 3 lines, 2 citing nothing, 1 with no figure or quotation to judge
```

The rules are the person's own. Nothing is written into the notes and no heading is suggested. A workspace that
names no sections runs exactly as it does now.

## The rule

Each `[[check.sections]]` table has:

- `headings`: one heading or a list of them. Each names a section in every note the rule covers.
- `notes`: which notes the rule covers, as file names or patterns (`*_industry.md`). Left out, it covers every note.
- `min_sourced`: how many lines under the heading must be held to a source. Defaults to 1.

### Matching a heading

A heading matches when its words are the rule's, after the parts that vary between writers are taken off:

- the leading `#`s;
- a leading section number: `2.`, `2.3`, `3)`, `IV.`;
- source keys and pinpoints in brackets at the end: `(S3)`, `(S3 p.12, S4)`;
- case, and runs of spaces.

So `## 4. Buyer power (S3)` matches `Buyer power`. Nothing looser than that: `Buyer power in Asia` is a different
section. A rule that has to cover both names both.

The Sources and Gaps and cautions sections are never matched, since `check` doesn't treat them as notes.

### Where a section ends

A section runs from its heading to the next heading at the same level or above. Sub-headings belong to it, so lines
under `### Large customers` inside `## Buyer power` count toward Buyer power. This needs the heading's level, which
`NoteLine` doesn't keep today; the check reads it from the heading lines' `#`s.

### What counts as held to a source

A line counts when `check` judged it against a source's text, by the same measure behind the `held to a source` line:

- a row whose figures the numbers check judged: supported, not found, not near its label, or waived;
- a line whose quotation the quotations check judged;
- a worked-out row whose inputs were traced (`inputs_traced`), since it then rests on sourced figures.

A line counts once, however many results it has.

A line counts whether or not it passed. Coverage asks whether a section was held to a source, and the other checks
already report one that didn't hold up. Counting only passing lines would report one wrong figure twice: once as
itself and once as a thin section.

A line counts when its keys come from the heading or the prose above it, as `check` already treats it. `## Buyer
power (S3)` over three rows with figures gives three lines held to S3.

## What it reports

Each rule gives one result for each note it covers and each heading it names. The new check is called `sections`.

| Status | Verdict | When |
|---|---|---|
| `covered` | pass | at least `min_sourced` lines under the heading were held to a source |
| `thin` | fail | fewer were, and fetching more wouldn't change that |
| `section_missing` | fail | the note has no heading that matches |
| `section_not_judged` | not judged | fewer were held, but enough lines with figures or quotations are waiting on a source with no text held (`source_text_unavailable`) to reach `min_sourced` once it's fetched |
| `unused_rule` | warning | the rule covers no note, or `notes` matches no file |

The detail of a `thin` result breaks down what's under the heading: lines held to a source, lines citing nothing,
lines waiting on a source's text, and lines with no figure or quotation to judge. That last count makes a gap of a
different kind visible: a section of sourced prose with nothing in it the checks can read.

`section_missing` is a failure because the person named that heading for that note. A rule that covers notes without
the section is too broad, and `notes` narrows it.

Results go where the other checks' do: printed by `check`, written to `data/research_checks.csv` (the heading's line
number, or 0 for a missing section), and compared with the last run through `history`. `sections` isn't one of
`AGAINST_SOURCES`: it reads their results, so the `held to a source` count stays as it is.

`--strict` needs nothing new. A `section_not_judged` is listed and fails a strict run, like any other result that
isn't judged.

## Waivers

A row of `checks/waivers.csv` with `check` set to `sections` and `item` set to the heading accepts a thin or missing
section, as for any other check:

```
check,note_file,line_no,item,reason,accepted_by,accepted_on
sections,03_industry.md,,Supplier power,Two suppliers named; neither publishes anything,A. Researcher,2026-11-11
```

`waivers.CHECKS` gains `sections`.

A waiver is judged against the hash of its line and of the sources that line cites. For a section, that's the wrong
thing to hold: the heading line rarely changes, but what's under it does. Delete the one sourced line under a waived
heading and the waiver should lapse. So a sections waiver hashes every line of the section, from its heading to where
it ends. `Ledger.decide` needs a way to be given that text in place of the one line.

## Not in scope

- **Framework templates.** No headings are shipped, suggested or filled in. A Five Forces rule is a few lines of
  `workspace.toml` the person writes. `docs/setup.md` can show one.
- **Judging the argument.** Whether two sourced lines bear out "buyer power is high" is the reader's call. The check
  says they're there and that they hold up against their source, nothing more.
- **Prose with a citation but no figure or quotation.** "The company buys from two suppliers (S4)" isn't judged by
  anything that reads the source, so it doesn't count toward `min_sourced`. See the first open question.
- **Sections in drafts.** Drafts are held to the notes by `assay`, and their sections are the writer's business.

## Changes

- `tools/drillcore/sections.py`: reads `[[check.sections]]`, refusing a malformed rule (no `headings`, a `min_sourced`
  that isn't a whole number of 1 or more, a setting it doesn't know) with an error that names the rule, and finds
  each section and its extent.
- `research.py`: `coverage` reads what each line came to from the quotations and numbers results and gives the
  `sections` results, which are waived with the rest. A section's result carries the section's text, which its waiver
  is held to.
- `cli.py`: `check` prints a `sections` line only when there are sections results, so a workspace with no rules reads
  as before, and names a missing section by its note alone.
- `waivers.py`: `sections` as a check, and `decide` takes the text a finding is held to in place of its line.
- `example/workspace.toml`: a commented rule, like the others there.
- `README.md`: the rule under "What `check` holds the notes to". `docs/setup.md`: a short Five Forces example in
  "Write notes it can read", using fictional material.
- `changelog.d/<branch>.md`: an Added entry.

## Tests

In `tools/tests/test_sections.py`, against the throwaway copy of `example/` that `support.py` sets up:

- a heading with enough sourced rows is covered; one with fewer is thin, and its detail breaks down what's under it;
- `## 4. Buyer power (S3)` matches `Buyer power`; `Buyer power in Asia` doesn't;
- lines under a sub-heading count; lines after the next heading at the same level don't;
- keys inherited from the heading count;
- a row that fails the numbers check still counts toward coverage;
- a worked-out row counts only when its inputs were traced;
- a section whose rows wait on a source with no text is `section_not_judged`, and becomes `covered` once text is held;
- a note the rule covers with no matching heading is `section_missing`; a rule covering no note is `unused_rule`;
- a waiver accepts a thin section, and lapses when a line under the heading changes;
- no `[[check.sections]]` leaves `check`'s output as it is;
- a malformed rule is refused with an error naming it.

## Open questions

1. **Should cited prose count?** Much of the evidence under a framework heading is a sentence with a key and no
   figure ("The company buys from two suppliers (S4)"). A second setting, `min_cited`, could count lines that cite a
   fetched source with a key of their own. A key inherited from the heading wouldn't count, or every line under
   `## Buyer power (S3)` would count. This would be a weaker test than `min_sourced`, since nothing checks that the
   source says it. Leave it out until a real workspace needs it?
2. **`workspace.toml` or a file in `checks/`?** The rules sit with the other rules (`[assay]`, `[check]`) in
   `workspace.toml`. A `checks/sections.csv` would suit a long list kept apart from settings. A workspace with a
   handful of rules is the likely case, so this note takes `workspace.toml`.
3. **A command of its own?** `drillcore sections` could print the coverage of every heading in the notes, named by a
   rule or not, as a map of where the sourcing is thin. That's useful before any rule is written, and could come
   first.
