### Added

- `drillcore fetch --reread` reads the text again from the copy kept of every page, without fetching anything, so pages kept by an older version are read as this one reads them.

### Security

- `drillcore fetch` leaves out of a page's text whatever the page hides from its reader: an element with the `hidden` attribute, or an inline style of `display: none`, `visibility: hidden` or `opacity: 0`, with everything inside it. A figure or quotation planted out of sight no longer passes `figures`, `check` or `quotes`, or turns an assay failure into a warning. Run `drillcore fetch --reread` to read pages already kept this way.
- Control characters, direction overrides and invisible marks are taken out of a source's text as it's kept, and out of what `search` and `fetch` print, so a page can't send a terminal escape sequence (clearing the screen, rewriting a line, setting the clipboard) through a report. `search` marks each snippet as source text.
- A page naming UTF-7 or an escape codec as its encoding is read as UTF-8 instead, as a browser would, so bytes that look plain can't turn into markup or control characters.
- A redirect is followed only to another `http` or `https` address on the public internet, after the usual pause for its host. Before, a cited page could send the fetch to an FTP address, to this machine, a private network or a cloud's metadata service, and what it found there was kept as the source.
- Only a filing index cited at, and served from, `www.sec.gov/Archives/` brings in the documents it lists. Before, any address containing "sec.gov/Archives" did.
