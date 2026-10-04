"""
firestore_store.py
Firestore storage backend for cloud mode (DB_TYPE=firestore).

Used by the GitHub Actions poller (poller.py). Authenticates with a
GCP service account (FIREBASE_SERVICE_ACCOUNT_JSON) — SA requests use
Google OAuth tokens which bypass Firestore security rules, so the site
can keep simple `allow read: if true` rules while writes stay locked to
the key in GitHub secrets.

Collections (Firestore project mw-novels):
    novels/{slug}                  — one doc per series
    novels/{slug}/chapters/{id}    — one doc per chapter (id = sha256(url))
    novels_updates/{chapter_id}    — flat per-chapter feed for the site's
                                     Latest-updates tab (id = sha256(url))
    novels_seen/{guid_hash}        — RSS dedup (replaces seen_entries.db)
    novels_meta/state              — latest poller run status

The companion site app reads `novels` + `novels_meta` client-side via
the Firestore REST API behind Cloudflare Access; `novels_seen` is
poller-internal.
"""

import hashlib
import json
import logging
import re
import time
import unicodedata
from typing import Optional

import requests

from core.exceptions import DatabaseError, ValidationError
from core.settings import get_settings

logger = logging.getLogger(__name__)

SERIES_COL = "novels"
SEEN_COL = "novels_seen"
META_COL = "novels_meta"
UPDATES_COL = "novels_updates"
META_DOC = "state"

_DOCS_ROOT = (
    "https://firestore.googleapis.com/v1/projects/{project}"
    "/databases/(default)/documents"
)
_SCOPES = ["https://www.googleapis.com/auth/datastore"]
_CREDENTIALS = None


def _project() -> str:
    return get_settings().FIRESTORE_PROJECT


def _access_token() -> str:
    """OAuth access token from the service-account JSON (google-auth
    handles refresh automatically)."""
    global _CREDENTIALS
    if _CREDENTIALS is None:
        raw = get_settings().FIREBASE_SERVICE_ACCOUNT_JSON
        if not raw:
            raise DatabaseError("FIREBASE_SERVICE_ACCOUNT_JSON is not set")
        try:
            info = json.loads(raw)
        except json.JSONDecodeError as e:
            raise DatabaseError(
                f"FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON: {e}") from e
        try:
            from google.oauth2 import service_account
            _CREDENTIALS = service_account.Credentials.from_service_account_info(
                info, scopes=_SCOPES)
        except ImportError:
            raise DatabaseError(
                "google-auth is required for DB_TYPE=firestore "
                "(pip install -r requirements-poller.txt)")
    if not _CREDENTIALS.valid:
        from google.auth.transport.requests import Request as _GARequest
        try:
            _CREDENTIALS.refresh(_GARequest())
        except Exception as e:
            raise DatabaseError(f"Service-account token refresh failed: {e}") from e
    return _CREDENTIALS.token


def _req(method: str, path: str, **kwargs) -> requests.Response:
    """Authed request against the documents API. `path` is relative to
    the documents root, or ':commit'."""
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {_access_token()}"
    resp = requests.request(
        method, f"{_DOCS_ROOT.format(project=_project())}/{path}",
        headers=headers, timeout=30, **kwargs,
    )
    return resp


def _doc_name(path: str) -> str:
    """Full resource name for commit writes."""
    return (
        f"projects/{_project()}/databases/(default)/documents/{path}"
    )


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _slugify(name: str) -> str:
    """Derive a stable doc id from a series name (NU slug style, ascii-folded)."""
    slug = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9\s]+", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug or "unknown"


def _to_field(v):
    """Python scalar/list/dict → Firestore REST field value."""
    if v is None:
        return {"nullValue": None}
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, str):
        return {"stringValue": v}
    if isinstance(v, list):
        return {"arrayValue": {"values": [_to_field(x) for x in v]}}
    if isinstance(v, dict):
        return {"mapValue": {"fields": {k: _to_field(x) for k, x in v.items()}}}
    raise ValidationError(f"Unsupported field type: {type(v)}")


def _fields(data: dict) -> dict:
    return {k: _to_field(v) for k, v in data.items()}


