"""
parse_curl_cookies.py
Parse a curl command file and extract the -b cookie string,
then update config.py via set_cookies.py.
"""

import re
import sys
from pathlib import Path
from set_cookies import parse_cookie_string, update_config_cookies


def extract_cookie_string_from_curl(text: str) -> str:
    """Extract the value of the -b/--cookie argument from a curl command."""
    # Try -b '...' or --cookie '...'
    match = re.search(r"-b\s+['\"]([^'\"]+)['\"]", text)
    if not match:
        match = re.search(r"--cookie\s+['\"]([^'\"]+)['\"]", text)
    if not match:
        raise ValueError("Could not find -b or --cookie value in curl command")
    return match.group(1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 parse_curl_cookies.py curl_command.txt")
        sys.exit(1)
    
    curl_file = Path(sys.argv[1])
    if not curl_file.exists():
        print(f"File not found: {curl_file}")
        sys.exit(1)
    
    text = curl_file.read_text()
    cookie_string = extract_cookie_string_from_curl(text)
    cookies = parse_cookie_string(cookie_string)
    update_config_cookies(cookies)
    print(f"Extracted {len(cookies)} cookies and updated config.py")
