"""
Tests for backend/app/services/ai_grid_optimizer.py

AI-Dynamic Grid Optimizer — uses AI to analyze grid performance and recommend
parameter adjustments.
"""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Bot, PendingOrder, Position, Trade
from app.services.ai_grid_optimizer import (
    analyze_grid_performance,
    apply_ai_recommendations,
    calculate_market_metrics,
    get_ai_grid_recommendations,
    run_ai_grid_optimization,
)


# ---------------------------------------------------------------------------
# Helpers / Factories
# ---------------------------------------------------------------------------


def _make_bot(
    bot_id=1,
    user_id=1,
    product_id="BTC-USD",
    strategy_config=None,
):
    """Create a Bot-like object with strategy_config."""
    bot = MagicMock(spec=Bot)
    bot.id = bot_id
    bot.user_id = user_id
    bot.product_id = product_id
    # strategy_config must be a real dict (code mutates it)
    bot.strategy_config = strategy_config or {}
    return bot


def _make_position(position_id=1, bot_id=1):
    pos = MagicMock(spec=Position)
    pos.id = position_id
    pos.bot_id = bot_id
    return pos


def _make_grid_state(
    num_levels=10,
    filled=3,
    total_profit=0.005,
    breakout_count=2,
    hours_ago=12,
):
    """Build a realistic grid_state dict."""
    levels = []
    for i in range(num_levels):
        status = "filled" if i < filled else "open"
        levels.append({"price": 50000 + i * 100, "status": status})

    return {
        "grid_levels": levels,
        "total_profit_quote": total_profit,
        "breakout_count": breakout_count,
        "initialized_at": (
            datetime.utcnow() - timedelta(hours=hours_ago)
        ).isoformat(),
    }


def _candles_from_prices(prices):
    """Convert a list of close prices to candle dicts."""
    return [
        {
            "open": str(p * 0.999),
            "high": str(p * 1.005),
            "low": str(p * 0.995),
            "close": str(p),
            "volume": "100",
        }
        for p in prices
    ]


# ---------------------------------------------------------------------------
# analyze_grid_performance
# ---------------------------------------------------------------------------


class TestAnalyzeGridPerformance:
    """Tests for analyze_grid_performance()"""

    @pytest.mark.asyncio
    async def test_happy_path_returns_correct_metrics(self, db_session):
        """Happy path: metrics calculated correctly from grid state."""
        grid_state = _make_grid_state(
            num_levels=10, filled=3, total_profit=0.006, breakout_count=2, hours_ago=24
        )
        bot = _make_bot(strategy_config={"grid_state": grid_state})
        position = _make_position()

        # Mock DB results (no trades, no pending orders)
        # Set up the db mock to return empty results for both queries
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        db_session.execute = AsyncMock(return_value=mock_result)

        result = await analyze_grid_performance(bot, position, db_session)

        assert result["total_levels"] == 10
        assert result["filled_levels"] == 3
        assert result["pending_levels"] == 0
        assert result["fill_rate_percent"] == pytest.approx(30.0)
        assert result["total_profit_quote"] == pytest.approx(0.006)
        assert result["avg_profit_per_level"] == pytest.approx(0.002)
        assert result["breakout_count"] == 2
        assert result["trades_count"] == 0
        # ~24 hours running → ~2 breakouts/day
        assert result["breakouts_per_day"] == pytest.approx(2.0, rel=0.1)

    @pytest.mark.asyncio
    async def test_zero_levels_returns_zero_fill_rate(self, db_session):
        """Edge case: empty grid_state has no levels → fill rate 0."""
        bot = _make_bot(strategy_config={"grid_state": {}})
        position = _make_position()

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        db_session.execute = AsyncMock(return_value=mock_result)

        result = await analyze_grid_performance(bot, position, db_session)

        assert result["total_levels"] == 0
        assert result["filled_levels"] == 0
        assert result["fill_rate_percent"] == 0
        assert result["avg_profit_per_level"] == 0

    @pytest.mark.asyncio
    async def test_no_initialized_at_defaults_to_utcnow(self, db_session):
        """Edge case: grid_state missing initialized_at uses utcnow."""
        bot = _make_bot(strategy_config={
            "grid_state": {
                "grid_levels": [{"price": 100, "status": "open"}],
            }
        })
        position = _make_position()

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        db_session.execute = AsyncMock(return_value=mock_result)

        result = await analyze_grid_performance(bot, position, db_session)

        # hours_running should be close to 0 since initialized_at defaults to now
        assert result["hours_running"] < 0.1

    @pytest.mark.asyncio
    async def test_with_pending_orders_counts_correctly(self, db_session):
        """Happy path: pending orders are counted from DB results."""
        grid_state = _make_grid_state(num_levels=5, filled=2)
        bot = _make_bot(strategy_config={"grid_state": grid_state})
        position = _make_position()

        pending1 = MagicMock(spec=PendingOrder)
        pending1.status = "pending"
        pending2 = MagicMock(spec=PendingOrder)
        pending2.status = "pending"
        pending3 = MagicMock(spec=PendingOrder)
        pending3.status = "filled"

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            mock_scalars = MagicMock()
            if call_count == 1:
                # Trades query
                mock_scalars.all.return_value = [MagicMock(spec=Trade)]
            else:
                # Pending orders query
                mock_scalars.all.return_value = [pending1, pending2, pending3]
            mock_result.scalars.return_value = mock_scalars
            return mock_result

        db_session.execute = mock_execute

        result = await analyze_grid_performance(bot, position, db_session)

        assert result["pending_levels"] == 2  # Only "pending" status counted
        assert result["trades_count"] == 1


