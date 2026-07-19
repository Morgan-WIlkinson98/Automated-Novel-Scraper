"""
browser.py
Browser automation using Playwright for Cloudflare-protected pages.
Depends on: playwright
    pip install playwright
    python -m playwright install chromium
"""

import logging
from contextlib import contextmanager
from urllib.parse import urlparse
from core.exceptions import HTTPError, TimeoutError, ValidationError

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
    
    from core.settings.settings import get_settings
    settings = get_settings()
    cookies = settings.NOVELUPDATES_COOKIES if isinstance(settings.NOVELUPDATES_COOKIES, dict) else None
    
    # Use the same browser fingerprint as the provided curl command
    user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    )
    
    try:
        with sync_playwright() as p:
            # Try to use installed Google Chrome for better fingerprint matching
            try:
                browser = p.chromium.launch(
                    headless=True,
                    channel="chrome",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--disable-web-security",
                    ]
                )
            except Exception as e:
                logger.warning(f"Could not launch Google Chrome ({e}), falling back to Playwright Chromium")
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--disable-web-security",
                    ]
                )
            
            context = browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1280, "height": 800},
                extra_http_headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.novelupdates.com/",
                    "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"macOS"',
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            
            if cookies:
                # Format cookies for Playwright context (must include domain and path)
                context_cookies = [
                    {"name": k, "value": v, "domain": ".novelupdates.com", "path": "/"}
                    for k, v in cookies.items()
                ]
                try:
                    context.add_cookies(context_cookies)
                except Exception as e:
                    logger.warning(f"Failed to add some cookies: {e}")
            
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


def get_page_html(url: str, timeout: int = 60) -> str:
    """Use Playwright to navigate to a Cloudflare-protected page and return the final HTML."""
    if not url or not isinstance(url, str):
        raise ValidationError(f"Invalid URL: {url}")
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        logger.error("Playwright is not installed. Run: pip install playwright && python -m playwright install chromium")
        raise HTTPError("Playwright not installed") from e
    
    logger.info(f"Fetching page HTML with browser: {url}")
    
    from core.settings.settings import get_settings
    settings = get_settings()
    cookies = settings.NOVELUPDATES_COOKIES if isinstance(settings.NOVELUPDATES_COOKIES, dict) else None
    
    user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    )
    
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(
                    headless=True,
                    channel="chrome",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--disable-web-security",
                    ]
                )
            except Exception as e:
                logger.warning(f"Could not launch Google Chrome ({e}), falling back to Playwright Chromium")
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--disable-web-security",
                    ]
                )
            
            context = browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1280, "height": 800},
                extra_http_headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.novelupdates.com/",
                    "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"macOS"',
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            
            if cookies:
                context_cookies = [
                    {"name": k, "value": v, "domain": ".novelupdates.com", "path": "/"}
                    for k, v in cookies.items()
                ]
                try:
                    context.add_cookies(context_cookies)
                except Exception as e:
                    logger.warning(f"Failed to add some cookies: {e}")
            
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                window.chrome = { runtime: {} };
            """)
            
            page = context.new_page()
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                page.wait_for_timeout(5000)
                
                final_url = page.url
                logger.info(f"Browser fetched HTML: {url} -> {final_url}")
                
                if 'cloudflare' in page.content().lower():
                    raise HTTPError(f"Cloudflare challenge blocked {url}")
                
                return page.content()
            finally:
                context.close()
                browser.close()
    except TimeoutError as e:
        logger.error(f"Browser timeout fetching {url}: {e}")
        raise TimeoutError(f"Browser timeout fetching URL {url}") from e
    except HTTPError:
        raise
    except Exception as e:
        logger.error(f"Browser failed to fetch {url}: {e}")
        raise HTTPError(f"Browser failed to fetch URL {url}: {e}") from e


@contextmanager
def get_browser_page(timeout: int = 60):
    """
    Context manager that yields a single Playwright page with the same
    fingerprint/cookies used by get_page_html. Useful for making multiple
    requests in one session (e.g. paginated chapter lists).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        logger.error("Playwright is not installed. Run: pip install playwright && python -m playwright install chromium")
        raise HTTPError("Playwright not installed") from e
    
    from core.settings.settings import get_settings
    settings = get_settings()
    cookies = settings.NOVELUPDATES_COOKIES if isinstance(settings.NOVELUPDATES_COOKIES, dict) else None
    
    user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    )
    
    p = sync_playwright().start()
    try:
        try:
            browser = p.chromium.launch(
                headless=True,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-web-security",
                ]
            )
        except Exception as e:
            logger.warning(f"Could not launch Google Chrome ({e}), falling back to Playwright Chromium")
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-web-security",
                ]
            )
        
        context = browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1280, "height": 800},
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.novelupdates.com/",
                "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
                "Upgrade-Insecure-Requests": "1",
            },
        )
        
        if cookies:
            context_cookies = [
                {"name": k, "value": v, "domain": ".novelupdates.com", "path": "/"}
                for k, v in cookies.items()
            ]
            try:
                context.add_cookies(context_cookies)
            except Exception as e:
                logger.warning(f"Failed to add some cookies: {e}")
        
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.chrome = { runtime: {} };
        """)
        
        page = context.new_page()
        page.set_default_navigation_timeout(timeout * 1000)
        page.set_default_timeout(timeout * 1000)
        yield page
    finally:
        context.close()
        browser.close()
        p.stop()
