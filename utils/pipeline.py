"""Scraping pipeline orchestration."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from config import APP_CONFIG, OUTPUT_DIR
from scrapers.base import ContentItem
from utils.fallback_data import fallback_for_feed
from utils.image_utils import (
    extract_image_from_article,
    normalize_rss_thumbnail_url,
    validate_image_url,
)
from utils.json_utils import validate_item_schema, write_json
from utils.http_client import HTTPClient
from utils.article_url import is_valid_article_page_url
from utils.normalization import (
    cross_platform_key,
    dedupe_key_parts,
    looks_entertainment_related,
    normalized_url_signature,
)

logger = logging.getLogger(__name__)

_GENERIC_BAD_TITLES = {
    "breaking news",
    "news",
    "update",
    "latest updates",
}

_CLICKBAIT_HINTS = ("you won't believe", "shocking", "insane", "must see", "viral hack")


def _quality_score(item: dict[str, Any]) -> int:
    score = 0
    domain = str(item.get("source_domain", "")).lower()
    if any(k in domain for k in ("netflix.com", "disney", "primevideo.com", "max.com", "imdb.com", "variety.com")):
        score += 3
    if item.get("poster_image_url"):
        score += 2
    if item.get("published_at"):
        score += 2
    if item.get("article_url"):
        score += 2
    text = f"{item.get('title', '')} {item.get('overview', '')}".lower()
    if looks_entertainment_related(item.get("title", ""), item.get("overview", "")):
        score += 2
    if any(k in text for k in _CLICKBAIT_HINTS):
        score -= 3
    if item.get("title", "").strip().lower() in _GENERIC_BAD_TITLES:
        score -= 3
    if len(item.get("title", "").strip()) < 8:
        score -= 4
    return score


def _sort_key(item: dict[str, Any]) -> tuple[int, str]:
    release_date = item.get("release_date")
    if release_date:
        try:
            ordinal = date.fromisoformat(release_date).toordinal()
            return (ordinal, item.get("title", ""))
        except ValueError:
            pass
    return (0, item.get("title", ""))


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        key = dedupe_key_parts(
            title=item.get("title", ""),
            year=item.get("year"),
            media_type=item.get("type", ""),
            source_url=item.get("source_url", ""),
            article_url=item.get("article_url"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def process_raw_items(
    raw_items: list[dict[str, Any]],
    *,
    feed_name: str | None = None,
    validate_images: bool = True,
) -> list[dict[str, Any]]:
    raw_cap = APP_CONFIG.max_items_per_feed
    raw_items = raw_items[:raw_cap]
    http_client = HTTPClient()
    processed: list[dict[str, Any]] = []
    enrichment_cache: dict[str, str | None] = {}
    enrichment_attempts = 0
    max_enrichment_attempts = min(60, APP_CONFIG.max_items_per_feed * 3)
    for raw in raw_items:
        item = ContentItem.from_raw(raw, feed_name=feed_name).to_dict()
        if not item["source_url"]:
            logger.debug("Skipping item due to missing source_url: %s", raw)
            continue
        if item["title"].lower() in {"unknown title", "home", "video"}:
            logger.debug("Skipping low-quality title item: %s", item["title"])
            continue
        title_clean = item["title"].strip().lower()
        if len(item["title"].strip()) < 8 or title_clean in _GENERIC_BAD_TITLES:
            logger.debug("Skipping generic/short title: %s", item["title"])
            continue
        if not looks_entertainment_related(item.get("title", ""), item.get("overview", "")):
            logger.debug("Skipping non-entertainment row: %s", item.get("title"))
            continue

        for img_key in ("poster_image_url", "backdrop_image_url"):
            u = item.get(img_key)
            if isinstance(u, str) and u.startswith("https://"):
                item[img_key] = normalize_rss_thumbnail_url(u) or u

        if validate_images:
            item["poster_image_url"] = validate_image_url(item["poster_image_url"], http_client)
            item["backdrop_image_url"] = validate_image_url(item["backdrop_image_url"], http_client)
            if (
                not item["poster_image_url"]
                and enrichment_attempts < max_enrichment_attempts
                and (item.get("article_url") or item["source_url"])
            ):
                source_url = item.get("article_url") or item["source_url"]
                if source_url not in enrichment_cache:
                    enrichment_cache[source_url] = extract_image_from_article(source_url, http_client)
                    enrichment_attempts += 1
                enriched = enrichment_cache[source_url]
                if enriched:
                    item["poster_image_url"] = enriched
                    item["backdrop_image_url"] = item["backdrop_image_url"] or enriched

        if item.get("poster_image_url") and not item.get("backdrop_image_url"):
            item["backdrop_image_url"] = item["poster_image_url"]
        if not item.get("article_url"):
            item["article_url"] = item["source_url"]
        if (
            item.get("source_url")
            and is_valid_article_page_url(str(item["source_url"]))
            and not is_valid_article_page_url(str(item.get("article_url") or ""))
        ):
            item["article_url"] = item["source_url"]
        # Discovery/news feeds must point to a concrete article page (not homepage/root).
        # The upcoming feed uses Google News RSS where URL resolution often fails;
        # content value comes from the title + overview, not the link target.
        if feed_name in {"trending", "cinema_releases"}:
            article_candidate = str(item.get("article_url") or "").strip()
            source_candidate = str(item.get("source_url") or "").strip()
            if not (
                is_valid_article_page_url(article_candidate)
                or is_valid_article_page_url(source_candidate)
            ):
                logger.debug(
                    "Skipping row without valid article page URL feed=%s title=%s article=%s source=%s",
                    feed_name,
                    item.get("title"),
                    article_candidate,
                    source_candidate,
                )
                continue
        if _quality_score(item) < 3:
            logger.debug("Skipping low-quality row score<3: %s", item.get("title"))
            continue
        if validate_item_schema(item):
            processed.append(item)
        else:
            logger.debug("Schema validation failed for item title=%s", item.get("title"))

    deduped = _dedupe(processed)
    deduped.sort(key=_sort_key, reverse=True)
    return deduped[: APP_CONFIG.max_items_per_feed]


def run_feed(feed_name: str, scraper_objects: list[Any]) -> list[dict[str, Any]]:
    logger.info("Running feed '%s' with %s scraper(s)", feed_name, len(scraper_objects))
    aggregate_raw: list[dict[str, Any]] = []
    scraper_stats: list[str] = []
    for scraper in scraper_objects:
        try:
            scraped = scraper.scrape()
            aggregate_raw.extend(scraped)
            scraper_stats.append(f"{scraper.scraper_name}={len(scraped)}")
        except Exception as exc:
            logger.exception("Scraper %s failed: %s", scraper.scraper_name, exc)
            scraper_stats.append(f"{scraper.scraper_name}=error")
            continue

    aggregate_raw = aggregate_raw[: APP_CONFIG.max_items_per_feed]
    payload = process_raw_items(aggregate_raw, feed_name=feed_name, validate_images=True)
    if not payload:
        logger.warning(
            "Feed '%s' was empty after normalization. scraper_stats=%s raw_count=%s",
            feed_name,
            ",".join(scraper_stats) or "none",
            len(aggregate_raw),
        )
        payload = process_raw_items(fallback_for_feed(feed_name), feed_name=feed_name, validate_images=False)
        logger.info("Injected %s fallback items for feed '%s'", len(payload), feed_name)

    low_boost = frozenset(
        {"trending", "upcoming", "cinema_releases", "netflix", "disney_plus", "prime_video", "hbo_max"},
    )
    if feed_name in low_boost and len(payload) < 2:
        logger.warning("Feed '%s' had low volume (%s). adding fallback boosters", feed_name, len(payload))
        payload = process_raw_items(
            payload + fallback_for_feed(feed_name),
            feed_name=feed_name,
            validate_images=False,
        )

    logger.info("Prepared feed '%s' with %s item(s); JSON written after global dedupe in main.", feed_name, len(payload))
    return payload


def apply_cross_platform_dedupe(feed_name: str, payload: list[dict[str, Any]], taken_keys: set[str]) -> list[dict[str, Any]]:
    """
    Keep platform feeds mutually exclusive by title/year/type.
    """
    if feed_name not in {"netflix", "disney_plus", "prime_video", "hbo_max"}:
        return payload

    filtered: list[dict[str, Any]] = []
    dropped = 0
    for item in payload:
        key = cross_platform_key(
            title=item.get("title", ""),
            year=item.get("year"),
            media_type=item.get("type", ""),
            article_url=item.get("article_url"),
        )
        if key in taken_keys:
            dropped += 1
            continue
        taken_keys.add(key)
        filtered.append(item)

    if dropped:
        logger.info("Cross-platform dedupe removed %s item(s) from %s", dropped, feed_name)

    if not filtered:
        logger.warning("Feed '%s' became empty after cross-platform dedupe. injecting fallback.", feed_name)
        filtered = process_raw_items(
            fallback_for_feed(feed_name),
            feed_name=feed_name,
            validate_images=False,
        )
    return filtered


def filter_global_article_dedupe(payload: list[dict[str, Any]], seen_urls: set[str]) -> list[dict[str, Any]]:
    """
    Drop items whose normalized article URL appeared in an earlier feed payload.
    Keeps feeds lightweight and avoids duplicate journalism links in the mobile cache.
    """
    filtered: list[dict[str, Any]] = []
    for item in payload:
        au = item.get("article_url")
        if au and is_valid_article_page_url(str(au)):
            candidate = normalized_url_signature(str(au))
            if candidate.startswith("http"):
                if candidate in seen_urls:
                    logger.debug(
                        "Global article dedupe dropped title=%s url=%s",
                        item.get("title"),
                        candidate,
                    )
                    continue
                seen_urls.add(candidate)
        filtered.append(item)
    return filtered
