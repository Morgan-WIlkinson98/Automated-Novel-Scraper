# 04 — Core Modules and APIs

> **Who this is for:** beginner developers and non-technical readers.
> **Repository stamp:** base commit `ba8c7c0` · branch `docs/update-documentation-2026-10-11` · dated 2026-10-11 · no uncommitted changes when the docs were written.
> Back to [Documentation index](README.md) · Previous version: [archive/2026-10-10_api.md](archive/2026-10-10_api.md)

## Contents

- [How to read this page](#how-to-read-this-page)
- [Pipeline functions](#pipeline-functions)
- [Storage functions](#storage-functions)
- [Web UI HTTP endpoints](#web-ui-http-endpoints)

Links point at the source at base commit `ba8c7c0`.

## How to read this page

- **Signature** is what you call; **in** describes the arguments; **out**
  describes what you get back. Types are from the source signatures.
- "Raises" lists exceptions callers must expect. Functions not listed do the
  same shape of work as a listed sibling (e.g. Firestore mirrors of SQLite
  functions).

## Pipeline functions

### Entry points

| Function | In | Out | Notes |
|---|---|---|---|
| [`main.main()`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/main.py#L200) | — | never returns (loop) | Initializes storage, replays `data/xml_exports/` feed snapshots to rebuild the series catalog, starts `run_forever`. |
| [`main.handle_new_entry(entry, is_import=False)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/main.py#L68) | feedparser entry | — | The whole per-entry pipeline: catalogue series → resolve → extract → check → save → async series sync. |
| [`poller.main()`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/poller.py#L31) | env vars | `int` exit code | Requires `DB_TYPE=firestore`. One RSS pass + `process_request_queue`, writes `runs` doc. Exit `1` if any errors were collected. |
| [`poller.process_request_queue(errors, max_chapters=40, ...)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/poller.py#L176) | `errors` list to append to | mutates Firestore | Pass 1 promotes request docs into queues via `series_scraper`; Pass 2 works each queue with fair-share time slices; flushes progress every 60 s. |
| [`queue_worker.main()`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/queue_worker.py#L40) | env vars | `int` exit code | Firestore-only. `claim_worker_run` enforces `WORKER_MAX_MONTHLY_RUNS`; then calls `process_request_queue` under `WORKER_RUN_BUDGET_S`. |
| [`rss_watcher.poll_once(conn, on_new_entry, deadline=None, on_dead_entry=None)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/rss/rss_watcher.py#L351) | seen-entries conn, callbacks | count processed | One feed fetch; new GUIDs → `on_new_entry`; entries past retry cap → `on_dead_entry`. |
| [`rss_watcher.run_forever(on_new_entry)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/rss/rss_watcher.py#L426) | callback | never returns | Local loop: `poll_once` every `POLL_INTERVAL_SECONDS` (default 900). |
| [`import_nu_export.main()`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/core/import_nu_export.py#L118) | `--export`, `--db` args | prints import count | Manual CLI: imports a NU reading-list JSON export into `series_info`; defaults to newest `*.json` in `READING_LISTS_DIR`. Not called by `main.py`. |

### Fetching and extraction

| Function | In | Out | Notes |
|---|---|---|---|
| [`politeness.is_allowed(url)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/scraping/politeness.py#L46) | URL | `bool` | `robots.txt` check, cached per domain. **Fails open** when robots can't be fetched. |
| [`politeness.polite_get(url, timeout=15)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/scraping/politeness.py#L61) | URL | `requests.Response` or `None` | robots check + per-domain delay (`MIN_DELAY_SECONDS`, 5 s) before `GET`. |
| [`link_resolver.resolve_final_url(url, timeout=15)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/scraping/link_resolver.py#L40) | URL | final URL string | HEAD, then GET with cookies; plain-HTTP path. |
| [`link_resolver.resolve_final_url_with_browser_fallback(url, timeout=15, use_browser=True)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/scraping/link_resolver.py#L83) | URL | final URL string | Adds headed-Chromium fallback; NU `/extnu/` links go straight to the browser (they 403 plain requests). |
| [`generic_extractor.fetch_html(url)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/scraping/generic_extractor.py#L53) | URL | HTML str or `None` | Fetch through the politeness layer. |
| [`generic_extractor.quality_check(text, min_chars=500, min_paragraphs=3)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/scraping/generic_extractor.py#L136) | extracted text | `bool` | Thresholds from `MIN_CHARS`/`MIN_PARAGRAPHS`. |
| [`generic_extractor.extract_chapter(url, page=None)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/scraping/generic_extractor.py#L147) | URL, optional Playwright page | `ExtractionResult` | trafilatura → readability → rendered-HTML retry → site override. Result carries `text`, `title`, `method`, `success`. |

### Backfill queue helpers

| Function | In | Out | Notes |
|---|---|---|---|
| [`series_scraper` — series-page scrape](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/scraping/series_scraper.py) | series NU URL, browser page | synopsis + paginated release rows | Resumable via `scrapePage` cursor stored on the request doc. |
| [`alt_sources.fetch_chapter(series_name, num, caches, page=None)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/scraping/alt_sources.py#L34) | series slug, chapter number, per-site caches | extracted chapter or failure | Ordered chain **wuxiaworld.eu → novelfull.net → novellunar.com → NU link**. |
| [`firestore_store.enqueue_backfill(series_name, series_url, reason="")`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/data/firestore_store.py#L694) | series id + NU URL | `bool` | Writes a `novels_requests` doc; used by the site and by dead-entry auto-queue. |
| [`firestore_store.claim_worker_run(max_runs=None)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/data/firestore_store.py#L769) | monthly cap | `bool` allowed | Monthly run counter used by `queue_worker.py` to cap Cloud Run cost. |

## Storage functions

Two backends with matching shapes — `data/storage.py` (SQLite) and
`data/firestore_store.py` (Firestore REST). Callers pick via `DB_TYPE`.

| Function (SQLite sig; Firestore mirrors it) | In | Out |
|---|---|---|
| [`init_storage(path=None)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/data/storage.py#L58) | optional db path | connection/client | SQLite version creates tables and adds missing columns on open |
| [`save_chapter(conn, url, series, chapter_label, title, text, method, ...)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/data/storage.py#L106) | chapter fields | — | Insert-if-absent keyed on URL (sha256 doc id in Firestore) |
| [`save_series_info(conn, series, ...)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/data/storage.py#L200) | series metadata | — | synopsis, latest/release table, `groupsHealed` flag (Firestore) |
| [`heal_chapter_groups(conn, series, release_rows)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/data/storage.py#L154) | release table | count patched | backfills `group` on older chapters; capped at 400 in Firestore |
| [`is_new_entry(conn, guid)` / `mark_seen(conn, guid, link)` / `mark_failed(...)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/rss/rss_watcher.py#L58) | GUID/link | `bool` / — / retry count | dedup + failure bookkeeping in `seen_entries` |
| [`export.create_epub(series_name, chapters, output_dir=None)`](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/blob/ba8c7c0/data/export.py#L83) | series + chapter dicts | path to `.epub` | used by `export_all_to_epub`, `export_series_to_epub`, `export_selected_chapters_to_epub` |

## Web UI HTTP endpoints

`web_ui.py` serves pages (HTML) and `/api/*` endpoints (JSON). Base URL
locally: `http://localhost:6110`.

### Pages

| Route | Method | What it renders |
|---|---|---|
| `/` | GET | Library dashboard (`index.html`) |
| `/series` | GET | Series list |
| `/series/<name>` | GET | One series: chapters + release table |
| `/chapter/<path:url>` | GET | Reading view for a chapter |
| `/rss`, `/rss/view/<file>`, `/rss/raw/<file>` | GET | Saved RSS feed snapshots |
| `/export` | GET | Export page |
| `/settings` | GET | Settings editor |
| `/logs` | GET | Log viewer |
| `/download/<path:filename>` | GET | Download a generated `.epub` |

### API (JSON)

| Route | Method | In → Out |
|---|---|---|
| `/api/statistics` | GET | — → totals for the dashboard |
| `/api/series` | GET | — → series list |
| `/api/series/<name>/chapters` | GET | — → chapter list |
| `/api/series/<name>/url` | POST | `{url}` → sets the NU series URL |
| `/api/series/<name>/sync` | POST | — → `{job_id}`; polls [`/api/sync_status/<job_id>`] for progress |
| `/api/series/<name>/download` | POST | `{chapter_urls}` → `{job_id}`; status via [`/api/download_status/<job_id>`] |
| `/export/all`, `/export/series/<name>` | POST | — → generates `.epub`(s), returns download paths |
| `/api/export/series/<name>/chapters` | POST | `{chapter_urls}` → exports a selection |
| `/api/config` | GET / POST | settings dict → saved via `Settings.save_to_file` (see [08](08-known-limitations-and-enhancements.md) for what's exposed) |
| `/api/test-auth` | POST | — → checks NU credentials/cookies |
| `/api/fetch_rss` | POST | — → `{job_id}` for a manual fetch |
| `/api/load_xml_exports`, `/api/periodic_exports`, `/api/trigger_periodic_export` | GET/POST | reading-list import + RSS snapshot exports |
| `/api/scraper_status`, `/api/start_scraper`, `/api/stop_scraper`, `/api/stop` | GET/POST | start/stop the local scraper process |
| `/api/logs` | GET | — → recent log lines |

**Notable behaviors to know before calling these:**

- Sync/download endpoints are **async**: they return a `job_id` immediately;
  poll the matching `*_status` endpoint until `done`.
- `/api/stop_scraper` stops the scraper subprocess launched through the UI;
  it won't touch a `main.py` you started yourself in another shell.
- Chapter URLs double as ids — `/chapter/<path:url>` and
  `/api/series/<name>/download` both take the full stored URL.
