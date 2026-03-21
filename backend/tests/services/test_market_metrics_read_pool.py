"""
Tests that market_metrics_service uses the read session maker for its
read-only DB operations (metric history queries).

Note: record_metric_snapshot() and prune_old_snapshots() are WRITE operations
(INSERT/DELETE + commit) and correctly stay on the write pool (async_session_maker).
Only get_metric_history_data() is a pure read and belongs on the read pool.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestMarketMetricsUsesReadSessionMaker:
    """market_metrics_service must import and use read_async_session_maker for reads."""

    def test_module_imports_read_async_session_maker(self):
        """Happy path: the service imports read_async_session_maker from app.database."""
        import inspect
        import app.services.market_metrics_service as mod

        src = inspect.getsource(mod)
        assert "read_async_session_maker" in src, (
            "market_metrics_service.py must import and use read_async_session_maker"
        )

    def test_get_metric_history_data_uses_read_session_maker(self):
        """Happy path: get_metric_history_data opens a session via read_async_session_maker."""
        import inspect
        import app.services.market_metrics_service as mod

        src = inspect.getsource(mod.get_metric_history_data)
        assert "read_async_session_maker" in src, (
            "get_metric_history_data must use read_async_session_maker for its DB read"
        )

    def test_record_snapshot_still_uses_write_session_maker(self):
        """Edge case: record_metric_snapshot is a WRITE op — must use write async_session_maker."""
        import inspect
        import app.services.market_metrics_service as mod

        src = inspect.getsource(mod.record_metric_snapshot)
        assert "async_session_maker" in src, (
            "record_metric_snapshot must use the write pool (it does INSERTs)"
        )


class TestMarketMetricsHistoryUsesReadDb:
    """get_metric_history_data uses the read session via read_async_session_maker."""

    @pytest.mark.asyncio
    @patch("app.services.market_metrics_service.read_async_session_maker")
    async def test_get_metric_history_data_opens_read_session(self, mock_session_maker):
        """Happy path: get_metric_history_data opens a session via read_async_session_maker."""
        from app.services.market_metrics_service import get_metric_history_data

        mock_session = AsyncMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        await get_metric_history_data("fear_greed_index", days=7, max_points=100)

        mock_session_maker.assert_called_once()
