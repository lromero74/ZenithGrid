"""
Tests for backend/app/strategies/market_making.py

Covers:
- Definition and registration in StrategyRegistry
- Reference price computation (order book mid vs. fallback)
- Quote price computation (bid = ref - half-spread, ask = ref + half-spread)
- Inventory skew multipliers (mean-revert when long/short-heavy)
- needs_requote: refresh-interval trigger and recenter-threshold trigger
- analyze_signal: hold when within interval, requote when needed
- should_buy / should_sell based on requote signal
- Edge cases: zero/negative price, zero inventory, max_inventory=0
- Account isolation: two strategy instances share no state
"""

import time
import pytest


# =============================================================================
# Helper
# =============================================================================


def _make_strategy(**kwargs):
    """Create a MarketMakingStrategy with default config, overridable via kwargs."""
    from app.strategies.market_making import MarketMakingStrategy

    config = {
        "spread_bps": 20.0,
        "order_size": 100.0,
        "max_inventory": 1.0,
        "recenter_threshold_pct": 0.5,
        "order_refresh_interval": 30.0,
        "quote_currency": "USD",
    }
    config.update(kwargs)
    return MarketMakingStrategy(config)


# =============================================================================
# Registration tests
# =============================================================================


def test_strategy_registered_in_registry():
    """MarketMakingStrategy is accessible via StrategyRegistry."""
    from app.strategies import StrategyRegistry
    definition = StrategyRegistry.get_definition("market_making")
    assert definition.id == "market_making"
    assert "market" in definition.name.lower()


def test_get_definition_returns_expected_parameters():
    """get_definition lists all required config parameters."""
    strategy = _make_strategy()
    defn = strategy.get_definition()
    assert defn.id == "market_making"
    param_names = [p.name for p in defn.parameters]
    for required_param in (
        "spread_bps",
        "order_size",
        "max_inventory",
        "recenter_threshold_pct",
        "order_refresh_interval",
        "quote_currency",
    ):
        assert required_param in param_names, f"Missing parameter: {required_param}"


def test_strategy_description_non_empty():
    """Strategy description is non-empty."""
    strategy = _make_strategy()
    defn = strategy.get_definition()
    assert len(defn.description) > 10


# =============================================================================
# Reference price tests
# =============================================================================


def test_reference_price_uses_orderbook_midprice():
    """Mid-price is used when a valid order book is provided."""
    strategy = _make_strategy()
    order_book = {"best_bid": 49_000.0, "best_ask": 51_000.0}
    ref = strategy.compute_reference_price(50_000.0, order_book)
    assert ref == pytest.approx(50_000.0)


def test_reference_price_fallback_to_current_price():
    """Falls back to current_price when no order book is given."""
    strategy = _make_strategy()
    ref = strategy.compute_reference_price(42_000.0)
    assert ref == pytest.approx(42_000.0)


def test_reference_price_fallback_on_invalid_orderbook():
    """Falls back to current_price when order book has zero or inverted values."""
    strategy = _make_strategy()
    # Inverted book (ask < bid)
    ref = strategy.compute_reference_price(42_000.0, {"best_bid": 51_000.0, "best_ask": 49_000.0})
    assert ref == pytest.approx(42_000.0)
    # Zero bid
    ref2 = strategy.compute_reference_price(42_000.0, {"best_bid": 0.0, "best_ask": 49_000.0})
    assert ref2 == pytest.approx(42_000.0)


def test_reference_price_fallback_on_missing_keys():
    """Falls back to current_price when order book keys are absent."""
    strategy = _make_strategy()
    ref = strategy.compute_reference_price(42_000.0, {})
    assert ref == pytest.approx(42_000.0)


# =============================================================================
# Quote price tests
# =============================================================================


def test_quote_prices_symmetric_around_reference():
    """Bid and ask are equidistant from reference price."""
    strategy = _make_strategy(spread_bps=20.0)  # 0.20%
    quotes = strategy.compute_quote_prices(50_000.0)
    half_spread = 50_000.0 * (20.0 / 2.0) / 10_000.0  # = 50.0
    assert quotes["bid_price"] == pytest.approx(50_000.0 - half_spread)
    assert quotes["ask_price"] == pytest.approx(50_000.0 + half_spread)


