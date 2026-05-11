"""Scraper package exports."""

from scrapers.cinema import CinemaReleasesScraper, IMDbBoxOfficeScraper
from scrapers.imdb_trending import IMDbTrendingScraper
from scrapers.platforms import DisneyPlusScraper, HBOMaxScraper, NetflixScraper, PrimeVideoScraper
from scrapers.trending import TrendingNewReleasesScraper
from scrapers.upcoming import UpcomingReleasesScraper

__all__ = [
    "IMDbTrendingScraper",
    "IMDbBoxOfficeScraper",
    "TrendingNewReleasesScraper",
    "UpcomingReleasesScraper",
    "NetflixScraper",
    "DisneyPlusScraper",
    "PrimeVideoScraper",
    "HBOMaxScraper",
    "CinemaReleasesScraper",
]
