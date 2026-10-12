# 02 — Setup and Quickstart

> **Who this is for:** beginner developers and non-technical readers.
> **Repository stamp:** base commit `ba8c7c0` · branch `docs/update-documentation-2026-10-11` · dated 2026-10-11 · no uncommitted changes when the docs were written.
> Back to [Documentation index](README.md) · Previous version: [archive/2026-10-10_index.md](archive/2026-10-10_index.md)

## Contents

- [Prerequisites](#prerequisites)
- [Clone and install](#clone-and-install)
- [Create your config](#create-your-config)
- [Run it locally](#run-it-locally)
- [Run it with Docker](#run-it-with-docker)
- [Run it in the cloud](#run-it-in-the-cloud)
- [Where to go next](#where-to-go-next)

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | ≥ 3.10 (tested on 3.12) | `pyproject.toml` requires `>=3.10` |
| pip / uv | latest | `requirements.txt` is a flat list; `pyproject.toml` has the same deps |
| Chromium | via Playwright | `playwright install chromium` — ~150 MB download |
| xvfb | any | **Linux/CI only**, needed because NU fetches run a *headed* browser |
| Docker + Compose | any | optional, only for the Docker route |

No other build tools, runtimes, or package managers are needed. There is no
Node, no compiled extension, no codegen step.

## Clone and install

```bash
git clone https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper.git
cd Automated-Novel-Scraper
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

On Linux also install `xvfb` (`sudo apt-get install xvfb`) — the headed browser
needs a display. On macOS/Windows it isn't needed because a real display
exists. *Not verified by running: a fresh venv install was not performed for
these docs; the import smoke test used the existing environment.*

## Create your config

The app reads settings from environment variables first, then from a root
`config.py` file (which is gitignored — see
[05 — Configuration](05-configuration-and-services.md) for the full picture).

Create `config.py` in the repo root:

```python
# NovelUpdates credentials — used for NU RSS auth, series-page sync, and extnu link resolution.
RSS_FEED_URL = "https://www.novelupdates.com/rss.php?uid=<your-uid>&unq=<your-key>"  # your private feed URL
USER_AGENT = "Mozilla/5.0 ..."  # match the browser you copied cookies from
NOVELUPDATES_USERNAME = "your-nu-username"
NOVELUPDATES_PASSWORD = "your-nu-password"
NOVELUPDATES_COOKIES = {
    "wordpress_logged_in_xxxxxxxxxxxx": "your-user%xxxxx",  # session cookie from browser devtools
    "cf_clearance": "xxxxx",                                 # Cloudflare clearance cookie
}
```

**How to get these values (step by step):**

1. Log in to novelupdates.com in a real browser.
2. Go to **User Settings → RSS** — that page shows your private feed URL; copy
   it into `RSS_FEED_URL`.
3. Open devtools → Application/Storage → Cookies → copy `wordpress_logged_in_*`
   and `cf_clearance` into `NOVELUPDATES_COOKIES`. Copy the browser's
   `User-Agent` header (Network tab, any request) into `USER_AGENT`.
4. Cookies expire — when NU fetches start failing, repeat step 3.

Equivalent environment variables work too (`NOVELUPDATES_COOKIES` accepts a
JSON string). **Never commit this file** — it contains live credentials.

## Run it locally

```bash
python start.py
```

`start.py` launches `web_ui.py` first, waits ~2 s, then launches `main.py`.
Process IDs land in `pids.json`; Ctrl+C stops both cleanly. To run just one
piece: `python web_ui.py` (UI only) or `python main.py` (scraper only).

**Expected output** (verified by reading `start.py`/`main.py`/`rss_watcher.py`;
not re-run for these docs):

```
Starting Novel Scraper
Starting web UI on http://localhost:6110
Started web_ui.py (PID: NNNNN)
Starting scraper
Started main.py (PID: NNNNN)
Starting novel scraper
Database initialized
Loading XML exports from data/xml_exports
Starting RSS watcher
```

Then open **http://localhost:6110** — you'll see the library dashboard
(empty until the first poll runs). Chapters land in `chapters.db`, processed
feed entries in `seen_entries.db`.

**What `main.py` loads at startup:** archived RSS-feed XML snapshots in
`data/xml_exports/` (files the scraper itself writes on each poll) are
replayed to rebuild the series catalog. This is a different thing from the
reading-list import below.

**Import your existing reading list (optional, manual step):** use the
bundled Chrome extension in
[`tools/nu-reading-list-exporter/`](../tools/nu-reading-list-exporter/)
(load unpacked, then click its icon on any novelupdates.com page while logged
in) to download a `novelupdates-*.json` export. Move that file into
`reading_lists/` (repo root — gitignored; that is the default
`READING_LISTS_DIR`), then run the importer once:

```bash
python -m core.import_nu_export                # imports newest *.json in reading_lists/
python -m core.import_nu_export --export path/to/file.json   # or a specific file
```

Nothing imports these files automatically — `main.py` does not call the
importer; run the command after each new export. The My List page then knows
which chapter you're currently on.

## Run it with Docker

```bash
docker-compose up -d --build
```

The compose file runs two containers: the app (`python start.py`, no
published port) and an `nginx` proxy that publishes **port 80** and forwards
to the app. `./data` is mounted into the app container (your `chapters.db`,
`seen_entries.db`, and exports live there). `config.py` is **excluded from
the image** by `.dockerignore`, but compose mounts `./config.py` read-only
into `/app/config.py` when it exists — edit that file (or the commented env
vars in `environment:`) to configure the container.

**Reaching the UI:** nginx only serves the app for `Host:
novelscraper.local` (every other Host gets a 404 from the default server in
`nginx.conf`). Add `127.0.0.1 novelscraper.local` to `/etc/hosts`, then open
**http://novelscraper.local/** — *not* localhost:6110. See
[#61](https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper/issues/61)
for why this trips up a first run. Logs: `docker-compose logs -f` (also
visible in the UI's Logs page, which tails the container's `/app/logs`
mount).

*Not verified by running: the image was not built for these docs.*

## Run it in the cloud

The cloud mode targets the owner's Firebase project (`mw-novels`). Adapting it
to your own project works, but every piece below needs setup:

1. **Firebase project** — create one, enable Firestore, deploy the security
   rules in `firestore.rules` (`firebase deploy --only firestore:rules` —
   *not verified by running*).
2. **Service account** — create a service account with Firestore access and
   download its JSON key. This is the *only* credential the cloud pipeline
   needs for the database.
3. **GitHub Actions secrets** — in repo Settings → Secrets and variables →
   Actions, add exactly three secrets: `NU_RSS_FEED_URL` (the private feed
   URL), `NU_COOKIES` (the cookie dict as a JSON string), and
   `FIREBASE_SERVICE_ACCOUNT_JSON` (the whole key file as one string). The
   workflow maps them onto the app's env names. `FIRESTORE_PROJECT` is not a
   secret — it defaults to `mw-novels` in `poller.py`; export it only if your
   project id differs.
4. **The workflow** — `.github/workflows/poll.yml` already does the rest:
   runs every 30 minutes (cron `7,37 * * * *`) plus manual dispatch with an
   optional "process only this request slug" input. It runs inside the
   official Playwright container image pinned to `v1.63.0-noble` (matching
   `requirements-poller.txt`'s playwright pin), then runs
   `xvfb-run -a python3 poller.py` with `DB_TYPE=firestore` and
   `NU_HEADED=1`.
5. **On-demand worker (optional)** — `tools/deploy_worker.sh` builds and
   deploys the `novels-worker` Cloud Run Job in `us-central1` (2 vCPU / 2 GiB,
   3600 s timeout, `xvfb-run -a python queue_worker.py`). No `gcloud` CLI
   needed — the script mints an access token from the service-account JSON
   and talks to the GCP REST API directly; it does need `docker` (buildx)
   plus `FIREBASE_SERVICE_ACCOUNT_JSON` in the environment, and the SA needs
   the roles listed in the script's header comment. *Not verified by running.*
6. **Migrate existing data (optional)** — `python tools/import_sqlite.py`
   copies local `chapters.db`/`seen_entries.db` into Firestore
   (insert-if-absent, safe to re-run).

## Where to go next

- [03 — Project structure](03-project-structure.md) — where everything lives.
- [05 — Configuration](05-configuration-and-services.md) — every env var and
  what it controls.
- [06 — Testing and debugging](06-testing-and-debugging.md) — when the first
  poll finds nothing or a page refuses to yield its text.