def _from_field(v):
    """Firestore REST field value → Python scalar."""
    if "stringValue" in v:
        return v["stringValue"]
    if "integerValue" in v:
        return int(v["integerValue"])
    if "doubleValue" in v:
        return v["doubleValue"]
    if "booleanValue" in v:
        return v["booleanValue"]
    if "nullValue" in v:
        return None
    if "timestampValue" in v:
        return v["timestampValue"]
    if "arrayValue" in v:
        return [_from_field(x) for x in v.get("arrayValue", {}).get("values", [])]
    if "mapValue" in v:
        return {k: _from_field(x) for k, x in v.get("mapValue", {}).get("fields", {}).items()}
    return None


def _iso_now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def init_storage(path=None):
    """Validate credentials + return the REST store handle (the settings
    object — all calls go through the module's cached token)."""
    _access_token()  # fail fast if the service account key is bad
    logger.info("Firestore storage initialized (REST, service account)")
    return _get_client_sentinel()


class _ClientSentinel:
    """Opaque handle so call sites keep the same (conn, ...) signature."""

    def close(self):
        """No-op — REST has nothing to close; keeps sqlite-style
        conn.close() call sites working in firestore mode."""

    def __repr__(self):
        return "<FirestoreREST>"


_SENTINEL = _ClientSentinel()


def _get_client_sentinel():
    return _SENTINEL


def init_seen():
    """Alias for init_storage — seen-entries share the same store."""
    _access_token()
    return _SENTINEL


MAX_ATTEMPTS = 3


def is_new_entry(conn, guid: str) -> bool:
    """Check whether an RSS guid needs processing. Docs marked `failed`
    retry until attempts hits MAX_ATTEMPTS, then count as seen."""
    try:
        if not guid:
            raise ValidationError("GUID cannot be empty")
        resp = _req("GET", f"{SEEN_COL}/{_hash(guid)}")
        if resp.status_code == 404:
            is_new = True
        elif resp.ok:
            fields = resp.json().get("fields", {})
            if fields.get("failed", {}).get("booleanValue"):
                attempts = int(fields.get("attempts", {}).get("integerValue", "0"))
                is_new = attempts < MAX_ATTEMPTS
            else:
                is_new = False
        else:
            raise DatabaseError(f"Firestore read failed {resp.status_code}: {resp.text[:200]}")
        logger.debug(f"Entry {guid} is_new={is_new}")
        return is_new
    except ValidationError:
        raise
    except DatabaseError:
        raise
    except Exception as e:
        logger.error(f"Firestore error checking entry {guid}: {e}")
        raise DatabaseError(f"Failed to check entry: {e}") from e


def mark_seen(conn, guid: str, link: str):
    """Record an RSS guid as processed."""
    try:
        if not guid or not link:
            raise ValidationError("GUID and link cannot be empty")
        resp = _req("PATCH", f"{SEEN_COL}/{_hash(guid)}", json={
            "fields": _fields({"guid": guid, "link": link, "firstSeen": time.time()})
        })
        if not resp.ok:
            raise DatabaseError(f"Firestore write failed {resp.status_code}: {resp.text[:200]}")
        logger.debug(f"Marked entry {guid} as seen")
    except ValidationError:
        raise
    except DatabaseError:
        raise
    except Exception as e:
        logger.error(f"Failed to mark entry {guid}: {e}")
        raise DatabaseError(f"Failed to mark entry: {e}") from e


def mark_failed(conn, guid: str, link: str, error: str = "") -> int:
    """Record a failed processing attempt. Unlike mark_seen, the entry
    stays retryable until attempts reaches MAX_ATTEMPTS — protects
    against dropping chapters during transient outages (e.g. a
    Cloudflare-challenged redirect that clears later). Returns the new
    attempt count; callers compare it to MAX_ATTEMPTS to spot an entry
    that just died for good."""
    try:
        if not guid:
            raise ValidationError("GUID cannot be empty")
        attempts = 0
        resp = _req("GET", f"{SEEN_COL}/{_hash(guid)}")
        if resp.ok:
            attempts = int(resp.json().get("fields", {})
                           .get("attempts", {}).get("integerValue", "0"))
        resp = _req("PATCH", f"{SEEN_COL}/{_hash(guid)}", json={
            "fields": _fields({
                "guid": guid,
                "link": link or "",
                "failed": True,
                "attempts": attempts + 1,
                "lastError": (error or "")[:300],
                "lastSeen": time.time(),
            })
        })
        if not resp.ok:
            raise DatabaseError(f"Firestore write failed {resp.status_code}: {resp.text[:200]}")
        logger.info(f"Recorded failed attempt {attempts + 1} for entry {guid}")
        return attempts + 1
    except ValidationError:
        raise
    except DatabaseError:
        raise
    except Exception as e:
        logger.error(f"Failed to record entry failure {guid}: {e}")
        raise DatabaseError(f"Failed to record entry failure: {e}") from e


