"""JSON serialization and validation helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_KEYS = {
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
}


def validate_item_schema(item: dict[str, Any]) -> bool:
    if not REQUIRED_KEYS.issubset(item.keys()):
        return False
    if not isinstance(item["genres"], list):
        return False
    return True


def write_json(path: Path, payload: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
