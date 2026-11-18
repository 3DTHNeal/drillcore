### Fixed

- `drillcore fetch --reread` no longer replaces text gathered by hand with what the address's stored copy reads as. A page that fetched but shows its words only once a script has laid them out reads as no text, so its text is loaded with `import-text`; reading every copy again used to put nothing back in its place until `import-text` was run again. That text is now kept, and the command says how many of the pages it kept were gathered by hand. A JSON address listed under `[sources] read_json` is still read from its copy in place of text gathered by hand.
