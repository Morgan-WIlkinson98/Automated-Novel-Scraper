"""
import_nu_export.py
One-time or repeatable import of a NovelUpdates reading-list JSON export
into the scraper's `series_info` table.
"""

import argparse
import json
import logging
import time
from pathlib import Path

from core.settings import get_settings
from core.utils import clean_series_name, novelupdates_series_url
from data.storage import init_storage

logger = logging.getLogger(__name__)


def find_latest_export(dir_path: str) -> str:
    """Find the most recently modified *.json file in a directory."""
    path = Path(dir_path)
    path.mkdir(parents=True, exist_ok=True)
    json_files = sorted(path.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not json_files:
        raise FileNotFoundError(f"No *.json reading-list exports found in {path}")
    return str(json_files[0])


def resolve_export_path(path: str) -> str:
    """Return a file path to import. If a directory is given, use the latest *.json."""
    candidate = Path(path)
    if candidate.is_dir():
        return find_latest_export(str(candidate))
    if candidate.is_file():
        return str(candidate)
    raise FileNotFoundError(f"Reading-list export not found: {path}")


def load_nu_export(path: str):
    """Load a NovelUpdates export file. Returns a list of list dicts."""
    data = Path(path).read_text(encoding="utf-8")
    return json.loads(data)


def import_export(export_path: str, db_path: str = None):
    """Import every item from the export into series_info."""
    if db_path is None:
        db_path = get_settings().CHAPTERS_DB

    export_path = resolve_export_path(export_path)
    export = load_nu_export(export_path)
    conn = init_storage(db_path)

    imported = 0
    rows = []
    now = time.time()

    for reading_list in export:
        list_name = reading_list.get("title", "Unknown")
        for item in reading_list.get("items", []):
            title = item.get("title") or "Unknown"
            series_name = clean_series_name(title)
            if not series_name or series_name == "Unknown":
                continue

            series_url = (
                item.get("rawChapterLink")
                or novelupdates_series_url(item.get("title") or "")
            )
            if not series_url:
                continue

            current_label = item.get("chapterStatus") or ""
            current_link = item.get("chapterLink") or ""
            latest_label = item.get("letestChapter") or ""
            latest_link = item.get("latestChapterLink") or ""

            rows.append((
                series_name, series_url, None, None,
                current_label, current_link,
                latest_label, latest_link,
                list_name, now, now,
            ))

    if rows:
        conn.executemany(
            """
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
                imported_at = excluded.imported_at,
                last_synced = excluded.last_synced
            """,
            rows,
        )
        conn.commit()
        imported = len(rows)

    conn.close()
    logger.info(f"Imported {imported} series from {export_path}")
    return imported


def main():
    parser = argparse.ArgumentParser(description="Import NovelUpdates reading-list export")
    parser.add_argument(
        "--export",
        default=None,
        help="Path to the NovelUpdates JSON export or a folder of exports (defaults to READING_LISTS_DIR)",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to the chapters database (defaults to settings.CHAPTERS_DB)",
    )
    args = parser.parse_args()

    export_path = args.export or get_settings().READING_LISTS_DIR

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    count = import_export(export_path, args.db)
    print(f"Imported {count} series into {args.db or get_settings().CHAPTERS_DB}")


if __name__ == "__main__":
    main()