def test_quote_prices_bid_always_below_ask():
    """bid_price < ask_price for any positive spread."""
    strategy = _make_strategy(spread_bps=1.0)
    quotes = strategy.compute_quote_prices(100.0)
    assert quotes["bid_price"] < quotes["ask_price"]


def test_quote_prices_scale_with_spread():
    """Wider spread → larger gap between bid and ask."""
    strategy_narrow = _make_strategy(spread_bps=10.0)
    strategy_wide = _make_strategy(spread_bps=100.0)
    ref = 10_000.0
    narrow = strategy_narrow.compute_quote_prices(ref)
    wide = strategy_wide.compute_quote_prices(ref)
    narrow_gap = wide["ask_price"] - wide["bid_price"]
    wide_gap = narrow["ask_price"] - narrow["bid_price"]
    # wide spread → larger gap (note variable names are intentionally swapped above)
    assert (wide["ask_price"] - wide["bid_price"]) > (narrow["ask_price"] - narrow["bid_price"])
    _ = narrow_gap  # suppress unused var
    _ = wide_gap


# =============================================================================
# Inventory skew tests
# =============================================================================


def test_inventory_skew_neutral_at_zero():
    """No skew when inventory is zero."""
    strategy = _make_strategy(max_inventory=1.0)
    skew = strategy.compute_inventory_skew(0.0)
    assert skew["buy_multiplier"] == pytest.approx(1.0)
    assert skew["sell_multiplier"] == pytest.approx(1.0)


def test_inventory_skew_reduces_buy_when_long_heavy():
    """Buy multiplier shrinks and sell multiplier grows when inventory is high."""
    strategy = _make_strategy(max_inventory=1.0)
    skew = strategy.compute_inventory_skew(1.0)  # at max
    assert skew["buy_multiplier"] == pytest.approx(0.0)
    assert skew["sell_multiplier"] == pytest.approx(2.0)


def test_inventory_skew_partial():
    """Half-way to max_inventory → buy=0.5, sell=1.5."""
    strategy = _make_strategy(max_inventory=2.0)
    skew = strategy.compute_inventory_skew(1.0)  # 50% of max
    assert skew["buy_multiplier"] == pytest.approx(0.5)
    assert skew["sell_multiplier"] == pytest.approx(1.5)


def test_inventory_skew_capped_at_max_inventory():
    """Inventory beyond max_inventory is clamped to buy=0, sell=2."""
    strategy = _make_strategy(max_inventory=1.0)
    skew = strategy.compute_inventory_skew(999.0)
    assert skew["buy_multiplier"] == pytest.approx(0.0)
    assert skew["sell_multiplier"] == pytest.approx(2.0)


def test_inventory_skew_zero_max_inventory():
    """When max_inventory=0, skew returns 1.0/1.0 (no-op guard)."""
    strategy = _make_strategy(max_inventory=0.0)
    skew = strategy.compute_inventory_skew(5.0)
    assert skew["buy_multiplier"] == pytest.approx(1.0)
    assert skew["sell_multiplier"] == pytest.approx(1.0)


# =============================================================================
# needs_requote tests
# =============================================================================


def test_needs_requote_on_first_call():
    """First call always triggers a requote (last_quote_time=0)."""
    strategy = _make_strategy(order_refresh_interval=60.0)
    assert strategy.needs_requote(50_000.0, now=time.time()) is True


def test_needs_requote_within_interval_and_threshold():
    """No requote needed when inside the interval and below threshold."""
    strategy = _make_strategy(
        order_refresh_interval=60.0,
        recenter_threshold_pct=1.0,
    )
    now = time.time()
    strategy.record_quote(50_000.0, now=now)
    # Price moved only 0.5% — below 1% threshold; only 5s elapsed — below 60s
    assert strategy.needs_requote(50_250.0, now=now + 5.0) is False


