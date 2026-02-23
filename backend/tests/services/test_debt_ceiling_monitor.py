"""
Tests for backend/app/services/debt_ceiling_monitor.py

Tests the DebtCeilingMonitor service that checks weekly for new
US debt ceiling legislation using AI providers.
"""

import asyncio
import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from app.services.debt_ceiling_monitor import DebtCeilingMonitor


# ---------------------------------------------------------------------------
# DebtCeilingMonitor.__init__ / lifecycle tests
# ---------------------------------------------------------------------------

class TestDebtCeilingMonitorInit:
    """Tests for DebtCeilingMonitor initialization and lifecycle."""

    def test_init_defaults(self):
        """Happy path: monitor initializes with expected defaults."""
        monitor = DebtCeilingMonitor()
        assert monitor._running is False
        assert monitor._task is None
        assert monitor._last_check is None
        assert monitor._last_result is None

    @pytest.mark.asyncio
    async def test_start_sets_running(self):
        """Happy path: start sets running flag and creates task."""
        monitor = DebtCeilingMonitor()
        with patch.object(monitor, '_monitor_loop', new_callable=AsyncMock):
            with patch.object(monitor, '_load_cache'):
                await monitor.start()
                assert monitor._running is True
                assert monitor._task is not None
                # Clean up
                monitor._running = False
                monitor._task.cancel()
                try:
                    await monitor._task
                except (Exception, asyncio.CancelledError):
                    pass

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        """Edge case: calling start when already running does nothing."""
        monitor = DebtCeilingMonitor()
        monitor._running = True
        await monitor.start()
        # Task should not be created (still None since it was already "running")
        assert monitor._task is None

    @pytest.mark.asyncio
    async def test_stop_resets_state(self):
        """Happy path: stop resets running flag and cancels task."""
        monitor = DebtCeilingMonitor()
        monitor._running = True
        # Create a real future that can be awaited and cancelled
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        fut.set_result(None)
        monitor._task = fut

        await monitor.stop()

        assert monitor._running is False


# ---------------------------------------------------------------------------
# _load_cache / _save_cache tests
# ---------------------------------------------------------------------------

class TestCacheOperations:
    """Tests for DebtCeilingMonitor cache load/save."""

    def test_load_cache_from_valid_file(self, tmp_path):
        """Happy path: loads cache from valid JSON file."""
        monitor = DebtCeilingMonitor()
        cache_data = {
            "last_check": "2025-01-15T12:00:00",
            "last_result": {"new_legislation_found": False, "summary": "No changes"},
        }
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(json.dumps(cache_data))

        with patch('app.services.debt_ceiling_monitor.DEBT_CEILING_CHECK_CACHE', cache_file):
            monitor._load_cache()

        assert monitor._last_check == datetime.fromisoformat("2025-01-15T12:00:00")
        assert monitor._last_result["new_legislation_found"] is False

    def test_load_cache_missing_file(self, tmp_path):
        """Edge case: cache file does not exist."""
        monitor = DebtCeilingMonitor()
        cache_file = tmp_path / "nonexistent.json"

        with patch('app.services.debt_ceiling_monitor.DEBT_CEILING_CHECK_CACHE', cache_file):
            monitor._load_cache()

        assert monitor._last_check is None
        assert monitor._last_result is None

    def test_load_cache_corrupt_file(self, tmp_path):
        """Failure: cache file contains invalid JSON."""
        monitor = DebtCeilingMonitor()
        cache_file = tmp_path / "bad.json"
        cache_file.write_text("not valid json{{{")

        with patch('app.services.debt_ceiling_monitor.DEBT_CEILING_CHECK_CACHE', cache_file):
            # Should not raise
            monitor._load_cache()

        assert monitor._last_check is None

    def test_save_cache_writes_file(self, tmp_path):
        """Happy path: saves cache data to file."""
        monitor = DebtCeilingMonitor()
        monitor._last_check = datetime(2025, 6, 1, 10, 0, 0)
        monitor._last_result = {"new_legislation_found": True}

        cache_file = tmp_path / "cache.json"
        with patch('app.services.debt_ceiling_monitor.DEBT_CEILING_CHECK_CACHE', cache_file):
            monitor._save_cache()

        saved = json.loads(cache_file.read_text())
        assert saved["last_check"] == "2025-06-01T10:00:00"
        assert saved["last_result"]["new_legislation_found"] is True

    def test_save_cache_handles_write_error(self, tmp_path):
        """Failure: write error is caught and logged."""
        monitor = DebtCeilingMonitor()
        monitor._last_check = datetime.utcnow()

        # Use a directory path instead of file to cause write error
        bad_path = tmp_path / "nonexistent_dir" / "cache.json"
        with patch('app.services.debt_ceiling_monitor.DEBT_CEILING_CHECK_CACHE', bad_path):
            # Should not raise
            monitor._save_cache()


