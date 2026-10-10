---
ARCHIVED 2026-10-10 — originally at docs/architecture.md.
Reason: describes the pre-package flat-module architecture from before the rss/, scraping/, core/, data/ reorganization and before Firestore cloud mode; no longer matches the code.
Replaced by: [../01-overview-and-architecture.md](../01-overview-and-architecture.md)
---

# System Architecture

This document describes the architecture of the AI Novel Web Scraper system, including component interactions, data flow, and design decisions.

## Overview

The AI Novel Web Scraper is a modular pipeline system that automatically watches NovelUpdates RSS feeds, extracts chapter text from hosting sites, and stores the results while respecting politeness constraints.

## High-Level Architecture

```
┌─────────────────┐
│  RSS Watcher    │
│  (rss_watcher)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Link Resolver   │
│(link_resolver) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Generic Extractor│
│(generic_        │
│  extractor)     │
└────────┬────────┘
         │
         ▼
    ┌────┴────┐
    │ Quality │
    │  Check  │
    └────┬────┘
         │
    ┌────┴────┐
    │  Pass?  │
    └────┬────┘
         │
    ┌────┴────┐
    │   No    │────┐
    └─────────┘    │
                   │
         Yes       ▼
         │    ┌─────────────────┐
         │    │ Site Overrides  │
         │    │(site_overrides)│
         │    └────────┬────────┘
         │             │
         │             ▼
         │    ┌─────────────────┐
         │    │ Politeness Layer│
         │    │  (politeness)   │
         │    └────────┬────────┘
         │             │
         └──────┬──────┘
                │
                ▼
         ┌─────────────────┐
         │     Storage     │
         │   (storage)    │
         └─────────────────┘
```

## Component Details

### 1. RSS Watcher (`rss_watcher.py`)

**Purpose**: Poll NovelUpdates RSS feed and detect new chapter releases

**Responsibilities**:
- Poll RSS feed at configurable intervals (default: 15 minutes)
- Track processed entries to avoid duplicates
- Invoke callback for new entries

**Key Functions**:
- `init_db()` - Initialize SQLite database for tracking seen entries
- `is_new_entry()` - Check if an entry has been processed
- `mark_seen()` - Mark entry as processed
- `poll_once()` - Single polling iteration
- `run_forever()` - Continuous polling loop

**Data Flow**:
```
RSS Feed → feedparser → Entry Processing → Callback Invocation
```

**Database Schema**:
```sql
CREATE TABLE seen_entries (
    guid TEXT PRIMARY KEY,
    link TEXT,
    first_seen REAL
)
```

### 2. Link Resolver (`link_resolver.py`)

**Purpose**: Resolve feed links to final chapter URLs

**Responsibilities**:
- Follow HTTP redirects
- Handle HEAD request failures with GET fallback
- Return final destination URL

**Key Functions**:
- `resolve_final_url()` - Follow redirects and return final URL

**Data Flow**:
```
Feed URL → HTTP HEAD → Redirect Chain → Final URL
           (if fails)
           ↓
         HTTP GET → Final URL
```

### 3. Generic Extractor (`generic_extractor.py`)

**Purpose**: Extract chapter text using generic algorithms

**Responsibilities**:
- Primary extraction with trafilatura
- Fallback extraction with readability-lxml
- Quality validation
- Text cleaning and normalization

**Key Functions**:
- `fetch_html()` - Fetch HTML using politeness layer
- `_extract_with_trafilatura()` - Primary extraction method
- `_extract_with_readability()` - Fallback extraction method
- `clean_text()` - Remove boilerplate and normalize
- `quality_check()` - Validate extracted content
- `extract_chapter()` - Main extraction orchestration

**Extraction Flow**:
```
URL → Politeness Layer → HTML → Trafilatura
                                    ↓
                              Quality Check
                                    ↓
                            (if fails)
                                    ↓
                          Readability-lxml
                                    ↓
                              Quality Check
                                    ↓
                            Text Cleaning
                                    ↓
                            ExtractionResult
```

**Quality Heuristics**:
- Minimum character count (default: 500)
- Minimum paragraph count (default: 3)
- Link density analysis
- Boilerplate pattern removal

### 4. Site Overrides (`site_overrides.py`)

**Purpose**: Provide site-specific extraction rules

**Responsibilities**:
- Store CSS selector configurations per domain
- Extract content using custom selectors
- Remove unwanted elements (ads, navigation, etc.)

**Key Functions**:
- `extract_with_override()` - Extract using site-specific rules

**Configuration Structure**:
```python
SITE_OVERRIDES = {
    "example.com": {
        "content_selector": "div.chapter-content",
        "remove_selectors": [".ads", ".nav", ".comments"],
    }
}
```

