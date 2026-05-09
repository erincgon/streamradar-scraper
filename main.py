"""Entry point for StreamRadar scraping jobs."""

from __future__ import annotations

import logging
import time

from config import OUTPUT_DIR
from scrapers import (
    CinemaReleasesScraper,
    DisneyPlusScraper,
    HBOMaxScraper,
    IMDbTrendingScraper,
    NetflixScraper,
    PrimeVideoScraper,
    UpcomingReleasesScraper,
)
from utils.json_utils import write_json
from utils.logging_setup import setup_logging
from utils.metadata import update_meta_file
from utils.pipeline import apply_cross_platform_dedupe, filter_global_article_dedupe, run_feed


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
    taken_cross_platform_keys: set[str] = set()
    seen_article_urls: set[str] = set()
    final_feeds_payload: dict[str, list[dict[str, object]]] = {}
    for feed_name, scraper_objects in feed_map.items():
        payload = run_feed(feed_name, scraper_objects)
        filtered = apply_cross_platform_dedupe(feed_name, payload, taken_cross_platform_keys)
        filtered = filter_global_article_dedupe(filtered, seen_article_urls)
        if filtered != payload:
            # rewrite feed only when cross-platform filtering changed it
            write_json(OUTPUT_DIR / f"{feed_name}.json", filtered)
        final_feeds_payload[feed_name] = filtered

    update_meta_file(OUTPUT_DIR / "meta.json", final_feeds_payload)

    elapsed = round(time.time() - started_at, 2)
    logging.getLogger(__name__).info("Completed all feeds in %s seconds", elapsed)


if __name__ == "__main__":
    setup_logging()
    run_all()
