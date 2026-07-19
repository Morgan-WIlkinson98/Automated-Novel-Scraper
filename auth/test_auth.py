"""
Test script to verify NovelUpdates RSS authentication.
Run this to check if your credentials work.
"""

import feedparser
import requests
from core.config import (
    RSS_FEED_URL,
    NOVELUPDATES_USERNAME,
    NOVELUPDATES_PASSWORD,
    NOVELUPDATES_COOKIES,
)

def test_rss_authentication():
    """Test if RSS feed can be fetched with authentication."""
    print(f"Testing RSS feed: {RSS_FEED_URL}")
    print(f"Username configured: {bool(NOVELUPDATES_USERNAME)}")
    print(f"Password configured: {bool(NOVELUPDATES_PASSWORD)}")
    print(f"Cookies configured: {bool(NOVELUPDATES_COOKIES)}")
    print()
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; NovelScraper/1.0)'
        }
        
        cookies = NOVELUPDATES_COOKIES if NOVELUPDATES_COOKIES else None
        auth = None
        if NOVELUPDATES_USERNAME and NOVELUPDATES_PASSWORD:
            auth = (NOVELUPDATES_USERNAME, NOVELUPDATES_PASSWORD)
            print("Using username/password authentication")
        elif cookies:
            print("Using cookie authentication")
        else:
            print("No authentication configured (will try unauthenticated)")
        
        print(f"Fetching RSS feed...")
        response = requests.get(RSS_FEED_URL, headers=headers, auth=auth, cookies=cookies, timeout=30)
        response.raise_for_status()
        
        print(f"✓ Successfully fetched RSS feed (status: {response.status_code})")
        print(f"✓ Content length: {len(response.text)} characters")
        
        # Parse the feed
        feed = feedparser.parse(response.text)
        
        if feed.bozo:
            print(f"⚠ Feed parsing warning: {feed.bozo_exception}")
        
        print(f"✓ Feed title: {feed.feed.get('title', 'N/A')}")
        print(f"✓ Number of entries: {len(feed.entries)}")
        
        if feed.entries:
            print(f"\nFirst entry:")
            print(f"  Title: {feed.entries[0].get('title', 'N/A')}")
            print(f"  Link: {feed.entries[0].get('link', 'N/A')}")
        
        print("\n✓ Authentication successful! The scraper should work.")
        return True
        
    except requests.HTTPError as e:
        print(f"✗ HTTP error: {e}")
        print(f"  Status code: {e.response.status_code}")
        if e.response.status_code == 401:
            print("  This indicates authentication failed. Check your credentials.")
        elif e.response.status_code == 403:
            print("  This indicates access forbidden. Check your credentials or cookies.")
        return False
    except requests.RequestException as e:
        print(f"✗ Request error: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_rss_authentication()
    exit(0 if success else 1)
