"""Detect real article/content pages vs homepage URLs; resolve redirects & HTML hints."""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse, urlunparse

from utils.attribution import canonical_article_url, strip_tracking_params
from utils.http_client import HTTPClient

logger = logging.getLogger(__name__)

GENERIC_SINGLE_SEGMENTS = frozenset(
    {
        "browse",
        "home",
        "us",
        "en",
        "gb",
        "fr",
        "de",
        "es",
        "it",
        "tv",
        "movies",
        "watch",
        "originals",
        "login",
        "signup",
        "search",
        "shop",
        "store",
        "help",
        "support",
        "download",
        "account",
        "profiles",
        "settings",
        "corporate",
        "press",
        "about",
        "news",
        "film",
        "sports",
    }
)


def collapse_duplicate_slashes_in_path(url: str) -> str:
    """Normalize accidental double slashes in the path segment only."""
    parsed = urlparse(url)
    path = parsed.path or "/"
    collapsed = re.sub(r"/{2,}", "/", path.replace("\\", "/"))
    if not collapsed.startswith("/"):
        collapsed = "/" + collapsed
    return urlunparse(parsed._replace(path=collapsed or "/"))


def unwrap_redirect_wrapper(url: str) -> str:
    """Unpack Google/Facebook outbound redirect wrappers to the inner publisher URL."""
    try:
        parts = urlparse(url.strip())
        host = parts.netloc.lower()
        qs = parse_qs(parts.query)
        if host.endswith("google.com") and "/url" in parts.path.lower():
            inner = qs.get("url") or qs.get("q") or qs.get("u")
            if inner and isinstance(inner[0], str):
                return unquote(inner[0].strip())
        if "facebook.com" in host or "l.facebook.com" in host:
            inner = qs.get("u") or qs.get("url")
            if inner and isinstance(inner[0], str):
                return unquote(inner[0].strip())
    except Exception:
        pass
    return url.strip()


