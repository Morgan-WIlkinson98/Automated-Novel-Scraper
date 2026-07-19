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
from exceptions import DatabaseError, RSSFeedError, ValidationError

logger = logging.getLogger(__name__)

# Try to import config, use defaults if not available
try:
    from config import (
        RSS_FEED_URL,
        POLL_INTERVAL_SECONDS,
        NOVELUPDATES_USERNAME,
        NOVELUPDATES_PASSWORD,
        NOVELUPDATES_COOKIES,
    )
except ImportError:
    RSS_FEED_URL = "https://www.novelupdates.com/rss/"
    POLL_INTERVAL_SECONDS = 15 * 60
    NOVELUPDATES_USERNAME = None
    NOVELUPDATES_PASSWORD = None
    NOVELUPDATES_COOKIES = None


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
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; NovelScraper/1.0)'
        }
        
        # Use cookies if provided
        cookies = NOVELUPDATES_COOKIES if NOVELUPDATES_COOKIES else None
        
        # Use basic auth if username/password provided
        auth = None
        if NOVELUPDATES_USERNAME and NOVELUPDATES_PASSWORD:
            auth = (NOVELUPDATES_USERNAME, NOVELUPDATES_PASSWORD)
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


def poll_once(conn, on_new_entry):
    """Perform a single polling iteration of the RSS feed."""
    try:
        logger.info(f"Polling RSS feed: {FEED_URL}")
        
        # Fetch feed with authentication
        feed_content = fetch_authenticated_feed(FEED_URL)
        
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
    logger.info("Starting RSS watcher")
    conn = None
    try:
        conn = init_db()
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
                    conn = init_db()
                except Exception as e2:
                    logger.error(f"Failed to reinitialize database: {e2}")
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue
            
            logger.debug(f"Sleeping for {POLL_INTERVAL_SECONDS} seconds")
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("RSS watcher stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in RSS watcher: {e}")
        raise
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed")
