# AI Novel Web Scraper

An end-to-end pipeline for automatically watching NovelUpdates' RSS feed, extracting chapter text from hosting sites, and storing the results — all while being a polite, rate-limited client.

## Overview

This project implements a complete scraping pipeline that:

1. **Watches NovelUpdates RSS feed** for new chapter releases
2. **Resolves links** to their final hosting URLs
3. **Extracts chapter text** using generic algorithms (trafilatura + readability-lxml)
4. **Falls back to site-specific overrides** when generic extraction fails
5. **Stores chapters** in SQLite with metadata
6. **Respects politeness** with robots.txt checking, rate limiting, and proper User-Agent

## Architecture

```
RSS feed → Link resolution → Generic extractor → (fallback: site override) → Clean & store
                                                        ↑
                                              Politeness layer wraps every HTTP call
```

## Project Structure

```
novel_scraper/
├── rss_watcher.py          # RSS feed polling and deduplication
├── link_resolver.py        # URL redirect resolution
├── generic_extractor.py    # Generic text extraction (trafilatura + readability)
├── site_overrides.py       # Site-specific CSS selector overrides
├── storage.py              # SQLite chapter storage
├── politeness.py           # Rate limiting and robots.txt compliance
├── main.py                 # Orchestration of all components
├── requirements.txt        # Python dependencies
├── seen_entries.db         # Created at runtime (RSS deduplication)
└── chapters.db             # Created at runtime (chapter storage)
```

## Documentation

For detailed documentation, see:

- **[Architecture](docs/architecture.md)** - System architecture, component details, and design decisions
- **[Development Guide](docs/development.md)** - Development setup, workflow, testing, and debugging
- **[Deployment Guide](docs/deployment.md)** - Deployment instructions for various environments
- **[API Documentation](docs/api.md)** - Complete API reference for all modules
- **[Contributing](CONTRIBUTING.md)** - Contribution guidelines and coding standards
- **[Project Guide](docs/project-guide.md)** - End-to-end overview, installation, packaged desktop releases, and workflow

## Installation

### Docker (Recommended)

The easiest way to run this project is with Docker using an nginx reverse proxy:

```bash
# Build and start with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the service
docker-compose down
```

**Setup custom hostname:**

Add an entry to your hosts file to access the service via http://novelscraper.local:

**Windows (as Administrator):**
```bash
echo 127.0.0.1 novelscraper.local >> C:\Windows\System32\drivers\etc\hosts
```

**Linux/Mac:**
```bash
echo "127.0.0.1 novelscraper.local" | sudo tee -a /etc/hosts
```

Then access the service at http://novelscraper.local

**Architecture:**
- nginx reverse proxy listens on port 80
- Routes traffic to the novel scraper container based on hostname
- Easy to add more web apps later by adding new server blocks to nginx.conf

**Adding more web apps:**
To add another web app, edit `nginx.conf` and add a new server block:

```nginx
server {
    listen 80;
    server_name yourapp.local;

    location / {
        proxy_pass http://yourapp:port;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Then add the corresponding entry to your hosts file and docker-compose.yml.

Databases are persisted in the `./data` directory. If you need to configure authentication, create a `config.py` file and it will be automatically mounted.

### Manual Installation

Install dependencies:

```bash
pip install -r requirements.txt
```

Dependencies:
- `feedparser` - RSS feed parsing
- `requests` - HTTP client
- `trafilatura` - Primary text extraction library
- `readability-lxml` - Fallback extraction library
- `beautifulsoup4` - Site override parsing
- `lxml` - XML/HTML processing
- `ebooklib` - EPUB generation
- `flask` - Web UI

## Configuration

### Authentication

NovelUpdates RSS feed may require authentication. Create a `config.py` file:

```python
# config.py
RSS_FEED_URL = "https://www.novelupdates.com/rss/"

# Option 1: Username/Password authentication
NOVELUPDATES_USERNAME = "your_username"
NOVELUPDATES_PASSWORD = "your_password"

