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

    from data import firestore_store as fs
    store = None
    if not args.dry_run:
        store = fs.init_storage()

    chapters = sqlite3.connect(args.chapters_db)
    chapters.row_factory = sqlite3.Row

    # --- series_info ---
    if _table_exists(chapters, "series_info"):
        cols = _series_columns(chapters)
        # Series actually holding chapters — noise feed rows get skipped
        # unless they're on the reading list or have real metadata.
        have_chapters = {r[0] for r in chapters.execute("SELECT DISTINCT series FROM chapters")}
        docs, skipped = [], 0
        for row in chapters.execute("SELECT * FROM series_info"):
            has_list = "reading_list_name" in cols and row["reading_list_name"]
            if row["series"] not in have_chapters and not has_list and not row["synopsis"]:
                skipped += 1
                continue
            slug = fs._slugify(row["series"])
            info = {
                "name": row["series"],
                "slug": slug,
                "url": row["url"],
                "synopsis": row["synopsis"],
                "availableChapters": row["available_chapters"],
            }
            col_map = {
                "current_chapter_label": "currentLabel",
                "current_chapter_link": "currentLink",
                "latest_chapter_label": "latestLabel",
                "latest_chapter_link": "latestLink",
                "reading_list_name": "listName",
                "imported_at": "importedAt",
            }
            for col, field in col_map.items():
                if col in cols and row[col] is not None:
                    info[field] = row[col]
            docs.append((f"novels/{slug}", info))
        if store:
            fs.bulk_upsert(docs)
        logger.info(
            f"series_info: {len(docs)} rows {'(dry run)' if not store else 'migrated'}"
            f", {skipped} noise rows skipped")
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
        import time as _time
        seen = sqlite3.connect(args.seen_db)
        docs = [
            (f"{fs.SEEN_COL}/{fs._hash(row[0])}",
             {"guid": row[0], "link": row[1], "firstSeen": _time.time()})
            for row in seen.execute("SELECT guid, link FROM seen_entries")
        ]
        if store:
            fs.bulk_upsert(docs)
        logger.info(f"seen_entries: {len(docs)} rows {'(dry run)' if not store else 'migrated'}")
    else:
        logger.info(f"No seen database at {args.seen_db} — skipping")

    logger.info("Migration complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
