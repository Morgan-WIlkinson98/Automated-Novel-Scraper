"""
set_cookies.py
Helper to parse a curl -b cookie string and save it to config.py.
"""

import re
import sys
from pathlib import Path


def parse_cookie_string(cookie_string: str) -> dict:
    """Parse a semicolon-separated cookie string into a dictionary."""
    cookies = {}
    for item in cookie_string.split('; '):
        if not item:
            continue
        if '=' in item:
            key, value = item.split('=', 1)
            cookies[key.strip()] = value.strip()
    return cookies


def update_config_cookies(cookies: dict, config_path: str = "config.py"):
    """Update NOVELUPDATES_COOKIES in config.py."""
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"{config_path} not found")
    
    content = config_file.read_text()
    
    # Build cookie dict string
    lines = ["NOVELUPDATES_COOKIES = {"]
    for key, value in cookies.items():
        # Escape backslashes and quotes for Python string literal
        safe_value = value.replace('\\', '\\\\').replace('"', '\\"')
        lines.append(f'    "{key}": "{safe_value}",')
    lines.append("}")
    
    cookie_block = "\n".join(lines)
    
    # Replace existing NOVELUPDATES_COOKIES line(s)
    pattern = r'^NOVELUPDATES_COOKIES\s*=\s*.*$'
    new_content, count = re.subn(pattern, cookie_block, content, flags=re.MULTILINE)
    
    if count == 0:
        # Insert before Polling Configuration section
        new_content = re.sub(
            r'^(# Polling Configuration)$',
            cookie_block + "\n\n\\1",
            content,
            flags=re.MULTILINE,
        )
    
    config_file.write_text(new_content)
    print(f"Updated NOVELUPDATES_COOKIES in {config_path} ({len(cookies)} cookies)")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cookie_string = sys.argv[1]
    else:
        cookie_string = sys.stdin.read().strip()
    
    if not cookie_string:
        print("Usage: python3 set_cookies.py 'cookie1=value1; cookie2=value2'")
        sys.exit(1)
    
    cookies = parse_cookie_string(cookie_string)
    update_config_cookies(cookies)
