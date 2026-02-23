"""
Tests for backend/app/position_routers/helpers.py

Covers compute_resize_budget() which calculates the true max deal cost
for a position from its config and trades.
"""

from unittest.mock import MagicMock, patch

from app.position_routers.helpers import compute_resize_budget


# =============================================================================
# compute_resize_budget
# =============================================================================


class TestComputeResizeBudget:
    """Tests for compute_resize_budget()"""

    @patch("app.position_routers.helpers.calculate_expected_position_budget")
    @patch("app.position_routers.helpers.calculate_max_deal_cost")
    def test_uses_expected_budget_when_positive(self, mock_max_deal, mock_expected):
        """Happy path: returns calculate_expected_position_budget when > 0."""
        mock_expected.return_value = 0.05
        mock_max_deal.return_value = 0.0  # Should not be called

        position = MagicMock()
        position.strategy_config_snapshot = {"base_order_fixed": 0.01, "max_safety_orders": 3}
        position.trades = []

        bot = MagicMock()
        bot.strategy_config = {"base_order_fixed": 0.01}

        result = compute_resize_budget(position, bot)
        assert result == 0.05
        mock_expected.assert_called_once()

    @patch("app.position_routers.helpers.calculate_expected_position_budget")
    @patch("app.position_routers.helpers.calculate_max_deal_cost")
    def test_falls_back_to_trade_based_calculation(self, mock_max_deal, mock_expected):
        """Edge case: when expected budget is 0, derives from first buy trade."""
        mock_expected.return_value = 0.0
        mock_max_deal.return_value = 0.035

        # Create mock trades
        trade1 = MagicMock()
        trade1.side = "buy"
        trade1.timestamp = 1000
        trade1.quote_amount = 0.01

        trade2 = MagicMock()
        trade2.side = "buy"
        trade2.timestamp = 2000
        trade2.quote_amount = 0.005

        position = MagicMock()
        position.strategy_config_snapshot = {"some_config": True}
        position.trades = [trade2, trade1]  # Unordered to test sorting

        result = compute_resize_budget(position, None)
        assert result == 0.035
        mock_max_deal.assert_called_once_with({"some_config": True}, 0.01)

    @patch("app.position_routers.helpers.calculate_expected_position_budget")
    @patch("app.position_routers.helpers.calculate_max_deal_cost")
    def test_falls_back_to_config_base_order_btc(self, mock_max_deal, mock_expected):
        """Edge case: no trades, uses config base_order_btc."""
        mock_expected.return_value = 0.0
        mock_max_deal.return_value = 0.025

        position = MagicMock()
        position.strategy_config_snapshot = {"base_order_btc": 0.008}
        position.trades = []

        result = compute_resize_budget(position, None)
        assert result == 0.025
        mock_max_deal.assert_called_once_with({"base_order_btc": 0.008}, 0.008)

    @patch("app.position_routers.helpers.calculate_expected_position_budget")
    @patch("app.position_routers.helpers.calculate_max_deal_cost")
    def test_falls_back_to_config_base_order_fixed(self, mock_max_deal, mock_expected):
        """Edge case: no trades, uses config base_order_fixed when base_order_btc is 0."""
        mock_expected.return_value = 0.0
        mock_max_deal.return_value = 50.0

        position = MagicMock()
        position.strategy_config_snapshot = {"base_order_btc": 0.0, "base_order_fixed": 10.0}
        position.trades = []

        result = compute_resize_budget(position, None)
        assert result == 50.0
        mock_max_deal.assert_called_once_with(
            {"base_order_btc": 0.0, "base_order_fixed": 10.0}, 10.0
        )

    @patch("app.position_routers.helpers.calculate_expected_position_budget")
    def test_returns_zero_when_no_base_order_found(self, mock_expected):
        """Failure: returns 0.0 when no base order size can be determined."""
        mock_expected.return_value = 0.0

        position = MagicMock()
        position.strategy_config_snapshot = {}
        position.trades = []

        result = compute_resize_budget(position, None)
        assert result == 0.0

    @patch("app.position_routers.helpers.calculate_expected_position_budget")
    @patch("app.position_routers.helpers.calculate_max_deal_cost")
    def test_uses_bot_config_when_position_snapshot_is_none(self, mock_max_deal, mock_expected):
        """Edge case: position has no snapshot, falls back to bot.strategy_config."""
        mock_expected.return_value = 0.04

        position = MagicMock()
        position.strategy_config_snapshot = None

        bot = MagicMock()
        bot.strategy_config = {"base_order_fixed": 0.01, "max_safety_orders": 2}

        result = compute_resize_budget(position, bot)
        assert result == 0.04
        # The config used should be the bot's config
        mock_expected.assert_called_once_with(
            {"base_order_fixed": 0.01, "max_safety_orders": 2}, 0
        )

    @patch("app.position_routers.helpers.calculate_expected_position_budget")
    def test_no_bot_no_snapshot_returns_zero(self, mock_expected):
        """Failure: no config source at all returns 0.0."""
        mock_expected.return_value = 0.0

        position = MagicMock()
        position.strategy_config_snapshot = None
        position.trades = []

        result = compute_resize_budget(position, None)
        assert result == 0.0

    @patch("app.position_routers.helpers.calculate_expected_position_budget")
    @patch("app.position_routers.helpers.calculate_max_deal_cost")
    def test_ignores_sell_trades_for_base_order(self, mock_max_deal, mock_expected):
        """Edge case: sell trades are excluded when finding base order size."""
        mock_expected.return_value = 0.0
        mock_max_deal.return_value = 0.02

        sell_trade = MagicMock()
        sell_trade.side = "sell"
        sell_trade.timestamp = 500
        sell_trade.quote_amount = 0.1

        buy_trade = MagicMock()
        buy_trade.side = "buy"
        buy_trade.timestamp = 1000
        buy_trade.quote_amount = 0.005

        position = MagicMock()
        position.strategy_config_snapshot = {}
        position.trades = [sell_trade, buy_trade]

        result = compute_resize_budget(position, None)
        assert result == 0.02
        mock_max_deal.assert_called_once_with({}, 0.005)
