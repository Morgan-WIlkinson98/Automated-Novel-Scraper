"""
firestore_store.py
Firestore storage backend for cloud mode (DB_TYPE=firestore).

Used by the GitHub Actions poller (poller.py). Reads/writes go through a
service account supplied via the FIREBASE_SERVICE_ACCOUNT_JSON env var.

Collections (Firestore project a-3d-printer-workshop):
    novels/{slug}                  — one doc per series
    novels/{slug}/chapters/{id}    — one doc per chapter (id = sha256(url))
    novels_seen/{guid_hash}        — RSS dedup (replaces seen_entries.db)
    novels_meta/state              — latest poller run status

The companion site app reads `novels` + `novels_meta` client-side behind
Cloudflare Access; `novels_seen` is poller-internal.
"""

import hashlib
import json
import logging
import re
import time
import unicodedata
from typing import Optional

from core.exceptions import DatabaseError, ValidationError
from core.settings import get_settings

logger = logging.getLogger(__name__)

SERIES_COL = "novels"
SEEN_COL = "novels_seen"
META_COL = "novels_meta"
META_DOC = "state"

_client = None


def _get_client():
    """Lazily build the Firestore client from the service-account env var."""
    global _client
    if _client is not None:
        return _client
    try:
        from google.cloud import firestore
        from google.oauth2 import service_account
    except ImportError as e:
        raise DatabaseError(
            "google-cloud-firestore is not installed (pip install google-cloud-firestore)"
        ) from e
    raw = get_settings().FIREBASE_SERVICE_ACCOUNT_JSON
    if not raw:
        raise DatabaseError("FIREBASE_SERVICE_ACCOUNT_JSON is not set")
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as e:
        raise DatabaseError(f"FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON: {e}") from e
    try:
        creds = service_account.Credentials.from_service_account_info(info)
        _client = firestore.Client(project=info.get("project_id"), credentials=creds)
    except Exception as e:
        raise DatabaseError(f"Failed to create Firestore client: {e}") from e
    return _client


def _server_timestamp():
    from google.cloud import firestore
    return firestore.SERVER_TIMESTAMP


def _increment(n: int):
    from google.cloud import firestore
    return firestore.Increment(n)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _slugify(name: str) -> str:
    """Derive a stable doc id from a series name (NU slug style, ascii-folded)."""
    slug = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9\s]+", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug or "unknown"


def init_storage(path=None):
    """Return the Firestore client (signature-compatible with storage.init_storage)."""
    client = _get_client()
    logger.info("Firestore storage initialized")
    return client


def init_seen():
    """Alias for init_storage — seen-entries share the same client."""
    return _get_client()


def is_new_entry(conn, guid: str) -> bool:
    """Check whether an RSS guid has been processed already."""
    try:
        if not guid:
            raise ValidationError("GUID cannot be empty")
        doc = conn.collection(SEEN_COL).document(_hash(guid)).get()
        is_new = not doc.exists
        logger.debug(f"Entry {guid} is_new={is_new}")
        return is_new
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Firestore error checking entry {guid}: {e}")
        raise DatabaseError(f"Failed to check entry: {e}") from e


def mark_seen(conn, guid: str, link: str):
    """Record an RSS guid as processed."""
    try:
        if not guid or not link:
            raise ValidationError("GUID and link cannot be empty")
        conn.collection(SEEN_COL).document(_hash(guid)).set(
            {"guid": guid, "link": link, "firstSeen": time.time()}, merge=True
        )
        logger.debug(f"Marked entry {guid} as seen")
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Failed to mark entry {guid}: {e}")
        raise DatabaseError(f"Failed to mark entry: {e}") from e


def save_chapter(conn, url, series, chapter_label, title, text, method):
    """Save a chapter (insert-if-absent, same semantics as INSERT OR IGNORE)."""
    try:
        if not url or not isinstance(url, str):
            raise ValidationError("URL cannot be empty")
        if not text or not isinstance(text, str):
            raise ValidationError("Text cannot be empty")

        from google.api_core.exceptions import AlreadyExists

        slug = _slugify(series)
        series_ref = conn.collection(SERIES_COL).document(slug)
        chapter_ref = series_ref.collection("chapters").document(_hash(url))
        try:
            chapter_ref.create({
                "url": url,
                "series": series,
                "seriesSlug": slug,
                "label": chapter_label or "",
                "title": title or "Untitled",
                "text": text,
                "method": method or "",
                "fetchedAt": time.time(),
            })
        except AlreadyExists:
            logger.debug(f"Chapter already stored, skipping: {url}")
            return

        series_ref.set({
            "name": series,
            "slug": slug,
            "chapterCount": _increment(1),
            "updatedAt": _server_timestamp(),
        }, merge=True)

        logger.info(f"Saved chapter: {title} ({method})")
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Failed to save chapter {url}: {e}")
        raise DatabaseError(f"Failed to save chapter: {e}") from e


def save_series_info(
    conn,
    series: str,
    url: Optional[str] = None,
    synopsis: Optional[str] = None,
    available_chapters: Optional[str] = None,
    current_chapter_label: Optional[str] = None,
    current_chapter_link: Optional[str] = None,
    latest_chapter_label: Optional[str] = None,
    latest_chapter_link: Optional[str] = None,
    reading_list_name: Optional[str] = None,
    imported_at: Optional[float] = None,
):
    """Merge series metadata — only provided (non-None) fields are written."""
    try:
        if not series:
            raise ValidationError("Series name cannot be empty")

        slug = _slugify(series)
        data = {"name": series, "slug": slug, "lastSynced": _server_timestamp()}
        field_map = {
            "url": url,
            "synopsis": synopsis,
            "availableChapters": available_chapters,
            "currentLabel": current_chapter_label,
            "currentLink": current_chapter_link,
            "latestLabel": latest_chapter_label,
            "latestLink": latest_chapter_link,
            "listName": reading_list_name,
            "importedAt": imported_at,
        }
        data.update({k: v for k, v in field_map.items() if v is not None})
        conn.collection(SERIES_COL).document(slug).set(data, merge=True)
        logger.info(f"Saved series info for: {series}")
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Failed to save series info for {series}: {e}")
        raise DatabaseError(f"Failed to save series info: {e}") from e


def get_series_info(conn, series: str):
    """Get metadata for a series."""
    try:
        if not series:
            raise ValidationError("Series name cannot be empty")
        doc = conn.collection(SERIES_COL).document(_slugify(series)).get()
        return doc.to_dict() if doc.exists else {}
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Failed to get series info for {series}: {e}")
        raise DatabaseError(f"Failed to get series info: {e}") from e


def save_run_meta(conn, status: str, processed: int, errors=None, duration_s: float = 0.0, run_url: str = None):
    """Record the outcome of a poller run for the site dashboard."""
    try:
        conn.collection(META_COL).document(META_DOC).set({
            "lastPollAt": _server_timestamp(),
            "lastStatus": status,
            "processed": processed,
            "errors": (errors or [])[-10:],
            "durationS": duration_s,
            "runUrl": run_url or "",
        })
        logger.info(f"Saved run meta: {status} ({processed} processed)")
    except Exception as e:
        logger.error(f"Failed to save run meta: {e}")
        raise DatabaseError(f"Failed to save run meta: {e}") from e
