"""
browser.py
Browser automation using Playwright for Cloudflare-protected pages.
Depends on: playwright
    pip install playwright
    python -m playwright install chromium
"""

import logging
from urllib.parse import urlparse
from exceptions import HTTPError, TimeoutError, ValidationError

logger = logging.getLogger(__name__)


def _is_novelupdates_extnu(url: str) -> bool:
    """Check if URL is a NovelUpdates external link redirect."""
    try:
        parsed = urlparse(url)
        return parsed.netloc == 'www.novelupdates.com' and parsed.path.startswith('/extnu/')
    except Exception:
        return False


def resolve_with_browser(url: str, timeout: int = 45) -> str:
    """
    Use Playwright to navigate to a Cloudflare-protected URL
    and return the final URL after redirects.
    """
    if not url or not isinstance(url, str):
        raise ValidationError(f"Invalid URL: {url}")
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        logger.error("Playwright is not installed. Run: pip install playwright && python -m playwright install chromium")
        raise HTTPError("Playwright not installed") from e
    
    logger.info(f"Resolving with browser: {url}")
    
    from settings import get_settings
    settings = get_settings()
    cookies = settings.NOVELUPDATES_COOKIES if isinstance(settings.NOVELUPDATES_COOKIES, dict) else None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-web-security",
                ]
            )
            context_options = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "viewport": {"width": 1280, "height": 800},
                "extra_http_headers": {
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.novelupdates.com/",
                },
            }
            if cookies:
                # Format cookies for Playwright context
                domain = '.novelupdates.com'
                context_cookies = [
                    {"name": k, "value": v, "domain": domain, "path": "/"}
                    for k, v in cookies.items()
                ]
                context_options["cookies"] = context_cookies
            
            context = browser.new_context(**context_options)
            
            # Hide webdriver property to avoid bot detection
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                window.chrome = { runtime: {} };
            """)
            
            page = context.new_page()
            
            try:
                # Navigate and wait until DOM is loaded, not networkidle
                # Cloudflare challenge may keep network busy
                response = page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                
                # Wait for Cloudflare challenge/redirect to complete
                page.wait_for_timeout(5000)
                
                # Try to wait for URL to change from original (indicating redirect)
                try:
                    page.wait_for_function(
                        f"window.location.href !== '{url}'",
                        timeout=10000
                    )
                except Exception:
                    pass
                
                # Extra wait to let final page settle
                page.wait_for_timeout(2000)
                
                final_url = page.url
                logger.info(f"Browser resolved: {url} -> {final_url}")
                
                # Check if we got stuck at Cloudflare
                if final_url == url or 'cloudflare' in page.content().lower():
                    raise HTTPError(f"Cloudflare challenge blocked {url}")
                
                return final_url
            finally:
                context.close()
                browser.close()
    except TimeoutError as e:
        logger.error(f"Browser timeout resolving {url}: {e}")
        raise TimeoutError(f"Browser timeout resolving URL {url}") from e
    except HTTPError:
        raise
    except Exception as e:
        logger.error(f"Browser failed to resolve {url}: {e}")
        raise HTTPError(f"Browser failed to resolve URL {url}: {e}") from e
