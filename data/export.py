"""
export.py
Export chapters to EPUB format organized by series.
Depends on: ebooklib
    pip install ebooklib
"""

import sqlite3
import logging
from pathlib import Path
from typing import List, Optional
from ebooklib import epub
from core.settings import get_settings
from core.exceptions import DatabaseError, ValidationError

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    """Get the chapters database path from settings."""
    return get_settings().CHAPTERS_DB


def _get_export_dir() -> str:
    """Get the export directory from settings."""
    return get_settings().EXPORT_DIR


def get_chapters_by_series(db_path: Optional[str] = None) -> dict:
    """Retrieve all chapters grouped by series from database."""
    if db_path is None:
        db_path = _get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT series, chapter_label, title, text, extraction_method, fetched_at
            FROM chapters
            ORDER BY series, fetched_at
        """)
        
        chapters_by_series = {}
        for row in cursor:
            series = row['series'] or 'Unknown'
            if series not in chapters_by_series:
                chapters_by_series[series] = []
            chapters_by_series[series].append(dict(row))
        
        conn.close()
        logger.info(f"Retrieved {sum(len(ch) for ch in chapters_by_series.values())} chapters across {len(chapters_by_series)} series")
        return chapters_by_series
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve chapters from database: {e}")
        raise DatabaseError(f"Failed to retrieve chapters: {e}") from e


def create_epub(series_name: str, chapters: List[dict], output_dir: Optional[str] = None) -> str:
    """Create an EPUB file for a series."""
    if not series_name:
        raise ValidationError("Series name cannot be empty")
    if not chapters:
        raise ValidationError("Chapters list cannot be empty")
    
    if output_dir is None:
        output_dir = _get_export_dir()
    
    # Sanitize series name for filename/folder
    safe_name = "".join(c for c in series_name if c.isalnum() or c in (' ', '-', '_')).strip()
    if not safe_name:
        safe_name = "Unknown"
    
    # Create output directory and series subfolder
    output_path = Path(output_dir) / safe_name
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Create EPUB
    book = epub.EpubBook()
    
    # Set metadata
    book.set_identifier(f"novel-{safe_name.lower().replace(' ', '-')}")
    book.set_title(series_name)
    book.set_language('en')
    
    # Add chapters
    epub_chapters = []
    toc_entries = []
    
    for i, chapter in enumerate(chapters):
        chapter_title = chapter.get('title', chapter.get('chapter_label', f'Chapter {i+1}'))
        chapter_text = chapter.get('text', '')
        
        # Create chapter file
        file_name = f"chapter_{i+1:03d}.xhtml"
        chapter_content = f"""
        <html>
        <head>
            <title>{chapter_title}</title>
        </head>
        <body>
            <h1>{chapter_title}</h1>
            <div>
                {chapter_text.replace('\n\n', '</p><p>').replace('\n', '<br/>')}
            </div>
        </body>
        </html>
        """
        
        epub_chapter = epub.EpubHtml(
            title=chapter_title,
            file_name=file_name,
            content=chapter_content
        )
        book.add_item(epub_chapter)
        epub_chapters.append(epub_chapter)
        toc_entries.append(epub_chapter)
    
    # Define Table of Contents
    book.toc = toc_entries
    
    # Add default NCX and Nav file
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    
    # Define CSS style
    style = '''
    @namespace epub "http://www.idpf.org/2007/ops";
    body {
        font-family: Cambria, Liberation Serif, serif;
        line-height: 1.5;
        margin: 2em;
    }
    h1 {
        text-align: center;
        margin-bottom: 1em;
    }
    p {
        text-indent: 1.5em;
        margin: 0;
    }
    '''
    nav_css = epub.EpubItem(
        uid="style_nav",
        file_name="style/nav.css",
        media_type="text/css",
        content=style
    )
    book.add_item(nav_css)
    
    # Add spine
    book.spine = ['nav'] + epub_chapters
    
    # Write EPUB file
    epub_filename = f"{safe_name}.epub"
    epub_path = output_path / epub_filename
    
    epub.write_epub(str(epub_path), book, {})
    logger.info(f"Created EPUB: {epub_path} ({len(chapters)} chapters)")
    
    return str(epub_path)


def export_all_to_epub(db_path: Optional[str] = None, output_dir: Optional[str] = None) -> List[str]:
    """Export all series to EPUB files."""
    if db_path is None:
        db_path = _get_db_path()
    if output_dir is None:
        output_dir = _get_export_dir()
    
    chapters_by_series = get_chapters_by_series(db_path)
    
    if not chapters_by_series:
        logger.warning("No chapters found to export")
        return []
    
    exported_files = []
    for series_name, chapters in chapters_by_series.items():
        try:
            epub_path = create_epub(series_name, chapters, output_dir)
            exported_files.append(epub_path)
        except Exception as e:
            logger.error(f"Failed to export series '{series_name}': {e}")
            continue
    
    logger.info(f"Exported {len(exported_files)} EPUB files to {output_dir}")
    return exported_files


def export_series_to_epub(series_name: str, db_path: Optional[str] = None, output_dir: Optional[str] = None) -> str:
    """Export a specific series to EPUB."""
    if db_path is None:
        db_path = _get_db_path()
    if output_dir is None:
        output_dir = _get_export_dir()
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT series, chapter_label, title, text, extraction_method, fetched_at
            FROM chapters
            WHERE series = ?
            ORDER BY fetched_at
        """, (series_name,))
        
        chapters = [dict(row) for row in cursor]
        conn.close()
        
        if not chapters:
            logger.warning(f"No chapters found for series: {series_name}")
            return None
        
        return create_epub(series_name, chapters, output_dir)
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve chapters for series '{series_name}': {e}")
        raise DatabaseError(f"Failed to retrieve chapters: {e}") from e


