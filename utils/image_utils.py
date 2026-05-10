"""Image URL validation helpers."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from utils.http_client import HTTPClient

logger = logging.getLogger(__name__)

_IMG_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")

_PLACEHOLDER_SNIPPETS = (
    "placeholder",
    "/1x1",
    "1x1.",
    "blank.gif",
    "pixel.gif",
    "spacer.gif",
    "/clear.gif",
    "transparent.gif",
    "default-avatar",
    "anonymous.png",
    "no-image",
    "missing-image",
    "image-not-found",
)


def _looks_like_image_url(url: str) -> bool:
    lowered = url.lower()
    if any(ext in lowered for ext in _IMG_EXTENSIONS):
        return True
    if (
        "format=webp" in lowered
        or "format=jpeg" in lowered
        or "format=jpg" in lowered
        or "format=pjpeg" in lowered
        or "format=png" in lowered
    ):
        return True
    if "/ripcut-delivery/" in lowered:
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
        "nflximg.net",
        "nflxext.com",
        "disney",
        "amazon",
        "brightspotcdn",
        "brightspot",
        "bamgrid.com",
        "max.com",
        "hbo",
        "googleusercontent.com",
        "ggpht.com",
        "turner.com",
        "wbd.",
        "press.wbd",
        "wordpress.com",
        "wp.com",
        "squarespace",
        "wikimedia.org",
        # generic fallbacks still gated by HTTPS + validation
        "cdn",
        "image",
        "img",
    )
    return any(key in host for key in known)


def _is_placeholder(url: str) -> bool:
    lowered = url.lower()
    return any(snippet in lowered for snippet in _PLACEHOLDER_SNIPPETS)


def validate_image_url(url: str | None, http_client: HTTPClient) -> str | None:
    """Return URL only when it appears to reference a reachable HTTPS asset."""
    if not url:
        return None
    if url.startswith("http://"):
        url = "https://" + url[7:]
    if not url.startswith("https://"):
        return None
    if _is_placeholder(url):
        return None

    if _looks_like_image_url(url) and _is_known_image_host(url):
        return url
    if _is_known_image_host(url):
        return url

    try:
        response = http_client.head(url)
        content_type = response.headers.get("Content-Type", "").lower()
        if response.ok and content_type.startswith("image/"):
            return url
        if response.status_code in (401, 403, 405) and _looks_like_image_url(url):
            return url
        if response.ok and not content_type and _looks_like_image_url(url):
            return url
    except Exception as exc:  # pragma: no cover - network errors are environment specific
        logger.debug("Image URL validation failed for %s: %s", url, exc)
        if _looks_like_image_url(url):
            return url
    return None


def is_standalone_image_cdn_url(url: str | None) -> bool:
    """True when URL is almost certainly a hotlinked image, not an HTML article."""
    if not url or not isinstance(url, str):
        return False
    host = urlparse(url.strip()).netloc.lower()
    return bool(
        host.endswith("googleusercontent.com")
        or host.endswith("ggpht.com")
        or host.endswith("gstatic.com")
    )


def normalize_rss_thumbnail_url(url: str | None) -> str | None:
    """Upgrade tiny Google-hosted RSS thumbnails (`=w16`) to a larger rendition."""
    if not url or not isinstance(url, str):
        return None
    u = url.strip()
    if not is_standalone_image_cdn_url(u):
        return u

    def repl(m: re.Match[str]) -> str:
        n = int(m.group(1))
        return "=w1280" if n < 400 else m.group(0)

    return re.sub(r"=w(\d+)\b", repl, u, count=1)


def extract_image_from_article(source_url: str, http_client: HTTPClient) -> str | None:
    """
    Try to resolve article page and extract og/twitter image.
    """
    if not source_url.startswith(("http://", "https://")):
        return None

    if is_standalone_image_cdn_url(source_url):
        upsized = normalize_rss_thumbnail_url(source_url)
        return validate_image_url(upsized, http_client) if upsized else None

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
            if candidate.startswith("//"):
                candidate = f"https:{candidate}"
            candidate = normalize_rss_thumbnail_url(candidate) or candidate
            validated = validate_image_url(candidate, http_client)
            if validated:
                return validated
    except Exception as exc:  # pragma: no cover
        logger.debug("Article image extraction failed for %s: %s", source_url, exc)
    return None