# Option 2: Cookie authentication (if you have session cookies)
NOVELUPDATES_COOKIES = {
    "session_id": "your_session_cookie",
}

# Polling interval (seconds)
POLL_INTERVAL_SECONDS = 15 * 60  # 15 minutes
```

**Important:** `config.py` is excluded from git to protect your credentials. Create it locally and never commit it.

If no authentication is needed, the scraper will work without `config.py` (though NovelUpdates may return empty results).

## Usage

### Running the Full Pipeline

```bash
python main.py
```

This will:
- Poll NovelUpdates RSS every 15 minutes
- Process new chapter releases
- Extract and store chapters
- Continue running indefinitely

### Web UI

A web interface is available to browse chapters, view statistics, and export to EPUB:

```bash
python web_ui.py
```

Then open http://localhost:6110 in your browser.

**Web UI Features:**
- Dashboard with statistics
- Browse all series and chapters
- Read chapters online
- Export to EPUB format
- REST API endpoints

### Export to EPUB

Export all chapters to EPUB format:

```bash
python export.py
```

Or use the web UI to export specific series.

### Individual Components

#### RSS Watcher

```python
from rss_watcher import init_db, poll_once

def on_new_entry(entry):
    print(f"New entry: {entry.title}")

conn = init_db()
poll_once(conn, on_new_entry)
```

#### Link Resolver

```python
from link_resolver import resolve_final_url

final_url = resolve_final_url("https://novelupdates.com/series/...")
```

#### Generic Extractor

```python
from generic_extractor import extract_chapter

result = extract_chapter("https://example.com/chapter-1")
if result.passed_quality_check:
    print(f"Title: {result.title}")
    print(f"Text: {result.text}")
    print(f"Method: {result.method}")
```

#### Site Overrides

Add entries to `site_overrides.py`:

```python
SITE_OVERRIDES = {
    "example-translations.com": {
        "content_selector": "div.entry-content",
        "remove_selectors": [".sharedaddy", ".ads", ".jp-relatedposts"],
    },
}
```

#### Storage

```python
from storage import init_storage, save_chapter

conn = init_storage()
save_chapter(
    conn,
    url="https://example.com/chapter-1",
    series="My Novel",
    chapter_label="Chapter 1",
    title="The Beginning",
    text="Chapter text here...",
    method="trafilatura"
)
```

#### Politeness Layer

```python
from politeness import polite_get

resp = polite_get("https://example.com/page")
# Automatically handles:
# - robots.txt checking
# - Rate limiting (5 second minimum delay)
# - Proper User-Agent
```

## Configuration

### RSS Polling Interval

Edit `rss_watcher.py`:

```python
POLL_INTERVAL_SECONDS = 15 * 60  # 15 minutes
```

### Rate Limiting

Edit `politeness.py`:

```python
MIN_DELAY_SECONDS = 5  # Minimum delay between requests to same domain
```

### Quality Thresholds

Edit `generic_extractor.py`:

```python
def quality_check(text: str, min_chars: int = 500, min_paragraphs: int = 3) -> bool:
    # Adjust minimum character count and paragraph count
```

## Cloud Mode (Scheduled Poller)

The app can run without any always-on host: a GitHub Actions workflow
(`.github/workflows/poll.yml`) polls the RSS feed every 30 minutes and
writes results to **Firestore** — the same project that backs
morganwilkinson.com's workshop apps. The site's `/apps/novels` page reads
that data client-side, so nothing scrapes from Cloudflare
infrastructure.

```
GitHub Actions cron → python poller.py (single pass) → Firestore
                                                          ↑
                                          browser reads (Access-gated)
