"""upcoming.json — Google News: upcoming releases + entertainment news from cinema & digital platforms."""

from __future__ import annotations

from scrapers.rss_scraper import GoogleNewsRSSScraper


class UpcomingReleasesScraper(GoogleNewsRSSScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="upcoming_releases",
            query=(
                "(upcoming OR \"coming soon\" OR premiere OR \"release date\" OR "
                "\"new season\" OR trailer OR renewed OR cancelled OR canceled) "
                "(movie OR film OR series OR show OR Netflix OR \"Disney+\" OR "
                "\"Prime Video\" OR \"HBO Max\" OR Max OR streaming OR cinema OR theater)"
            ),
            platform="multi_platform",
            default_type="movie",
            fallback_queries=[
                "Netflix Disney+ \"Prime Video\" Max new movie series 2026",
                "upcoming movie film premiere 2026 trailer",
                "streaming series renewed cancelled new season 2026",
                "cinema theatrical release upcoming film 2026",
                "\"release date\" movie series streaming premiere",
            ],
            feed_urls=[],
            release_signal_keywords=[],
            exclude_keywords=[
                "stock price",
                "quarterly earnings",
                "shares fell",
                "shares rose",
                "lawsuit filed",
                "sports schedule",
                "nfl draft",
                "nba trade",
            ],
        )
