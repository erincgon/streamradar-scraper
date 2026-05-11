"""cinema_releases.json — Box Office Mojo daily chart + Google News theatrical haberleri."""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any

from bs4 import BeautifulSoup, Tag

from config import APP_CONFIG
from scrapers.base import BaseScraper
from scrapers.rss_scraper import GoogleNewsRSSScraper, THEATRICAL_RELEASE_SIGNAL_KEYWORDS
from utils.http_client import HTTPClient
from utils.normalization import parse_release_date

logger = logging.getLogger(__name__)

_BOM_BASE = "https://www.boxofficemojo.com"
_BOM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
_IMDB_TT_RE = re.compile(r"/title/(tt\d+)")
_AMAZON_POSTER_RE = re.compile(r"https://m\.media-amazon\.com/images/M/[^\"']+")
_POSTER_RESIZE_RE = re.compile(r"\._V1_.*$")


class IMDbBoxOfficeScraper(BaseScraper):
    """Scrape Box Office Mojo daily chart for currently-in-theaters movies,
    then enrich each title with its IMDb page link and release date."""

    scraper_name = "imdb_box_office"

    def __init__(self) -> None:
        self.http_client = HTTPClient()

    def _bom_chart_urls(self) -> list[str]:
        """Date-agnostic daily/weekend charts first, then date-specific pages as fallback.

        BOM publishes data with a ~1-day lag, so relying solely on
        ``/date/YYYY-MM-DD/`` for "today" is fragile.  The ``/daily/chart/``
        and ``/weekend/chart/`` endpoints always reflect the latest available
        data regardless of the calendar date.
        """
        today = date.today()
        urls = [
            f"{_BOM_BASE}/daily/chart/",
            f"{_BOM_BASE}/weekend/chart/",
        ]
        urls.extend(
            f"{_BOM_BASE}/date/{(today - timedelta(days=d)).isoformat()}/"
            for d in range(7)
        )
        return urls

    def _parse_date_page(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        table = soup.select_one("table")
        if not table:
            return []

        rows = table.select("tr")
        items: list[dict[str, Any]] = []
        today = date.today()

        for row in rows[1:]:
            cells = row.select("td")
            if len(cells) < 10:
                continue
            release_cell = cells[2]
            link: Tag | None = release_cell.select_one("a[href*='/release/']")
            if not link:
                continue
            title = link.get_text(strip=True)
            if not title or len(title) < 2:
                continue

            href = link.get("href", "")
            bom_url = f"{_BOM_BASE}{href}" if href.startswith("/") else href
            bom_url = re.sub(r"\?.*$", "", bom_url).rstrip("/")

            days_text = cells[9].get_text(strip=True).replace(",", "") if len(cells) > 9 else ""
            release_date: str | None = None
            try:
                days_in_release = int(days_text)
                release_date = (today - timedelta(days=days_in_release - 1)).isoformat()
            except (ValueError, TypeError):
                pass

            theaters_text = cells[6].get_text(strip=True).replace(",", "") if len(cells) > 6 else ""
            theaters = 0
            try:
                theaters = int(theaters_text)
            except (ValueError, TypeError):
                pass

            distributor = cells[10].get_text(strip=True) if len(cells) > 10 else ""

            items.append({
                "title": title,
                "bom_url": bom_url,
                "release_date": release_date,
                "days_in_release": days_text,
                "theaters": theaters,
                "distributor": distributor,
            })

        return items

    @staticmethod
    def _upscale_amazon_poster(thumb_url: str) -> str:
        """Replace tiny BOM thumbnail sizing with a high-quality rendition."""
        return _POSTER_RESIZE_RE.sub("._V1_QL75_UX380_.jpg", thumb_url)

    def _enrich_from_release_page(self, bom_url: str) -> dict[str, Any]:
        """Fetch a BOM release page and extract IMDb title ID, release date, and poster."""
        result: dict[str, Any] = {
            "imdb_id": None,
            "release_date_precise": None,
            "mpaa": None,
            "poster_url": None,
        }
        try:
            resp = self.http_client.get(bom_url + "/", headers=_BOM_HEADERS)
            if not resp.ok:
                return result
            soup = BeautifulSoup(resp.text, "lxml")

            for a in soup.select("a[href*='imdb.com/title/']"):
                match = _IMDB_TT_RE.search(a.get("href", ""))
                if match:
                    result["imdb_id"] = match.group(1)
                    break

            for img in soup.select("img[src*='m.media-amazon.com/images/M/']"):
                src = img.get("src", "")
                if src:
                    result["poster_url"] = self._upscale_amazon_poster(src)
                    break

            spans = soup.select(".mojo-summary-values span")
            label = ""
            for span in spans:
                text = span.get_text(strip=True)
                if text == "Release Date":
                    label = "release_date"
                elif text == "MPAA":
                    label = "mpaa"
                elif label == "release_date" and text and text != "Release Date":
                    result["release_date_precise"] = text
                    label = ""
                elif label == "mpaa" and text and text != "MPAA":
                    result["mpaa"] = text
                    label = ""
                elif text not in {"Release Date", "MPAA", "Opening", "Distributor", "Running Time", "Genres", "IMDbPro"}:
                    label = ""
        except Exception as exc:
            logger.debug("%s release page enrichment failed for %s: %s", self.scraper_name, bom_url, exc)
        return result

    def scrape(self) -> list[dict[str, Any]]:
        cap = APP_CONFIG.max_items_per_feed
        try:
            raw_movies: list[dict[str, Any]] = []
            used_url = ""
            for url in self._bom_chart_urls():
                resp = self.http_client.get(url, headers=_BOM_HEADERS)
                if not resp.ok:
                    logger.debug("%s date page %s returned status=%s", self.scraper_name, url, resp.status_code)
                    continue
                raw_movies = self._parse_date_page(resp.text)
                if raw_movies:
                    used_url = url
                    break
                logger.debug("%s date page %s had no table data, trying earlier date", self.scraper_name, url)

            if not raw_movies:
                logger.warning("%s found 0 movies across all date pages", self.scraper_name)
                return []

            logger.info("%s found %s movies on %s", self.scraper_name, len(raw_movies), used_url)
            results: list[dict[str, Any]] = []

            for movie in raw_movies[:cap]:
                enrichment = self._enrich_from_release_page(movie["bom_url"])
                imdb_id = enrichment.get("imdb_id")

                if imdb_id:
                    source_url = f"https://www.imdb.com/title/{imdb_id}/"
                    article_url = source_url
                else:
                    source_url = movie["bom_url"]
                    article_url = movie["bom_url"]

                release_date = movie.get("release_date")
                if enrichment.get("release_date_precise"):
                    parsed = parse_release_date(enrichment["release_date_precise"])
                    if parsed:
                        release_date = parsed

                year = ""
                if release_date:
                    year_match = re.search(r"(20\d{2})", str(release_date))
                    if year_match:
                        year = year_match.group(1)

                theaters = movie.get("theaters", 0)
                distributor = movie.get("distributor", "")
                overview_parts = ["Movie currently playing in cinema theaters."]
                if distributor:
                    overview_parts.append(f"Distributed by {distributor}.")
                if theaters:
                    overview_parts.append(f"Showing in {theaters:,} theaters.")
                overview = " ".join(overview_parts)

                poster_url = enrichment.get("poster_url")

                results.append({
                    "title": movie["title"],
                    "year": year,
                    "type": "movie",
                    "platform": "cinema",
                    "release_date": release_date,
                    "published_raw": release_date,
                    "overview": overview,
                    "genres": [],
                    "poster_image_url": poster_url,
                    "backdrop_image_url": poster_url,
                    "rating": None,
                    "trailer_url": None,
                    "source_url": source_url,
                    "article_url": article_url,
                })

            logger.info("%s produced %s items", self.scraper_name, len(results))
            return results
        except Exception as exc:
            logger.exception("%s failed: %s", self.scraper_name, exc)
            return []


class CinemaReleasesScraper(GoogleNewsRSSScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="cinema_releases",
            query=(
                '("opening this week" OR "in theaters" OR "in theatres" OR '
                '"opening weekend" OR "box office" OR "wide release" OR '
                '"new movie" OR "new film")'
            ),
            platform="cinema",
            default_type="movie",
            fallback_queries=[
                "new movies theaters this weekend OR Friday opening films",
                "theatrical release date announced blockbuster",
                "limited release expands wide box office",
            ],
            feed_urls=[],
            release_signal_keywords=THEATRICAL_RELEASE_SIGNAL_KEYWORDS,
        )
