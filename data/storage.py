"""
storage.py
"""

import os
import logging
import sqlite3
import time
from core.settings import get_settings
from core.exceptions import DatabaseError, ValidationError
from core.database_manager import get_database_manager

logger = logging.getLogger(__name__)

_EXTRA_SERIES_COLUMNS = {
    'current_chapter_label': 'TEXT',
    'current_chapter_link': 'TEXT',
    'latest_chapter_label': 'TEXT',
    'latest_chapter_link': 'TEXT',
    'reading_list_name': 'TEXT',
    'imported_at': 'REAL',
}

_EXTRA_CHAPTER_COLUMNS = {
    'translator_group': 'TEXT',
    'nu_link': 'TEXT',
}


def _ensure_series_info_columns(conn):
    """Add any missing NovelUpdates reading-list columns to series_info."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(series_info)")}
    for column, col_type in _EXTRA_SERIES_COLUMNS.items():
        if column not in existing:
            try:
                conn.execute(f"ALTER TABLE series_info ADD COLUMN {column} {col_type}")
                logger.info(f"Added missing column '{column}' to series_info")
            except sqlite3.OperationalError:
                pass
    conn.commit()


def _ensure_chapter_columns(conn):
    """Add any missing columns to chapters (e.g. translator_group for
    multi-group archives)."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(chapters)")}
    for column, col_type in _EXTRA_CHAPTER_COLUMNS.items():
        if column not in existing:
            try:
                conn.execute(f"ALTER TABLE chapters ADD COLUMN {column} {col_type}")
                logger.info(f"Added missing column '{column}' to chapters")
            except sqlite3.OperationalError:
                pass
    conn.commit()


def init_storage(path=None):
    """Initialize the chapters database."""
    db_manager = get_database_manager()

    if db_manager.db_type == "firestore":
        from data import firestore_store
        return firestore_store.init_storage(path)

    # Only handle SQLite-specific initialization for backwards compatibility
    if os.getenv("DB_TYPE", "sqlite").lower() == "sqlite":
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
            _ensure_series_info_columns(conn)
            _ensure_chapter_columns(conn)
            conn.commit()
            logger.info(f"Storage database initialized at {path}")
            return conn
        except Exception as e:
            logger.error(f"Failed to initialize storage database at {path}: {e}")
            raise DatabaseError(f"Failed to initialize storage database: {e}") from e
    else:
        # PostgreSQL tables are created by the init script
        logger.info("Using PostgreSQL - tables created by initialization script")
        return db_manager


