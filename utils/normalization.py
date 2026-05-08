"""Normalization and defensive data conversion helpers."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d %b %Y",
    "%B %d, %Y",
    "%Y-%m",
    "%Y",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text or fallback


def parse_year(value: Any) -> int | None:
    text = clean_text(value)
    match = re.search(r"(19|20)\d{2}", text)
    return int(match.group(0)) if match else None


def parse_release_date(value: Any) -> str | None:
    """Return date as YYYY-MM-DD when possible."""
    text = clean_text(value)
    if not text:
        return None

    try:
        return parsedate_to_datetime(text).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        pass

    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt == "%Y":
                parsed = parsed.replace(month=1, day=1)
            elif fmt == "%Y-%m":
                parsed = parsed.replace(day=1)
            return parsed.date().isoformat()
        except ValueError:
            continue

    return None


def normalize_genres(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r"[,/|]", str(value))
    return sorted({clean_text(item).title() for item in raw if clean_text(item)})
