"""Tests for trading_engine/trailing_stops.py"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.trading_engine.trailing_stops import (
    check_bull_flag_exit_conditions,
    setup_bull_flag_position_stops,
    update_trailing_stop_loss,
    update_trailing_take_profit,
)


def _make_position(
    entry_price=100.0,
    stop_loss=90.0,
    take_profit=120.0,
    tsl_active=True,
    ttp_active=False,
    highest_since_entry=None,
    highest_since_tp=None,
):
    pos = MagicMock()
    pos.id = 1
    pos.average_buy_price = entry_price
    pos.entry_stop_loss = stop_loss
    pos.entry_take_profit_target = take_profit
    pos.trailing_stop_loss_active = tsl_active
    pos.trailing_tp_active = ttp_active
    pos.trailing_stop_loss_price = stop_loss
    pos.highest_price_since_entry = highest_since_entry or entry_price
    pos.highest_price_since_tp = highest_since_tp
    pos.exit_reason = None
    return pos


# ---------------------------------------------------------------------------
# update_trailing_stop_loss
# ---------------------------------------------------------------------------

class TestUpdateTrailingStopLoss:
    @pytest.mark.asyncio
    async def test_tsl_triggers_sell_when_price_at_stop(self):
        """Price <= TSL triggers sell"""
        db = AsyncMock()
        pos = _make_position(entry_price=100.0, stop_loss=90.0)

        should_sell, reason = await update_trailing_stop_loss(pos, 89.0, db)

        assert should_sell is True
        assert "Trailing stop loss triggered" in reason
        assert pos.exit_reason == "trailing_stop_loss"

    @pytest.mark.asyncio
    async def test_tsl_trails_up_on_price_rise(self):
        """TSL moves up as price increases (maintaining risk distance)"""
        db = AsyncMock()
        pos = _make_position(entry_price=100.0, stop_loss=90.0)
        # risk_distance = 100 - 90 = 10

        should_sell, reason = await update_trailing_stop_loss(pos, 115.0, db)

        assert should_sell is False
        # new_tsl = 115 - 10 = 105 > old 90
        assert pos.trailing_stop_loss_price == 105.0

    @pytest.mark.asyncio
    async def test_tsl_does_not_trail_down(self):
        """TSL never moves down"""
        db = AsyncMock()
        pos = _make_position(entry_price=100.0, stop_loss=90.0)
        pos.trailing_stop_loss_price = 95.0  # Already trailed up

        should_sell, reason = await update_trailing_stop_loss(pos, 100.0, db)

        assert should_sell is False
        # new_tsl = 100 - 10 = 90, which is < current 95, so no change
        assert pos.trailing_stop_loss_price == 95.0

    @pytest.mark.asyncio
    async def test_tsl_skipped_when_ttp_active(self):
        """When TTP is active, TSL is disabled"""
        db = AsyncMock()
        pos = _make_position(entry_price=100.0, stop_loss=90.0, ttp_active=True)

        should_sell, reason = await update_trailing_stop_loss(pos, 85.0, db)

        assert should_sell is False
        assert "TTP active" in reason

    @pytest.mark.asyncio
    async def test_tsl_skipped_when_not_active(self):
        db = AsyncMock()
        pos = _make_position(entry_price=100.0, stop_loss=90.0, tsl_active=False)

        should_sell, reason = await update_trailing_stop_loss(pos, 85.0, db)

        assert should_sell is False
        assert "not active" in reason

    @pytest.mark.asyncio
    async def test_tsl_skipped_no_entry_stop_loss(self):
        db = AsyncMock()
        pos = _make_position()
        pos.entry_stop_loss = None

        should_sell, reason = await update_trailing_stop_loss(pos, 85.0, db)

        assert should_sell is False
        assert "No entry stop loss" in reason

    @pytest.mark.asyncio
    async def test_tsl_skipped_invalid_entry_price(self):
        db = AsyncMock()
        pos = _make_position()
        pos.average_buy_price = 0

        should_sell, reason = await update_trailing_stop_loss(pos, 85.0, db)

        assert should_sell is False
        assert "Invalid entry price" in reason


# ---------------------------------------------------------------------------
# update_trailing_take_profit
# ---------------------------------------------------------------------------

class TestUpdateTrailingTakeProfit:
    @pytest.mark.asyncio
    async def test_ttp_activates_at_target(self):
        """TTP activates when price >= target, disables TSL"""
        db = AsyncMock()
        pos = _make_position(entry_price=100.0, stop_loss=90.0, take_profit=120.0)

        should_sell, reason = await update_trailing_take_profit(pos, 125.0, db)

        assert should_sell is False
        assert pos.trailing_tp_active is True
        assert pos.trailing_stop_loss_active is False
        assert pos.highest_price_since_tp == 125.0
        assert "TTP activated" in reason

    @pytest.mark.asyncio
    async def test_ttp_does_not_activate_below_target(self):
        db = AsyncMock()
        pos = _make_position(entry_price=100.0, stop_loss=90.0, take_profit=120.0)

        should_sell, reason = await update_trailing_take_profit(pos, 115.0, db)

        assert should_sell is False
        assert pos.trailing_tp_active is False
        assert "below TTP target" in reason

    @pytest.mark.asyncio
    async def test_ttp_triggers_sell_on_drop_from_peak(self):
        """After TTP activation, sell when price drops by risk distance from peak"""
        db = AsyncMock()
        pos = _make_position(
            entry_price=100.0, stop_loss=90.0, take_profit=120.0,
            ttp_active=True, highest_since_tp=130.0,
        )
        pos.trailing_tp_active = True
        pos.highest_price_since_tp = 130.0
        # risk_distance = 100 - 90 = 10
        # trigger = 130 - 10 = 120
        # price = 119 <= 120 → sell

        should_sell, reason = await update_trailing_take_profit(pos, 119.0, db)

        assert should_sell is True
        assert "Trailing take profit triggered" in reason
        assert pos.exit_reason == "trailing_take_profit"

    @pytest.mark.asyncio
    async def test_ttp_updates_peak_price(self):
        db = AsyncMock()
        pos = _make_position(
            entry_price=100.0, stop_loss=90.0, take_profit=120.0,
            ttp_active=True, highest_since_tp=125.0,
        )
        pos.trailing_tp_active = True
        pos.highest_price_since_tp = 125.0

        should_sell, reason = await update_trailing_take_profit(pos, 135.0, db)

        assert should_sell is False
        assert pos.highest_price_since_tp == 135.0

    @pytest.mark.asyncio
    async def test_ttp_missing_parameters_returns_false(self):
        db = AsyncMock()
        pos = _make_position()
        pos.entry_take_profit_target = None

        should_sell, reason = await update_trailing_take_profit(pos, 125.0, db)

        assert should_sell is False
        assert "Missing entry parameters" in reason


# ---------------------------------------------------------------------------
# check_bull_flag_exit_conditions
# ---------------------------------------------------------------------------

class TestCheckBullFlagExitConditions:
    @pytest.mark.asyncio
    async def test_ttp_sell_takes_priority(self):
        """TTP sell triggers even if TSL would also trigger"""
        db = AsyncMock()
        pos = _make_position(
            entry_price=100.0, stop_loss=90.0, take_profit=120.0,
            ttp_active=True, highest_since_tp=130.0,
        )
        pos.trailing_tp_active = True
        pos.highest_price_since_tp = 130.0

        # Price 119 triggers TTP (130 - 10 = 120, 119 <= 120)
        should_sell, reason = await check_bull_flag_exit_conditions(pos, 119.0, db)

        assert should_sell is True
        assert "take profit" in reason.lower()

    @pytest.mark.asyncio
    async def test_tsl_sell_when_ttp_inactive(self):
        db = AsyncMock()
        pos = _make_position(entry_price=100.0, stop_loss=90.0, take_profit=120.0)

        should_sell, reason = await check_bull_flag_exit_conditions(pos, 89.0, db)

        assert should_sell is True
        assert "stop loss" in reason.lower()

    @pytest.mark.asyncio
    async def test_no_sell_when_price_in_range(self):
        db = AsyncMock()
        pos = _make_position(entry_price=100.0, stop_loss=90.0, take_profit=120.0)

        should_sell, reason = await check_bull_flag_exit_conditions(pos, 110.0, db)

        assert should_sell is False


# ---------------------------------------------------------------------------
# setup_bull_flag_position_stops
# ---------------------------------------------------------------------------

class TestSetupBullFlagPositionStops:
    def test_initializes_all_fields(self):
        pos = MagicMock()
        pos.average_buy_price = 100.0
        pos.id = 1

        pattern = {
            "stop_loss": 90.0,
            "take_profit_target": 120.0,
            "pattern_type": "bull_flag",
        }

        setup_bull_flag_position_stops(pos, pattern)

        assert pos.entry_stop_loss == 90.0
        assert pos.entry_take_profit_target == 120.0
        assert pos.trailing_stop_loss_price == 90.0
        assert pos.trailing_stop_loss_active is True
        assert pos.trailing_tp_active is False
        assert pos.highest_price_since_tp is None
        assert pos.highest_price_since_entry == 100.0

        # Pattern stored as JSON
        stored = json.loads(pos.pattern_data)
        assert stored["pattern_type"] == "bull_flag"

    def test_handles_missing_optional_fields_raises(self):
        """Empty pattern data causes TypeError in logger.info (None:.4f)"""
        pos = MagicMock()
        pos.average_buy_price = 50.0
        pos.id = 2

        pattern = {}

        with pytest.raises(TypeError):
            setup_bull_flag_position_stops(pos, pattern)
