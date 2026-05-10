"""Centralized console output with verbosity levels.

Reads from environment:
  WIKI_VERBOSITY — 0 (SILENT), 1 (NORMAL, default), 2 (VERBOSE).

Provides a singleton ``console`` instance with colour-coded, structured
output methods.  No external dependencies — pure ANSI escape codes.
"""

from __future__ import annotations

import os
import sys
from enum import IntEnum


class Verbosity(IntEnum):
    SILENT = 0
    NORMAL = 1
    VERBOSE = 2


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

_SUPPORTS_COLOR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _ansi(code: str) -> str:
    return f"\033[{code}m" if _SUPPORTS_COLOR else ""


_RESET = _ansi("0")
_BOLD = _ansi("1")
_DIM = _ansi("2")
_CYAN = _ansi("36")
_GREEN = _ansi("32")
_YELLOW = _ansi("33")
_RED = _ansi("31")
_MAGENTA = _ansi("35")


# ---------------------------------------------------------------------------
# Console
# ---------------------------------------------------------------------------


class Console:
    """Structured, colour-coded console output with verbosity gating."""

    def __init__(self) -> None:
        self._verbosity = self._read_verbosity()

    # -- public properties --------------------------------------------------

    @property
    def verbosity(self) -> Verbosity:
        return self._verbosity

    @verbosity.setter
    def verbosity(self, value: int | Verbosity) -> None:
        self._verbosity = Verbosity(value)

    # -- output methods -----------------------------------------------------

    def banner(self, title: str) -> None:
        """Top-level pipeline banner.  Shown at NORMAL+."""
        if self._verbosity < Verbosity.NORMAL:
            return
        width = len(title) + 6
        self._print(f"\n{_CYAN}{_BOLD}╭{'─' * width}╮{_RESET}")
        self._print(f"{_CYAN}{_BOLD}│   {title}   │{_RESET}")
        self._print(f"{_CYAN}{_BOLD}╰{'─' * width}╯{_RESET}")
        self._print("")

    def banner_end(self) -> None:
        """Closing line (visual only).  Shown at NORMAL+."""
        if self._verbosity < Verbosity.NORMAL:
            return
        self._print("")

    def step(self, msg: str) -> None:
        """A major pipeline phase (e.g. 'Scanning sources...').  NORMAL+."""
        if self._verbosity < Verbosity.NORMAL:
            return
        self._print(f"{_CYAN}⏵ {msg}{_RESET}")

    def detail(self, msg: str) -> None:
        """Verbose-only detail inside a step."""
        if self._verbosity < Verbosity.VERBOSE:
            return
        self._print(f"  {_DIM}{msg}{_RESET}")

    def info(self, msg: str) -> None:
        """Secondary info line inside a step.  NORMAL+."""
        if self._verbosity < Verbosity.NORMAL:
            return
        self._print(f"  {msg}")

    def success(self, msg: str) -> None:
        """Green check — shown at ALL verbosity levels (including SILENT)."""
        self._print(f"{_GREEN}✔ {msg}{_RESET}")

    def warning(self, msg: str) -> None:
        """Yellow warning — shown at ALL levels."""
        self._print(f"{_YELLOW}⚠ {msg}{_RESET}")

    def error(self, msg: str) -> None:
        """Red error — shown at ALL levels."""
        self._print(f"{_RED}✗ {msg}{_RESET}")

    def result(self, msg: str) -> None:
        """Final result / answer block — shown at ALL levels."""
        self._print(msg)

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _read_verbosity() -> Verbosity:
        raw = os.environ.get("WIKI_VERBOSITY", "1")
        try:
            return Verbosity(int(raw))
        except (ValueError, KeyError):
            return Verbosity.NORMAL

    @staticmethod
    def _print(text: str) -> None:
        print(text, flush=True)


# Singleton — import ``console`` from this module.
console = Console()
