"""Logging setup helpers."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from config import LOG_DIR


def setup_logging() -> None:
    """Configure console and file logging once."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    if logger.handlers:
        return

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        LOG_DIR / "scraper.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
