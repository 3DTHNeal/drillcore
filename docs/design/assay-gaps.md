# Design note: the assay's remaining gaps

Status: titles, numbers bound to what they're for, names respelled with digits and `212 K` are built, in assay 1.4.0
and `drillcore assay`. The model-based check is written up here as not built, with why. The two gaps that only a résumé
has, a headline's title and the target company's name, are left to Pyrite's own gate, which can build them on the
assay's `titles` module once it's mirrored there.

The assay used to live in Pyrite, and a probe of it there listed what it could still miss. It lives here now, so this
note takes up the gaps that are the assay's own and records what was decided for each.

## Titles built from real words

**The gap.** Every word of "Senior Principal Firmware Engineer" can be true while the title is not: a senior engineer
and a principal one. A check that reads words one at a time passes it, and so does one that looks for each capitalized
term in the evidence.

**Decided.** A title must be one title of the evidence, read whole (`assay/titles.py`). It may leave words out, since
"Senior Engineer" is true of a senior software engineer, but never one that lessens it: dropping "Assistant" from an
assistant vice president, or "Co-" from a co-founder, makes the title more than it was. And it may never take its words
from two titles.

- *What counts as a title.* In the text judged, a run of capitalized words ending in a role word (Engineer, Director,
  Officer and the like, listed in `ROLES`), with what follows "of" or "for". Capitals mark where a title starts and ends, which
  is why the text judged has to use them. One word alone counts only away from the start of a sentence, since "Director"
  opening one says nothing. The first word of a sentence is capitalized anyway, so one no title uses ("Led", "Worked")
  is read as outside the title, but a word that ranks one ("Senior", "Chief") is read as part of it.
- *In the evidence*, titles are read in any case, from the role back to the first word that can't be part of one ("the",
  "was", "as"), since sources write "promoted to senior engineer". Reading too much there only approves more.
- *A credential* (a run opening with Certified, Chartered, Licensed, Registered or Accredited) must be in the evidence
  word for word: dropping a word from one names a different credential.
- *In Drillcore it's a warning.* Research drafts name institutions, surveys and offices whose names end in a role word,
  and how often that raises a false alarm hasn't been measured. A draft writer reads warnings; a gate that blocks on an
  unmeasured rule teaches people to ignore it. Pyrite, where a résumé headline is the case the rule was written for, can
  make it a failure.
- *What it can't do.* A title that runs straight into a name is cut at its last role word only when two or more words
  lead to it ("Chief Financial Officer Jane Roe"), since "Head Office" names no one. A title in lowercase in the draft
  isn't read at all. An acronym for a C-level role (CFO, CTO) isn't expanded, since CTO is written for two different
  titles; VP, SVP, EVP and AVP are.

**Left to Pyrite.** The headline (`=` line) of a résumé and an allow-list of headline titles on its Profile tab are
Pyrite's. `titles.held_titles` takes any text, so the allow-list can be passed in as evidence beside the Timeline.

## The target company's name approves itself

**Left to Pyrite.** Pyrite sets aside the name of the company a letter is written to, so the name isn't questioned as a
skill, and that lets "Built data pipelines on Acme" through. Drillcore has nothing like it: a draft's names are judged
only against `[assay] forbidden`. The fix the probe suggested, allowing the name in a letter's greeting and opening and
on a résumé only where the sources use it, is about where a letter's parts are, which only Pyrite knows. The assay's
`text.set_aside` already takes the phrase to set aside; Pyrite chooses the span.

## The posting's requisition number

Done in Pyrite before the move. It's about a job posting, so nothing of it is the assay's.

## Bind numbers to claims

**The gap.** A number in the evidence approves that number anywhere. "The order backlog was $551.1M" passes when the
notes' $551.1M is revenue.

**Decided.** The probe proposed having the drafter cite the fact each number comes from. In Drillcore a person writes
the draft, and asking them to cite a line of the notes for every figure is a cost the tool shouldn't impose to check
what they wrote. So `drillcore assay` finds the fact instead: each figure the notes hold is looked for in the lines that
state it, and when none of them, with its heading and table header, shares a describing word with the draft's
sentence, it's a warning. This is the test `check` already makes of a row against its source (`not_near_label`), with
the same word list and the same five-letter match, so the two read a figure's label the same way.

- *A warning, not a failure*, as `check`'s is: a figure can be right and described in other words.
- *What it can't do.* A sentence that shares any describing word with a line holding the figure passes, so "revenue
  from orders was $551.1M" passes against a revenue line whatever orders are. A figure of fewer than three digits, or a
  percentage of fewer than two, stands in too many lines to say anything and isn't judged.
- *Citing, for a drafter that can.* Pyrite's drafter is a model, which can be asked to cite. The assay's
  `numbers.holds` says whether one fact's evidence supports one figure, which is what a check of a cited fact needs.

## A semantic layer that can only add blocks

**Not built.** Plain prose with no number and no unfamiliar name passes every lexical check however false it is, and a
model could flag a sentence no fact supports. It isn't built here, for three reasons:

1. *The assay calls no model, by design.* Its verdict is the same for the same input, and there is nothing in it to
   persuade (`tools/assay/__init__.py`, held by `test_assay_core`). A model-based check would sit outside it, in a tool,
   and could only ever send a draft back, never pass one.
2. *Its cost isn't known.* The best of these checks are wrong about one time in five. Whether that's worth it depends on
   the lexical checks' own false-alarm rate on real drafts, which Pyrite's benchmark is meant to measure and hasn't yet.
3. *Drillcore's drafts are a person's.* The tool checks what a person wrote; a model second-guessing their prose is
   closer to writing it for them.

Revisit when the benchmark gives a false-alarm rate to weigh it against.

## Known misses, now fixed

- **A name respelled with digits** (`Blueb1rd`). `names.flexible` now lets a digit stand for the letter it looks like
  (1 for i or l, 0 for o, 3 for e, 4 for a, 5 for s, 7 for t, 8 for b, 9 for g, 2 for z). Two guards keep it from
  matching what isn't a name: the first letter must stay a letter, so `8017` is never Bolt, and a digit stands for a
  letter only when no digit follows it, so `l10n` is never Lion. A name respelled at every other letter, or with two
  digits together (`Bl00bird`), still gets past it.
- **`212 K`**, with a space and no currency sign. It's still read as 212, since 300 K is a temperature, but a bare 212
  in the evidence no longer supports it: the evidence must write it the same way ("300 K") or hold it at that scale
  ("$212K", "212,000"). A source that writes "300 kelvin" no longer supports a draft's "300 K", which is the cost.
