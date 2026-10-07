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
import re
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
    from core.utils import clean_series_name, novelupdates_series_url

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

    def on_dead_entry(entry):
        """RSS entry exhausted its retries — queue a series backfill so
        the request queue retries the chapter via NU's release table,
        where a different group's live host may serve the same chapter.
        A dead aggregator link doesn't have to mean a lost chapter."""
        try:
            series_name = clean_series_name(
                getattr(entry, "title", "") or "")
            summary = getattr(entry, "summary", "") or ""
            m = re.search(
                r"https?://www\.novelupdates\.com/series/[^/\s]+/?",
                summary)
            series_url = (m.group(0).rstrip("/") + "/") if m \
                else novelupdates_series_url(series_name)
            if not series_url or series_name == "Unknown":
                return
            if firestore_store.enqueue_backfill(
                    series_name, series_url,
                    reason="RSS entry exhausted retries: "
                           + str(getattr(entry, "title", "?"))):
                stats["errors"].append(
                    f"auto-backfill queued: {series_name} (dead RSS entry)")
        except Exception as e:
            logger.warning(f"dead-entry backfill enqueue failed: {e}")

    started = time.time()
    status = "ok"
    run_url = ""
    if os.getenv("GITHUB_RUN_ID"):
        run_url = (
            f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/"
            f"{os.getenv('GITHUB_REPOSITORY', '')}/actions/runs/{os.getenv('GITHUB_RUN_ID')}"
        )
    def report_phase(phase):
        """Live 'what is it doing' marker on novels_meta/state — the
        site's backend card shows this while the run is in flight."""
        try:
            firestore_store.save_run_meta(
                firestore_store.init_storage(), status="running",
                processed=stats["processed"], errors=list(stats["errors"]),
                duration_s=0, run_url=run_url, phase=phase)
        except Exception as e:
            logger.warning(f"Meta phase write failed: {e}")

    try:
        firestore_store.init_storage()  # validate credentials up front
        conn = init_db()
        # Heartbeat — lets the site show a run in progress. Without this,
        # novels_meta/state only exists after a *completed* run, so
        # long-running (or dying) jobs were invisible.
        report_phase("starting")
        # Budget split — a busy RSS phase previously consumed the whole
        # window and left the queue deadline already expired (its deadline
        # was measured from run start). Now RSS gets up to
        # RSS_TIME_BUDGET_S, and queue processing gets whatever is left
        # under POLL_RUN_BUDGET_S — a hard cap that leaves headroom under
        # the job's 25-min timeout for the run-meta write and teardown.
        run_deadline = started + int(os.getenv("POLL_RUN_BUDGET_S", "1260"))
        # Focused mode (workflow_dispatch `slug` input): skip RSS and
        # spend the whole run on one request's queue — used to verify a
        # single series end-to-end without queueing behind the rest.
        only_slug = (os.getenv("POLL_ONLY_SLUG") or "").strip() or None
        if not only_slug:
            report_phase("polling RSS")
            rss_deadline = started + int(os.getenv("RSS_TIME_BUDGET_S", "300"))
            poll_once(conn, on_new_entry, deadline=rss_deadline,
                      on_dead_entry=on_dead_entry)
        report_phase("processing request queue")
        queue_budget = int(os.getenv(
            "QUEUE_TIME_BUDGET_S",
            os.getenv("DRAIN_TIME_BUDGET_S", "1200")))
        deadline = min(run_deadline, time.time() + queue_budget)
        stats["processed"] += process_request_queue(
            stats["errors"], deadline=deadline, only_slug=only_slug)
    except Exception as e:
        status = "failed"
        stats["errors"].append(str(e))
        logger.exception("Poll run failed")

    try:
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


