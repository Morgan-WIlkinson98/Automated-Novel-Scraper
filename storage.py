"""
storage.py
"""

import sqlite3
import logging
import time
from settings import get_settings
from exceptions import DatabaseError, ValidationError

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
