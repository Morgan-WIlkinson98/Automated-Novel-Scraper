"""
Utility functions including retry logic for transient failures.
"""

import re
import time
import logging
import unicodedata
from functools import wraps
from typing import Callable, Type, Tuple, Optional

logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None,
):
    """
    Decorator to retry a function on specific exceptions with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exception types to catch and retry on
        on_retry: Optional callback function called before each retry
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts - 1:
                        logger.error(f"Function {func.__name__} failed after {max_attempts} attempts: {e}")
                        raise
                    
                    logger.warning(
                        f"Function {func.__name__} failed (attempt {attempt + 1}/{max_attempts}): {e}. "
                        f"Retrying in {current_delay:.2f}s..."
                    )
                    
                    if on_retry:
                        on_retry(attempt + 1, e)
                    
                    time.sleep(current_delay)
                    current_delay *= backoff
            
            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
        
        return wrapper
    return decorator


def clean_series_name(title: str) -> str:
    """Remove trailing chapter labels like ' c226' from an RSS or list entry title."""
    if not title:
        return "Unknown"
    title = re.sub(r'\s+[Pp]art(?:\s*\d+(?:\.\d+)?(?:\s*/\s*\d+)?)?\s*$', '', title)
    title = re.sub(r'\s*[Cc][\.\s]?\d+(?:\.\d+)?\s*$', '', title)
    title = re.sub(r'\s*[Cc]hapter\s*\d+(?:\.\d+)?\s*$', '', title)
    title = re.sub(r'\s*\(?\d+(?:\.\d+)?\)?\s*$', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title.strip() or "Unknown"


def novelupdates_series_url(title: str) -> str:
    """Build a NovelUpdates series URL from a series title, matching NU's slug style.

    Example: "Black Bellied Prince's Stunning Abandoned Consort" becomes
    https://www.novelupdates.com/series/black-bellied-princes-stunning-abandoned-consort/
    """
    if not title:
        return ""
    # Strip ASCII-folding (accents) and lower-case
    slug = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode('ascii').lower()
    # Remove characters that are not letters, numbers, or whitespace
    slug = re.sub(r'[^a-z0-9\s]+', '', slug)
    # Collapse whitespace and convert to hyphens
    slug = re.sub(r'\s+', '-', slug.strip())
    slug = re.sub(r'-+', '-', slug)
    return f"https://www.novelupdates.com/series/{slug}/" if slug else ""
