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
import subprocess
import sys
import time
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_file
from export import get_statistics, get_series_list, export_all_to_epub, export_series_to_epub, export_selected_chapters_to_epub
from storage import get_series_info, save_series_info
from series_scraper import scrape_series_page, filter_chapters
from settings import get_settings, reload_settings
from exceptions import DatabaseError
from logging_config import setup_logging as setup_app_logging, get_log_path
from curl_parser import parse_curl_command
from main import handle_new_entry
from rss_watcher import init_db as init_seen_db, poll_once

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


@app.route('/rss')
def rss_feeds_page():
    """List stored raw RSS feed snapshots."""
    try:
        feed_dir = Path(get_settings().EXPORT_DIR).parent / "rss_feeds"
        feed_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(feed_dir.glob('feed_*.xml'), key=lambda p: p.stat().st_mtime, reverse=True)
        latest = feed_dir / "latest.xml"
        return render_template('rss.html', files=[f.name for f in files], latest=latest.name if latest.exists() else None)
    except Exception as e:
        logger.error(f"Error listing RSS feeds: {e}")
        return render_template('error.html', error=str(e)), 500


@app.route('/rss/raw/<filename>')
def rss_raw(filename):
    """Return the raw XML for a stored RSS snapshot."""
    try:
        feed_dir = Path(get_settings().EXPORT_DIR).parent / "rss_feeds"
        file_path = feed_dir / filename
        if not file_path.resolve().is_relative_to(feed_dir.resolve()):
            return render_template('error.html', error="Invalid path"), 403
        if not file_path.exists():
            return render_template('error.html', error="Feed not found"), 404
        return send_file(file_path, mimetype='application/xml')
    except Exception as e:
        logger.error(f"Error serving RSS feed {filename}: {e}")
        return render_template('error.html', error=str(e)), 500


@app.route('/rss/view/<filename>')
def rss_view(filename):
    """Display a stored RSS feed snapshot safely in the browser."""
    try:
        feed_dir = Path(get_settings().EXPORT_DIR).parent / "rss_feeds"
        file_path = feed_dir / filename
        if not file_path.resolve().is_relative_to(feed_dir.resolve()):
            return render_template('error.html', error="Invalid path"), 403
        if not file_path.exists():
            return render_template('error.html', error="Feed not found"), 404
        content = file_path.read_text(encoding='utf-8')
        return render_template('rss_view.html', filename=filename, content=content)
    except Exception as e:
        logger.error(f"Error viewing RSS feed {filename}: {e}")
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
    """View chapters and details for a specific series."""
    try:
        conn = get_db_connection()
        cursor = conn.execute("""
            SELECT url, chapter_label, title, text, extraction_method, fetched_at
            FROM chapters
            WHERE series = ?
            ORDER BY fetched_at
        """, (series_name,))
        chapters = [dict(row) for row in cursor]
        
        # Aggregate stats for the series info section
        total_words = sum(len(str(c['text'] or '').split()) for c in chapters)
        method_counts = {}
        for c in chapters:
            method_counts[c['extraction_method']] = method_counts.get(c['extraction_method'], 0) + 1
        
        series_info = get_series_info(conn, series_name)
        
        available_chapters = []
        if series_info.get('available_chapters'):
            try:
                available_chapters = json.loads(series_info['available_chapters'])
            except json.JSONDecodeError:
                pass
        
        # Map extnu URLs to the final downloaded chapter URLs for on-demand viewing
        cursor = conn.execute(
            "SELECT chapter_label, url FROM chapters WHERE series = ? AND chapter_label LIKE 'https://www.novelupdates.com/extnu/%'",
            (series_name,)
        )
        downloaded_urls = {row['chapter_label']: row['url'] for row in cursor}
        conn.close()
        
        return render_template(
            'series_detail.html',
            series_name=series_name,
            chapters=chapters,
            total_words=total_words,
            method_counts=method_counts,
            series_info=series_info,
            available_chapters=available_chapters,
            downloaded_urls=downloaded_urls,
        )
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


def _relative_export_path(file_path: str) -> str:
    """Convert an absolute export path to a path relative to EXPORT_DIR."""
    try:
        return str(Path(file_path).relative_to(Path(get_settings().EXPORT_DIR)))
    except ValueError:
        return str(Path(file_path).name)


