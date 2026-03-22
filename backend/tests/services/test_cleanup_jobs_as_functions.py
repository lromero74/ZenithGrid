"""
Tests for cleanup_jobs functions as plain async functions (post-APScheduler migration).

TDD: Written before refactoring cleanup_jobs.py to remove the while-True loops.
Each function should:
- Run once and return cleanly (happy path)
- Log and NOT re-raise on DB error (failure case) — APScheduler reschedules on return
"""

import logging
from unittest import mock

import pytest


@pytest.fixture
def mock_session_maker():
    """Mock session_maker that returns a context-manager-compatible async session."""
    mock_session = mock.AsyncMock()
    mock_session.execute = mock.AsyncMock(return_value=mock.MagicMock(fetchall=lambda: [], scalars=mock.MagicMock(return_value=mock.MagicMock(all=lambda: [], first=mock.MagicMock(return_value=None)))))
    mock_session.commit = mock.AsyncMock()

    mock_ctx = mock.AsyncMock()
    mock_ctx.__aenter__ = mock.AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = mock.AsyncMock(return_value=False)

    mock_sm = mock.MagicMock(return_value=mock_ctx)
    return mock_sm, mock_session


class TestCleanupOldDecisionLogs:
    @pytest.mark.asyncio
    async def test_runs_without_error(self, mock_session_maker):
        """Happy path: function completes without raising."""
        from app.cleanup_jobs import cleanup_old_decision_logs
        sm, session = mock_session_maker
        # Should return cleanly
        await cleanup_old_decision_logs(session_maker=sm)

    @pytest.mark.asyncio
    async def test_handles_db_error_without_reraise(self, caplog):
        """Failure: DB raises → function logs and returns (does not reraise)."""
        from app.cleanup_jobs import cleanup_old_decision_logs

        async def boom():
            raise RuntimeError("DB failure")

        mock_ctx = mock.MagicMock()
        mock_ctx.__aenter__ = mock.AsyncMock(side_effect=RuntimeError("DB failure"))
        mock_ctx.__aexit__ = mock.AsyncMock(return_value=False)
        bad_sm = mock.MagicMock(return_value=mock_ctx)

        # Should NOT raise
        with caplog.at_level(logging.ERROR):
            await cleanup_old_decision_logs(session_maker=bad_sm)
        assert any("decision log" in r.message.lower() or "error" in r.message.lower()
                   for r in caplog.records), "Expected an error log entry"


class TestCleanupFailedConditionLogs:
    @pytest.mark.asyncio
    async def test_runs_without_error(self, mock_session_maker):
        """Happy path: function completes without raising."""
        from app.cleanup_jobs import cleanup_failed_condition_logs
        sm, session = mock_session_maker
        await cleanup_failed_condition_logs(session_maker=sm)

    @pytest.mark.asyncio
    async def test_handles_db_error_without_reraise(self, caplog):
        """Failure: DB raises → function logs and returns."""
        from app.cleanup_jobs import cleanup_failed_condition_logs

        mock_ctx = mock.MagicMock()
        mock_ctx.__aenter__ = mock.AsyncMock(side_effect=RuntimeError("DB failure"))
        mock_ctx.__aexit__ = mock.AsyncMock(return_value=False)
        bad_sm = mock.MagicMock(return_value=mock_ctx)

        with caplog.at_level(logging.ERROR):
            await cleanup_failed_condition_logs(session_maker=bad_sm)
        assert any("error" in r.message.lower() for r in caplog.records)


class TestCleanupOldFailedOrders:
    @pytest.mark.asyncio
    async def test_runs_without_error(self, mock_session_maker):
        """Happy path: function completes without raising."""
        from app.cleanup_jobs import cleanup_old_failed_orders
        sm, session = mock_session_maker
        await cleanup_old_failed_orders(session_maker=sm)

    @pytest.mark.asyncio
    async def test_handles_db_error_without_reraise(self, caplog):
        """Failure: DB raises → function logs and returns."""
        from app.cleanup_jobs import cleanup_old_failed_orders

        mock_ctx = mock.MagicMock()
        mock_ctx.__aenter__ = mock.AsyncMock(side_effect=RuntimeError("DB failure"))
        mock_ctx.__aexit__ = mock.AsyncMock(return_value=False)
        bad_sm = mock.MagicMock(return_value=mock_ctx)

        with caplog.at_level(logging.ERROR):
            await cleanup_old_failed_orders(session_maker=bad_sm)
        assert any("error" in r.message.lower() for r in caplog.records)