def save_chapter(conn, url, series, chapter_label, title, text, method,
                 group=None, nu_link=None):
    """Save a chapter to the database. `group` is the translator/release
    group name from the NU releases table (None for RSS-sourced saves).
    `nu_link` is the NU /extnu/ release link — kept so group data can be
    healed onto the row later without re-resolving the redirect."""
    try:
        # Validate inputs
        if not url or not isinstance(url, str):
            raise ValidationError("URL cannot be empty")
        if not text or not isinstance(text, str):
            raise ValidationError("Text cannot be empty")

        db_manager = get_database_manager()

        if db_manager.db_type == "firestore":
            from data import firestore_store
            return firestore_store.save_chapter(conn, url, series, chapter_label, title, text, method, group, nu_link)
        elif db_manager.db_type == "sqlite":
            _ensure_chapter_columns(conn)
            conn.execute("""
                INSERT OR IGNORE INTO chapters
                (url, series, chapter_label, title, text, extraction_method, fetched_at, translator_group, nu_link)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (url, series, chapter_label, title, text, method, time.time(), group, nu_link))
            conn.commit()
        else:
            # PostgreSQL uses different syntax for INSERT ... ON CONFLICT
            with db_manager.connect() as pg_conn:
                pg_conn.execute("""
                    INSERT INTO chapters
                    (url, series, chapter_label, title, text, extraction_method, fetched_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO NOTHING
                """, (url, series, chapter_label, title, text, method, time.time()))
                pg_conn.commit()
        
        logger.info(f"Saved chapter: {title} ({method})")
    except Exception as e:
        logger.error(f"Failed to save chapter {url}: {e}")
        raise DatabaseError(f"Failed to save chapter: {e}") from e


def heal_chapter_groups(conn, series, release_rows):
    """Self-heal — backfill translator group onto chapters whose NU
    release link is known but that predate group capture. Called after
    a series-page sync refreshes the release table, so the database
    heals itself on natural updates instead of needing a migration.
    Returns the number of chapters patched."""
    db_manager = get_database_manager()
    if db_manager.db_type == "firestore":
        from data import firestore_store
        return firestore_store.heal_chapter_groups(conn, series, release_rows)
    if db_manager.db_type != "sqlite":
        return 0
    _ensure_chapter_columns(conn)
    group_by_link = {
        c.get('extnu_url'): c.get('group')
        for c in (release_rows or [])
        if c.get('extnu_url') and c.get('group')
    }
    if not group_by_link:
        return 0
    rows = conn.execute(
        """SELECT url, nu_link FROM chapters
           WHERE series = ? AND (translator_group IS NULL OR translator_group = '')""",
        (series,),
    ).fetchall()
    healed = 0
    for url, nu_link in rows:
        g = group_by_link.get(nu_link)
        if g:
            conn.execute(
                "UPDATE chapters SET translator_group = ? WHERE url = ?",
                (g, url))
            healed += 1
    if healed:
        conn.commit()
    return healed


def save_series_info(
    conn,
    series: str,
    url: str = None,
    synopsis: str = None,
    available_chapters: str = None,
    current_chapter_label: str = None,
    current_chapter_link: str = None,
    latest_chapter_label: str = None,
    latest_chapter_link: str = None,
    reading_list_name: str = None,
    imported_at: float = None,
):
    """Save or update metadata for a series. Only overwrites fields that are provided (non-None)."""
    try:
        if not series:
            raise ValidationError("Series name cannot be empty")
        
        db_manager = get_database_manager()

        if db_manager.db_type == "firestore":
            from data import firestore_store
            return firestore_store.save_series_info(
                conn, series, url, synopsis, available_chapters,
                current_chapter_label, current_chapter_link,
                latest_chapter_label, latest_chapter_link,
                reading_list_name, imported_at,
            )
        elif db_manager.db_type == "sqlite":
            conn.execute("""
                INSERT INTO series_info (
                    series, url, synopsis, available_chapters,
                    current_chapter_label, current_chapter_link,
                    latest_chapter_label, latest_chapter_link,
                    reading_list_name, imported_at, last_synced
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(series) DO UPDATE SET
                    url = COALESCE(excluded.url, series_info.url),
                    synopsis = COALESCE(excluded.synopsis, series_info.synopsis),
                    available_chapters = COALESCE(excluded.available_chapters, series_info.available_chapters),
                    current_chapter_label = COALESCE(excluded.current_chapter_label, series_info.current_chapter_label),
                    current_chapter_link = COALESCE(excluded.current_chapter_link, series_info.current_chapter_link),
                    latest_chapter_label = COALESCE(excluded.latest_chapter_label, series_info.latest_chapter_label),
                    latest_chapter_link = COALESCE(excluded.latest_chapter_link, series_info.latest_chapter_link),
                    reading_list_name = COALESCE(excluded.reading_list_name, series_info.reading_list_name),
                    imported_at = COALESCE(excluded.imported_at, series_info.imported_at),
                    last_synced = excluded.last_synced
            """, (
                series, url, synopsis, available_chapters,
                current_chapter_label, current_chapter_link,
                latest_chapter_label, latest_chapter_link,
                reading_list_name, imported_at, time.time()
            ))
            conn.commit()
        else:
            # PostgreSQL version
            with db_manager.connect() as pg_conn:
                pg_conn.execute("""
                    INSERT INTO series_info (
                        series, url, synopsis, available_chapters,
                        current_chapter_label, current_chapter_link,
                        latest_chapter_label, latest_chapter_link,
                        reading_list_name, imported_at, last_synced
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (series) DO UPDATE SET
                        url = COALESCE(EXCLUDED.url, series_info.url),
                        synopsis = COALESCE(EXCLUDED.synopsis, series_info.synopsis),
                        available_chapters = COALESCE(EXCLUDED.available_chapters, series_info.available_chapters),
                        current_chapter_label = COALESCE(EXCLUDED.current_chapter_label, series_info.current_chapter_label),
                        current_chapter_link = COALESCE(EXCLUDED.current_chapter_link, series_info.current_chapter_link),
                        latest_chapter_label = COALESCE(EXCLUDED.latest_chapter_label, series_info.latest_chapter_label),
                        latest_chapter_link = COALESCE(EXCLUDED.latest_chapter_link, series_info.latest_chapter_link),
                        reading_list_name = COALESCE(EXCLUDED.reading_list_name, series_info.reading_list_name),
                        imported_at = COALESCE(EXCLUDED.imported_at, series_info.imported_at),
                        last_synced = EXCLUDED.last_synced
                """, (
                    series, url, synopsis, available_chapters,
                    current_chapter_label, current_chapter_link,
                    latest_chapter_label, latest_chapter_link,
                    reading_list_name, imported_at, time.time()
                ))
                pg_conn.commit()
        
        logger.info(f"Saved series info for: {series}")
    except Exception as e:
        logger.error(f"Failed to save series info for {series}: {e}")
        raise DatabaseError(f"Failed to save series info: {e}") from e


def get_series_info(conn, series: str):
    """Get metadata for a series."""
    try:
        db_manager = get_database_manager()

        if db_manager.db_type == "firestore":
            from data import firestore_store
            return firestore_store.get_series_info(conn, series)
        elif db_manager.db_type == "sqlite":
            cursor = conn.execute(
                """SELECT url, synopsis, available_chapters,
                          current_chapter_label, current_chapter_link,
                          latest_chapter_label, latest_chapter_link,
                          reading_list_name, imported_at, last_synced
                   FROM series_info WHERE series = ?""",
                (series,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    'url': row[0],
                    'synopsis': row[1],
                    'available_chapters': row[2],
                    'current_chapter_label': row[3],
                    'current_chapter_link': row[4],
                    'latest_chapter_label': row[5],
                    'latest_chapter_link': row[6],
                    'reading_list_name': row[7],
                    'imported_at': row[8],
                    'last_synced': row[9],
                }
        else:
            # PostgreSQL version
            with db_manager.connect() as pg_conn:
                cursor = pg_conn.execute(
                    """SELECT url, synopsis, available_chapters,
                              current_chapter_label, current_chapter_link,
                              latest_chapter_label, latest_chapter_link,
                              reading_list_name, imported_at, last_synced
                       FROM series_info WHERE series = %s""",
                    (series,)
                )
                row = cursor.fetchone()
                if row:
                    return row
        
        return {}
    except Exception as e:
        logger.error(f"Failed to get series info for {series}: {e}")
        raise DatabaseError(f"Failed to get series info: {e}") from e
