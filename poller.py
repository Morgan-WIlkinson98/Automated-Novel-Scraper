"""
poller.py
Single-pass cloud poller — designed for scheduled GitHub Actions runs.

One invocation = one poll: fetch the NovelUpdates RSS feed, process new
entries through the normal pipeline (resolve → extract → save), record
run metadata in Firestore, then exit. No daemon loop.

Required env (see .github/workflows/poll.yml):
    DB_TYPE=firestore
    RSS_FEED_URL                    — keyed personal feed (Actions secret)
    FIREBASE_REFRESH_TOKEN          — dedicated anonymous Firebase user
                                      (Actions secret; see README → Cloud Mode)
Optional:
    NOVELUPDATES_COOKIES            — JSON dict of session cookies
    SERIES_SYNC_INLINE=1            — run series-page sync inline (workflow sets this)
"""

import logging
import os
import sys
import time

logger = logging.getLogger(__name__)


def main() -> int:
    from core.logging_config import setup_logging
    setup_logging()

    from core.settings import get_settings
    settings = get_settings()

    if os.getenv("DB_TYPE", "sqlite").lower() != "firestore":
        logger.error("poller.py requires DB_TYPE=firestore")
        return 2
    if not settings.RSS_FEED_URL:
        logger.error("RSS_FEED_URL is not set")
        return 2
    if not settings.FIREBASE_REFRESH_TOKEN:
        logger.error("FIREBASE_REFRESH_TOKEN is not set")
        return 2

    from data import firestore_store
    from rss.rss_watcher import init_db, poll_once
    from main import handle_new_entry

    stats = {"processed": 0, "errors": []}

    def on_new_entry(entry, is_import=False):
        try:
            handle_new_entry(entry, is_import)
            stats["processed"] += 1
        except Exception as e:
            logger.exception("Entry processing failed")
            stats["errors"].append(str(e))

    started = time.time()
    status = "ok"
    try:
        firestore_store.init_storage()  # validate credentials up front
        conn = init_db()
        poll_once(conn, on_new_entry)
    except Exception as e:
        status = "failed"
        stats["errors"].append(str(e))
        logger.exception("Poll run failed")

    try:
        run_url = ""
        if os.getenv("GITHUB_RUN_ID"):
            run_url = (
                f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/"
                f"{os.getenv('GITHUB_REPOSITORY', '')}/actions/runs/{os.getenv('GITHUB_RUN_ID')}"
            )
        firestore_store.save_run_meta(
            firestore_store.init_storage(),
            status=status,
            processed=stats["processed"],
            errors=stats["errors"],
            duration_s=round(time.time() - started, 1),
            run_url=run_url,
        )
    except Exception as e:
        logger.error(f"Failed to write run metadata: {e}")

    elapsed = round(time.time() - started, 1)
    logger.info(f"Poll finished: {status} — {stats['processed']} new entries, {elapsed}s")
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
