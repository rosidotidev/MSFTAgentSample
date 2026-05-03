"""Configurable logging for the wiki system.

Reads WIKI_LOG_LEVEL from environment. Levels:
  ERROR  — only failures
  WARNING — failures + warnings
  INFO   — executor start/end + summaries (default)
  DEBUG  — full payloads in/out of each executor + timing
"""

import logging
import os


def setup_logging() -> None:
    """Configure logging based on WIKI_LOG_LEVEL env var."""
    level_name = os.environ.get("WIKI_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(name)s — %(message)s",
        force=True,
    )
    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
