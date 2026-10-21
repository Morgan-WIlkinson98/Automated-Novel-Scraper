# 08 — Known Limitations and Enhancements

> **Who this is for:** beginner developers and non-technical readers.
> **Repository stamp:** base commit `ba8c7c0` · branch `docs/update-documentation-2026-10-11` · dated 2026-10-11 · no uncommitted changes when the docs were written.
> Back to [Documentation index](README.md)

## Contents

- [Known limitations](#known-limitations)
- [Tracked bugs (filed during this documentation pass)](#tracked-bugs-filed-during-this-documentation-pass)
- [Enhancement ideas](#enhancement-ideas)

## Known limitations

Design-level constraints — things that are intentional or hard to remove:

- **Personal scale only.** Single feed, single reader's library. There is no
  multi-user concept anywhere in the data model.
- **Cookies expire.** NU fetches depend on `wordpress_logged_in_*` and
  `cf_clearance` cookies copied from a real browser. When they lapse, NU
  requests fail until refreshed — there is no automated re-login.
- **Cloudflare is probabilistic.** The headed-browser approach usually clears
  NU's challenge but not always; items that fail mid-queue requeue rather than
  die, so a bad window delays rather than loses work.
- **Extraction is heuristic.** Quality gates (`MIN_CHARS`/`MIN_PARAGRAPHS`)
  reject thin pages rather than fix them; unusual site layouts need a manual
  `site_overrides.py` entry.
- **Politeness fails open.** If `robots.txt` can't be fetched, the layer
  allows the request — deliberate (sites with flaky robots endpoints would
  otherwise block everything) but worth knowing. `robots.txt` is fetched
  with the scraper's own UA: Cloudflare fronts answer urllib's default
  `Python-urllib` UA with a 403, which `robotparser` reads as
  `disallow_all` — a false total block, not the file's rules (#65).
- **Auto-pause needs a human.** Two circuit breakers park work rather
  than grind it: a request pauses after 5 consecutive same-signature
  failures, and the service pauses after 3 consecutive failed runs.
  Neither self-heals — resuming is a deliberate click (re-request the
  backfill; clear `novels_meta/state.paused` from the site admin).
- **No test suite.** Verification is manual; see
  [06 — Testing and debugging](06-testing-and-debugging.md).
- **Firestore public read.** `firestore.rules` allows unauthenticated reads of
  the whole library — fine for personal chapter text, by design, but it means
  anything stored there is world-readable.
- **AGENTS.md required-reads `.devin/rules/REPOSITORY_RULES.md`** — the
  detailed rules live there, not in AGENTS.md itself.

## Tracked bugs (filed during documentation passes)

Real problems found while verifying the docs — filed as GitHub issues rather
than fixed (these passes do not change source code). All still open as of
2026-10-11.

Filed in the 2026-10-10 pass:

| Issue | Problem |
|---|---|
| [#49](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/49) | `web_ui.py:631` uses `urlparse` without importing it — NameError on the `/api/series/<name>/download` fallback path (caught by the broad `except`, so the chapter is skipped) |
| [#50](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/50) | `auth/` helpers import `core.config` — a stale credentials duplicate the app never reads (app uses root `config.py`) |
| [#51](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/51) | `GET /api/config` returns session cookies and the private feed URL — `hide_secrets` only masks the password; UI binds `0.0.0.0` |
| [#52](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/52) | `EXTRA_HTTP_HEADERS` is configurable but no request path sends it; `MIN_DELAY_SECONDS`, `MIN_CHARS`, `MIN_PARAGRAPHS` are likewise settable but unread — dead config |
| [#53](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/53) | `DB_TYPE=postgresql` is dead code — SQLite `?` placeholders throughout, `conn.row_factory` on psycopg2, no schema file, `psycopg2-binary` missing from `pyproject.toml` |

Filed in the 2026-10-11 refresh:

| Issue | Problem |
|---|---|
| [#58](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/58) | `EXPORT_DIR` falls back to a hardcoded personal path (`EXPORT_DIR_MAC`/`EXPORT_DIR_WINDOWS` in `core/settings.py`) on every non-Windows OS — wrong default for anyone else and a personal path committed to the repo |
| [#59](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/59) | Flask `app.secret_key` is a hardcoded placeholder string in `web_ui.py` — session cookies would be forgeable; unused today, unsafe default |
| [#60](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/60) | Vendored `nu-reading-list-exporter` extension requests `host_permissions: ["*://*/"]` but only ever runs on `www.novelupdates.com` — over-broad permission |
| [#61](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/61) | Docker route unreachable as documented — nginx only serves `Host: novelscraper.local` (default server 404s everything else) and the app container publishes no port |

Separately, this refresh corrected stale doc claims rather than filing issues
for them: the NU reading-list import is a manual CLI step into
`reading_lists/` (not auto-imported from `data/reading_lists/` by `main.py`),
`main.py`'s startup replay is `data/xml_exports/` feed snapshots, and the
Cloud Run job is `novels-worker`.

## Enhancement ideas

Not bugs — plausible next improvements (not yet scoped or scheduled):

- **Cookie refresh automation** — the `auth/` scripts parse a pasted curl
  command into config; automating login would remove the biggest recurring
  manual step.
- **A real test suite** — even a thin layer over `quality_check`,
  `heal_chapter_groups`, and the settings precedence rules would catch
  regressions like #49.
- **Per-domain settings** — `MIN_DELAY_SECONDS` is global; some mirror sites
  could go faster, NU probably shouldn't.
- **`site_overrides.py` contributions** — the hook exists and is empty;
  per-site selectors for frequently-failing hosts would reduce browser
  renders.
- **Health endpoint for the UI** — `/api/scraper_status` exists for the local
  process; a Firestore-side "last successful run" check would help the site
  surface a stalled poller.
