"""
Tests for safety order cascade execution.

When price drops past multiple safety order trigger levels and a DCA
condition fires, all eligible SOs should execute in one cycle rather
than requiring one cycle per SO level.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from app.strategies.indicator_based import IndicatorBasedStrategy


def _make_strategy(config_overrides=None):
    base_config = {
        "base_order_type": "percentage",
        "base_order_percentage": 10.0,
        "base_order_fixed": 0.001,
        "max_safety_orders": 5,
        "safety_order_type": "percentage_of_base",
        "safety_order_percentage": 100.0,  # SO = 100% of base
        "safety_order_volume_scale": 1.0,
        "safety_order_step_scale": 1.0,
        "price_deviation": 2.0,  # 2% per SO level
        "take_profit_percentage": 3.0,
        "stop_loss_enabled": False,
        "take_profit_mode": "fixed",
        "trailing_stop_loss": False,
        "base_order_conditions": [],
        "base_order_logic": "and",
        "safety_order_conditions": [],
        "safety_order_logic": "and",
        "take_profit_conditions": [],
        "take_profit_logic": "and",
    }
    if config_overrides:
        base_config.update(config_overrides)
    with patch("app.strategies.indicator_based.IndicatorCalculator"), \
         patch("app.strategies.indicator_based.PhaseConditionEvaluator"), \
         patch("app.strategies.indicator_based.AISpotOpinionEvaluator"), \
         patch("app.strategies.indicator_based.BullFlagIndicatorEvaluator"):
        return IndicatorBasedStrategy(base_config)


def _make_position(avg_price=100.0, total_quote=1.0, max_quote=10.0,
                   num_buys=1, direction="long"):
    """Create a mock position with `num_buys` buy trades."""
    pos = MagicMock()
    pos.average_buy_price = avg_price
    pos.total_quote_spent = total_quote
    pos.max_quote_allowed = max_quote
    pos.direction = direction
    pos.entry_stop_loss = None
    pos.entry_take_profit_target = None
    pos.highest_price_since_entry = None
    pos.trailing_stop_loss_price = None
    pos.trailing_tp_active = False
    pos.highest_price_since_tp = None
    pos.previous_indicators = None
    pos.id = 1

    trades = []
    for i in range(num_buys):
        t = MagicMock()
        t.side = "buy"
        t.price = avg_price - i * 2  # Each buy 2 lower
        t.timestamp = 1000 + i
        t.trade_type = "initial" if i == 0 else "dca"
        t.dca_levels = 1  # one SO level per trade unless a test overrides (cascade)
        trades.append(t)
    pos.trades = trades
    return pos


class TestSafetyOrderCascade:
    """Test that multiple safety orders trigger when price drops past
    several SO levels at once."""

    @pytest.mark.asyncio
    async def test_single_so_normal(self):
        """Price below SO#1 only -> exactly 1 SO amount."""
        strategy = _make_strategy()
        position = _make_position()
        # SO#1 trigger at 98.0 (2% drop). Price=97.0 -> below SO#1, above SO#2 (96.0)
        signal = {"price": 97.0, "base_order_signal": False, "safety_order_signal": False}

        should, amount, reason = strategy._check_dca_conditions(signal, position, 10.0)

        assert should is True
        assert "Safety order #1" in reason
        # Should NOT mention #2
        assert "#2" not in reason

    @pytest.mark.asyncio
    async def test_cascade_two_sos(self):
        """Price below SO#1 and SO#2 triggers -> combined amount for both."""
        strategy = _make_strategy()
        position = _make_position()
        # SO#1 at 98.0, SO#2 at 96.0 (cumulative 4%). Price=95.0 -> below both
        signal = {"price": 95.0, "base_order_signal": False, "safety_order_signal": False}

        should, amount, reason = strategy._check_dca_conditions(signal, position, 10.0)

        assert should is True
        assert "#1" in reason and "#2" in reason
        # Two SOs combined should be more than a single SO
        single_so_amount = strategy._calculate_safety_order_amount(position, 0, 1)
        assert amount > single_so_amount

    @pytest.mark.asyncio
    async def test_cascade_all_sos(self):
        """Price crashes below ALL SO levels -> all SOs execute."""
        strategy = _make_strategy({
            "max_safety_orders": 3,
            "price_deviation": 2.0,
            "safety_order_step_scale": 1.0,
        })
        position = _make_position()
        # SO#1 at 98, SO#2 at 96, SO#3 at 94. Price=90 -> below all 3
        signal = {"price": 90.0, "base_order_signal": False, "safety_order_signal": False}

        should, amount, reason = strategy._check_dca_conditions(signal, position, 10.0)

        assert should is True
        assert "#1" in reason and "#3" in reason
        # 3 SOs combined should be more than a single SO
        single_so_amount = strategy._calculate_safety_order_amount(position, 0, 1)
        assert amount > single_so_amount

    @pytest.mark.asyncio
    async def test_cascade_with_conditions(self):
        """Cascade only triggers when SO conditions also pass."""
        strategy = _make_strategy({
            "safety_order_conditions": [{"indicator": "RSI", "operator": "<", "value": 40}],
        })
        position = _make_position()
        # Price below SO#1 and SO#2, but conditions not met
        signal = {"price": 95.0, "base_order_signal": False, "safety_order_signal": False}

        should, amount, reason = strategy._check_dca_conditions(signal, position, 10.0)

        assert should is False
        assert "conditions not met" in reason.lower()

    @pytest.mark.asyncio
    async def test_cascade_conditions_met(self):
        """With conditions met + price below multiple levels -> cascade fires."""
        strategy = _make_strategy({
            "safety_order_conditions": [{"indicator": "RSI", "operator": "<", "value": 40}],
        })
        position = _make_position()
        signal = {"price": 95.0, "base_order_signal": False, "safety_order_signal": True}

        should, amount, reason = strategy._check_dca_conditions(signal, position, 10.0)

        assert should is True
        assert "#1" in reason and "#2" in reason

    @pytest.mark.asyncio
    async def test_cascade_respects_max(self):
        """Already used 3 of 5 SOs, price below remaining 2 -> only 2 cascade."""
        strategy = _make_strategy({"max_safety_orders": 5})
        # 4 buy trades = base + 3 SOs used
        position = _make_position(num_buys=4, avg_price=100.0)
        # Price at 80.0 -> below SO#4 and SO#5 triggers
        signal = {"price": 80.0, "base_order_signal": False, "safety_order_signal": False}

        should, amount, reason = strategy._check_dca_conditions(signal, position, 10.0)

        assert should is True
        assert "#4" in reason and "#5" in reason
        # Should not mention #6
        assert "#6" not in reason

    @pytest.mark.asyncio
    async def test_cascade_insufficient_balance(self):
        """Price below multiple SOs but balance only covers partial -> execute what fits."""
        strategy = _make_strategy({
            "max_safety_orders": 5,
            "safety_order_percentage": 100.0,
        })
        position = _make_position(total_quote=1.0, max_quote=10.0)
        # Price below SO#1, SO#2, SO#3 but balance only enough for 1.5 SOs
        signal = {"price": 90.0, "base_order_signal": False, "safety_order_signal": False}

        # Very low balance - only covers about 1 SO
        should, amount, reason = strategy._check_dca_conditions(signal, position, 1.05)

        # Should trigger with at least SO#1
        assert should is True
        assert amount <= 1.05  # Should not exceed balance

    @pytest.mark.asyncio
    async def test_no_cascade_when_price_above_all(self):
        """Price above first SO trigger -> no cascade."""
        strategy = _make_strategy()
        position = _make_position()
        signal = {"price": 99.0, "base_order_signal": False, "safety_order_signal": False}

        should, amount, reason = strategy._check_dca_conditions(signal, position, 10.0)

        assert should is False

    @pytest.mark.asyncio
    async def test_cascade_with_step_scale(self):
        """Step scale > 1 creates exponentially wider gaps. Verify correct cascade count."""
        strategy = _make_strategy({
            "max_safety_orders": 4,
            "price_deviation": 2.0,
            "safety_order_step_scale": 2.0,
        })
        position = _make_position()
        # With step_scale=2: SO#1=2%, SO#2=2+4=6%, SO#3=2+4+8=14%, SO#4=2+4+8+16=30%
        # Price=93.0 -> 7% drop. Below SO#1(98) and SO#2(94), above SO#3(86)
        signal = {"price": 93.0, "base_order_signal": False, "safety_order_signal": False}

        should, amount, reason = strategy._check_dca_conditions(signal, position, 10.0)

        assert should is True
        assert "#1" in reason and "#2" in reason
        assert "#3" not in reason

    @pytest.mark.asyncio
    async def test_cascade_with_volume_scale(self):
        """Volume scale affects individual SO sizes. Cascade sums correctly."""
        strategy = _make_strategy({
            "max_safety_orders": 3,
            "safety_order_percentage": 100.0,
            "safety_order_volume_scale": 2.0,  # Each SO doubles
        })
        position = _make_position(total_quote=1.0, max_quote=20.0)
        # Price below all 3 SOs
        signal = {"price": 90.0, "base_order_signal": False, "safety_order_signal": False}

        should, amount, reason = strategy._check_dca_conditions(signal, position, 20.0)

        assert should is True
        # Verify it's a 3-SO cascade
        assert "#1" in reason and "#3" in reason
        # Sum should be more than SO#1 alone
        so1_size = strategy._calculate_safety_order_amount(position, 0, 1)
        assert amount > so1_size * 2  # Volume scaling should make it significantly more