# Per-request slice cap and progress-flush cadence for the queue loop.
# The fetched-count cap alone can't bound a run: queue items that resolve
# to already-archived chapters (or fail) don't count against it, so a run
# could grind through hundreds of ~9s browser resolves until the job's
# 25-min timeout kills it mid-loop — and unflushed progress is lost.
_QUEUE_ITEM_CAP = int(os.getenv(
    "QUEUE_ITEMS_PER_REQUEST",
    os.getenv("DRAIN_ITEMS_PER_REQUEST", "40")))
_QUEUE_FLUSH_S = 60


def process_request_queue(errors: list, max_chapters: int = 40,
                          deadline: float = None,
                          only_slug: str = None) -> int:
    """Process queued full-series requests from the site (novels_requests
    docs written by the Pages Function). Each request carries the series
    URL + a queue of extnu chapter links; we resolve+extract a bounded
    slice per run so a deep backfill can't blow the workflow timeout.

    Every request gets a slice per run (FIFO by requestedAt) so a deep
    queue can't starve the ones behind it, and progress is flushed to
    Firestore periodically — a cancelled run loses at most the last flush
    window instead of the whole run's work. Returns chapters fetched.

    Chapter sources, tried in order: wuxiaworld.eu → novelfull.net →
    novellunar.com → the chapter link from NovelUpdates (scraping/
    alt_sources.py). NovelUpdates stays the source of truth for series
    metadata and release discovery; the mirrors only fill in text.

    only_slug (POLL_ONLY_SLUG): restrict to a single request, include it
    even in a terminal-error state, and log each item outcome — used by
    manual dispatch runs to verify one series end-to-end."""
    from data import firestore_store
    from scraping.series_scraper import scrape_series_page
    from scraping.link_resolver import resolve_final_url_with_browser_fallback as resolve_final_url
    from scraping.generic_extractor import extract_chapter
    from scraping import alt_sources
    from data.storage import save_chapter

    try:
        requests_ = firestore_store.list_requests(
            ("pending", "processing", "error"))
    except Exception as e:
        errors.append(f"requests read failed: {e}")
        logger.warning(f"Could not read novels_requests: {e}")
        return 0
    # Requests that died on transient infrastructure errors (playwright
    # nesting crashes, CF walls on the series page, timeouts) get auto-
    # retried — bounded by autoRetries so a genuinely broken series URL
    # doesn't resurrect forever. Anything else stays terminal.
    if only_slug:
        # Focused runs bypass the error-state filter — the point is to
        # retry one specific request even if it looks terminal.
        requests_ = [r for r in requests_ if r.get("slug") == only_slug]
        if not requests_:
            errors.append(f"focus run: no pending request for {only_slug}")
            logger.warning(
                f"POLL_ONLY_SLUG={only_slug}: no matching request")
            return 0
    else:
        _TRANSIENT_ERR = ("asyncio", "cloudflare", "timeout", "timed out",
                          "connection", "temporar", "rate limit", "playwright",
                          "truncat")
        requests_ = [
            r for r in requests_
            if r.get("status") != "error"
            # A paused series scrape is progress, not failure — always retry.
            or "paused" in str(r.get("error") or "").lower()
            or (any(t in str(r.get("error") or "").lower()
                    for t in _TRANSIENT_ERR)
                and int(r.get("autoRetries") or 0) < 3)
        ]
    if not requests_:
        return 0

    requests_.sort(key=lambda r: r.get("requestedAt") or "")

    # Shared headed-browser session for extnu resolves — the first
    # navigation solves NU's Cloudflare challenge and the clearance
    # cookie then covers every later resolve (~1-2s each instead of a
    # ~9s fresh-browser challenge roll per link, which also tripped CF's
    # rate limit). Falls back to the standalone per-item resolver if the
    # session can't open or dies.
    _browser_cm = _page = None
    _page_rebuilds = 0
    try:
        from scraping.browser import get_browser_page, resolve_in_page
        _browser_cm = get_browser_page()
        _page = _browser_cm.__enter__()
        logger.info("Shared queue-processing browser session opened")
    except Exception as e:
        logger.warning(f"Shared browser session unavailable, per-item resolve only: {e}")

    def resolve(link):
        nonlocal _browser_cm, _page, _page_rebuilds
        if _page is not None:
            try:
                return resolve_in_page(_page, link)
            except Exception:
                # Item-level failures (CF block, timeout) are the item's
                # problem — churning the session just pokes NU harder.
                # Only rebuild when the browser itself actually died.
                try:
                    dead = _page.is_closed() \
                        or not _page.context.browser.is_connected()
                except Exception:
                    dead = True
                if not dead or _page_rebuilds >= 3:
                    raise
                _page_rebuilds += 1
                try:
                    _browser_cm.__exit__(None, None, None)
                except Exception:
                    pass
                _browser_cm = get_browser_page()
                _page = _browser_cm.__enter__()
                return resolve_in_page(_page, link)
        return resolve_final_url(link)

    def out_of_time() -> bool:
        return deadline is not None and time.time() >= deadline

    def flush(slug, status, remaining, done, activity=None,
              processed=None):
        fields = {
            "status": status, "queue": remaining,
            "processedCount": done,
            # Total = done + still-queued. Grows while a paused series
            # keeps discovering chapters, so the site's bar stays real.
            "totalCount": done + len(remaining),
            "lastRunAt": firestore_store._iso_now(),
        }
        if processed is not None:
            fields["processedLinks"] = sorted(processed)
        if activity is not None:
            # One-line narration for the site's progress card —
            # e.g. "saved c45" / "c46 already archived".
            fields["activity"] = activity
        firestore_store.update_request(slug, fields)

    def merge_queue(req, chapters):
        """Fold newly discovered chapters into the request's live queue —
        keeps unprocessed items, skips links already queued or processed
        in earlier runs, and re-sorts oldest-first."""
        queue = list(req.get("queue") or [])
        seen = {i.get("extnu") for i in queue}
        seen |= set(req.get("processedLinks") or [])
        for c in chapters:
            link = c.get("extnu_url")
            if link and link not in seen:
                queue.append({
                    "num": c.get("number"), "extnu": link,
                    "label": c.get("title", ""), "group": c.get("group"),
                })
                seen.add(link)
        queue.sort(key=lambda i: (i["num"] is None, i["num"] or 0))
        return queue

    fetched = 0
    bail_queue = False
    stormed_reqs = 0  # consecutive requests that CF-bailed their slice
    # Mirror-source slug lookups + misses cached for the run so a dead
    # series doesn't re-probe every site on every failed item.
    alt_caches = {}

    # Pass 1 — promotions first: queue-building shouldn't starve behind a
    # storming request (the head request used to bail the whole pass on
    # CF blocks before later requests were even reached). Series-page
    # navigation may also pass where extnu resolves are walled.
    for req in requests_:
        if out_of_time():
            logger.info("Backfill time budget exhausted — deferring "
                        "remaining work to the next run")
            break
        # Fresh promotions AND paused series still carrying a scrapePage
        # cursor — the latter already have a queue processing beneath the
        # resume, so they aren't skipped just for being "processing".
        if req.get("status") not in ("pending", "error") \
                and not req.get("scrapePage"):
            continue
        slug = req["slug"]
        series_name = req.get("series") or slug
        logger.info(f"Backfill request for {slug}: scraping series page")
        try:
            info = scrape_series_page(
                req.get("url", ""), page=_page, stop_at=deadline,
                start_pg=int(req.get("scrapePage") or 2))
        except Exception as e:
            firestore_store.update_request(slug, {
                "status": "error", "error": str(e)[:300],
                "autoRetries": int(req.get("autoRetries") or 0) + 1,
            })
            errors.append(f"backfill {slug}: {e}")
            continue
        if info.get("blocked"):
            if req.get("scrapePage") or req.get("pendingChapters") \
                    or req.get("queue"):
                # Mid-scrape wall on a *resumed* series — a pause, not a
                # failure: don't burn autoRetries. Fold whatever the
                # paused scrape already discovered into the live queue
                # so processing still makes progress this run.
                queue = merge_queue(req, req.get("pendingChapters") or [])
                status = "processing" if queue else "pending"
                firestore_store.update_request(slug, {
                    "status": status,
                    "error": "Cloudflare wall on series page — pagination "
                             "resumes next run; queue keeps processing",
                    "queue": queue,
                    "totalCount": int(req.get("processedCount") or 0)
                                  + len(queue),
                })
                req["queue"], req["status"] = queue, status
            else:
                firestore_store.update_request(slug, {
                    "status": "error",
                    "error": "Cloudflare challenge on series page — set NU_COOKIES",
                    "autoRetries": int(req.get("autoRetries") or 0) + 1,
                })
            errors.append(f"backfill {slug}: Cloudflare challenge")
            continue
        if info.get("truncated"):
            # Paused mid-table — persist the resume point + the chapters
            # found so far so a giant series doesn't have to fit inside
            # one run, AND fold the discoveries straight into the live
            # queue so processing works them now instead of idling until
            # the table finishes. Not an autoRetries failure: a pause
            # isn't one.
            found = {c.get("extnu_url"): c
                     for c in (req.get("pendingChapters") or [])
                     if c.get("extnu_url")}
            for c in info.get("chapters", []):
                found.setdefault(c.get("extnu_url"), c)
            queue = merge_queue(req, found.values())
            status = "processing" if queue else "pending"
            firestore_store.update_request(slug, {
                "status": status,
                "error": f"series scrape paused at page {info.get('stopped_pg')} "
                         f"({len(found)} chapters discovered) — resumes next run",
                "scrapePage": info.get("stopped_pg") or 2,
                "pendingChapters": list(found.values()),
                "pendingSynopsis": info.get("synopsis") or "",
                "queue": queue,
                "totalCount": int(req.get("processedCount") or 0) + len(queue),
            })
            req["queue"], req["status"] = queue, status
            errors.append(f"backfill {slug}: scrape paused "
                          f"at pg {info.get('stopped_pg')}")
            continue
        # Complete scrape — fold in chapters carried over from paused
        # runs, preserving the pending queue + already-processed links.
        all_chapters = {c.get("extnu_url"): c
                        for c in (req.get("pendingChapters") or [])
                        if c.get("extnu_url")}
        for c in info.get("chapters", []):
            all_chapters.setdefault(c.get("extnu_url"), c)
        chapters_found = list(all_chapters.values())
        synopsis = info.get("synopsis") or req.get("pendingSynopsis") or ""
        # NU's releases table is newest-first — merge_queue re-sorts
        # ascending so a backfill fills from chapter 1 up and early
        # chapters are readable long before the tail is processed.
        # Unnumbered rows (prologues/side stories) ride at the end.
        queue = merge_queue(req, chapters_found)
        if synopsis:
            firestore_store.save_series_info(
                None, series=series_name,
                synopsis=synopsis)
        status = "processing" if queue else "done"
        firestore_store.update_request(slug, {
            "status": status,
            "queue": queue,
            "totalCount": int(req.get("processedCount") or 0) + len(queue),
            "scrapePage": "", "pendingChapters": [], "pendingSynopsis": "",
        })
        req["queue"], req["status"] = queue, status
        logger.info(f"Backfill {slug}: {len(queue)} chapters queued")
        # Instant heal — chapters that already carry a nuLink get
        # their group patched now, no need to wait for the queue to
        # reach them across runs.
        try:
            healed = firestore_store.heal_chapter_groups(
                None, series_name, chapters_found)
            if healed:
                logger.info(f"Healed group on {healed} archived chapters for {slug}")
        except Exception as e:
            logger.warning(f"group heal skipped for {slug}: {e}")

    # Pass 2 — process queued items, only for requests that have one.
    queued_reqs = [r for r in requests_ if r.get("queue")]
    for i, req in enumerate(queued_reqs):
        if out_of_time() or bail_queue:
            logger.info("Queue processing stopping — deferring "
                        "remaining requests to the next run")
            break

        slug = req["slug"]
        series_name = req.get("series") or slug
        queue = req.get("queue") or []
        done = int(req.get("processedCount") or 0)
        # Extnu links already processed (saved/archived/dropped) — the
        # series-page resume merges use this to never requeue them.
        processed_links = set(req.get("processedLinks") or [])

        remaining = list(queue)
        # Items that failed this pass collect in retry_next — re-joined
        # to the queue at flush time so they retry on a LATER run (a
        # Cloudflare mood swing shouldn't burn all 3 attempts inside one
        # run), never re-popped in this pass. Dropped for good after 3
        # failures.
        retry_next = []
        attempted = 0
        cf_streak = 0
        stormed = False
        last_flush = time.time()
        activity = "queue processing resumed"
        # Flush immediately so the site's "last worked" reflects this run
        # instead of waiting up to a minute for the first item flush.
        try:
            flush(slug, "processing", remaining + retry_next,
                  done, activity, processed_links)
        except Exception:
            pass
        # Fair-share slice — a request whose items are slow (dead
        # sources take ~35s each to resolve-then-fail) could burn the
        # whole queue window and starve everyone behind it, so each
        # request gets an even share of the budget still on the clock.
        remaining_reqs = max(1, len(queued_reqs) - i)
        slice_deadline = min(
            deadline if deadline is not None else float("inf"),
            time.time() + max(60.0,
                              (deadline - time.time()) / remaining_reqs)
            if deadline is not None else float("inf"))
        while (remaining and fetched < max_chapters
               and attempted < _QUEUE_ITEM_CAP and not out_of_time()
               and time.time() < slice_deadline):
            item = remaining.pop(0)
            attempted += 1
            num, link = item.get("num"), item.get("extnu")
            label = f"c{num}" if num else (item.get("label") or "chapter")
            succeeded = False
            try:
                # Dedup on the NU release link itself — every save stamps
                # nuLink (RSS pipeline, earlier backfills, wuxiaworld
                # saves), so this catches chapters archived by ANY source
                # for this release without an extnu resolve. Docs old
                # enough to lack nuLink get caught by the final-URL check
                # in the fallback path below.
                doc = firestore_store.get_chapter_by_nulink(series_name, link)
                if doc is not None:
                    done += 1  # already archived — count it, skip fetching
                    processed_links.add(link)
                    activity = f"{label} already archived"
                    if item.get("group") and not doc.get("group"):
                        try:
                            firestore_store.patch_chapter_fields(
                                series_name, doc.get("url"),
                                group=item.get("group"))
                            activity = f"{label} healed (group)"
                        except Exception as e:
                            logger.debug(f"heal patch failed for {link}: {e}")
                    succeeded = True
                else:
                    # Backfills walk the mirror chain FIRST —
                    # wuxiaworld.eu → novelfull.net → novellunar.com —
                    # before resolving the NU-linked host. Mirrors have
                    # predictable layouts and (mostly) no Cloudflare, so
                    # they're far more forgiving than translator hosts
                    # for bulk work. NU links are the last resort (RSS
                    # items keep them primary — they arrive with fresh
                    # links). The shared page is passed for novelfull,
                    # which sits behind Cloudflare for plain requests.
                    alt = alt_sources.fetch_chapter(
                        series_name, num, alt_caches, page=_page)
                    if alt:
                        save_chapter(
                            None, url=alt["url"], series=series_name,
                            chapter_label=f"c{num}" if num else (item.get("label") or ""),
                            title=alt["title"], text=alt["text"],
                            method=alt["source"], group=item.get("group"),
                            nu_link=link)
                        done += 1
                        fetched += 1
                        processed_links.add(link)
                        activity = f"saved {label} via {alt['source']}"
                        succeeded = True
                    else:
                        final_url = resolve(link)
                        doc = firestore_store.get_chapter(
                            series_name, final_url)
                        if doc is not None:
                            done += 1
                            processed_links.add(link)
                            activity = f"{label} already archived"
                            # Lazy heal — docs archived before group/nuLink
                            # existed get patched as the queue walks past
                            # them; no migration.
                            if (item.get("group") and not doc.get("group")) \
                                    or not doc.get("nuLink"):
                                try:
                                    firestore_store.patch_chapter_fields(
                                        series_name, final_url,
                                        group=item.get("group")
                                        if not doc.get("group") else None,
                                        nu_link=link
                                        if not doc.get("nuLink") else None)
                                    activity = f"{label} healed (group/nuLink)"
                                except Exception as e:
                                    logger.debug(
                                        f"heal patch failed for {final_url}: {e}")
                            succeeded = True
                        else:
                            result = extract_chapter(final_url, page=_page)
                            if result.passed_quality_check:
                                save_chapter(
                                    None, url=final_url,
                                    series=series_name,
                                    chapter_label=f"c{num}" if num else (item.get("label") or ""),
                                    title=result.title or "Untitled",
                                    text=result.text, method=result.method,
                                    group=item.get("group"),
                                    nu_link=link,
                                )
                                done += 1
                                fetched += 1
                                processed_links.add(link)
                                activity = f"saved {label}"
                                succeeded = True
                            else:
                                activity = f"{label} extraction failed"
                                errors.append(f"backfill {slug}: extraction failed {link}")
            except Exception as e:
                cf_blocked = "cloudflare" in str(e).lower()
                activity = f"{label} error: {str(e)[:80]}"
                errors.append(f"backfill {slug}: {e}")
            else:
                cf_blocked = False
            failed = not succeeded
            if cf_blocked:
                cf_streak += 1
            else:
                cf_streak = 0
            if failed:
                if cf_blocked:
                    # Transient NU challenge storm — the item isn't
                    # actually bad, so it doesn't burn an attempt.
                    retry_next.append(item)
                else:
                    item["attempts"] = int(item.get("attempts") or 0) + 1
                    if item["attempts"] < 3:
                        retry_next.append(item)
                    else:
                        activity = f"{label} dropped after 3 failures"
                        processed_links.add(link)
                        errors.append(f"backfill {slug}: dropped {link} after 3 failures")
            time.sleep(1.5)  # politeness between fetches
            if only_slug:
                # Focused runs narrate every item so the Actions log shows
                # exactly where a series dies (resolve, extract, dedup).
                logger.info(f"[{slug}] {activity}")
            if cf_blocked:
                # Rapid-fire resolves trip CF's challenge rate limit —
                # cool off so the burst doesn't burn the whole slice.
                time.sleep(20)
                if cf_streak >= 4:
                    # One poisoned request shouldn't starve the whole
                    # queue: skip the rest of ITS slice. Only stop queue
                    # processing entirely if consecutive requests all
                    # storm (then NU really is walling the runner IP).
                    stormed = True
                    logger.warning(
                        f"{cf_streak} consecutive Cloudflare blocks on "
                        f"{slug} — skipping its slice until next run")
                    break
            if time.time() - last_flush >= _QUEUE_FLUSH_S:
                flush(slug, "processing", remaining + retry_next,
                      done, activity, processed_links)
                last_flush = time.time()

        queue_out = remaining + retry_next
        flush(slug, "done" if not queue_out else "processing",
              queue_out, done, activity, processed_links)
        stormed_reqs = stormed_reqs + 1 if stormed else 0
        if stormed_reqs >= 2:
            logger.warning(
                "Consecutive requests storming Cloudflare — "
                "pausing queue processing until next run")
            bail_queue = True
        if bail_queue:
            break

    if _browser_cm is not None:
        try:
            _browser_cm.__exit__(None, None, None)
        except Exception:
            pass
    return fetched


if __name__ == "__main__":
    sys.exit(main())