_HREF_PUB = re.compile(r'href=["\'](https?://[^"\']+)["\']', re.I)
_CANON_LINK = re.compile(
    r'<link[^>]+rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\'][^>]*>',
    re.I,
)
_CANON_LINK_ALT = re.compile(
    r'<link[^>]+href=["\']([^"\']+)["\'][^>]*rel=["\']canonical["\'][^>]*>',
    re.I,
)
_OG_URL = re.compile(
    r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_OG_URL_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:url["\']',
    re.I,
)


def _segments(path_norm: str) -> list[str]:
    return [s for s in path_norm.strip("/").split("/") if s]


def is_valid_article_page_url(url: str | None) -> bool:
    """
    True when URL points at a concrete content page (not bare domain / hub / browse).
    """
    if not url:
        return False
    cleaned = canonical_article_url(unwrap_redirect_wrapper(url))
    if not cleaned or not cleaned.startswith("https://"):
        return False
    parsed = urlparse(cleaned)
    host = (parsed.netloc or "").split("@")[-1].lower()
    if ":" in host:
        host = host.split(":")[0]
    raw_path = parsed.path or "/"
    path_norm = re.sub(r"/{2,}", "/", raw_path)
    if not path_norm.startswith("/"):
        path_norm = "/" + path_norm
    path_lower = path_norm.lower()
    segments = _segments(path_norm)

    if "news.google.com" in host:
        return False

    if len(segments) == 0:
        return False

    if "nflxext.com" in host:
        return len(segments) >= 2

    if "netflix.com" in host:
        skip_roots = frozenset({"browse", "login", "account", "profiles", "signup"})
        # Tudum / editorial subsite uses article-style paths without /title/
        if host.startswith("tudum.") or ".tudum." in host:
            return len(segments) >= 2 and segments[0].lower() not in skip_roots
        if "/title/" in path_lower:
            return bool(re.search(r"/title/[a-z0-9-]+", path_lower))
        if "/nq/" in path_lower:
            return True
        if segments and segments[0].lower() in skip_roots:
            return len(segments) >= 3
        return len(segments) >= 2 and segments[0].lower() not in skip_roots

    if "disneyplus.com" in host:
        if segments[0].lower() in {"browse", "home", "shop", "espn"} and len(segments) < 3:
            return False
        return len(segments) >= 2

    if "primevideo.com" in host:
        return bool(
            re.search(r"/detail/|/video/|/storefront/|/dp/|/gp/video/", path_lower)
        )

    if "amazon." in host and ("/gp/video" in path_lower or "primevideo" in path_lower):
        return bool(re.search(r"/detail/|/video/|/dp/", path_lower))

    if "max.com" in host or "hbo.com" in host or "hbomax.com" in host:
        if segments[0].lower() in {"sign-in", "login", "404"}:
            return False
        return len(segments) >= 2

    if "imdb.com" in host:
        return bool(
            re.search(r"/title/tt\d+|/chart/|/name/nm\d+|/news/ni\d+", path_lower)
        )

    if re.search(r"/(19|20)\d{2}/", path_lower):
        return True

    if len(segments) >= 3:
        return True

    if len(segments) == 2:
        a, b = segments[0].lower(), segments[1].lower()
        if a == "v" and b in {"film", "tv", "music", "awards"}:
            return False
        if a in {"tv", "film", "movies"} and b in {"film", "tv", "news", "boxes", "reviews"}:
            return False
        return True

    lone = segments[0].lower()
    if lone in GENERIC_SINGLE_SEGMENTS:
        return False
    return len(segments[0]) >= 24


def extract_meta_article_urls(html: str, base_url: str) -> list[str]:
    """Priority: canonical link, then og:url."""
    found: list[str] = []
    for pattern in (_CANON_LINK, _CANON_LINK_ALT):
        match = pattern.search(html)
        if match:
            found.append(match.group(1).strip())
            break
    for pattern in (_OG_URL, _OG_URL_ALT):
        match = pattern.search(html)
        if match:
            found.append(match.group(1).strip())
            break
    normalized: list[str] = []
    for raw in found:
        joined = unwrap_redirect_wrapper(urljoin(base_url, raw))
        c = canonical_article_url(joined)
        if c:
            normalized.append(c)
    return normalized


def harvest_html_hrefs(html: str, base_url: str) -> list[str]:
    """Collect absolute http(s) links for Google News intermediary pages."""
    urls: list[str] = []
    for match in _HREF_PUB.finditer(html):
        candidate = unwrap_redirect_wrapper(urljoin(base_url, match.group(1).strip()))
        urls.append(candidate)
    return urls


def resolve_to_article_url(
    url: str | None,
    http_client: HTTPClient,
    *,
    max_html_bytes: int = 450_000,
) -> str | None:
    """
    Follow redirects, then parse canonical / og:url / publisher hrefs when needed.
    Returns a validated article URL or None (never homepage fallbacks).
    """
    if not url or not isinstance(url, str):
        return None
    try:
        unwrapped = unwrap_redirect_wrapper(strip_tracking_params(url.split("#")[0].strip()))
    except Exception:
        unwrapped = (url or "").strip()
    if not unwrapped.startswith(("http://", "https://")):
        return None

    response = http_client.get(unwrapped, allow_redirects=True)
    text = ""
    final_url = str(response.url or unwrapped)
    candidates: list[str] = []

    ctype = response.headers.get("Content-Type", "").lower()
    meta_base = canonical_article_url(final_url) or canonical_article_url(unwrapped) or ""
    candidates.append(canonical_article_url(meta_base))

    if "html" in ctype:
        chunk = getattr(response, "text", "") or ""
        text = chunk[:max_html_bytes]
        candidates.extend(extract_meta_article_urls(text, meta_base))

        parsed_host = urlparse(meta_base).netloc.lower()
        if "news.google.com" in parsed_host:
            for href in harvest_html_hrefs(text, meta_base):
                if "google." in urlparse(href).netloc.lower():
                    continue
                candidates.append(canonical_article_url(href))

    seen: set[str] = set()
    for cand in candidates:
        if not cand:
            continue
        c = collapse_duplicate_slashes_in_path(cand)
        c = canonical_article_url(c)
        if not c or c in seen:
            continue
        seen.add(c)
        if is_valid_article_page_url(c):
            return c

    logger.debug("Could not resolve substantive article URL from %s (final=%s)", url, response.url)
    return None