def _buy(trade_type="dca", dca_levels=1, price=100.0):
    t = MagicMock()
    t.side = "buy"
    t.trade_type = trade_type
    t.dca_levels = dca_levels
    t.price = price
    return t


def _sell(trade_type="dca", dca_levels=1, price=100.0):
    t = MagicMock()
    t.side = "sell"
    t.trade_type = trade_type
    t.dca_levels = dca_levels
    t.price = price
    return t


class TestEntryTradesDirectionAware:
    """Long positions ADD via buys; short positions ADD via sells. The safety-order
    count must look at the ENTRY side for the position's direction — counting only
    buys leaves a short's safety-order count stuck at 0, corrupting SO numbering,
    volume-scale exponent, and trigger spacing."""

    def test_long_entry_trades_are_buys(self):
        from app.strategies.safety_order_calculator import entry_trades_for_position
        pos = MagicMock(direction="long")
        # base buy + 1 dca buy + a close (sell) — the close must be excluded
        pos.trades = [_buy("initial"), _buy("dca"), _sell("sell")]
        assert len(entry_trades_for_position(pos)) == 2

    def test_short_entry_trades_are_sells(self):
        from app.strategies.safety_order_calculator import entry_trades_for_position
        pos = MagicMock(direction="short")
        # base sell + 1 dca sell + a close (buy) — the close must be excluded
        pos.trades = [_sell("initial"), _sell("dca"), _buy("close_short")]
        assert len(entry_trades_for_position(pos)) == 2

    def test_short_safety_order_count_uses_sells(self):
        from app.strategies.safety_order_calculator import (
            entry_trades_for_position, count_deployed_safety_orders,
        )
        pos = MagicMock(direction="short")
        pos.trades = [_sell("initial"), _sell("dca"), _sell("dca")]
        # base + 2 short safety orders → 2 (was 0 before the direction-aware fix)
        assert count_deployed_safety_orders(entry_trades_for_position(pos)) == 2

    def test_missing_direction_defaults_to_long(self):
        from app.strategies.safety_order_calculator import entry_trades_for_position
        pos = MagicMock(spec=["trades"])  # no .direction attribute
        pos.trades = [_buy("initial"), _buy("dca")]
        assert len(entry_trades_for_position(pos)) == 2


