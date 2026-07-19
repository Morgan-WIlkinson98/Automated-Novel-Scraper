"""
link_resolver.py
Depends on: requests
"""

import requests

def resolve_final_url(url: str, timeout: int = 15) -> str:
    """Follow redirects and return the final destination URL."""
    try:
        resp = requests.head(url, allow_redirects=True, timeout=timeout)
        return resp.url
    except requests.RequestException:
        # Some servers reject HEAD; fall back to a lightweight GET
        resp = requests.get(url, allow_redirects=True, timeout=timeout, stream=True)
        resp.close()
        return resp.url
