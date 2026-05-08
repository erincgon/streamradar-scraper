"""Platform-specific scraper wrappers."""

from __future__ import annotations

from scrapers.rss_scraper import GoogleNewsRSSScraper


class NetflixScraper(GoogleNewsRSSScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="netflix",
            query="site:tudum.com Netflix new on netflix",
            platform="netflix",
            default_type="movie",
        )


class DisneyPlusScraper(GoogleNewsRSSScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="disney_plus",
            query="Disney Plus release date announcement",
            platform="disney_plus",
            default_type="series",
        )


class PrimeVideoScraper(GoogleNewsRSSScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="prime_video",
            query="Prime Video new releases this month",
            platform="prime_video",
            default_type="movie",
        )


class HBOMaxScraper(GoogleNewsRSSScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="hbo_max",
            query="HBO Max new releases this month",
            platform="hbo_max",
            default_type="series",
        )
