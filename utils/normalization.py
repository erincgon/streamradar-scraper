"""Normalization and defensive data conversion helpers."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from urllib.parse import parse_qsl, urlsplit

from utils.article_url import is_valid_article_page_url
from utils.attribution import canonical_article_url, publication_domain, simplify_domain

SUMMARY_MAX_CHARS = 500

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


def utc_now_iso_z() -> str:
    """ISO 8601 UTC with trailing Z for mobile parsers."""
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text or fallback


def clamp_summary(value: Any, *, max_chars: int = SUMMARY_MAX_CHARS, fallback: str = "") -> str:
    """Trim overview/excerpt safely for attribution; avoids oversized copyright-risk blobs."""
    text = clean_text(value, fallback=fallback)
    if not text:
        return fallback
    if len(text) <= max_chars:
        return text

    clipped = text[:max_chars].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    clipped = clipped.rstrip(" ,;:-–—")
    if not clipped.endswith((".", "!", "?")):
        clipped = f"{clipped}..."
    return clipped if clipped else fallback


def normalize_pub_date_to_iso_z(value: Any) -> str | None:
    """
    Normalize assorted date strings / datetimes into ISO 8601 UTC ending with Z.
    Returns None if unknown.
    """
    if value is None or value == "":
        return None
    dt: datetime | None = None

    if isinstance(value, datetime):
        dt = value.astimezone(timezone.utc).replace(tzinfo=timezone.utc, microsecond=0)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    text = clean_text(value)
    if not text:
        return None

    if text.endswith("Z") and len(text) >= 20:
        try:
            dt = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc).replace(microsecond=0)
        return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        pass

    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc).replace(microsecond=0)
        return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OverflowError):
        pass

    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
            parsed = datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc).replace(microsecond=0)
            return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue

    return None


def normalize_title(value: Any, fallback: str = "Unknown Title") -> str:
    text = clean_text(value, fallback=fallback)
    text = re.sub(r"\s*\((?:\d{4}|TV Series|TV Mini Series)\)\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" -|")
    return text or fallback


def normalize_type(value: Any, fallback: str = "movie") -> str:
    text = clean_text(value, fallback=fallback).lower()
    if "doc" in text:
        return "documentary"
    if "anime" in text:
        return "anime"
    if any(keyword in text for keyword in ("tv", "series", "show", "season", "episode")):
        return "series"
    return "movie"


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


def normalized_url_signature(url: str | None) -> str:
    if not url:
        return ""
    canonical = canonical_article_url(url).lower().rstrip("/")
    try:
        parsed = urlsplit(canonical)
        scheme = parsed.scheme
        dom = publication_domain(simplify_domain(parsed.netloc))
        path = parsed.path.lower().rstrip("/")
        qs = "&".join(sorted(f"{k}={v}" for k, v in parse_qsl(parsed.query)))
        return f"{scheme}://{dom}{path}" + (f"?{qs}" if qs else "")
    except Exception:
        return canonical


def title_similarity_signature(title: str) -> str:
    """Collapsed title fingerprint for fuzzy-ish dedupe without heavy deps."""
    t = normalize_title(title).lower()
    t = re.sub(r"\b(?:the|a|an)\b", "", t)
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def dedupe_key_parts(
    title: str,
    year: int | None,
    media_type: str,
    source_url: str,
    article_url: str | None = None,
) -> str:
    url_sig = ""
    if article_url and is_valid_article_page_url(article_url):
        url_sig = normalized_url_signature(article_url)
    elif source_url and is_valid_article_page_url(source_url):
        url_sig = normalized_url_signature(source_url)
    if url_sig.startswith("http") and url_sig not in {"", "http://unknown", "https://unknown"}:
        return "url|" + url_sig

    normalized_source = normalized_url_signature(source_url) or clean_text(source_url).split("?")[0].rstrip("/").lower()
    return "|".join(
        [
            title_similarity_signature(title),
            str(year or ""),
            normalize_type(media_type),
            normalized_source,
        ]
    )


def cross_platform_key(
    title: str,
    year: int | None,
    media_type: str,
    article_url: str | None = None,
) -> str:
    url_sig = ""
    if article_url and is_valid_article_page_url(article_url):
        url_sig = normalized_url_signature(article_url)
    if url_sig.startswith("http"):
        return "url|" + url_sig
    return "|".join(
        [
            title_similarity_signature(title),
            str(year or ""),
            normalize_type(media_type),
        ]
    )
