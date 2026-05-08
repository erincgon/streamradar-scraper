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
            include_keywords=["netflix", "tudum", "new on netflix"],
            exclude_keywords=["disney+", "disney plus", "prime video", "hbo max", "max "],
            trusted_domains=["netflix.com", "tudum.netflix.com", "whats-on-netflix.com"],
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
            include_keywords=["disney+", "disney plus", "hulu/disney", "star wars", "marvel"],
            exclude_keywords=["netflix", "prime video", "hbo max", "new on max"],
            trusted_domains=["disneyplus.com", "whatsondisneyplus.com"],
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
            include_keywords=["prime video", "amazon prime", "prime original"],
            exclude_keywords=["netflix", "disney+", "hbo max", "max "],
            trusted_domains=["primevideo.com", "amazon.com"],
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
            ],
            include_keywords=["hbo max", "max original", "new on max", "hbo original"],
            exclude_keywords=["netflix", "disney+", "prime video", "amazon prime"],
            trusted_domains=["max.com", "hbo.com", "hbomax.com"],
        )