def has_chapter(series: str, url: str) -> bool:
    """True if a chapter doc already exists for this final URL — lets the
    backfill skip re-extracting chapters we already archived."""
    return get_chapter(series, url) is not None


def get_chapter(series: str, url: str):
    """Chapter doc fields for a final URL, or None — the drain loop uses
    this both to skip re-extraction and to spot docs worth lazy-healing."""
    resp = _req(
        "GET", f"{SERIES_COL}/{_slugify(series)}/chapters/{_hash(url)}")
    if resp.status_code == 404:
        return None
    if not resp.ok:
        raise DatabaseError(
            f"Firestore chapter read failed {resp.status_code}: {resp.text[:200]}")
    return {k: _from_field(v) for k, v in resp.json().get("fields", {}).items()}


def _set_groups_healed(series: str, value: str):
    """Write the `groupsHealed` flag on the series doc — an ISO timestamp
    when a full heal scan finished, "" to reopen heal-eligibility."""
    resp = _req("PATCH", f"{SERIES_COL}/{_slugify(series)}",
                params=[("updateMask.fieldPaths", "groupsHealed")],
                json={"fields": _fields({"groupsHealed": value})})
    if not resp.ok:
        raise DatabaseError(
            f"Firestore heal flag write failed {resp.status_code}: {resp.text[:200]}")


def patch_chapter_fields(series: str, url: str, group=None, nu_link=None):
    """Merge `group`/`nuLink` onto an existing chapter doc — the lazy-heal
    path for docs written before those fields existed. Also patches the
    novels_updates feed entry (same doc id) so the site's Latest tab
    heals too. No-ops when there's nothing to write."""
    fields = {}
    if group:
        fields["group"] = group
    if nu_link:
        fields["nuLink"] = nu_link
    if not fields or not url:
        return False
    chapter_id = _hash(url)
    params = [("updateMask.fieldPaths", k) for k in fields.keys()]
    resp = _req(
        "PATCH", f"{SERIES_COL}/{_slugify(series)}/chapters/{chapter_id}",
        params=params, json={"fields": _fields(fields)})
    if resp.status_code == 404:
        return False  # doc vanished between the read and the patch
    if not resp.ok:
        raise DatabaseError(
            f"Firestore chapter patch failed {resp.status_code}: {resp.text[:200]}")
    if group:
        # Feed doc may not exist for very old chapters — 404 is fine.
        _req("PATCH", f"{UPDATES_COL}/{chapter_id}",
             params=[("updateMask.fieldPaths", "group")],
             json={"fields": _fields({"group": group})})
    if nu_link and not group:
        # This doc may now be healable via its nuLink — the series can no
        # longer claim to be fully healed.
        try:
            _set_groups_healed(series, "")
        except Exception as e:
            logger.warning(f"Could not clear heal flag for {series}: {e}")
    return True


