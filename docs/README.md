# Novel Scraper — Documentation

> **Who this is for:** beginner developers and non-technical readers.
> **Repository stamp:** base commit `ba8c7c0` · branch `docs/update-documentation-2026-10-11` · dated 2026-10-11 · no uncommitted changes when the docs were written.

**What this project is, in two sentences:** Novel Scraper watches a private
NovelUpdates RSS feed for new chapter releases, follows each release link to
the site actually hosting the chapter, and saves a clean copy of the text. A
small web UI lets you browse and export what it collected, and a scheduled
cloud poller does the same job without leaving a computer running.

**Who these docs are for:** someone who has never seen this codebase. Every
command, file, and setting described here was checked against the code at the
commit above. Where something could not be verified it is labelled, e.g.
"Not verified by running" or "Inferred:".

## Start here — reading order

1. **[01 — Overview and architecture](01-overview-and-architecture.md)** —
   what the system does and how the pieces talk to each other, with diagrams.
2. **[02 — Setup and quickstart](02-setup-and-quickstart.md)** — get it running
   on your machine (or in Docker, or in the cloud) from a clean slate.
3. **[03 — Project structure](03-project-structure.md)** — what every folder
   and file is for.
4. **[04 — Core modules and APIs](04-core-modules-and-apis.md)** — the
   functions and web endpoints that do the work, with inputs and outputs.
5. **[05 — Configuration and services](05-configuration-and-services.md)** —
   every setting and every external service the project talks to.
6. **[06 — Testing and debugging](06-testing-and-debugging.md)** — how to check
   your work and what to do when something breaks.
7. **[07 — Costs and billing](07-costs-and-billing.md)** — what the cloud
   pieces can cost and where to check the bill.
8. **[08 — Known limitations and enhancements](08-known-limitations-and-enhancements.md)** —
   honest list of weak spots, linked to GitHub issues.

Also useful:

- **[Glossary](glossary.md)** — every technical term used in these docs,
  in plain language.
- **[References](references.md)** — all external links in one place.
- **[Package security policy](PACKAGE-SECURITY.md)** — rules for adding or
  upgrading dependencies (still current; kept where it is).
- **[Deployment checklist](DEPLOYMENT-CHECKLIST.md)** — the verification
  runbook to run after every merge/deploy so a green merge can't hide a
  dead pipeline.
- **[Archive](archive/)** — the previous documentation set, kept for
  comparison. Newer files link back to the version they replaced.
- **[Diagrams](diagrams/)** — D2 source and rendered SVGs for every diagram.

## Related documents outside docs/

- [README.md](../README.md) — project overview and the file GitHub shows first.
- [CONTRIBUTING.md](../CONTRIBUTING.md) — how to propose a change.
- [AGENTS.md](../AGENTS.md) — rules for automated contributors.
