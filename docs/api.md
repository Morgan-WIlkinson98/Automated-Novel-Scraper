# API Documentation

This document provides detailed API documentation for all modules and functions in the AI Novel Web Scraper.

## Table of Contents

- [RSS Watcher Module](#rss-watcher-module-rss_watcherpy)
- [Link Resolver Module](#link-resolver-module-link_resolverpy)
- [Generic Extractor Module](#generic-extractor-module-generic_extractorpy)
- [Site Overrides Module](#site-overrides-module-site_overridespy)
- [Storage Module](#storage-module-storagepy)
- [Politeness Module](#politeness-module-politenesspy)
- [Main Orchestration Module](#main-orchestration-module-mainpy)

---

## RSS Watcher Module (`rss_watcher.py`)

### Overview

The RSS watcher module polls the NovelUpdates RSS feed and detects new chapter releases while tracking processed entries to avoid duplicates.

### Functions

#### `init_db(path="seen_entries.db")`

Initialize the SQLite database for tracking seen RSS entries.

**Parameters:**
- `path` (str, optional): Path to the SQLite database file. Defaults to "seen_entries.db".

**Returns:**
- `sqlite3.Connection`: Database connection object

**Example:**
```python
from rss_watcher import init_db

conn = init_db("/custom/path/seen_entries.db")
```

---

#### `is_new_entry(conn, guid: str) -> bool`

Check if an RSS entry has been processed before.

**Parameters:**
- `conn` (sqlite3.Connection): Database connection
- `guid` (str): GUID of the RSS entry

**Returns:**
- `bool`: True if entry is new, False if already seen

**Example:**
```python
from rss_watcher import is_new_entry

if is_new_entry(conn, "entry-guid-123"):
    print("This is a new entry")
```

---

#### `mark_seen(conn, guid: str, link: str)`

Mark an RSS entry as processed in the database.

**Parameters:**
- `conn` (sqlite3.Connection): Database connection
- `guid` (str): GUID of the RSS entry
- `link` (str): URL of the RSS entry

**Returns:**
- None

**Example:**
```python
from rss_watcher import mark_seen

mark_seen(conn, "entry-guid-123", "https://example.com/chapter-1")
```

---

#### `poll_once(conn, on_new_entry)`

Perform a single polling iteration of the RSS feed.

**Parameters:**
- `conn` (sqlite3.Connection): Database connection
- `on_new_entry` (callable): Callback function invoked for each new entry

**Callback Signature:**
```python
def on_new_entry(entry):
    """
    Args:
        entry: feedparser.FeedParserDict object with keys:
            - title: str - Entry title
            - link: str - Entry URL
            - summary: str - Entry summary
            - id: str - Entry GUID (if available)
    """
    pass
```

**Returns:**
- None

**Example:**
```python
from rss_watcher import poll_once, init_db

def handle_entry(entry):
    print(f"New: {entry.title}")

conn = init_db()
poll_once(conn, handle_entry)
```

---

#### `run_forever(on_new_entry)`

Run the RSS watcher in a continuous loop.

**Parameters:**
- `on_new_entry` (callable): Callback function for new entries

**Behavior:**
- Polls RSS feed every 15 minutes (configurable via `POLL_INTERVAL_SECONDS`)
- Runs indefinitely until interrupted

**Example:**
```python
from rss_watcher import run_forever

def handle_entry(entry):
    print(f"Processing: {entry.title}")

run_forever(handle_entry)
```

---

### Constants

#### `FEED_URL`

The NovelUpdates RSS feed URL.

```python
FEED_URL = "https://www.novelupdates.com/rss/"
```

#### `POLL_INTERVAL_SECONDS`

Time in seconds between RSS polling iterations.

```python
POLL_INTERVAL_SECONDS = 15 * 60  # 15 minutes
```

---

## Link Resolver Module (`link_resolver.py`)

### Overview

The link resolver module follows HTTP redirects to resolve feed links to their final destination URLs.

### Functions

#### `resolve_final_url(url: str, timeout: int = 15) -> str`

Follow redirects and return the final destination URL.

**Parameters:**
- `url` (str): The URL to resolve
- `timeout` (int, optional): Request timeout in seconds. Defaults to 15.

**Returns:**
- `str`: The final URL after following redirects

**Behavior:**
- First attempts HTTP HEAD request
- Falls back to HTTP GET if HEAD fails
- Automatically follows redirect chains

**Example:**
```python
from link_resolver import resolve_final_url

feed_url = "https://novelupdates.com/series/..."
final_url = resolve_final_url(feed_url)
print(f"Final URL: {final_url}")
```

**Raises:**
- `requests.RequestException`: If both HEAD and GET requests fail

---

## Generic Extractor Module (`generic_extractor.py`)

### Overview

The generic extractor module extracts chapter text from URLs using dual-algorithm approach (trafilatura + readability-lxml) with quality validation.

### Data Classes

#### `ExtractionResult`

Data class containing extraction results and metadata.

**Attributes:**
- `url` (str): Original URL
- `title` (Optional[str]): Extracted chapter title
- `text` (Optional[str]): Cleaned chapter text
- `method` (str): Extraction method used ("trafilatura", "readability", "failed", "site_override")
- `char_count` (int): Character count of extracted text
- `paragraph_count` (int): Paragraph count of extracted text
- `passed_quality_check` (bool): Whether extraction passed quality heuristics

**Example:**
```python
from generic_extractor import ExtractionResult

result = ExtractionResult(
    url="https://example.com/chapter-1",
    title="Chapter 1",
    text="Chapter content...",
    method="trafilatura",
    char_count=1500,
    paragraph_count=10,
    passed_quality_check=True
)
```

---

### Functions

#### `fetch_html(url: str) -> Optional[str]`

Fetch raw HTML for a URL using the politeness layer.

**Parameters:**
- `url` (str): URL to fetch

**Returns:**
- `Optional[str]`: HTML content if successful, None otherwise

**Behavior:**
- Uses `polite_get()` for rate-limited requests
- Respects robots.txt
- Handles request failures gracefully

**Example:**
```python
from generic_extractor import fetch_html

html = fetch_html("https://example.com/chapter-1")
if html:
    print(f"Fetched {len(html)} characters")
```

---

#### `_extract_with_trafilatura(html: str, url: str)`

Extract text using trafilatura library.

**Parameters:**
- `html` (str): HTML content
- `url` (str): Source URL (for metadata extraction)

**Returns:**
- `tuple`: (title: Optional[str], text: Optional[str])

**Behavior:**
- Excludes comments and tables
- Favors precision over recall
- Extracts metadata including title

**Example:**
```python
from generic_extractor import _extract_with_trafilatura

title, text = _extract_with_trafilatura(html, url)
print(f"Title: {title}")
print(f"Text length: {len(text) if text else 0}")
```

---

#### `_extract_with_readability(html: str)`

Extract text using readability-lxml library.

**Parameters:**
- `html` (str): HTML content

**Returns:**
- `tuple`: (title: Optional[str], text: Optional[str])

**Behavior:**
- Returns HTML summary
- Strips HTML tags for plain text
- Normalizes whitespace

**Example:**
```python
from generic_extractor import _extract_with_readability

title, text = _extract_with_readability(html)
print(f"Title: {title}")
print(f"Text length: {len(text) if text else 0}")
```

---

#### `clean_text(text: str) -> str`

Clean and normalize extracted text.

**Parameters:**
- `text` (str): Raw extracted text

**Returns:**
- `str`: Cleaned text

**Behavior:**
- Removes boilerplate patterns (navigation, ads, etc.)
- Normalizes whitespace
- Removes empty lines

**Boilerplate Patterns Removed:**
- "next/previous chapter" links
- "chapter index/list" text
- "share" buttons
- "advertisement" text

**Example:**
```python
from generic_extractor import clean_text

cleaned = clean_text(raw_text)
print(f"Cleaned text: {cleaned}")
```

---

#### `quality_check(text: str, min_chars: int = 500, min_paragraphs: int = 3) -> bool`

Validate extracted content quality.

**Parameters:**
- `text` (str): Text to validate
- `min_chars` (int, optional): Minimum character count. Defaults to 500.
- `min_paragraphs` (int, optional): Minimum paragraph count. Defaults to 3.

**Returns:**
- `bool`: True if text passes quality check, False otherwise

**Example:**
```python
from generic_extractor import quality_check

if quality_check(text, min_chars=300, min_paragraphs=2):
    print("Text quality acceptable")
```

---

#### `extract_chapter(url: str) -> ExtractionResult`

Main extraction orchestration function.

**Parameters:**
- `url` (str): URL to extract chapter from

**Returns:**
- `ExtractionResult`: Extraction result with metadata

**Behavior:**
1. Fetches HTML using politeness layer
2. Attempts trafilatura extraction
3. Falls back to readability-lxml if quality check fails
4. Cleans and validates final text
5. Returns structured result

**Example:**
```python
from generic_extractor import extract_chapter

result = extract_chapter("https://example.com/chapter-1")
if result.passed_quality_check:
    print(f"Title: {result.title}")
    print(f"Method: {result.method}")
    print(f"Text: {result.text[:200]}...")
else:
    print("Extraction failed")
```

---

### Constants

#### `REQUEST_TIMEOUT`

Default request timeout in seconds.

```python
REQUEST_TIMEOUT = 15
```

---

## Site Overrides Module (`site_overrides.py`)

### Overview

The site overrides module provides site-specific extraction rules using CSS selectors for sites where generic extraction fails.

### Configuration

#### `SITE_OVERRIDES`

Dictionary mapping domains to extraction configurations.

**Structure:**
```python
SITE_OVERRIDES = {
    "domain.com": {
        "content_selector": "css.selector.for.content",
        "remove_selectors": [
            "css.selector.to.remove",
            "another.selector",
        ],
    },
}
```

**Example:**
```python
SITE_OVERRIDES = {
    "example-translations.com": {
        "content_selector": "div.entry-content",
        "remove_selectors": [
            ".sharedaddy",
            ".ads",
            ".jp-relatedposts",
        ],
    },
}
```

---

### Functions

#### `extract_with_override(html: str, domain: str) -> Optional[str]`

Extract text using site-specific CSS selectors.

**Parameters:**
- `html` (str): HTML content
- `domain` (str): Domain name to look up in overrides

**Returns:**
- `Optional[str]`: Extracted text if override exists and succeeds, None otherwise

**Behavior:**
1. Looks up domain in `SITE_OVERRIDES`
2. Selects content using `content_selector`
3. Removes elements matching `remove_selectors`
4. Returns plain text

**Example:**
```python
from site_overrides import extract_with_override

text = extract_with_override(html, "example.com")
if text:
    print(f"Extracted {len(text)} characters")
else:
    print("No override configured for this domain")
```

---

## Storage Module (`storage.py`)

### Overview

The storage module handles SQLite database operations for persisting extracted chapters.

### Functions

#### `init_storage(path="chapters.db")`

Initialize the chapters database.

**Parameters:**
- `path` (str, optional): Path to SQLite database file. Defaults to "chapters.db".

**Returns:**
- `sqlite3.Connection`: Database connection object

**Database Schema:**
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

**Example:**
```python
from storage import init_storage

conn = init_storage("/custom/path/chapters.db")
```

---

#### `save_chapter(conn, url, series, chapter_label, title, text, method)`

Save a chapter to the database.

**Parameters:**
- `conn` (sqlite3.Connection): Database connection
- `url` (str): Chapter URL (primary key)
- `series` (str): Series name
- `chapter_label` (str): Chapter label (e.g., "Chapter 1")
- `title` (str): Chapter title
- `text` (str): Chapter text content
- `method` (str): Extraction method used

**Returns:**
- None

**Behavior:**
- Uses `INSERT OR IGNORE` to prevent duplicates
- Automatically includes timestamp via `time.time()`

**Example:**
```python
from storage import init_storage, save_chapter

conn = init_storage()
save_chapter(
    conn,
    url="https://example.com/chapter-1",
    series="My Novel",
    chapter_label="Chapter 1",
    title="The Beginning",
    text="Chapter content here...",
    method="trafilatura"
)
```

---

## Politeness Module (`politeness.py`)

### Overview

The politeness module ensures respectful scraping behavior through robots.txt compliance, rate limiting, and proper User-Agent identification.

### Constants

#### `USER_AGENT`

User-Agent string for HTTP requests.

```python
USER_AGENT = "Mozilla/5.0 (compatible; ChapterFetcher/1.0; +https://example.invalid/bot-info)"
```

**Note:** Update the URL to your actual contact information.

#### `MIN_DELAY_SECONDS`

Minimum delay between requests to the same domain in seconds.

```python
MIN_DELAY_SECONDS = 5
```

---

### Functions

#### `_domain_of(url: str) -> str`

Extract domain from URL.

**Parameters:**
- `url` (str): Full URL

**Returns:**
- `str`: Domain (netloc) portion of URL

**Example:**
```python
from politeness import _domain_of

domain = _domain_of("https://example.com/page")
# Returns: "example.com"
```

---

#### `_get_robot_parser(domain: str) -> RobotFileParser`

Get cached robots.txt parser for a domain.

**Parameters:**
- `domain` (str): Domain name

**Returns:**
- `RobotFileParser`: Configured robots.txt parser

**Behavior:**
- Caches parsers per domain
- Fetches robots.txt on first access
- Fails open if robots.txt unreachable

**Example:**
```python
from politeness import _get_robot_parser

rp = _get_robot_parser("example.com")
print(rp.can_fetch(USER_AGENT, "https://example.com/page"))
```

---

#### `is_allowed(url: str) -> bool`

Check if URL is allowed by robots.txt.

**Parameters:**
- `url` (str): URL to check

**Returns:**
- `bool`: True if allowed, False if disallowed

**Example:**
```python
from politeness import is_allowed

if is_allowed("https://example.com/page"):
    print("Allowed to scrape")
else:
    print("Blocked by robots.txt")
```

---

#### `polite_get(url: str, timeout: int = 15) -> Optional[requests.Response]`

Make a rate-limited HTTP request.

**Parameters:**
- `url` (str): URL to request
- `timeout` (int, optional): Request timeout in seconds. Defaults to 15.

**Returns:**
- `Optional[requests.Response]`: Response object if successful, None otherwise

**Behavior:**
- Checks robots.txt compliance
- Enforces minimum delay between requests to same domain
- Uses configured User-Agent
- Handles request failures gracefully

**Example:**
```python
from politeness import polite_get

resp = polite_get("https://example.com/page")
if resp:
    print(f"Status: {resp.status_code}")
    print(f"Content length: {len(resp.text)}")
```

---

## Main Orchestration Module (`main.py`)

### Overview

The main orchestration module ties all components together to form the complete scraping pipeline.

### Functions

#### `handle_new_entry(entry)`

Process a new RSS entry through the complete pipeline.

**Parameters:**
- `entry`: feedparser.FeedParserDict object containing:
    - `title`: Series name
    - `link`: Feed link
    - `summary`: Chapter label

**Behavior:**
1. Resolves feed link to final URL
2. Attempts generic extraction
3. Falls back to site override if quality check fails
4. Saves successful extraction to database
5. Logs results

**Example:**
```python
from main import handle_new_entry
import feedparser

# Simulate an entry
entry = type('Entry', (), {
    'title': 'My Novel',
    'link': 'https://novelupdates.com/series/...',
    'summary': 'Chapter 1'
})()

handle_new_entry(entry)
```

---

### Main Execution

When run as script:

```bash
python main.py
```

**Behavior:**
- Initializes storage database
- Starts RSS watcher in continuous loop
- Processes new entries indefinitely

**Example:**
```python
if __name__ == "__main__":
    run_forever(handle_new_entry)
```

---

## Usage Examples

### Complete Pipeline Example

```python
from rss_watcher import init_db, poll_once
from link_resolver import resolve_final_url
from generic_extractor import extract_chapter
from storage import init_storage, save_chapter

# Initialize databases
rss_conn = init_db()
storage_conn = init_storage()

def process_entry(entry):
    # Resolve link
    final_url = resolve_final_url(entry.link)
    
    # Extract chapter
    result = extract_chapter(final_url)
    
    if result.passed_quality_check:
        # Save to database
        save_chapter(
            storage_conn,
            url=final_url,
            series=entry.title,
            chapter_label=entry.summary,
            title=result.title,
            text=result.text,
            method=result.method
        )
        print(f"Saved: {result.title}")
    else:
        print(f"Failed to extract: {final_url}")

# Poll once
poll_once(rss_conn, process_entry)
```

### Component Testing Example

```python
# Test individual components
from generic_extractor import extract_chapter
from politeness import is_allowed

# Check if URL is allowed
url = "https://example.com/chapter-1"
if is_allowed(url):
    # Extract chapter
    result = extract_chapter(url)
    print(f"Method: {result.method}")
    print(f"Quality: {result.passed_quality_check}")
```

### Custom Configuration Example

```python
# Modify polling interval
import rss_watcher
rss_watcher.POLL_INTERVAL_SECONDS = 30 * 60  # 30 minutes

# Modify rate limiting
import politeness
politeness.MIN_DELAY_SECONDS = 10  # 10 seconds

# Modify quality thresholds
from generic_extractor import extract_chapter
result = extract_chapter(url, min_chars=300, min_paragraphs=2)
```

---

## Error Handling

### Common Exceptions

- `requests.RequestException`: Network-related errors
- `sqlite3.Error`: Database errors
- `ValueError`: Invalid parameters

### Error Handling Pattern

```python
from generic_extractor import extract_chapter

try:
    result = extract_chapter(url)
    if result.passed_quality_check:
        # Process result
        pass
    else:
        # Handle extraction failure
        pass
except Exception as e:
    print(f"Error: {e}")
    # Handle error
```

---

## Type Hints

All functions use type hints for better IDE support and type checking:

```python
from typing import Optional
import sqlite3
import requests

def example_function(
    url: str,
    timeout: int = 15
) -> Optional[str]:
    """Example with type hints."""
    pass
```

---

## Performance Considerations

- **Rate Limiting**: Built-in via politeness layer
- **Caching**: robots.txt parsers cached per domain
- **Connection Reuse**: SQLite connections reused
- **Timeouts**: All HTTP requests have configurable timeouts

---

## Thread Safety

- **SQLite**: Connections are not thread-safe; use separate connections per thread
- **Politeness Layer**: Uses in-memory state; not thread-safe
- **Recommendation**: Run single-threaded or implement proper locking

---

## Future API Extensions

Planned additions:
- REST API for external access
- WebSocket support for real-time updates
- GraphQL interface for flexible queries
- Authentication and authorization
- Rate limiting API endpoints
