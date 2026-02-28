"""
Tests for bull_flag_processor.process_bull_flag_bot().

Tests bull flag strategy processing: open position exit checks (TSL/TTP),
new opportunity scanning, position entry, budget calculation, and category filtering.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.monitor.bull_flag_processor import process_bull_flag_bot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bot(
    bot_id=1,
    name="BullFlagBot",
    is_active=True,
    account_id=10,
    user_id=1,
    strategy_config=None,
):
    bot = MagicMock()
    bot.id = bot_id
    bot.name = name
    bot.is_active = is_active
    bot.account_id = account_id
    bot.user_id = user_id
    bot.strategy_config = strategy_config or {
        "max_concurrent_positions": 5,
        "max_scan_coins": 100,
        "budget_mode": "percentage",
        "budget_percentage": 5.0,
    }
    bot.get_quote_currency = MagicMock(return_value="USD")
    return bot


def _make_position(pos_id=1, bot_id=1, product_id="BTC-USD", status="open", total_base_acquired=0.5):
    pos = MagicMock()
    pos.id = pos_id
    pos.bot_id = bot_id
    pos.product_id = product_id
    pos.status = status
    pos.total_base_acquired = total_base_acquired
    pos.closed_at = None
    pos.close_price = None
    return pos


def _make_monitor():
    monitor = MagicMock()
    monitor.exchange = MagicMock()
    monitor.exchange.get_current_price = AsyncMock(return_value=50000.0)
    monitor.exchange.create_market_sell_order = AsyncMock(return_value={"order_id": "sell-123"})
    monitor.exchange.create_market_buy_order = AsyncMock(return_value={"order_id": "buy-456"})
    monitor.exchange.calculate_aggregate_quote_value = AsyncMock(return_value=10000.0)
    return monitor


def _make_opportunity(product_id="SOL-USD", entry_price=150.0):
    return {
        "product_id": product_id,
        "pattern": {
            "entry_price": entry_price,
            "stop_loss": entry_price * 0.95,
            "take_profit_target": entry_price * 1.10,
        },
    }


# ===========================================================================
# Class: TestBullFlagExitSignals
# ===========================================================================


class TestBullFlagExitSignals:
    """Tests for checking trailing stop / take profit on existing positions."""

    @pytest.mark.asyncio
    async def test_exit_triggered_sells_position(self, db_session):
        """When TSL/TTP triggers, a sell order is executed."""
        monitor = _make_monitor()
        bot = _make_bot()
        pos = _make_position()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pos]
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.commit = AsyncMock()

        with patch(
            "app.monitor.bull_flag_processor.check_bull_flag_exit_conditions",
            new_callable=AsyncMock,
            return_value=(True, "Trailing stop loss triggered"),
        ), patch(
            "app.monitor.bull_flag_processor.log_scanner_decision",
            new_callable=AsyncMock,
        ), patch(
            "app.monitor.bull_flag_processor.scan_for_bull_flag_opportunities",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.multi_bot_monitor.filter_pairs_by_allowed_categories",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await process_bull_flag_bot(monitor, db_session, bot)

        assert len(result["exits"]) == 1
        assert result["exits"][0]["reason"] == "Trailing stop loss triggered"
        monitor.exchange.create_market_sell_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_exit_not_triggered_holds(self, db_session):
        """When exit conditions not met, position is held."""
        monitor = _make_monitor()
        bot = _make_bot()
        pos = _make_position()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pos]
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.commit = AsyncMock()

        with patch(
            "app.monitor.bull_flag_processor.check_bull_flag_exit_conditions",
            new_callable=AsyncMock,
            return_value=(False, "Price within range"),
        ), patch(
            "app.monitor.bull_flag_processor.log_scanner_decision",
            new_callable=AsyncMock,
        ), patch(
            "app.monitor.bull_flag_processor.scan_for_bull_flag_opportunities",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.multi_bot_monitor.filter_pairs_by_allowed_categories",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await process_bull_flag_bot(monitor, db_session, bot)

        assert len(result["exits"]) == 0
        monitor.exchange.create_market_sell_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_exit_price_fetch_fails_skips_position(self, db_session):
        """When price fetch fails, the position check is skipped gracefully."""
        monitor = _make_monitor()
        monitor.exchange.get_current_price = AsyncMock(return_value=0)  # Invalid price

        bot = _make_bot()
        pos = _make_position()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pos]
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.commit = AsyncMock()

        with patch(
            "app.monitor.bull_flag_processor.scan_for_bull_flag_opportunities",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.multi_bot_monitor.filter_pairs_by_allowed_categories",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await process_bull_flag_bot(monitor, db_session, bot)

        assert len(result["exits"]) == 0
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_exit_sell_order_failure_logged(self, db_session):
        """When sell order execution fails, error is logged."""
        monitor = _make_monitor()
        monitor.exchange.create_market_sell_order = AsyncMock(side_effect=Exception("Exchange down"))

        bot = _make_bot()
        pos = _make_position()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pos]
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.commit = AsyncMock()

        with patch(
            "app.monitor.bull_flag_processor.check_bull_flag_exit_conditions",
            new_callable=AsyncMock,
            return_value=(True, "TSL hit"),
        ), patch(
            "app.monitor.bull_flag_processor.log_scanner_decision",
            new_callable=AsyncMock,
        ), patch(
            "app.monitor.bull_flag_processor.scan_for_bull_flag_opportunities",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.multi_bot_monitor.filter_pairs_by_allowed_categories",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await process_bull_flag_bot(monitor, db_session, bot)

        assert len(result["errors"]) == 1
        assert "Sell error" in result["errors"][0]


# ===========================================================================
# Class: TestBullFlagScanning
# ===========================================================================


class TestBullFlagScanning:
    """Tests for scanning for new bull flag opportunities."""

    @pytest.mark.asyncio
    async def test_at_max_positions_skips_scan(self, db_session):
        """When at max_concurrent_positions, scanning is skipped."""
        monitor = _make_monitor()
        bot = _make_bot(strategy_config={
            "max_concurrent_positions": 1,
            "max_scan_coins": 100,
        })

        pos = _make_position()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pos]
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.commit = AsyncMock()

        with patch(
            "app.monitor.bull_flag_processor.check_bull_flag_exit_conditions",
            new_callable=AsyncMock,
            return_value=(False, "Holding"),
        ), patch(
            "app.monitor.bull_flag_processor.log_scanner_decision",
            new_callable=AsyncMock,
        ):
            result = await process_bull_flag_bot(monitor, db_session, bot)

        # No scan should have occurred
        assert result["scanned"] == 0

    @pytest.mark.asyncio
    async def test_scan_finds_opportunities(self, db_session):
        """Scanner finds opportunities and counts them."""
        monitor = _make_monitor()
        bot = _make_bot()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []  # No open positions
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.commit = AsyncMock()

        opportunities = [
            _make_opportunity("SOL-USD"),
            _make_opportunity("AVAX-USD"),
            {"product_id": "LOW-USD", "pattern": None},  # No pattern = no opportunity
        ]

        with patch(
            "app.monitor.bull_flag_processor.scan_for_bull_flag_opportunities",
            new_callable=AsyncMock,
            return_value=opportunities,
        ), patch(
            "app.multi_bot_monitor.filter_pairs_by_allowed_categories",
            new_callable=AsyncMock,
            return_value=["SOL-USD", "AVAX-USD", "LOW-USD"],
        ), patch(
            "app.monitor.bull_flag_processor.setup_bull_flag_position_stops",
        ):
            result = await process_bull_flag_bot(monitor, db_session, bot)

        assert result["scanned"] == 3
        assert result["opportunities"] == 2  # Only ones with patterns


# ===========================================================================
# Class: TestBullFlagEntry
# ===========================================================================


class TestBullFlagEntry:
    """Tests for entering new bull flag positions."""

    @pytest.mark.asyncio
    async def test_enters_position_with_valid_opportunity(self, db_session):
        """Valid opportunity leads to market buy + position creation."""
        monitor = _make_monitor()
        bot = _make_bot(strategy_config={
            "max_concurrent_positions": 5,
            "max_scan_coins": 100,
            "budget_mode": "fixed_usd",
            "fixed_usd_amount": 100.0,
        })

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.commit = AsyncMock()
        db_session.add = MagicMock()

        opp = _make_opportunity("SOL-USD", entry_price=150.0)

        with patch(
            "app.monitor.bull_flag_processor.scan_for_bull_flag_opportunities",
            new_callable=AsyncMock,
            return_value=[opp],
        ), patch(
            "app.multi_bot_monitor.filter_pairs_by_allowed_categories",
            new_callable=AsyncMock,
            return_value=["SOL-USD"],
        ), patch(
            "app.monitor.bull_flag_processor.setup_bull_flag_position_stops",
        ) as mock_stops:
            result = await process_bull_flag_bot(monitor, db_session, bot)

        assert len(result["entries"]) == 1
        assert result["entries"][0]["product_id"] == "SOL-USD"
        monitor.exchange.create_market_buy_order.assert_called_once()
        mock_stops.assert_called_once()
        db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_existing_product(self, db_session):
        """Does not enter a position for a product that already has an open position."""
        monitor = _make_monitor()
        bot = _make_bot(strategy_config={
            "max_concurrent_positions": 5,
            "max_scan_coins": 100,
            "budget_mode": "fixed_usd",
            "fixed_usd_amount": 100.0,
        })

        existing_pos = _make_position(product_id="SOL-USD")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [existing_pos]
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.commit = AsyncMock()

        opp = _make_opportunity("SOL-USD")

        with patch(
            "app.monitor.bull_flag_processor.check_bull_flag_exit_conditions",
            new_callable=AsyncMock,
            return_value=(False, "Holding"),
        ), patch(
            "app.monitor.bull_flag_processor.log_scanner_decision",
            new_callable=AsyncMock,
        ), patch(
            "app.monitor.bull_flag_processor.scan_for_bull_flag_opportunities",
            new_callable=AsyncMock,
            return_value=[opp],
        ), patch(
            "app.multi_bot_monitor.filter_pairs_by_allowed_categories",
            new_callable=AsyncMock,
            return_value=["SOL-USD"],
        ):
            result = await process_bull_flag_bot(monitor, db_session, bot)

        assert len(result["entries"]) == 0
        monitor.exchange.create_market_buy_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_position_size_below_minimum_skipped(self, db_session):
        """When calculated position size < $10, entry is skipped."""
        monitor = _make_monitor()
        monitor.exchange.calculate_aggregate_quote_value = AsyncMock(return_value=100.0)

        bot = _make_bot(strategy_config={
            "max_concurrent_positions": 5,
            "max_scan_coins": 100,
            "budget_mode": "percentage",
            "budget_percentage": 0.001,  # Very small percentage -> < $10
        })

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.commit = AsyncMock()

        opp = _make_opportunity("SOL-USD", entry_price=150.0)

        with patch(
            "app.monitor.bull_flag_processor.scan_for_bull_flag_opportunities",
            new_callable=AsyncMock,
            return_value=[opp],
        ), patch(
            "app.multi_bot_monitor.filter_pairs_by_allowed_categories",
            new_callable=AsyncMock,
            return_value=["SOL-USD"],
        ):
            result = await process_bull_flag_bot(monitor, db_session, bot)

        assert len(result["entries"]) == 0
        monitor.exchange.create_market_buy_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_entry_respects_available_slots(self, db_session):
        """Only enters up to available_slots (max_concurrent - open_count) positions."""
        monitor = _make_monitor()
        bot = _make_bot(strategy_config={
            "max_concurrent_positions": 2,
            "max_scan_coins": 100,
            "budget_mode": "fixed_usd",
            "fixed_usd_amount": 100.0,
        })

        existing = _make_position(product_id="BTC-USD")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [existing]
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.commit = AsyncMock()
        db_session.add = MagicMock()

        opps = [
            _make_opportunity("SOL-USD"),
            _make_opportunity("AVAX-USD"),
            _make_opportunity("LINK-USD"),
        ]

        with patch(
            "app.monitor.bull_flag_processor.check_bull_flag_exit_conditions",
            new_callable=AsyncMock,
            return_value=(False, "Holding"),
        ), patch(
            "app.monitor.bull_flag_processor.log_scanner_decision",
            new_callable=AsyncMock,
        ), patch(
            "app.monitor.bull_flag_processor.scan_for_bull_flag_opportunities",
            new_callable=AsyncMock,
            return_value=opps,
        ), patch(
            "app.multi_bot_monitor.filter_pairs_by_allowed_categories",
            new_callable=AsyncMock,
            return_value=["SOL-USD", "AVAX-USD", "LINK-USD"],
        ), patch(
            "app.monitor.bull_flag_processor.setup_bull_flag_position_stops",
        ):
            result = await process_bull_flag_bot(monitor, db_session, bot)

        # max_concurrent=2, 1 existing -> only 1 slot available
        assert len(result["entries"]) == 1

    @pytest.mark.asyncio
    async def test_entry_error_logged(self, db_session):
        """When buy order fails, error is captured in results."""
        monitor = _make_monitor()
        monitor.exchange.create_market_buy_order = AsyncMock(side_effect=Exception("Insufficient funds"))

        bot = _make_bot(strategy_config={
            "max_concurrent_positions": 5,
            "max_scan_coins": 100,
            "budget_mode": "fixed_usd",
            "fixed_usd_amount": 100.0,
        })

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.commit = AsyncMock()

        opp = _make_opportunity("SOL-USD")

        with patch(
            "app.monitor.bull_flag_processor.scan_for_bull_flag_opportunities",
            new_callable=AsyncMock,
            return_value=[opp],
        ), patch(
            "app.multi_bot_monitor.filter_pairs_by_allowed_categories",
            new_callable=AsyncMock,
            return_value=["SOL-USD"],
        ):
            result = await process_bull_flag_bot(monitor, db_session, bot)

        assert len(result["errors"]) == 1
        assert "Entry error" in result["errors"][0]


# ===========================================================================
# Class: TestBullFlagCategoryFilter
# ===========================================================================


class TestBullFlagCategoryFilter:
    """Tests for category filtering of opportunities."""

    @pytest.mark.asyncio
    async def test_category_filter_applied(self, db_session):
        """When allowed_categories is set, opportunities are filtered."""
        monitor = _make_monitor()
        bot = _make_bot(strategy_config={
            "max_concurrent_positions": 5,
            "max_scan_coins": 100,
            "budget_mode": "fixed_usd",
            "fixed_usd_amount": 100.0,
            "allowed_categories": ["APPROVED"],
        })

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.commit = AsyncMock()
        db_session.add = MagicMock()

        opps = [
            _make_opportunity("SOL-USD"),
            _make_opportunity("MEME-USD"),
        ]

        with patch(
            "app.monitor.bull_flag_processor.scan_for_bull_flag_opportunities",
            new_callable=AsyncMock,
            return_value=opps,
        ), patch(
            "app.multi_bot_monitor.filter_pairs_by_allowed_categories",
            new_callable=AsyncMock,
            return_value=["SOL-USD"],  # MEME-USD filtered out
        ), patch(
            "app.monitor.bull_flag_processor.setup_bull_flag_position_stops",
        ):
            result = await process_bull_flag_bot(monitor, db_session, bot)

        # Only SOL-USD should be entered
        assert len(result["entries"]) == 1
        assert result["entries"][0]["product_id"] == "SOL-USD"


# ===========================================================================
# Class: TestBullFlagTopLevelError
# ===========================================================================


class TestBullFlagTopLevelError:
    """Tests for top-level exception handling."""

    @pytest.mark.asyncio
    async def test_top_level_exception_returns_error(self, db_session):
        """A top-level exception is caught and returned as error dict."""
        monitor = _make_monitor()
        bot = _make_bot()

        db_session.execute = AsyncMock(side_effect=RuntimeError("DB crashed"))

        result = await process_bull_flag_bot(monitor, db_session, bot)
        assert "error" in result
        assert "DB crashed" in result["error"]
