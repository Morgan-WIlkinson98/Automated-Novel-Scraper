# Glossary

> **Who this is for:** beginner developers and non-technical readers.
> **Repository stamp:** base commit `217431f` · branch `feature/update-documentation-2026-10-10` · dated 2026-10-10 · no uncommitted changes when the docs were written.
> Back to [Documentation index](README.md)

Every technical term used in these docs, in plain language. Alphabetical.

**Aggregator / hosting site** — the website that actually publishes a chapter's
text (for example a translation group's WordPress blog). NovelUpdates only
*links* to these sites; the text lives there.

**Backfill** — filling in old, missing chapters for a series the scraper
already knows about, as opposed to catching new releases as they arrive.
Example: you start following a 400-chapter novel — the backfill queue walks
back and fetches all of them.

**Cloudflare challenge ("Just a moment…")** — an anti-bot check some sites show
before the real page. A plain HTTP request gets a challenge page instead of
content; a real browser solves it automatically. This project uses a
headed (visible-window) Chromium via Playwright for exactly this reason.

**Cloud Run Job** — a Google Cloud feature that runs a container once and
shuts it down. Used for on-demand backfills (`queue_worker.py`). Contrast with
a *service*, which stays running waiting for requests.

**Cron** — a scheduler syntax (`7,37 * * * *` = "at minute 7 and 37 of every
hour"). GitHub Actions uses it to run the poller every 30 minutes.

**EPUB** — the standard e-book file format. The export feature bundles a
series' chapters into one `.epub` you can open in any e-reader.

**extnu link** — a NovelUpdates redirect URL like
`https://www.novelupdates.com/extnu/12345/`. It bounces the reader to the
aggregator site. The scraper stores it as `nuLink`/`nu_link` so it can match
chapters later without resolving the redirect again.

**Feed / RSS feed** — a machine-readable list of new posts a website publishes.
This project watches NovelUpdates' "releases" feed. `feedparser` is the Python
library that reads it.

**Firestore** — Google Firebase's document database. In cloud mode it replaces
the local SQLite files. A *collection* is like a folder of documents;
`novels/{slug}/chapters/{id}` means "the chapters subfolder inside one series
document".

**GUID** — the unique identifier each RSS entry carries. Used to remember which
entries were already processed (deduplication).

**GitHub Actions** — GitHub's built-in automation: run code on a schedule or on
demand, in a fresh virtual machine. The `.github/workflows/poll.yml` file
defines this repo's scheduled run. On a *private* repo, run time counts against
the account's monthly Actions minutes.

**Playwright** — a library that drives a real web browser (here, Chromium)
from Python. Used when a page needs JavaScript or sits behind Cloudflare.

**Politeness layer** — code that makes the scraper a good citizen: checks each
site's `robots.txt` rules before fetching and waits a minimum number of
seconds between requests to the same site. See `scraping/politeness.py`.

**Poll / poller** — checking the feed on a schedule. `poller.py` is the
single-pass version used by GitHub Actions: it does one poll and exits instead
of looping forever like `main.py`.

**Reading list** — NovelUpdates' personal list of series you follow.
The site can export it as JSON; `core/import_nu_export.py` imports that file
so the web UI can show "you are on c45, latest is c52".

**robots.txt** — a file every website can publish saying which pages automated
tools may fetch. The politeness layer checks it before every request.

**Series / slug** — a "series" is one novel. A *slug* is the lowercase,
hyphenated form of its name used in URLs and as the Firestore document id:
`My Great Novel` → `my-great-novel`.

**Service account (SA)** — a robot identity in Google Cloud. The poller's SA
key (stored as the `FIREBASE_SERVICE_ACCOUNT_JSON` secret) is what lets the
cloud runs *write* to Firestore even though the security rules are read-only
for everyone else.

**Site override** — a per-website CSS selector that says "the chapter text is
inside *this* HTML element", used when the generic extractors guess wrong.
Configured in `scraping/site_overrides.py` (currently empty).

**SQLite** — a database that lives in a single file on disk. Default storage
for local mode: `chapters.db` (the text) and `seen_entries.db` (which RSS
entries were processed).

**Translator group / `group`** — the scanlation/translation group that posted
a release. The same chapter number can exist from several groups; the release
table on the series page says which group published which link.

**Web UI** — the Flask web app (`web_ui.py`, port 6110) for browsing the
library, triggering syncs/downloads, editing settings, and exporting EPUBs.

**xvfb** — a virtual display for Linux servers. Headed Chromium needs a screen;
`xvfb-run` fakes one so the browser can run in CI where no monitor exists.
