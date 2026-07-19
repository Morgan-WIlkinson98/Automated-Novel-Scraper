"""
storage.py
"""

import sqlite3
import logging
import time
from core.settings import get_settings
from core.exceptions import DatabaseError, ValidationError

logger = logging.getLogger(__name__)

def init_storage(path=None):
    """Initialize the chapters database."""
    if path is None:
        path = get_settings().CHAPTERS_DB
    try:
        conn = sqlite3.connect(path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chapters (
                url TEXT PRIMARY KEY,
                series TEXT,
                chapter_label TEXT,
                title TEXT,
                text TEXT,
                extraction_method TEXT,
                fetched_at REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS series_info (
                series TEXT PRIMARY KEY,
                url TEXT,
                synopsis TEXT,
                available_chapters TEXT,
                last_synced REAL
            )
        """)
        conn.commit()
        logger.info(f"Storage database initialized at {path}")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize storage database at {path}: {e}")
        raise DatabaseError(f"Failed to initialize storage database: {e}") from e


def save_chapter(conn, url, series, chapter_label, title, text, method):
    """Save a chapter to the database."""
    try:
        # Validate inputs
        if not url or not isinstance(url, str):
            raise ValidationError("URL cannot be empty")
        if not text or not isinstance(text, str):
            raise ValidationError("Text cannot be empty")
        
        conn.execute("""
            INSERT OR IGNORE INTO chapters
            (url, series, chapter_label, title, text, extraction_method, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (url, series, chapter_label, title, text, method, time.time()))
        conn.commit()
        logger.info(f"Saved chapter: {title} ({method})")
    except sqlite3.Error as e:
        logger.error(f"Failed to save chapter {url}: {e}")
        raise DatabaseError(f"Failed to save chapter: {e}") from e


def save_series_info(conn, series: str, url: str = None, synopsis: str = None, available_chapters: str = None):
    """Save or update metadata for a series. Only overwrites fields that are provided (non-None)."""
    try:
        if not series:
            raise ValidationError("Series name cannot be empty")
        conn.execute("""
            INSERT INTO series_info (series, url, synopsis, available_chapters, last_synced)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(series) DO UPDATE SET
                url = COALESCE(excluded.url, series_info.url),
                synopsis = COALESCE(excluded.synopsis, series_info.synopsis),
                available_chapters = COALESCE(excluded.available_chapters, series_info.available_chapters),
                last_synced = excluded.last_synced
        """, (series, url, synopsis, available_chapters, time.time()))
        conn.commit()
        logger.info(f"Saved series info for: {series}")
    except sqlite3.Error as e:
        logger.error(f"Failed to save series info for {series}: {e}")
        raise DatabaseError(f"Failed to save series info: {e}") from e


def get_series_info(conn, series: str):
    """Get metadata for a series."""
    try:
        cursor = conn.execute("SELECT url, synopsis, available_chapters, last_synced FROM series_info WHERE series = ?", (series,))
        row = cursor.fetchone()
        if row:
            return {
                'url': row[0],
                'synopsis': row[1],
                'available_chapters': row[2],
                'last_synced': row[3],
            }
        return {}
    except sqlite3.Error as e:
        logger.error(f"Failed to get series info for {series}: {e}")
        raise DatabaseError(f"Failed to get series info: {e}") from e
