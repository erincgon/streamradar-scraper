"""StreamRadar scraping entrypoint.

Platform feeds hold daily Top 10 movies + Top 10 series:
- Netflix: official Tudum Top 10 (Turkey)
- Disney+ / Prime / Max: JustWatch TRENDING (TR)

Discovery feeds (trending, upcoming, cinema) use RSS / chart sources.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import OUTPUT_DIR
from scrapers import (
    CinemaReleasesScraper,
    DisneyPlusScraper,
    HBOMaxScraper,
    IMDbBoxOfficeScraper,
    NetflixScraper,
    PrimeVideoScraper,
    TrendingNewReleasesScraper,
    UpcomingReleasesScraper,
)
from utils.json_utils import write_json
from utils.logging_setup import setup_logging
from utils.metadata import update_meta_file
from utils.pipeline import apply_cross_platform_dedupe, filter_global_article_dedupe, run_feed

PLATFORM_FEEDS = frozenset({"netflix", "disney_plus", "prime_video", "hbo_max"})
DISCOVERY_FEEDS = frozenset({"trending", "upcoming"})


def _run_one(feed_name: str, scraper_objects: list) -> tuple[str, list[dict[str, object]]]:
    payload = run_feed(feed_name, scraper_objects)
    return feed_name, apply_cross_platform_dedupe(feed_name, payload, set())


def run_all() -> None:
    feed_map = {
        "trending": [TrendingNewReleasesScraper()],
        "upcoming": [UpcomingReleasesScraper()],
        "netflix": [NetflixScraper()],
        "disney_plus": [DisneyPlusScraper()],
        "prime_video": [PrimeVideoScraper()],
        "hbo_max": [HBOMaxScraper()],
        "cinema_releases": [IMDbBoxOfficeScraper(), CinemaReleasesScraper()],
    }

    started_at = time.time()
    seen_discovery_article_urls: set[str] = set()
    final_feeds_payload: dict[str, list[dict[str, object]]] = {}

    # Platform charts are independent — scrape them concurrently for speed.
    platform_jobs = {name: scrapers for name, scrapers in feed_map.items() if name in PLATFORM_FEEDS}
    other_jobs = {name: scrapers for name, scrapers in feed_map.items() if name not in PLATFORM_FEEDS}

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_run_one, name, scrapers) for name, scrapers in platform_jobs.items()]
        for fut in as_completed(futures):
            feed_name, filtered = fut.result()
            write_json(OUTPUT_DIR / f"{feed_name}.json", filtered)
            final_feeds_payload[feed_name] = filtered

    for feed_name, scraper_objects in other_jobs.items():
        feed_name, filtered = _run_one(feed_name, scraper_objects)
        if feed_name in DISCOVERY_FEEDS:
            filtered = filter_global_article_dedupe(filtered, seen_discovery_article_urls)
        write_json(OUTPUT_DIR / f"{feed_name}.json", filtered)
        final_feeds_payload[feed_name] = filtered

    update_meta_file(OUTPUT_DIR / "meta.json", final_feeds_payload)

    elapsed = round(time.time() - started_at, 2)
    logging.getLogger(__name__).info("Completed all feeds in %s seconds", elapsed)


if __name__ == "__main__":
    setup_logging()
    run_all()
