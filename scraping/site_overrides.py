"""
site_overrides.py
Depends on: beautifulsoup4, lxml
    pip install beautifulsoup4 lxml
"""

from bs4 import BeautifulSoup

SITE_OVERRIDES = {
    # "example-translations.com": {
    #     "content_selector": "div.entry-content",
    #     "remove_selectors": [".sharedaddy", ".ads", ".jp-relatedposts"],
    # },
}

def extract_with_override(html: str, domain: str) -> str | None:
    config = SITE_OVERRIDES.get(domain)
    if not config:
        return None

    soup = BeautifulSoup(html, "lxml")
    container = soup.select_one(config["content_selector"])
    if not container:
        return None

    for sel in config.get("remove_selectors", []):
        for el in container.select(sel):
            el.decompose()

    return container.get_text(separator="\n\n", strip=True)
