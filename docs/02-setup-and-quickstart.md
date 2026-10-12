# 02 — Setup and Quickstart

> **Who this is for:** beginner developers and non-technical readers.
> **Repository stamp:** base commit `217431f` · branch `feature/update-documentation-2026-10-10` · dated 2026-10-10 · no uncommitted changes when the docs were written.
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

**Expected output** (verified by reading `start.py`/`main.py`; not re-run for
these docs):

```
[START] Launched web_ui.py (pid NNNNN)
[START] Launched main.py (pid NNNNN)
[WATCHER] Monitoring ...
[INIT] Loading XML exports from data/reading_lists ...
Starting RSS watcher (SQLite storage, check every 900s)
```

Then open **http://localhost:6110** — you'll see the library dashboard
(empty until the first poll runs). Chapters land in `chapters.db`, processed
feed entries in `seen_entries.db`.

**Import your existing reading list (optional):** use the bundled Chrome
extension in [`tools/nu-reading-list-exporter/`](../tools/nu-reading-list-exporter/)
(load unpacked, then click its icon on any novelupdates.com page while logged
in) to download a `novelupdates-*.json` export. Drop it in
`data/reading_lists/`, and `main.py` imports it automatically on startup
(picks the newest file if several exist). The My List page then knows which
chapter you're currently on.

## Run it with Docker

```bash
docker-compose up -d --build
```

The compose file builds the image, mounts `./data` as a volume (your
`chapters.db`, `seen_entries.db`, exports, and `reading_lists/` all live
there), and publishes the UI on **http://localhost:6110**. `config.py` is
baked into the image at build time — rebuild after changing it, or prefer env
vars. Logs: `docker-compose logs -f` (also visible in the UI's Logs page,
which tails the container's `/app/logs` mount).

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
   deploys the `novels-backfill` Cloud Run Job in `us-central1` and gives the
   site's pages-worker SA `run.invoker`. Requires `gcloud` CLI authenticated
   as a project owner. *Not verified by running.*
6. **Migrate existing data (optional)** — `python tools/import_sqlite.py`
   copies local `chapters.db`/`seen_entries.db` into Firestore
   (insert-if-absent, safe to re-run).

## Where to go next

- [03 — Project structure](03-project-structure.md) — where everything lives.
- [05 — Configuration](05-configuration-and-services.md) — every env var and
  what it controls.
- [06 — Testing and debugging](06-testing-and-debugging.md) — when the first
  poll finds nothing or a page refuses to yield its text.
