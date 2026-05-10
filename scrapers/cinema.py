"""cinema_releases.json — Google News: bu hafta / yakın tarih vizyon ve gişe haberleri."""

from __future__ import annotations

from scrapers.rss_scraper import GoogleNewsRSSScraper, THEATRICAL_RELEASE_SIGNAL_KEYWORDS


class CinemaReleasesScraper(GoogleNewsRSSScraper):
    def __init__(self) -> None:
        super().__init__(
            scraper_name="cinema_releases",
            query=(
                '("opening this week" OR "in theaters" OR "in theatres" OR '
                '"opening weekend" OR "box office" OR "wide release" OR '
                '"new movie" OR "new film")'
            ),
            platform="cinema",
            default_type="movie",
            fallback_queries=[
                "new movies theaters this weekend OR Friday opening films",
                "theatrical release date announced blockbuster",
                "limited release expands wide box office",
            ],
            feed_urls=[],
            release_signal_keywords=THEATRICAL_RELEASE_SIGNAL_KEYWORDS,
        )