@app.route('/export/all', methods=['POST'])
def export_all():
    """Export all series to EPUB."""
    try:
        files = export_all_to_epub(get_settings().CHAPTERS_DB, get_settings().EXPORT_DIR)
        return jsonify({'success': True, 'files': [_relative_export_path(f) for f in files]})
    except Exception as e:
        logger.error(f"Export all failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/export/series/<series_name>', methods=['POST'])
def export_series(series_name):
    """Export a specific series to EPUB."""
    try:
        file_path = export_series_to_epub(series_name, get_settings().CHAPTERS_DB, get_settings().EXPORT_DIR)
        if file_path:
            return jsonify({'success': True, 'file': _relative_export_path(file_path)})
        else:
            return jsonify({'success': False, 'error': 'No chapters found for series'}), 404
    except Exception as e:
        logger.error(f"Export series {series_name} failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/export/series/<series_name>/chapters', methods=['POST'])
def export_series_chapters(series_name):
    """Export selected chapters from a series to EPUB."""
    try:
        data = request.json or {}
        chapter_urls = data.get('chapter_urls', [])
        
        if chapter_urls:
            file_path = export_selected_chapters_to_epub(
                series_name,
                chapter_urls,
                get_settings().CHAPTERS_DB,
                get_settings().EXPORT_DIR
            )
        else:
            file_path = export_series_to_epub(
                series_name,
                get_settings().CHAPTERS_DB,
                get_settings().EXPORT_DIR
            )
        
        if file_path:
            return jsonify({'success': True, 'file': _relative_export_path(file_path)})
        else:
            return jsonify({'success': False, 'error': 'No chapters found for series'}), 404
    except Exception as e:
        logger.error(f"Export series chapters failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/series/<series_name>/url', methods=['POST'])
def set_series_url(series_name):
    """Manually set or update the NovelUpdates series URL."""
    try:
        data = request.json or {}
        series_url = data.get('url', '').strip()
        if not series_url:
            return jsonify({'success': False, 'error': 'URL is required'}), 400
        
        conn = get_db_connection()
        existing = get_series_info(conn, series_name)
        save_series_info(
            conn,
            series_name,
            url=series_url,
            synopsis=existing.get('synopsis'),
            available_chapters=existing.get('available_chapters')
        )
        conn.close()
        
        return jsonify({'success': True, 'url': series_url})
    except Exception as e:
        logger.error(f"Set series URL {series_name} failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/series/<series_name>/sync', methods=['POST'])
def sync_series(series_name):
    """Scrape the NovelUpdates series page for synopsis and chapter list."""
    try:
        data = request.json or {}
        provided_url = data.get('url', '').strip()
        
        conn = get_db_connection()
        series_info = get_series_info(conn, series_name)
        conn.close()
        
        series_url = provided_url or series_info.get('url')
        if not series_url:
            return jsonify({'success': False, 'error': 'No series URL stored. Wait for an RSS entry or set the URL manually.'}), 400
        
        scraped = scrape_series_page(series_url)
        
        conn = get_db_connection()
        save_series_info(
            conn,
            series_name,
            url=series_url,
            synopsis=scraped['synopsis'],
            available_chapters=json.dumps(scraped['chapters'])
        )
        conn.close()
        
        return jsonify({
            'success': True,
            'chapters': len(scraped['chapters']),
            'synopsis': scraped['synopsis'][:500] if scraped['synopsis'] else ''
        })
    except Exception as e:
        logger.error(f"Sync series {series_name} failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/series/<series_name>/download', methods=['POST'])
def download_series_chapters(series_name):
    """Download selected chapters or a chapter range from the NovelUpdates series page."""
    try:
        data = request.json or {}
        urls = data.get('urls')  # list of specific extnu URLs
        start = data.get('start')
        end = data.get('end')
        
        selected = []
        if urls:
            selected = [{'extnu_url': url} for url in urls if isinstance(url, str)]
        elif start is not None or end is not None:
            conn = get_db_connection()
            series_info = get_series_info(conn, series_name)
            conn.close()
            
            if not series_info.get('available_chapters'):
                return jsonify({'success': False, 'error': 'Series not synced. Run Sync Series first.'}), 400
            
            chapters = json.loads(series_info['available_chapters'])
            selected = filter_chapters(chapters, start, end)
        
        if not selected:
            return jsonify({'success': False, 'error': 'No chapters selected.'}), 404
        
        # Process in background so the request returns quickly
        import threading
        def _download():
            _process_chapter_downloads(series_name, selected)
        
        thread = threading.Thread(target=_download, daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': f'Started downloading {len(selected)} chapter(s). Check logs for progress.'
        })
    except Exception as e:
        logger.error(f"Download series {series_name} failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _process_chapter_downloads(series_name: str, chapters: list):
    """Resolve and extract a list of chapters in the background."""
    import sqlite3
    from link_resolver import resolve_final_url_with_browser_fallback as resolve_final_url
    from generic_extractor import extract_chapter
    from site_overrides import extract_with_override
    from politeness import polite_get
    from storage import init_storage, save_chapter
    from settings import get_settings
    from exceptions import HTTPError, ValidationError
    
    settings = get_settings()
    db = init_storage(settings.CHAPTERS_DB)
    
    for ch in chapters:
        extnu_url = ch.get('extnu_url')
        if not extnu_url:
            continue
        try:
            final_url = resolve_final_url(extnu_url)
            result = extract_chapter(final_url)
            
            if not result.passed_quality_check:
                resp = polite_get(final_url)
                if resp:
                    override_text = extract_with_override(resp.text, urlparse(final_url).netloc)
                    if override_text:
                        result.text = override_text
                        result.method = 'site_override'
                        result.passed_quality_check = True
                if not result.passed_quality_check:
                    logger.warning(f"Skipping chapter {ch.get('number')} from {extnu_url}: extraction failed")
                    continue
            
            save_chapter(
                db,
                url=final_url,
                series=series_name,
                chapter_label=extnu_url,
                title=result.title or f"Chapter {ch.get('number')}",
                text=result.text,
                method=result.method,
            )
            logger.info(f"Downloaded chapter {ch.get('number')} for {series_name}")
        except Exception as e:
            logger.error(f"Failed to download chapter {ch.get('number')} for {series_name}: {e}")
            continue
    
    db.close()


@app.route('/download/<path:filename>')
def download_file(filename):
    """Download exported file (supports subfolder paths)."""
    try:
        export_dir = Path(get_settings().EXPORT_DIR).resolve()
        file_path = export_dir / filename
        # Prevent directory traversal outside export_dir
        if export_dir not in file_path.resolve().parents and file_path.resolve() != export_dir:
            return render_template('error.html', error="Invalid path"), 403
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
    """Ensure required directories and database tables exist."""
    Path("templates").mkdir(exist_ok=True)
    get_settings().EXPORT_DIR and Path(get_settings().EXPORT_DIR).mkdir(exist_ok=True)
    from storage import init_storage
    init_storage(get_settings().CHAPTERS_DB)


SCRAPER_PID_FILE = Path("scraper_pid.json")


def _scraper_is_running() -> bool:
    """Check if the scraper process is still running."""
    if not SCRAPER_PID_FILE.exists():
        return False
    try:
        pid = json.loads(SCRAPER_PID_FILE.read_text()).get('pid')
        if pid is None:
            return False
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, ProcessLookupError):
        return False


@app.route('/api/fetch_rss', methods=['POST'])
def api_fetch_rss():
    """Manually trigger one RSS poll in the background."""
    try:
        import threading
        
        def _fetch():
            conn = init_seen_db(get_settings().SEEN_ENTRIES_DB)
            try:
                poll_once(conn, handle_new_entry)
            finally:
                conn.close()
        
        thread = threading.Thread(target=_fetch, daemon=True)
        thread.start()
        return jsonify({'success': True, 'message': 'RSS fetch started. Check logs for progress.'})
    except Exception as e:
        logger.error(f"Fetch RSS failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scraper_status')
def api_scraper_status():
    """Check whether the scraper is currently running."""
    try:
        running = _scraper_is_running()
        return jsonify({'running': running})
    except Exception as e:
        logger.error(f"Error checking scraper status: {e}")
        return jsonify({'running': False, 'error': str(e)})


@app.route('/api/start_scraper', methods=['POST'])
def api_start_scraper():
    """Start the scraper (main.py) as a subprocess."""
    try:
        if _scraper_is_running():
            return jsonify({'success': False, 'error': 'Scraper is already running'}), 409
        
        python = sys.executable
        process = subprocess.Popen(
            [python, 'main.py'],
            cwd=Path(__file__).parent,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        SCRAPER_PID_FILE.write_text(json.dumps({'pid': process.pid}))
        logger.info(f"Started scraper (PID: {process.pid})")
        return jsonify({'success': True, 'pid': process.pid})
    except Exception as e:
        logger.error(f"Error starting scraper: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stop_scraper', methods=['POST'])
def api_stop_scraper():
    """Stop the running scraper (main.py)."""
    try:
        if not SCRAPER_PID_FILE.exists():
            return jsonify({'success': False, 'error': 'No scraper PID file found'}), 400
        
        pid = json.loads(SCRAPER_PID_FILE.read_text()).get('pid')
        if not pid:
            return jsonify({'success': False, 'error': 'Invalid PID file'}), 400
        
        try:
            os.kill(pid, signal.SIGTERM)
            logger.info(f"Sent SIGTERM to scraper (PID: {pid})")
            time.sleep(1)
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
                logger.info(f"Sent SIGKILL to scraper (PID: {pid})")
            except ProcessLookupError:
                pass
        except ProcessLookupError:
            logger.warning(f"Scraper process (PID: {pid}) already gone")
        
        if SCRAPER_PID_FILE.exists():
            SCRAPER_PID_FILE.unlink()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error stopping scraper: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stop', methods=['POST'])
def api_stop():
    """Stop the scraper and web UI processes (legacy/global stop)."""
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

