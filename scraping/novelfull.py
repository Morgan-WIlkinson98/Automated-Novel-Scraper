"""novelfull.net fallback source.

Classic truyen-family layout:
    /search?keyword={name}      → result links like /{slug}.html
    /{slug}.html                → novel page
    /{slug}/chapter-{num}.html  → chapter page, prose in #chapter-content

Chapter URLs carry the real chapter number directly, so no index
probing — /chapter-42.html *is* chapter 42.

Plain requests get a Cloudflare challenge (HTTP 403) much of the time,
so fetch_chapter accepts the shared Playwright `page` and falls back
to it; if the challenge defeats the browser too we miss honestly and
the chain moves on to novellunar.
"""

import logging
import re
import time

import requests

logger = logging.getLogger(__name__)

_BASE = "https://novelfull.net"
_UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0 Safari/537.36"
}
_TIMEOUT = 15
_PROBE_DELAY = 0.35

_NOVEL_LINK = re.compile(r'/([a-z0-9-]+)\.html')


def _slugify(name: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", name or "") \
        .encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9\s]+", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    return re.sub(r"-+", "-", s) or "unknown"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _cf_blocked(resp) -> bool:
    if resp is None:
        return False
    if resp.status_code == 403:
        return True
    head = (resp.text or "")[:2000].lower()
    return "just a moment" in head or "cf-chl" in head


def _get(url: str, params: dict = None):
    try:
        return requests.get(url, params=params, headers=_UA,
                            timeout=_TIMEOUT)
    except Exception as e:
        logger.debug(f"novelfull {url}: {e}")
        return None


def _browser_get(page, url: str) -> str:
    """Render `url` in the shared Playwright page; '' on failure."""
    try:
        resp = page.goto(url, wait_until="domcontentloaded",
                         timeout=45000)
        # Give a CF interstitial a moment to resolve, then give up —
        # the challenge either clears quickly or not at all.
        if resp and resp.status == 403:
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
        html = page.content()
        if "just a moment" in html[:2000].lower():
            return ""
        return html
    except Exception as e:
        logger.debug(f"novelfull browser {url}: {e}")
        return ""


def _novel_title(html: str) -> str:
    for pat in (
        r'<h3[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)<',
        r"<h3[^>]*>(.*?)</h3>",
        r"<title>(.*?)<",
    ):
        m = re.search(pat, html or "", re.S | re.I)
        if m:
            t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            return t.split("|")[0].split(" - ")[0].strip() or t
    return ""


def _novel_slug(series_name: str, cache: dict, page=None):
    if series_name in cache:
        return cache[series_name]
    slug = None
    target = _norm(series_name)

    def _verify(cand):
        r = _get(f"{_BASE}/{cand}.html")
        html = None
        if r and r.ok and not _cf_blocked(r):
            html = r.text
        elif page and (r is None or _cf_blocked(r)):
            html = _browser_get(page, f"{_BASE}/{cand}.html") or None
        return bool(html) and _norm(_novel_title(html)) == target

    guess = _slugify(series_name)
    if _verify(guess):
        slug = guess
    else:
        r = _get(f"{_BASE}/search", params={"keyword": series_name})
        html = None
        if r and r.ok and not _cf_blocked(r):
            html = r.text
        elif page and (r is None or _cf_blocked(r)):
            html = _browser_get(
                page, f"{_BASE}/search?keyword="
                + requests.utils.quote(series_name)) or None
        if html:
            for cand in list(dict.fromkeys(
                    _NOVEL_LINK.findall(html)))[:5]:
                if _verify(cand):
                    slug = cand
                    break
    cache[series_name] = slug
    return slug


def _chapter_num(label: str):
    m = re.search(r"chapter\s*(\d+)", label or "", re.I)
    return int(m.group(1)) if m else None


def _parse_chapter(html: str, num: int, url: str, slug: str):
    """Extract title + prose from a chapter page; None on mismatch."""
    mh = re.search(
        r'<h2[^>]*>(.*?)</h2>', html or "", re.S | re.I)
    if not mh:
        mh = re.search(r"<title>(.*?)</title>", html or "", re.S | re.I)
    title = re.sub(r"<[^>]+>", "", mh.group(1)).strip() if mh else ""
    if _chapter_num(title) != num:
        return None
    mc = re.search(
        r'<div[^>]*id="chapter-content"[^>]*>(.*?)</div>',
        html or "", re.S | re.I)
    if not mc:
        return None
    text = re.sub(r"<br[^>]*>", "\n", mc.group(1))
    text = re.sub(r"<[^>]+>", "", text)
    import html as _html
    text = _html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 500:
        return None
    return {"title": title, "text": text, "url": url,
            "source_slug": slug}


def fetch_chapter(series_name: str, num, cache: dict, page=None):
    """(series, NU chapter num) → novelfull chapter, or None on miss."""
    if num is None:
        return None
    if isinstance(num, float) and not num.is_integer():
        return None
    try:
        num = int(num)
    except (TypeError, ValueError):
        return None
    slug = _novel_slug(series_name, cache, page)
    if not slug:
        return None

    time.sleep(_PROBE_DELAY)
    url = f"{_BASE}/{slug}/chapter-{num}.html"
    r = _get(url)
    html = None
    if r and r.ok and not _cf_blocked(r):
        html = r.text
    elif page:
        html = _browser_get(page, url) or None
    if not html:
        return None
    return _parse_chapter(html, num, url, slug)
