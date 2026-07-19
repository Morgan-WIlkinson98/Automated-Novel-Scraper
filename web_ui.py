"""
web_ui.py
Simple Flask web interface for the novel scraper.
Depends on: flask
    pip install flask
"""

import sqlite3
import logging
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_file
from export import get_statistics, get_series_list, export_all_to_epub, export_series_to_epub
from exceptions import DatabaseError

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'novel-scraper-secret-key-change-in-production'

# Database path
DB_PATH = "chapters.db"


def get_db_connection():
    """Get database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
    app.run(host="0.0.0.0", port=5000, debug=True)