def heal_chapter_groups(conn, series: str, release_rows, limit: int = 400):
    """Self-heal — backfill `group` onto chapter docs that know their NU
    release link (`nuLink`, saved at fetch time) but predate group
    capture. Called after a series-page sync refreshes the release
    table, so healing costs a couple of masked list calls + PATCHes and
    no link resolution. Returns the number of docs patched."""
    # Fast path — a previous full scan already patched everything
    # healable; the flag is reopened by any save/patch that introduces a
    # nuLink-bearing doc without a group.
    try:
        if (get_series_info(conn, series) or {}).get("groupsHealed"):
            return 0
    except Exception:
        pass
    group_by_extnu = {
        c.get("extnu_url"): c.get("group")
        for c in (release_rows or [])
        if c.get("extnu_url") and c.get("group")
    }
    if not group_by_extnu:
        return 0
    slug = _slugify(series)
    healed = 0
    page_token = ""
    complete = False
    while True:
        params = [
            ("pageSize", "300"),
            ("mask.fieldPaths", "url"),
            ("mask.fieldPaths", "nuLink"),
            ("mask.fieldPaths", "group"),
        ]
        if page_token:
            params.append(("pageToken", page_token))
        resp = _req("GET", f"{SERIES_COL}/{slug}/chapters", params=params)
        if not resp.ok:
            break
        payload = resp.json()
        for d in payload.get("documents", []):
            f = {k: _from_field(v) for k, v in d.get("fields", {}).items()}
            if f.get("group"):
                continue
            g = group_by_extnu.get(f.get("nuLink") or "")
            if not g:
                continue
            try:
                patch_chapter_fields(series, f.get("url"), group=g)
                healed += 1
            except Exception as e:
                logger.warning(f"group heal failed for {f.get('url')}: {e}")
            if healed >= limit:
                return healed
        page_token = payload.get("nextPageToken")
        if not page_token:
            complete = True
            break
    if complete:
        # Whole subcollection scanned — nothing healable remains, so later
        # syncs can skip the walk entirely until the flag is reopened.
        try:
            _set_groups_healed(series, _iso_now())
        except Exception as e:
            logger.warning(f"Could not set heal flag for {series}: {e}")
    return healed


def save_chapter(conn, url, series, chapter_label, title, text, method,
                 group=None, nu_link=None):
    """Save a chapter (insert-if-absent, same semantics as INSERT OR IGNORE).
    `group` is the NU releases-table group name — a series can carry
    several groups' versions of the same chapter number as distinct docs
    (dedup is by final URL). `nu_link` is the NU /extnu/ release link —
    stored so group data can be healed onto the doc later without
    re-resolving the redirect."""
    try:
        if not url or not isinstance(url, str):
            raise ValidationError("URL cannot be empty")
        if not text or not isinstance(text, str):
            raise ValidationError("Text cannot be empty")

        slug = _slugify(series)

        # Insert-if-absent: POST to the subcollection errors 409 on dupes
        resp = _req(
            "POST", f"{SERIES_COL}/{slug}/chapters",
            params={"documentId": _hash(url)},
            json={"fields": _fields({
                "url": url,
                "series": series,
                "seriesSlug": slug,
                "label": chapter_label or "",
                "title": title or "Untitled",
                "text": text,
                "method": method or "",
                "group": group or "",
                "nuLink": nu_link or "",
                "fetchedAt": time.time(),
            })},
        )
        if resp.status_code == 409:
            logger.debug(f"Chapter already stored, skipping: {url}")
            return
        if not resp.ok:
            raise DatabaseError(
                f"Firestore chapter write failed {resp.status_code}: {resp.text[:200]}")

        chapter_id = _hash(url)

        # One atomic commit: upsert the series doc (identity + latest-
        # chapter pointer for the library "latest" column), bump the
        # count, and append to the novels_updates feed the site's
        # Latest-updates tab reads.
        series_fields = {
            "name": series,
            "slug": slug,
            "latestChapterId": chapter_id,
            "latestChapterLabel": chapter_label or "",
            "latestChapterTitle": title or "Untitled",
            "latestChapterUrl": url,
            "latestFetchedAt": time.time(),
        }
        series_mask = [
            "name", "slug",
            "latestChapterId", "latestChapterLabel",
            "latestChapterTitle", "latestChapterUrl",
            "latestFetchedAt",
        ]
        if nu_link and not group:
            # A healable chapter landed — reopen the series' heal flag.
            series_fields["groupsHealed"] = ""
            series_mask.append("groupsHealed")
        resp = _req("POST", ":commit", json={"writes": [
            {
                "update": {
                    "name": _doc_name(f"{SERIES_COL}/{slug}"),
                    "fields": _fields(series_fields),
                },
                "updateMask": {"fieldPaths": series_mask},
            },
            {
                "transform": {
                    "document": _doc_name(f"{SERIES_COL}/{slug}"),
                    "fieldTransforms": [
                        {"fieldPath": "chapterCount", "increment": {"integerValue": "1"}},
                        {"fieldPath": "updatedAt", "setToServerValue": "REQUEST_TIME"},
                    ],
                }
            },
            {
                "update": {
                    "name": _doc_name(f"{UPDATES_COL}/{chapter_id}"),
                    "fields": _fields({
                        "slug": slug,
                        "series": series,
                        "chapterId": chapter_id,
                        "label": chapter_label or "",
                        "title": title or "Untitled",
                        "url": url,
                        "group": group or "",
                        "addedAt": time.time(),
                    }),
                },
            },
        ]})
        if not resp.ok:
            raise DatabaseError(
                f"Firestore series update failed {resp.status_code}: {resp.text[:200]}")

        logger.info(f"Saved chapter: {title} ({method})")
    except ValidationError:
        raise
    except DatabaseError:
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
        data = {"name": series, "slug": slug, "lastSynced": _iso_now()}
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
        params = [("updateMask.fieldPaths", k) for k in data.keys()]
        resp = _req("PATCH", f"{SERIES_COL}/{slug}", params=params,
                    json={"fields": _fields(data)})
        if not resp.ok:
            raise DatabaseError(
                f"Firestore series write failed {resp.status_code}: {resp.text[:200]}")
        logger.info(f"Saved series info for: {series}")
    except ValidationError:
        raise
    except DatabaseError:
        raise
    except Exception as e:
        logger.error(f"Failed to save series info for {series}: {e}")
        raise DatabaseError(f"Failed to save series info: {e}") from e


