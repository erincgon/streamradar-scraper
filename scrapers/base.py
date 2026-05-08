"""Base data model and scraper abstraction."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any

from utils.normalization import clean_text, normalize_genres, parse_release_date, parse_year, utc_now_iso

logger = logging.getLogger(__name__)


@dataclass
class ContentItem:
    title: str
    year: int | None
    type: str
    platform: str
    release_date: str | None
    overview: str
    genres: list[str]
    poster_image_url: str | None
    backdrop_image_url: str | None
    rating: float | None
    trailer_url: str | None
    source_url: str
    scraped_at: str

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "ContentItem":
        return cls(
            title=clean_text(raw.get("title"), fallback="Unknown Title"),
            year=parse_year(raw.get("year") or raw.get("title")),
            type=clean_text(raw.get("type"), fallback="movie").lower(),
            platform=clean_text(raw.get("platform"), fallback="unknown"),
            release_date=parse_release_date(raw.get("release_date")),
            overview=clean_text(raw.get("overview"), fallback="Overview not available."),
            genres=normalize_genres(raw.get("genres")),
            poster_image_url=raw.get("poster_image_url"),
            backdrop_image_url=raw.get("backdrop_image_url"),
            rating=_coerce_rating(raw.get("rating")),
            trailer_url=raw.get("trailer_url"),
            source_url=clean_text(raw.get("source_url"), fallback=""),
            scraped_at=utc_now_iso(),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coerce_rating(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(10.0, rating))


class BaseScraper(ABC):
    """Each scraper returns a list of normalized raw items."""

    scraper_name = "base"

    @abstractmethod
    def scrape(self) -> list[dict[str, Any]]:
        raise NotImplementedError
