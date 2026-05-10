"""Platform feed’leri: resmî vitrin ve basın kaynaklarından `output/*.json`.

Ayrıntılı parser mantığı için `scrapers.official_platforms` modülüne bakın.
"""

from __future__ import annotations

from scrapers.official_platforms import (
    AboutAmazonPrimeVideoRSSScraper as PrimeVideoScraper,
    DisneyOnDisneyPlusRecentScraper as DisneyPlusScraper,
    NetflixAboutNewWatchScraper as NetflixScraper,
    WBDPressMaxMediaReleasesScraper as HBOMaxScraper,
)

__all__ = ["NetflixScraper", "DisneyPlusScraper", "PrimeVideoScraper", "HBOMaxScraper"]
