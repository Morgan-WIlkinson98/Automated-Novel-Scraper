"""
queue_worker.py
Cloud Run Job entrypoint — on-demand request-queue processing.

The site's "Fetch missing chapters" button (Pages Function) executes this
job directly via the Cloud Run API, so processing starts in seconds
instead of waiting for the GitHub Actions schedule — and isn't subject
to Actions minutes or schedule throttling at all.

One execution = one pass over the novels_requests queue (the same work
poller.py does after its RSS phase), then the job exits and scales to
zero. Chapter text still walks the mirror chain: wuxiaworld.eu →
novelfull.net → novellunar.com → NovelUpdates links.

Env:
    DB_TYPE=firestore                    — required
    FIREBASE_SERVICE_ACCOUNT_JSON        — required (same SA as the poller)
    NU_COOKIES                           — optional, NU session cookies
    NU_HEADED=1                          — headed Chromium under xvfb for
                                           NU's Cloudflare challenge
    POLL_ONLY_SLUG                       — optional; process only this
                                           novels_requests slug (set
                                           per-execution via job overrides)
    WORKER_RUN_BUDGET_S                  — wall-clock cap, default 3300
                                           (job timeout is 3600s)

Deploy: tools/deploy_worker.sh builds+pushes the image and creates or
updates the `novels-worker` job. The job carries no inbound network —
the site triggers executions over the Cloud Run REST API.
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
        logger.error("queue_worker.py requires DB_TYPE=firestore")
        return 2
    if not settings.FIREBASE_SERVICE_ACCOUNT_JSON:
        logger.error("FIREBASE_SERVICE_ACCOUNT_JSON is not set")
        return 2

    from data import firestore_store
    from poller import process_request_queue

    stats = {"processed": 0, "errors": []}
    started = time.time()
    status = "ok"
    run_url = os.getenv("WORKER_RUN_URL") or ""

    # CLOUD_RUN_* envs are set automatically by the runtime — log the
    # execution name so run-meta links are traceable in the console.
    execution = os.getenv("CLOUD_RUN_EXECUTION", "")
    if execution and not run_url:
        project = os.getenv("GOOGLE_CLOUD_PROJECT", "mw-novels")
        region = os.getenv("CLOUD_RUN_REGION", "us-central1")
        run_url = (
            f"https://console.cloud.google.com/run/jobs/executions/"
            f"details/{region}/{execution}/logs?project={project}")

    def report_phase(phase):
        try:
            firestore_store.save_run_meta(
                firestore_store.init_storage(), status="running",
                processed=stats["processed"], errors=list(stats["errors"]),
                duration_s=0, run_url=run_url, phase=phase)
        except Exception as e:
            logger.warning(f"Meta phase write failed: {e}")

    try:
        firestore_store.init_storage()  # validate credentials up front
        report_phase("starting")

        only_slug = (os.getenv("POLL_ONLY_SLUG") or "").strip() or None
        budget = int(os.getenv("WORKER_RUN_BUDGET_S", "3300"))
        deadline = started + budget

        report_phase("processing request queue")
        stats["processed"] += process_request_queue(
            stats["errors"], deadline=deadline, only_slug=only_slug)
    except Exception as e:
        status = "failed"
        stats["errors"].append(str(e))
        logger.exception("Queue worker run failed")

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
    logger.info(f"Queue worker finished: {status} — "
                f"{stats['processed']} chapters, {elapsed}s")
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
