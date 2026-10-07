"""
generic_extractor.py

Generic chapter-text extraction from an arbitrary URL.
Depends on: trafilatura, readability-lxml, politeness
    pip install trafilatura readability-lxml
"""

import re
import logging
import trafilatura
from readability import Document
from dataclasses import dataclass
from typing import Optional
from scraping.politeness import polite_get
from core.exceptions import ExtractionError, QualityError, ValidationError


def _fetch_rendered_html(url: str, page=None) -> Optional[str]:
    """Use Playwright to render JS-heavy pages as a last resort.

    `page` lets a caller inside a long-lived Playwright session (request
    queue processing) reuse it — sync_playwright() can't start again
    while another instance is already running on this thread."""
    try:
        if page is not None:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            return page.content()
        from scraping.browser import get_page_html
        return get_page_html(url, timeout=60)
    except Exception as e:
        logger.warning(f"Browser-rendered fetch failed for {url}: {e}")
        return None

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15


@dataclass
class ExtractionResult:
    url: str
    title: Optional[str]
    text: Optional[str]
    method: str          # "trafilatura", "readability", "site_override", or "failed"
    char_count: int
    paragraph_count: int
    passed_quality_check: bool
    error: Optional[str] = None  # Error message if extraction failed


def fetch_html(url: str) -> Optional[str]:
    """Fetch raw HTML for a given URL using the politeness layer."""
    if not url or not isinstance(url, str):
        raise ValidationError(f"Invalid URL: {url}")

    logger.debug(f"Fetching HTML from {url}")
    resp = polite_get(url, timeout=REQUEST_TIMEOUT)
    if resp is None:
        logger.warning(f"Failed to fetch HTML from {url}")
        return None
    try:
        resp.raise_for_status()
        html = resp.text
        logger.debug(f"Successfully fetched {len(html)} characters from {url}")
        return html
    except Exception as exc:
        logger.error(f"[fetch_html] failed for {url}: {exc}")
        return None


def _extract_with_trafilatura(html: str, url: str):
    """Extract text using trafilatura library."""
    try:
        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            favor_recall=False,
        )
        metadata = trafilatura.extract_metadata(html)
        title = metadata.title if metadata else None
        logger.debug(f"Trafilatura extraction: title={title}, text_length={len(text) if text else 0}")
        return title, text
    except Exception as e:
        logger.error(f"Trafilatura extraction failed for {url}: {e}")
        return None, None


def _extract_with_readability(html: str):
    """Extract text using readability-lxml library."""
    try:
        doc = Document(html)
        title = doc.short_title()
        # readability-lxml returns an HTML summary; strip tags for plain text
        summary_html = doc.summary()
        text = re.sub(r"<[^>]+>", "\n", summary_html)
        text = re.sub(r"\n{2,}", "\n\n", text).strip()
        logger.debug(f"Readability extraction: title={title}, text_length={len(text) if text else 0}")
        return title, text
    except Exception as e:
        logger.error(f"Readability extraction failed: {e}")
        return None, None


def clean_text(text: str) -> str:
    """Basic whitespace normalization and residual-boilerplate line removal."""
    if not text:
        return text

    lines = [ln.strip() for ln in text.splitlines()]

    boilerplate_patterns = [
        r"^\s*(next|previous|prev)\s*(chapter)?\s*$",
        r"^\s*chapter\s*(index|list)\s*$",
        r"^\s*share\s*(this)?\s*$",
        r"^\s*advertisement\s*$",
    ]
    compiled = [re.compile(p, re.IGNORECASE) for p in boilerplate_patterns]

    kept = []
    for ln in lines:
        if not ln:
            continue
        if any(p.match(ln) for p in compiled):
            continue
        kept.append(ln)

    cleaned = "\n\n".join(kept)
    logger.debug(f"Cleaned text: {len(text)} -> {len(cleaned)} characters")
    return cleaned


def quality_check(text: str, min_chars: int = 500, min_paragraphs: int = 3) -> bool:
    """Validate extracted content quality."""
    if not text:
        return False
    char_count = len(text)
    paragraph_count = len([p for p in text.split("\n\n") if p.strip()])
    passed = char_count >= min_chars and paragraph_count >= min_paragraphs
    logger.debug(f"Quality check: chars={char_count}, paragraphs={paragraph_count}, passed={passed}")
    return passed


def extract_chapter(url: str, page=None) -> ExtractionResult:
    """
    Attempt generic extraction of a chapter's text from a URL.
    Tries trafilatura first, falls back to readability-lxml,
    and reports whether the result passed a basic quality check
    so the caller can decide whether to hand off to a site override.
    Uses the politeness layer for all HTTP requests.
    """
    if not url or not isinstance(url, str):
        return ExtractionResult(url, None, None, "failed", 0, 0, False, "Invalid URL")

    logger.info(f"Starting extraction for {url}")

    try:
        html = fetch_html(url)
        if not html:
            return ExtractionResult(url, None, None, "failed", 0, 0, False, "Failed to fetch HTML")

        title, text = _extract_with_trafilatura(html, url)
        method = "trafilatura"

        if not quality_check(text):
            logger.info(f"Trafilatura quality check failed, trying readability for {url}")
            alt_title, alt_text = _extract_with_readability(html)
            if quality_check(alt_text) and (not text or len(alt_text) > len(text)):
                title, text, method = alt_title, alt_text, "readability"
                logger.info(f"Readability extraction succeeded for {url}")

        # Last resort: render the page with Playwright for JS-heavy sites
        if not quality_check(text):
            logger.info(f"Readability also failed, trying browser-rendered fetch for {url}")
            rendered_html = _fetch_rendered_html(url, page=page)
            if rendered_html:
                logger.debug(f"Fetched rendered HTML ({len(rendered_html)} chars) for {url}")
                rendered_title, rendered_text = _extract_with_trafilatura(rendered_html, url)
                if not quality_check(rendered_text):
                    rendered_title, rendered_text = _extract_with_readability(rendered_html)
                if quality_check(rendered_text) and (not text or len(rendered_text) > len(text)):
                    title, text, method = rendered_title, rendered_text, "browser"
                    logger.info(f"Browser-rendered extraction succeeded for {url}")

        text = clean_text(text) if text else text
        passed = quality_check(text)
        char_count = len(text) if text else 0
        paragraph_count = len([p for p in text.split("\n\n") if p.strip()]) if text else 0

        if passed:
            logger.info(f"Extraction successful for {url}: method={method}, chars={char_count}")
        else:
            logger.warning(f"Extraction quality check failed for {url}: method={method}")

        return ExtractionResult(
            url=url,
            title=title,
            text=text,
            method=method if passed else "failed",
            char_count=char_count,
            paragraph_count=paragraph_count,
            passed_quality_check=passed,
            error=None if passed else f"Quality check failed (chars={char_count}, paragraphs={paragraph_count})",
        )
    except Exception as e:
        logger.error(f"Unexpected error during extraction for {url}: {e}")
        return ExtractionResult(url, None, None, "failed", 0, 0, False, str(e))


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    result = extract_chapter("https://example.invalid/some-chapter-url")
    if result.passed_quality_check:
        print(f"[{result.method}] {result.title} ({result.char_count} chars)")
    else:
        print(f"Generic extraction failed for {result.url} — needs a site override")
        if result.error:
            print(f"Error: {result.error}")
