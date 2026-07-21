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
import threading
import time
import urllib.request
import webview

import main as scraper_module
from web_ui import app, setup_app, setup_app_logging

logger = logging.getLogger(__name__)

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
    setup_app_logging()
    setup_app()
    logger.info(f"Starting Flask server on http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False, threaded=True)


def wait_for_server(url, timeout=15):
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
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    scraper = threading.Thread(target=start_scraper, daemon=True)
    scraper.start()

    server = threading.Thread(target=run_server, daemon=True)
    server.start()

    url = f"http://{HOST}:{PORT}"
    if not wait_for_server(url, timeout=15):
        logger.error(f"Flask server did not start in time; check {url}")
        return

    logger.info("Flask server is ready; opening webview")
    webview.create_window("Novel Scraper", url, width=1400, height=900, min_size=(800, 600))
    webview.start()


if __name__ == "__main__":
    main()