# ---------------------------------------------------------------------------
# _check_for_updates tests
# ---------------------------------------------------------------------------

class TestCheckForUpdates:
    """Tests for DebtCeilingMonitor._check_for_updates()."""

    @pytest.mark.asyncio
    @patch('app.services.debt_ceiling_monitor.DEBT_CEILING_HISTORY', [
        {"date": "2025-01-01", "amount_trillion": 36.1}
    ])
    async def test_no_new_legislation_found(self):
        """Happy path: AI reports no new legislation."""
        monitor = DebtCeilingMonitor()

        with patch.object(
            monitor, '_ai_check_debt_ceiling', new_callable=AsyncMock,
            return_value={"new_legislation_found": False, "summary": "No changes"}
        ):
            await monitor._check_for_updates()

        assert monitor._last_result is not None
        assert monitor._last_result["new_legislation_found"] is False

    @pytest.mark.asyncio
    @patch('app.services.debt_ceiling_monitor.DEBT_CEILING_HISTORY', [
        {"date": "2025-01-01", "amount_trillion": 36.1}
    ])
    async def test_new_legislation_found(self):
        """Happy path: AI reports new legislation detected."""
        monitor = DebtCeilingMonitor()

        with patch.object(
            monitor, '_ai_check_debt_ceiling', new_callable=AsyncMock,
            return_value={
                "new_legislation_found": True,
                "date": "2025-06-15",
                "amount_trillion": 40.0,
                "legislation": "Debt Ceiling Act of 2025",
                "summary": "New legislation passed",
            }
        ):
            await monitor._check_for_updates()

        assert monitor._last_result["new_legislation_found"] is True
        assert monitor._last_result["amount_trillion"] == pytest.approx(40.0)

    @pytest.mark.asyncio
    @patch('app.services.debt_ceiling_monitor.DEBT_CEILING_HISTORY', [])
    async def test_empty_history_uses_defaults(self):
        """Edge case: no debt ceiling history, uses defaults."""
        monitor = DebtCeilingMonitor()

        with patch.object(
            monitor, '_ai_check_debt_ceiling', new_callable=AsyncMock,
            return_value={"new_legislation_found": False, "summary": "No data"}
        ) as mock_ai:
            await monitor._check_for_updates()
            # Should be called with None values
            mock_ai.assert_awaited_once_with(None, None)

    @pytest.mark.asyncio
    async def test_ai_exception_caught(self):
        """Failure: AI check raises exception, caught and logged."""
        monitor = DebtCeilingMonitor()

        with patch.object(
            monitor, '_ai_check_debt_ceiling', new_callable=AsyncMock,
            side_effect=Exception("AI service down")
        ):
            # Should not raise
            await monitor._check_for_updates()


# ---------------------------------------------------------------------------
# _ai_check_debt_ceiling tests
# ---------------------------------------------------------------------------

