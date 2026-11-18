### Changed

- The assay's number check, at version 1.2.0, reads more of what a source writes. A figure after a currency code (`RMB 107.49m`, `EUR 1.7M`) and a range that states its scale once (`$65-75M`, `0.7-1.5%`) are now read at the scale they're written to. The day of a date ("Sept 30", "Sep 16-17, 2025"), a numbered reference ("item 9", "Lists 1-3") and a document number such as `COM(2025) 989` are set aside, since they measure nothing.
