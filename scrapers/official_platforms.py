"""Official platform “new releases” scrapers (Netflix About, Disney+ storefront, etc.).

Raw rows are normalized via `ContentItem.from_raw` to match existing JSON (`title`,
`poster_image_url`, `article_url`, …). Prefer English storefront copy via `Accept-Language`
and EN/US source URLs where supported.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from html import unescape
from typing import Any
from urllib.parse import urljoin

import feedparser
from bs4 import BeautifulSoup

from config import APP_CONFIG
from scrapers.base import BaseScraper
from utils.http_client import HTTPClient
from utils.next_data import parse_next_data_json
from utils.normalization import utc_now_iso

logger = logging.getLogger(__name__)

# Prefer English storefront copy from marketing HTML.
_ACCEPT_LANG_EN = {"Accept-Language": "en-US,en;q=0.9"}

_CAP = APP_CONFIG.max_items_per_feed

_DISNEY_UUID_PATH = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)


def _iso_date_from_epoch_ms(ms: int | float | None) -> str | None:
    if ms is None:
        return None
    try:
        sec = float(ms) / 1000.0
        dt = datetime.fromtimestamp(sec, tz=UTC)
        return dt.strftime("%Y-%m-%d")
    except (OverflowError, OSError, TypeError, ValueError):
        return None


def _disney_bamgrid_compose_url(image_key: str, width: int = 440) -> str | None:
    """
    Build the same `variant/disney/<id>/compose` URL the storefront HTML uses.

    UUID `ripcutId` values must stay hyphenated and lower-case; stripping dashes yields 404.
    Some marketing assets use a 64-char uppercase hex segment instead.
    """
    key = (image_key or "").strip()
    if not key:
        return None
    if _DISNEY_UUID_PATH.match(key):
        segment = key.lower()
    elif re.fullmatch(r"[0-9A-Fa-f]{64}", key):
        segment = key.upper()
    elif re.fullmatch(r"[0-9A-Fa-f]{32}", key):
        k = key.lower()
        segment = f"{k[:8]}-{k[8:12]}-{k[12:16]}-{k[16:20]}-{k[20:32]}"
    else:
        segment = key.lower()

    return (
        "https://disney.images.edge.bamgrid.com/ripcut-delivery/v2/variant/disney/"
        f"{segment}/compose?format=webp&width={width}"
    )


def _pick_image_variants_ripcut(image_variants: dict[str, Any]) -> str | None:
    """Return first ripcutId / imageId UUID string under `imageVariants`."""
    if not isinstance(image_variants, dict):
        return None
    found: list[str] = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("ripcutId", "imageId") and isinstance(v, str) and v.strip():
                    found.append(v.strip())
                    return
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(image_variants)
    return found[0] if found else None


class NetflixAboutNewWatchScraper(BaseScraper):
    """https://about.netflix.com/{locale}/new-to-watch embedded `__NEXT_DATA__`."""

    scraper_name = "netflix_about"

    def __init__(self, locale: str = "en") -> None:
        self.locale = locale
        self.http = HTTPClient()

    def scrape(self) -> list[dict[str, Any]]:
        raw_out: list[dict[str, Any]] = []
        base = f"https://about.netflix.com/{self.locale}/new-to-watch"
        first_url = f"{base}?page=1"
        r = self.http.get(first_url, headers=_ACCEPT_LANG_EN)
        if r.status_code != 200 or not r.text:
            logger.warning("Netflix About: bad first response %s", r.status_code)
            return []
        payload = parse_next_data_json(r.text)
        if not payload:
            return []
        try:
            pdata = payload["props"]["pageProps"]["data"]
            total_pages = int(pdata.get("totalPages") or 1)
            batch = pdata.get("data") or []
        except (KeyError, TypeError, ValueError):
            return []

        def consume(rows: list[Any]) -> None:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                vid = row.get("videoID")
                title = (row.get("title1") or row.get("title2") or "").strip()
                if vid is None or not title:
                    continue
                rd = _iso_date_from_epoch_ms(row.get("startTime"))
                img = row.get("image")
                if isinstance(img, str) and img.startswith("//"):
                    img = "https:" + img
                watch = f"https://www.netflix.com/watch/{vid}"
                raw_out.append(
                    {
                        "title": title,
                        "year": int(rd[:4]) if rd and len(rd) >= 4 else None,
                        "type": "movie",
                        "platform": "netflix",
                        "release_date": rd,
                        "overview": f"Featured on Netflix new-to-watch: {title}.",
                        "genres": [],
                        "poster_image_url": img if isinstance(img, str) else None,
                        "backdrop_image_url": None,
                        "rating": None,
                        "trailer_url": None,
                        "source_url": watch,
                        "scraped_at": utc_now_iso(),
                        "article_url": watch,
                        "content_type": "platform_release",
                        "published_raw": rd,
                    }
                )

        consume(batch)

        max_pages = min(total_pages, 5)
        for page in range(2, max_pages + 1):
            if len(raw_out) >= _CAP:
                break
            rr = self.http.get(f"{base}?page={page}", headers=_ACCEPT_LANG_EN)
            if rr.status_code != 200:
                break
            pp = parse_next_data_json(rr.text)
            if not pp:
                continue
            try:
                rows = pp["props"]["pageProps"]["data"]["data"] or []
            except (KeyError, TypeError):
                continue
            consume(rows)

        seen: set[str] = set()
        uniq: list[dict[str, Any]] = []
        for item in raw_out:
            k = item["title"].lower()
            if k in seen:
                continue
            seen.add(k)
            uniq.append(item)

        return uniq[:_CAP]


