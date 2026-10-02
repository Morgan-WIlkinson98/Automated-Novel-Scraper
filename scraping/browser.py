"""
browser.py
Browser automation using Playwright for Cloudflare-protected pages.
Depends on: playwright
    pip install playwright
    python -m playwright install chromium
"""

import logging
import os
from contextlib import contextmanager
from urllib.parse import urlparse
from core.exceptions import HTTPError, TimeoutError, ValidationError

logger = logging.getLogger(__name__)


def _headed() -> bool:
    """Run the browser headed (NU_HEADED=1). Headless Chromium never
    clears NovelUpdates' Cloudflare challenge — headed does in ~4s.
    Locally a window briefly pops up; in CI run under xvfb (see
    poll.yml)."""
    return os.getenv("NU_HEADED") == "1"


def _is_novelupdates_extnu(url: str) -> bool:
    """Check if URL is a NovelUpdates external link redirect."""
    try:
        parsed = urlparse(url)
        return parsed.netloc == 'www.novelupdates.com' and parsed.path.startswith('/extnu/')
    except Exception:
        return False


_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
)


def _launch_browser(p):
    """Launch Google Chrome when available, else bundled Chromium.
    Headed (NU_HEADED=1) clears NU's Cloudflare challenge; headless does
    not. Keep the launch args minimal — extra hardening flags
    (--disable-web-security, site-per-process off), forged sec-ch-ua
    headers, and stubbing window.chrome all trip the bot check."""
    args = ["--disable-blink-features=AutomationControlled"]
    try:
        return p.chromium.launch(
            headless=not _headed(), channel="chrome", args=args)
    except Exception as e:
        logger.warning(f"Could not launch Google Chrome ({e}), falling back to Playwright Chromium")
        return p.chromium.launch(headless=not _headed(), args=args)


def _new_context(browser):
    """Browser context with the NU session cookies loaded."""
    from core.settings import get_settings
    cookies = get_settings().NOVELUPDATES_COOKIES
    context = browser.new_context(
        user_agent=_USER_AGENT,
        viewport={"width": 1280, "height": 800},
    )
    if isinstance(cookies, dict) and cookies:
        try:
            context.add_cookies([
                {"name": k, "value": v, "domain": ".novelupdates.com", "path": "/"}
                for k, v in cookies.items()
            ])
        except Exception as e:
            logger.warning(f"Failed to add some cookies: {e}")
    return context


def resolve_in_page(page, url: str, timeout: int = 45) -> str:
    """Resolve an extnu/redirect link inside an existing browser page.

    Shared-session variant for the backfill drain: the first navigation
    solves Cloudflare once and the clearance cookie persists in the
    context, so subsequent resolves ride the same session instead of
    re-rolling the challenge per link (which is what got the drain
    rate-limited)."""
    # Navigate and wait until DOM is loaded, not networkidle —
    # the Cloudflare challenge may keep network busy.
    page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
    page.wait_for_timeout(5000)
    try:
        page.wait_for_function(
            f"window.location.href !== '{url}'", timeout=10000)
    except Exception:
        pass
    page.wait_for_timeout(2000)

    def _still_challenged() -> bool:
        try:
            u = page.url
            t = (page.title() or "").lower()
        except Exception:
            return False
        return u == url or "just a moment" in t \
            or "attention required" in t

    # A flagged IP can keep the challenge churning well past the first
    # waits — give it up to ~30s more (2s polls) before declaring blocked.
    if _still_challenged():
        for _ in range(15):
            page.wait_for_timeout(2000)
            if not _still_challenged():
                break

    final_url = page.url
    logger.info(f"Browser resolved: {url} -> {final_url}")
    # A resolved link can still land on a CF interstitial — but many
    # legit chapter sites also serve "cloudflare" strings in their HTML
    # (CDN scripts, protection badges), which made the old body-substring
    # check a false-positive factory. Real interstitials identify by
    # title: "Just a moment…" / "Attention Required!".
    try:
        title = (page.title() or "").lower()
    except Exception:
        title = ""
    if final_url == url or "just a moment" in title \
            or "attention required" in title:
        raise HTTPError(f"Cloudflare challenge blocked {url}")
    return final_url


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

    try:
        with sync_playwright() as p:
            browser = _launch_browser(p)
            context = _new_context(browser)
            page = context.new_page()
            try:
                return resolve_in_page(page, url, timeout)
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

    try:
        with sync_playwright() as p:
            browser = _launch_browser(p)
            context = _new_context(browser)
            page = context.new_page()
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                page.wait_for_timeout(5000)
                
                final_url = page.url
                logger.info(f"Browser fetched HTML: {url} -> {final_url}")

                # Title-based interstitial check — legit pages can carry
                # "cloudflare" strings without being a challenge.
                try:
                    title = (page.title() or "").lower()
                except Exception:
                    title = ""
                if "just a moment" in title or "attention required" in title:
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
    
    p = sync_playwright().start()
    try:
        browser = _launch_browser(p)
        context = _new_context(browser)
        page = context.new_page()
        page.set_default_navigation_timeout(timeout * 1000)
        page.set_default_timeout(timeout * 1000)
        yield page
    finally:
        context.close()
        browser.close()
        p.stop()
