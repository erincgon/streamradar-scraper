"""TMDB API integration for fetching movie/series poster and backdrop images."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from utils.http_client import HTTPClient

logger = logging.getLogger(__name__)

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/"

POSTER_SIZE = "w500"
BACKDROP_SIZE = "w1280"


def _clean_title_for_search(title: str) -> str:
    """Strip trailing noise like source names, season/episode info for better search."""
    cleaned = re.sub(
        r"\s*[-–—|:]\s*("
        r"netflix|hulu|disney\+?|prime video|amazon|hbo max|max|peacock|"
        r"apple tv\+?|paramount\+?|abc|cbs|nbc|fox|"
        r"official trailer|trailer|teaser|first look|watch now!?"
        r").*$",
        "",
        title,
        flags=re.I,
    )
    cleaned = re.sub(r"\bseason\s+\d+\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or title.strip()


def _extract_title_core(title: str) -> str:
    """Extract the likely film/series name from a news headline.

    News headlines often wrap the real title in quotes or follow patterns like
    'Watch X Trailer' / 'X Season 2 Is ...'.  We try the quoted portion first.
    """
    quoted = re.search(r"['\u2018\u2019\u201C\u201D\"]+([^'\u2018\u2019\u201C\u201D\"]{3,})['\u2018\u2019\u201C\u201D\"]+", title)
    if quoted:
        return quoted.group(1).strip()
    return _clean_title_for_search(title)


def fetch_tmdb_images(
    title: str,
    media_type: str = "movie",
    year: int | None = None,
    http_client: HTTPClient | None = None,
) -> dict[str, str | None]:
    """Search TMDB for *title* and return poster + backdrop URLs.

    Returns ``{"poster_image_url": ..., "backdrop_image_url": ...}`` where
    values are full HTTPS URLs or ``None``.
    """
    result: dict[str, str | None] = {"poster_image_url": None, "backdrop_image_url": None}

    if not TMDB_API_KEY:
        return result

    client = http_client or HTTPClient()
    search_title = _extract_title_core(title)
    if not search_title:
        return result

    endpoint = "search/tv" if media_type in ("series", "anime") else "search/movie"

    params: dict[str, Any] = {
        "api_key": TMDB_API_KEY,
        "query": search_title,
        "language": "en-US",
        "page": 1,
        "include_adult": "false",
    }
    if year and media_type not in ("series", "anime"):
        params["year"] = year

    try:
        resp = client.get(f"{TMDB_BASE_URL}/{endpoint}", params=params, timeout=10)
        if not resp.ok:
            logger.debug("TMDB search failed %s for '%s': HTTP %s", endpoint, search_title, resp.status_code)
            return result

        data = resp.json()
        results_list = data.get("results") or []
        if not results_list:
            if media_type in ("series", "anime"):
                return _fallback_search(search_title, "movie", year, client)
            return result

        best = results_list[0]
        poster_path = best.get("poster_path")
        backdrop_path = best.get("backdrop_path")

        if poster_path:
            result["poster_image_url"] = f"{TMDB_IMAGE_BASE}{POSTER_SIZE}{poster_path}"
        if backdrop_path:
            result["backdrop_image_url"] = f"{TMDB_IMAGE_BASE}{BACKDROP_SIZE}{backdrop_path}"

        if result["poster_image_url"] and not result["backdrop_image_url"]:
            result["backdrop_image_url"] = result["poster_image_url"]
        elif result["backdrop_image_url"] and not result["poster_image_url"]:
            result["poster_image_url"] = result["backdrop_image_url"]

    except Exception as exc:
        logger.debug("TMDB lookup error for '%s': %s", search_title, exc)

    return result


def _fallback_search(
    title: str,
    fallback_type: str,
    year: int | None,
    client: HTTPClient,
) -> dict[str, str | None]:
    """Try the opposite media type when the primary search returned nothing."""
    result: dict[str, str | None] = {"poster_image_url": None, "backdrop_image_url": None}
    endpoint = "search/movie" if fallback_type == "movie" else "search/tv"
    params: dict[str, Any] = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "language": "en-US",
        "page": 1,
        "include_adult": "false",
    }
    try:
        resp = client.get(f"{TMDB_BASE_URL}/{endpoint}", params=params, timeout=10)
        if not resp.ok:
            return result
        data = resp.json()
        results_list = data.get("results") or []
        if not results_list:
            return result
        best = results_list[0]
        poster_path = best.get("poster_path")
        backdrop_path = best.get("backdrop_path")
        if poster_path:
            result["poster_image_url"] = f"{TMDB_IMAGE_BASE}{POSTER_SIZE}{poster_path}"
        if backdrop_path:
            result["backdrop_image_url"] = f"{TMDB_IMAGE_BASE}{BACKDROP_SIZE}{backdrop_path}"
        if result["poster_image_url"] and not result["backdrop_image_url"]:
            result["backdrop_image_url"] = result["poster_image_url"]
        elif result["backdrop_image_url"] and not result["poster_image_url"]:
            result["poster_image_url"] = result["backdrop_image_url"]
    except Exception as exc:
        logger.debug("TMDB fallback search error for '%s': %s", title, exc)
    return result
