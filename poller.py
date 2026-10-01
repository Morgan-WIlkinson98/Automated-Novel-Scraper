"""
poller.py
Single-pass cloud poller — designed for scheduled GitHub Actions runs.

One invocation = one poll: fetch the NovelUpdates RSS feed, process new
entries through the normal pipeline (resolve → extract → save), record
run metadata in Firestore, then exit. No daemon loop.

Required env (see .github/workflows/poll.yml):
    DB_TYPE=firestore
    RSS_FEED_URL                    — keyed personal feed (Actions secret)
    FIREBASE_SERVICE_ACCOUNT_JSON   — GCP SA key JSON (Actions secret;
                                      see README → Cloud Mode)
Optional:
    NOVELUPDATES_COOKIES            — JSON dict of session cookies
    SERIES_SYNC_INLINE=1            — run series-page sync inline (workflow sets this)
    NU_HEADED=1                     — run Playwright headed; required to clear
                                      NU's Cloudflare challenge (headless never
                                      does). CI runs it under xvfb (poll.yml).
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
    if not settings.FIREBASE_SERVICE_ACCOUNT_JSON:
        logger.error("FIREBASE_SERVICE_ACCOUNT_JSON is not set")
        return 2

    from data import firestore_store
    from rss.rss_watcher import init_db, poll_once
    from main import handle_new_entry

    stats = {"processed": 0, "errors": []}

    def on_new_entry(entry, is_import=False):
        try:
            ok = handle_new_entry(entry, is_import)
        except Exception as e:
            logger.exception("Entry processing failed")
            stats["errors"].append(str(e))
            raise
        if ok is False:
            stats["errors"].append(
                f"failed: {getattr(entry, 'title', 'unknown')}")
        else:
            stats["processed"] += 1
        return ok

    started = time.time()
    status = "ok"
    try:
        firestore_store.init_storage()  # validate credentials up front
        conn = init_db()
        poll_once(conn, on_new_entry)
        stats["processed"] += drain_requests(stats["errors"])
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


def drain_requests(errors: list, max_chapters: int = 40) -> int:
    """Process queued full-series requests from the site (novels_requests
    docs written by the Pages Function). Each request carries the series
    URL + a queue of extnu chapter links; we resolve+extract a bounded
    slice per run so a deep backfill can't blow the workflow timeout.
    Returns chapters fetched."""
    from data import firestore_store
    from scraping.series_scraper import scrape_series_page
    from scraping.link_resolver import resolve_final_url_with_browser_fallback as resolve_final_url
    from scraping.generic_extractor import extract_chapter
    from data.storage import save_chapter

    try:
        requests_ = firestore_store.list_requests()
    except Exception as e:
        errors.append(f"requests read failed: {e}")
        logger.warning(f"Could not read novels_requests: {e}")
        return 0
    if not requests_:
        return 0

    fetched = 0
    for req in requests_[:1]:  # one series per run keeps runs bounded
        slug = req["slug"]
        queue = req.get("queue") or []
        done = int(req.get("processedCount") or 0)

        if req.get("status") == "pending":
            logger.info(f"Backfill request for {slug}: scraping series page")
            try:
                info = scrape_series_page(req.get("url", ""))
            except Exception as e:
                firestore_store.update_request(slug, {
                    "status": "error", "error": str(e)[:300],
                })
                errors.append(f"backfill {slug}: {e}")
                continue
            if info.get("blocked"):
                firestore_store.update_request(slug, {
                    "status": "error",
                    "error": "Cloudflare challenge on series page — set NU_COOKIES",
                })
                errors.append(f"backfill {slug}: Cloudflare challenge")
                continue
            queue = [
                {"num": c.get("number"), "extnu": c["extnu_url"],
                 "label": c.get("title", "")}
                for c in info.get("chapters", []) if c.get("extnu_url")
            ]
            if info.get("synopsis"):
                firestore_store.save_series_info(
                    None, series=req.get("series") or slug,
                    synopsis=info["synopsis"])
            firestore_store.update_request(slug, {
                "status": "processing", "queue": queue,
                "totalCount": len(queue), "processedCount": 0,
            })
            logger.info(f"Backfill {slug}: {len(queue)} chapters queued")

        remaining = list(queue)
        while remaining and fetched < max_chapters:
            item = remaining.pop(0)
            num, link = item.get("num"), item.get("extnu")
            try:
                final_url = resolve_final_url(link)
                if firestore_store.has_chapter(req.get("series") or slug, final_url):
                    done += 1  # already archived — count it, skip extraction
                else:
                    result = extract_chapter(final_url)
                    if result.passed_quality_check:
                        save_chapter(
                            None, url=final_url,
                            series=req.get("series") or slug,
                            chapter_label=f"c{num}" if num else (item.get("label") or ""),
                            title=result.title or "Untitled",
                            text=result.text, method=result.method,
                        )
                        done += 1
                        fetched += 1
                    else:
                        errors.append(f"backfill {slug}: extraction failed {link}")
            except Exception as e:
                errors.append(f"backfill {slug}: {e}")
            time.sleep(1.5)  # politeness between fetches

        firestore_store.update_request(slug, {
            "status": "done" if not remaining else "processing",
            "queue": remaining, "processedCount": done,
            "lastRunAt": firestore_store._iso_now(),
        })
        logger.info(f"Backfill {slug}: {done} done, {len(remaining)} left")

    return fetched


if __name__ == "__main__":
    sys.exit(main())
