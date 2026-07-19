"""
series_scraper.py
Scrape NovelUpdates series pages for synopsis and chapter lists.
Uses Playwright to bypass Cloudflare, and BeautifulSoup to parse the HTML.
"""

import logging
import json
import re
import time
from typing import List, Optional, Dict
from urllib.parse import urljoin, urlparse
from core.exceptions import HTTPError

logger = logging.getLogger(__name__)


def _extract_series_url_from_summary(summary: str) -> Optional[str]:
    """Find the NovelUpdates series URL in an RSS summary/description."""
    match = re.search(r'https?://www\.novelupdates\.com/series/[^/\s]+/?', summary)
    return match.group(0).rstrip('/') + '/' if match else None


def _parse_chapter_list(html: str, base_url: str) -> List[Dict]:
    """Attempt to find all chapter links on a NovelUpdates series page."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("BeautifulSoup not installed. Run: pip install beautifulsoup4")
        raise HTTPError("BeautifulSoup not installed")
    
    soup = BeautifulSoup(html, 'html.parser')
    chapters = []
    seen_urls = set()
    
    # Strategy 1: links with class or containing 'extnu'
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text(strip=True) or ''
        full_url = urljoin(base_url, href)
        if '/extnu/' in full_url or 'novelupdates.com/extnu/' in full_url:
            # Try to extract chapter number from surrounding text or link text
            number = _guess_chapter_number(text)
            if full_url not in seen_urls:
                seen_urls.add(full_url)
                chapters.append({
                    'number': number,
                    'title': text,
                    'extnu_url': full_url,
                })
    
    # Strategy 2: rows in the chapter table (NU commonly uses .chapter-list or similar)
    if not chapters:
        for tr in soup.find_all('tr'):
            tds = tr.find_all(['td', 'th'])
            if not tds:
                continue
            for td in tds:
                a = td.find('a', href=True)
                if not a:
                    continue
                full_url = urljoin(base_url, a['href'])
                if '/extnu/' in full_url and full_url not in seen_urls:
                    seen_urls.add(full_url)
                    text = a.get_text(strip=True)
                    chapters.append({
                        'number': _guess_chapter_number(text),
                        'title': text,
                        'extnu_url': full_url,
                    })
    
    # Sort by chapter number where possible, otherwise stable order
    chapters.sort(key=lambda c: (c['number'] if c['number'] is not None else float('inf')))
    return chapters


def _guess_chapter_number(text: str) -> Optional[int]:
    """Try to extract a chapter number from chapter text."""
    if not text:
        return None
    patterns = [
        r'[Cc]hapter\s*(\d+)',
        r'[Cc]\s*(\d+)',
        r'\b(\d+)\b',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return int(m.group(1))
    return None


def _get_max_page(html: str) -> Optional[int]:
    """Extract the highest pagination page number from NovelUpdates pagination links."""
    # e.g. href="./?pg=12#myTable"
    matches = re.findall(r'[?&]pg=(\d+)(?:#myTable)?"', html)
    if not matches:
        matches = re.findall(r'[?&]pg=(\d+)', html)
    if matches:
        return max(int(m) for m in matches)
    return None


def _extract_synopsis(html: str) -> str:
    """Try to extract the series synopsis from the page."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return ''
    
    soup = BeautifulSoup(html, 'html.parser')
    # Common NU container IDs/classes
    selectors = [
        '#editdescription',
        '.summary-content',
        '.series-synopsis',
        '[itemprop="description"]',
        '.sContent',
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            return el.get_text('\n', strip=True)
    # Fallback: meta description
    meta = soup.find('meta', attrs={'name': 'description'})
    if meta and meta.get('content'):
        return meta['content'].strip()
    return ''


def scrape_series_page(series_url: str, timeout: int = 60, max_pages: int = 1200) -> Dict:
    """Scrape a NovelUpdates series page for synopsis and all paginated chapters."""
    from scraping.browser import get_browser_page
    
    base_url = series_url.rstrip('/') + '/'
    logger.info(f"Scraping series page: {base_url}")
    
    synopsis = ''
    chapters = []
    seen_urls = set()
    
    with get_browser_page(timeout=timeout) as page:
        # First page: synopsis and first batch of chapters
        page.goto(base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(7000)
        html = page.content()
        
        if 'cloudflare' in html.lower():
            raise HTTPError(f"Cloudflare challenge blocked {base_url}")
        
        synopsis = _extract_synopsis(html)
        chapters = _parse_chapter_list(html, base_url)
        seen_urls = {c['extnu_url'] for c in chapters}
        
        # Use the actual highest page number from the pagination links, capped by max_pages
        parsed_max_page = _get_max_page(html)
        last_page = min(parsed_max_page, max_pages) if parsed_max_page else max_pages
        logger.info(f"Detected {last_page} chapter pages for {base_url}")
        
        # Follow paginated chapter tables (?pg=2#myTable, etc.) until no new chapters
        for pg in range(2, last_page + 1):
            page_url = urljoin(base_url, f'?pg={pg}#myTable')
            logger.info(f"Scraping page {pg}: {page_url}")
            try:
                page.goto(page_url, wait_until="domcontentloaded")
                page.wait_for_timeout(7000)
            except Exception as e:
                logger.warning(f"Failed to load page {pg}: {e}")
                break
            
            html = page.content()
            if 'cloudflare' in html.lower():
                logger.warning(f"Cloudflare challenge on page {pg}, stopping pagination")
                break
            
            page_chapters = _parse_chapter_list(html, base_url)
            new_chapters = [c for c in page_chapters if c['extnu_url'] not in seen_urls]
            if not new_chapters:
                break
            
            for c in new_chapters:
                seen_urls.add(c['extnu_url'])
                chapters.append(c)
            
            # Small delay to avoid hammering the site
            time.sleep(1.5)
    
    # Sort ascending by chapter number where available
    chapters.sort(key=lambda c: (c['number'] if c['number'] is not None else float('inf')))
    logger.info(f"Found {len(chapters)} chapters on {series_url}")
    return {
        'url': series_url,
        'synopsis': synopsis,
        'chapters': chapters,
    }


def filter_chapters(chapters: List[Dict], start: Optional[int] = None, end: Optional[int] = None) -> List[Dict]:
    """Filter chapter list by chapter number range."""
    result = []
    for ch in chapters:
        num = ch.get('number')
        if num is None:
            continue
        if start is not None and num < start:
            continue
        if end is not None and num > end:
            continue
        result.append(ch)
    return result