class TestSafetyOrderLevelCount:
    """A cascade fills multiple SO levels in ONE trade. The deployed-SO count
    must therefore SUM levels (dca_levels), not count trade rows — otherwise the
    engine under-reports completed SOs and, on the next evaluation, tries to
    re-place an already-deployed level (gated only by remaining budget)."""

    def test_helper_counts_single_levels(self):
        from app.strategies.safety_order_calculator import count_deployed_safety_orders
        trades = [_buy("initial"), _buy("dca"), _buy("dca")]
        assert count_deployed_safety_orders(trades) == 2

    def test_helper_counts_cascade_levels(self):
        from app.strategies.safety_order_calculator import count_deployed_safety_orders
        # base + ONE dca trade that deployed TWO levels (a cascade)
        assert count_deployed_safety_orders([_buy("initial"), _buy("dca", dca_levels=2)]) == 2

    def test_helper_base_only_is_zero(self):
        from app.strategies.safety_order_calculator import count_deployed_safety_orders
        assert count_deployed_safety_orders([_buy("initial")]) == 0

    def test_helper_legacy_missing_dca_levels_defaults_one(self):
        from app.strategies.safety_order_calculator import count_deployed_safety_orders
        base = MagicMock()
        base.dca_levels = None
        dca = MagicMock()
        dca.dca_levels = None
        assert count_deployed_safety_orders([base, dca]) == 1

    @pytest.mark.asyncio
    async def test_cascade_records_level_count_in_signal(self):
        """A 3-level cascade must stamp signal_data['dca_levels'] = 3 so the
        recorded trade knows how many SO levels it deployed."""
        strategy = _make_strategy({"max_safety_orders": 3, "price_deviation": 2.0,
                                   "safety_order_step_scale": 1.0})
        position = _make_position()
        signal = {"price": 90.0, "base_order_signal": False, "safety_order_signal": False}
        should, amount, reason = strategy._check_dca_conditions(signal, position, 10.0)
        assert should is True
        assert "#1" in reason and "#3" in reason
        assert signal["dca_levels"] == 3

    @pytest.mark.asyncio
    async def test_single_so_records_one_level(self):
        strategy = _make_strategy()
        position = _make_position()
        signal = {"price": 97.0, "base_order_signal": False, "safety_order_signal": False}
        should, amount, reason = strategy._check_dca_conditions(signal, position, 10.0)
        assert should is True
        assert signal["dca_levels"] == 1

    @pytest.mark.asyncio
    async def test_no_replacement_after_cascade(self):
        """After a cascade recorded as one dca trade with dca_levels=2 (levels #1
        and #2 deployed), the next safety order must be #3 — NOT a re-placement
        of #2 — even with budget headroom."""
        strategy = _make_strategy({"max_safety_orders": 5, "price_deviation": 2.0,
                                   "safety_order_step_scale": 1.0})
        position = _make_position(num_buys=2)
        position.trades[1].dca_levels = 2  # the single dca trade covered TWO levels
        signal = {"price": 80.0, "base_order_signal": False, "safety_order_signal": False}
        should, amount, reason = strategy._check_dca_conditions(signal, position, 50.0)
        assert should is True
        assert "#3" in reason
        assert "#2" not in reason  # level 2 already deployed; must not re-place it


