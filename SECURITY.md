# Security

Drillcore runs on your own machine. It fetches pages and files that other people wrote, keeps them, and serves your notes and those sources to a page in your browser. A flaw here can let a source do more than be read, or let a web page reach your notes, so I'd rather hear about one privately.

## Reporting a problem

Use [GitHub's private advisory form](https://github.com/3DTHNeal/drillcore/security/advisories/new), not a public issue. Say what you ran, what happened and what an attacker gains. Leave your own research out: the fictional workspace in `example/` can show almost anything, and a made-up source served from your own machine can stand in for a hostile page.

I'll reply within a week. This is a personal project, so there's no bounty, but I'll credit you in the fix unless you'd rather I didn't.

Only the latest `main` is supported.

## What counts

- A fetched source, or a file kept with `import-file`, getting out of being data: code it holds being run, a file written outside the workspace's `data/`, or control characters reaching your terminal through `fetch`, `search` or any other command's output.
- A cited address reaching this machine, a private network or a cloud's metadata service, directly or by a redirect.
- A hidden element in a page (the `hidden` attribute, or an inline `display: none`, `visibility: hidden` or `opacity: 0`) passing a check as if it were the page's text.
- The review page (`drillcore review`) letting another site open in the browser, or another user on the machine, read your notes or sources or write to them. It's meant to answer only requests to 127.0.0.1 or localhost that carry the token the page was given.
- The assay or `check` passing a draft or a note that its documented rules say must fail, because of something in the text rather than a known gap.
- A way past `tools/check_public.py` for the kinds of data it says it catches.

## What doesn't

- Anything that needs your user account on the machine already. Whoever has it can read the workspace directly.
- Text a source hides by a style sheet, by colour, by size or by position, and a PDF's invisible text layer. These are read on purpose, as the README's "What a source can't do" explains.
- The misses listed in [docs/design/assay-gaps.md](docs/design/assay-gaps.md). They're known, not vulnerabilities.
- A site refusing Drillcore's fetch. That's recorded as a refusal by design.
- A flaw in a dependency with no path through Drillcore. Report that upstream.
