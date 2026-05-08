"""Reusable RSS scraper helpers."""

from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus
from typing import Any

import feedparser

from scrapers.base import BaseScraper
from utils.http_client import HTTPClient

logger = logging.getLogger(__name__)


class GoogleNewsRSSScraper(BaseScraper):
    """Scrape release intelligence from stable RSS feed endpoints."""

    def __init__(
        self,
        scraper_name: str,
        query: str,
        platform: str,
        default_type: str,
        fallback_queries: list[str] | None = None,
        feed_urls: list[str] | None = None,
        max_items: int = 120,
    ) -> None:
        self.scraper_name = scraper_name
        self.query = query
        self.fallback_queries = fallback_queries or []
        self.platform = platform
        self.default_type = default_type
        self.max_items = max_items
        self.http_client = HTTPClient()
        self._extra_feed_urls = feed_urls or []

    @property
    def feed_url(self) -> str:
        return (
            "https://news.google.com/rss/search?"
            f"q={quote_plus(self.query)}&hl=en-US&gl=US&ceid=US:en"
        )

    def _google_news_url(self, query: str) -> str:
        return (
            "https://news.google.com/rss/search?"
            f"q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
        )

    def _build_feed_urls(self) -> list[str]:
        urls = [self.feed_url]
        urls.extend(self._google_news_url(query) for query in self.fallback_queries)
        urls.extend(self._extra_feed_urls)
        # keep order, remove duplicates
        return list(dict.fromkeys(urls))

    def _extract_type(self, text: str) -> str:
        lowered = text.lower()
        if "documentary" in lowered:
            return "documentary"
        if "anime" in lowered:
            return "anime"
        if any(k in lowered for k in ("season", "episode", "series", "tv")):
            return "series"
        if "movie" in lowered or "film" in lowered:
            return "movie"
        return self.default_type

    def _extract_genres(self, text: str) -> list[str]:
        candidates = [
            "Action",
            "Adventure",
            "Animation",
            "Comedy",
            "Crime",
            "Documentary",
            "Drama",
            "Family",
            "Fantasy",
            "Horror",
            "Mystery",
            "Romance",
            "Sci-Fi",
            "Thriller",
        ]
        lowered = text.lower()
        return [genre for genre in candidates if genre.lower() in lowered]

    def _sanitize_title(self, title: str) -> str:
        cleaned = re.sub(r"\s*[-|]\s*(netflix|disney\+?|prime video|max|hbo max|tudum).*$", "", title, flags=re.I)
        return cleaned.strip() or title.strip()

    def _parse_feed(self, feed_url: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        response = self.http_client.get(feed_url)
        if not response.ok:
            logger.warning("%s feed URL returned %s: %s", self.scraper_name, response.status_code, feed_url)
            return results

        feed = feedparser.parse(response.content)
        if getattr(feed, "bozo", False):
            logger.warning("%s feed parsing bozo flag set for %s", self.scraper_name, feed_url)

        for entry in getattr(feed, "entries", [])[: self.max_items]:
            title = getattr(entry, "title", "")
            description = getattr(entry, "summary", "")
            published = getattr(entry, "published", None)
            source_url = getattr(entry, "link", "")
            merged_text = f"{title} {description}"

            media_url = None
            media = getattr(entry, "media_content", None)
            if media and isinstance(media, list):
                media_url = media[0].get("url")

            results.append(
                {
                    "title": self._sanitize_title(title),
                    "year": title,
                    "type": self._extract_type(merged_text),
                    "platform": self.platform,
                    "release_date": published,
                    "overview": description,
                    "genres": self._extract_genres(merged_text),
                    "poster_image_url": media_url,
                    "backdrop_image_url": media_url,
                    "rating": None,
                    "trailer_url": None,
                    "source_url": source_url,
                }
            )
        return results

    def scrape(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        empty_sources: list[str] = []
        for feed_url in self._build_feed_urls():
            try:
                parsed_items = self._parse_feed(feed_url)
                if not parsed_items:
                    empty_sources.append(feed_url)
                results.extend(parsed_items)
            except Exception as exc:
                logger.exception("%s feed request failed (%s): %s", self.scraper_name, feed_url, exc)

        if not results:
            logger.warning("%s returned no entries. checked_sources=%s", self.scraper_name, empty_sources)
        else:
            logger.info("%s produced %s raw items", self.scraper_name, len(results))
        return results
