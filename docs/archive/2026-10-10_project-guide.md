---
ARCHIVED 2026-10-10 — originally at docs/project-guide.md.
Reason: broad pre-cloud overview superseded by the new docs set; useful detail folded into the replacements.
Replaced by: [../README.md](../README.md) and [../01-overview-and-architecture.md](../01-overview-and-architecture.md)
---

# Novel Scraper Project Guide

This guide is a one-stop reference for the project: what it does, how to install and run it, how the different pieces fit together, and how releases and development are managed.

## What the project does

Novel Scraper watches the NovelUpdates RSS feed for new chapter releases, fetches the actual chapter text from the hosting site, and stores it locally. You can browse, search, and export the stored chapters through a Flask web UI.

High-level flow:

```
NovelUpdates RSS  →  new chapter link  →  link resolver  →  chapter extractor
                                                            ↓
                                          store in SQLite  →  web UI
```

The pipeline is deliberately polite: it respects `robots.txt`, enforces a minimum delay between requests to the same domain, and uses a realistic User-Agent string.

## Main features

- **RSS watcher**: polls NovelUpdates (or any configured RSS feed) and only processes unseen entries.
- **Link resolution**: follows redirects from NovelUpdates to the final hosting page.
- **Chapter extraction**: first tries `trafilatura`, then `readability-lxml`, then a site-specific CSS override.
- **Cloudflare handling**: Playwright can be used as a fallback when a hosting site is behind Cloudflare.
- **Storage**: two SQLite databases:
  - `chapters.db` — stored chapter text and metadata.
  - `seen_entries.db` — deduplication for RSS entries.
- **Web UI**: browse series, read chapters, export EPUBs, and monitor scraper status.
- **NovelUpdates import**: import a NovelUpdates JSON reading-list export so the UI can show current/latest chapter status.
- **EPUB export**: generate EPUB files for a series.
- **Search**: filter the series list by title.

## Installation

### From source (recommended for development)

```bash
# Clone
git clone https://github.com/Morgan-Wilkinson/Automated-Novel-Scraper.git
cd Automated-Novel-Scraper

# Create and activate a virtual environment (optional but recommended)
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# or .venv\Scripts\activate  # Windows

# Install
pip install -r requirements.txt
# or install the package in editable mode
pip install -e .
```

### From PyPI / pip

If a release is published:

```bash
pip install novel-scraper
```

## Configuration

Settings are loaded in this order of priority:

1. Hard-coded defaults in `core/settings.py`.
2. `config.py` in the project root (if present).
3. Environment variables.

Create `config.py` for credentials and site-specific tweaks. Example:

```python
RSS_FEED_URL = "https://rssnovelupdates.com/rss.php?uid=..."
NOVELUPDATES_USERNAME = "your_username"
NOVELUPDATES_PASSWORD = "your_password"

POLL_INTERVAL_SECONDS = 15 * 60  # 15 minutes
MIN_DELAY_SECONDS = 5            # per-domain minimum delay
```

`config.py` is gitignored so your credentials are never committed.

## Running the project

The `pyproject.toml` installs two console scripts:

| Command                | What it does                                |
|------------------------|---------------------------------------------|
| `novel-scraper`        | Runs the RSS watcher / scraper continuously |
| `novel-scraper-web`    | Starts the Flask web UI on `localhost:6110` |

You can also run the scripts directly:

```bash
python main.py      # scraper
python web_ui.py    # web UI
```

## Importing a NovelUpdates reading list

NovelUpdates can export your reading lists as JSON. Drop the JSON file into `reading_lists/`. Run `core/import_nu_export.py` or use the relevant web UI path. The importer creates/updates `series_info` records with:

- `current_chapter_label` and `current_chapter_link`
- `latest_chapter_label` and `latest_chapter_link`
- `reading_list_name`
- `imported_at`

These values are shown on the series list and detail pages.

## Project layout

```
Automated-Novel-Scraper/
├── .github/workflows/poll.yml     # Scheduled NovelUpdates poller
├── auth/                          # Authentication utilities
├── core/                          # Settings, logging, utils, NU import
├── data/                          # Storage and export helpers
├── docs/                          # Additional documentation
├── rss/                           # RSS polling and deduplication
├── scraping/                      # Link resolution, extraction, overrides
├── templates/                     # Flask/Jinja2 templates
├── main.py                        # Scraper entry point
├── web_ui.py                      # Flask application
├── start.py                       # Helper to launch both scraper + UI
├── pyproject.toml                 # Package definition and console scripts
├── requirements.txt               # Python dependencies
└── config.py                      # Created locally; holds credentials
```

## Git workflow

This repo uses a feature-branch workflow.

1. Create a feature branch from `main`.
2. Make your changes.
3. Open a Pull Request to `main`.
4. Do **not** push directly to `main` or `dev`.

The `dev` branch is used for pre-release testing.

## Releases and versioning

Packaged desktop releases (`NovelScraper.dmg` / `NovelScraper.exe`) have been retired — the app is hosted at morganwilkinson.com and no longer ships installable builds. The `release.yml` workflow was removed; the only GitHub Actions workflow is the scheduled `poll.yml` poller.

## Troubleshooting

### Cloudflare keeps blocking a series page

The scraper now returns a blocked marker instead of crashing. Cloudflare-protected series will be skipped and logged. You can refresh the browser manually to pass the challenge, or use Playwright if the site requires JavaScript.

### Generic extraction is failing for a specific host

Add a site override in `scraping/site_overrides.py`:

```python
SITE_OVERRIDES = {
    "example.com": {
        "content_selector": "div.chapter-content",
        "remove_selectors": [".ad", ".comments"],
    },
}
```

## Logs and runtime data

| Item                         | Path                       |
|------------------------------|----------------------------|
| Log file                     | `logs/app.log`             |
| Chapter database             | `chapters.db`              |
| Seen-entries database        | `seen_entries.db`          |
| EPUB exports                 | `exports/` or `EXPORT_DIR` |
| Reading list JSON imports    | `reading_lists/`           |
