"""Upcoming releases scraper."""

from __future__ import annotations

from scrapers.rss_scraper import GoogleNewsRSSScraper


class UpcomingReleasesScraper(GoogleNewsRSSScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="upcoming_releases",
            query="upcoming movie release OR upcoming tv series release",
            platform="multi_platform",
            default_type="movie",
            fallback_queries=[
                "upcoming netflix series release date",
                "upcoming disney plus releases",
                "upcoming cinema releases",
            ],
            feed_urls=[
                "https://variety.com/v/film/feed/",
                "https://variety.com/v/tv/feed/",
            ],
        )
