"""Safe fallback demo data when upstream scraping is empty."""

from __future__ import annotations

from utils.normalization import utc_now_iso


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
) -> dict[str, object]:
    return {
        "title": title,
        "year": year,
        "type": media_type,
        "platform": platform,
        "release_date": release_date,
        "overview": overview,
        "genres": genres,
        "poster_image_url": None,
        "backdrop_image_url": None,
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
                overview="Demo fallback item used when IMDb or news sources are temporarily unavailable.",
                genres=["Drama"],
                source_url="https://www.imdb.com/chart/moviemeter/",
            ),
            _item(
                title="StreamRadar TV Buzz",
                year=2026,
                media_type="series",
                platform="imdb_trending",
                release_date="2026-05-08",
                overview="Demo fallback series item to keep trending feed usable for app development.",
                genres=["Thriller"],
                source_url="https://www.imdb.com/chart/tvmeter/",
            ),
        ],
        "upcoming": [
            _item(
                title="StreamRadar Upcoming Premiere",
                year=2026,
                media_type="movie",
                platform="multi_platform",
                release_date="2026-06-01",
                overview="Demo fallback upcoming title injected when release feeds return empty.",
                genres=["Adventure"],
                source_url="https://news.google.com/",
            ),
            _item(
                title="StreamRadar Upcoming Series",
                year=2026,
                media_type="series",
                platform="multi_platform",
                release_date="2026-06-15",
                overview="Fallback upcoming series to ensure downstream clients always receive testable payloads.",
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
