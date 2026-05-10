"""Tests for the Console output system."""

import os

import pytest

from afw_core.console import Console, Verbosity


@pytest.fixture
def _no_color(monkeypatch):
    """Disable ANSI colours so captured output is plain text."""
    import afw_core.console as _mod
    monkeypatch.setattr(_mod, "_SUPPORTS_COLOR", False)
    monkeypatch.setattr(_mod, "_RESET", "")
    monkeypatch.setattr(_mod, "_BOLD", "")
    monkeypatch.setattr(_mod, "_DIM", "")
    monkeypatch.setattr(_mod, "_CYAN", "")
    monkeypatch.setattr(_mod, "_GREEN", "")
    monkeypatch.setattr(_mod, "_YELLOW", "")
    monkeypatch.setattr(_mod, "_RED", "")
    monkeypatch.setattr(_mod, "_MAGENTA", "")


@pytest.fixture
def con(_no_color):
    """A fresh Console instance with colours disabled."""
    return Console()


# ---------------------------------------------------------------------------
# Verbosity reading
# ---------------------------------------------------------------------------

class TestVerbosityReading:

    def test_default_is_normal(self, monkeypatch):
        monkeypatch.delenv("WIKI_VERBOSITY", raising=False)
        c = Console()
        assert c.verbosity == Verbosity.NORMAL

    def test_reads_env_silent(self, monkeypatch):
        monkeypatch.setenv("WIKI_VERBOSITY", "0")
        c = Console()
        assert c.verbosity == Verbosity.SILENT

    def test_reads_env_verbose(self, monkeypatch):
        monkeypatch.setenv("WIKI_VERBOSITY", "2")
        c = Console()
        assert c.verbosity == Verbosity.VERBOSE

    def test_invalid_env_falls_back_to_normal(self, monkeypatch):
        monkeypatch.setenv("WIKI_VERBOSITY", "banana")
        c = Console()
        assert c.verbosity == Verbosity.NORMAL

    def test_setter(self, con):
        con.verbosity = 0
        assert con.verbosity == Verbosity.SILENT
        con.verbosity = Verbosity.VERBOSE
        assert con.verbosity == Verbosity.VERBOSE


# ---------------------------------------------------------------------------
# SILENT mode — only success/warning/error/result visible
# ---------------------------------------------------------------------------

class TestSilentMode:

    def test_banner_suppressed(self, con, capsys):
        con.verbosity = Verbosity.SILENT
        con.banner("TEST")
        assert capsys.readouterr().out == ""

    def test_step_suppressed(self, con, capsys):
        con.verbosity = Verbosity.SILENT
        con.step("doing something")
        assert capsys.readouterr().out == ""

    def test_detail_suppressed(self, con, capsys):
        con.verbosity = Verbosity.SILENT
        con.detail("low-level info")
        assert capsys.readouterr().out == ""

    def test_info_suppressed(self, con, capsys):
        con.verbosity = Verbosity.SILENT
        con.info("some info")
        assert capsys.readouterr().out == ""

    def test_success_visible(self, con, capsys):
        con.verbosity = Verbosity.SILENT
        con.success("done")
        out = capsys.readouterr().out
        assert "done" in out
        assert "✔" in out

    def test_warning_visible(self, con, capsys):
        con.verbosity = Verbosity.SILENT
        con.warning("careful")
        out = capsys.readouterr().out
        assert "careful" in out

    def test_error_visible(self, con, capsys):
        con.verbosity = Verbosity.SILENT
        con.error("bad")
        out = capsys.readouterr().out
        assert "bad" in out
        assert "✗" in out

    def test_result_visible(self, con, capsys):
        con.verbosity = Verbosity.SILENT
        con.result("the answer is 42")
        out = capsys.readouterr().out
        assert "the answer is 42" in out


# ---------------------------------------------------------------------------
# NORMAL mode
# ---------------------------------------------------------------------------

class TestNormalMode:

    def test_banner_visible(self, con, capsys):
        con.verbosity = Verbosity.NORMAL
        con.banner("INGEST")
        out = capsys.readouterr().out
        assert "INGEST" in out
        assert "╭" in out

    def test_step_visible(self, con, capsys):
        con.verbosity = Verbosity.NORMAL
        con.step("Reading sources...")
        out = capsys.readouterr().out
        assert "Reading sources..." in out
        assert "⏵" in out

    def test_detail_suppressed(self, con, capsys):
        con.verbosity = Verbosity.NORMAL
        con.detail("chunk-level noise")
        assert capsys.readouterr().out == ""

    def test_info_visible(self, con, capsys):
        con.verbosity = Verbosity.NORMAL
        con.info("3 pages created")
        out = capsys.readouterr().out
        assert "3 pages created" in out


# ---------------------------------------------------------------------------
# VERBOSE mode
# ---------------------------------------------------------------------------

class TestVerboseMode:

    def test_banner_visible(self, con, capsys):
        con.verbosity = Verbosity.VERBOSE
        con.banner("TEST")
        assert "TEST" in capsys.readouterr().out

    def test_step_visible(self, con, capsys):
        con.verbosity = Verbosity.VERBOSE
        con.step("Phase 1")
        assert "Phase 1" in capsys.readouterr().out

    def test_detail_visible(self, con, capsys):
        con.verbosity = Verbosity.VERBOSE
        con.detail("internal detail")
        out = capsys.readouterr().out
        assert "internal detail" in out

    def test_info_visible(self, con, capsys):
        con.verbosity = Verbosity.VERBOSE
        con.info("summary line")
        assert "summary line" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_banner_end_no_crash(self, con, capsys):
        con.verbosity = Verbosity.NORMAL
        con.banner_end()
        # just a blank line
        assert capsys.readouterr().out.strip() == ""

    def test_empty_messages(self, con, capsys):
        """Empty strings should not crash."""
        con.verbosity = Verbosity.VERBOSE
        con.step("")
        con.detail("")
        con.info("")
        con.success("")
        con.warning("")
        con.error("")
        con.result("")
        # No assertion needed — just verifying no exceptions

    def test_verbosity_enum_values(self):
        assert Verbosity.SILENT == 0
        assert Verbosity.NORMAL == 1
        assert Verbosity.VERBOSE == 2
