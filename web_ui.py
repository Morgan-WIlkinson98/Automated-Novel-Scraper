"""
web_ui.py
Simple Flask web interface for the novel scraper.
Depends on: flask
    pip install flask
"""

import sqlite3
import logging
import os
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_file, redirect, url_for
from export import get_statistics, get_series_list, export_all_to_epub, export_series_to_epub
from exceptions import DatabaseError

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'novel-scraper-secret-key-change-in-production'

# Database path
DB_PATH = "chapters.db"
CONFIG_PATH = "config.py"


def get_db_connection():
    """Get database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_config():
    """Load configuration from config.py file."""
    config = {
        'RSS_FEED_URL': 'https://www.novelupdates.com/rss/',
        'NOVELUPDATES_USERNAME': '',
        'NOVELUPDATES_PASSWORD': '',
        'NOVELUPDATES_COOKIES': '',
        'POLL_INTERVAL_SECONDS': 900,
        'MIN_DELAY_SECONDS': 5,
        'MIN_CHARS': 500,
        'MIN_PARAGRAPHS': 3,
    }
    
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                config_content = f.read()
                # Parse the config file
                for key in config.keys():
                    if f'{key} = ' in config_content:
                        # Extract value
                        lines = config_content.split('\n')
                        for line in lines:
                            if line.strip().startswith(f'{key} = '):
                                value = line.split('=', 1)[1].strip()
                                # Remove quotes if present
                                if value.startswith('"') and value.endswith('"'):
                                    value = value[1:-1]
                                elif value.startswith("'") and value.endswith("'"):
                                    value = value[1:-1]
                                # Handle None
                                if value == 'None':
                                    value = ''
                                # Handle numbers
                                elif key in ['POLL_INTERVAL_SECONDS', 'MIN_DELAY_SECONDS', 'MIN_CHARS', 'MIN_PARAGRAPHS']:
                                    try:
                                        value = int(value)
                                    except ValueError:
                                        pass
                                config[key] = value
                                break
        except Exception as e:
            logger.error(f"Error loading config: {e}")
    
    return config


def save_config(config_data):
    """Save configuration to config.py file."""
    try:
        config_content = f'''"""
