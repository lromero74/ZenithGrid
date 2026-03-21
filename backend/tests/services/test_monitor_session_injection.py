"""
Tests for session_maker injection on class-based monitors that move to Tier 2/3.

Verifies:
1. set_session_maker() / _get_sm() pattern works correctly for each monitor
2. Falls back to app.database.async_session_maker when no injection
"""


class TestAutoBuyMonitorInjection:
    """AutoBuyMonitor session maker injection."""

    def test_auto_buy_monitor_uses_injected_session_maker(self):
        """Happy path: set_session_maker() is returned by _get_sm()."""
        from app.services.auto_buy_monitor import AutoBuyMonitor

        mock_sm = object()
        monitor = AutoBuyMonitor()
        monitor.set_session_maker(mock_sm)
        assert monitor._get_sm() is mock_sm

    def test_auto_buy_monitor_falls_back_to_default_session_maker(self):
        """Edge case: _get_sm() returns default when no injected SM."""
        from app.database import async_session_maker
        from app.services.auto_buy_monitor import AutoBuyMonitor

        monitor = AutoBuyMonitor()
        assert monitor._get_sm() is async_session_maker


class TestRebalanceMonitorInjection:
    """RebalanceMonitor session maker injection."""

    def test_rebalance_monitor_uses_injected_session_maker(self):
        """Happy path: set_session_maker() is returned by _get_sm()."""
        from app.services.rebalance_monitor import RebalanceMonitor

        mock_sm = object()
        monitor = RebalanceMonitor()
        monitor.set_session_maker(mock_sm)
        assert monitor._get_sm() is mock_sm

    def test_rebalance_monitor_falls_back_to_default_session_maker(self):
        """Edge case: _get_sm() returns default when no injected SM."""
        from app.database import async_session_maker
        from app.services.rebalance_monitor import RebalanceMonitor

        monitor = RebalanceMonitor()
        assert monitor._get_sm() is async_session_maker


class TestTradingPairMonitorInjection:
    """TradingPairMonitor session maker injection."""

    def test_trading_pair_monitor_uses_injected_session_maker(self):
        """Happy path: set_session_maker() is returned by _get_sm()."""
        from app.services.delisted_pair_monitor import TradingPairMonitor

        mock_sm = object()
        monitor = TradingPairMonitor()
        monitor.set_session_maker(mock_sm)
        assert monitor._get_sm() is mock_sm

    def test_trading_pair_monitor_falls_back_to_default_session_maker(self):
        """Edge case: _get_sm() returns default when no injected SM."""
        from app.database import async_session_maker
        from app.services.delisted_pair_monitor import TradingPairMonitor

        monitor = TradingPairMonitor()
        assert monitor._get_sm() is async_session_maker
