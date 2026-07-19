"""
main.py
Ties together: rss_watcher, link_resolver, generic_extractor,
site_overrides, storage, politeness
"""

import logging
import re
from urllib.parse import urlparse
from settings import get_settings
from rss_watcher import run_forever
from link_resolver import resolve_final_url_with_browser_fallback as resolve_final_url
from generic_extractor import extract_chapter
from site_overrides import extract_with_override
from storage import init_storage, save_chapter, save_series_info
from politeness import polite_get
from exceptions import DatabaseError, HTTPError, ValidationError
from logging_config import setup_logging

logger = logging.getLogger(__name__)


def clean_series_name(title: str) -> str:
    """Remove trailing chapter labels like ' c226' from an RSS entry title."""
    if not title:
        return "Unknown"
    # Strip common trailing chapter patterns: c123, c 123, chapter 123, etc.
    title = re.sub(r'\s*[Cc][\.\s]?\d+(?:\.\d+)?\s*$', '', title)
    title = re.sub(r'\s*[Cc]hapter\s*\d+(?:\.\d+)?\s*$', '', title)
    title = re.sub(r'\s*\(?\d+(?:\.\d+)?\)?\s*$', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title.strip() or "Unknown"


db = None

def get_db():
    """Get or initialize the global chapters database connection."""
    global db
    if db is None:
        db = init_storage(get_settings().CHAPTERS_DB)
    return db

def handle_new_entry(entry):
    """Process a new RSS entry through the complete pipeline."""
    try:
        db = get_db()
        feed_link = entry.link
        if not feed_link:
            logger.warning("Entry has no link, skipping")
            return
        
        logger.info(f"Processing entry: {getattr(entry, 'title', 'unknown')}")
        
        # Resolve link
        try:
            final_url = resolve_final_url(feed_link)
            logger.debug(f"Resolved URL: {feed_link} -> {final_url}")
        except (HTTPError, ValidationError) as e:
            logger.error(f"Failed to resolve URL {feed_link}: {e}")
            return
        
        domain = urlparse(final_url).netloc
        logger.debug(f"Domain: {domain}")

        # Extract chapter
        result = extract_chapter(final_url)
        
        if not result.passed_quality_check:
            logger.warning(f"Generic extraction failed for {final_url}, trying site override")
            resp = polite_get(final_url)
            if resp is None:
                logger.warning(f"Skipping {final_url}, blocked or unreachable")
                return
            
            override_text = extract_with_override(resp.text, domain)
            if override_text:
                result.text = override_text
                result.method = "site_override"
                result.passed_quality_check = True
                logger.info(f"Site override succeeded for {final_url}")
            else:
                logger.warning(f"No extraction succeeded for {final_url}, needs a new override entry")
                return

        # Save to database
        try:
            series_name = clean_series_name(getattr(entry, "title", "unknown"))
            chapter_summary = getattr(entry, "summary", "")
            save_chapter(
                db,
                url=final_url,
                series=series_name,
                chapter_label=chapter_summary,
                title=result.title or "Untitled",
                text=result.text,
                method=result.method,
            )
            
            # Extract and save series URL from the RSS summary
            series_url_match = re.search(r'https?://www\.novelupdates\.com/series/[^/\s]+/?', chapter_summary)
            if series_url_match:
                save_series_info(db, series=series_name, url=series_url_match.group(0))
            
            logger.info(f"Saved: {result.title} ({result.method})")
        except DatabaseError as e:
            logger.error(f"Failed to save chapter {final_url}: {e}")
            return
        except ValidationError as e:
            logger.error(f"Validation error saving chapter: {e}")
            return
            
    except Exception as e:
        logger.error(f"Unexpected error processing entry: {e}", exc_info=True)

def main():
    """Main entry point with proper initialization and cleanup."""
    global db
    
    setup_logging()
    settings = get_settings()
    
    logger.info("Starting novel scraper")
    
    try:
        db = init_storage(settings.CHAPTERS_DB)
        logger.info("Database initialized")
        
        run_forever(handle_new_entry)
        
    except DatabaseError as e:
        logger.error(f"Fatal database error: {e}")
        raise
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully")
    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        raise
    finally:
        if db:
            db.close()
            logger.info("Database connection closed")

if __name__ == "__main__":
    main()
