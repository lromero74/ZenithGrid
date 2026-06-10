"""
Tests for the background monitor loops in app.main.

Focus: corruption-aware logging in run_order_reconciliation_monitor().
A PostgreSQL bad-block error must produce one concise WARNING per cycle —
including on the startup pass, which previously also emitted the full
"Startup order reconciliation error" ERROR line.
"""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import OperationalError


class _StopLoop(BaseException):
    """Raised from the patched sleep to break out of an infinite monitor loop.

    Derives from BaseException so the loop's ``except Exception`` can't catch it.
    """


def _corruption_error():
    return OperationalError(
        "SELECT", {},
        Exception('could not read block 3 in file "base/1/2": Input/output error'),
    )


def _session_maker_raising(exc):
    """async_session_maker stand-in whose session raises exc on execute."""
    session = MagicMock()
    session.execute = AsyncMock(side_effect=exc)
    maker = MagicMock()
    maker.return_value.__aenter__ = AsyncMock(return_value=session)
    maker.return_value.__aexit__ = AsyncMock(return_value=False)
    return maker


async def _run_one_cycle(monkeypatch, exc):
    """Run one iteration of the reconciliation loop with execute raising exc."""
    from app.main import run_order_reconciliation_monitor

    monkeypatch.setattr("app.database.async_session_maker", _session_maker_raising(exc))
    monkeypatch.setattr("app.main.asyncio.sleep", AsyncMock(side_effect=_StopLoop))

    with pytest.raises(_StopLoop):
        await run_order_reconciliation_monitor()


class TestReconciliationLoopCorruptionLogging:
    @pytest.mark.asyncio
    async def test_startup_corruption_logs_warning_only(self, monkeypatch, caplog):
        """Corruption on the startup pass → one WARNING, zero ERROR records (happy path)."""
        with caplog.at_level(logging.DEBUG, logger="app.main"):
            await _run_one_cycle(monkeypatch, _corruption_error())

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("Database corruption in order reconciliation" in r.getMessage() for r in warnings)
        assert errors == []

    @pytest.mark.asyncio
    async def test_startup_real_error_still_logs_startup_error(self, monkeypatch, caplog):
        """A genuine bug on the startup pass keeps the startup ERROR line (failure case)."""
        with caplog.at_level(logging.DEBUG, logger="app.main"):
            await _run_one_cycle(monkeypatch, RuntimeError("boom"))

        errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("Startup order reconciliation error" in m for m in errors)
        assert any("Error in order reconciliation monitor loop" in m for m in errors)

    @pytest.mark.asyncio
    async def test_corruption_warning_includes_original_message(self, monkeypatch, caplog):
        """The single WARNING still carries the underlying PG message (edge case)."""
        with caplog.at_level(logging.DEBUG, logger="app.main"):
            await _run_one_cycle(monkeypatch, _corruption_error())

        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("could not read block" in m for m in warnings)
