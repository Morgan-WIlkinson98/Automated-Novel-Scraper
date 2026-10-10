# References

> **Who this is for:** beginner developers and non-technical readers.
> **Repository stamp:** base commit `217431f` · branch `feature/update-documentation-2026-10-10` · dated 2026-10-10 · no uncommitted changes when the docs were written.
> Back to [Documentation index](README.md)

Every external link used across this documentation set, grouped. Links marked
*not verified* were taken from code/config and not re-checked during this
pass.

## Upstream services

- [NovelUpdates](https://www.novelupdates.com/) — the directory site this
  project polls; RSS feed and `/extnu/` release links.
- [wuxiaworld.eu](https://wuxiaworld.eu/) — mirror source #1 *not verified*.
- [novelfull.net](https://novelfull.net/) — mirror source #2 *not verified*.
- [novellunar.com](https://novellunar.com/) — mirror source #3 *not verified*.
- [morganwilkinson.com](https://morganwilkinson.com) — the site hosting the
  Novels reader app that consumes Firestore data.

## Python dependencies (docs)

- [feedparser](https://feedparser.readthedocs.io/) — RSS/Atom parsing.
- [Playwright for Python](https://playwright.dev/python/) — browser automation.
- [trafilatura](https://trafilatura.readthedocs.io/) — primary text extractor.
- [readability-lxml](https://github.com/buriy/python-readability) — fallback extractor.
- [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/) —
  HTML parsing for overrides/mirrors.
- [Flask](https://flask.palletsprojects.com/) — the web UI.
- [ebooklib](https://github.com/aerkalov/ebooklib) — EPUB generation.
- [google-auth](https://googleapis.dev/python/google-auth/latest/) — SA token
  for Firestore REST calls.

## Cloud services

- [Firestore REST API](https://firebase.google.com/docs/firestore/reference/rest) —
  the interface `data/firestore_store.py` uses (no SDK).
- [Cloud Run Jobs](https://cloud.google.com/run/docs/create-jobs) — the
  `novels-backfill` execution model.
- [GitHub Actions schedules](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule) —
  cron semantics used by `poll.yml`.
- [xvfb](https://www.x.org/releases/X11R7.7/doc/man/man1/Xvfb.1.xhtml) —
  virtual display for headed Chromium on CI.

## Repository internals

- [Issue #46 — Refresh repository documentation set](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/46) —
  tracking issue for this documentation pass.
- [PACKAGE-SECURITY.md](PACKAGE-SECURITY.md) — dependency vetting policy.
- [Archived previous documentation set](archive/) — superseded files with
  archive notes.

## Tools used to write these docs

- [D2](https://d2lang.com/) — diagram language for `docs/diagrams/*.d2`.