def get_series_info(conn, series: str):
    """Get metadata for a series."""
    try:
        if not series:
            raise ValidationError("Series name cannot be empty")
        resp = _req("GET", f"{SERIES_COL}/{_slugify(series)}")
        if resp.status_code == 404:
            return {}
        if not resp.ok:
            raise DatabaseError(f"Firestore read failed {resp.status_code}: {resp.text[:200]}")
        return {k: _from_field(v) for k, v in resp.json().get("fields", {}).items()}
    except ValidationError:
        raise
    except DatabaseError:
        raise
    except Exception as e:
        logger.error(f"Failed to get series info for {series}: {e}")
        raise DatabaseError(f"Failed to get series info: {e}") from e


def bulk_upsert(docs):
    """Batch-write docs via the commit API — docs is a list of
    (doc_path, {field: value}) pairs, or (doc_path, fields, mask) triples
    where mask is a list of field paths to merge (leaving other fields
    on the doc untouched). Upserts, no per-doc dedup — intended for the
    one-off migration where speed beats delicacy.
    Returns number of docs written."""
    written = 0
    for i in range(0, len(docs), 400):
        chunk = docs[i:i + 400]
        writes = []
        for item in chunk:
            path, fields = item[0], item[1]
            w = {"update": {"name": _doc_name(path), "fields": _fields(fields)}}
            if len(item) > 2 and item[2]:
                w["updateMask"] = {"fieldPaths": list(item[2])}
            writes.append(w)
        resp = _req("POST", ":commit", json={"writes": writes})
        if not resp.ok:
            raise DatabaseError(
                f"Firestore bulk commit failed {resp.status_code}: {resp.text[:300]}")
        written += len(chunk)
        logger.info(f"Bulk wrote {written}/{len(docs)} docs")
    return written


def get_chapter_by_nulink(series: str, nu_link: str):
    """Any archived chapter saved via this NU release link — regardless
    of which source's text it holds (RSS pipeline, earlier backfills,
    and wuxiaworld saves all stamp nuLink). Dedups queue items without
    an extnu resolve. Docs old enough to lack nuLink miss this check —
    the final-URL lookup still catches those. Returns doc fields or
    None."""
    if not nu_link:
        return None
    slug = _slugify(series)
    resp = _req("POST", f"{SERIES_COL}/{slug}:runQuery", json={
        "structuredQuery": {
            "from": [{"collectionId": "chapters"}],
            "where": {"fieldFilter": {
                "field": {"fieldPath": "nuLink"},
                "op": "EQUAL",
                "value": {"stringValue": nu_link},
            }},
            "limit": 1,
        }})
    if not resp.ok:
        raise DatabaseError(
            f"Firestore chapter query failed {resp.status_code}: {resp.text[:200]}")
    for row in resp.json() or []:
        doc = row.get("document")
        if doc:
            return {k: _from_field(v) for k, v in doc.get("fields", {}).items()}
    return None