def test_needs_requote_when_interval_elapsed():
    """Requote triggered once the refresh interval has elapsed."""
    strategy = _make_strategy(order_refresh_interval=30.0)
    now = time.time()
    strategy.record_quote(50_000.0, now=now)
    assert strategy.needs_requote(50_000.0, now=now + 31.0) is True


def test_needs_requote_when_price_moves_beyond_threshold():
    """Requote triggered when price move exceeds recenter_threshold_pct."""
    strategy = _make_strategy(
        order_refresh_interval=3600.0,
        recenter_threshold_pct=0.5,
    )
    now = time.time()
    strategy.record_quote(50_000.0, now=now)
    # Price moved 1% (>0.5%) but only 1s elapsed (<<3600s)
    assert strategy.needs_requote(50_500.0, now=now + 1.0) is True


def test_needs_requote_exact_threshold():
    """Requote triggered when price move exactly equals threshold."""
    strategy = _make_strategy(
        order_refresh_interval=3600.0,
        recenter_threshold_pct=1.0,
    )
    now = time.time()
    strategy.record_quote(100.0, now=now)
    assert strategy.needs_requote(101.0, now=now + 1.0) is True  # exactly 1%


# =============================================================================
# analyze_signal tests
# =============================================================================


async def test_analyze_signal_returns_none_for_zero_price():
    """Returns None when current_price is zero or negative."""
    strategy = _make_strategy()
    result = await strategy.analyze_signal([], 0.0)
    assert result is None


async def test_analyze_signal_hold_when_no_requote_needed():
    """Returns hold signal when within refresh interval and threshold."""
    strategy = _make_strategy(
        order_refresh_interval=3600.0,
        recenter_threshold_pct=5.0,
    )
    now = time.time()
    strategy.record_quote(50_000.0, now=now)
    result = await strategy.analyze_signal([], 50_010.0, now=now + 1.0)
    assert result is not None
    assert result["signal_type"] == "hold"
    assert result["indicators"]["requote"] is False


async def test_analyze_signal_requote_happy_path():
    """Returns requote signal on first call (no prior quote)."""
    strategy = _make_strategy(
        spread_bps=20.0,
        order_size=100.0,
        order_refresh_interval=60.0,
    )
    result = await strategy.analyze_signal([], 50_000.0)
    assert result is not None
    assert result["signal_type"] == "requote"
    assert "bid_price" in result
    assert "ask_price" in result
    assert result["bid_price"] < 50_000.0
    assert result["ask_price"] > 50_000.0
    assert result["buy_size"] == pytest.approx(100.0)
    assert result["sell_size"] == pytest.approx(100.0)


async def test_analyze_signal_uses_orderbook_midprice():
    """analyze_signal uses order-book mid-price when provided."""
    strategy = _make_strategy(spread_bps=0.0)
    order_book = {"best_bid": 49_000.0, "best_ask": 51_000.0}
    result = await strategy.analyze_signal([], 50_000.0, order_book=order_book)
    assert result is not None
    assert result["signal_type"] == "requote"
    assert result["indicators"]["reference_price"] == pytest.approx(50_000.0)


async def test_analyze_signal_includes_inventory_skew():
    """analyze_signal applies inventory skew to buy/sell sizes."""
    strategy = _make_strategy(
        order_size=100.0,
        max_inventory=1.0,
    )
    # At max inventory: buy_size → 0, sell_size → 200
    result = await strategy.analyze_signal([], 50_000.0, current_inventory=1.0)
    assert result is not None
    assert result["buy_size"] == pytest.approx(0.0)
    assert result["sell_size"] == pytest.approx(200.0)


async def test_analyze_signal_updates_last_reference_price():
    """record_quote is called so subsequent signals won't re-quote immediately."""
    strategy = _make_strategy(
        order_refresh_interval=3600.0,
        recenter_threshold_pct=5.0,
    )
    now = time.time()
    await strategy.analyze_signal([], 50_000.0, now=now)
    # Price hasn't moved; still within interval → should hold
    result = await strategy.analyze_signal([], 50_000.0, now=now + 1.0)
    assert result["signal_type"] == "hold"


