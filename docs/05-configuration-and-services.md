# 05 — Configuration and Services

> **Who this is for:** beginner developers and non-technical readers.
> **Repository stamp:** base commit `ba8c7c0` · branch `docs/update-documentation-2026-10-11` · dated 2026-10-11 · no uncommitted changes when the docs were written.
> Back to [Documentation index](README.md) · Previous version: [archive/2026-10-10_deployment.md](archive/2026-10-10_deployment.md) (deployment sections only)

## Contents

- [How settings resolve](#how-settings-resolve)
- [Settings reference](#settings-reference)
- [Secrets — where they live](#secrets--where-they-live)
- [External services](#external-services)
- [Deployment surfaces](#deployment-surfaces)

## How settings resolve

`core/settings.py` is the single source of truth. Precedence, highest first:

1. **Environment variables** — always win. This is how GitHub Actions and
   Cloud Run configure runs.
2. **`config.py`** — a gitignored module in the repo root. `Settings.load()`
   imports it if present; `Settings.save_to_file()` writes back to it (this is
   what the Settings page's Save button does).
3. **Built-in defaults** — used when neither of the above sets a value.

There is also a `core/config.example.py` template — copy from it, don't
edit it. A stale second copy of credentials (`core/config.py`) may exist on
your disk from before the package layout — it is not imported by the app; see
[08 — Known limitations](08-known-limitations-and-enhancements.md).

## Settings reference

**Required for any real run** (no useful defaults exist):

| Setting | Purpose |
|---|---|
| `RSS_FEED_URL` | Your private NovelUpdates RSS URL (secret: `NU_RSS_FEED_URL`) |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | SA key JSON; **required in cloud mode** (`DB_TYPE=firestore`) — `poller.py` and `queue_worker.py` exit early without it |
| `NOVELUPDATES_USERNAME` / `NOVELUPDATES_PASSWORD` | NU login; used for authenticated feed fetches and series-page sync |
| `NOVELUPDATES_COOKIES` | Cookie dict (or JSON string) — `wordpress_logged_in_*`, `cf_clearance` (secret: `NU_COOKIES`) |
| `USER_AGENT` | Should match the browser you copied cookies from |

**Behavior tuning** (all have defaults):

| Setting | Default | Purpose |
|---|---|---|
| `DB_TYPE` | `sqlite` | `sqlite` or `firestore`. Cloud entry points refuse anything else. |
| `POLL_INTERVAL_SECONDS` | 900 | Seconds between RSS polls in local loop mode |
| `MIN_DELAY_SECONDS` | 5 | Per-domain politeness delay — **dead config**: `politeness.py` uses its own hardcoded `5`, ignoring this setting ([#52](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/52)) |
| `MIN_CHARS` / `MIN_PARAGRAPHS` | 500 / 3 | Extraction quality thresholds — **dead config**: `quality_check` is always called with its own defaults ([#52](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/52)) |
| `SEEN_ENTRIES_DB` / `CHAPTERS_DB` | `seen_entries.db` / `chapters.db` | SQLite file paths |
| `READING_LISTS_DIR` | `reading_lists` | Where the NU-list importer looks for `*.json` exports (manual: `python -m core.import_nu_export`) |
| `EXPORT_DIR` | `EXPORT_DIR_MAC` on macOS/Linux, `EXPORT_DIR_WINDOWS` on Windows | Where `.epub` files and `rss_exports/` are written. **Note:** the macOS/Linux fallback is a hardcoded owner-specific absolute path, not `exports/` — set this explicitly; see [#58](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/58) |
| `EXPORT_DIR_MAC` / `EXPORT_DIR_WINDOWS` | personal absolute paths | Fallbacks used when `EXPORT_DIR` is unset — see [#58](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/58) |
| `SHARED_STORAGE_PATH` | — | env-only: when set, RSS feed snapshots, `xml_exports`, and EPUB/rss exports move under `$SHARED_STORAGE_PATH/{rss-feeds,xml-exports,exports/rss_exports}` (used by `rss_watcher.py`, `data/export.py`) |
| `SERIES_SYNC_INLINE` | off | `1` runs series-page sync in-line instead of a thread (set in `poll.yml`) |
| `NU_HEADED` | off | `1` forces headed Chromium (set in `poll.yml`; needed on CI) |
| `POLL_ONLY_SLUG` | — | Workflow-dispatch input: process only this `novels_requests` slug, skip RSS |
| `POLL_RUN_BUDGET_S` | 1260 | Overall poller time budget |
| `RSS_TIME_BUDGET_S` | 300 | RSS phase budget within a poller run |
| `QUEUE_TIME_BUDGET_S` | 1200 | Queue phase budget |
| `DRAIN_ITEMS_PER_REQUEST` / `DRAIN_TIME_BUDGET_S` | — | Per-request drain slice inside a queue pass |
| `WORKER_RUN_BUDGET_S` | 3300 | Cloud Run worker budget (< 3600 s job timeout) |
| `WORKER_MAX_MONTHLY_RUNS` | 20 | Monthly cap on Cloud Run executions (`claim_worker_run` ledger in `novels_meta/worker_usage`) |
| `FIRESTORE_PROJECT` | `mw-novels` | Firestore project id |
| `GOOGLE_CLOUD_PROJECT`, `CLOUD_RUN_REGION`, `CLOUD_RUN_EXECUTION`, `WORKER_RUN_URL` | — | Worker/job metadata; the site links `WORKER_RUN_URL` to watch executions |
| `DB_HOST` `DB_PORT` `DB_NAME` `DB_USER` `DB_PASSWORD` | — | PostgreSQL path in `database_manager.py` — **incomplete**, see [08](08-known-limitations-and-enhancements.md) |
| `EXTRA_HTTP_HEADERS` | — | Parsed by settings but not used by the request paths — dead config, see [08](08-known-limitations-and-enhancements.md) |

## Secrets — where they live

| Location | What | Status |
|---|---|---|
| GitHub repo Secrets | `NU_RSS_FEED_URL`, `NU_COOKIES`, `FIREBASE_SERVICE_ACCOUNT_JSON` | The intended home; read by `poll.yml` |
| Root `config.py` | Local credentials/cookies | Gitignored — **do not commit** |
| `core/config.py` | Older duplicate of the above | Gitignored; not imported by the app — see [08](08-known-limitations-and-enhancements.md) |
| Firestore documents | SA-authenticated data | Public-read rules mean chapter text is world-readable — acceptable for this project, worth knowing |

Never paste real cookie/password values into docs, issues, or PRs. One
caveat in the other direction: the Flask `secret_key` in `web_ui.py`
(line 37) is a hardcoded placeholder, not a real secret — see
[#59](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/59).

## External services

| Service | Used for | Auth |
|---|---|---|
| NovelUpdates (`novelupdates.com`) | RSS feed, series pages, `/extnu/` release links | Cookies + optional login; behind Cloudflare |
| Translator-group hosting sites | Actual chapter text | None; guarded by politeness layer; some behind Cloudflare |
| wuxiaworld.eu, novelfull.net, novellunar.com | Mirror/backfill chapter fetches | None |
| Firestore (project `mw-novels`) | Cloud storage | SA OAuth token over REST API (`google-auth`) |
| GitHub Actions | Scheduled polling | Secrets above |
| Cloud Run (`novels-worker` job, `us-central1`) | On-demand queue processing | `run.invoker` granted to the site's pages-worker SA |
| morganwilkinson.com Novels app | Reads Firestore; triggers the worker via `WORKER_RUN_URL` | Cloudflare Access on the site's side |

## Deployment surfaces

- **Local**: `python start.py` — no infra needed.
- **Docker**: `Dockerfile` + `docker-compose.yml` (+ optional `nginx.conf`
  proxy). Runs local mode; `./data` volume holds the SQLite files.
- **GitHub Actions**: `.github/workflows/poll.yml` — every 30 min, Playwright
  container `v1.63.0-noble`, 25-minute timeout.
- **Cloud Run Job**: `tools/deploy_worker.sh` deploys `novels-worker`;
  executed on demand from the site, capped by `WORKER_MAX_MONTHLY_RUNS`.
- **Firebase**: `firebase.json` + `firestore.rules` — deploy rules with the
  Firebase CLI (`firebase deploy --only firestore:rules`).
