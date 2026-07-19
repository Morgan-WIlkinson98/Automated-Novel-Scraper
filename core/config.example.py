"""
Configuration file for the novel scraper.
Copy this file to config.py and fill in your credentials.
"""

# NovelUpdates RSS Feed Configuration
RSS_FEED_URL = "https://www.novelupdates.com/rss/"

# NovelUpdates Authentication (if required)
# Set these to your NovelUpdates credentials if the RSS feed requires login
NOVELUPDATES_USERNAME = None  # Set to your username
NOVELUPDATES_PASSWORD = None  # Set to your password

# Alternatively, if NovelUpdates uses session cookies, you can provide them:
# NOVELUPDATES_COOKIES = {
#     "session_id": "your_session_cookie",
#     "other_cookie": "value"
# }
NOVELUPDATES_COOKIES = None

# Polling Configuration
POLL_INTERVAL_SECONDS = 15 * 60  # 15 minutes

# Politeness Configuration
MIN_DELAY_SECONDS = 5  # Minimum delay between requests to same domain
USER_AGENT = "Mozilla/5.0 (compatible; ChapterFetcher/1.0; +https://example.invalid/bot-info)"

# Quality Thresholds
MIN_CHARS = 500  # Minimum character count for quality check
MIN_PARAGRAPHS = 3  # Minimum paragraph count for quality check

# Database Paths
SEEN_ENTRIES_DB = "seen_entries.db"
CHAPTERS_DB = "chapters.db"

# Export Configuration
EXPORT_DIR = "exports"
