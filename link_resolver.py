"""
link_resolver.py
Depends on: requests
"""

import requests
import logging
from exceptions import HTTPError, TimeoutError, ValidationError

logger = logging.getLogger(__name__)

def resolve_final_url(url: str, timeout: int = 15) -> str:
    """Follow redirects and return the final destination URL."""
    if not url or not isinstance(url, str):
        raise ValidationError(f"Invalid URL: {url}")

    logger.debug(f"Resolving URL: {url}")

    # Try HEAD first (lighter)
    try:
        resp = requests.head(url, allow_redirects=True, timeout=timeout)
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
        resp = requests.get(url, allow_redirects=True, timeout=timeout, stream=True)
        resp.raise_for_status()
        final_url = resp.url
        resp.close()
        logger.debug(f"Resolved via GET: {url} -> {final_url}")
        return final_url
    except requests.Timeout as e:
        logger.error(f"Timeout resolving {url}: {e}")
        raise TimeoutError(f"Timeout resolving URL {url}") from e
    except requests.HTTPError as e:
        logger.error(f"HTTP error resolving {url}: {e}")
        raise HTTPError(f"HTTP error resolving URL {url}: {e}") from e
    except requests.RequestException as e:
        logger.error(f"Failed to resolve {url}: {e}")
        raise HTTPError(f"Failed to resolve URL {url}: {e}") from e
