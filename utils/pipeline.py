"""Scraping pipeline orchestration."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from config import APP_CONFIG, OUTPUT_DIR
from scrapers.base import ContentItem
from utils.image_utils import validate_image_url
from utils.json_utils import validate_item_schema, write_json
from utils.http_client import HTTPClient

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
        key = "|".join(
            [
                item.get("title", "").lower(),
                str(item.get("year") or ""),
                item.get("type", "").lower(),
                item.get("platform", "").lower(),
            ]
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
            continue
        if validate_images:
            item["poster_image_url"] = validate_image_url(item["poster_image_url"], http_client)
            item["backdrop_image_url"] = validate_image_url(item["backdrop_image_url"], http_client)
        if validate_item_schema(item):
            processed.append(item)

    deduped = _dedupe(processed)
    deduped.sort(key=_sort_key, reverse=True)
    return deduped[: APP_CONFIG.max_items_per_feed]


def run_feed(feed_name: str, scraper_objects: list[Any]) -> list[dict[str, Any]]:
    logger.info("Running feed '%s' with %s scraper(s)", feed_name, len(scraper_objects))
    aggregate_raw: list[dict[str, Any]] = []
    for scraper in scraper_objects:
        try:
            aggregate_raw.extend(scraper.scrape())
        except Exception as exc:
            logger.exception("Scraper %s failed: %s", scraper.scraper_name, exc)
            continue

    payload = process_raw_items(aggregate_raw, validate_images=True)
    write_json(OUTPUT_DIR / f"{feed_name}.json", payload)
    logger.info("Wrote output/%s.json (%s items)", feed_name, len(payload))
    return payload
