"""Canonical article URLs and human-readable source attribution from URLs."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Common analytics / tracking params to strip where safe.
TRACKING_QUERY_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "gclid",
        "fbclid",
        "mc_cid",
        "mc_eid",
        "_ga",
        "igshid",
        "ref",
        "ref_src",
        "ref_url",
        "cmpid",
    }
)

# Public suffix quirks: bare registrable domains we label explicitly.
_PUBLISHER_PRETTY_FROM_DOMAIN: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(?:[\w.-]+\.)*variety\.com$", re.I), "Variety"),
    (re.compile(r"^(?:www\.)?deadline\.com$", re.I), "Deadline"),
    (re.compile(r"^(?:www\.)?hollywoodreporter\.com$", re.I), "The Hollywood Reporter"),
    (re.compile(r"^(?:www\.)?screenrant\.com$", re.I), "ScreenRant"),
    (re.compile(r"^(?:www\.)?collider\.com$", re.I), "Collider"),
    (re.compile(r"^(?:www\.)?indiewire\.com$", re.I), "IndieWire"),
    (re.compile(r"^(?:www\.)?thewrap\.com$", re.I), "TheWrap"),
    (re.compile(r"^(?:www\.)?slashfilm\.com$", re.I), "SlashFilm"),
    (re.compile(r"^(?:www\.)?ign\.com$", re.I), "IGN"),
    (re.compile(r"^(?:www\.)?imdb\.com$", re.I), "IMDb"),
    (re.compile(r"^(?:[^.]+\.)?netflix\.com$", re.I), "Netflix"),
    (re.compile(r"^(?:www\.)?tudum\.netflix\.com$", re.I), "Netflix Tudum"),
    (re.compile(r"^(?:www\.)?disneyplus\.com$", re.I), "Disney+"),
    (re.compile(r"^(?:www\.)?primevideo\.com$", re.I), "Prime Video"),
    (re.compile(r"^(?:www\.)?max\.com$", re.I), "Max"),
    (re.compile(r"^(?:www\.)?(?:hbomax|hbo)\.com$", re.I), "HBO Max"),
    (re.compile(r"^(?:[^.]+\.)?amazon\.(?:com|co\.uk)$", re.I), "Amazon"),
    (re.compile(r"^(?:www\.)?news\.google\.com$", re.I), "Google News"),
    (re.compile(r"^(?:www\.)?rollingstone\.com$", re.I), "Rolling Stone"),
    (re.compile(r"^(?:www\.)?theringer\.com$", re.I), "The Ringer"),
    (re.compile(r"^(?:www\.)?vulture\.com$", re.I), "Vulture"),
]


def simplify_domain(host: str) -> str:
    """Normalize hostname to registrable-ish domain label (strip leading www.)."""
    h = host.strip().lower().rstrip(".")
    if h.startswith("www."):
        h = h[4:]
    return h


def collapsible_news_apex_domains() -> tuple[str, ...]:
    """Known outlets where subdomains collapse to apex for attribution."""
    return (
        "variety.com",
        "deadline.com",
        "hollywoodreporter.com",
        "screenrant.com",
        "collider.com",
        "indiewire.com",
        "thewrap.com",
        "rollingstone.com",
        "imdb.com",
        "amazon.com",
        "amazon.co.uk",
        "netflix.com",
        "disneyplus.com",
        "primevideo.com",
        "max.com",
    )


def publication_domain(dom: str) -> str:
    """Strip decorative subdomains down to apex for outlets we recognize."""
    d = simplify_domain(dom)
    for apex in collapsible_news_apex_domains():
        if d == apex or d.endswith("." + apex):
            return apex
    return d


def _title_case_fragment(label: str) -> str:
    parts = label.replace("-", " ").replace("_", " ").split(".")
    return " ".join(p[:1].upper() + p[1:].lower() if p else "" for p in parts if p).strip()


def source_label_from_domain(domain: str) -> str:
    """Human-readable outlet name without exposing noisy subdomains."""
    base = publication_domain(domain)
    for pattern, name in _PUBLISHER_PRETTY_FROM_DOMAIN:
        if pattern.match(base) or pattern.match(domain):
            return name

    segments = base.split(".")
    if len(segments) >= 3 and segments[-1] == "uk" and segments[-2] in {"co", "com", "org", "net", "gov"}:
        return _title_case_fragment(segments[-3])
    if len(segments) >= 2:
        return _title_case_fragment(segments[-2])
    return _title_case_fragment(segments[0]) if segments else base


def derive_source_attribution(url: str) -> tuple[str, str]:
    """
    Returns (source_name, source_domain) from an absolute HTTP(S) URL.
    Falls back to conservative defaults when parsing fails.
    """
    if not url or not isinstance(url, str):
        return "Unknown", "unknown"
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        return "Unknown", "unknown"
    try:
        parts = urlsplit(u)
        host = parts.netloc.split("@")[-1]
        if ":" in host:
            host = host.split(":")[0]
        domain = publication_domain(simplify_domain(host))
        name = source_label_from_domain(domain)
        return name, domain
    except Exception:
        return "Unknown", "unknown"


def strip_tracking_params(url: str) -> str:
    """Remove common tracking query parameters; preserve other query keys."""
    if not url.startswith(("http://", "https://")):
        return url
    try:
        parts = urlsplit(url)
        q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False) if k.lower() not in TRACKING_QUERY_PARAMS]
        query = urlencode(q, doseq=True)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
    except Exception:
        return url


def canonical_article_url(url: str | None) -> str:
    """
    Best-effort absolute canonical article URL: https preferred, strip tracking.
    Fallback: empty string (callers coerce for schema).
    """
    if url is None:
        return ""
    u = str(url).strip()
    if not u:
        return ""
    if u.startswith("//"):
        u = "https:" + u
    if not u.startswith(("http://", "https://")):
        return ""

    cleaned = strip_tracking_params(u.split("#")[0].rstrip())
    split = urlsplit(cleaned)
    scheme = split.scheme.lower()
    netloc = split.netloc
    path = split.path or "/"
    query = split.query

    # Upgrade http -> https for attribution safety (scrapers rarely need plain http).
    if scheme == "http":
        scheme = "https"

    return urlunsplit((scheme, netloc, path, query, ""))
