"""Infer stream-safe content classification for aggregated metadata rows."""

from __future__ import annotations

import re
from typing import Any


def infer_content_type(
    *,
    feed_name: str | None,
    platform: str,
    media_type: str,
    title: str,
    overview: str,
) -> str:
    """
    Allowed: movie_news, series_news, trending, upcoming_release, platform_release,
    cinema_release, documentary, entertainment_news
    """
    feed = (feed_name or "").lower()
    plat = clean_lower(platform)
    mt = clean_lower(media_type)
    merged = f"{clean_lower(title)} {clean_lower(overview)}"

    if mt == "documentary" or re.search(r"\bdocumentary\b", merged):
        return "documentary"

    if feed == "trending" or plat == "imdb_trending":
        return "trending"

    if feed == "upcoming":
        return "upcoming_release"

    if feed == "cinema_releases":
        return "cinema_release"

    if feed in {"netflix", "disney_plus", "prime_video", "hbo_max"}:
        return "platform_release"

    if re.search(r"\b(?:tv\s+series|season\s*\d+|anthology\s+series|episode|limited\s+series)\b", merged):
        return "series_news"
    if re.search(r"\b(?:feature\s+film|movie\s+release|film\s+release|blockbuster|cinematic)\b", merged):
        return "movie_news"
    if mt == "series":
        return "series_news"
    if mt == "movie":
        return "movie_news"

    return "entertainment_news"


def clean_lower(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()
