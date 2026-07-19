"""
rss_watcher.py
Depends on: feedparser, requests
    pip install feedparser requests
"""

import feedparser
import sqlite3
import logging
import time
import requests
from datetime import datetime
from pathlib import Path
from exceptions import DatabaseError, RSSFeedError, ValidationError

from settings import get_settings

logger = logging.getLogger(__name__)

def _get_config():
    """Get current settings."""
    return get_settings()


def init_db(path="seen_entries.db"):
    """Initialize SQLite database for tracking seen RSS entries."""
    try:
        conn = sqlite3.connect(path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_entries (
                guid TEXT PRIMARY KEY,
                link TEXT,
                first_seen REAL
            )
        """)
        conn.commit()
        logger.info(f"Database initialized at {path}")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize database at {path}: {e}")
        raise DatabaseError(f"Failed to initialize database: {e}") from e


def is_new_entry(conn, guid: str) -> bool:
    """Check if an RSS entry has been processed before."""
    try:
        if not guid:
            raise ValidationError("GUID cannot be empty")
        cur = conn.execute("SELECT 1 FROM seen_entries WHERE guid = ?", (guid,))
        is_new = cur.fetchone() is None
        logger.debug(f"Entry {guid} is_new={is_new}")
        return is_new
    except sqlite3.Error as e:
        logger.error(f"Database error checking entry {guid}: {e}")
        raise DatabaseError(f"Failed to check entry: {e}") from e


def mark_seen(conn, guid: str, link: str):
    """Mark an RSS entry as processed in the database."""
    try:
        if not guid or not link:
            raise ValidationError("GUID and link cannot be empty")
        conn.execute(
            "INSERT OR IGNORE INTO seen_entries (guid, link, first_seen) VALUES (?, ?, ?)",
            (guid, link, time.time()),
        )
        conn.commit()
        logger.debug(f"Marked entry {guid} as seen")
    except sqlite3.Error as e:
        logger.error(f"Failed to mark entry {guid} as seen: {e}")
        raise DatabaseError(f"Failed to mark entry: {e}") from e


def fetch_authenticated_feed(url: str) -> str:
    """Fetch RSS feed with authentication if credentials are provided."""
    try:
        config = _get_config()
        headers = {
            'User-Agent': config.USER_AGENT
        }
        
        # Use cookies if provided
        cookies = config.NOVELUPDATES_COOKIES if isinstance(config.NOVELUPDATES_COOKIES, dict) else None
        
        # Use basic auth if username/password provided
        auth = None
        if config.NOVELUPDATES_USERNAME and config.NOVELUPDATES_PASSWORD:
            auth = (config.NOVELUPDATES_USERNAME, config.NOVELUPDATES_PASSWORD)
            logger.info("Using username/password authentication for RSS feed")
        elif cookies:
            logger.info("Using cookie authentication for RSS feed")
        else:
            logger.info("Fetching RSS feed without authentication")
        
        response = requests.get(url, headers=headers, auth=auth, cookies=cookies, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"Failed to fetch RSS feed: {e}")
        raise RSSFeedError(f"Failed to fetch RSS feed: {e}") from e


def _get_rss_feeds_dir() -> Path:
    """Directory where raw RSS feed XML snapshots are stored."""
    settings = get_settings()
    feed_dir = Path(getattr(settings, 'EXPORT_DIR', 'exports')).parent / "rss_feeds"
    feed_dir.mkdir(parents=True, exist_ok=True)
    return feed_dir


def save_raw_rss_feed(content: str) -> Path:
    """Archive the raw RSS feed XML with a timestamp and keep a latest.xml copy."""
    feed_dir = _get_rss_feeds_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = feed_dir / f"feed_{timestamp}.xml"
    latest_path = feed_dir / "latest.xml"
    try:
        archive_path.write_text(content, encoding="utf-8")
        latest_path.write_text(content, encoding="utf-8")
        logger.info(f"Saved raw RSS feed to {archive_path} and {latest_path}")
    except Exception as e:
        logger.warning(f"Failed to save raw RSS feed: {e}")
    return archive_path


def poll_once(conn, on_new_entry):
    """Perform a single polling iteration of the RSS feed."""
    try:
        config = _get_config()
        logger.info(f"Polling RSS feed: {config.RSS_FEED_URL}")
        
        # Fetch feed with authentication
        feed_content = fetch_authenticated_feed(config.RSS_FEED_URL)
        
        # Store the raw XML for UI inspection
        save_raw_rss_feed(feed_content)
        
        # Parse the feed content
        feed = feedparser.parse(feed_content)
        
        if feed.bozo:
            logger.warning(f"Feed parsing warning: {feed.bozo_exception}")
        
        if not feed.entries:
            logger.warning(f"No entries found in feed")
            return
        
        logger.info(f"Found {len(feed.entries)} entries in feed")
        
        processed_count = 0
        for entry in feed.entries:
            try:
                guid = getattr(entry, "id", entry.link)
                if not guid:
                    logger.warning("Entry has no GUID or link, skipping")
                    continue
                
                if is_new_entry(conn, guid):
                    logger.info(f"Processing new entry: {getattr(entry, 'title', 'unknown')}")
                    on_new_entry(entry)
                    mark_seen(conn, guid, entry.link)
                    processed_count += 1
            except Exception as e:
                logger.error(f"Error processing entry: {e}")
                continue
        
        logger.info(f"Processed {processed_count} new entries")
        
    except Exception as e:
        logger.error(f"Failed to poll RSS feed: {e}")
        raise RSSFeedError(f"RSS feed polling failed: {e}") from e


def run_forever(on_new_entry):
    """Run the RSS watcher in a continuous loop."""
    config = _get_config()
    logger.info("Starting RSS watcher")
    conn = None
    try:
        conn = init_db(config.SEEN_ENTRIES_DB)
        while True:
            try:
                poll_once(conn, on_new_entry)
            except RSSFeedError as e:
                logger.error(f"Polling failed, will retry: {e}")
            except DatabaseError as e:
                logger.error(f"Database error, reinitializing connection: {e}")
                try:
                    if conn:
                        conn.close()
                    conn = init_db(config.SEEN_ENTRIES_DB)
                except Exception as e2:
                    logger.error(f"Failed to reinitialize database: {e2}")
                    time.sleep(config.POLL_INTERVAL_SECONDS)
                    continue
            
            logger.debug(f"Sleeping for {config.POLL_INTERVAL_SECONDS} seconds")
            time.sleep(config.POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("RSS watcher stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in RSS watcher: {e}")
        raise
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed")
