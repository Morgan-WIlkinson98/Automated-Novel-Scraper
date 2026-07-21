"""
desktop_app.py
Standalone desktop wrapper for the Novel Scraper web UI.

Starts the Flask server in a background thread and opens it in a native
webview window, so the app looks like a desktop application while still
being accessible on localhost.

Usage:
    python desktop_app.py
    # or, after pip install -e .:
    novel-scraper-gui
"""

import logging
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

import webview

# Use a per-user data directory so the packaged app has a writable location
# for databases, logs, and exports on any machine.
APP_DIR = Path.home() / ".novelscraper"
APP_DIR.mkdir(parents=True, exist_ok=True)

# Point all app data to the writable directory before any other imports.
os.environ.setdefault("CHAPTERS_DB", str(APP_DIR / "chapters.db"))
os.environ.setdefault("SEEN_ENTRIES_DB", str(APP_DIR / "seen_entries.db"))
os.environ.setdefault("EXPORT_DIR", str(APP_DIR / "exports"))
os.environ.setdefault("READING_LISTS_DIR", str(APP_DIR / "reading_lists"))

# Set up logging to a file first so startup failures can be diagnosed.
from core.logging_config import setup_logging, get_log_path  # noqa: E402
setup_logging()
logger = logging.getLogger(__name__)

import main as scraper_module  # noqa: E402
from web_ui import app, setup_app  # noqa: E402

PORT = 6110
HOST = "127.0.0.1"


def start_scraper():
    """Start the RSS scraper in the background."""
    try:
        scraper_module.main()
    except Exception:
        logger.exception("Scraper process crashed")


def run_server():
    """Start the Flask server in the background."""
    setup_app()
    logger.info(f"Starting Flask server on http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False, threaded=True)


def wait_for_server(url, timeout=20):
    """Wait until the Flask server responds before opening the UI."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def main():
    """Launch the scraper, start the Flask server, and open the UI."""
    scraper = threading.Thread(target=start_scraper, daemon=True)
    scraper.start()

    server = threading.Thread(target=run_server, daemon=True)
    server.start()

    url = f"http://{HOST}:{PORT}"
    if not wait_for_server(url, timeout=20):
        logger.error(f"Flask server did not start in time; check {url}")
        log_path = get_log_path()
        error_html = (
            f"<h1>Could not start Novel Scraper</h1>"
            f"<p>The Flask server failed to start.</p>"
            f"<p>Check the log file for details: <code>{log_path}</code></p>"
        )
        webview.create_window(
            "Novel Scraper - Error",
            html=error_html,
            width=800,
            height=600,
        )
        webview.start()
        return

    logger.info("Flask server is ready; opening webview")
    webview.create_window(
        "Novel Scraper",
        url,
        width=1400,
        height=900,
        min_size=(800, 600),
    )
    webview.start()


if __name__ == "__main__":
    main()
