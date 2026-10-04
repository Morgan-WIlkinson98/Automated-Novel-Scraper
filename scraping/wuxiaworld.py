"""wuxiaworld.eu fallback source — plain JSON API, no Cloudflare wall.

When an NU-linked chapter resolve/extract fails (CF block, dead
aggregator host, no site override), try fetching the same chapter from
wuxiaworld.eu instead. Verified 2026-10: anonymous requests to
/api/* succeed from datacenter IPs where NU-linked hosts 403.

Shape:
    /api/novels/{slug}/           → novel metadata (numOfChaps, first_chapter)
    /api/novels/?search={name}    → fuzzy novel search (results[].slug)
    /api/getchapter/{slug}-{idx}/ → {index, title, text, nextChap, prevChap}

Numbering caveat: {slug}-{idx} uses wuxiaworld's own position index,
which drifts from NU's "cN" numbering by however many prologue/extra
rows sit before it. Chapter titles carry the real number ("Wu Dong
Qian Kun Chapter 246"), and index order is monotonic, so we
extrapolate-then-binary-search the index for the title whose parsed
number matches. Unparseable or missing numbering = honest miss, never
a wrong-chapter guess.
"""

import logging
import re
import time

import requests

logger = logging.getLogger(__name__)

_API = "https://wuxiaworld.eu/api"
_CHAPTER_URL = "https://wuxiaworld.eu/chapter/{chap_slug}"
_UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0 Safari/537.36"
}
_TIMEOUT = 15
_MAX_PROBES = 8      # index-search fetches per chapter, worst case
_PROBE_DELAY = 0.35  # politeness between JSON fetches

# Boilerplate lines wuxiaworld prepends to .text.
_BOILER = re.compile(
    r"(?i)^(publishedat\b.*|if audio player doesn't work.*|"
    r"chapter\s*\d+(?:\.\d+)?\s*)$"
)


def _slugify(name: str) -> str:
    """NU-slug-style normalize — mirrors data.firestore_store._slugify
    (and wuxiaworld's own slugs: apostrophes/colons fold the same way)."""
    import unicodedata
    s = unicodedata.normalize("NFKD", name or "") \
        .encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9\s]+", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    return re.sub(r"-+", "-", s) or "unknown"


def _get(path: str, params: dict = None):
    """GET a wuxiaworld API path → parsed JSON, or None on any miss."""
    try:
        r = requests.get(_API + path, params=params, headers=_UA,
                         timeout=_TIMEOUT)
        if not r.ok:
            return None
        return r.json()
    except Exception as e:
        logger.debug(f"wuxiaworld {path}: {e}")
        return None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _name_match(novel: dict, series_name: str) -> bool:
    """Search-result sanity check — name or other_names must equal the
    series name after normalization (fuzzy search otherwise returns the
    whole catalog ranked by vibes)."""
    target = _norm(series_name)
    if not target:
        return False
    if _norm(novel.get("name")) == target:
        return True
    for alias in novel.get("other_names") or []:
        text = alias.get("name") if isinstance(alias, dict) else alias
        if _norm(text) == target:
            return True
    return False


def _novel_slug(series_name: str, cache: dict):
    """series_name → wuxiaworld slug (or None), cached per drain run.
    A novel must actually host chapters — stubs with numOfChaps=0 and
    no first_chapter are dead ends."""
    if series_name in cache:
        return cache[series_name]
    slug = None
    guess = _slugify(series_name)
    n = _get(f"/novels/{guess}/")
    if n and (n.get("numOfChaps") or n.get("first_chapter")):
        slug = guess
    else:
        res = _get("/novels/", params={"search": series_name, "limit": 6})
        for r in (res or {}).get("results", []):
            if _name_match(r, series_name):
                slug = r.get("slug")
                break
    cache[series_name] = slug
    return slug


def _title_num(title: str):
    """Real chapter number out of a wuxiaworld title — same patterns the
    NU release-table parser uses ("Chapter 246", "CH 23", bare digits)."""
    from scraping.series_scraper import _guess_chapter_number
    return _guess_chapter_number(title)


def _clean_text(text: str) -> str:
    """Strip wuxiaworld's prepended boilerplate, keep the body."""
    lines = [ln for ln in (text or "").splitlines()
             if not _BOILER.match(ln.strip())]
    return "\n".join(lines).strip()


def fetch_chapter(series_name: str, num, cache: dict):
    """Best-effort (series, NU chapter num) → wuxiaworld chapter.

    Returns dict(title, text, url, source_slug) on a verified number
    match, else None. Probes ≤_MAX_PROBES JSON endpoints — cheap enough
    to run per failed drain item."""
    if num is None:
        return None
    if isinstance(num, float) and not num.is_integer():
        return None  # fractional chapters (c72.5) can't map to wuxiaworld ints
    try:
        num = int(num)
    except (TypeError, ValueError):
        return None
    slug = _novel_slug(series_name, cache)
    if not slug:
        return None

    # Index search: the slug's index and the real chapter number move
    # together, so each probe's parsed number tells us which way to jump.
    lo, hi = 1, None
    guess = num
    tried = set()
    saw_chapter = False  # any getchapter hit at all — stub novels 404 every probe
    for _ in range(_MAX_PROBES):
        if hi is not None and lo > hi:
            break
        guess = max(lo, min(guess, hi)) if hi is not None else max(1, guess)
        if guess in tried:
            guess = (lo + hi) // 2 if hi is not None else guess + 1
            if guess in tried or guess < 1 or (hi is not None and guess > hi):
                break
        tried.add(guess)
        time.sleep(_PROBE_DELAY)
        d = _get(f"/getchapter/{slug}-{guess}/")
        if not d or not d.get("text"):
            # Past the hosted tail — pull the bound in.
            hi = guess - 1 if hi is None else min(hi, guess - 1)
            guess = (lo + hi) // 2
            continue
        saw_chapter = True
        real = _title_num(d.get("title") or "")
        if real == num:
            return {
                "title": (d.get("title") or "").strip() or f"Chapter {num}",
                "text": _clean_text(d["text"]),
                "url": _CHAPTER_URL.format(chap_slug=f"{slug}-{guess}"),
                "source_slug": slug,
            }
        if real is None:
            # Can't map unnumbered rows — nudge toward num and count the
            # probe; a couple of these exhausts the budget honestly.
            guess = guess + 1 if guess < num else guess - 1
            continue
        if real < num:
            lo = guess + 1
            guess += num - real  # offset is usually uniform — extrapolate
        else:
            hi = guess - 1
            guess -= real - num
    if not saw_chapter:
        # Every probe 404'd — stub novel with no hosted chapters. Mark it
        # dead so the rest of this series' failed items don't each burn
        # a full probe budget against the same empty shelf.
        cache[series_name] = None
    return None
