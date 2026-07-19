"""
Custom exception classes for the novel scraper.
Provides specific exception types for better error handling and debugging.
"""


class ScraperError(Exception):
    """Base exception for all scraper errors."""
    pass


class NetworkError(ScraperError):
    """Raised when network operations fail."""
    pass


class HTTPError(NetworkError):
    """Raised when HTTP requests fail."""
    pass


class TimeoutError(NetworkError):
    """Raised when operations timeout."""
    pass


class RobotsTxtError(NetworkError):
    """Raised when robots.txt checking fails."""
    pass


class ExtractionError(ScraperError):
    """Raised when content extraction fails."""
    pass


class QualityError(ExtractionError):
    """Raised when extracted content fails quality checks."""
    pass


class DatabaseError(ScraperError):
    """Raised when database operations fail."""
    pass


class RSSFeedError(ScraperError):
    """Raised when RSS feed operations fail."""
    pass


class ConfigurationError(ScraperError):
    """Raised when configuration is invalid."""
    pass


class ValidationError(ScraperError):
    """Raised when input validation fails."""
    pass
