"""
import_sqlite.py
One-off migration of the local SQLite data into Firestore (cloud mode).

Reads chapters.db (chapters + series_info) and seen_entries.db and writes
them through data.firestore_store — same dedup keys the poller uses, so
migrated data won't be re-fetched.

Usage:
    export FIREBASE_SERVICE_ACCOUNT_JSON="$(cat service-account.json)"
    python tools/import_sqlite.py \
        --chapters-db chapters.db --seen-db seen_entries.db [--dry-run]
"""

import argparse
import logging
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DB_TYPE", "firestore")

logger = logging.getLogger(__name__)


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _series_columns(conn) -> set:
    return {row[1] for row in conn.execute("PRAGMA table_info(series_info)")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--chapters-db", default="chapters.db")
    parser.add_argument("--seen-db", default="seen_entries.db")
    parser.add_argument("--dry-run", action="store_true", help="Count rows only, write nothing")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not os.path.exists(args.chapters_db):
        logger.error(f"Chapters database not found: {args.chapters_db}")
        return 1

    store = None
    fs = None
    if not args.dry_run:
        from data import firestore_store as fs
        store = fs.init_storage()

    chapters = sqlite3.connect(args.chapters_db)
    chapters.row_factory = sqlite3.Row

    # --- series_info ---
    if _table_exists(chapters, "series_info"):
        cols = _series_columns(chapters)
        n = 0
        for row in chapters.execute("SELECT * FROM series_info"):
            info = {
                "series": row["series"],
                "url": row["url"],
                "synopsis": row["synopsis"],
                "available_chapters": row["available_chapters"],
            }
            for col in (
                "current_chapter_label", "current_chapter_link",
                "latest_chapter_label", "latest_chapter_link",
                "reading_list_name", "imported_at",
            ):
                if col in cols:
                    info[col] = row[col]
            if store:
                fs.save_series_info(store, **info)
            n += 1
        logger.info(f"series_info: {n} rows {'(dry run)' if not store else 'migrated'}")
    else:
        logger.info("No series_info table — skipping")

    # --- chapters ---
    n = 0
    for row in chapters.execute(
        "SELECT url, series, chapter_label, title, text, extraction_method FROM chapters"
    ):
        if store:
            fs.save_chapter(
                store, row["url"], row["series"], row["chapter_label"],
                row["title"], row["text"], row["extraction_method"],
            )
        n += 1
    logger.info(f"chapters: {n} rows {'(dry run)' if not store else 'migrated'}")

    # --- seen_entries ---
    if os.path.exists(args.seen_db):
        seen = sqlite3.connect(args.seen_db)
        n = 0
        for row in seen.execute("SELECT guid, link FROM seen_entries"):
            if store:
                fs.mark_seen(store, row[0], row[1])
            n += 1
        logger.info(f"seen_entries: {n} rows {'(dry run)' if not store else 'migrated'}")
    else:
        logger.info(f"No seen database at {args.seen_db} — skipping")

    logger.info("Migration complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
