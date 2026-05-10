"""Safe fallback demo data when upstream scraping is empty."""

from __future__ import annotations

from utils.normalization import utc_now_iso

# Neutral demo art when live feeds are empty (Wikimedia Commons–style stock “no picture”).
_DEFAULT_FALLBACK_POSTER = "https://upload.wikimedia.org/wikipedia/en/6/60/No_Picture.jpg"


def _item(
    *,
    title: str,
    year: int,
    media_type: str,
    platform: str,
    release_date: str,
    overview: str,
    genres: list[str],
    source_url: str,
    poster_url: str | None = None,
) -> dict[str, object]:
    art = poster_url or _DEFAULT_FALLBACK_POSTER
    return {
        "title": title,
        "year": year,
        "type": media_type,
        "platform": platform,
        "release_date": release_date,
        "overview": overview,
        "genres": genres,
        "poster_image_url": art,
        "backdrop_image_url": art,
        "rating": None,
        "trailer_url": None,
        "source_url": source_url,
        "scraped_at": utc_now_iso(),
    }


def fallback_for_feed(feed_name: str) -> list[dict[str, object]]:
    fallback_map: dict[str, list[dict[str, object]]] = {
        "trending": [
            _item(
                title="StreamRadar Trending Spotlight",
                year=2026,
                media_type="movie",
                platform="imdb_trending",
                release_date="2026-05-08",
                overview="Demo trending premiere cue when headline feeds are empty.",
                genres=["Drama"],
                source_url="https://www.imdb.com/chart/moviemeter/",
            ),
            _item(
                title="StreamRadar TV Buzz",
                year=2026,
                media_type="series",
                platform="imdb_trending",
                release_date="2026-05-08",
                overview="Demo viral streaming premiere teaser for trending feed offline testing.",
                genres=["Thriller"],
                source_url="https://www.imdb.com/chart/tvmeter/",
            ),
        ],
        "netflix": [
            _item(
                title="StreamRadar Netflix Placeholder",
                year=2026,
                media_type="movie",
                platform="netflix",
                release_date="2026-05-15",
                overview="Begins streaming placeholder when Google News returns no rows for this run.",
                genres=["Drama"],
                source_url="https://www.netflix.com/title/80057281",
            ),
        ],
        "cinema_releases": [
            _item(
                title="StreamRadar Theatrical Placeholder",
                year=2026,
                media_type="movie",
                platform="cinema",
                release_date="2026-05-22",
                overview="Wide release placeholder when theatrical RSS search returns no rows.",
                genres=["Action"],
                source_url="https://www.imdb.com/chart/boxoffice/",
            ),
        ],
        "upcoming": [
            _item(
                title="StreamRadar Upcoming Premiere",
                year=2026,
                media_type="movie",
                platform="multi_platform",
                release_date="2026-06-01",
                overview="Demo slate: will premiere soon when upcoming release feeds return empty.",
                genres=["Adventure"],
                source_url="https://news.google.com/",
            ),
            _item(
                title="StreamRadar Upcoming Series",
                year=2026,
                media_type="series",
                platform="multi_platform",
                release_date="2026-06-15",
                overview="Coming soon — set to stream next month for downstream test payloads.",
                genres=["Sci-Fi"],
                source_url="https://news.google.com/",
            ),
        ],
    }
    default_item = _item(
        title=f"StreamRadar {feed_name.replace('_', ' ').title()} Demo Item",
        year=2026,
        media_type="movie",
        platform=feed_name,
        release_date="2026-05-08",
        overview="Fallback demo content used while source pages are unavailable.",
        genres=["Drama"],
        source_url="https://news.google.com/",
    )
    return fallback_map.get(feed_name, [default_item])
