"""Ordered chapter-source fallback chain.

NovelUpdates stays the source of truth for series metadata and release
discovery; these mirrors only fill in chapter *text*. Order:

    1. wuxiaworld.eu   — Next.js page scrape, plain HTTP
    2. novelfull.net   — classic truyen layout; CF-walled, so it can
                         borrow the shared Playwright session
    3. novellunar.com  — Next.js RSC-stream scrape, plain HTTP

Each source resolves the NU series name to its own slug and translates
the NU chapter number onto its own numbering. A source returning None
means "miss" (not hosted, stub only, blocked, or numbering doesn't
match) and the chain moves on — the last resort remains the
NovelUpdates-linked chapter URL, handled by the caller.
"""

import logging
import time

from scraping import novelfull, novellunar, wuxiaworld

logger = logging.getLogger(__name__)

_SOURCES = (
    ("wuxiaworld", wuxiaworld.fetch_chapter),
    ("novelfull", novelfull.fetch_chapter),
    ("novellunar", novellunar.fetch_chapter),
)

_INTER_SOURCE_DELAY = 0.4


def fetch_chapter(series_name: str, num, caches: dict, page=None):
    """Walk the mirror chain for (series, NU chapter num).

    `caches` is a caller-owned dict of per-source slug/index caches.
    Returns {title, text, url, source} on hit, None if every mirror
    misses — the caller then falls back to the NovelUpdates link.
    """
    for name, fetch in _SOURCES:
        cache = caches.setdefault(name, {})
        try:
            hit = fetch(series_name, num, cache, page=page)
        except Exception as e:
            logger.debug(f"alt source {name} c{num}: {e}")
            hit = None
        if hit:
            logger.info(
                f"  alt source hit: {name} c{num} — {hit['url']}")
            return {**hit, "source": name}
        time.sleep(_INTER_SOURCE_DELAY)
    return None
