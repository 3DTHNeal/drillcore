### Added

- `proof` has a `dates` check. A date in a sentence ("since April 2025") later than every work the sentence cites, by the dates the reference list gives them (filed, published; never the access date), is a warning unless a cited source's stored text gives that date, as a filing gives a lock-up's end in advance: the fact came from a later source the sentence doesn't cite. A sentence about what's expected or planned is passed over. And a sentence that states the cut-off as an absolute, "nothing published after 30 June 2025", is a warning when the drafts cite works the list dates after that day, unless it names its exceptions.
- `proof` warns of an author a caption's or table's source line names in prose, "Source: annual reports of Acme Corp. and Beta Ltd.", when no entry of the reference list gives that author (in its author or anywhere in its text, as an SEC data entry names its company).
- `proof` warns of "the Appendix" where the drafts and companions give lettered appendices, naming them, and naming the one that holds the entries the line cites ("entry 50").
- `names` reads the parts of the report `[proof] companions` names, such as an appendix kept beside the drafts, as it reads the drafts.
- `consistency` reads a table whose rows are companies and whose columns are measures: a row labelled "Acme (maker)" under "Revenue growth" is Acme's revenue growth, compared only with Acme's. Its year may come from the line leading into the table ("Cross-section: 2025, the latest full year"), and a cell may give several years ("+3.1% (2024); +41.6% (2025)"). A table whose rows repeat a company, as a deal table's acquirers do, isn't read so.
- `proof`'s pointer check warns, too, when a sentence that cites nothing points to a section for a figure ("(section 7)") and the line there that gives it cites no source either: no citation in the line, no label of the author's working, and for a table's row none in its caption or note. A chain of pointers that ends nowhere is a claim nothing supports.

### Changed

- `consistency` reports two figures a whole step apart in their last place, 18.4% and 18.5%, as stated two ways. It used to count them as agreeing, since both round 18.45; a reader sees two figures for one thing.
- `names` leaves out a reference list, whose titles keep each source's own spelling.
- `names` reads a legal form after a name as the same spelling: "Kestrel Arms Co" and "Kestrel Arms LP" are "Kestrel Arms".

### Fixed

- `assay` no longer reads a citation's lettered year as a figure: "(Acme Ltd. 2024k)" warned of 2,024,000. Outside a citation, "2024k" is read as before.
- `proof` reads a reference list or companion file as it reads a Markdown draft, without the backslashes an export puts before punctuation, so an address written `annual\_report.htm` matches the source the notes cite and the figures of the sentences citing it are held to its text.
- `overlap` leaves out in-text citations: a court's or an agency's full name in a citation, which the cited document prints on its first page, isn't copied prose.
- `consistency` reads a bracketed negative with its percent sign after the bracket, "(12.7)%", as negative, and a figure written with a plus sign, "+41.6%", as a figure.
- `proof` no longer reads a company's founding year in brackets, "Acme, Inc. (1979)", as a narrative citation, when it's more than ten years before every work the list gives that author.
- `proof` holds a figure to a citation only in the citation's own clause: in "costs $1M each (Doe 2024); restores the 20% cut", the 20% isn't held to Doe 2024.
- `assay` passes a multiple in a conditional sentence, "doubling the weight would put C ahead", with that reason: the draft's own what-if claims nothing.
