"""
storage.py
"""

import sqlite3
import time

def init_storage(path="chapters.db"):
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
    return conn

def save_chapter(conn, url, series, chapter_label, title, text, method):
    conn.execute("""
        INSERT OR IGNORE INTO chapters
        (url, series, chapter_label, title, text, extraction_method, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (url, series, chapter_label, title, text, method, time.time()))
    conn.commit()
