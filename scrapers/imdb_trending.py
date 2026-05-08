"""IMDb trending scrapers for movies and TV."""

from __future__ import annotations

import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from utils.http_client import HTTPClient

logger = logging.getLogger(__name__)


class IMDbTrendingScraper(BaseScraper):
    scraper_name = "imdb_trending"

    def __init__(self) -> None:
        self.http_client = HTTPClient()

    def _scrape_chart(self, url: str, media_type: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        response = self.http_client.get(url)
        if not response.ok:
            return items

        soup = BeautifulSoup(response.text, "lxml")
        anchors = soup.select("a.ipc-title-link-wrapper")
        for anchor in anchors[:120]:
            title_text = anchor.get_text(" ", strip=True)
            clean_title = re.sub(r"^\d+\.\s*", "", title_text)
            href = anchor.get("href") or ""
            full_url = f"https://www.imdb.com{href}" if href.startswith("/") else href
            items.append(
                {
                    "title": clean_title,
                    "year": clean_title,
                    "type": media_type,
                    "platform": "imdb_trending",
                    "release_date": None,
                    "overview": "IMDb trending title.",
                    "genres": [],
                    "poster_image_url": None,
                    "backdrop_image_url": None,
                    "rating": None,
                    "trailer_url": None,
                    "source_url": full_url or url,
                }
            )
        return items

    def scrape(self) -> list[dict[str, Any]]:
        try:
            movie_items = self._scrape_chart("https://www.imdb.com/chart/moviemeter/", "movie")
            series_items = self._scrape_chart("https://www.imdb.com/chart/tvmeter/", "series")
            results = movie_items + series_items
            logger.info("%s produced %s items", self.scraper_name, len(results))
            return results
        except Exception as exc:
            logger.exception("%s failed: %s", self.scraper_name, exc)
            return []
