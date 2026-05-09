"""IMDb trending scrapers for movies and TV."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from utils.http_client import HTTPClient

logger = logging.getLogger(__name__)


def _imdb_genres(raw: Any) -> list[Any]:
    if raw is None:
        return []
    return raw if isinstance(raw, list) else [raw]


class IMDbTrendingScraper(BaseScraper):
    scraper_name = "imdb_trending"

    def __init__(self) -> None:
        self.http_client = HTTPClient()

    def _extract_from_embedded_json(self, soup: BeautifulSoup, media_type: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        scripts = soup.select("script[type='application/ld+json']")
        for script in scripts:
            content = script.string or script.get_text(strip=True)
            if not content:
                continue
            try:
                payload = json.loads(content)
            except json.JSONDecodeError:
                continue

            maybe_graph = payload.get("@graph") if isinstance(payload, dict) else None
            nodes = maybe_graph if isinstance(maybe_graph, list) else [payload]
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                name = node.get("name")
                url = node.get("url", "")
                if not name or not isinstance(name, str):
                    continue
                full_url = f"https://www.imdb.com{url}" if isinstance(url, str) and url.startswith("/") else url
                items.append(
                    {
                        "title": name.strip(),
                        "year": node.get("datePublished", ""),
                        "type": media_type,
                        "platform": "imdb_trending",
                        "release_date": node.get("datePublished"),
                        "published_raw": node.get("datePublished"),
                        "overview": node.get("description") or "IMDb trending title.",
                        "genres": _imdb_genres(node.get("genre")),
                        "poster_image_url": node.get("image"),
                        "backdrop_image_url": node.get("image"),
                        "rating": ((node.get("aggregateRating") or {}).get("ratingValue") if isinstance(node.get("aggregateRating"), dict) else None),
                        "trailer_url": None,
                        "source_url": full_url or "https://www.imdb.com/",
                    }
                )
        return items

    def _extract_from_dom(self, soup: BeautifulSoup, media_type: str, url: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        selectors = [
            "a.ipc-title-link-wrapper",
            "ul.ipc-metadata-list li a[href*='/title/']",
            "a[href*='/title/tt']",
        ]
        seen: set[str] = set()
        for selector in selectors:
            anchors = soup.select(selector)
            for anchor in anchors:
                title_text = anchor.get_text(" ", strip=True)
                clean_title = re.sub(r"^\d+\.\s*", "", title_text).strip()
                if not clean_title or len(clean_title) < 2:
                    continue
                href = anchor.get("href") or ""
                full_url = f"https://www.imdb.com{href}" if href.startswith("/") else href
                key = f"{clean_title.lower()}|{full_url}"
                if key in seen:
                    continue
                seen.add(key)
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
            if items:
                break
        return items

    def _scrape_chart(self, url: str, media_type: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        response = self.http_client.get(url)
        if not response.ok:
            logger.warning("%s %s returned status=%s", self.scraper_name, url, response.status_code)
            return items

        soup = BeautifulSoup(response.text, "lxml")
        json_items = self._extract_from_embedded_json(soup, media_type)
        dom_items = self._extract_from_dom(soup, media_type, url)
        combined = json_items + dom_items
        if not combined:
            logger.warning("%s extracted 0 items from %s", self.scraper_name, url)
        return combined[:120]

    def scrape(self) -> list[dict[str, Any]]:
        try:
            movie_items = self._scrape_chart("https://www.imdb.com/chart/moviemeter/", "movie")
            series_items = self._scrape_chart("https://www.imdb.com/chart/tvmeter/", "series")
            results = movie_items + series_items
            if not results:
                logger.warning("%s returned empty list for both chart endpoints", self.scraper_name)
            logger.info("%s produced %s items", self.scraper_name, len(results))
            return results
        except Exception as exc:
            logger.exception("%s failed: %s", self.scraper_name, exc)
            return []
