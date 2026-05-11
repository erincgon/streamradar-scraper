"""TMDB poster/backdrop lookup via web scraping — no API key required."""

from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

from utils.http_client import HTTPClient

logger = logging.getLogger(__name__)

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/"
POSTER_SIZE = "w500"
BACKDROP_SIZE = "w1280"

_POSTER_PATH_RE = re.compile(r"/t/p/w\d+(?:_and_h\d+_\w+)?(/[a-zA-Z0-9]+\.jpg)")


_TRAILING_NOISE_RE = re.compile(
    r"\s*[-\u2013\u2014|:]\s*("
    r"netflix|hulu|disney\+?|prime video|amazon|hbo max|max|peacock|"
    r"apple tv\+?|paramount\+?|abc|cbs|nbc|fox|"
    r"official trailer|trailer|teaser|first look|watch now!?"
    r").*$",
    re.I,
)

_HEADLINE_SUFFIXES_RE = re.compile(
    r"\s+("
    r"is\s+filming\s+now|is\s+coming\s+back|is\s+back\b.*|"
    r"teaser\s+trailer\b.*|official\s+trailer\b.*|trailer\b.*|"
    r"first\s+look\b.*|gets?\s+(a\s+)?new\s+trailer\b.*|"
    r"holds?\s+wonders?\b.*|reveals?\s+the\b.*|reveals?\s+.*|"
    r"examines?\s+the\b.*|examines?\s+.*|"
    r"debuts?\s+trailer\b.*|debuts?\b.*|"
    r"where\s+will\b.*|"
    r"here'?s\s+the\s+cast\b.*|"
    r"announces?\b.*|every\b.*"
    r")$",
    re.I,
)

_HEADLINE_PREFIXES_RE = re.compile(
    r"^("
    r"watch\s+[\w\s]+?\s+in\s+|watch\s+|"
    r"dive\s+in\s+to\s+(all\s+)?the\s+|"
    r"from\s+page\s+to\s+screen:\s*|"
    r"here'?s?\s+(what|the|every)\b.*?:\s*|"
    r"\d+\s+shows?\s+\w+\s+in\s+\d{4}\s+by\s+"
    r")",
    re.I,
)


def _clean_title_for_search(title: str) -> str:
    """Strip trailing noise like source names, season/episode tags."""
    cleaned = _TRAILING_NOISE_RE.sub("", title)
    cleaned = re.sub(r"\bseason\s+\d+\b", "", cleaned, flags=re.I)
    cleaned = _HEADLINE_SUFFIXES_RE.sub("", cleaned)
    cleaned = _HEADLINE_PREFIXES_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"[:\-\u2013\u2014|]+\s*$", "", cleaned).strip()
    return cleaned or title.strip()


def _extract_title_core(title: str) -> str:
    """Pull the real film/series name from a news headline.

    Quoted titles are preferred (e.g. 'Scary Movie' from "Some Stuff in 'Scary Movie' Trailer").
    """
    quoted = re.search(
        r"[\u2018\u2019\u201C\u201D'\"]+([^\u2018\u2019\u201C\u201D'\"]{3,})[\u2018\u2019\u201C\u201D'\"]+",
        title,
    )
    if quoted:
        return quoted.group(1).strip()
    return _clean_title_for_search(title)


def _scrape_tmdb_search(query: str, search_type: str, client: HTTPClient) -> str | None:
    """GET TMDB search page, return the first poster path (e.g. /abc123.jpg)."""
    url = f"https://www.themoviedb.org/search/{search_type}?query={quote_plus(query)}&language=en-US"
    try:
        resp = client.get(url, timeout=12)
        if not resp.ok:
            logger.debug("TMDB web search HTTP %s for '%s'", resp.status_code, query)
            return None
        match = _POSTER_PATH_RE.search(resp.text or "")
        if match:
            return match.group(1)
    except Exception as exc:
        logger.debug("TMDB web scrape error for '%s': %s", query, exc)
    return None


def _search_candidates(title: str) -> list[str]:
    """Build a list of progressively simplified search queries."""
    core = _extract_title_core(title)
    candidates = [core] if core else []
    cleaned = _clean_title_for_search(title)
    if cleaned and cleaned != core:
        candidates.append(cleaned)
    words = (core or cleaned or "").split()
    if len(words) > 4:
        candidates.append(" ".join(words[:4]))
    if len(words) > 6:
        candidates.append(" ".join(words[:3]))
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        key = c.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(c)
    return out


def fetch_tmdb_images(
    title: str,
    media_type: str = "movie",
    year: int | None = None,
    http_client: HTTPClient | None = None,
) -> dict[str, str | None]:
    """Scrape TMDB search results and return poster + backdrop URLs.

    No API key needed — parses poster paths from the HTML search page.
    """
    result: dict[str, str | None] = {"poster_image_url": None, "backdrop_image_url": None}

    client = http_client or HTTPClient()
    queries = _search_candidates(title)
    if not queries:
        return result

    search_type = "tv" if media_type in ("series", "anime") else "movie"
    alt_type = "movie" if search_type == "tv" else "tv"

    for query in queries:
        poster_path = _scrape_tmdb_search(query, search_type, client)
        if not poster_path:
            poster_path = _scrape_tmdb_search(query, alt_type, client)
        if not poster_path:
            poster_path = _scrape_tmdb_search(query, "multi", client)
        if poster_path:
            result["poster_image_url"] = f"{TMDB_IMAGE_BASE}{POSTER_SIZE}{poster_path}"
            result["backdrop_image_url"] = f"{TMDB_IMAGE_BASE}{BACKDROP_SIZE}{poster_path}"
            return result

    return result
