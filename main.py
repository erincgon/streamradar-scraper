"""StreamRadar scraping entrypoint.

Platform çıktıları (`netflix`, `disney_plus`, `prime_video`, `hbo_max`) artık her servisin
**resmî liste / basın kaynağından** çekilir (Netflix About “Yeni İçerikler”, Disney+ vitrin kartları,
About Amazon Entertainment RSS içinde Prime Video odaklı girdiler, WBD Max/HBO ile ilgili basın
duyuruları). Trending, upcoming ve sinema için Google News RSS araması kullanılmaya devam eder.

Feed map (dosya adı): trending, upcoming; netflix, disney_plus, prime_video, hbo_max;
cinema_releases.
"""

from __future__ import annotations

import logging
import time

from config import OUTPUT_DIR
from scrapers import (
    CinemaReleasesScraper,
    DisneyPlusScraper,
    HBOMaxScraper,
    NetflixScraper,
    PrimeVideoScraper,
    TrendingNewReleasesScraper,
    UpcomingReleasesScraper,
)
from utils.json_utils import write_json
from utils.logging_setup import setup_logging
from utils.metadata import update_meta_file
from utils.pipeline import apply_cross_platform_dedupe, filter_global_article_dedupe, run_feed

# Global article dedupe only within these groups so discovery feeds do not strip platform rows
# that cite the same publisher URL (different feed intent).
PLATFORM_FEEDS = frozenset({"netflix", "disney_plus", "prime_video", "hbo_max"})
DISCOVERY_FEEDS = frozenset({"trending", "upcoming"})
# Cinema shares trade-press URLs with discovery feeds — do not strip via the same dedupe pool.


def run_all() -> None:
    feed_map = {
        "trending": [TrendingNewReleasesScraper()],
        "upcoming": [UpcomingReleasesScraper()],
        "netflix": [NetflixScraper(locale="tr")],
        "disney_plus": [DisneyPlusScraper()],
        "prime_video": [PrimeVideoScraper()],
        "hbo_max": [HBOMaxScraper(locale_prefix="tr")],
        "cinema_releases": [CinemaReleasesScraper()],
    }

    started_at = time.time()
    taken_cross_platform_keys: set[str] = set()
    seen_discovery_article_urls: set[str] = set()
    seen_platform_article_urls: set[str] = set()
    final_feeds_payload: dict[str, list[dict[str, object]]] = {}
    for feed_name, scraper_objects in feed_map.items():
        payload = run_feed(feed_name, scraper_objects)
        filtered = apply_cross_platform_dedupe(feed_name, payload, taken_cross_platform_keys)
        if feed_name in PLATFORM_FEEDS:
            filtered = filter_global_article_dedupe(filtered, seen_platform_article_urls)
        elif feed_name in DISCOVERY_FEEDS:
            filtered = filter_global_article_dedupe(filtered, seen_discovery_article_urls)
        write_json(OUTPUT_DIR / f"{feed_name}.json", filtered)
        final_feeds_payload[feed_name] = filtered

    update_meta_file(OUTPUT_DIR / "meta.json", final_feeds_payload)

    elapsed = round(time.time() - started_at, 2)
    logging.getLogger(__name__).info("Completed all feeds in %s seconds", elapsed)


if __name__ == "__main__":
    setup_logging()
    run_all()
