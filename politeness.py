"""
politeness.py
Depends on: requests (stdlib urllib.robotparser)
"""

import time
import requests
import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from exceptions import RobotsTxtError, HTTPError, TimeoutError, ValidationError

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; ChapterFetcher/1.0; +https://example.invalid/bot-info)"
MIN_DELAY_SECONDS = 5

_last_request_time = {}
_robots_cache = {}

def _domain_of(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            raise ValidationError(f"Invalid URL: {url}")
        return parsed.netloc
    except Exception as e:
        logger.error(f"Failed to parse URL {url}: {e}")
        raise ValidationError(f"Invalid URL: {url}") from e

def _get_robot_parser(domain: str) -> RobotFileParser:
    """Get or create cached robots.txt parser for domain."""
    if domain not in _robots_cache:
        rp = RobotFileParser()
        rp.set_url(f"https://{domain}/robots.txt")
        try:
            rp.read()
            logger.debug(f"Loaded robots.txt for {domain}")
        except Exception as e:
            logger.warning(f"Failed to fetch robots.txt for {domain}: {e}. Failing open.")
            # Fail open but stay conservative elsewhere
        _robots_cache[domain] = rp
    return _robots_cache[domain]

def is_allowed(url: str) -> bool:
    """Check if URL is allowed by robots.txt."""
    try:
        domain = _domain_of(url)
        rp = _get_robot_parser(domain)
        allowed = rp.can_fetch(USER_AGENT, url)
        if not allowed:
            logger.info(f"robots.txt disallows {url}")
        return allowed
    except ValidationError:
        return False
    except Exception as e:
        logger.error(f"Error checking robots.txt for {url}: {e}")
        return False

def polite_get(url: str, timeout: int = 15) -> requests.Response | None:
    """Make a rate-limited HTTP request with robots.txt compliance."""
    try:
        domain = _domain_of(url)
    except ValidationError:
        return None

    if not is_allowed(url):
        return None

    # Rate limiting
    try:
        last = _last_request_time.get(domain, 0)
        wait = MIN_DELAY_SECONDS - (time.time() - last)
        if wait > 0:
            logger.debug(f"Rate limiting: waiting {wait:.2f}s for {domain}")
            time.sleep(wait)
    except Exception as e:
        logger.warning(f"Rate limiting error for {domain}: {e}")

    # Make request
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
        _last_request_time[domain] = time.time()
        logger.debug(f"Successfully fetched {url} (status: {resp.status_code})")
        return resp
    except requests.Timeout as e:
        logger.error(f"Timeout fetching {url}: {e}")
        return None
    except requests.HTTPError as e:
        logger.error(f"HTTP error fetching {url}: {e}")
        return None
    except requests.RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
        return None
