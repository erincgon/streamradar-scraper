"""trending.json — Google News: bu hafta öne çıkan / viral yayın başlıkları."""

from __future__ import annotations

from scrapers.rss_scraper import (
    GoogleNewsRSSScraper,
    PLATFORM_STREAMING_RELEASE_SIGNAL_KEYWORDS,
    TRENDING_BURST_KEYWORDS,
)


class TrendingNewReleasesScraper(GoogleNewsRSSScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="trending_new_releases",
            query=(
                '("this week" OR trending OR viral OR breakout OR "streaming charts") '
                '(Netflix OR "Prime Video" OR "Disney+" OR "HBO Max" OR Max OR '
                'premiere OR "release date" OR "new series" OR streaming)'
            ),
            platform="multi_platform",
            default_type="movie",
            fallback_queries=[
                '("most watched" OR "top 10") streaming this week premiere',
                '(viral OR trending) Netflix OR HBO OR Prime OR "Disney Plus"',
                '"breakout hit" streaming OR limited series premiere',
                '"what everyone is watching" streaming series',
            ],
            feed_urls=[],
            release_signal_keywords=PLATFORM_STREAMING_RELEASE_SIGNAL_KEYWORDS,
            additional_signal_keywords=TRENDING_BURST_KEYWORDS,
        )
