"""Scraper package exports."""

from scrapers.cinema import CinemaReleasesScraper
from scrapers.imdb_trending import IMDbTrendingScraper
from scrapers.platforms import DisneyPlusScraper, HBOMaxScraper, NetflixScraper, PrimeVideoScraper
from scrapers.upcoming import UpcomingReleasesScraper

__all__ = [
    "IMDbTrendingScraper",
    "UpcomingReleasesScraper",
    "NetflixScraper",
    "DisneyPlusScraper",
    "PrimeVideoScraper",
    "HBOMaxScraper",
    "CinemaReleasesScraper",
]
