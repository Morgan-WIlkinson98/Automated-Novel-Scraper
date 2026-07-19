"""
logging_config.py
Centralized logging configuration for the application.
"""

import logging
import logging.handlers
from pathlib import Path
from core.settings import get_settings


def setup_logging(level: int = logging.INFO, log_dir: str = None):
    """
    Set up logging to console and rotating file.
    All modules log to a single app log; the UI can filter by logger name.
    """
    if log_dir is None:
        log_dir = get_settings().EXPORT_DIR if hasattr(get_settings(), 'EXPORT_DIR') else '.'
        log_dir = Path(log_dir).parent / "logs"
    else:
        log_dir = Path(log_dir)
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / "app.log"
    
    # Avoid duplicate handlers if called multiple times
    root = logging.getLogger()
    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        return
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)
    
    # File handler (5 MB x 3 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    
    root.setLevel(level)
    
    return str(log_dir)


def get_log_path() -> str:
    """Return the current application log file path."""
    settings = get_settings()
    log_dir = Path(getattr(settings, 'EXPORT_DIR', 'exports')).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    return str(log_dir / "app.log")
