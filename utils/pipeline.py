"""Scraping pipeline orchestration."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from config import APP_CONFIG, OUTPUT_DIR
from scrapers.base import ContentItem
from utils.fallback_data import fallback_for_feed
from utils.image_utils import validate_image_url
from utils.json_utils import validate_item_schema, write_json
from utils.http_client import HTTPClient
from utils.normalization import dedupe_key_parts

logger = logging.getLogger(__name__)


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
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def process_raw_items(raw_items: list[dict[str, Any]], validate_images: bool = True) -> list[dict[str, Any]]:
    http_client = HTTPClient()
    processed: list[dict[str, Any]] = []
    for raw in raw_items:
        item = ContentItem.from_raw(raw).to_dict()
        if not item["source_url"]:
            logger.debug("Skipping item due to missing source_url: %s", raw)
            continue
        if item["title"].lower() in {"unknown title", "home", "video"}:
            logger.debug("Skipping low-quality title item: %s", item["title"])
            continue
        if validate_images:
            item["poster_image_url"] = validate_image_url(item["poster_image_url"], http_client)
            item["backdrop_image_url"] = validate_image_url(item["backdrop_image_url"], http_client)
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

    payload = process_raw_items(aggregate_raw, validate_images=True)
    if not payload:
        logger.warning(
            "Feed '%s' was empty after normalization. scraper_stats=%s raw_count=%s",
            feed_name,
            ",".join(scraper_stats) or "none",
            len(aggregate_raw),
        )
        payload = process_raw_items(fallback_for_feed(feed_name), validate_images=False)
        logger.info("Injected %s fallback items for feed '%s'", len(payload), feed_name)

    if feed_name in {"trending", "upcoming"} and len(payload) < 2:
        logger.warning("Feed '%s' had low volume (%s). adding fallback boosters", feed_name, len(payload))
        payload = process_raw_items(payload + fallback_for_feed(feed_name), validate_images=False)

    write_json(OUTPUT_DIR / f"{feed_name}.json", payload)
    logger.info("Wrote output/%s.json (%s items)", feed_name, len(payload))
    return payload
