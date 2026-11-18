### Added

- **`drillcore assay`** warns about a title the notes don't give whole, such as "Chief Financial Vice President" made from a chief financial officer and a vice president, or "President" when the notes give a vice president. A credential (Certified, Chartered and the like) must be in the notes word for word.
- **`drillcore assay`** warns about a figure the notes hold only on lines about something else: "The order backlog was $551.1M" when the notes' $551.1M is revenue. A line's heading and its table's header count as its words.

### Changed

- The assay is at version 1.4.0. A name under `[assay] forbidden` is blocked with digits written for letters that look like them (`K3str3l`), and a number written with a scale letter after a space, as in `212 K`, is no longer supported by a bare 212. A verdict sealed before this names the checker as changed until `assay` is run again.