# ---------------------------------------------------------------------------
# calculate_market_metrics
# ---------------------------------------------------------------------------


class TestCalculateMarketMetrics:
    """Tests for calculate_market_metrics()"""

    @pytest.mark.asyncio
    async def test_happy_path_returns_market_data(self, mock_exchange_client):
        """Happy path: returns price, volatility, range, and trend."""
        # Sideways market: prices oscillate around 50000
        prices = [50000, 50100, 49900, 50050, 49950, 50000, 50020, 49980]
        candles = _candles_from_prices(prices)
        mock_exchange_client.get_candles = AsyncMock(return_value=candles)

        result = await calculate_market_metrics(
            "BTC-USD", mock_exchange_client, lookback_hours=24
        )

        assert "error" not in result
        assert result["current_price"] == pytest.approx(49980.0)
        assert "volatility_percent" in result
        assert result["trend"] == "sideways"
        assert result["high_24h"] > result["low_24h"]

    @pytest.mark.asyncio
    async def test_insufficient_candles_returns_error(self, mock_exchange_client):
        """Edge case: fewer than 7 candles returns error dict."""
        candles = _candles_from_prices([100, 101, 102])
        mock_exchange_client.get_candles = AsyncMock(return_value=candles)

        result = await calculate_market_metrics(
            "BTC-USD", mock_exchange_client
        )

        assert "error" in result
        assert result["error"] == "Insufficient market data"

    @pytest.mark.asyncio
    async def test_empty_candles_returns_error(self, mock_exchange_client):
        """Edge case: no candles at all returns error."""
        mock_exchange_client.get_candles = AsyncMock(return_value=[])

        result = await calculate_market_metrics(
            "BTC-USD", mock_exchange_client
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_upward_trend_detected(self, mock_exchange_client):
        """Happy path: strongly rising prices detected as upward trend."""
        # First half around 100, second half around 110 (>2% higher)
        prices = [100, 100, 101, 100, 108, 110, 111, 112]
        candles = _candles_from_prices(prices)
        mock_exchange_client.get_candles = AsyncMock(return_value=candles)

        result = await calculate_market_metrics(
            "BTC-USD", mock_exchange_client
        )

        assert result["trend"] == "upward"

    @pytest.mark.asyncio
    async def test_downward_trend_detected(self, mock_exchange_client):
        """Happy path: strongly falling prices detected as downward trend."""
        # First half around 110, second half around 100 (<-2%)
        prices = [112, 111, 110, 108, 100, 101, 100, 99]
        candles = _candles_from_prices(prices)
        mock_exchange_client.get_candles = AsyncMock(return_value=candles)

        result = await calculate_market_metrics(
            "BTC-USD", mock_exchange_client
        )

        assert result["trend"] == "downward"

    @pytest.mark.asyncio
    async def test_exchange_exception_returns_error(self, mock_exchange_client):
        """Failure: exchange client raises → returns error dict."""
        mock_exchange_client.get_candles = AsyncMock(
            side_effect=Exception("Connection timeout")
        )

        result = await calculate_market_metrics(
            "BTC-USD", mock_exchange_client
        )

        assert "error" in result
        assert "Connection timeout" in result["error"]


# ---------------------------------------------------------------------------
# get_ai_grid_recommendations
# ---------------------------------------------------------------------------


class TestGetAiGridRecommendations:
    """Tests for get_ai_grid_recommendations()"""

    @pytest.mark.asyncio
    async def test_ai_disabled_returns_none(self, db_session):
        """Happy path: AI optimization disabled → returns None immediately."""
        bot = _make_bot(strategy_config={"enable_ai_optimization": False})
        position = _make_position()

        result = await get_ai_grid_recommendations(
            bot, position, {}, {}, db_session
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_happy_path_parses_json_code_block(self, db_session):
        """Happy path: AI returns JSON in markdown code block → parsed."""
        bot = _make_bot(strategy_config={
            "enable_ai_optimization": True,
            "ai_provider": "anthropic",
            "ai_model": "claude-sonnet-4.5",
            "grid_state": _make_grid_state(),
        })
        position = _make_position()

        ai_response = """Here's my analysis:

```json
{
  "recommendation_summary": "Widen range to reduce breakouts",
  "confidence": 85,
  "adjustments": {
    "num_grid_levels": 25,
    "upper_limit": 55000,
    "lower_limit": 45000
  },
  "reasoning": "High breakout frequency suggests tight range",
  "expected_impact": "Reduce breakouts by 50%"
}
```
"""
        mock_ai_client = AsyncMock()
        mock_ai_client.analyze = AsyncMock(return_value=ai_response)

        with patch(
            "app.services.ai_grid_optimizer.get_ai_client",
            new_callable=AsyncMock,
            return_value=mock_ai_client,
        ):
            result = await get_ai_grid_recommendations(
                bot, position,
                {"filled_levels": 5, "total_levels": 10,
                 "fill_rate_percent": 50, "total_profit_quote": 0.01,
                 "avg_profit_per_level": 0.002, "hours_running": 12,
                 "breakout_count": 3, "breakouts_per_day": 6,
                 "trades_count": 20},
                {"current_price": 50000, "volatility_percent": 2.5,
                 "high_24h": 51000, "low_24h": 49000,
                 "price_range_percent": 4.0, "trend": "sideways"},
                db_session,
            )

        assert result is not None
        assert result["confidence"] == 85
        assert result["adjustments"]["num_grid_levels"] == 25

    @pytest.mark.asyncio
    async def test_parses_json_without_code_block(self, db_session):
        """Edge case: AI returns raw JSON without markdown code block."""
        bot = _make_bot(strategy_config={
            "enable_ai_optimization": True,
            "grid_state": _make_grid_state(),
        })
        position = _make_position()

        ai_response = '{"recommendation_summary": "No changes", "confidence": 30, "adjustments": {}}'

        mock_ai_client = AsyncMock()
        mock_ai_client.analyze = AsyncMock(return_value=ai_response)

        with patch(
            "app.services.ai_grid_optimizer.get_ai_client",
            new_callable=AsyncMock,
            return_value=mock_ai_client,
        ):
            result = await get_ai_grid_recommendations(
                bot, position, _perf_metrics(), _market_metrics(), db_session
            )

        assert result is not None
        assert result["confidence"] == 30

    @pytest.mark.asyncio
    async def test_invalid_json_returns_none(self, db_session):
        """Failure: AI returns no valid JSON → returns None."""
        bot = _make_bot(strategy_config={
            "enable_ai_optimization": True,
            "grid_state": _make_grid_state(),
        })
        position = _make_position()

        mock_ai_client = AsyncMock()
        mock_ai_client.analyze = AsyncMock(
            return_value="I don't know what to recommend."
        )

        with patch(
            "app.services.ai_grid_optimizer.get_ai_client",
            new_callable=AsyncMock,
            return_value=mock_ai_client,
        ):
            result = await get_ai_grid_recommendations(
                bot, position, _perf_metrics(), _market_metrics(), db_session
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_ai_client_failure_returns_none(self, db_session):
        """Failure: get_ai_client raises → returns None gracefully."""
        bot = _make_bot(strategy_config={
            "enable_ai_optimization": True,
            "grid_state": _make_grid_state(),
        })
        position = _make_position()

        with patch(
            "app.services.ai_grid_optimizer.get_ai_client",
            new_callable=AsyncMock,
            side_effect=ValueError("No API key configured"),
        ):
            result = await get_ai_grid_recommendations(
                bot, position, _perf_metrics(), _market_metrics(), db_session
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_ai_analyze_exception_returns_none(self, db_session):
        """Failure: ai_client.analyze() raises → returns None."""
        bot = _make_bot(strategy_config={
            "enable_ai_optimization": True,
            "grid_state": _make_grid_state(),
        })
        position = _make_position()

        mock_ai_client = AsyncMock()
        mock_ai_client.analyze = AsyncMock(
            side_effect=RuntimeError("API quota exceeded")
        )

        with patch(
            "app.services.ai_grid_optimizer.get_ai_client",
            new_callable=AsyncMock,
            return_value=mock_ai_client,
        ):
            result = await get_ai_grid_recommendations(
                bot, position, _perf_metrics(), _market_metrics(), db_session
            )

        assert result is None


# ---------------------------------------------------------------------------
# apply_ai_recommendations
# ---------------------------------------------------------------------------


class TestApplyAiRecommendations:
    """Tests for apply_ai_recommendations()"""

    @pytest.mark.asyncio
    async def test_no_adjustments_returns_false(
        self, db_session, mock_exchange_client
    ):
        """Edge case: all adjustments are null → returns False, no rebalance."""
        bot = _make_bot(strategy_config={"grid_state": {}})
        position = _make_position()
        recommendations = {
            "confidence": 80,
            "adjustments": {"num_grid_levels": None, "grid_type": None},
        }

        result = await apply_ai_recommendations(
            bot, position, recommendations, mock_exchange_client, db_session
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_low_confidence_returns_false(
        self, db_session, mock_exchange_client
    ):
        """Edge case: confidence below 50% → skips adjustments."""
        bot = _make_bot(strategy_config={"grid_state": {}})
        position = _make_position()
        recommendations = {
            "confidence": 30,
            "adjustments": {"num_grid_levels": 25},
        }

        result = await apply_ai_recommendations(
            bot, position, recommendations, mock_exchange_client, db_session
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_happy_path_applies_adjustments(
        self, db_session, mock_exchange_client
    ):
        """Happy path: high-confidence adjustments applied + rebalance triggered."""
        bot = _make_bot(strategy_config={
            "grid_state": {},
            "grid_type": "arithmetic",
            "upper_limit": 55000,
            "lower_limit": 45000,
            "num_grid_levels": 20,
        })
        position = _make_position()
        recommendations = {
            "confidence": 85,
            "adjustments": {"num_grid_levels": 30},
            "reasoning": "More levels for volatile market",
            "expected_impact": "+15% fill rate",
        }

        mock_exchange_client.get_current_price = AsyncMock(return_value=50000.0)
        db_session.commit = AsyncMock()

        with patch(
            "app.services.grid_trading_service.rebalance_grid_on_breakout",
            new_callable=AsyncMock,
        ) as mock_rebalance, patch(
            "app.strategies.grid_trading.calculate_arithmetic_levels",
            return_value=[45000 + i * 345 for i in range(30)],
        ):
            result = await apply_ai_recommendations(
                bot, position, recommendations, mock_exchange_client, db_session
            )

        assert result is True
        assert bot.strategy_config["num_grid_levels"] == 30
        assert len(bot.strategy_config["grid_state"]["ai_adjustments"]) == 1
        adj_log = bot.strategy_config["grid_state"]["ai_adjustments"][0]
        assert adj_log["confidence"] == 85
        assert adj_log["reasoning"] == "More levels for volatile market"
        mock_rebalance.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_geometric_grid_type_uses_geometric_levels(
        self, db_session, mock_exchange_client
    ):
        """Happy path: geometric grid type → calls calculate_geometric_levels."""
        bot = _make_bot(strategy_config={
            "grid_state": {},
            "grid_type": "geometric",
            "upper_limit": 55000,
            "lower_limit": 45000,
            "num_grid_levels": 20,
        })
        position = _make_position()
        recommendations = {
            "confidence": 75,
            "adjustments": {"upper_limit": 60000},
        }

        mock_exchange_client.get_current_price = AsyncMock(return_value=50000.0)
        db_session.commit = AsyncMock()

        with patch(
            "app.services.grid_trading_service.rebalance_grid_on_breakout",
            new_callable=AsyncMock,
        ), patch(
            "app.strategies.grid_trading.calculate_geometric_levels",
            return_value=[45000 + i * 500 for i in range(20)],
        ) as mock_geo:
            result = await apply_ai_recommendations(
                bot, position, recommendations, mock_exchange_client, db_session
            )

        assert result is True
        mock_geo.assert_called_once()
        # upper_limit should be updated in strategy_config
        assert bot.strategy_config["upper_limit"] == 60000

    @pytest.mark.asyncio
    async def test_empty_adjustments_dict_returns_false(
        self, db_session, mock_exchange_client
    ):
        """Edge case: empty adjustments dict → returns False."""
        bot = _make_bot(strategy_config={"grid_state": {}})
        position = _make_position()
        recommendations = {"confidence": 90, "adjustments": {}}

        result = await apply_ai_recommendations(
            bot, position, recommendations, mock_exchange_client, db_session
        )

        assert result is False


# ---------------------------------------------------------------------------
# run_ai_grid_optimization (orchestrator)
# ---------------------------------------------------------------------------


class TestRunAiGridOptimization:
    """Tests for run_ai_grid_optimization()"""

    @pytest.mark.asyncio
    async def test_ai_disabled_returns_none(
        self, db_session, mock_exchange_client
    ):
        """Happy path: AI optimization disabled → early return None."""
        bot = _make_bot(strategy_config={"enable_ai_optimization": False})
        position = _make_position()

        result = await run_ai_grid_optimization(
            bot, position, mock_exchange_client, db_session
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_interval_not_elapsed_returns_none(
        self, db_session, mock_exchange_client
    ):
        """Edge case: too soon since last AI check → returns None."""
        bot = _make_bot(strategy_config={
            "enable_ai_optimization": True,
            "ai_adjustment_interval_minutes": 120,
            "grid_state": {
                "last_ai_check": (
                    datetime.utcnow() - timedelta(minutes=30)
                ).isoformat(),
            },
        })
        position = _make_position()

        result = await run_ai_grid_optimization(
            bot, position, mock_exchange_client, db_session
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_happy_path_full_pipeline(
        self, db_session, mock_exchange_client
    ):
        """Happy path: full optimization pipeline runs end-to-end."""
        grid_state = _make_grid_state(num_levels=10, filled=5)
        grid_state["last_ai_check"] = (
            datetime.utcnow() - timedelta(hours=3)
        ).isoformat()

        bot = _make_bot(strategy_config={
            "enable_ai_optimization": True,
            "ai_adjustment_interval_minutes": 120,
            "grid_state": grid_state,
            "grid_type": "arithmetic",
            "upper_limit": 55000,
            "lower_limit": 45000,
            "num_grid_levels": 20,
        })
        position = _make_position()

        # Mock exchange for candles + price
        prices = [50000, 50100, 49900, 50050, 49950, 50000, 50020, 49980]
        candles = _candles_from_prices(prices)
        mock_exchange_client.get_candles = AsyncMock(return_value=candles)
        mock_exchange_client.get_current_price = AsyncMock(return_value=50000.0)

        # Mock DB queries for analyze_grid_performance
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.commit = AsyncMock()

        ai_json = json.dumps({
            "recommendation_summary": "Widen range",
            "confidence": 80,
            "adjustments": {"num_grid_levels": 25},
            "reasoning": "Better fill rate",
            "expected_impact": "+10% fills",
        })
        ai_response = f"```json\n{ai_json}\n```"

        mock_ai_client = AsyncMock()
        mock_ai_client.analyze = AsyncMock(return_value=ai_response)

        with patch(
            "app.services.ai_grid_optimizer.get_ai_client",
            new_callable=AsyncMock,
            return_value=mock_ai_client,
        ), patch(
            "app.services.grid_trading_service.rebalance_grid_on_breakout",
            new_callable=AsyncMock,
        ), patch(
            "app.strategies.grid_trading.calculate_arithmetic_levels",
            return_value=[45000 + i * 400 for i in range(25)],
        ):
            result = await run_ai_grid_optimization(
                bot, position, mock_exchange_client, db_session
            )

        assert result is not None
        assert result["confidence"] == 80
        assert bot.strategy_config["num_grid_levels"] == 25

    @pytest.mark.asyncio
    async def test_no_recommendations_updates_last_check(
        self, db_session, mock_exchange_client
    ):
        """Edge case: AI returns no recommendations → updates last_ai_check."""
        grid_state = _make_grid_state()
        bot = _make_bot(strategy_config={
            "enable_ai_optimization": True,
            "grid_state": grid_state,
        })
        position = _make_position()

        prices = [50000, 50100, 49900, 50050, 49950, 50000, 50020, 49980]
        candles = _candles_from_prices(prices)
        mock_exchange_client.get_candles = AsyncMock(return_value=candles)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.commit = AsyncMock()

        # AI disabled in config → get_ai_grid_recommendations returns None
        with patch(
            "app.services.ai_grid_optimizer.get_ai_grid_recommendations",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await run_ai_grid_optimization(
                bot, position, mock_exchange_client, db_session
            )

        assert result is None
        # last_ai_check should be updated
        assert "last_ai_check" in bot.strategy_config["grid_state"]
        db_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_low_confidence_returns_none(
        self, db_session, mock_exchange_client
    ):
        """Edge case: recommendations with low confidence → applied=False → returns None."""
        grid_state = _make_grid_state()
        bot = _make_bot(strategy_config={
            "enable_ai_optimization": True,
            "grid_state": grid_state,
            "grid_type": "arithmetic",
            "upper_limit": 55000,
            "lower_limit": 45000,
            "num_grid_levels": 20,
        })
        position = _make_position()

        prices = [50000, 50100, 49900, 50050, 49950, 50000, 50020, 49980]
        candles = _candles_from_prices(prices)
        mock_exchange_client.get_candles = AsyncMock(return_value=candles)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.commit = AsyncMock()

        # Low confidence recommendation
        low_conf = {
            "recommendation_summary": "Maybe increase levels",
            "confidence": 30,
            "adjustments": {"num_grid_levels": 25},
        }

        with patch(
            "app.services.ai_grid_optimizer.get_ai_grid_recommendations",
            new_callable=AsyncMock,
            return_value=low_conf,
        ):
            result = await run_ai_grid_optimization(
                bot, position, mock_exchange_client, db_session
            )

        # Low confidence → apply returns False → orchestrator returns None
        assert result is None

    @pytest.mark.asyncio
    async def test_first_run_no_last_check_proceeds(
        self, db_session, mock_exchange_client
    ):
        """Happy path: no last_ai_check in grid_state → proceeds immediately."""
        bot = _make_bot(strategy_config={
            "enable_ai_optimization": True,
            "grid_state": _make_grid_state(),
        })
        position = _make_position()

        prices = [50000, 50100, 49900, 50050, 49950, 50000, 50020, 49980]
        candles = _candles_from_prices(prices)
        mock_exchange_client.get_candles = AsyncMock(return_value=candles)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.commit = AsyncMock()

        with patch(
            "app.services.ai_grid_optimizer.get_ai_grid_recommendations",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_recs:
            await run_ai_grid_optimization(
                bot, position, mock_exchange_client, db_session
            )

        # Should have proceeded to call get_ai_grid_recommendations
        mock_recs.assert_awaited_once()


# ---------------------------------------------------------------------------
# Helpers for repeated test data
# ---------------------------------------------------------------------------


def _perf_metrics():
    return {
        "filled_levels": 5,
        "total_levels": 10,
        "fill_rate_percent": 50,
        "total_profit_quote": 0.01,
        "avg_profit_per_level": 0.002,
        "hours_running": 12,
        "breakout_count": 3,
        "breakouts_per_day": 6,
        "trades_count": 20,
    }


def _market_metrics():
    return {
        "current_price": 50000,
        "volatility_percent": 2.5,
        "high_24h": 51000,
        "low_24h": 49000,
        "price_range_percent": 4.0,
        "trend": "sideways",
    }
