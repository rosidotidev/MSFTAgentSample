"""Configurable logging for the wiki system.

Reads from environment:
  WIKI_LOG_LEVEL — standard log verbosity (ERROR|WARNING|INFO|DEBUG). Default: INFO
  WIKI_MONITOR  — if "true", dump intermediate artifacts (extraction, plan, writer input)
                  to <WIKI_ROOT_DIR>/tmp/diagnostics/ for post-mortem inspection.
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


def is_monitor_enabled() -> bool:
    """Check if WIKI_MONITOR mode is active."""
    return os.environ.get("WIKI_MONITOR", "").lower() in ("true", "1", "yes")


def get_diagnostics_dir() -> str:
    """Return the diagnostics dump directory, creating it if needed."""
    base = os.environ.get(
        "WIKI_ROOT_DIR",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    dump_dir = os.path.join(base, "tmp", "diagnostics")
    os.makedirs(dump_dir, exist_ok=True)
    return dump_dir
