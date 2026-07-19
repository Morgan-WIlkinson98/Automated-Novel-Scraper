"""
main.py
Ties together: rss_watcher, link_resolver, generic_extractor,
site_overrides, storage, politeness
"""

from urllib.parse import urlparse
from rss_watcher import run_forever
from link_resolver import resolve_final_url
from generic_extractor import extract_chapter
from site_overrides import extract_with_override
from storage import init_storage, save_chapter
from politeness import polite_get

db = init_storage()

def handle_new_entry(entry):
    feed_link = entry.link
    final_url = resolve_final_url(feed_link)
    domain = urlparse(final_url).netloc

    result = extract_chapter(final_url)

    if not result.passed_quality_check:
        resp = polite_get(final_url)
        if resp is None:
            print(f"skipping {final_url}, blocked or unreachable")
            return
        override_text = extract_with_override(resp.text, domain)
        if override_text:
            result.text = override_text
            result.method = "site_override"
        else:
            print(f"no extraction succeeded for {final_url}, needs a new override entry")
            return

    save_chapter(
        db,
        url=final_url,
        series=getattr(entry, "title", "unknown"),
        chapter_label=getattr(entry, "summary", ""),
        title=result.title,
        text=result.text,
        method=result.method,
    )
    print(f"saved: {result.title} ({result.method})")

if __name__ == "__main__":
    run_forever(handle_new_entry)