```

### Required env / Actions secrets

| Env var | Secret | Purpose |
|---|---|---|
| `DB_TYPE=firestore` | — | Selects the Firestore backend |
| `RSS_FEED_URL` | `NU_RSS_FEED_URL` | Keyed personal NU feed URL |
| `FIREBASE_REFRESH_TOKEN` | `FIREBASE_REFRESH_TOKEN` | Anonymous Firebase user's refresh token (mint once via Identity Toolkit `accounts:signUp`; rules gate writes to that uid) |
| `NOVELUPDATES_COOKIES` | `NU_COOKIES` | Optional JSON dict if the feed needs auth |
| `SERIES_SYNC_INLINE=1` | — | Set by the workflow (no daemon threads in a one-shot run) |
| `EXPORT_DIR` | — | Set to `$RUNNER_TEMP/exports` in the workflow |

### Firestore layout

- `novels/{slug}` — series docs (`name`, `url`, `synopsis`, `latestLabel`,
  `latestLink`, `chapterCount`, `lastSynced`, …)
- `novels/{slug}/chapters/{sha256(url)}` — chapter docs (`title`, `label`,
  `text`, `method`, `fetchedAt`) — insert-if-absent, so runs are idempotent
- `novels_seen/{sha256(guid)}` — RSS dedup (replaces `seen_entries.db`)
- `novels_meta/state` — last run status for the site dashboard

### Migrating existing data

```bash
export FIREBASE_REFRESH_TOKEN="<anon-user refresh token>"
python tools/import_sqlite.py --dry-run          # count what would migrate
python tools/import_sqlite.py                    # write it to Firestore
```

Local/desktop mode is unchanged — `DB_TYPE` still defaults to `sqlite`
and `main.py`/`web_ui.py` work exactly as before.

## Database Schema

### seen_entries.db

```sql
CREATE TABLE seen_entries (
    guid TEXT PRIMARY KEY,
    link TEXT,
    first_seen REAL
)
```

### chapters.db

```sql
CREATE TABLE chapters (
    url TEXT PRIMARY KEY,
    series TEXT,
    chapter_label TEXT,
    title TEXT,
    text TEXT,
    extraction_method TEXT,
    fetched_at REAL
)
```

## Politeness Features

- **robots.txt compliance**: Checks and respects robots.txt before scraping
- **Rate limiting**: Enforces minimum delay between requests to same domain
- **Proper User-Agent**: Identifies the bot with contact information
- **Timeout handling**: Reasonable timeouts to avoid hanging
- **Graceful failures**: Logs errors without crashing the pipeline

## Adding Site Overrides

When generic extraction fails for a site:

1. Identify the CSS selector for the content container
2. Identify selectors for elements to remove (ads, navigation, etc.)
3. Add entry to `SITE_OVERRIDES` in `site_overrides.py`:

```python
SITE_OVERRIDES = {
    "problem-site.com": {
        "content_selector": "div.chapter-content",
        "remove_selectors": [".ad-banner", ".nav-links", ".comments"],
    },
}
```

## Extraction Methods

The system tries extraction in this order:

1. **trafilatura** - Primary generic extractor
2. **readability-lxml** - Fallback generic extractor
3. **site_override** - Site-specific CSS selector (if configured)

## Monitoring

The pipeline logs:
- New RSS entries detected
- Extraction method used for each chapter
- Failures needing manual review
- robots.txt blocks
- Network errors

## Troubleshooting

### Generic extraction failing frequently

- Check logs for which sites are failing
- Add site-specific overrides for problematic domains
- Consider adjusting quality thresholds if too strict

### Rate limiting too aggressive

- Increase `MIN_DELAY_SECONDS` in `politeness.py`
- Or decrease if you need faster polling (be careful)

### robots.txt blocking

- Check if the site actually blocks bots
- Verify your User-Agent is correctly identifying you
- Consider contacting site owner if legitimate use

## Future Enhancements

- **JS-rendered sites**: Add Playwright/Selenium for JavaScript-heavy sites
- **Feed filtering**: Filter RSS to specific reading lists
- **Web interface**: Add UI to browse stored chapters
- **Export formats**: Export to EPUB, PDF, etc.
- **Duplicate detection**: Cross-site chapter deduplication

## License

[Add your license here]
