"""
curl_parser.py
Parse a curl command into scraper configuration values.
"""

import re
import shlex
import logging
from urllib.parse import urlparse, unquote

logger = logging.getLogger(__name__)


def _find_flag_value(parts: list, short: str, long: str = None) -> str:
    """Find the value of a flag like -b / --cookie in a tokenized curl command."""
    for i, part in enumerate(parts):
        if part == short or (long and part == long):
            if i + 1 < len(parts):
                return parts[i + 1]
        if part.startswith(short) and len(part) > len(short):
            return part[len(short):]
        if long and part.startswith(long + '='):
            return part[len(long) + 1:]
    return None


def _find_quoted(parts: list, flag: str) -> str:
    """Find a flag that takes the next shell-quoted argument."""
    for i, part in enumerate(parts):
        if part == flag:
            if i + 1 < len(parts):
                return parts[i + 1]
    return None


def _find_header(parts: list, header_name: str) -> str:
    """Find the value of an HTTP header passed with -H/--header."""
    pattern = re.compile(rf"^{re.escape(header_name)}:\s*(.+)$", re.IGNORECASE)
    for part in parts:
        m = pattern.match(part)
        if m:
            return m.group(1).strip()
    return None


def _extract_cookies(parts: list) -> dict:
    """Extract cookies from -b, --cookie, or Cookie header."""
    cookie_source = _find_flag_value(parts, '-b', '--cookie') or _find_header(parts, 'cookie')
    if not cookie_source:
        return None
    
    # Strip surrounding quotes if present
    cookie_source = cookie_source.strip("'\"")
    cookies = {}
    for item in cookie_source.split(';'):
        item = item.strip()
        if not item:
            continue
        if '=' in item:
            key, value = item.split('=', 1)
            cookies[key.strip()] = value.strip()
    return cookies if cookies else None


def _extract_user_agent(parts: list) -> str:
    """Extract User-Agent from -H or -A/--user-agent."""
    ua = _find_header(parts, 'user-agent')
    if ua:
        return ua.strip("'\"")
    ua = _find_flag_value(parts, '-A', '--user-agent')
    if ua:
        return ua.strip("'\"")
    return None


def _extract_basic_auth(parts: list) -> tuple:
    """Extract username/password from -u/--user."""
    auth = _find_flag_value(parts, '-u', '--user')
    if not auth:
        return None, None
    auth = auth.strip("'\"")
    if ':' in auth:
        return auth.split(':', 1)
    # curl may ask for password interactively, which we can't handle
    return auth, None


def _extract_url(parts: list) -> str:
    """Extract the URL from the curl command."""
    # The URL is usually the last non-flag token, but we need to be careful.
    # Heuristic: any token that looks like http(s):// and is not a flag value.
    skip_next = False
    for i, part in enumerate(parts):
        if skip_next:
            skip_next = False
            continue
        if part in ('-b', '--cookie', '-H', '--header', '-A', '--user-agent', '-u', '--user'):
            skip_next = True
            continue
        if part.startswith('http://') or part.startswith('https://'):
            return part.strip("'\"")
    # Fallback: try last token if it looks like a URL
    for part in reversed(parts):
        if part.startswith('http://') or part.startswith('https://'):
            return part.strip("'\"")
    return None


def _is_rss_url(url: str) -> bool:
    """Check if a URL is likely an RSS feed."""
    if not url:
        return False
    path = urlparse(url).path.lower()
    return 'rss' in path or 'feed' in path or url.endswith('.xml') or url.endswith('.rss')


def parse_curl_command(command: str) -> dict:
    """
    Parse a curl command string into a dict of configuration updates.
    
    Returns:
        dict with keys such as:
        - NOVELUPDATES_COOKIES
        - USER_AGENT
        - NOVELUPDATES_USERNAME
        - NOVELUPDATES_PASSWORD
        - RSS_FEED_URL
        - (and any headers that should override defaults)
    """
    if not command or not isinstance(command, str):
        return {}
    
    updates = {}
    try:
        # Use posix=True and keep whitespace inside quotes
        parts = shlex.split(command, posix=True)
    except ValueError as e:
        logger.error(f"Failed to parse curl command: {e}")
        return {}
    
    cookies = _extract_cookies(parts)
    if cookies is not None:
        updates['NOVELUPDATES_COOKIES'] = cookies
    
    user_agent = _extract_user_agent(parts)
    if user_agent:
        updates['USER_AGENT'] = user_agent
    
    username, password = _extract_basic_auth(parts)
    if username:
        updates['NOVELUPDATES_USERNAME'] = username
    if password:
        updates['NOVELUPDATES_PASSWORD'] = password
    
    url = _extract_url(parts)
    if url and _is_rss_url(url):
        updates['RSS_FEED_URL'] = url
    
    # Extract some additional headers useful for Cloudflare bypass
    accept = _find_header(parts, 'accept')
    if accept:
        updates.setdefault('EXTRA_HTTP_HEADERS', {})
        updates['EXTRA_HTTP_HEADERS']['Accept'] = accept
    
    referer = _find_header(parts, 'referer')
    if referer:
        updates.setdefault('EXTRA_HTTP_HEADERS', {})
        updates['EXTRA_HTTP_HEADERS']['Referer'] = referer
    
    return updates
