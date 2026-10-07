"""wuxiaworld.eu fallback source — Next.js SSR pages.

When an NU-linked chapter resolve/extract fails (CF block, dead
aggregator host, no site override), try fetching the same chapter from
wuxiaworld.eu instead.

History: the site previously exposed a JSON API under /api/* (novels,
getchapter). That surface was retired in the October 2026 rebuild —
the site is now server-rendered Next.js, and every page embeds its
payload in a __NEXT_DATA__ script tag, which is actually cleaner:

    /search?q={name}            → HTML results with /novel/{slug} links
    /novel/{slug}               → pageProps.novel {title, altTitles,
                                  chapterCount, firstChapterNumber,
                                  latestChapterNumber}
    /chapter/{slug}-{idx}       → pageProps.data.chapter {number, title,
                                  paragraphs[]}  — `number` is the real
                                  chapter number, authoritative over
                                  title text.

Numbering caveat: {slug}-{idx} uses wuxiaworld's own position index,
which drifts from NU's "cN" numbering by however many prologue/extra
rows sit before it. chapter.number is monotonic with the index, so we
extrapolate-then-binary-search the index for the chapter whose number
matches. Missing numbering = honest miss, never a wrong-chapter guess.
"""

import json
import logging
import re
import time

import requests

logger = logging.getLogger(__name__)

_BASE = "https://wuxiaworld.eu"
_NOVEL_URL = _BASE + "/novel/{slug}"
_CHAPTER_URL = _BASE + "/chapter/{chap_slug}"
_UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0 Safari/537.36"
}
_TIMEOUT = 15
_MAX_PROBES = 8      # index-search fetches per chapter, worst case
_PROBE_DELAY = 0.35  # politeness between page fetches

_NEXT_DATA = re.compile(r'__NEXT_DATA__[^>]*>(.*?)</script>', re.S)
_NOVEL_LINK = re.compile(r'/novel/([a-z0-9-]+)')

# Boilerplate paragraphs wuxiaworld prepends to chapter bodies.
_BOILER = re.compile(
    r"(?i)^(publishedat\b.*|if audio player doesn't work.*|"
    r"chapter\s*\d+(?:\.\d+)?\s*)$"
)


def _slugify(name: str) -> str:
    """NU-slug-style normalize — mirrors data.firestore_store._slugify.
    Note it collapses "son-in-law" → "soninlaw" while wuxiaworld keeps
    interior hyphens; the search fallback covers those mismatches."""
    import unicodedata
    s = unicodedata.normalize("NFKD", name or "") \
        .encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9\s]+", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    return re.sub(r"-+", "-", s) or "unknown"


def _get(path: str, params: dict = None):
    """GET a wuxiaworld page → parsed __NEXT_DATA__ props, or None."""
    try:
        r = requests.get(_BASE + path, params=params, headers=_UA,
                         timeout=_TIMEOUT)
        if not r.ok:
            return None
        m = _NEXT_DATA.search(r.text)
        if not m:
            return None
        return json.loads(m.group(1)).get("props", {}).get("pageProps")
    except Exception as e:
        logger.debug(f"wuxiaworld {path}: {e}")
        return None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _name_match(novel: dict, series_name: str) -> bool:
    """Novel-page sanity check — title or an alt title must equal the
    series name after normalization (search ranking otherwise returns
    the whole catalog by vibes)."""
    target = _norm(series_name)
    if not target:
        return False
    if _norm(novel.get("title") or novel.get("name")) == target:
        return True
    for alias in novel.get("altTitles") or novel.get("other_names") or []:
        text = alias.get("name") if isinstance(alias, dict) else alias
        if _norm(text) == target:
            return True
    return False


def _novel(slug: str):
    """/novel/{slug} → its pageProps.novel dict, or None."""
    props = _get(f"/novel/{slug}")
    return (props or {}).get("novel")


def _novel_slug(series_name: str, cache: dict):
    """series_name → wuxiaworld slug (or None), cached per run.
    A novel must actually host chapters — stubs with chapterCount=0
    (like NU-mirror entries) are dead ends."""
    if series_name in cache:
        return cache[series_name]
    slug = None
    n = _novel(_slugify(series_name))
    if n and n.get("chapterCount") and _name_match(n, series_name):
        slug = n.get("slug") or _slugify(series_name)
    else:
        # Search page results link straight to /novel/{slug}; probe a
        # few candidates and keep the first verified name match with
        # real chapters.
        try:
            r = requests.get(_BASE + "/search",
                             params={"q": series_name}, headers=_UA,
                             timeout=_TIMEOUT)
            candidates = list(dict.fromkeys(
                _NOVEL_LINK.findall(r.text)))[:5] if r.ok else []
        except Exception as e:
            logger.debug(f"wuxiaworld search: {e}")
            candidates = []
        for cand in candidates:
            n = _novel(cand)
            if n and n.get("chapterCount") \
                    and _name_match(n, series_name):
                slug = cand
                break
    cache[series_name] = slug
    return slug


def _chapter(slug: str, idx: int):
    """/chapter/{slug}-{idx} → pageProps.data.chapter dict, or None."""
    props = _get(f"/chapter/{slug}-{idx}")
    return ((props or {}).get("data") or {}).get("chapter")


def _clean_paragraphs(paragraphs) -> str:
    """Join paragraph strings, dropping boilerplate lines."""
    lines = [p.strip() for p in (paragraphs or [])
             if isinstance(p, str) and not _BOILER.match(p.strip())]
    return "\n\n".join(lines).strip()


def fetch_chapter(series_name: str, num, cache: dict, page=None):
    """Best-effort (series, NU chapter num) → wuxiaworld chapter.

    Returns dict(title, text, url, source_slug) on a verified number
    match, else None. Probes ≤_MAX_PROBES pages — cheap enough to run
    per failed queue item. `page` is unused (plain HTTP suffices) but
    accepted for signature parity with the other mirror sources."""
    del page
    if num is None:
        return None
    if isinstance(num, float) and not num.is_integer():
        return None  # fractional chapters (c72.5) can't map to int numbers
    try:
        num = int(num)
    except (TypeError, ValueError):
        return None
    slug = _novel_slug(series_name, cache)
    if not slug:
        return None

    # Index search: the chapter index and chapter.number move together,
    # so each probe's number tells us which way to jump.
    lo, hi = 1, None
    guess = num
    tried = set()
    saw_chapter = False  # any chapter hit at all — stubs 404 every probe
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
        c = _chapter(slug, guess)
        real = (c or {}).get("number")
        if real is None:
            # Past the hosted tail (or unnumbered row) — pull bound in.
            hi = guess - 1 if hi is None else min(hi, guess - 1)
            guess = (lo + hi) // 2
            continue
        saw_chapter = True
        try:
            real = int(real)
        except (TypeError, ValueError):
            real = None
        if real == num:
            return {
                "title": (c.get("title") or "").strip() or f"Chapter {num}",
                "text": _clean_paragraphs(c.get("paragraphs")),
                "url": _CHAPTER_URL.format(chap_slug=f"{slug}-{guess}"),
                "source_slug": slug,
            }
        if real is None:
            # Can't map unnumbered rows — nudge toward num and count the
            # probe; a couple of these exhausts the budget honestly.
            guess += 1 if num >= guess else -1
            continue
        if real < num:
            lo = guess + 1
        else:
            hi = guess - 1
    if saw_chapter:
        logger.debug(f"wuxiaworld {slug}: no index maps to chapter {num}")
    return None
