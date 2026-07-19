"""
link_resolver.py
Depends on: requests
"""

import requests
import logging
from core.exceptions import HTTPError, TimeoutError, ValidationError
from core.settings import get_settings
from scraping.browser import resolve_with_browser, _is_novelupdates_extnu

logger = logging.getLogger(__name__)


def _get_request_kwargs(timeout: int):
    """Build request kwargs with headers, auth, and cookies from settings."""
    settings = get_settings()
    kwargs = {
        "timeout": timeout,
        "headers": {
            "User-Agent": settings.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
        },
    }
    
    cookies = settings.NOVELUPDATES_COOKIES if isinstance(settings.NOVELUPDATES_COOKIES, dict) else None
    if cookies:
        kwargs["cookies"] = cookies
    
    if settings.NOVELUPDATES_USERNAME and settings.NOVELUPDATES_PASSWORD:
        kwargs["auth"] = (settings.NOVELUPDATES_USERNAME, settings.NOVELUPDATES_PASSWORD)
    
    return kwargs


def resolve_final_url(url: str, timeout: int = 15) -> str:
    """Follow redirects and return the final destination URL."""
    if not url or not isinstance(url, str):
        raise ValidationError(f"Invalid URL: {url}")

    logger.debug(f"Resolving URL: {url}")
    request_kwargs = _get_request_kwargs(timeout)

    # Try HEAD first (lighter)
    try:
        resp = requests.head(url, allow_redirects=True, **request_kwargs)
        resp.raise_for_status()
        final_url = resp.url
        logger.debug(f"Resolved via HEAD: {url} -> {final_url}")
        return final_url
    except requests.Timeout as e:
        logger.warning(f"HEAD timeout for {url}, trying GET: {e}")
    except requests.HTTPError as e:
        logger.warning(f"HEAD HTTP error for {url}, trying GET: {e}")
    except requests.RequestException as e:
        logger.warning(f"HEAD failed for {url}, trying GET: {e}")

    # Fallback to GET (some servers reject HEAD)
    try:
        resp = requests.get(url, allow_redirects=True, stream=True, **request_kwargs)
        resp.raise_for_status()
        final_url = resp.url
        resp.close()
        logger.debug(f"Resolved via GET: {url} -> {final_url}")
        return final_url
    except requests.Timeout as e:
        logger.error(f"Timeout resolving {url}: {e}")
        raise TimeoutError(f"Timeout resolving URL {url}") from e
    except requests.HTTPError as e:
        # Log as warning rather than error; callers like the browser fallback
        # will handle 403/Cloudflare and log a real error only if that also fails.
        logger.warning(f"HTTP error resolving {url}: {e}")
        raise HTTPError(f"HTTP error resolving URL {url}: {e}") from e
    except requests.RequestException as e:
        logger.warning(f"Failed to resolve {url}: {e}")
        raise HTTPError(f"Failed to resolve URL {url}: {e}") from e


def resolve_final_url_with_browser_fallback(url: str, timeout: int = 15, use_browser: bool = True) -> str:
    """
    Resolve a URL. NovelUpdates extnu links go straight to browser automation
    because direct HTTP requests consistently return 403 Cloudflare pages.
    """
    if use_browser and _is_novelupdates_extnu(url):
        logger.debug(f"NovelUpdates extnu link, using browser directly: {url}")
        return resolve_with_browser(url, timeout=45)
    
    try:
        return resolve_final_url(url, timeout)
    except HTTPError as e:
        if use_browser:
            logger.debug(f"HTTP resolution failed, trying browser: {url}")
            return resolve_with_browser(url, timeout=45)
        raise