REQUESTS_COL = "novels_requests"


def list_requests(statuses=("pending", "processing")):
    """Docs in novels_requests that still need work. The site queues a
    full-series backfill here via the Pages Function; the poller drains
    the queue each run."""
    resp = _req("GET", REQUESTS_COL)
    if resp.status_code == 404:
        return []
    if not resp.ok:
        raise DatabaseError(
            f"Firestore requests read failed {resp.status_code}: {resp.text[:200]}")
    out = []
    for d in resp.json().get("documents", []):
        fields = {k: _from_field(v) for k, v in d.get("fields", {}).items()}
        fields["slug"] = d["name"].rsplit("/", 1)[-1]
        if fields.get("status") in statuses:
            out.append(fields)
    return out


def update_request(slug: str, fields: dict):
    """Merge-write a novels_requests doc (status, queue, progress)."""
    params = [("updateMask.fieldPaths", k) for k in fields.keys()]
    resp = _req("PATCH", f"{REQUESTS_COL}/{slug}", params=params,
                json={"fields": _fields(fields)})
    if not resp.ok:
        raise DatabaseError(
            f"Firestore request write failed {resp.status_code}: {resp.text[:200]}")


def enqueue_backfill(series_name: str, series_url: str, reason: str = "") -> bool:
    """Queue a series backfill on behalf of a permanently dead RSS entry —
    NU's release table often lists the same chapter from another group on
    a live host, so a dead aggregator link doesn't have to mean a lost
    chapter.

    Never touches an active request: a pending/processing doc keeps its
    progress ledger and the dead entry simply rides along. A finished or
    errored one gets a *fresh* series-page scan from page 1 — the table
    is newest-first, so resuming from a stale scrapePage cursor could
    skip the very releases we're hunting. processedLinks survives so
    the re-scan doesn't requeue chapters that are already archived.
    Returns True when a request was (re)queued."""
    if not series_url:
        return False
    slug = _slugify(series_name)
    resp = _req("GET", f"{REQUESTS_COL}/{slug}")
    if resp.ok:
        existing = {k: _from_field(v)
                    for k, v in resp.json().get("fields", {}).items()}
        if existing.get("status") in ("pending", "processing"):
            logger.info(
                f"Backfill already active for {slug} — dead entry rides along")
            return False
    elif resp.status_code != 404:
        raise DatabaseError(
            f"Firestore request read failed {resp.status_code}: {resp.text[:200]}")
    update_request(slug, {
        "slug": slug,
        "series": series_name,
        "url": series_url,
        "status": "pending",
        "requestedBy": "auto:dead-rss",
        "autoReason": (reason or "")[:300],
        "requestedAt": _iso_now(),
        "queue": [],
        "processedCount": 0,
        "totalCount": 0,
        "error": "",
        "autoRetries": 0,
        "scrapePage": "",
        "pendingChapters": [],
        "pendingSynopsis": "",
    })
    logger.info(f"Auto-queued backfill for {slug} ({(reason or '')[:120]})")
    return True


def save_run_meta(conn, status: str, processed: int, errors=None, duration_s: float = 0.0, run_url: str = None, phase: str = ""):
    """Record the outcome of a poller run for the site dashboard.
    `phase` narrates what the run is doing while status == "running"
    (setup → polling RSS → draining backfill)."""
    try:
        resp = _req("PATCH", f"{META_COL}/{META_DOC}", json={"fields": _fields({
            "lastPollAt": _iso_now(),
            "lastStatus": status,
            "processed": processed,
            "errors": (errors or [])[-10:],
            "durationS": duration_s,
            "runUrl": run_url or "",
            "phase": phase or "",
        })})
        if not resp.ok:
            raise DatabaseError(f"Firestore meta write failed {resp.status_code}: {resp.text[:200]}")
        logger.info(f"Saved run meta: {status} ({processed} processed)")
    except DatabaseError:
        raise
    except Exception as e:
        logger.error(f"Failed to save run meta: {e}")
        raise DatabaseError(f"Failed to save run meta: {e}") from e
