"""Cinema/theatrical releases scraper."""

from __future__ import annotations

from scrapers.rss_scraper import GoogleNewsRSSScraper


class CinemaReleasesScraper(GoogleNewsRSSScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="cinema_releases",
            query="in theaters now OR theatrical release date",
            platform="cinema",
            default_type="movie",
            fallback_queries=[
                "box office weekend releases",
                "new theatrical releases this week",
            ],
            feed_urls=[
                "https://variety.com/v/film/feed/",
            ],
        )