class TestCleanupExpiredRevokedTokens:
    @pytest.mark.asyncio
    async def test_runs_without_error(self, mock_session_maker):
        """Happy path: function completes without raising."""
        from app.cleanup_jobs import cleanup_expired_revoked_tokens
        sm, session = mock_session_maker
        await cleanup_expired_revoked_tokens(session_maker=sm)

    @pytest.mark.asyncio
    async def test_handles_db_error_without_reraise(self, caplog):
        """Failure: DB raises → function logs and returns."""
        from app.cleanup_jobs import cleanup_expired_revoked_tokens

        mock_ctx = mock.MagicMock()
        mock_ctx.__aenter__ = mock.AsyncMock(side_effect=RuntimeError("DB failure"))
        mock_ctx.__aexit__ = mock.AsyncMock(return_value=False)
        bad_sm = mock.MagicMock(return_value=mock_ctx)

        with caplog.at_level(logging.ERROR):
            await cleanup_expired_revoked_tokens(session_maker=bad_sm)
        assert any("error" in r.message.lower() for r in caplog.records)


class TestCleanupOldReports:
    @pytest.mark.asyncio
    async def test_runs_without_error(self, mock_session_maker):
        """Happy path: function completes without raising."""
        from app.cleanup_jobs import cleanup_old_reports
        sm, session = mock_session_maker
        await cleanup_old_reports(session_maker=sm)

    @pytest.mark.asyncio
    async def test_handles_db_error_without_reraise(self, caplog):
        """Failure: DB raises → function logs and returns."""
        from app.cleanup_jobs import cleanup_old_reports

        mock_ctx = mock.MagicMock()
        mock_ctx.__aenter__ = mock.AsyncMock(side_effect=RuntimeError("DB failure"))
        mock_ctx.__aexit__ = mock.AsyncMock(return_value=False)
        bad_sm = mock.MagicMock(return_value=mock_ctx)

        with caplog.at_level(logging.ERROR):
            await cleanup_old_reports(session_maker=bad_sm)
        assert any("error" in r.message.lower() for r in caplog.records)


class TestCleanupExpiredSessions:
    @pytest.mark.asyncio
    async def test_runs_without_error(self, mock_session_maker):
        """Happy path: function completes without raising."""
        from app.cleanup_jobs import cleanup_expired_sessions
        sm, session = mock_session_maker
        # Patch the session_service import that happens inside the function
        with mock.patch("app.cleanup_jobs.expire_all_stale_sessions", new_callable=mock.AsyncMock,
                        return_value=0):
            await cleanup_expired_sessions(session_maker=sm)

    @pytest.mark.asyncio
    async def test_handles_db_error_without_reraise(self, caplog):
        """Failure: DB raises → function logs and returns."""
        from app.cleanup_jobs import cleanup_expired_sessions

        mock_ctx = mock.MagicMock()
        mock_ctx.__aenter__ = mock.AsyncMock(side_effect=RuntimeError("DB failure"))
        mock_ctx.__aexit__ = mock.AsyncMock(return_value=False)
        bad_sm = mock.MagicMock(return_value=mock_ctx)

        with caplog.at_level(logging.ERROR):
            await cleanup_expired_sessions(session_maker=bad_sm)
        assert any("error" in r.message.lower() for r in caplog.records)


class TestCleanupOldRateLimitAttempts:
    @pytest.mark.asyncio
    async def test_runs_without_error(self, mock_session_maker):
        """Happy path: function completes without raising."""
        from app.cleanup_jobs import cleanup_old_rate_limit_attempts
        sm, session = mock_session_maker
        await cleanup_old_rate_limit_attempts(session_maker=sm)

    @pytest.mark.asyncio
    async def test_handles_db_error_without_reraise(self, caplog):
        """Failure: DB raises → function logs and returns."""
        from app.cleanup_jobs import cleanup_old_rate_limit_attempts

        mock_ctx = mock.MagicMock()
        mock_ctx.__aenter__ = mock.AsyncMock(side_effect=RuntimeError("DB failure"))
        mock_ctx.__aexit__ = mock.AsyncMock(return_value=False)
        bad_sm = mock.MagicMock(return_value=mock_ctx)

        with caplog.at_level(logging.ERROR):
            await cleanup_old_rate_limit_attempts(session_maker=bad_sm)
        assert any("error" in r.message.lower() for r in caplog.records)
