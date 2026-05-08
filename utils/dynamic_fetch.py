"""Optional dynamic page fetch support via Playwright."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def fetch_dynamic_html(url: str, timeout_ms: int = 45_000) -> str | None:
    """Return rendered HTML when Playwright is available, otherwise None."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        logger.debug("Playwright is not available; skipping dynamic fetch.")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            html = page.content()
            browser.close()
            return html
    except Exception as exc:  # pragma: no cover - browser runtime is environment specific
        logger.warning("Dynamic fetch failed for %s: %s", url, exc)
        return None
