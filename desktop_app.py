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
import webview

from web_ui import app, setup_app, setup_app_logging

logger = logging.getLogger(__name__)

PORT = 6110
HOST = "127.0.0.1"


def run_server():
    """Start the Flask server in the background."""
    setup_app_logging()
    setup_app()
    logger.info(f"Starting Flask server on http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False, threaded=True)


def main():
    """Launch the Flask server and open it in a desktop webview window."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    server = threading.Thread(target=run_server, daemon=True)
    server.start()

    # Wait briefly for the server to start accepting connections
    time.sleep(1.5)

    window_title = "Novel Scraper"
    url = f"http://{HOST}:{PORT}"

    webview.create_window(window_title, url, width=1400, height=900, min_size=(800, 600))
    webview.start()


if __name__ == "__main__":
    main()