class TestAiCheckDebtCeiling:
    """Tests for DebtCeilingMonitor._ai_check_debt_ceiling()."""

    @pytest.mark.asyncio
    @patch('app.services.debt_ceiling_monitor.get_ai_review_provider_from_db')
    @patch('app.services.debt_ceiling_monitor._call_claude')
    async def test_successful_claude_check(self, mock_claude, mock_provider):
        """Happy path: Claude returns valid JSON response."""
        mock_provider.return_value = "claude"
        mock_claude.return_value = json.dumps({
            "new_legislation_found": False,
            "summary": "No new legislation found",
        })

        monitor = DebtCeilingMonitor()
        result = await monitor._ai_check_debt_ceiling("2025-01-01", 36.1)

        assert result["new_legislation_found"] is False
        mock_claude.assert_awaited_once()

    @pytest.mark.asyncio
    @patch('app.services.debt_ceiling_monitor.get_ai_review_provider_from_db')
    @patch('app.services.debt_ceiling_monitor._call_openai')
    async def test_successful_openai_check_with_markdown(self, mock_openai, mock_provider):
        """Happy path: OpenAI returns JSON wrapped in markdown code block."""
        mock_provider.return_value = "openai"
        mock_openai.return_value = '```json\n{"new_legislation_found": true, "summary": "Found new act"}\n```'

        monitor = DebtCeilingMonitor()
        result = await monitor._ai_check_debt_ceiling("2025-01-01", 36.1)

        assert result["new_legislation_found"] is True

    @pytest.mark.asyncio
    @patch('app.services.debt_ceiling_monitor.get_ai_review_provider_from_db')
    async def test_unknown_provider_returns_default(self, mock_provider):
        """Edge case: unknown provider returns default result."""
        mock_provider.return_value = "unknown_ai"

        monitor = DebtCeilingMonitor()
        result = await monitor._ai_check_debt_ceiling("2025-01-01", 36.1)

        assert result["new_legislation_found"] is False
        assert "Unknown provider" in result["summary"]

    @pytest.mark.asyncio
    @patch('app.services.debt_ceiling_monitor.get_ai_review_provider_from_db')
    async def test_missing_api_key_returns_error(self, mock_provider):
        """Failure: ValueError (missing API key) returns error result."""
        mock_provider.side_effect = ValueError("No API key configured for claude")

        monitor = DebtCeilingMonitor()
        result = await monitor._ai_check_debt_ceiling("2025-01-01", 36.1)

        assert result["new_legislation_found"] is False
        assert "No API key" in result["summary"]

    @pytest.mark.asyncio
    @patch('app.services.debt_ceiling_monitor.get_ai_review_provider_from_db')
    @patch('app.services.debt_ceiling_monitor._call_claude')
    async def test_unparseable_response_returns_default(self, mock_claude, mock_provider):
        """Failure: AI returns non-JSON response."""
        mock_provider.return_value = "claude"
        mock_claude.return_value = "I don't understand the question."

        monitor = DebtCeilingMonitor()
        result = await monitor._ai_check_debt_ceiling("2025-01-01", 36.1)

        assert result["new_legislation_found"] is False
        assert result["summary"] == "Failed to check with AI"


# ---------------------------------------------------------------------------
# status property tests
# ---------------------------------------------------------------------------

class TestDebtCeilingMonitorStatus:
    """Tests for DebtCeilingMonitor.status property."""

    @patch('app.services.debt_ceiling_monitor.DEBT_CEILING_HISTORY', [
        {"date": "2025-01-01", "amount_trillion": 36.1}
    ])
    def test_status_initial(self):
        """Happy path: status before any check."""
        monitor = DebtCeilingMonitor()
        status = monitor.status

        assert status["running"] is False
        assert status["last_check"] is None
        assert status["last_result"] is None
        assert status["check_interval_days"] == 7
        assert status["current_ceiling_trillion"] == pytest.approx(36.1)

    @patch('app.services.debt_ceiling_monitor.DEBT_CEILING_HISTORY', [])
    def test_status_empty_history(self):
        """Edge case: no debt ceiling history data."""
        monitor = DebtCeilingMonitor()
        status = monitor.status

        assert status["current_ceiling_trillion"] is None

    def test_status_after_check(self):
        """Happy path: status after a check has run."""
        monitor = DebtCeilingMonitor()
        monitor._running = True
        monitor._last_check = datetime(2025, 6, 1, 10, 0, 0)
        monitor._last_result = {"new_legislation_found": False}

        with patch('app.services.debt_ceiling_monitor.DEBT_CEILING_HISTORY', [
            {"date": "2025-01-01", "amount_trillion": 36.1}
        ]):
            status = monitor.status

        assert status["running"] is True
        assert status["last_check"] == "2025-06-01T10:00:00"
        assert status["last_result"]["new_legislation_found"] is False