Configuration file for the novel scraper.
Contains credentials and settings.
"""

# NovelUpdates RSS Feed Configuration
RSS_FEED_URL = "{config_data.get('RSS_FEED_URL', 'https://www.novelupdates.com/rss/')}"

# NovelUpdates Authentication (if required)
NOVELUPDATES_USERNAME = {repr(config_data.get('NOVELUPDATES_USERNAME', ''))}
NOVELUPDATES_PASSWORD = {repr(config_data.get('NOVELUPDATES_PASSWORD', ''))}

# Cookie authentication (if you have session cookies)
NOVELUPDATES_COOKIES = {repr(config_data.get('NOVELUPDATES_COOKIES', ''))}

# Polling Configuration
POLL_INTERVAL_SECONDS = {config_data.get('POLL_INTERVAL_SECONDS', 900)}

# Politeness Configuration
MIN_DELAY_SECONDS = {config_data.get('MIN_DELAY_SECONDS', 5)}
USER_AGENT = "Mozilla/5.0 (compatible; ChapterFetcher/1.0; +https://example.invalid/bot-info)"

# Quality Thresholds
MIN_CHARS = {config_data.get('MIN_CHARS', 500)}
MIN_PARAGRAPHS = {config_data.get('MIN_PARAGRAPHS', 3)}

# Database Paths
SEEN_ENTRIES_DB = "seen_entries.db"
CHAPTERS_DB = "chapters.db"

# Export Configuration
EXPORT_DIR = "exports"
'''
        
        with open(CONFIG_PATH, 'w') as f:
            f.write(config_content)
        
        logger.info("Configuration saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return False


@app.route('/')
def index():
    """Dashboard with statistics and overview."""
    try:
        stats = get_statistics(DB_PATH)
        return render_template('index.html', stats=stats)
    except DatabaseError as e:
        return render_template('error.html', error=str(e)), 500


@app.route('/series')
def series_list():
    """List all series."""
    try:
        series = get_series_list(DB_PATH)
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
        stats = get_statistics(DB_PATH)
        return jsonify(stats)
    except DatabaseError as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/series')
def api_series():
    """API endpoint for series list."""
    try:
        series = get_series_list(DB_PATH)
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
        series = get_series_list(DB_PATH)
        return render_template('export.html', series=series)
    except DatabaseError as e:
        return render_template('error.html', error=str(e)), 500


@app.route('/export/all', methods=['POST'])
def export_all():
    """Export all series to EPUB."""
    try:
        files = export_all_to_epub(DB_PATH, "exports")
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        logger.error(f"Export all failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/export/series/<series_name>', methods=['POST'])
def export_series(series_name):
    """Export a specific series to EPUB."""
    try:
        file_path = export_series_to_epub(series_name, DB_PATH, "exports")
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
        file_path = Path("exports") / filename
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
        config = load_config()
        return render_template('settings.html', config=config)
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        return render_template('error.html', error=str(e)), 500


@app.route('/api/config', methods=['GET'])
def api_get_config():
    """API endpoint to get current configuration."""
    try:
        config = load_config()
        # Don't send password to frontend
        safe_config = config.copy()
        safe_config['NOVELUPDATES_PASSWORD'] = '******' if config.get('NOVELUPDATES_PASSWORD') else ''
        return jsonify(safe_config)
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/config', methods=['POST'])
def api_save_config():
    """API endpoint to save configuration."""
    try:
        config_data = request.json
        success = save_config(config_data)
        if success:
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
        
        config = load_config()
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; NovelScraper/1.0)'
        }
        
        cookies = None
        if config.get('NOVELUPDATES_COOKIES'):
            try:
                import ast
                cookies = ast.literal_eval(config['NOVELUPDATES_COOKIES'])
            except:
                pass
        
        auth = None
        if config.get('NOVELUPDATES_USERNAME') and config.get('NOVELUPDATES_PASSWORD'):
            auth = (config['NOVELUPDATES_USERNAME'], config['NOVELUPDATES_PASSWORD'])
        
        response = requests.get(
            config.get('RSS_FEED_URL', 'https://www.novelupdates.com/rss/'),
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


def create_templates():
    """Create HTML templates for the web UI."""
    templates_dir = Path("templates")
    templates_dir.mkdir(exist_ok=True)
    
    # Base template
    base_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Novel Scraper{% endblock %}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { background: #2c3e50; color: white; padding: 20px 0; margin-bottom: 30px; }
        .header h1 { margin: 0; }
        .nav { background: #34495e; padding: 10px 0; }
        .nav a { color: white; text-decoration: none; margin-right: 20px; padding: 5px 10px; }
        .nav a:hover { background: #455a64; }
        .nav a.active { background: #1abc9c; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; }
        .stat-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; }
        .stat-card h3 { font-size: 2em; margin-bottom: 5px; }
        .stat-card p { opacity: 0.9; }
        .btn { background: #3498db; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; text-decoration: none; }
        .btn:hover { background: #2980b9; }
        .btn-success { background: #27ae60; }
        .btn-success:hover { background: #219150; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #f8f9fa; }
        tr:hover { background: #f5f5f5; }
        .chapter-text { line-height: 1.8; max-width: 800px; margin: 0 auto; padding: 20px; }
        .alert { padding: 15px; border-radius: 4px; margin-bottom: 20px; }
        .alert-error { background: #e74c3c; color: white; }
        .alert-success { background: #27ae60; color: white; }
    </style>
</head>
<body>
    <div class="header">
        <div class="container">
            <h1>📚 Novel Scraper</h1>
        </div>
    </div>
    <div class="nav">
        <div class="container">
            <a href="/" class="{% if request.endpoint == 'index' %}active{% endif %}">Dashboard</a>
            <a href="/series" class="{% if request.endpoint == 'series_list' %}active{% endif %}">Series</a>
            <a href="/export" class="{% if request.endpoint == 'export_page' %}active{% endif %}">Export</a>
            <a href="/settings" class="{% if request.endpoint == 'settings_page' %}active{% endif %}">Settings</a>
        </div>
    </div>
    <div class="container">
        {% block content %}{% endblock %}
    </div>
</body>
</html>
    """
    
    (templates_dir / "base.html").write_text(base_template)
    
    # Index template
    index_template = """
{% extends "base.html" %}
{% block title %}Dashboard - Novel Scraper{% endblock %}
{% block content %}
    <div class="card">
        <h2>📊 Statistics</h2>
        <div class="stats-grid" style="margin-top: 20px;">
            <div class="stat-card">
                <h3>{{ stats.total_chapters }}</h3>
                <p>Total Chapters</p>
            </div>
            <div class="stat-card">
                <h3>{{ stats.total_series }}</h3>
                <p>Total Series</p>
            </div>
        </div>
    </div>
    
    <div class="card">
        <h2>📈 Extraction Methods</h2>
        <table style="margin-top: 20px;">
            <tr>
                <th>Method</th>
                <th>Count</th>
            </tr>
            {% for method, count in stats.by_method.items() %}
            <tr>
                <td>{{ method }}</td>
                <td>{{ count }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>
    
    <div class="card">
        <h2>🏆 Top Series</h2>
        <table style="margin-top: 20px;">
            <tr>
                <th>Series</th>
                <th>Chapters</th>
            </tr>
            {% for series, count in stats.by_series.items() %}
            <tr>
                <td><a href="/series/{{ series }}">{{ series }}</a></td>
                <td>{{ count }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>
{% endblock %}
    """
    
    (templates_dir / "index.html").write_text(index_template)
    
    # Series list template
    series_template = """
{% extends "base.html" %}
{% block title %}Series - Novel Scraper{% endblock %}
{% block content %}
    <div class="card">
        <h2>📚 All Series ({{ series|length }})</h2>
        <table style="margin-top: 20px;">
            <tr>
                <th>Series Name</th>
                <th>Action</th>
            </tr>
            {% for s in series %}
            <tr>
                <td><a href="/series/{{ s }}">{{ s }}</a></td>
                <td>
                    <a href="/series/{{ s }}" class="btn">View Chapters</a>
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
{% endblock %}
    """
    
    (templates_dir / "series.html").write_text(series_template)
    
    # Series detail template
    series_detail_template = """
{% extends "base.html" %}
{% block title %}{{ series_name }} - Novel Scraper{% endblock %}
{% block content %}
    <div class="card">
        <h2>📖 {{ series_name }}</h2>
        <p>{{ chapters|length }} chapters</p>
    </div>
    
    <div class="card">
        <h3>Chapters</h3>
        <table style="margin-top: 20px;">
            <tr>
                <th>Chapter</th>
                <th>Title</th>
                <th>Method</th>
                <th>Date</th>
                <th>Action</th>
            </tr>
            {% for chapter in chapters %}
            <tr>
                <td>{{ chapter.chapter_label }}</td>
                <td>{{ chapter.title }}</td>
                <td>{{ chapter.extraction_method }}</td>
                <td>{{ chapter.fetched_at|round|int }}</td>
                <td>
                    <a href="/chapter/{{ chapter.url }}" class="btn">Read</a>
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
{% endblock %}
    """
    
    (templates_dir / "series_detail.html").write_text(series_detail_template)
    
    # Chapter template
    chapter_template = """
{% extends "base.html" %}
{% block title %}{{ chapter.title }} - Novel Scraper{% endblock %}
{% block content %}
    <div class="card">
        <p><a href="/series/{{ chapter.series }}">← Back to {{ chapter.series }}</a></p>
        <h1>{{ chapter.title }}</h1>
        <p><strong>{{ chapter.chapter_label }}</strong></p>
        <p><small>Extracted via: {{ chapter.extraction_method }}</small></p>
    </div>
    
    <div class="card">
        <div class="chapter-text">
            {{ chapter.text|replace('\n\n', '<br><br>')|safe }}
        </div>
    </div>
{% endblock %}
    """
    
    (templates_dir / "chapter.html").write_text(chapter_template)
    
    # Export template
    export_template = """
{% extends "base.html" %}
{% block title %}Export - Novel Scraper{% endblock %}
{% block content %}
    <div class="card">
        <h2>📦 Export to EPUB</h2>
        <p>Export your chapters to EPUB format for reading on e-readers.</p>
    </div>
    
    <div class="card">
        <h3>Export All Series</h3>
        <p>Export all series to individual EPUB files.</p>
        <button onclick="exportAll()" class="btn btn-success">Export All</button>
    </div>
    
    <div class="card">
        <h3>Export Specific Series</h3>
        <table style="margin-top: 20px;">
            <tr>
                <th>Series</th>
                <th>Action</th>
            </tr>
            {% for s in series %}
            <tr>
                <td>{{ s }}</td>
                <td>
                    <button onclick="exportSeries('{{ s }}')" class="btn">Export</button>
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
    
    <div id="status"></div>
    
    <script>
        function exportAll() {
            fetch('/export/all', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('status').innerHTML = 
                            '<div class="alert alert-success">Exported ' + data.files.length + ' files!</div>';
                    } else {
                        document.getElementById('status').innerHTML = 
                            '<div class="alert alert-error">Error: ' + data.error + '</div>';
                    }
                });
        }
        
        function exportSeries(name) {
            fetch('/export/series/' + encodeURIComponent(name), { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('status').innerHTML = 
                            '<div class="alert alert-success">Exported: ' + name + '</div>';
                    } else {
                        document.getElementById('status').innerHTML = 
                            '<div class="alert alert-error">Error: ' + data.error + '</div>';
                    }
                });
        }
    </script>
{% endblock %}
    """
    
    (templates_dir / "export.html").write_text(export_template)
    
    # Settings template
    settings_template = """
{% extends "base.html" %}
{% block title %}Settings - Novel Scraper{% endblock %}
{% block content %}
    <div class="card">
        <h2>⚙️ Settings</h2>
        <p>Configure authentication, polling, and quality thresholds.</p>
    </div>
    
    <div class="card">
        <h3>🔐 Authentication</h3>
        <form id="authForm" style="margin-top: 20px;">
            <div style="margin-bottom: 15px;">
                <label for="rss_url"><strong>RSS Feed URL:</strong></label><br>
                <input type="text" id="rss_url" name="rss_url" value="{{ config.RSS_FEED_URL }}" style="width: 100%; padding: 8px; margin-top: 5px;" placeholder="https://www.novelupdates.com/rss/">
            </div>
            <div style="margin-bottom: 15px;">
                <label for="username"><strong>NovelUpdates Username:</strong></label><br>
                <input type="text" id="username" name="username" value="{{ config.NOVELUPDATES_USERNAME }}" style="width: 100%; padding: 8px; margin-top: 5px;" placeholder="your_username">
            </div>
            <div style="margin-bottom: 15px;">
                <label for="password"><strong>NovelUpdates Password:</strong></label><br>
                <input type="password" id="password" name="password" value="{{ config.NOVELUPDATES_PASSWORD }}" style="width: 100%; padding: 8px; margin-top: 5px;" placeholder="••••••••">
            </div>
            <div style="margin-bottom: 15px;">
                <label for="cookies"><strong>Session Cookies (optional):</strong></label><br>
                <textarea id="cookies" name="cookies" style="width: 100%; padding: 8px; margin-top: 5px;" rows="3" placeholder='{"session_id": "your_cookie"}'></textarea>
            </div>
        </form>
    </div>
    
    <div class="card">
        <h3>⏱️ Polling & Delays</h3>
        <form id="settingsForm" style="margin-top: 20px;">
            <div style="margin-bottom: 15px;">
                <label for="poll_interval"><strong>Poll Interval (seconds):</strong></label><br>
                <input type="number" id="poll_interval" name="poll_interval" value="{{ config.POLL_INTERVAL_SECONDS }}" style="width: 100%; padding: 8px; margin-top: 5px;">
            </div>
            <div style="margin-bottom: 15px;">
                <label for="min_delay"><strong>Minimum Request Delay (seconds):</strong></label><br>
                <input type="number" id="min_delay" name="min_delay" value="{{ config.MIN_DELAY_SECONDS }}" style="width: 100%; padding: 8px; margin-top: 5px;">
            </div>
        </form>
    </div>
    
    <div class="card">
        <h3>📏 Quality Thresholds</h3>
        <form id="qualityForm" style="margin-top: 20px;">
            <div style="margin-bottom: 15px;">
                <label for="min_chars"><strong>Minimum Characters:</strong></label><br>
                <input type="number" id="min_chars" name="min_chars" value="{{ config.MIN_CHARS }}" style="width: 100%; padding: 8px; margin-top: 5px;">
            </div>
            <div style="margin-bottom: 15px;">
                <label for="min_paragraphs"><strong>Minimum Paragraphs:</strong></label><br>
                <input type="number" id="min_paragraphs" name="min_paragraphs" value="{{ config.MIN_PARAGRAPHS }}" style="width: 100%; padding: 8px; margin-top: 5px;">
            </div>
        </form>
    </div>
    
    <div class="card">
        <button onclick="saveConfig()" class="btn btn-success" style="margin-right: 10px;">💾 Save Settings</button>
        <button onclick="testAuth()" class="btn">🧪 Test Authentication</button>
    </div>
    
    <div id="status"></div>
    
    <script>
        document.getElementById('cookies').value = {{ config.NOVELUPDATES_COOKIES|tojson }};
        
        function getFormData() {
            return {
                RSS_FEED_URL: document.getElementById('rss_url').value,
                NOVELUPDATES_USERNAME: document.getElementById('username').value,
                NOVELUPDATES_PASSWORD: document.getElementById('password').value,
                NOVELUPDATES_COOKIES: document.getElementById('cookies').value,
                POLL_INTERVAL_SECONDS: parseInt(document.getElementById('poll_interval').value),
                MIN_DELAY_SECONDS: parseInt(document.getElementById('min_delay').value),
                MIN_CHARS: parseInt(document.getElementById('min_chars').value),
                MIN_PARAGRAPHS: parseInt(document.getElementById('min_paragraphs').value)
            };
        }
        
        function saveConfig() {
            fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(getFormData())
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('status').innerHTML = '<div class="alert alert-success">✅ Settings saved successfully!</div>';
                } else {
                    document.getElementById('status').innerHTML = '<div class="alert alert-error">❌ Error: ' + data.error + '</div>';
                }
            });
        }
        
        function testAuth() {
            document.getElementById('status').innerHTML = '<div class="alert alert-success">🧪 Testing authentication, please wait...</div>';
            fetch('/api/test-auth', { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('status').innerHTML = '<div class="alert alert-success">✅ Authentication successful!<br>' +
                        'Feed title: ' + data.feed_title + '<br>' +
                        'Entries: ' + data.entry_count + '</div>';
                } else {
                    document.getElementById('status').innerHTML = '<div class="alert alert-error">❌ Authentication failed: ' + data.error + '</div>';
                }
            });
        }
    </script>
{% endblock %}
    """
    
    (templates_dir / "settings.html").write_text(settings_template)
    
    # Error template
    error_template = """
{% extends "base.html" %}
{% block title %}Error - Novel Scraper{% endblock %}
{% block content %}
    <div class="card">
        <div class="alert alert-error">
            <h2>❌ Error</h2>
            <p>{{ error }}</p>
        </div>
        <a href="/" class="btn">Return to Dashboard</a>
    </div>
{% endblock %}
    """
    
    (templates_dir / "error.html").write_text(error_template)
    
    logger.info("Created HTML templates")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Create templates
    create_templates()
    
    # Create exports directory
    Path("exports").mkdir(exist_ok=True)
    
    # Run the app
    app.run(host="0.0.0.0", port=6110, debug=True)
