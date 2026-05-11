"""Platform feed'leri: resmî vitrin ve basın kaynaklarından `output/*.json`.

Ayrıntılı parser mantığı için `scrapers.official_platforms` modülüne bakın.
"""

from __future__ import annotations

from scrapers.official_platforms import (
    DisneyOnDisneyPlusRecentScraper as DisneyPlusScraper,
    JustWatchMaxScraper as HBOMaxScraper,
    JustWatchPrimeVideoScraper as PrimeVideoScraper,
    NetflixAboutNewWatchScraper as NetflixScraper,
)

__all__ = ["NetflixScraper", "DisneyPlusScraper", "PrimeVideoScraper", "HBOMaxScraper"]
