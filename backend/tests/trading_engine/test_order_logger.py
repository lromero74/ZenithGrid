"""Tests for trading_engine/order_logger.py"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.trading_engine.order_logger import (
    _bot_uses_ai_indicators,
    log_order_to_history,
    save_ai_log,
    OrderLogEntry,
)


# ---------------------------------------------------------------------------
# _bot_uses_ai_indicators
# ---------------------------------------------------------------------------

class TestBotUsesAiIndicators:
    def test_ai_autonomous_strategy_returns_true(self):
        bot = MagicMock()
        bot.strategy_type = "ai_autonomous"
        bot.strategy_config = {}
        assert _bot_uses_ai_indicators(bot) is True

    def test_non_ai_strategy_no_conditions_returns_false(self):
        bot = MagicMock()
        bot.strategy_type = "indicator_based"
        bot.strategy_config = {"base_order_conditions": []}
        assert _bot_uses_ai_indicators(bot) is False

    def test_ai_buy_in_base_conditions_returns_true(self):
        bot = MagicMock()
        bot.strategy_type = "indicator_based"
        bot.strategy_config = {
            "base_order_conditions": [{"type": "ai_buy", "operator": ">=", "value": 70}],
            "safety_order_conditions": [],
            "take_profit_conditions": [],
        }
        assert _bot_uses_ai_indicators(bot) is True

    def test_ai_sell_in_take_profit_conditions_returns_true(self):
        bot = MagicMock()
        bot.strategy_type = "indicator_based"
        bot.strategy_config = {
            "base_order_conditions": [],
            "safety_order_conditions": [],
            "take_profit_conditions": [{"indicator": "ai_sell", "operator": ">=", "value": 80}],
        }
        assert _bot_uses_ai_indicators(bot) is True

    def test_empty_config_returns_false(self):
        bot = MagicMock()
        bot.strategy_type = "grid"
        bot.strategy_config = None
        assert _bot_uses_ai_indicators(bot) is False

    def test_non_list_conditions_returns_false(self):
        bot = MagicMock()
        bot.strategy_type = "indicator_based"
        bot.strategy_config = {
            "base_order_conditions": "not_a_list",
            "safety_order_conditions": [],
            "take_profit_conditions": [],
        }
        assert _bot_uses_ai_indicators(bot) is False


# ---------------------------------------------------------------------------
# log_order_to_history
# ---------------------------------------------------------------------------

class TestLogOrderToHistory:
    @pytest.mark.asyncio
    async def test_happy_path_success_order(self):
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 1
        position = MagicMock()
        position.id = 10

        await log_order_to_history(
            db=db, bot=bot, position=position,
            entry=OrderLogEntry(
                product_id="ETH-BTC", side="BUY", order_type="MARKET",
                trade_type="initial", quote_amount=0.001, price=0.05,
                status="success", order_id="order-123", base_amount=0.02,
            ),
        )

        db.add.assert_called_once()
        order = db.add.call_args[0][0]
        assert order.side == "BUY"
        assert order.status == "success"
        assert order.order_id == "order-123"

    @pytest.mark.asyncio
    async def test_failed_order_with_error_message(self):
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 1

        await log_order_to_history(
            db=db, bot=bot, position=None,
            entry=OrderLogEntry(
                product_id="BTC-USD", side="BUY", order_type="MARKET",
                trade_type="initial", quote_amount=100.0, price=50000.0,
                status="failed", error_message="Insufficient funds",
            ),
        )

        order = db.add.call_args[0][0]
        assert order.status == "failed"
        assert order.error_message == "Insufficient funds"
        assert order.position_id is None

    @pytest.mark.asyncio
    async def test_db_exception_does_not_propagate(self):
        db = MagicMock()
        db.add = MagicMock(side_effect=Exception("DB down"))
        bot = MagicMock()
        bot.id = 1

        # Should not raise
        await log_order_to_history(
            db=db, bot=bot, position=None,
            entry=OrderLogEntry(
                product_id="ETH-BTC", side="BUY", order_type="MARKET",
                trade_type="initial", quote_amount=0.001, price=0.05,
                status="failed",
            ),
        )


# ---------------------------------------------------------------------------
# save_ai_log
# ---------------------------------------------------------------------------

class TestSaveAiLog:
    @pytest.mark.asyncio
    async def test_saves_log_for_ai_bot(self):
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 1
        bot.strategy_type = "ai_autonomous"
        bot.strategy_config = {}
        position = MagicMock()
        position.id = 5
        position.status = "open"

        signal_data = {"reasoning": "Bullish signal", "confidence": 85}

        await save_ai_log(db, bot, "ETH-BTC", signal_data, "buy", 0.05, position)

        db.add.assert_called_once()
        log = db.add.call_args[0][0]
        assert log.decision == "buy"
        assert log.confidence == 85
        assert log.thinking == "Bullish signal"
        assert log.product_id == "ETH-BTC"

    @pytest.mark.asyncio
    async def test_skips_log_for_non_ai_bot(self):
        db = AsyncMock()
        bot = MagicMock()
        bot.strategy_type = "indicator_based"
        bot.strategy_config = {"base_order_conditions": []}

        await save_ai_log(db, bot, "ETH-BTC", {}, "hold", 0.05, None)

        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_no_position(self):
        db = AsyncMock()
        bot = MagicMock()
        bot.id = 1
        bot.strategy_type = "ai_autonomous"
        bot.strategy_config = {}

        signal_data = {"reasoning": "Looking for entry", "confidence": 60}

        await save_ai_log(db, bot, "BTC-USD", signal_data, "hold", 50000.0, None)

        log = db.add.call_args[0][0]
        assert log.position_id is None
        assert log.position_status == "none"
