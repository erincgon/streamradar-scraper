"""Reusable RSS scraper helpers."""

from __future__ import annotations

import logging
import re
from html import unescape
from urllib.parse import urlparse
from urllib.parse import quote_plus
from typing import Any

import feedparser

from config import APP_CONFIG
from scrapers.base import BaseScraper
from utils.article_url import (
    is_valid_article_page_url,
    resolve_to_article_url,
    unwrap_redirect_wrapper,
)
from utils.attribution import canonical_article_url
from utils.http_client import HTTPClient

logger = logging.getLogger(__name__)


class GoogleNewsRSSScraper(BaseScraper):
    """
    Tek veri kaynağı: Google News **arama RSS** (`feed_url` + `fallback_queries`).
    İstenen kategori için sorguyu yaz → gelen başlıkları işle → `ContentItem` alanlarına dök → pipeline JSON’a yazar.
    """

    def __init__(
        self,
        scraper_name: str,
        query: str,
        platform: str,
        default_type: str,
        fallback_queries: list[str] | None = None,
        feed_urls: list[str] | None = None,
        include_keywords: list[str] | None = None,
        exclude_keywords: list[str] | None = None,
        trusted_domains: list[str] | None = None,
        max_items: int | None = None,
        release_signal_keywords: tuple[str, ...] | list[str] | None = None,
        additional_signal_keywords: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        self.scraper_name = scraper_name
        self.query = query
        self.fallback_queries = fallback_queries or []
        self.platform = platform
        self.default_type = default_type
        # Max RSS entries examined per URL; raw output is hard-capped at max_items_per_feed.
        self.max_items = max_items if max_items is not None else APP_CONFIG.max_items_per_feed
        self.http_client = HTTPClient()
        self._extra_feed_urls = feed_urls or []
        self.include_keywords = [word.lower() for word in (include_keywords or [])]
        self.exclude_keywords = [word.lower() for word in (exclude_keywords or [])]
        self.trusted_domains = [domain.lower() for domain in (trusted_domains or [])]
        self.release_signal_keywords = [w.lower() for w in (release_signal_keywords or ())]
        self.additional_signal_keywords = [w.lower() for w in (additional_signal_keywords or ())]
        self._article_resolve_cache: dict[str, str | None] = {}
        self._article_resolve_budget = 96
        self._article_resolve_budget_warned = False

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

    def _sanitize_overview(self, overview: str) -> str:
        text = re.sub(r"<[^>]+>", " ", unescape(overview or ""))
        return re.sub(r"\s+", " ", text).strip()

    def _extract_media_url(self, entry: Any, raw_summary: str) -> str | None:
        # 1) RSS media content blocks
        media = getattr(entry, "media_content", None)
        if media and isinstance(media, list):
            for media_item in media:
                candidate = media_item.get("url")
                if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
                    return candidate

        # 2) RSS media thumbnail blocks
        thumbnails = getattr(entry, "media_thumbnail", None)
        if thumbnails and isinstance(thumbnails, list):
            for media_item in thumbnails:
                candidate = media_item.get("url")
                if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
                    return candidate

        # 3) RSS links with enclosure relation
        links = getattr(entry, "links", None)
        if links and isinstance(links, list):
            for link in links:
                href = link.get("href")
                link_type = str(link.get("type", "")).lower()
                rel = str(link.get("rel", "")).lower()
                if isinstance(href, str) and href.startswith(("http://", "https://")):
                    if rel == "enclosure" and "image" in link_type:
                        return href

        # 4) image URL from summary HTML
        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw_summary or "", flags=re.I)
        if img_match:
            candidate = img_match.group(1).strip()
            if candidate.startswith("//"):
                candidate = f"https:{candidate}"
            if candidate.startswith(("http://", "https://")):
                return candidate

        # 5) data-src / srcset image URL from summary HTML
        attr_match = re.search(
            r'<img[^>]+(?:data-src|srcset)=["\']([^"\']+)["\']',
            raw_summary or "",
            flags=re.I,
        )
        if attr_match:
            candidate = attr_match.group(1).split(",")[0].strip().split(" ")[0]
            if candidate.startswith("//"):
                candidate = f"https:{candidate}"
            if candidate.startswith(("http://", "https://")):
                return candidate
        return None

    def _is_google_news_url(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return host == "news.google.com" or host.endswith(".news.google.com")

    def _normalize_href(self, href: str) -> str | None:
        h = href.strip()
        if h.startswith("//"):
            h = "https:" + h
        if h.startswith(("http://", "https://")):
            return h
        return None

    def _candidate_article_urls(self, entry: Any, raw_summary: str) -> list[str]:
        """Prefer in-summary anchors, then identifiers, enclosures, raw link, outlet feed root last."""
        found: list[str] = []

        for match in re.finditer(r'href=["\']([^"\']+)["\']', raw_summary or "", flags=re.I):
            norm = self._normalize_href(match.group(1))
            if norm:
                found.append(norm)

        entry_id = getattr(entry, "id", "") or getattr(entry, "guid", "")
        if isinstance(entry_id, str) and entry_id.strip().startswith("http"):
            n = self._normalize_href(entry_id.strip())
            if n:
                found.append(n)

        links = getattr(entry, "links", None)
        if links and isinstance(links, list):
            for link in links:
                if not isinstance(link, dict):
                    continue
                href = link.get("href")
                norm = self._normalize_href(href.strip()) if isinstance(href, str) and href.strip() else None
                if norm:
                    found.append(norm)

        elink = getattr(entry, "link", "")
        if isinstance(elink, str):
            norm = self._normalize_href(elink.strip())
            if norm:
                found.append(norm)

        source = getattr(entry, "source", None)
        if isinstance(source, dict):
            href = source.get("href")
            if isinstance(href, str):
                norm = self._normalize_href(href.strip())
                if norm:
                    found.append(norm)

        out: list[str] = []
        seen: set[str] = set()
        for candidate in found:
            if candidate not in seen:
                seen.add(candidate)
                out.append(candidate)
        return out

    def _resolve_article_cached(self, seed_url: str) -> str | None:
        if seed_url in self._article_resolve_cache:
            return self._article_resolve_cache[seed_url]
        if self._article_resolve_budget <= 0:
            if not self._article_resolve_budget_warned:
                logger.warning(
                    "%s article-resolve HTTP budget exhausted — remaining RSS rows skip URL resolve",
                    self.scraper_name,
                )
                self._article_resolve_budget_warned = True
            self._article_resolve_cache[seed_url] = None
            return None
        self._article_resolve_budget -= 1
        try:
            resolved = resolve_to_article_url(seed_url, self.http_client)
        except Exception as exc:
            logger.debug("%s article resolve failed for %s (%s)", self.scraper_name, seed_url, exc)
            resolved = None
        self._article_resolve_cache[seed_url] = resolved
        return resolved

    def _finalize_urls(self, entry: Any, description: str) -> tuple[str | None, str]:
        """
        Return (validated article_url or None, source_url kept non-empty for the pipeline).

        Applies redirect resolution once per RSS row when shallow candidates lack real paths.
        """
        candidates = self._candidate_article_urls(entry, description)
        article_val: str | None = None

        for cand in candidates:
            plain = unwrap_redirect_wrapper(cand.strip())
            canon = canonical_article_url(plain)
            if is_valid_article_page_url(canon):
                article_val = canon
                break

        if article_val is None:
            resolve_attempts = 0
            for cand in candidates:
                if resolve_attempts >= 4:
                    break
                if not cand.startswith(("http://", "https://")):
                    continue
                resolve_attempts += 1
                resolved = self._resolve_article_cached(cand)
                if resolved:
                    article_val = resolved
                    break

        source_val = ""
        if article_val:
            source_val = article_val
        else:
            for cand in candidates:
                cu = canonical_article_url(unwrap_redirect_wrapper(cand.strip()))
                if cu.startswith("https://") and not self._is_google_news_url(cu):
                    source_val = cu
                    break
            if not source_val:
                for cand in candidates:
                    cu = canonical_article_url(unwrap_redirect_wrapper(cand.strip()))
                    if cu.startswith("https://"):
                        source_val = cu
                        break
            if not source_val:
                el = getattr(entry, "link", "")
                if isinstance(el, str) and el.strip().startswith(("http://", "https://", "//")):
                    raw = self._normalize_href(el.strip()) or el.strip()
                    source_val = canonical_article_url(unwrap_redirect_wrapper(raw)) or raw

        return article_val, source_val.strip()

    def _domain_matches(self, source_url: str) -> bool:
        if not self.trusted_domains:
            return False
        lowered = (source_url or "").lower()
        return any(domain in lowered for domain in self.trusted_domains)

    def _is_relevant(self, title: str, overview: str, source_url: str) -> bool:
        merged = f"{title} {overview}".lower()
        if any(word in merged for word in self.exclude_keywords):
            return False
        if self.release_signal_keywords and not any(sig in merged for sig in self.release_signal_keywords):
            return False
        if self.additional_signal_keywords and not any(sig in merged for sig in self.additional_signal_keywords):
            return False
        if self._domain_matches(source_url):
            return True
        if not self.include_keywords:
            return True
        return any(word in merged for word in self.include_keywords)

    def _parse_feed(self, feed_url: str, *, max_raw_rows: int | None = None) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        response = self.http_client.get(feed_url)
        if not response.ok:
            logger.warning("%s feed URL returned %s: %s", self.scraper_name, response.status_code, feed_url)
            return results

        feed = feedparser.parse(response.content)
        if getattr(feed, "bozo", False):
            logger.warning("%s feed parsing bozo flag set for %s", self.scraper_name, feed_url)

        cap = APP_CONFIG.max_items_per_feed
        want = max_raw_rows if max_raw_rows is not None else min(self.max_items, cap)
        target = max(0, min(want, cap))
        if target <= 0:
            return results
        scan_budget = min(400, max(target * 25, target + 20))

        scanned = 0
        for entry in getattr(feed, "entries", []):
            scanned += 1
            if len(results) >= target or scanned > scan_budget:
                break
            title = getattr(entry, "title", "")
            description = getattr(entry, "summary", "")
            published = getattr(entry, "published", None)
            article_url, source_url = self._finalize_urls(entry, description)
            clean_overview = self._sanitize_overview(description)
            merged_text = f"{title} {clean_overview}"
            if not self._is_relevant(title, clean_overview, source_url):
                continue

            media_url = self._extract_media_url(entry, description)

            results.append(
                {
                    "title": self._sanitize_title(title),
                    "year": title,
                    "type": self._extract_type(merged_text),
                    "platform": self.platform,
                    "release_date": published,
                    "published_raw": published or None,
                    "overview": clean_overview,
                    "genres": self._extract_genres(merged_text),
                    "poster_image_url": media_url,
                    "backdrop_image_url": media_url,
                    "rating": None,
                    "trailer_url": None,
                    "article_url": article_url,
                    "source_url": source_url,
                }
            )
        return results

    def scrape(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        empty_sources: list[str] = []
        raw_cap = APP_CONFIG.max_items_per_feed
        self._article_resolve_cache.clear()
        self._article_resolve_budget_warned = False
        # Enough resolves for mostly-Google-RSS feeds (many rows need one GET to reach publisher URL).
        self._article_resolve_budget = min(150, max(40, raw_cap * 12))
        for feed_url in self._build_feed_urls():
            if len(results) >= raw_cap:
                break
            try:
                need = raw_cap - len(results)
                parsed_items = self._parse_feed(feed_url, max_raw_rows=need)
                if not parsed_items:
                    empty_sources.append(feed_url)
                results.extend(parsed_items)
            except Exception as exc:
                logger.exception("%s feed request failed (%s): %s", self.scraper_name, feed_url, exc)

        results = results[:raw_cap]
        if not results:
            logger.warning("%s returned no entries. checked_sources=%s", self.scraper_name, empty_sources)
        else:
            logger.info("%s produced %s raw items", self.scraper_name, len(results))
        return results


# Minimum one substring must appear in title + summary (streaming / platform new-release intent).
PLATFORM_STREAMING_RELEASE_SIGNAL_KEYWORDS: tuple[str, ...] = (
    "premiere",
    "premieres",
    "premiering",
    "season premiere",
    "series premiere",
    "release date",
    "releases on",
    "releasing on",
    "debuts",
    "debut",
    "new on ",
    "new to ",
    " arrives ",
    "arriving on",
    "arriving this",
    "coming to ",
    "starts streaming",
    "begins streaming",
    "begin streaming",
    "now streaming",
    "streaming on",
    "streaming this",
    "drop on",
    "drops on",
    "launches on",
    "launch on",
    "launching on",
    "due on",
    "due out",
    "slated for",
    "set for",
    "incoming",
    "exclusive release",
    "stream this",
    "streaming soon",
    "to stream",
    "this week",
    "this month",
    "added this week",
    "just added",
    "new episodes",
)

# Theatrical / box office new-release intent.
THEATRICAL_RELEASE_SIGNAL_KEYWORDS: tuple[str, ...] = (
    "theatrical",
    "theatrical release",
    "in theaters",
    "in theatres",
    "box office",
    "wide release",
    "limited release",
    "opening weekend",
    "opening day",
    "opening friday",
    "opens ",
    "opening ",
    "opens this week",
    "opens december",
    "opens january",
    "opens february",
    "opens march",
    "opens april",
    "opens may",
    "opens june",
    "opens july",
    "opens august",
    "opens september",
    "opens october",
    "opens november",
    "new movie",
    "new film",
    "coming to theaters",
    "coming to theatres",
    "cinema release",
    "theater release",
    "theatre release",
    "release this week",
    "release this month",
    "exclusive run",
    "film release",
    "movie release",
)

# Must ALSO match alongside PLATFORM_STREAMING_RELEASE_SIGNAL_KEYWORDS (attention / traction cues).
TRENDING_BURST_KEYWORDS: tuple[str, ...] = (
    " trending",
    "trending on",
    "trending now",
    "trended",
    " viral",
    "viral ",
    "viral hit",
    "breakout ",
    "breakout hit",
    "streaming charts",
    "top 10",
    "tops the chart",
    "number one",
    "no. 1",
    " #1",
    "#1 ",
    "#1.",
    "#1:",
    "#1?",
    "#1;",
    "most-watched",
    "most watched",
    "viewership record",
    "rating record",
    "smash hit",
    "buzzworthy",
    "cultural moment",
    "this week",
    "this month",
)


# Futures / calendars — items that imply the title has not dropped yet or a future date anchor.
UPCOMING_FUTURE_SIGNAL_KEYWORDS: tuple[str, ...] = (
    "upcoming ",
    " coming soon",
    "coming soon",
    "next week",
    "next month",
    "will premiere",
    "will debut",
    "will release",
    "will arrive",
    "will stream",
    "will launch",
    "set to premiere",
    "set to debut",
    "set to release",
    "set to arrive",
    "set to stream",
    "scheduled for",
    "slated ",
    "slated for",
    "due ",
    "due out",
    "premieres on",
    "premieres this",
    "premieres next",
    "premieres in ",
    "premieres december",
    "premieres january",
    "premieres february",
    "premieres march",
    "premieres april",
    "premieres may",
    "premieres june",
    "premieres july",
    "premieres august",
    "premieres september",
    "premieres october",
    "premieres november",
    "release date announced",
    "release date:",
    "release date ",
    "arrives ",
    "arrives on",
    "arriving ",
    "coming to ",
    "coming in ",
    "coming this",
    "coming next",
    "drops ",
    "drop on ",
    "push back",
    "pushed to",
    "pushed back",
    "delayed until",
    "delayed ",
    "arrives december",
    "arrives january",
    "arrives february",
    "season returns",
)
