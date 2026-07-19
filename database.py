"""
database.py
Database connection manager with context managers.
"""

import sqlite3
import logging
from contextlib import contextmanager
from exceptions import DatabaseError

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLite database connections."""
    
    def __init__(self, path: str, init_sql: str):
        self.path = path
        self.init_sql = init_sql
    
    @contextmanager
    def connect(self):
        """Context manager for database connections."""
        conn = None
        try:
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            yield conn
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            raise DatabaseError(f"Database error: {e}") from e
        finally:
            if conn:
                conn.close()
    
    def initialize(self):
        """Initialize the database with the schema."""
        try:
            with self.connect() as conn:
                conn.execute(self.init_sql)
                conn.commit()
                logger.info(f"Database initialized: {self.path}")
        except Exception as e:
            raise DatabaseError(f"Failed to initialize database {self.path}: {e}") from e
    
    def execute(self, query: str, params: tuple = ()):
        """Execute a query and return cursor."""
        try:
            with self.connect() as conn:
                cursor = conn.execute(query, params)
                conn.commit()
                return cursor
        except sqlite3.Error as e:
            logger.error(f"Query failed: {query} with {params}: {e}")
            raise DatabaseError(f"Failed to execute query: {e}") from e
    
    def fetchall(self, query: str, params: tuple = ()) -> list:
        """Fetch all rows as list of dictionaries."""
        try:
            with self.connect() as conn:
                cursor = conn.execute(query, params)
                return [dict(row) for row in cursor]
        except sqlite3.Error as e:
            logger.error(f"Fetch failed: {query}: {e}")
            raise DatabaseError(f"Failed to fetch: {e}") from e
    
    def fetchone(self, query: str, params: tuple = ()) -> dict | None:
        """Fetch one row as dictionary or None."""
        try:
            with self.connect() as conn:
                cursor = conn.execute(query, params)
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Fetch failed: {query}: {e}")
            raise DatabaseError(f"Failed to fetch: {e}") from e
