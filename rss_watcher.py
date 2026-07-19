"""
rss_watcher.py
Depends on: feedparser
    pip install feedparser
"""

import feedparser
import sqlite3
import time

FEED_URL = "https://www.novelupdates.com/rss/"
POLL_INTERVAL_SECONDS = 15 * 60


def init_db(path="seen_entries.db"):
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_entries (
            guid TEXT PRIMARY KEY,
            link TEXT,
            first_seen REAL
        )
    """)
    conn.commit()
    return conn


def is_new_entry(conn, guid: str) -> bool:
    cur = conn.execute("SELECT 1 FROM seen_entries WHERE guid = ?", (guid,))
    return cur.fetchone() is None


def mark_seen(conn, guid: str, link: str):
    conn.execute(
        "INSERT OR IGNORE INTO seen_entries (guid, link, first_seen) VALUES (?, ?, ?)",
        (guid, link, time.time()),
    )
    conn.commit()


def poll_once(conn, on_new_entry):
    feed = feedparser.parse(FEED_URL)
    for entry in feed.entries:
        guid = getattr(entry, "id", entry.link)
        if is_new_entry(conn, guid):
            on_new_entry(entry)
            mark_seen(conn, guid, entry.link)


def run_forever(on_new_entry):
    conn = init_db()
    while True:
        poll_once(conn, on_new_entry)
        time.sleep(POLL_INTERVAL_SECONDS)
