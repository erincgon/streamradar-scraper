"""Platform feed'leri: günlük Top 10 film + Top 10 dizi → `output/*.json`.

- Netflix: resmi Tudum Top 10 (Türkiye)
- Disney+ / Prime Video / Max: JustWatch TRENDING (TR)
"""

from __future__ import annotations

from scrapers.official_platforms import (
    JustWatchDisneyPlusScraper as DisneyPlusScraper,
    JustWatchMaxScraper as HBOMaxScraper,
    JustWatchPrimeVideoScraper as PrimeVideoScraper,
    NetflixTudumTop10Scraper as NetflixScraper,
)

__all__ = ["NetflixScraper", "DisneyPlusScraper", "PrimeVideoScraper", "HBOMaxScraper"]