def export_selected_chapters_to_epub(series_name: str, chapter_urls: List[str], db_path: Optional[str] = None, output_dir: Optional[str] = None) -> str:
    """Export a selected subset of chapters from a series to EPUB."""
    if not chapter_urls:
        raise ValidationError("No chapters selected for export")
    
    if db_path is None:
        db_path = _get_db_path()
    if output_dir is None:
        output_dir = _get_export_dir()
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Build placeholders for the IN clause
        placeholders = ','.join('?' for _ in chapter_urls)
        cursor = conn.execute(f"""
            SELECT series, chapter_label, title, text, extraction_method, fetched_at
            FROM chapters
            WHERE series = ? AND url IN ({placeholders})
            ORDER BY fetched_at
        """, (series_name, *chapter_urls))
        
        chapters = [dict(row) for row in cursor]
        conn.close()
        
        if not chapters:
            logger.warning(f"No chapters found for series: {series_name} with selected URLs")
            return None
        
        # Use a distinct filename when exporting a subset
        safe_name = "".join(c for c in series_name if c.isalnum() or c in (' ', '-', '_')).strip() or "Unknown"
        export_label = f"{safe_name} (selected)"
        return create_epub(export_label, chapters, output_dir)
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve selected chapters for series '{series_name}': {e}")
        raise DatabaseError(f"Failed to retrieve selected chapters: {e}") from e


def get_series_list(db_path: Optional[str] = None) -> List[str]:
    """Get list of all series from both chapters and series_info."""
    if db_path is None:
        db_path = _get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("""
            SELECT DISTINCT series FROM chapters
            UNION
            SELECT DISTINCT series FROM series_info
            ORDER BY series
        """)
        series = [row[0] for row in cursor if row[0]]
        conn.close()
        return series
    except sqlite3.Error as e:
        logger.error(f"Failed to get series list: {e}")
        raise DatabaseError(f"Failed to get series list: {e}") from e


def get_statistics(db_path: Optional[str] = None) -> dict:
    """Get statistics about stored chapters."""
    if db_path is None:
        db_path = _get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        
        # Total chapters
        cursor = conn.execute("SELECT COUNT(*) FROM chapters")
        total_chapters = cursor.fetchone()[0]
        
        # Total series
        cursor = conn.execute("SELECT COUNT(DISTINCT series) FROM chapters")
        total_series = cursor.fetchone()[0]
        
        # Chapters by method
        cursor = conn.execute("""
            SELECT extraction_method, COUNT(*) 
            FROM chapters 
            GROUP BY extraction_method
        """)
        by_method = {row[0]: row[1] for row in cursor}
        
        # Chapters by series
        cursor = conn.execute("""
            SELECT series, COUNT(*) 
            FROM chapters 
            GROUP BY series 
            ORDER BY COUNT(*) DESC
            LIMIT 10
        """)
        by_series = {row[0]: row[1] for row in cursor}
        
        conn.close()
        
        return {
            'total_chapters': total_chapters,
            'total_series': total_series,
            'by_method': by_method,
            'by_series': by_series
        }
    except sqlite3.Error as e:
        logger.error(f"Failed to get statistics: {e}")
        raise DatabaseError(f"Failed to get statistics: {e}") from e


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Export all series
    export_all_to_epub()
    
    # Print statistics
    stats = get_statistics()
    print(f"\nStatistics:")
    print(f"Total chapters: {stats['total_chapters']}")
    print(f"Total series: {stats['total_series']}")
    print(f"By method: {stats['by_method']}")
    print(f"Top series: {stats['by_series']}")
