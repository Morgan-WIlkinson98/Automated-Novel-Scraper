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
import hashlib
from datetime import datetime
from pathlib import Path
from core.exceptions import DatabaseError, RSSFeedError, ValidationError

from core.settings import get_settings

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


def _get_xml_exports_dir() -> Path:
    """Directory where RSS feed XML exports are stored for catalog building."""
    xml_dir = Path("data") / "xml_exports"
    xml_dir.mkdir(parents=True, exist_ok=True)
    return xml_dir


def _get_periodic_export_dir() -> Path:
    """Directory where periodic RSS feed XML exports are stored for user access."""
    settings = get_settings()
    export_dir = Path(settings.EXPORT_DIR)
    periodic_dir = export_dir / "rss_exports"
    periodic_dir.mkdir(parents=True, exist_ok=True)
    return periodic_dir


def _get_content_hash(content: str) -> str:
    """Generate a hash of the content for duplicate detection."""
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def _is_duplicate_content(content: str, export_dir: Path) -> bool:
    """Check if content already exists in the export directory."""
    content_hash = _get_content_hash(content)
    
    # Check if any existing file has the same hash
    for existing_file in export_dir.glob("rss_export_*.xml"):
        try:
            existing_content = existing_file.read_text(encoding="utf-8")
            if _get_content_hash(existing_content) == content_hash:
                logger.debug(f"Duplicate content detected, skipping export (matches {existing_file.name})")
                return True
        except Exception as e:
            logger.warning(f"Error reading existing file {existing_file.name}: {e}")
            continue
    
    return False


def save_periodic_rss_export(content: str) -> Path:
    """Save RSS feed to periodic export directory with duplicate detection."""
    periodic_dir = _get_periodic_export_dir()
    
    # Skip if duplicate content
    if _is_duplicate_content(content, periodic_dir):
        logger.info("Skipping periodic RSS export - duplicate content")
        return None
    
    # Save with timestamp including microseconds for uniqueness
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    export_path = periodic_dir / f"rss_export_{timestamp}.xml"
    
    try:
        export_path.write_text(content, encoding="utf-8")
        logger.info(f"Saved periodic RSS export to {export_path}")
        return export_path
    except Exception as e:
        logger.error(f"Failed to save periodic RSS export: {e}")
        return None


# Track last periodic export time
_last_periodic_export_time = 0
_PERIODIC_EXPORT_INTERVAL = 15 * 60  # 15 minutes in seconds


def trigger_periodic_export(content: str) -> Path:
    """Force an immediate periodic export regardless of time interval."""
    return save_periodic_rss_export(content)


def save_raw_rss_feed(content: str) -> Path:
    """Archive the raw RSS feed XML with a timestamp and keep a latest.xml copy."""
    global _last_periodic_export_time
    
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
    
    # Also save to xml_exports directory
    xml_exports_dir = _get_xml_exports_dir()
    xml_export_path = xml_exports_dir / f"feed_{timestamp}.xml"
    try:
        xml_export_path.write_text(content, encoding="utf-8")
        logger.info(f"Saved RSS feed export to {xml_export_path}")
    except Exception as e:
        logger.warning(f"Failed to save RSS feed export: {e}")
    
    # Check if it's time for periodic export to main export directory
    current_time = time.time()
    if current_time - _last_periodic_export_time >= _PERIODIC_EXPORT_INTERVAL:
        save_periodic_rss_export(content)
        _last_periodic_export_time = current_time
    
    return archive_path


def load_xml_exports(on_new_entry):
    """Load and process all XML files from the xml_exports directory."""
    xml_dir = _get_xml_exports_dir()
    
    if not xml_dir.exists():
        logger.info(f"XML exports directory does not exist: {xml_dir}")
        return
    
    xml_files = sorted(xml_dir.glob("*.xml"))
    
    if not xml_files:
        logger.info(f"No XML files found in {xml_dir}")
        return
    
    logger.info(f"Found {len(xml_files)} XML files in {xml_dir}")
    
    processed_count = 0
    for xml_file in xml_files:
        try:
            logger.info(f"Processing XML file: {xml_file.name}")
            content = xml_file.read_text(encoding="utf-8")
            
            # Parse the feed content
            feed = feedparser.parse(content)
            
            if feed.bozo:
                logger.warning(f"Feed parsing warning for {xml_file.name}: {feed.bozo_exception}")
            
            if not feed.entries:
                logger.warning(f"No entries found in {xml_file.name}")
                continue
            
            logger.info(f"Found {len(feed.entries)} entries in {xml_file.name}")
            
            for entry in feed.entries:
                try:
                    guid = getattr(entry, "id", entry.link)
                    if not guid:
                        logger.warning("Entry has no GUID or link, skipping")
                        continue
                    
                    # Process the entry (without database tracking since these are imports)
                    logger.info(f"Processing imported entry: {getattr(entry, 'title', 'unknown')}")
                    on_new_entry(entry, is_import=True)
                    processed_count += 1
                except Exception as e:
                    logger.error(f"Error processing entry from {xml_file.name}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Failed to process XML file {xml_file.name}: {e}")
            continue
    
    logger.info(f"Processed {processed_count} entries from XML exports")


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
                    on_new_entry(entry, is_import=False)
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
