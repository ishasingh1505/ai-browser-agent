"""
Browser tool — wraps Playwright for async web automation.

 search_web uses DuckDuckGo first, with Brave/Startpage HTML fallbacks.
visit_page uses Playwright to render JS-heavy pages and extract clean text/HTML.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import httpx
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import DuckDuckGoSearchException

from app.core.config import settings

log = logging.getLogger("browser-tool")

BLOCKED_SEARCH_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "quora.com",
    "facebook.com",
    "instagram.com",
    "reddit.com",
    "google.com",
    "support.google.com",
)


# ── Singleton browser instance ────────────────────────────────────────────────

_browser: Browser | None = None
_context: BrowserContext | None = None


async def get_browser() -> Browser:
    """Return a shared Chromium browser, launching it on first call."""
    global _browser
    if _browser is None or not _browser.is_connected():
        pw = await async_playwright().start()
        _browser = await pw.chromium.launch(headless=settings.browser_headless)
    return _browser


async def get_context() -> BrowserContext:
    """Return a shared browser context with a realistic user-agent."""
    global _context
    if _context is None:
        browser = await get_browser()
        _context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
    return _context


# ── Core tools ────────────────────────────────────────────────────────────────

async def search_web(query: str, max_results: int = 8) -> list[dict[str, str]]:
    """
    Search the web using DuckDuckGo first, with Brave HTML as a fallback.
    Runs in a thread pool so it doesn't block the async event loop.
    Returns a list of dicts: [{"title": ..., "url": ...}, ...]
    """
    def _is_allowed_result(url: str) -> bool:
        domain = urlparse(url).netloc.lower()
        return bool(domain) and not any(blocked in domain for blocked in BLOCKED_SEARCH_DOMAINS)

    def _result_from_link(url: str, title: str) -> dict[str, str] | None:
        url = url.strip()
        if not url.startswith("http") or not _is_allowed_result(url):
            return None
        domain = urlparse(url).netloc.lower()
        return {"title": title.strip() or domain, "url": url}

    def _brave_search() -> list[dict[str, str]]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        response = httpx.get(
            "https://search.brave.com/search",
            params={"q": query},
            headers=headers,
            timeout=20.0,
            follow_redirects=True,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        seen: set[str] = set()
        results: list[dict[str, str]] = []
        for link in soup.select(".snippet a[href]"):
            url = link.get("href", "").strip()
            result = _result_from_link(url, link.get_text(" ", strip=True))
            if result is None or result["url"] in seen:
                continue

            seen.add(result["url"])
            results.append(result)
            if len(results) >= max_results:
                break

        log.info("Brave fallback returned %d results for: %r", len(results), query)
        return results

    def _startpage_search() -> list[dict[str, str]]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        response = httpx.get(
            "https://www.startpage.com/sp/search",
            params={"query": query},
            headers=headers,
            timeout=20.0,
            follow_redirects=True,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        seen: set[str] = set()
        results: list[dict[str, str]] = []
        for link in soup.select("a.result-link[href]"):
            result = _result_from_link(link.get("href", ""), link.get_text(" ", strip=True))
            if result is None or result["url"] in seen:
                continue

            seen.add(result["url"])
            results.append(result)
            if len(results) >= max_results:
                break

        log.info("Startpage fallback returned %d results for: %r", len(results), query)
        return results

    def _ddg_search() -> list[dict[str, str]]:
        errors: list[str] = []
        for backend in ("api", "html", "lite"):
            try:
                results = []
                with DDGS() as ddgs:
                    for r in ddgs.text(query, backend=backend, max_results=max_results):
                        result = _result_from_link(r.get("href", ""), r.get("title", ""))
                        if result is not None:
                            results.append(result)
                if results:
                    log.info("DDG %s backend returned %d results for: %r", backend, len(results), query)
                    return results
                errors.append(f"{backend}: no results")
            except DuckDuckGoSearchException as exc:
                errors.append(f"{backend}: {exc}")
                log.warning("DDG %s backend failed for %r: %s", backend, query, exc)

        for fallback_name, fallback in (("Brave", _brave_search), ("Startpage", _startpage_search)):
            try:
                log.warning("DuckDuckGo failed across all backends for %r; trying %s fallback", query, fallback_name)
                results = fallback()
                if results:
                    return results
                errors.append(f"{fallback_name}: no results")
            except Exception as exc:
                errors.append(f"{fallback_name}: {exc}")
                log.warning("%s fallback failed for %r: %s", fallback_name, query, exc)

        raise RuntimeError("Search failed across all providers: " + " | ".join(errors))

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, _ddg_search)
    return results


async def visit_page(url: str) -> dict[str, Any]:
    """
    Load a URL with Playwright, then parse it with BeautifulSoup.

    Returns:
        {
            "url": str,
            "title": str,
            "text": str,          # cleaned visible text
            "headings": list[str],
            "html": str,          # raw HTML (truncated to 50k chars)
        }
    """
    context = await get_context()
    page: Page = await context.new_page()

    try:
        await page.goto(url, timeout=settings.browser_timeout_ms, wait_until="domcontentloaded")
        await asyncio.sleep(1.5)

        # ── Dismiss common consent / cookie popups ────────────────────────────
        consent_selectors = [
            "button:has-text('Accept all')",
            "button:has-text('Accept All')",
            "button:has-text('Accept Cookies')",
            "button:has-text('I Accept')",
            "button:has-text('Agree')",
            "button:has-text('OK')",
            "#accept-all",
            ".cookie-accept",
        ]
        for selector in consent_selectors:
            try:
                await page.click(selector, timeout=2000)
                await asyncio.sleep(1.0)
                break
            except Exception:
                continue

        # ── If page has a "Tech Specs" tab (button only, not links) click it ──
        # Only click buttons/tabs — never <a href> links as they navigate away
        spec_tab_selectors = [
            "button:has-text('Tech Specs')",
            "button:has-text('Specifications')",
            "[role='tab']:has-text('Specs')",
            "[role='tab']:has-text('Specifications')",
        ]
        for selector in spec_tab_selectors:
            try:
                await page.click(selector, timeout=2000)
                await asyncio.sleep(1.5)
                break
            except Exception:
                continue

        # ── Scroll down gradually to trigger lazy-loaded content ──────────────
        for scroll_pos in [0.25, 0.5, 0.75, 1.0]:
            await page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {scroll_pos})")
            await asyncio.sleep(0.8)

        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1.0)

        html: str = await page.content()

    finally:
        await page.close()

    # ── Parse with BeautifulSoup ──────────────────────────────────────────────
    soup = BeautifulSoup(html, "lxml")

    # Remove noisy tags
    for tag in soup(["script", "style", "nav", "footer", "iframe", "noscript"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title else ""

    headings = [h.get_text(strip=True) for h in soup.find_all(["h1", "h2", "h3"]) if h.get_text(strip=True)]

    # Clean body text — join paragraphs
    paragraphs = [p.get_text(separator=" ", strip=True) for p in soup.find_all(["p", "li", "td", "th"])]
    text = "\n".join(p for p in paragraphs if len(p) > 30)  # skip tiny fragments

    return {
        "url": url,
        "title": title,
        "headings": headings[:20],            # top 20 headings
        "text": text[:8_000],                  # ~8k chars for LLM context
        "html": html[:50_000],                 # raw HTML for deep parsing later
    }


async def close_browser() -> None:
    """Gracefully close the shared browser (call on app shutdown)."""
    global _browser, _context
    if _context:
        await _context.close()
        _context = None
    if _browser:
        await _browser.close()
        _browser = None