class DisneyOnDisneyPlusRecentScraper(BaseScraper):
    """https://ondisneyplus.disney.com/recent-releases (Stitch ImageCard payloads)."""

    scraper_name = "disney_recent"

    ORIGIN = "https://ondisneyplus.disney.com"
    LIST_URL = f"{ORIGIN}/recent-releases"

    def __init__(self) -> None:
        self.http = HTTPClient()

    def scrape(self) -> list[dict[str, Any]]:
        r = self.http.get(self.LIST_URL, headers=_ACCEPT_LANG_EN)
        if r.status_code != 200:
            return []
        payload = parse_next_data_json(r.text)
        if not payload:
            return []
        try:
            stitch = payload["props"]["pageProps"]["stitchDocument"]
        except (KeyError, TypeError):
            return []

        cards: list[dict[str, Any]] = []

        def walk(obj: Any) -> None:
            if isinstance(obj, dict):
                if obj.get("_type") == "ImageCard":
                    cards.append(obj)
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v)

        walk(stitch)

        raw_out: list[dict[str, Any]] = []
        for c in cards:
            title = (c.get("title") or "").strip()
            path = (c.get("url") or "").strip()
            if not title or not path.startswith("/whats-on/"):
                continue
            variants = c.get("imageVariants")
            rid = (
                _pick_image_variants_ripcut(variants)
                if isinstance(variants, dict)
                else None
            )
            poster = _disney_bamgrid_compose_url(rid) if rid else None
            is_episode = bool(c.get("isEpisode"))
            # Entity URLs from Stitch payload can 404 publicly; keep a stable landing URL.
            card_id = (c.get("_id") or "").strip()
            detail = f"{self.LIST_URL}#{card_id}" if card_id else self.LIST_URL
            raw_out.append(
                {
                    "title": title,
                    "year": None,
                    "type": "series" if is_episode else "movie",
                    "platform": "disney_plus",
                    "release_date": None,
                    "overview": f"Disney+ recent release: {title}.",
                    "genres": [],
                    "poster_image_url": poster,
                    "backdrop_image_url": None,
                    "rating": None,
                    "trailer_url": None,
                    "source_url": detail,
                    "scraped_at": utc_now_iso(),
                    "article_url": self.LIST_URL,
                    "content_type": "platform_release",
                }
            )

        seen: set[str] = set()
        uniq: list[dict[str, Any]] = []
        for item in raw_out:
            key = item["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            uniq.append(item)

        return uniq[:_CAP]


_JUSTWATCH_GQL = "https://apis.justwatch.com/graphql"
_JUSTWATCH_QUERY = """query($country: Country!, $language: Language!, $first: Int!, $filter: TitleFilter) {
  popularTitles(country: $country, first: $first, sortBy: POPULAR, filter: $filter, language: $language) {
    edges {
      node {
        id
        objectType
        content(country: $country, language: $language) {
          title
          shortDescription
          fullPath
          posterUrl
          originalReleaseYear
          genres { shortName }
        }
      }
    }
  }
}"""

_JW_GENRE_MAP: dict[str, str] = {
    "act": "Action", "adv": "Adventure", "ani": "Animation", "cmy": "Comedy",
    "crm": "Crime", "doc": "Documentary", "drm": "Drama", "fml": "Family",
    "fnt": "Fantasy", "hst": "History", "hrr": "Horror", "msc": "Music",
    "mys": "Mystery", "rma": "Romance", "scf": "Sci-Fi", "trl": "Thriller",
    "war": "War", "wsn": "Western", "eur": "European", "rly": "Reality",
    "spt": "Sport",
}


_TOP_PER_TYPE = 10  # top 10 movies + top 10 series = 20 per platform


class _JustWatchPlatformScraper(BaseScraper):
    """Fetch top popular movies and series for a platform via JustWatch GraphQL."""

    def __init__(
        self,
        *,
        scraper_name: str,
        platform_key: str,
        jw_packages: list[str],
    ) -> None:
        self.scraper_name = scraper_name
        self._platform_key = platform_key
        self._jw_packages = jw_packages
        self.http = HTTPClient()

    @staticmethod
    def _poster_url(raw: str) -> str | None:
        if not raw:
            return None
        return (
            f"https://images.justwatch.com{raw}"
            .replace("{profile}", "s592")
            .replace("{format}", "webp")
        )

    def _fetch_edges(self, object_type: str, limit: int) -> list[dict[str, Any]]:
        import requests as _req

        try:
            resp = _req.post(
                _JUSTWATCH_GQL,
                json={
                    "query": _JUSTWATCH_QUERY,
                    "variables": {
                        "country": "US",
                        "language": "en",
                        "first": limit,
                        "filter": {
                            "packages": self._jw_packages,
                            "objectTypes": [object_type],
                        },
                    },
                },
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Content-Type": "application/json",
                },
                timeout=20,
            )
        except Exception as exc:
            logger.exception(
                "%s JustWatch request failed for %s: %s",
                self.scraper_name,
                object_type,
                exc,
            )
            return []

        if resp.status_code != 200:
            logger.warning(
                "%s JustWatch returned %s for %s",
                self.scraper_name,
                resp.status_code,
                object_type,
            )
            return []

        try:
            data = resp.json()
        except Exception:
            logger.warning("%s could not parse JustWatch JSON for %s", self.scraper_name, object_type)
            return []

        if "errors" in data:
            logger.warning(
                "%s JustWatch errors (%s): %s",
                self.scraper_name,
                object_type,
                data["errors"][0].get("message", ""),
            )
            return []

        return data.get("data", {}).get("popularTitles", {}).get("edges", []) or []

    def _edge_to_item(self, edge: dict[str, Any], *, media_type: str) -> dict[str, Any] | None:
        node = edge.get("node", {})
        content = node.get("content", {})
        title = (content.get("title") or "").strip()
        if not title:
            return None

        year = content.get("originalReleaseYear")
        full_path = content.get("fullPath", "")
        jw_url = f"https://www.justwatch.com{full_path}" if full_path else ""
        poster = self._poster_url(content.get("posterUrl", ""))
        desc = content.get("shortDescription") or ""
        genres_raw = content.get("genres") or []
        genres = [
            _JW_GENRE_MAP.get(g.get("shortName", ""), g.get("shortName", ""))
            for g in genres_raw
            if g.get("shortName")
        ]

        platform_label = self._platform_key.replace("_", " ").title()
        streaming_prefix = f"Top {media_type} on {platform_label}."
        overview = f"{streaming_prefix} {desc}" if desc else streaming_prefix
        year_str = str(year) if year else None

        return {
            "title": title,
            "year": year,
            "type": media_type,
            "platform": self._platform_key,
            "release_date": year_str,
            "overview": overview,
            "genres": genres,
            "poster_image_url": poster,
            "backdrop_image_url": poster,
            "rating": None,
            "trailer_url": None,
            "source_url": jw_url,
            "scraped_at": utc_now_iso(),
            "article_url": jw_url,
            "content_type": "platform_release",
            "published_raw": year_str,
        }

    def scrape(self) -> list[dict[str, Any]]:
        """Return top 10 movies followed by top 10 series (up to 20 items)."""
        out: list[dict[str, Any]] = []
        seen: set[str] = set()

        for object_type, media_type in (("MOVIE", "movie"), ("SHOW", "series")):
            edges = self._fetch_edges(object_type, _TOP_PER_TYPE)
            for edge in edges:
                if len([i for i in out if i["type"] == media_type]) >= _TOP_PER_TYPE:
                    break
                item = self._edge_to_item(edge, media_type=media_type)
                if not item:
                    continue
                key = item["title"].lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(item)

        logger.info(
            "%s produced %s items via JustWatch (movies=%s series=%s)",
            self.scraper_name,
            len(out),
            sum(1 for i in out if i["type"] == "movie"),
            sum(1 for i in out if i["type"] == "series"),
        )
        return out[:_CAP]


class JustWatchNetflixScraper(_JustWatchPlatformScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="justwatch_netflix",
            platform_key="netflix",
            jw_packages=["nfx"],
        )


class JustWatchDisneyPlusScraper(_JustWatchPlatformScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="justwatch_disney_plus",
            platform_key="disney_plus",
            jw_packages=["dnp", "disneyplus"],
        )


class JustWatchPrimeVideoScraper(_JustWatchPlatformScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="justwatch_prime_video",
            platform_key="prime_video",
            jw_packages=["amazonprime"],
        )


class JustWatchMaxScraper(_JustWatchPlatformScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="justwatch_max",
            platform_key="hbo_max",
            # `mxx` is the current US Max catalog; legacy `hbm` returns a stale subset.
            jw_packages=["mxx"],
        )
