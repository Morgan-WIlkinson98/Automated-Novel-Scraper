"""
database_manager.py
Unified database manager supporting both SQLite and PostgreSQL.
"""

import os
import logging
from contextlib import contextmanager
from typing import Optional, Dict, Any
from core.exceptions import DatabaseError

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections with support for SQLite and PostgreSQL."""
    
    def __init__(self, db_type: str = "sqlite", **kwargs):
        """
        Initialize database manager.
        
        Args:
            db_type: "sqlite" or "postgresql"
            **kwargs: Database connection parameters
                For SQLite: path (str)
                For PostgreSQL: host, port, database, user, password
        """
        self.db_type = db_type.lower()
        self.connection_params = kwargs
        
        if self.db_type == "sqlite":
            self.path = kwargs.get("path", "chapters.db")
        elif self.db_type == "postgresql":
            self.host = kwargs.get("host", "localhost")
            self.port = kwargs.get("port", 5432)
            self.database = kwargs.get("database", "novel_scraper")
            self.user = kwargs.get("user", "postgres")
            self.password = kwargs.get("password", "")
        elif self.db_type == "firestore":
            pass  # no connection params — data.firestore_store owns the client
        else:
            raise ValueError(f"Unsupported database type: {db_type}")
    
    @contextmanager
    def connect(self):
        """Context manager for database connections."""
        if self.db_type == "firestore":
            raise DatabaseError("Firestore has no connect(); use data.firestore_store")
        conn = None
        try:
            if self.db_type == "sqlite":
                import sqlite3
                conn = sqlite3.connect(self.path)
                conn.row_factory = sqlite3.Row
            elif self.db_type == "postgresql":
                import psycopg2
                conn = psycopg2.connect(
                    host=self.host,
                    port=self.port,
                    database=self.database,
                    user=self.user,
                    password=self.password
                )
                conn.row_factory = dict_factory
            
            yield conn
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise DatabaseError(f"Database connection error: {e}") from e
        finally:
            if conn:
                conn.close()
    
    def initialize(self, schema_sql: str):
        """Initialize the database with the provided schema."""
        try:
            with self.connect() as conn:
                conn.execute(schema_sql)
                conn.commit()
                logger.info(f"Database initialized: {self.db_type}")
        except Exception as e:
            raise DatabaseError(f"Failed to initialize database: {e}") from e
    
    def execute(self, query: str, params: tuple = ()):
        """Execute a query and return cursor."""
        try:
            with self.connect() as conn:
                cursor = conn.execute(query, params)
                conn.commit()
                return cursor
        except Exception as e:
            logger.error(f"Query failed: {query} with {params}: {e}")
            raise DatabaseError(f"Failed to execute query: {e}") from e
    
    def fetchall(self, query: str, params: tuple = ()) -> list:
        """Fetch all rows as list of dictionaries."""
        try:
            with self.connect() as conn:
                cursor = conn.execute(query, params)
                if self.db_type == "sqlite":
                    return [dict(row) for row in cursor]
                else:
                    return [row for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Fetch failed: {query}: {e}")
            raise DatabaseError(f"Failed to fetch: {e}") from e
    
    def fetchone(self, query: str, params: tuple = ()) -> Optional[dict]:
        """Fetch one row as dictionary or None."""
        try:
            with self.connect() as conn:
                cursor = conn.execute(query, params)
                row = cursor.fetchone()
                if row:
                    if self.db_type == "sqlite":
                        return dict(row)
                    else:
                        return row
                return None
        except Exception as e:
            logger.error(f"Fetch failed: {query}: {e}")
            raise DatabaseError(f"Failed to fetch: {e}") from e


def dict_factory(cursor, row):
    """Factory function for PostgreSQL to return dict-like rows."""
    result = {}
    for idx, col_desc in enumerate(cursor.description):
        result[col_desc.name] = row[idx]
    return result


def get_database_manager() -> DatabaseManager:
    """Get configured database manager based on environment variables."""
    db_type = os.getenv("DB_TYPE", "sqlite").lower()
    
    if db_type == "firestore":
        return DatabaseManager(db_type="firestore")

    if db_type == "postgresql":
        return DatabaseManager(
            db_type="postgresql",
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "novel_scraper"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "")
        )
    else:
        # Default to SQLite
        from core.settings import get_settings
        settings = get_settings()
        return DatabaseManager(
            db_type="sqlite",
            path=settings.CHAPTERS_DB
        )
