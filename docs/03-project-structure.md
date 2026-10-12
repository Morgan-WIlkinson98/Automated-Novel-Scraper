# 03 — Project Structure

> **Who this is for:** beginner developers and non-technical readers.
> **Repository stamp:** base commit `ba8c7c0` · branch `docs/update-documentation-2026-10-11` · dated 2026-10-11 · no uncommitted changes when the docs were written.
> Back to [Documentation index](README.md) · Previous version: [archive/2026-10-10_project-guide.md](archive/2026-10-10_project-guide.md)

## Contents

- [The map](#the-map)
- [Entry points (run these)](#entry-points-run-these)
- [The pipeline, folder by folder](#the-pipeline-folder-by-folder)
- [Web UI](#web-ui)
- [Data stores and file artifacts](#data-stores-and-file-artifacts)
- [Tooling and ops](#tooling-and-ops)
- [Governance and GitHub files](#governance-and-github-files)

## The map

```text
Automated-Novel-Scrapper/
├── start.py                # launches web_ui.py + main.py together
├── main.py                 # local continuous scraper (RSS loop)
├── poller.py               # cloud single-pass poller (GitHub Actions)
├── queue_worker.py         # Cloud Run Job: request-queue only
├── web_ui.py               # Flask UI + JSON API, port 6110
│
├── core/                   # config, DB access, imports, logging, utils
├── rss/                    # feed polling and seen-entry dedup
├── scraping/               # fetching, extraction, browser, mirrors
├── data/                   # storage backends + EPUB export
├── auth/                   # cookie/credential helper scripts
├── templates/              # Jinja2 HTML for web_ui.py
├── tools/                  # ops scripts (migration, deploy) + vendored NU list exporter
│
├── docs/                   # this documentation set
├── reading_lists/          # NU reading-list JSON exports (gitignored user data)
├── chapters.db  seen_entries.db   # local SQLite state (gitignored)
├── requirements.txt        # local/full install
├── requirements-poller.txt # minimal CI deps (pinned Playwright)
├── pyproject.toml          # project metadata + deps (no build backend needed)
├── Dockerfile  docker-compose.yml  nginx.conf   # containerized local run
├── firebase.json  .firebaserc  firestore.rules  # Firestore project config
└── .github/workflows/poll.yml                   # scheduled cloud poller
```

## Entry points (run these)

| File | Role | Started by |
|---|---|---|
| `start.py` | Convenience launcher: starts the web UI, waits ~2 s, starts `main.py`; both PIDs go to `pids.json`; Ctrl+C stops both. | you |
| `main.py` | Local scraper. Initializes storage, replays `data/xml_exports/` feed snapshots into the catalog, then runs the RSS watcher loop forever. (Reading-list import is a separate manual CLI: `core/import_nu_export.py`.) | `start.py` or you |
| `poller.py` | Cloud scraper. One RSS pass + one request-queue pass + run metadata, then exits. Refuses to run unless `DB_TYPE=firestore`. | GitHub Actions |
| `queue_worker.py` | Queue-only variant of the poller for the Cloud Run Job (`novels-worker`). Enforces `WORKER_MAX_MONTHLY_RUNS` (default 20) to cap cost. | Cloud Run trigger |
| `web_ui.py` | Flask app on port 6110 — library dashboard, series pages, RSS viewer, EPUB export, logs, settings. | `start.py`, Docker, or you |

## The pipeline, folder by folder

**`rss/`** — feed side.

| File | Purpose |
|---|---|
| `rss_watcher.py` | Polls the RSS feed (feedparser), dedups entries by GUID, calls back into `main.handle_new_entry` / `poller.process_entry` for each new one. Loops forever locally; `poller.py` drives a single pass. Tracks per-entry retry/failure counts. |

**`scraping/`** — the fetch side, in rough pipeline order.

| File | Purpose |
|---|---|
| `politeness.py` | Good-citizen layer: `robots.txt` check + per-domain rate limit (5 s default via `MIN_DELAY_SECONDS`). Fails open if `robots.txt` can't be fetched — see [08 — Known limitations](08-known-limitations-and-enhancements.md). |
| `link_resolver.py` | Turns a NU `/extnu/` redirect into the real hosting URL. HEAD → GET → headed-browser fallback; uses configured cookies/credentials. |
| `generic_extractor.py` | Text extraction ladder: trafilatura → readability-lxml → browser-rendered HTML; applies `MIN_CHARS`/`MIN_PARAGRAPHS` quality gates. |
| `browser.py` | Playwright helpers; shared headed-Chromium session for queue processing (one Cloudflare solve covers the run). |
| `site_overrides.py` | Per-domain CSS-selector overrides for sites the generic extractor mangles. Currently empty — the extension point exists. |
| `series_scraper.py` | Playwright scrape of a NU series page: synopsis + paginated release table (the release table drives backfill). |
| `alt_sources.py` | Mirror-chain orchestration: tries the mirror sites in order before the original NU link. |
| `wuxiaworld.py`, `novelfull.py`, `novellunar.py` | Per-site adapters for the three mirror sources. |

**`data/`** — where everything lands.

| File | Purpose |
|---|---|
| `storage.py` | SQLite backend: creates/migrates `chapters.db` tables (adds missing columns on open), stores chapters + series metadata. |
| `firestore_store.py` | Firestore REST backend: chapters, novels, seen entries, run/queue/request documents, service-account auth. |
| `export.py` | Bundles a series' chapters into an `.epub` (ebooklib) under `EXPORT_DIR`. |

**`core/`** — shared plumbing.

| File | Purpose |
|---|---|
| `settings.py` | Settings resolution: environment variables over `config.py` values over defaults. Single source of truth used by everything. |
| `config.example.py` | Template for the gitignored `config.py` (no real secrets in the repo). |
| `database.py`, `database_manager.py` | DB abstraction; `database_manager.py` carries a partial PostgreSQL path — see [08 — Known limitations](08-known-limitations-and-enhancements.md). |
| `import_nu_export.py` | CLI (`python -m core.import_nu_export`) that imports NovelUpdates reading-list JSON exports into `series_info`. Manual step — `main.py` does not run it. |
| `logging_config.py` | Log format/handlers shared by entry points. |
| `exceptions.py` | Shared exception types (e.g. politeness/robots violations). |
| `utils.py` | Small helpers (slugify, text cleaning). |

**`auth/`** — helper scripts for refreshing the NU session cookies
(`parse_curl_cookies.py`, `set_cookies.py`, `curl_parser.py`,
`test_auth.py`). Standalone utilities, not part of the pipeline — see
[08](08-known-limitations-and-enhancements.md) for the config-module mismatch
they currently have.

## Web UI

`web_ui.py` + `templates/`. One template per page:

| Template | Page |
|---|---|
| `base.html` | Shared layout/nav |
| `index.html` | Library dashboard |
| `series.html`, `series_detail.html` | Series list and per-series chapters/releases |
| `chapter.html` | Reading view for one chapter |
| `rss.html`, `rss_view.html` | RSS entry viewer |
| `export.html` | EPUB export |
| `settings.html` | Settings editor |
| `logs.html` | Live log tail |
| `error.html` | Error page |

## Data stores and file artifacts

| Path | Mode | Contents |
|---|---|---|
| `chapters.db` | local | SQLite — chapter text + series metadata (gitignored) |
| `seen_entries.db` | local | SQLite — processed RSS GUIDs (gitignored) |
| Firestore `mw-novels` | cloud | `novels`, `novels/{slug}/chapters`, `seen_entries`, `runs`, `queue`, `novels_requests` documents |
| `reading_lists/` | local | NU reading-list JSON exports (`READING_LISTS_DIR`, default `reading_lists`); imported manually via `python -m core.import_nu_export` (gitignored) |
| `data/xml_exports/` | local | Archived RSS-feed XML snapshots; replayed by `main.py` at startup to rebuild the series catalog (gitignored) |
| `rss_feeds/` / `EXPORT_DIR/rss_exports/` | local | Feed snapshots and periodic RSS exports written by `rss_watcher.py` (gitignored) |
| `EXPORT_DIR` | both | Generated `.epub` files — default is platform-specific, see [05](05-configuration-and-services.md) and [#58](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/58) |
| `pids.json` / `scraper_pid.json` | local | PIDs written by `start.py` / the UI-launched scraper (gitignored) |
| `logs/` | Docker | Log files surfaced in the UI Logs page |

## Tooling and ops

| File | Purpose |
|---|---|
| `tools/import_sqlite.py` | One-way migration: local SQLite → Firestore. Insert-if-absent, safe to re-run. |
| `tools/deploy_worker.sh` | Builds + deploys the `novels-worker` Cloud Run Job (REST API + docker, no gcloud) and wires invoke permissions. |
| `tools/nu-reading-list-exporter/` | Vendored Chrome extension (upstream snapshot, commit `817c19d`) that exports NU reading lists to `novelupdates-*.json` — the files `core/import_nu_export.py` consumes. |
| `Dockerfile` | Local-mode image: Python + Playwright/Chromium + xvfb + the app. |
| `docker-compose.yml` | Runs the image with `./data` volume and port 6110 published. |
| `nginx.conf` | Optional reverse proxy config for the UI. |
| `firebase.json`, `.firebaserc` | Firebase CLI config pointing at project `mw-novels`. |
| `firestore.rules` | Firestore security rules: public read, no client writes (the SA bypasses them). |
| `requirements-poller.txt` | Minimal dep set for `poll.yml`; `playwright==1.63.0` pinned to match the container image tag. |

## Governance and GitHub files

| File | Purpose |
|---|---|
| `AGENTS.md` | Rules for automated contributors (branch/issue/PR workflow, secrets discipline, package vetting). |
| `.devin/rules/REPOSITORY_RULES.md` | The detailed rule set `AGENTS.md` points at. |
| `CONTRIBUTING.md` | Human-facing contribution guide. |
| `.github/pull_request_template.md` | PR template (summary/why/approach/how-to-test/checklist). |
| `.github/ISSUE_TEMPLATE/` | Bug report + feature request templates. |
| `.github/workflows/poll.yml` | The scheduled cloud poller (the only CI in the repo — there is no test/build workflow). |
