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


_AMZ_ENTERTAINMENT_RSS = "https://www.aboutamazon.com/rss/feed.rss?category=entertainment"


def _amazon_item_primes_article(entry: Any) -> bool:
    blob = (
        ((getattr(entry, "title", None) or "") + " "
         + unescape(getattr(entry, "summary", None) or "")
         + " " + unescape(getattr(entry, "link", None) or ""))
    ).lower()
    if "prime video" in blob:
        return True
    if "/prime-video" in blob or "-prime-video" in blob:
        return True
    return False


class AboutAmazonPrimeVideoRSSScraper(BaseScraper):
    """Source: About Amazon Entertainment RSS entries that reference Prime Video."""

    scraper_name = "aboutamazon_prime_rss"

    def __init__(self) -> None:
        self.http = HTTPClient()

    def scrape(self) -> list[dict[str, Any]]:
        r = self.http.get(_AMZ_ENTERTAINMENT_RSS, headers=_ACCEPT_LANG_EN)
        if r.status_code != 200:
            return []
        parsed = feedparser.parse(r.content)
        out: list[dict[str, Any]] = []
        for entry in parsed.entries:
            if not _amazon_item_primes_article(entry):
                continue
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue
            thumb = None
            md = entry.get("media_thumbnail")
            if md:
                thumb = md[0].get("url") if isinstance(md, list) else md.get("url")
            summary_text = (
                BeautifulSoup(unescape(entry.get("summary") or ""), "lxml").get_text(
                    separator=" ",
                    strip=True,
                )
            )
            if not summary_text:
                summary_text = title
            pub_hint = (
                getattr(entry, "published", None)
                or getattr(entry, "updated", None)
                or ""
            )
            out.append(
                {
                    "title": title,
                    "year": None,
                    "type": "series",
                    "platform": "prime_video",
                    "release_date": None,
                    "overview": summary_text[:2000],
                    "genres": [],
                    "poster_image_url": thumb,
                    "backdrop_image_url": None,
                    "rating": None,
                    "trailer_url": None,
                    "source_url": link.split("?", 1)[0],
                    "scraped_at": utc_now_iso(),
                    "article_url": link.split("?", 1)[0],
                    "content_type": "platform_release",
                    "published_raw": pub_hint,
                }
            )
            if len(out) >= _CAP:
                break
        return out


_WBD_FOCUS = re.compile(
    r"\bmax\b|\bhbo\b|hbomax|series\s+(premieres?|renew|returns)"
    r"|streaming\s+on\s+max|on\s+max\b|max\s+original",
    re.IGNORECASE,
)


class WBDPressMaxMediaReleasesScraper(BaseScraper):
    """Source: WBD press search HTML (US or other locale) filtered to Max/HBO streaming news."""

    scraper_name = "wbd_press_max"

    def __init__(self, locale_prefix: str = "us") -> None:
        self.locale_prefix = locale_prefix.strip("/") or "us"
        self.http = HTTPClient()

    def scrape(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for page in range(0, 4):
            if len(out) >= _CAP:
                break
            url = (
                f"https://press.wbd.com/{self.locale_prefix}/search"
                f"?q={self.locale_prefix}/search&type=media_release&page={page}"
            )
            r = self.http.get(url, headers=_ACCEPT_LANG_EN)
            if r.status_code != 200:
                logger.warning("WBD press page %s -> %s", page, r.status_code)
                break
            soup = BeautifulSoup(r.text, "lxml")
            articles = soup.select("article.m-item-content-row")
            for art in articles:
                if len(out) >= _CAP:
                    break
                ta = art.select_one(".m-item-content-row__title a")
                if not ta:
                    continue
                title = ta.get_text(strip=True)
                href = ta.get("href") or ""
                if not title or not href.startswith("/"):
                    continue
                sum_el = art.select_one(".m-item-content-row__summary")
                summary = ""
                if sum_el:
                    summary = sum_el.get_text(separator=" ", strip=True)
                date_parts = [
                    x.get_text(strip=True)
                    for x in art.select(".m-item-content-row__date")
                ]
                date_hint = next((x for x in date_parts if x), "")
                hay = f"{title} {summary} {href}"
                if not _WBD_FOCUS.search(hay):
                    continue
                full_url = urljoin("https://press.wbd.com", href)
                row_thumb = None
                img_el = art.select_one("img[src]")
                if img_el and img_el.get("src"):
                    row_thumb = img_el["src"].strip()
                    if row_thumb.startswith("//"):
                        row_thumb = "https:" + row_thumb
                out.append(
                    {
                        "title": title,
                        "year": None,
                        "type": "series",
                        "platform": "hbo_max",
                        "release_date": None,
                        "overview": summary or title,
                        "genres": [],
                        "poster_image_url": row_thumb,
                        "backdrop_image_url": None,
                        "rating": None,
                        "trailer_url": None,
                        "source_url": full_url,
                        "scraped_at": utc_now_iso(),
                        "article_url": full_url,
                        "content_type": "platform_release",
                        "published_raw": date_hint,
                    }
                )
        return out[:_CAP]
