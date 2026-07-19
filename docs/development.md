# Development Guide

This guide provides detailed instructions for developing, testing, and debugging the AI Novel Web Scraper.

## Table of Contents

- [Environment Setup](#environment-setup)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Debugging](#debugging)
- [Adding Site Overrides](#adding-site-overrides)
- [Modifying Extraction Logic](#modifying-extraction-logic)
- [Database Management](#database-management)
- [Performance Profiling](#performance-profiling)

## Environment Setup

### Prerequisites

- Python 3.8 or higher
- Git
- Virtual environment tool (venv or conda)

### Step-by-Step Setup

#### 1. Clone the Repository

```bash
git clone https://github.com/Morgan-Wilkinson/AI-Web-Scrapper.git
cd AI-Web-Scrapper
git checkout v2
```

#### 2. Create Virtual Environment

**Using venv:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

**Using conda:**
```bash
conda create -n novel-scraper python=3.9
conda activate novel-scraper
```

#### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 4. Install Development Tools (Optional)

```bash
pip install pytest pytest-cov black flake8 mypy ipython
```

#### 5. Verify Installation

```bash
python -c "import trafilatura; print('trafilatura installed')"
python -c "import feedparser; print('feedparser installed')"
python -c "from readability import Document; print('readability installed')"
```

## Project Structure

```
AI-Web-Scrapper/
├── docs/                      # Documentation
│   ├── architecture.md        # System architecture
│   ├── development.md         # This file
│   ├── deployment.md          # Deployment guide
│   └── api.md                 # API documentation
├── .github/                   # GitHub configuration
│   ├── ISSUE_TEMPLATE/        # Issue templates
│   └── pull_request_template.md
├── rss_watcher.py             # RSS feed polling
├── link_resolver.py           # URL resolution
├── generic_extractor.py       # Text extraction
├── site_overrides.py          # Site-specific rules
├── storage.py                 # Database operations
├── politeness.py              # Rate limiting & robots.txt
├── main.py                    # Main orchestration
├── requirements.txt           # Dependencies
├── README.md                  # Project overview
├── CONTRIBUTING.md            # Contribution guidelines
├── seen_entries.db            # Runtime: RSS tracking (created automatically)
└── chapters.db                # Runtime: Chapter storage (created automatically)
```

## Development Workflow

### Making Changes

#### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

#### 2. Make Your Changes

Edit the relevant files. For example:
- Adding a new site override: edit `site_overrides.py`
- Modifying extraction logic: edit `generic_extractor.py`
- Changing polling interval: edit `rss_watcher.py`

#### 3. Test Your Changes

```bash
# Run the main script to test
python main.py

# Or test individual components
python -c "from generic_extractor import extract_chapter; print(extract_chapter('https://example.com'))"
```

#### 4. Format and Lint

```bash
# Format code with black
black .

# Check style with flake8
flake8 .

# Type check with mypy
mypy .
```

#### 5. Commit Changes

```bash
git add .
git commit -m "feat: add your feature description"
```

#### 6. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub.

### Code Style Guidelines

#### Python Style (PEP 8)

- Use 4 spaces for indentation
- Maximum line length: 88 characters (Black default)
- Use snake_case for variables and functions
- Use PascalCase for classes
- Add docstrings to all functions and classes

#### Example:

```python
"""
Module docstring describing the module's purpose.
"""

from typing import Optional
import requests


def fetch_data(url: str, timeout: int = 15) -> Optional[str]:
    """
    Fetch data from a URL with a timeout.

    Args:
        url: The URL to fetch from
        timeout: Request timeout in seconds

    Returns:
        The response text if successful, None otherwise

    Raises:
        ValueError: If URL is invalid
    """
    if not url:
        raise ValueError("URL cannot be empty")

    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Failed to fetch {url}: {e}")
        return None
```

#### Type Hints

Use type hints for function signatures:

```python
from typing import Optional, List, Dict

def process_chapters(chapters: List[str]) -> Dict[str, int]:
    """Process chapters and return statistics."""
    return {"count": len(chapters)}
```

## Testing

### Manual Testing

#### Test RSS Watcher

```python
from rss_watcher import init_db, poll_once

def test_callback(entry):
    print(f"New entry: {entry.title}")
    print(f"Link: {entry.link}")

conn = init_db()
poll_once(conn, test_callback)
```

#### Test Link Resolver

```python
from link_resolver import resolve_final_url

url = "https://novelupdates.com/series/..."
final_url = resolve_final_url(url)
print(f"Final URL: {final_url}")
```

#### Test Generic Extractor

```python
from generic_extractor import extract_chapter

result = extract_chapter("https://example.com/chapter-1")
print(f"Title: {result.title}")
print(f"Method: {result.method}")
print(f"Passed quality check: {result.passed_quality_check}")
print(f"Character count: {result.char_count}")
```

#### Test Site Overrides

```python
from site_overrides import extract_with_override

html = "<html>...</html>"
domain = "example.com"
text = extract_with_override(html, domain)
print(f"Extracted text: {text}")
```

#### Test Politeness Layer

```python
from politeness import polite_get, is_allowed

url = "https://example.com/page"
if is_allowed(url):
    resp = polite_get(url)
    print(f"Response status: {resp.status_code if resp else 'None'}")
```

### Automated Testing (Future)

When tests are added:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test
pytest tests/test_extractor.py

# Run with verbose output
pytest -v
```

## Debugging

### Enable Debug Logging

Add logging to modules:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
```

### Common Issues and Solutions

#### Issue: RSS feed not updating

**Debug steps:**
1. Check if `seen_entries.db` has entries
2. Verify feed URL is correct
3. Test feed URL manually: `curl https://www.novelupdates.com/rss/`

**Solution:**
```python
# Clear seen entries to reprocess
import sqlite3
conn = sqlite3.connect("seen_entries.db")
conn.execute("DELETE FROM seen_entries")
conn.commit()
```

#### Issue: Extraction failing for a site

**Debug steps:**
1. Test with generic extractor first
2. Check if HTML is being fetched
3. Verify quality thresholds aren't too strict

**Solution:**
```python
# Lower quality thresholds temporarily
result = extract_chapter(url)
print(f"Text preview: {result.text[:500] if result.text else 'None'}")
print(f"Char count: {result.char_count}")
print(f"Paragraph count: {result.paragraph_count}")
```

#### Issue: Rate limiting too aggressive

**Debug steps:**
1. Check politeness logs
2. Verify domain tracking

**Solution:**
```python
# Modify politeness.py
MIN_DELAY_SECONDS = 2  # Reduce from 5
```

#### Issue: robots.txt blocking

**Debug steps:**
1. Check if robots.txt is accessible
2. Verify User-Agent is correct

**Solution:**
```python
# Test robots.txt manually
from politeness import _get_robot_parser, _domain_of

domain = _domain_of(url)
rp = _get_robot_parser(domain)
print(f"Can fetch: {rp.can_fetch(politeness.USER_AGENT, url)}")
```

### Using pdb for Debugging

```python
import pdb

def your_function():
    pdb.set_trace()  # Breakpoint
    # code to debug
```

Or use from command line:
```bash
python -m pdb your_script.py
```

## Adding Site Overrides

### When to Add an Override

Add a site override when:
- Generic extraction consistently fails
- The site has a unique structure
- Quality check fails repeatedly

### Steps to Add Override

#### 1. Inspect the Site

Visit the site and inspect the HTML structure:
```bash
# Use browser DevTools to find content selector
# Look for the main chapter text container
```

#### 2. Test Selectors

```python
from bs4 import BeautifulSoup
import requests

resp = requests.get("https://example.com/chapter-1")
soup = BeautifulSoup(resp.text, "lxml")

# Test different selectors
selectors = [
    "div.entry-content",
    "div.chapter-content",
    "article",
    "#content",
]

for sel in selectors:
    element = soup.select_one(sel)
    if element:
        print(f"Found with {sel}: {len(element.get_text())} chars")
```

#### 3. Add to site_overrides.py

```python
SITE_OVERRIDES = {
    "example-translations.com": {
        "content_selector": "div.entry-content",
        "remove_selectors": [
            ".sharedaddy",
            ".ads",
            ".jp-relatedposts",
            ".navigation",
        ],
    },
}
```

#### 4. Test the Override

```python
from site_overrides import extract_with_override
import requests

resp = requests.get("https://example.com/chapter-1")
text = extract_with_override(resp.text, "example.com")
print(f"Extracted: {len(text) if text else 0} characters")
```

#### 5. Monitor Quality

After adding, monitor logs to ensure extraction succeeds:
```
saved: Chapter Title (site_override)
```

## Modifying Extraction Logic

### Changing Quality Thresholds

Edit `generic_extractor.py`:

```python
def quality_check(text: str, min_chars: int = 500, min_paragraphs: int = 3) -> bool:
    # Adjust thresholds based on your needs
    min_chars = 300  # Lower threshold
    min_paragraphs = 2  # Lower threshold
    # ...
```

### Adding New Extraction Algorithm

1. Implement the extraction function:
```python
def _extract_with_custom(html: str):
    """Custom extraction logic."""
    # Your implementation
    return title, text
```

2. Add to extraction pipeline:
```python
def extract_chapter(url: str) -> ExtractionResult:
    # ... existing code ...
    
    # Add custom extraction
    if not quality_check(text):
        custom_title, custom_text = _extract_with_custom(html)
        if quality_check(custom_text):
            title, text, method = custom_title, custom_text, "custom"
    
    # ... rest of function ...
```

### Modifying Boilerplate Patterns

Edit `generic_extractor.py`:

```python
boilerplate_patterns = [
    r"^\s*(next|previous|prev)\s*(chapter)?\s*$",
    r"^\s*chapter\s*(index|list)\s*$",
    r"^\s*share\s*(this)?\s*$",
    r"^\s*advertisement\s*$",
    # Add your patterns
    r"^\s*subscribe\s*now\s*$",
    r"^\s*donate\s*$",
]
```

## Database Management

### Viewing Database Contents

#### seen_entries.db

```python
import sqlite3

conn = sqlite3.connect("seen_entries.db")
cursor = conn.execute("SELECT * FROM seen_entries ORDER BY first_seen DESC LIMIT 10")
for row in cursor:
    print(row)
```

#### chapters.db

```python
import sqlite3

conn = sqlite3.connect("chapters.db")
cursor = conn.execute("SELECT series, chapter_label, title, extraction_method FROM chapters LIMIT 10")
for row in cursor:
    print(row)
```

### Resetting Databases

**Warning:** This will delete all data!

```python
import sqlite3
import os

# Reset seen entries
os.remove("seen_entries.db")

# Reset chapters
os.remove("chapters.db")

# They will be recreated automatically on next run
```

### Database Backup

```python
import shutil
from datetime import datetime

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy("chapters.db", f"chapters_backup_{timestamp}.db")
shutil.copy("seen_entries.db", f"seen_entries_backup_{timestamp}.db")
```

### Querying Statistics

```python
import sqlite3

conn = sqlite3.connect("chapters.db")

# Total chapters
cursor = conn.execute("SELECT COUNT(*) FROM chapters")
print(f"Total chapters: {cursor.fetchone()[0]}")

# Chapters by extraction method
cursor = conn.execute("""
    SELECT extraction_method, COUNT(*) 
    FROM chapters 
    GROUP BY extraction_method
""")
for method, count in cursor:
    print(f"{method}: {count}")

# Chapters by series
cursor = conn.execute("""
    SELECT series, COUNT(*) 
    FROM chapters 
    GROUP BY series 
    ORDER BY COUNT(*) DESC 
    LIMIT 10
""")
for series, count in cursor:
    print(f"{series}: {count}")
```

## Performance Profiling

### Profiling Execution Time

```python
import time
import cProfile

def profile_extraction():
    start = time.time()
    result = extract_chapter("https://example.com/chapter-1")
    end = time.time()
    print(f"Extraction took {end - start:.2f} seconds")

# Or use cProfile for detailed profiling
cProfile.run('extract_chapter("https://example.com/chapter-1")')
```

### Profiling Memory Usage

```python
import tracemalloc

tracemalloc.start()

# Run your code
result = extract_chapter("https://example.com/chapter-1")

# Get memory stats
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')

for stat in top_stats[:10]:
    print(stat)
```

### Identifying Bottlenecks

Common bottlenecks:
1. Network latency (mitigated by politeness)
2. HTML parsing (trafilatura/readability)
3. Database writes (usually minimal)

Use profiling to identify specific bottlenecks in your use case.

## Development Tips

### Use IPython for Interactive Testing

```bash
ipython
```

Then:
```python
from generic_extractor import extract_chapter
result = extract_chapter("https://example.com")
result.title
result.text[:500]
```

### Keep Test URLs Handy

Maintain a list of test URLs for different sites:
```python
TEST_URLS = {
    "wordpress_site": "https://example.com/chapter-1",
    "custom_cms": "https://example.org/novel/chapter-2",
    "js_rendered": "https://example.net/chapter-3",
}
```

### Log Everything During Development

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='debug.log'
)
```

### Use Git Effectively

```bash
# View changes
git diff

# View history
git log --oneline --graph

# Stash changes
git stash

# View stashed changes
git stash list
```

## Getting Help

- Check [architecture.md](architecture.md) for system design
- Review [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines
- Open an issue on GitHub for bugs or questions
- Check existing issues for similar problems