async def test_analyze_signal_requote_after_interval():
    """Second analyze_signal re-quotes once the interval has elapsed."""
    strategy = _make_strategy(order_refresh_interval=30.0)
    now = time.time()
    await strategy.analyze_signal([], 50_000.0, now=now)
    result = await strategy.analyze_signal([], 50_000.0, now=now + 31.0)
    assert result["signal_type"] == "requote"


# =============================================================================
# should_buy / should_sell tests
# =============================================================================


async def test_should_buy_returns_true_on_requote():
    """should_buy returns True when signal is 'requote' with positive buy_size."""
    strategy = _make_strategy()
    signal = {
        "signal_type": "requote",
        "bid_price": 49_950.0,
        "ask_price": 50_050.0,
        "buy_size": 100.0,
        "sell_size": 100.0,
    }
    should, amount, reason = await strategy.should_buy(signal, None, 1_000.0)
    assert should is True
    assert amount == pytest.approx(100.0)
    assert "49950" in reason or "bid" in reason.lower()


async def test_should_buy_returns_false_on_hold():
    """should_buy returns False when signal is 'hold'."""
    strategy = _make_strategy()
    signal = {"signal_type": "hold"}
    should, amount, reason = await strategy.should_buy(signal, None, 1_000.0)
    assert should is False
    assert amount == pytest.approx(0.0)


async def test_should_buy_returns_false_when_buy_size_zero():
    """should_buy returns False when buy_size has been skewed to zero."""
    strategy = _make_strategy()
    signal = {
        "signal_type": "requote",
        "bid_price": 49_950.0,
        "ask_price": 50_050.0,
        "buy_size": 0.0,
        "sell_size": 200.0,
    }
    should, amount, reason = await strategy.should_buy(signal, None, 1_000.0)
    assert should is False
    assert amount == pytest.approx(0.0)


async def test_should_sell_returns_true_on_requote():
    """should_sell returns True when signal is 'requote' with positive sell_size."""
    strategy = _make_strategy()
    signal = {
        "signal_type": "requote",
        "bid_price": 49_950.0,
        "ask_price": 50_050.0,
        "buy_size": 100.0,
        "sell_size": 100.0,
    }
    should, reason = await strategy.should_sell(signal, None, 50_000.0)
    assert should is True
    assert "50050" in reason or "ask" in reason.lower()


async def test_should_sell_returns_false_on_hold():
    """should_sell returns False when signal is 'hold'."""
    strategy = _make_strategy()
    signal = {"signal_type": "hold"}
    should, reason = await strategy.should_sell(signal, None, 50_000.0)
    assert should is False


async def test_should_sell_returns_false_when_sell_size_zero():
    """should_sell returns False when sell_size has been skewed to zero."""
    strategy = _make_strategy()
    signal = {
        "signal_type": "requote",
        "bid_price": 49_950.0,
        "ask_price": 50_050.0,
        "buy_size": 200.0,
        "sell_size": 0.0,
    }
    should, reason = await strategy.should_sell(signal, None, 50_000.0)
    assert should is False


# =============================================================================
# Account isolation tests (HARD RULE)
# =============================================================================


def test_account_isolation_independent_instances():
    """Two strategy instances do not share state — account A never bleeds into B."""
    from app.strategies.market_making import MarketMakingStrategy

    config_a = {
        "spread_bps": 10.0,
        "order_size": 50.0,
        "max_inventory": 2.0,
        "recenter_threshold_pct": 0.5,
        "order_refresh_interval": 3600.0,
        "quote_currency": "USD",
    }
    config_b = {
        "spread_bps": 40.0,
        "order_size": 200.0,
        "max_inventory": 0.5,
        "recenter_threshold_pct": 1.0,
        "order_refresh_interval": 3600.0,
        "quote_currency": "BTC",
    }

    account_a = MarketMakingStrategy(config_a)
    account_b = MarketMakingStrategy(config_b)

    now = time.time()
    account_a.record_quote(100_000.0, now=now)

    # Account B has no recorded quote — it must still need a requote
    assert account_b.needs_requote(50_000.0, now=now + 1.0) is True

    # Account A's last reference price must not appear in account B
    assert account_b._last_reference_price != account_a._last_reference_price


