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
_JUSTWATCH_QUERY = """query($country: Country!, $language: Language!, $first: Int!, $filter: TitleFilter, $sortBy: PopularTitlesSorting!) {
  popularTitles(country: $country, first: $first, sortBy: $sortBy, filter: $filter, language: $language) {
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

_JUSTWATCH_SEARCH = """query($country: Country!, $language: Language!, $searchQuery: String!) {
  searchTitles(country: $country, first: 3, filter: {searchQuery: $searchQuery}, language: $language, source: "SEARCH") {
    edges {
      node {
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
_JW_COUNTRY = "TR"  # charts for Turkish StreamRadar audience
_JW_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
}


def _jw_poster_url(raw: str | None) -> str | None:
    if not raw:
        return None
    return (
        f"https://images.justwatch.com{raw}"
        .replace("{profile}", "s592")
        .replace("{format}", "webp")
    )


def _jw_genres(genres_raw: list[Any] | None) -> list[str]:
    return [
        _JW_GENRE_MAP.get(g.get("shortName", ""), g.get("shortName", ""))
        for g in (genres_raw or [])
        if isinstance(g, dict) and g.get("shortName")
    ]


def _jw_post(query: str, variables: dict[str, Any]) -> dict[str, Any] | None:
    import requests as _req

    try:
        resp = _req.post(
            _JUSTWATCH_GQL,
            json={"query": query, "variables": variables},
            headers=_JW_HEADERS,
            timeout=20,
        )
    except Exception as exc:
        logger.warning("JustWatch request failed: %s", exc)
        return None
    if resp.status_code != 200:
        logger.warning("JustWatch HTTP %s", resp.status_code)
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    if data.get("errors"):
        logger.warning("JustWatch GraphQL error: %s", data["errors"][0].get("message", ""))
        return None
    return data.get("data")


def _jw_lookup_title(title: str, *, prefer_type: str) -> dict[str, Any] | None:
    """Resolve poster/year/overview for a chart title via JustWatch search."""
    data = _jw_post(
        _JUSTWATCH_SEARCH,
        {"country": _JW_COUNTRY, "language": "en", "searchQuery": title},
    )
    if not data:
        return None
    edges = (data.get("searchTitles") or {}).get("edges") or []
    want = "SHOW" if prefer_type == "series" else "MOVIE"
    ordered = sorted(
        edges,
        key=lambda e: 0 if (e.get("node") or {}).get("objectType") == want else 1,
    )
    for edge in ordered:
        content = (edge.get("node") or {}).get("content") or {}
        if content.get("title"):
            return content
    return None


_SEASON_SUFFIX_RE = re.compile(
    r"(:\s*)?(Season\s+\d+|Limited Series|Series)\s*$",
    re.I,
)
_RANK_PREFIX_RE = re.compile(r"^\d+\s+")


def _clean_chart_title(raw: str) -> str:
    title = _RANK_PREFIX_RE.sub("", (raw or "").strip())
    title = _SEASON_SUFFIX_RE.sub("", title).strip(" :-")
    return title


class NetflixTudumTop10Scraper(BaseScraper):
    """Official Netflix Tudum Top 10 (Turkey) — movies + TV."""

    scraper_name = "netflix_tudum_top10"
    FILMS_URL = "https://www.netflix.com/tudum/top10/turkey"
    TV_URL = "https://www.netflix.com/tudum/top10/turkey/tv"

    def _parse_table(self, url: str) -> list[str]:
        import requests as _req

        try:
            r = _req.get(url, headers={**_JW_HEADERS, **_ACCEPT_LANG_EN}, timeout=30)
        except Exception as exc:
            logger.warning("Netflix Tudum request failed for %s: %s", url, exc)
            return []
        if r.status_code != 200 or not r.text:
            logger.warning("Netflix Tudum bad response %s for %s", r.status_code, url)
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        titles: list[str] = []
        seen: set[str] = set()
        for row in soup.select("table tr"):
            cells = row.select("td")
            if not cells:
                continue
            cleaned = _clean_chart_title(cells[0].get_text(" ", strip=True))
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            titles.append(cleaned)
            if len(titles) >= _TOP_PER_TYPE:
                break
        return titles

    def _build_item(self, title: str, *, media_type: str, rank: int, source_url: str) -> dict[str, Any]:
        meta = _jw_lookup_title(title, prefer_type=media_type) or {}
        year = meta.get("originalReleaseYear")
        poster = _jw_poster_url(meta.get("posterUrl"))
        full_path = meta.get("fullPath") or ""
        jw_url = f"https://www.justwatch.com{full_path}" if full_path else source_url
        desc = meta.get("shortDescription") or ""
        overview = (
            f"Netflix Turkey Top {rank} {media_type}. {desc}".strip()
            if desc
            else f"Netflix Turkey Top {rank} {media_type}."
        )
        year_str = str(year) if year else None
        return {
            "title": title,
            "year": year,
            "type": media_type,
            "platform": "netflix",
            "release_date": year_str,
            "overview": overview,
            "genres": _jw_genres(meta.get("genres")),
            "poster_image_url": poster,
            "backdrop_image_url": poster,
            "rating": None,
            "trailer_url": None,
            "source_url": jw_url,
            "scraped_at": utc_now_iso(),
            # Unique per title so URL-based dedupe cannot collapse the chart.
            "article_url": jw_url if full_path else f"{source_url}#{rank}-{media_type}",
            "content_type": "platform_release",
            "published_raw": year_str,
        }

    def scrape(self) -> list[dict[str, Any]]:
        from concurrent.futures import ThreadPoolExecutor

        films = self._parse_table(self.FILMS_URL)
        shows = self._parse_table(self.TV_URL)
        # If Turkey TV chart repeats a show across seasons, top up from global English list.
        if len(shows) < _TOP_PER_TYPE:
            for title in self._parse_table("https://www.netflix.com/tudum/top10/tv"):
                if title.lower() in {s.lower() for s in shows}:
                    continue
                shows.append(title)
                if len(shows) >= _TOP_PER_TYPE:
                    break

        jobs: list[tuple[str, str, int, str]] = []
        for i, title in enumerate(films[:_TOP_PER_TYPE], start=1):
            jobs.append((title, "movie", i, self.FILMS_URL))
        for i, title in enumerate(shows[:_TOP_PER_TYPE], start=1):
            jobs.append((title, "series", i, self.TV_URL))

        out: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [
                pool.submit(self._build_item, title, media_type=media_type, rank=rank, source_url=src)
                for title, media_type, rank, src in jobs
            ]
            for fut in futures:
                out.append(fut.result())

        logger.info(
            "%s produced %s items (movies=%s series=%s)",
            self.scraper_name,
            len(out),
            sum(1 for i in out if i["type"] == "movie"),
            sum(1 for i in out if i["type"] == "series"),
        )
        return out[:_CAP]


class _JustWatchPlatformScraper(BaseScraper):
    """Daily trending top titles for a platform via JustWatch (Turkey)."""

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

    def _fetch_edges(self, object_type: str, limit: int) -> list[dict[str, Any]]:
        data = _jw_post(
            _JUSTWATCH_QUERY,
            {
                "country": _JW_COUNTRY,
                "language": "en",
                "first": limit,
                "sortBy": "TRENDING",
                "filter": {
                    "packages": self._jw_packages,
                    "objectTypes": [object_type],
                },
            },
        )
        if not data:
            return []
        return (data.get("popularTitles") or {}).get("edges") or []

    def _edge_to_item(self, edge: dict[str, Any], *, media_type: str, rank: int) -> dict[str, Any] | None:
        content = (edge.get("node") or {}).get("content") or {}
        title = (content.get("title") or "").strip()
        if not title:
            return None

        year = content.get("originalReleaseYear")
        full_path = content.get("fullPath") or ""
        jw_url = f"https://www.justwatch.com{full_path}" if full_path else ""
        poster = _jw_poster_url(content.get("posterUrl"))
        desc = content.get("shortDescription") or ""
        platform_label = self._platform_key.replace("_", " ").title()
        streaming_prefix = f"Top {rank} trending {media_type} on {platform_label} (TR)."
        overview = f"{streaming_prefix} {desc}" if desc else streaming_prefix
        year_str = str(year) if year else None

        return {
            "title": title,
            "year": year,
            "type": media_type,
            "platform": self._platform_key,
            "release_date": year_str,
            "overview": overview,
            "genres": _jw_genres(content.get("genres")),
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
        out: list[dict[str, Any]] = []
        seen: set[str] = set()

        for object_type, media_type in (("MOVIE", "movie"), ("SHOW", "series")):
            edges = self._fetch_edges(object_type, _TOP_PER_TYPE + 5)
            rank = 0
            for edge in edges:
                if rank >= _TOP_PER_TYPE:
                    break
                item = self._edge_to_item(edge, media_type=media_type, rank=rank + 1)
                if not item:
                    continue
                key = item["title"].lower()
                if key in seen:
                    continue
                seen.add(key)
                rank += 1
                out.append(item)

        logger.info(
            "%s produced %s items via JustWatch TRENDING TR (movies=%s series=%s)",
            self.scraper_name,
            len(out),
            sum(1 for i in out if i["type"] == "movie"),
            sum(1 for i in out if i["type"] == "series"),
        )
        return out[:_CAP]


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
            jw_packages=["mxx"],
        )
