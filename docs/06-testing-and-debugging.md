# 06 — Testing and Debugging

> **Who this is for:** beginner developers and non-technical readers.
> **Repository stamp:** base commit `ba8c7c0` · branch `docs/update-documentation-2026-10-11` · dated 2026-10-11 · no uncommitted changes when the docs were written.
> Back to [Documentation index](README.md) · Previous version: [archive/2026-10-10_development.md](archive/2026-10-10_development.md)

## Contents

- [What "tests" exist here](#what-tests-exist-here)
- [Fast checks to run after a change](#fast-checks-to-run-after-a-change)
- [Manual verification paths](#manual-verification-paths)
- [Common problems](#common-problems)

## What "tests" exist here

Honest answer: **there is no test suite.** No `tests/` directory, no pytest
config, no CI build/test workflow — the only GitHub workflow is the live
poller itself. `auth/test_auth.py` is a manual credentials check script, not
a unit test. Changes are verified by syntax checks, import smoke tests, and
running the real pipeline.

## Fast checks to run after a change

```bash
# 1. Syntax — catches the f-string backslash trap the repo rules warn about
python -m compileall . -q

# 2. Import smoke — entry points must import cleanly
python -c "import main, web_ui, poller, queue_worker"

# 3. UI boots (Ctrl+C to stop; needs a venv with requirements.txt installed)
python web_ui.py   # then open http://localhost:6110
```

All three were verified working at base commit `ba8c7c0` (Python 3.12;
`compileall` + `ast.parse` re-verified 2026-10-11).

## Manual verification paths

- **RSS pipeline without the loop**: run one pass —
  `python -c "import rss.rss_watcher as w; w.poll_once(w.init_db(), print)"`
  exercises fetch + dedup with real feed data. *Not verified by running —
  hits the live feed.*
- **One entry end-to-end**: watch the dashboard while `main.py` runs; a new
  release should appear on the series page within a poll cycle.
- **Dry-run a poller pass locally**: `poller.py` exits early unless
  `DB_TYPE=firestore` + `FIREBASE_SERVICE_ACCOUNT_JSON` are set — you can
  confirm the guard fires without credentials.
- **Logs**: the UI's `/logs` page tails the log; locally check stdout of
  `main.py`/`web_ui.py`, in Docker `docker-compose logs -f`, in cloud the
  GitHub Actions step output and `runs` Firestore documents.

## Common problems

| Symptom | Likely cause | Fix |
|---|---|---|
| Every NU fetch 403s / "Just a moment…" | `cf_clearance` / `wordpress_logged_in_*` cookies expired | Re-copy cookies into `config.py`/`NU_COOKIES`; re-copy `USER_AGENT` from the same browser |
| Series appears but no chapters | Extraction failing quality gates | Check logs for which method failed; add a `site_overrides.py` entry for that domain |
| Poller run exits immediately | `DB_TYPE`/`FIREBASE_SERVICE_ACCOUNT_JSON` unset | Set env vars per [05](05-configuration-and-services.md) |
| "Failed entries" accumulating | Dead release links | Expected — after 3 retries the entry is dead-queued and a backfill request is auto-created |
| UI Settings save fails | `config.py` unwritable / permission | Check file permissions; `save_to_file` needs write access to repo root |
| Selected-chapter download skips the site-override path | `urlparse` NameError in `web_ui.py` (line ~631, inside the `/api/series/<name>/download` worker) | Known bug [#49](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/49) — the NameError is caught by the broad `except`, so the chapter is skipped rather than crashing the job |
| `docker-compose up` then `localhost`/`localhost:6110` gives 404/refused | nginx only serves `Host: novelscraper.local`; app has no published port | Add `127.0.0.1 novelscraper.local` to `/etc/hosts`, browse `http://novelscraper.local/` — see [#61](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/61) |
| EPUB export lands in a strange absolute path (or fails) | `EXPORT_DIR` unset → falls back to a hardcoded personal path on macOS/Linux | Set `EXPORT_DIR` in `config.py`/env — see [#58](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/58) |
| Browser crashes mid-run | Shared Chromium session died | Automatic — session rebuilds up to 3×, then items fall back to standalone resolver |
| Backfill stalls on huge series | Release-table pagination | Expected — the `scrapePage` cursor resumes on the next run |