**Data Flow**:
```
HTML + Domain → Config Lookup → CSS Selection → Element Removal → Text
```

### 5. Politeness Layer (`politeness.py`)

**Purpose**: Ensure respectful scraping behavior

**Responsibilities**:
- Check robots.txt compliance
- Enforce rate limiting per domain
- Provide proper User-Agent
- Handle request failures gracefully

**Key Functions**:
- `is_allowed()` - Check robots.txt permission
- `polite_get()` - Rate-limited HTTP requests
- `_get_robot_parser()` - Cached robots.txt parser

**Rate Limiting**:
- Per-domain minimum delay (default: 5 seconds)
- In-memory cache of last request times
- Automatic sleep before requests

**robots.txt Handling**:
- Cached per domain
- Fail-open if robots.txt unreachable
- Uses Python's urllib.robotparser

### 6. Storage (`storage.py`)

**Purpose**: Persist extracted chapters

**Responsibilities**:
- Initialize SQLite database
- Store chapter metadata and content
- Prevent duplicate storage

**Key Functions**:
- `init_storage()` - Initialize chapters database
- `save_chapter()` - Store chapter with metadata

**Database Schema**:
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

### 7. Main Orchestration (`main.py`)

**Purpose**: Tie all components together

**Responsibilities**:
- Initialize storage
- Coordinate component interactions
- Handle extraction failures
- Log progress and errors

**Key Functions**:
- `handle_new_entry()` - Process individual RSS entry
- Main loop via `run_forever()`

**Orchestration Flow**:
```
RSS Entry → Link Resolution → Generic Extraction
                                    ↓
                            Quality Check
                                    ↓
                        (if fails) Site Override
                                    ↓
                            Storage → Logging
```

## Data Flow

### Complete Pipeline Flow

```
1. RSS Watcher polls NovelUpdates feed
2. New entry detected → callback invoked
3. Link resolver resolves feed link to final URL
4. Generic extractor attempts extraction
5. Quality check validates result
6. If quality check fails:
   - Politeness layer fetches HTML
   - Site override attempts extraction
7. Successful extraction stored in database
8. Process repeats for next polling cycle
```

## Design Decisions

### Why SQLite?

- Lightweight, no external dependencies
- Sufficient for this scale
- Easy to backup and migrate
- Built-in Python support

### Why Dual Extraction Algorithms?

- **Trafilatura**: Modern, actively maintained, good accuracy
- **Readability-lxml**: Mature, Mozilla-based, different heuristics
- **Combined**: Higher success rate, fallback coverage

### Why Politeness Layer?

- Respectful to small site operators
- Avoids IP bans
- Compliant with robots.txt standard
- Sustainable long-term operation

### Why Site Overrides?

- Generic extraction doesn't work everywhere
- CSS selectors are flexible and maintainable
- Organic growth - add only when needed
- Keeps generic code simple

### Why RSS Polling vs API?

- NovelUpdates doesn't provide public API
- RSS is standard and reliable
- Low bandwidth requirement
- Simple implementation

## Error Handling Strategy

### Network Errors
- Logged with context
- Non-fatal to pipeline
- Retry with politeness constraints

### Extraction Failures
- Logged for manual review
- Triggers site override attempt
- Pipeline continues for other entries

### Database Errors
- Logged immediately
- Pipeline halts to prevent data loss
- Manual intervention required

### robots.txt Blocks
- Respected automatically
- Logged for monitoring
- No retry to avoid violations

## Performance Considerations

### Bottlenecks
- Network latency (mitigated by politeness)
- RSS polling interval (configurable)
- Database writes (minimal impact)

### Optimizations
- robots.txt caching per domain
- In-memory rate limiting state
- SQLite connection reuse
- Minimal HTML parsing overhead

### Scalability Limits
- Single-threaded design
- SQLite for storage (not distributed)
- Suitable for personal use, not enterprise scale

## Security Considerations

### Input Validation
- URL validation before processing
- HTML sanitization via extraction libraries
- SQL injection prevention via parameterized queries

### Privacy
- No user data collection
- Local database storage only
- Identifying User-Agent for transparency

### Access Control
- No authentication required
- Designed for personal use
- Consider adding for multi-user scenarios

## Future Architecture Enhancements

### Potential Improvements
- **Multi-threading**: Parallel processing of entries
- **Message Queue**: Decouple components for scaling
- **Distributed Storage**: PostgreSQL/MongoDB for scale
- **API Layer**: REST API for external access
- **Web UI**: Browser-based management interface
- **Headless Browser**: Playwright for JS-rendered sites

### Extension Points
- Custom extraction algorithms
- Alternative storage backends
- Additional politeness strategies
- Custom quality metrics
- Plugin architecture for site handlers
