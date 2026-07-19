"""
settings.py
Clean configuration management with environment variable and config file support.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class Settings:
    """Application settings loaded from environment variables and config file."""
    
    CONFIG_PATH = Path("config.py")
    
    # Default values
    DEFAULTS: Dict[str, Any] = {
        'RSS_FEED_URL': 'https://www.novelupdates.com/rss/',
        'NOVELUPDATES_USERNAME': None,
        'NOVELUPDATES_PASSWORD': None,
        'NOVELUPDATES_COOKIES': None,
        'POLL_INTERVAL_SECONDS': 15 * 60,
        'MIN_DELAY_SECONDS': 5,
        'USER_AGENT': 'Mozilla/5.0 (compatible; ChapterFetcher/1.0; +https://example.invalid/bot-info)',
        'EXTRA_HTTP_HEADERS': None,
        'MIN_CHARS': 500,
        'MIN_PARAGRAPHS': 3,
        'SEEN_ENTRIES_DB': 'seen_entries.db',
        'CHAPTERS_DB': 'chapters.db',
        'EXPORT_DIR': None,
        'EXPORT_DIR_MAC': '/Users/morganwilkinson/Novel Exports',
        'EXPORT_DIR_WINDOWS': r'C:\Users\%USERNAME%\Novel Exports',
    }
    
    @classmethod
    def load(cls) -> 'Settings':
        """Load settings from environment variables and config file."""
        settings = cls()
        
        # Start with defaults
        for key, value in cls.DEFAULTS.items():
            setattr(settings, key, value)
        
        # Override from config file if it exists
        if cls.CONFIG_PATH.exists():
            settings._load_from_file()
        
        # Override from environment variables
        settings._load_from_env()
        
        # Resolve active export dir from OS-specific default if not explicitly set
        if getattr(settings, 'EXPORT_DIR', None) is None:
            if os.name == 'nt':
                settings.EXPORT_DIR = os.path.expandvars(settings.EXPORT_DIR_WINDOWS)
            else:
                settings.EXPORT_DIR = settings.EXPORT_DIR_MAC
        
        return settings
    
    def _load_from_file(self):
        """Load settings from config.py file."""
        try:
            config_globals = {}
            exec(compile(self.CONFIG_PATH.read_text(), self.CONFIG_PATH, 'exec'), config_globals)
            
            for key in self.DEFAULTS.keys():
                if key in config_globals:
                    setattr(self, key, config_globals[key])
                    
            logger.debug("Loaded settings from config.py")
        except Exception as e:
            logger.warning(f"Failed to load config.py: {e}. Using defaults and environment.")
    
    def _load_from_env(self):
        """Override settings from environment variables."""
        for key in self.DEFAULTS.keys():
            env_value = os.getenv(key)
            if env_value is not None:
                # Try to convert to original type
                default_value = self.DEFAULTS[key]
                if isinstance(default_value, int):
                    try:
                        setattr(self, key, int(env_value))
                    except ValueError:
                        logger.warning(f"Cannot convert env var {key} to int, using value as string")
                        setattr(self, key, env_value)
                elif isinstance(default_value, (dict, list)):
                    import json
                    try:
                        setattr(self, key, json.loads(env_value))
                    except json.JSONDecodeError:
                        setattr(self, key, env_value)
                elif env_value.lower() in ('true', 'false'):
                    setattr(self, key, env_value.lower() == 'true')
                elif env_value.lower() == 'none':
                    setattr(self, key, None)
                else:
                    setattr(self, key, env_value)
    
    def save_to_file(self, data: Dict[str, Any]) -> bool:
        """Save settings to config.py file."""
        try:
            content = self._generate_config_content(data)
            self.CONFIG_PATH.write_text(content)
            logger.info("Settings saved to config.py")
            return True
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            return False
    
    def _generate_config_content(self, data: Dict[str, Any]) -> str:
        """Generate config.py file content from settings data."""
        lines = [
            '"""',
            'Configuration file for the novel scraper.',
            'Contains credentials and settings.',
            '"""',
            '',
        ]
        
        for key in self.DEFAULTS.keys():
            value = data.get(key, self.DEFAULTS[key])
            lines.append(self._format_config_line(key, value))
            lines.append('')
        
        return '\n'.join(lines)
    
    def _format_config_line(self, key: str, value: Any) -> str:
        """Format a single config line."""
        comment = self._get_comment(key)
        if comment:
            lines = [f'# {line}' for line in comment.split('\n')]
        else:
            lines = []
        
        if value is None:
            lines.append(f'{key} = None')
        elif isinstance(value, str):
            # Use repr() to safely escape backslashes and quotes in paths
            lines.append(f'{key} = {repr(value)}')
        elif isinstance(value, (dict, list)):
            import json
            lines.append(f'{key} = {json.dumps(value, indent=4)}')
        else:
            lines.append(f'{key} = {value}')
        
        return '\n'.join(lines)
    
    def _get_comment(self, key: str) -> Optional[str]:
        """Get comment for a config key."""
        comments = {
            'RSS_FEED_URL': 'NovelUpdates RSS Feed URL',
            'NOVELUPDATES_USERNAME': 'NovelUpdates Authentication (if required)',
            'NOVELUPDATES_PASSWORD': 'Set to your password (kept private)',
            'NOVELUPDATES_COOKIES': 'Cookie authentication (if you have session cookies)',
            'POLL_INTERVAL_SECONDS': 'Polling interval in seconds',
            'MIN_DELAY_SECONDS': 'Minimum delay between requests to same domain',
            'USER_AGENT': 'User-Agent for HTTP requests',
            'MIN_CHARS': 'Minimum character count for quality check',
            'MIN_PARAGRAPHS': 'Minimum paragraph count for quality check',
            'EXTRA_HTTP_HEADERS': 'Additional HTTP headers for Cloudflare bypass (optional)',
            'SEEN_ENTRIES_DB': 'Database path for seen entries',
            'CHAPTERS_DB': 'Database path for chapters',
            'EXPORT_DIR': 'Active export directory for EPUB files (auto-resolved if empty)',
            'EXPORT_DIR_MAC': 'Default export directory on macOS',
            'EXPORT_DIR_WINDOWS': 'Default export directory on Windows (%USERNAME% expands to current user)',
        }
        return comments.get(key)
    
    def to_dict(self, hide_secrets: bool = False) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        result = {}
        for key in self.DEFAULTS.keys():
            value = getattr(self, key, self.DEFAULTS[key])
            if hide_secrets and key == 'NOVELUPDATES_PASSWORD' and value:
                value = '******'
            result[key] = value
        return result


# Global settings instance
_settings = None

def get_settings() -> Settings:
    """Get or create global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings.load()
    return _settings

def reload_settings() -> Settings:
    """Reload settings from file and environment."""
    global _settings
    _settings = Settings.load()
    return _settings
