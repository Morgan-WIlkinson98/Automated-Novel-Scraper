"""
generic_extractor.py

Generic chapter-text extraction from an arbitrary URL.
Depends on: trafilatura, readability-lxml, politeness
    pip install trafilatura readability-lxml
"""

import re
import trafilatura
from readability import Document
from dataclasses import dataclass
from typing import Optional
from politeness import polite_get

REQUEST_TIMEOUT = 15


@dataclass
class ExtractionResult:
    url: str
    title: Optional[str]
    text: Optional[str]
    method: str          # "trafilatura", "readability", or "failed"
    char_count: int
    paragraph_count: int
    passed_quality_check: bool


def fetch_html(url: str) -> Optional[str]:
    """Fetch raw HTML for a given URL using the politeness layer."""
    resp = polite_get(url, timeout=REQUEST_TIMEOUT)
    if resp is None:
        return None
    try:
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        print(f"[fetch_html] failed for {url}: {exc}")
        return None


def _extract_with_trafilatura(html: str, url: str):
    text = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_recall=False,
    )
    metadata = trafilatura.extract_metadata(html)
    title = metadata.title if metadata else None
    return title, text


def _extract_with_readability(html: str):
    doc = Document(html)
    title = doc.short_title()
    # readability-lxml returns an HTML summary; strip tags for plain text
    summary_html = doc.summary()
    text = re.sub(r"<[^>]+>", "\n", summary_html)
    text = re.sub(r"\n{2,}", "\n\n", text).strip()
    return title, text


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

    return "\n\n".join(kept)


def quality_check(text: str, min_chars: int = 500, min_paragraphs: int = 3) -> bool:
    if not text:
        return False
    char_count = len(text)
    paragraph_count = len([p for p in text.split("\n\n") if p.strip()])
    return char_count >= min_chars and paragraph_count >= min_paragraphs


def extract_chapter(url: str) -> ExtractionResult:
    """
    Attempt generic extraction of a chapter's text from a URL.
    Tries trafilatura first, falls back to readability-lxml,
    and reports whether the result passed a basic quality check
    so the caller can decide whether to hand off to a site override.
    Uses the politeness layer for all HTTP requests.
    """
    html = fetch_html(url)
    if not html:
        return ExtractionResult(url, None, None, "failed", 0, 0, False)

    title, text = _extract_with_trafilatura(html, url)
    method = "trafilatura"

    if not quality_check(text):
        alt_title, alt_text = _extract_with_readability(html)
        if quality_check(alt_text) and (not text or len(alt_text) > len(text)):
            title, text, method = alt_title, alt_text, "readability"

    text = clean_text(text) if text else text
    passed = quality_check(text)
    char_count = len(text) if text else 0
    paragraph_count = len([p for p in text.split("\n\n") if p.strip()]) if text else 0

    return ExtractionResult(
        url=url,
        title=title,
        text=text,
        method=method if passed else "failed",
        char_count=char_count,
        paragraph_count=paragraph_count,
        passed_quality_check=passed,
    )


if __name__ == "__main__":
    result = extract_chapter("https://example.invalid/some-chapter-url")
    if result.passed_quality_check:
        print(f"[{result.method}] {result.title} ({result.char_count} chars)")
    else:
        print(f"Generic extraction failed for {result.url} — needs a site override")
