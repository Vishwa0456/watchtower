"""Logging configuration. Logs to console and a rotating file so a
long-running monitor doesn't fill the disk with its own logs - which
would be an embarrassing bug for a *disk monitoring* tool to have.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler


def setup_logging(level: str = "INFO", log_path: str = "watchtower.log") -> None:
    logger = logging.getLogger("watchtower")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
