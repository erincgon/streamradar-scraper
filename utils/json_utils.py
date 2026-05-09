"""JSON serialization and validation helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_KEYS = (
    "title",
    "year",
    "type",
    "platform",
    "release_date",
    "overview",
    "genres",
    "poster_image_url",
    "backdrop_image_url",
    "rating",
    "trailer_url",
    "source_url",
    "scraped_at",
    "source_name",
    "source_domain",
    "article_url",
    "content_type",
    "published_at",
    "updated_at",
)

_KEY_ORDER_INDEX = {name: idx for idx, name in enumerate(REQUIRED_KEYS)}


def validate_item_schema(item: dict[str, Any]) -> bool:
    keys = item.keys()
    if not item or not isinstance(item, dict):
        return False
    if set(REQUIRED_KEYS) - set(keys):
        return False
    if not isinstance(item["genres"], list):
        return False
    return True


def sort_keys_canonical(payload: dict[str, Any]) -> dict[str, Any]:
    """Deterministic ordering for stable JSON diffs."""

    ordered: dict[str, Any] = {}
    remainder = sorted(
        [(k, v) for k, v in payload.items() if k not in _KEY_ORDER_INDEX],
        key=lambda kv: kv[0],
    )
    for name in REQUIRED_KEYS:
        ordered[name] = payload[name]
    for k, v in remainder:
        ordered[k] = v
    return ordered


def write_json(path: Path, payload: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    canon = [sort_keys_canonical(row) if isinstance(row, dict) else row for row in payload]
    with path.open("w", encoding="utf-8") as file:
        json.dump(canon, file, ensure_ascii=False, indent=2)
        file.write("\n")
