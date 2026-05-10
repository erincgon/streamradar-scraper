"""Base data model and scraper abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from utils.article_url import is_valid_article_page_url, unwrap_redirect_wrapper
from utils.attribution import canonical_article_url, derive_source_attribution
from utils.content_classification import infer_content_type
from utils.normalization import (
    clamp_summary,
    clean_text,
    normalize_genres,
    normalize_pub_date_to_iso_z,
    normalize_title,
    normalize_type,
    parse_release_date,
    parse_year,
    utc_now_iso,
    utc_now_iso_z,
)


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
    source_name: str
    source_domain: str
    article_url: str | None
    content_type: str
    published_at: str | None
    updated_at: str

    @classmethod
    def from_raw(cls, raw: dict[str, Any], *, feed_name: str | None = None) -> "ContentItem":
        source_url = clean_text(raw.get("source_url"), fallback="")
        raw_article = raw.get("article_url")

        article_resolved: str | None = None
        if raw_article is not None and str(raw_article).strip():
            candidate = canonical_article_url(unwrap_redirect_wrapper(str(raw_article).strip()))
            if is_valid_article_page_url(candidate):
                article_resolved = candidate
        if article_resolved is None and source_url:
            src_canon = canonical_article_url(unwrap_redirect_wrapper(source_url))
            if is_valid_article_page_url(src_canon):
                article_resolved = src_canon

        attr_url = article_resolved or unwrap_redirect_wrapper(source_url) or source_url
        name, domain = derive_source_attribution(attr_url)
        if name == "Unknown" and source_url:
            name, domain = derive_source_attribution(source_url)

        media_type = normalize_type(raw.get("type"), fallback="movie")

        merged_pub = raw.get("published_raw") or raw.get("published_at_hint") or ""
        published_at = normalize_pub_date_to_iso_z(merged_pub if merged_pub else None)
        if not published_at:
            published_at = normalize_pub_date_to_iso_z(raw.get("release_date"))

        ov = clamp_summary(raw.get("overview"), fallback="Overview not available.")

        ctx_item = cls(
            title=normalize_title(raw.get("title"), fallback="Unknown Title"),
            year=parse_year(raw.get("year") or raw.get("title")),
            type=media_type,
            platform=clean_text(raw.get("platform"), fallback="unknown"),
            release_date=parse_release_date(raw.get("release_date")),
            overview=ov,
            genres=normalize_genres(raw.get("genres")),
            poster_image_url=raw.get("poster_image_url"),
            backdrop_image_url=raw.get("backdrop_image_url"),
            rating=_coerce_rating(raw.get("rating")),
            trailer_url=raw.get("trailer_url"),
            source_url=source_url,
            scraped_at=utc_now_iso(),
            source_name=name,
            source_domain=domain,
            article_url=article_resolved,
            content_type=_infer_bucket(
                raw=raw,
                feed_name=feed_name,
                platform=clean_text(raw.get("platform"), fallback="unknown"),
                media_type=media_type,
                title=normalize_title(raw.get("title"), fallback="Unknown Title"),
                overview=ov,
            ),
            published_at=published_at,
            updated_at=utc_now_iso_z(),
        )
        return ctx_item

    def to_dict(self) -> dict[str, Any]:
        """Stable key order: legacy fields first, then enrichment fields."""
        return {
            "title": self.title,
            "year": self.year,
            "type": self.type,
            "platform": self.platform,
            "release_date": self.release_date,
            "overview": self.overview,
            "genres": self.genres,
            "poster_image_url": self.poster_image_url,
            "backdrop_image_url": self.backdrop_image_url,
            "rating": self.rating,
            "trailer_url": self.trailer_url,
            "source_url": self.source_url,
            "scraped_at": self.scraped_at,
            "source_name": self.source_name,
            "source_domain": self.source_domain,
            "article_url": self.article_url,
            "content_type": self.content_type,
            "published_at": self.published_at,
            "updated_at": self.updated_at,
        }


def _infer_bucket(
    *,
    raw: dict[str, Any],
    feed_name: str | None,
    platform: str,
    media_type: str,
    title: str,
    overview: str,
) -> str:
    explicit = clean_text(raw.get("content_type"), fallback="")
    allowed = {
        "movie_news",
        "series_news",
        "trending",
        "upcoming_release",
        "platform_release",
        "cinema_release",
        "documentary",
        "entertainment_news",
    }
    if explicit in allowed:
        return explicit
    return infer_content_type(
        feed_name=feed_name,
        platform=platform,
        media_type=media_type,
        title=title,
        overview=overview,
    )


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
