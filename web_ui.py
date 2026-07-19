"""
web_ui.py
Simple Flask web interface for the novel scraper.
Depends on: flask
    pip install flask
"""

import logging
import sqlite3
import json
import os
import signal
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_file
from export import get_statistics, get_series_list, export_all_to_epub, export_series_to_epub
from settings import get_settings, reload_settings
from exceptions import DatabaseError
from logging_config import setup_logging as setup_app_logging, get_log_path
from curl_parser import parse_curl_command

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'novel-scraper-secret-key-change-in-production'

def get_db_connection():
    """Get database connection with row factory."""
    settings = get_settings()
    conn = sqlite3.connect(settings.CHAPTERS_DB)
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/')
def index():
    """Dashboard with statistics and overview."""
    try:
        stats = get_statistics(get_settings().CHAPTERS_DB)
        return render_template('index.html', stats=stats)
    except DatabaseError as e:
        return render_template('error.html', error=str(e)), 500


@app.route('/series')
def series_list():
    """List all series."""
    try:
        series = get_series_list(get_settings().CHAPTERS_DB)
        return render_template('series.html', series=series)
    except DatabaseError as e:
        return render_template('error.html', error=str(e)), 500


@app.route('/series/<series_name>')
def series_detail(series_name):
    """View chapters for a specific series."""
    try:
        conn = get_db_connection()
        cursor = conn.execute("""
            SELECT url, chapter_label, title, text, extraction_method, fetched_at
            FROM chapters
            WHERE series = ?
            ORDER BY fetched_at
        """, (series_name,))
        chapters = [dict(row) for row in cursor]
        conn.close()
        
        return render_template('series_detail.html', series_name=series_name, chapters=chapters)
    except Exception as e:
        logger.error(f"Error viewing series {series_name}: {e}")
        return render_template('error.html', error=str(e)), 500


@app.route('/chapter/<path:url>')
def chapter_detail(url):
    """View a specific chapter."""
    try:
        conn = get_db_connection()
        cursor = conn.execute("""
            SELECT series, chapter_label, title, text, extraction_method, fetched_at
            FROM chapters
            WHERE url = ?
        """, (url,))
        chapter = cursor.fetchone()
        conn.close()
        
        if not chapter:
            return render_template('error.html', error="Chapter not found"), 404
        
        return render_template('chapter.html', chapter=dict(chapter))
    except Exception as e:
        logger.error(f"Error viewing chapter {url}: {e}")
        return render_template('error.html', error=str(e)), 500


@app.route('/api/statistics')
def api_statistics():
    """API endpoint for statistics."""
    try:
        stats = get_statistics(get_settings().CHAPTERS_DB)
        return jsonify(stats)
    except DatabaseError as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/series')
def api_series():
    """API endpoint for series list."""
    try:
        series = get_series_list(get_settings().CHAPTERS_DB)
        return jsonify(series)
    except DatabaseError as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/series/<series_name>/chapters')
