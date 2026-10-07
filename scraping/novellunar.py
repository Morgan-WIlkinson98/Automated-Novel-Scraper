"""novellunar.com fallback source — Next.js SSR, no Cloudflare wall.

Layout:
    /?s={name}                      → search results with /novel/{slug} links
    /novel/{slug}                   → novel page (title in <title>)
    /novel/{slug}/chapter/{num}     → chapter page; the prose isn't in
                                      the DOM — it rides inside the RSC
                                      stream (self.__next_f.push chunks)
                                      as a `T<hexlen>,<text>` field.
                                      The chapter body is the largest
                                      T payload on the page; everything
                                      else is ~1-2KB rec-card blurbs.

Chapter URLs carry the real chapter number directly, so no index
probing — /chapter/42 *is* chapter 42.
"""

import json
import logging
import re
import time

import requests

logger = logging.getLogger(__name__)

_BASE = "https://novellunar.com"
_UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0 Safari/537.36"
}
_TIMEOUT = 15
_PROBE_DELAY = 0.35

_NOVEL_LINK = re.compile(r'/novel/([a-z0-9-]+)')
_PUSH_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', re.S)
_T_FIELD = re.compile(r'\n?\d+:T([0-9a-fA-F]+),')
_MIN_CHAPTER_BYTES = 1500  # rec blurbs top out ~2KB; chapters run 5K+


def _slugify(name: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", name or "") \
        .encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9\s]+", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    return re.sub(r"-+", "-", s) or "unknown"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _get(url: str, params: dict = None):
    try:
        r = requests.get(url, params=params, headers=_UA,
                         timeout=_TIMEOUT)
        return r if r.ok else None
    except Exception as e:
        logger.debug(f"novellunar {url}: {e}")
        return None


def _novel_title(html: str) -> str:
    """<title> on novel pages looks like 'Renegade Immortal Novel'."""
    m = re.search(r"<title>(.*?)</title>", html or "", re.S)
    return re.sub(r"\s+Novel\s*$", "", m.group(1)).strip() if m else ""


def _novel_slug(series_name: str, cache: dict):
    """series_name → novellunar slug (or None), cached per run."""
    if series_name in cache:
        return cache[series_name]
    slug = None
    guess = _slugify(series_name)
    r = _get(f"{_BASE}/novel/{guess}")
    if r and _norm(_novel_title(r.text)) == _norm(series_name):
        slug = guess
    else:
        r = _get(f"{_BASE}/", params={"s": series_name})
        candidates = list(dict.fromkeys(
            _NOVEL_LINK.findall(r.text)))[:5] if r else []
        for cand in candidates:
            n = _get(f"{_BASE}/novel/{cand}")
            if n and _norm(_novel_title(n.text)) == _norm(series_name):
                slug = cand
                break
    cache[series_name] = slug
    return slug


def _chapter_text(html: str) -> str:
    """Pull the chapter body out of the RSC stream — it's the largest
    `T<hexlen>,` field on the page; smaller ones are rec-card blurbs."""
    chunks = _PUSH_CHUNK.findall(html or "")
    if not chunks:
        return ""
    try:
        stream = "".join(json.loads('"' + c + '"') for c in chunks)
    except Exception:
        return ""
    best = ""
    for m in _T_FIELD.finditer(stream):
        size = int(m.group(1), 16)
        if size < _MIN_CHAPTER_BYTES or size <= len(best):
            continue
        best = stream[m.end():m.end() + size]
    return best.strip()


def _chapter_num(title: str):
    m = re.search(r"chapter\s*(\d+)", title or "", re.I)
    return int(m.group(1)) if m else None


def fetch_chapter(series_name: str, num, cache: dict, page=None):
    """(series, NU chapter num) → novellunar chapter, or None on miss.

    page is accepted for signature parity with the other sources;
    novellunar needs no browser."""
    del page
    if num is None:
        return None
    if isinstance(num, float) and not num.is_integer():
        return None
    try:
        num = int(num)
    except (TypeError, ValueError):
        return None
    slug = _novel_slug(series_name, cache)
    if not slug:
        return None

    time.sleep(_PROBE_DELAY)
    url = f"{_BASE}/novel/{slug}/chapter/{num}"
    r = _get(url)
    if not r:
        return None
    # The URL number is already the real chapter number — sanity-check
    # via the page title ('<Series> Chapter N: ...') so a numbering
    # quirk still misses honestly instead of saving the wrong chapter.
    mt = re.search(r"<title>(.*?)</title>", r.text, re.S)
    title = mt.group(1).strip() if mt else ""
    if _chapter_num(title) != num:
        logger.debug(f"novellunar {slug}: chapter/{num} titled {title!r}")
        return None
    text = _chapter_text(r.text)
    if not text:
        return None
    return {
        "title": title,
        "text": text,
        "url": url,
        "source_slug": slug,
    }
