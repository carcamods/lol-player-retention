"""Logging in the project-wide format: `TIMESTAMP [lolret.module] [LEVEL] message`.

Timestamps are UTC ISO-8601. Every module gets its logger from `get_logger(__name__)`,
and the CLI calls `configure_logging()` once at start-up.
"""

import logging
import time

from lolret.config import PROJECT_NAME

LOG_FORMAT = "%(asctime)s [%(name)s] [%(levelname)s] %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger(PROJECT_NAME)
    root.setLevel(level.upper())
    if not root.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
        formatter.converter = time.gmtime
        handler.setFormatter(formatter)
        root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    if name != PROJECT_NAME and not name.startswith(f"{PROJECT_NAME}."):
        name = f"{PROJECT_NAME}.{name}"
    return logging.getLogger(name)
