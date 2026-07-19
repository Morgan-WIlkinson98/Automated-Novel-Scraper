"""
main.py
Ties together: rss_watcher, link_resolver, generic_extractor,
site_overrides, storage, politeness
"""

import logging
from urllib.parse import urlparse
from rss_watcher import run_forever
from link_resolver import resolve_final_url
from generic_extractor import extract_chapter
from site_overrides import extract_with_override
from storage import init_storage, save_chapter
from politeness import polite_get
from exceptions import DatabaseError, HTTPError, ValidationError

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

db = None

def handle_new_entry(entry):
    """Process a new RSS entry through the complete pipeline."""
    try:
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
            save_chapter(
                db,
                url=final_url,
                series=getattr(entry, "title", "unknown"),
                chapter_label=getattr(entry, "summary", ""),
                title=result.title or "Untitled",
                text=result.text,
                method=result.method,
            )
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
    
    logger.info("Starting novel scraper")
    
    try:
        db = init_storage()
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