async def test_account_isolation_signals_independent():
    """analyze_signal on account B is not affected by account A's prior signal."""
    from app.strategies.market_making import MarketMakingStrategy

    config_a = {
        "spread_bps": 20.0, "order_size": 100.0, "max_inventory": 1.0,
        "recenter_threshold_pct": 0.5, "order_refresh_interval": 3600.0, "quote_currency": "USD",
    }
    config_b = dict(config_a)  # identical config, different instance

    account_a = MarketMakingStrategy(config_a)
    account_b = MarketMakingStrategy(config_b)

    now = time.time()
    # Account A quotes now → it won't requote again for 3600 s
    await account_a.analyze_signal([], 50_000.0, now=now)

    # Account B has never quoted → must return requote, not hold
    result_b = await account_b.analyze_signal([], 50_000.0, now=now + 1.0)
    assert result_b["signal_type"] == "requote", (
        "Account B incorrectly received hold signal from Account A's state"
    )


def test_class_level_state_not_shared():
    """No class-level mutable state leaks across instances."""
    from app.strategies.market_making import MarketMakingStrategy

    a = MarketMakingStrategy({
        "spread_bps": 20.0, "order_size": 100.0, "max_inventory": 1.0,
        "recenter_threshold_pct": 0.5, "order_refresh_interval": 60.0, "quote_currency": "USD",
    })
    b = MarketMakingStrategy({
        "spread_bps": 20.0, "order_size": 100.0, "max_inventory": 1.0,
        "recenter_threshold_pct": 0.5, "order_refresh_interval": 60.0, "quote_currency": "USD",
    })

    now = time.time()
    a.record_quote(99_000.0, now=now)

    # b's state must be untouched
    assert b._last_reference_price == 0.0
    assert b._last_quote_time == 0.0

    # Mutate b — must not affect a
    b.record_quote(1_000.0, now=now + 1.0)
    assert a._last_reference_price == pytest.approx(99_000.0)


# =============================================================================
# Edge / failure case tests
# =============================================================================


def test_validate_config_logs_warning_on_zero_spread(caplog):
    """validate_config logs a warning when spread_bps <= 0."""
    import logging
    with caplog.at_level(logging.WARNING, logger="app.strategies.market_making"):
        _make_strategy(spread_bps=0.0)
    assert any("spread_bps" in r.message for r in caplog.records)


def test_validate_config_logs_warning_on_zero_order_size(caplog):
    """validate_config logs a warning when order_size <= 0."""
    import logging
    with caplog.at_level(logging.WARNING, logger="app.strategies.market_making"):
        _make_strategy(order_size=0.0)
    assert any("order_size" in r.message for r in caplog.records)


async def test_analyze_signal_negative_price_returns_none():
    """analyze_signal returns None for negative price."""
    strategy = _make_strategy()
    result = await strategy.analyze_signal([], -1.0)
    assert result is None


def test_compute_quote_prices_very_small_spread():
    """Extremely small spread still produces bid < ask."""
    strategy = _make_strategy(spread_bps=0.001)
    quotes = strategy.compute_quote_prices(50_000.0)
    assert quotes["bid_price"] < quotes["ask_price"]


def test_record_quote_updates_both_fields():
    """record_quote updates _last_quote_time and _last_reference_price."""
    strategy = _make_strategy()
    now = 1_700_000_000.0
    strategy.record_quote(42_000.0, now=now)
    assert strategy._last_quote_time == pytest.approx(now)
    assert strategy._last_reference_price == pytest.approx(42_000.0)
