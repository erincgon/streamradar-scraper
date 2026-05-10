"""upcoming.json — Google News: henüz yayına girmemiş / tarihi duyurulan yapımlar."""

from __future__ import annotations

from scrapers.rss_scraper import GoogleNewsRSSScraper, UPCOMING_FUTURE_SIGNAL_KEYWORDS


class UpcomingReleasesScraper(GoogleNewsRSSScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="upcoming_releases",
            query=(
                '("coming soon" OR upcoming OR "next week" OR "next month" OR '
                '"will premiere" OR "set to premiere" OR slated OR '
                '"release date announced" OR "premieres on") '
                '(movie OR film OR series OR Netflix OR "Disney+" OR "Prime Video" OR '
                '"HBO Max" OR Max OR streaming)'
            ),
            platform="multi_platform",
            default_type="movie",
            fallback_queries=[
                '"coming to Netflix" OR "coming to Disney Plus" premiere date',
                'Max OR "HBO Max" "release date" OR scheduled premiere',
                '"Prime Video" OR Amazon series premiere slated',
                "theatrical OR streaming postponed OR delayed premiere",
            ],
            feed_urls=[],
            release_signal_keywords=UPCOMING_FUTURE_SIGNAL_KEYWORDS,
            exclude_keywords=[
                "now streaming",
                "currently streaming",
                "available now",
                "already streaming",
                "already available",
                "out now",
                "watch now",
                "streams now",
                "just dropped",
            ],
        )