class TestManualBaseOrderSizing:
    """Manual (non-auto-calculate) percentage_of_base safety-order sizing must
    reference the actual base order (the earliest entry trade), NOT the average
    total_quote_spent/(1+count) — which over/under-sizes whenever orders aren't
    all equal to the base (any volume scaling, or percentage != 100%)."""

    def _scaled_position(self):
        # Base order 10, then SO1=20, SO2=40 (volume_scale=2) → total spent 70.
        def trade(q, ts):
            return SimpleNamespace(side="buy", quote_amount=q, timestamp=ts, dca_levels=1)
        return SimpleNamespace(
            direction="long", total_quote_spent=70.0, max_quote_allowed=100.0,
            trades=[trade(10.0, 1), trade(20.0, 2), trade(40.0, 3)],
        )

    def _manual_strategy(self):
        return _make_strategy({
            "auto_calculate_order_sizes": False,
            "safety_order_type": "percentage_of_base",
            "safety_order_percentage": 100.0,
            "safety_order_volume_scale": 2.0,
        })

    def test_uses_first_trade_not_backcalc(self):
        strategy = self._manual_strategy()
        pos = self._scaled_position()
        # SO #3 = base(10) * 100% * 2^(3-1) = 40. The buggy back-calc would give
        # total/(1+2)=23.33 * 4 = 93.3.
        assert strategy._calculate_safety_order_amount(pos, 2, 3) == pytest.approx(40.0)

    def test_independent_of_passed_count(self):
        strategy = self._manual_strategy()
        pos = self._scaled_position()
        # Same SO number → same size regardless of the cascade-inflated count arg.
        assert strategy._calculate_safety_order_amount(pos, 0, 3) == pytest.approx(40.0)
        assert strategy._calculate_safety_order_amount(pos, 99, 3) == pytest.approx(40.0)

    def test_falls_back_to_average_without_trades(self):
        strategy = _make_strategy({
            "auto_calculate_order_sizes": False,
            "safety_order_type": "percentage_of_base",
            "safety_order_percentage": 100.0,
            "safety_order_volume_scale": 1.0,
        })
        pos = SimpleNamespace(direction="long", total_quote_spent=4.0,
                              max_quote_allowed=100.0, trades=[])
        # No entry trades → average fallback 4.0/(1+1)=2.0; SO#1 = 2.0*100%*1 = 2.0.
        assert strategy._calculate_safety_order_amount(pos, 1, 1) == pytest.approx(2.0)