def api_series_chapters(series_name):
    """API endpoint for chapters in a series."""
    try:
        conn = get_db_connection()
        cursor = conn.execute("""
            SELECT url, chapter_label, title, extraction_method, fetched_at
            FROM chapters
            WHERE series = ?
            ORDER BY fetched_at
        """, (series_name,))
        chapters = [dict(row) for row in cursor]
        conn.close()
        return jsonify(chapters)
    except Exception as e:
        logger.error(f"API error for series {series_name}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/export')
def export_page():
    """Export page."""
    try:
        series = get_series_list(get_settings().CHAPTERS_DB)
        return render_template('export.html', series=series)
    except DatabaseError as e:
        return render_template('error.html', error=str(e)), 500


@app.route('/export/all', methods=['POST'])
def export_all():
    """Export all series to EPUB."""
    try:
        files = export_all_to_epub(get_settings().CHAPTERS_DB, get_settings().EXPORT_DIR)
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        logger.error(f"Export all failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/export/series/<series_name>', methods=['POST'])
def export_series(series_name):
    """Export a specific series to EPUB."""
    try:
        file_path = export_series_to_epub(series_name, get_settings().CHAPTERS_DB, get_settings().EXPORT_DIR)
        if file_path:
            return jsonify({'success': True, 'file': file_path})
        else:
            return jsonify({'success': False, 'error': 'No chapters found for series'}), 404
    except Exception as e:
        logger.error(f"Export series {series_name} failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/download/<filename>')
def download_file(filename):
    """Download exported file."""
    try:
        file_path = Path(get_settings().EXPORT_DIR) / filename
        if file_path.exists():
            return send_file(str(file_path), as_attachment=True)
        else:
            return render_template('error.html', error="File not found"), 404
    except Exception as e:
        logger.error(f"Download error for {filename}: {e}")
        return render_template('error.html', error=str(e)), 500


@app.route('/settings')
def settings_page():
    """Settings page for configuration."""
    try:
        config = get_settings().to_dict()
        return render_template('settings.html', config=config)
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        return render_template('error.html', error=str(e)), 500


@app.route('/api/config', methods=['GET'])
def api_get_config():
    """API endpoint to get current configuration."""
    try:
        config = get_settings().to_dict(hide_secrets=True)
        return jsonify(config)
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/config', methods=['POST'])
def api_save_config():
    """API endpoint to save configuration."""
    try:
        config_data = request.json
        
        # If a curl command is provided, parse it and merge extracted values
        curl_command = config_data.pop('curl_command', '')
        if curl_command and isinstance(curl_command, str):
            logger.info("Parsing curl command from settings UI")
            parsed = parse_curl_command(curl_command)
            logger.info(f"Parsed from curl: {list(parsed.keys())}")
            # Merged parsed values overwrite form values (curl is authoritative)
            config_data.update(parsed)
        
        settings = get_settings()
        success = settings.save_to_file(config_data)
        if success:
            reload_settings()
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to save configuration'}), 500
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/test-auth', methods=['POST'])
def api_test_auth():
    """Test authentication with current configuration."""
    try:
        import feedparser
        import requests
        
        settings = get_settings()
        
        headers = {
            'User-Agent': settings.USER_AGENT
        }
        
        cookies = settings.NOVELUPDATES_COOKIES if isinstance(settings.NOVELUPDATES_COOKIES, dict) else None
        
        auth = None
        if settings.NOVELUPDATES_USERNAME and settings.NOVELUPDATES_PASSWORD:
            auth = (settings.NOVELUPDATES_USERNAME, settings.NOVELUPDATES_PASSWORD)
        
        response = requests.get(
            settings.RSS_FEED_URL,
            headers=headers,
            auth=auth,
            cookies=cookies,
            timeout=30
        )
        response.raise_for_status()
        
        feed = feedparser.parse(response.text)
        
        return jsonify({
            'success': True,
            'status_code': response.status_code,
            'feed_title': feed.feed.get('title', 'N/A'),
            'entry_count': len(feed.entries),
            'has_auth': bool(auth or cookies)
        })
    except requests.HTTPError as e:
        return jsonify({
            'success': False,
            'error': f'HTTP Error: {e}',
            'status_code': e.response.status_code
        }), 400
    except Exception as e:
        logger.error(f"Error testing auth: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def setup_app():
    """Ensure required directories exist."""
    Path("templates").mkdir(exist_ok=True)
    get_settings().EXPORT_DIR and Path(get_settings().EXPORT_DIR).mkdir(exist_ok=True)


@app.route('/api/stop', methods=['POST'])
def api_stop():
    """Stop the scraper and web UI processes."""
    try:
        pid_file = Path("pids.json")
        if not pid_file.exists():
            return jsonify({'success': False, 'error': 'PID file not found. Run python3 start.py to start the app.'}), 400
        
        with open(pid_file) as f:
            pids = json.load(f)
        
        # Stop child processes first (scraper, then web UI)
        for key in ['scraper', 'web_ui', 'start']:
            pid = pids.get(key)
            if pid and pid != os.getpid():
                try:
                    os.kill(pid, signal.SIGTERM)
                    logger.info(f"Sent SIGTERM to {key} (PID: {pid})")
                except ProcessLookupError:
                    logger.warning(f"Process {key} (PID: {pid}) already gone")
                except Exception as e:
                    logger.error(f"Failed to stop {key} (PID: {pid}): {e}")
        
        if pid_file.exists():
            pid_file.unlink()
        
        return jsonify({'success': True, 'message': 'Stop signal sent. The app will shut down shortly.'})
    except Exception as e:
        logger.error(f"Error stopping app: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/logs')
def logs_page():
    """Logs page."""
    return render_template('logs.html')


@app.route('/api/logs')
def api_logs():
    """API endpoint to get recent log lines."""
    try:
        log_path = get_log_path()
        limit = request.args.get('limit', 200, type=int)
        category = request.args.get('category', 'all')
        
        if not Path(log_path).exists():
            return jsonify({'lines': []})
        
        lines = []
        with open(log_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        
        # Category filtering based on logger name
        keywords = {
            'rss': ['rss_watcher'],
            'auth': ['auth', 'Authentication', 'NOVELUPDATES_USERNAME'],
            'extract': ['generic_extractor', 'site_overrides', 'link_resolver', 'politeness'],
            'download': ['storage', 'export', 'Saved chapter', 'Created EPUB'],
        }
        
        for line in all_lines:
            if category == 'all' or any(kw in line for kw in keywords.get(category, [])):
                lines.append(line.rstrip())
        
        # Return last N matching lines
        lines = lines[-limit:]
        
        return jsonify({'lines': lines})
    except Exception as e:
        logger.error(f"Error reading logs: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == "__main__":
    setup_app_logging()
    setup_app()
    app.run(host="0.0.0.0", port=6110, debug=True)

