"""Entry point for StreamRadar scraping jobs."""

from __future__ import annotations

import logging
import time

from scrapers import (
    CinemaReleasesScraper,
    DisneyPlusScraper,
    HBOMaxScraper,
    IMDbTrendingScraper,
    NetflixScraper,
    PrimeVideoScraper,
    UpcomingReleasesScraper,
)
from utils.logging_setup import setup_logging
from utils.pipeline import run_feed


def run_all() -> None:
    feed_map = {
        "trending": [IMDbTrendingScraper()],
        "upcoming": [UpcomingReleasesScraper()],
        "netflix": [NetflixScraper()],
        "disney_plus": [DisneyPlusScraper()],
        "prime_video": [PrimeVideoScraper()],
        "hbo_max": [HBOMaxScraper()],
        "cinema_releases": [CinemaReleasesScraper()],
    }

    started_at = time.time()
    for feed_name, scraper_objects in feed_map.items():
        run_feed(feed_name, scraper_objects)

    elapsed = round(time.time() - started_at, 2)
    logging.getLogger(__name__).info("Completed all feeds in %s seconds", elapsed)


if __name__ == "__main__":
    setup_logging()
    run_all()
