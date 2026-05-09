"""Image URL validation helpers."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from utils.http_client import HTTPClient

logger = logging.getLogger(__name__)

_IMG_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")


def _looks_like_image_url(url: str) -> bool:
    lowered = url.lower()
    if any(ext in lowered for ext in _IMG_EXTENSIONS):
        return True
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in _IMG_EXTENSIONS)


def _is_known_image_host(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    known = (
        "variety.com",
        "tmdb.org",
        "imdb.com",
        "netflix.com",
        "disney",
        "amazon",
        "max.com",
        "hbo",
        "googleusercontent.com",
        "ggpht.com",
        "cdn",
        "image",
        "img",
    )
    return any(key in host for key in known)


def validate_image_url(url: str | None, http_client: HTTPClient) -> str | None:
    """Return URL if it is very likely an image."""
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        return None

    if _looks_like_image_url(url) and _is_known_image_host(url):
        return url
    if _is_known_image_host(url):
        # Many CDNs serve images without file extension.
        return url

    try:
        response = http_client.head(url)
        content_type = response.headers.get("Content-Type", "").lower()
        if response.ok and content_type.startswith("image/"):
            return url
        # Some CDNs block HEAD or omit content-type but URL is still valid.
        if response.status_code in (401, 403, 405) and _looks_like_image_url(url):
            return url
        if response.ok and not content_type and _looks_like_image_url(url):
            return url
    except Exception as exc:  # pragma: no cover - network errors are environment specific
        logger.debug("Image URL validation failed for %s: %s", url, exc)
        if _looks_like_image_url(url):
            return url
    return None


def extract_image_from_article(source_url: str, http_client: HTTPClient) -> str | None:
    """
    Try to resolve article page and extract og/twitter image.
    """
    if not source_url.startswith(("http://", "https://")):
        return None

    try:
        response = http_client.get(source_url)
        if not response.ok:
            return None
        html = response.text or ""
        patterns = (
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        )
        for pattern in patterns:
            match = re.search(pattern, html, flags=re.I)
            if not match:
                continue
            candidate = match.group(1).strip()
            validated = validate_image_url(candidate, http_client)
            if validated:
                return validated
    except Exception as exc:  # pragma: no cover
        logger.debug("Article image extraction failed for %s: %s", source_url, exc)
    return None
