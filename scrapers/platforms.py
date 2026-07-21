"""Platform feed'leri: JustWatch popüler listelerinden `output/*.json`.

Her platform için top 10 film + top 10 dizi (toplam 20).
Ayrıntılı parser mantığı için `scrapers.official_platforms` modülüne bakın.
"""

from __future__ import annotations

from scrapers.official_platforms import (
    JustWatchDisneyPlusScraper as DisneyPlusScraper,
    JustWatchMaxScraper as HBOMaxScraper,
    JustWatchNetflixScraper as NetflixScraper,
    JustWatchPrimeVideoScraper as PrimeVideoScraper,
)

__all__ = ["NetflixScraper", "DisneyPlusScraper", "PrimeVideoScraper", "HBOMaxScraper"]
