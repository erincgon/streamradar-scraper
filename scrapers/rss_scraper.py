"""Reusable RSS scraper helpers."""

from __future__ import annotations

import logging
from typing import Any

import feedparser

from scrapers.base import BaseScraper
from utils.http_client import HTTPClient

logger = logging.getLogger(__name__)


class GoogleNewsRSSScraper(BaseScraper):
    """Scrape Google News RSS search results for release intelligence."""

    def __init__(
        self,
        scraper_name: str,
        query: str,
        platform: str,
        default_type: str,
        max_items: int = 120,
    ) -> None:
        self.scraper_name = scraper_name
        self.query = query
        self.platform = platform
        self.default_type = default_type
        self.max_items = max_items
        self.http_client = HTTPClient()

    @property
    def feed_url(self) -> str:
        return (
            "https://news.google.com/rss/search?"
            f"q={self.query}&hl=en-US&gl=US&ceid=US:en"
        )

    def scrape(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            response = self.http_client.get(self.feed_url)
            feed = feedparser.parse(response.content)
        except Exception as exc:
            logger.exception("%s feed request failed: %s", self.scraper_name, exc)
            return results

        for entry in feed.entries[: self.max_items]:
            title = getattr(entry, "title", "")
            description = getattr(entry, "summary", "")
            published = getattr(entry, "published", None)
            source_url = getattr(entry, "link", "")

            media_url = None
            media = getattr(entry, "media_content", None)
            if media and isinstance(media, list):
                media_url = media[0].get("url")

            results.append(
                {
                    "title": title,
                    "year": title,
                    "type": self.default_type,
                    "platform": self.platform,
                    "release_date": published,
                    "overview": description,
                    "genres": [],
                    "poster_image_url": media_url,
                    "backdrop_image_url": media_url,
                    "rating": None,
                    "trailer_url": None,
                    "source_url": source_url,
                }
            )

        logger.info("%s produced %s items", self.scraper_name, len(results))
        return results
