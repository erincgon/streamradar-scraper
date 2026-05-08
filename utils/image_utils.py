"""Image URL validation helpers."""

from __future__ import annotations

import logging

from utils.http_client import HTTPClient

logger = logging.getLogger(__name__)


def validate_image_url(url: str | None, http_client: HTTPClient) -> str | None:
    """Return URL only if it looks like a reachable image."""
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        return None

    try:
        response = http_client.head(url)
        content_type = response.headers.get("Content-Type", "").lower()
        if response.ok and content_type.startswith("image/"):
            return url
    except Exception as exc:  # pragma: no cover - network errors are environment specific
        logger.debug("Image URL validation failed for %s: %s", url, exc)
    return None
