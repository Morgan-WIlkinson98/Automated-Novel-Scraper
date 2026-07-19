"""
politeness.py
Depends on: requests (stdlib urllib.robotparser)
"""

import time
import requests
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

USER_AGENT = "Mozilla/5.0 (compatible; ChapterFetcher/1.0; +https://example.invalid/bot-info)"
MIN_DELAY_SECONDS = 5

_last_request_time = {}
_robots_cache = {}

def _domain_of(url: str) -> str:
    return urlparse(url).netloc

def _get_robot_parser(domain: str) -> RobotFileParser:
    if domain not in _robots_cache:
        rp = RobotFileParser()
        rp.set_url(f"https://{domain}/robots.txt")
        try:
            rp.read()
        except Exception:
            pass  # if robots.txt is unreachable, fail open but stay conservative elsewhere
        _robots_cache[domain] = rp
    return _robots_cache[domain]

def is_allowed(url: str) -> bool:
    domain = _domain_of(url)
    rp = _get_robot_parser(domain)
    return rp.can_fetch(USER_AGENT, url)

def polite_get(url: str, timeout: int = 15) -> requests.Response | None:
    domain = _domain_of(url)

    if not is_allowed(url):
        print(f"[politeness] robots.txt disallows {url}, skipping")
        return None

    last = _last_request_time.get(domain, 0)
    wait = MIN_DELAY_SECONDS - (time.time() - last)
    if wait > 0:
        time.sleep(wait)

    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        _last_request_time[domain] = time.time()
        return resp
    except requests.RequestException as exc:
        print(f"[politeness] request failed for {url}: {exc}")
        return None
