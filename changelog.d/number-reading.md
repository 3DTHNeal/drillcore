### Added

- `drillcore check` reads a unit a table states once. With `US$M` as a table's first heading, or "US$ millions except per share" in the line leading into it, a bare cell such as 6.2 is judged as written and again as $6.2 million, and passes on either reading. A finding in such a table says both readings failed.
- `drillcore check` reads the figures a Chinese page counts in ten-thousands (万) and hundred-millions (亿), in the source and in a note that repeats the page's own characters. `RMB 3.7bn` is now held to the page's 37亿, where before the check could only say the digits were there at a scale it doesn't shift to.

### Fixed

- `drillcore check` no longer reads a figure a PDF wrapped onto two lines, "$31" then "million", as 31.
- A report that quotes text a Windows pipe's code page can't write, such as Chinese, no longer stops with an error partway through. What can't be written is shown as its escape.
