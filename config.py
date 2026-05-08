"""Central application configuration for StreamRadar scrapers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = BASE_DIR / "logs"


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration values used across modules."""

    request_timeout_seconds: int = 20
    request_retries: int = 3
    backoff_factor: float = 0.75
    min_rate_limit_seconds: float = 0.5
    max_rate_limit_seconds: float = 1.5
    max_items_per_feed: int = 100


APP_CONFIG = AppConfig()
