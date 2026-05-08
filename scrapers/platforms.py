"""Platform-specific scraper wrappers."""

from __future__ import annotations

from scrapers.rss_scraper import GoogleNewsRSSScraper


class NetflixScraper(GoogleNewsRSSScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="netflix",
            query="site:tudum.netflix.com Netflix new releases",
            platform="netflix",
            default_type="movie",
            fallback_queries=[
                "Netflix Tudum release date",
                "Netflix announces new series",
                "what's new on netflix this month",
            ],
            feed_urls=[
                "https://variety.com/v/tv/feed/",
                "https://variety.com/v/film/feed/",
            ],
        )


class DisneyPlusScraper(GoogleNewsRSSScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="disney_plus",
            query="Disney Plus release date announcement",
            platform="disney_plus",
            default_type="series",
            fallback_queries=[
                "Disney+ new releases",
                "Marvel Disney Plus release",
                "Star Wars Disney Plus series release date",
            ],
            feed_urls=[
                "https://variety.com/v/tv/feed/",
            ],
        )


class PrimeVideoScraper(GoogleNewsRSSScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="prime_video",
            query="Prime Video new releases this month",
            platform="prime_video",
            default_type="movie",
            fallback_queries=[
                "Amazon Prime Video release date announcement",
                "Prime Video original series release",
                "new on Prime Video",
            ],
            feed_urls=[
                "https://variety.com/v/film/feed/",
            ],
        )


class HBOMaxScraper(GoogleNewsRSSScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="hbo_max",
            query="HBO Max new releases this month",
            platform="hbo_max",
            default_type="series",
            fallback_queries=[
                "Max streaming release date",
                "HBO Max upcoming series",
                "new on Max this month",
            ],
            feed_urls=[
                "https://variety.com/v/tv/feed/",
                "https://www.hollywoodreporter.com/t/feed/",
            ],
        )
