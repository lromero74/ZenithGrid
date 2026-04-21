"""Tests for the get_candle_window tool.

Covers:
- Happy path — returns compact OHLCV for the requested timeframe + count
- Edge — count clamped to the tool's 10..100 range
- Edge — unknown timeframe returns structured error
- Failure — underlying fetch error surfaced as `{"error": ...}` by the registry
"""

from unittest.mock import AsyncMock, patch

from app.indicators.ai_tools import REGISTRY, ToolContext, execute


def _fake_candles(count=30, base_ts=1_700_000_000, step=900):
    """Coinbase returns newest-first; adapter reverses to oldest-first."""
    return [
        {
            "start": str(base_ts + i * step),
            "open": f"{100 + i * 0.5:.4f}",
            "high": f"{100 + i * 0.5 + 0.5:.4f}",
            "low": f"{100 + i * 0.5 - 0.5:.4f}",
            "close": f"{100 + i * 0.5 + 0.2:.4f}",
            "volume": f"{1000 + i * 10:.2f}",
        }
        for i in range(count)
    ]


class TestGetCandleWindow:
    async def test_happy_path_returns_compact_ohlcv(self):
        ctx = ToolContext(db=None, user_id=1, product_id="ETH-USD", current_price=100.0)
        with patch(
            "app.indicators.ai_tools.candle_window.fetch_candles",
            new_callable=AsyncMock,
            return_value=_fake_candles(count=20),
        ) as fetch:
            result = await execute("get_candle_window", {"timeframe": "15m", "count": 20}, ctx)

        fetch.assert_awaited_once()
        args, kwargs = fetch.call_args
        assert kwargs.get("product_id") == "ETH-USD"
        assert kwargs.get("granularity") == "FIFTEEN_MINUTE"
        assert result["product_id"] == "ETH-USD"
        assert result["timeframe"] == "15m"
        assert len(result["candles"]) == 20
        assert set(result["candles"][0].keys()) == {"t", "o", "h", "l", "c", "v"}

    async def test_unknown_timeframe_returns_error(self):
        ctx = ToolContext(db=None, user_id=1, product_id="ETH-USD", current_price=100.0)
        result = await execute("get_candle_window", {"timeframe": "2m", "count": 20}, ctx)
        assert "error" in result
        assert "2m" in result["error"]

    async def test_count_clamped_to_max(self):
        ctx = ToolContext(db=None, user_id=1, product_id="ETH-USD", current_price=100.0)
        with patch(
            "app.indicators.ai_tools.candle_window.fetch_candles",
            new_callable=AsyncMock,
            return_value=_fake_candles(count=100),
        ):
            result = await execute(
                "get_candle_window", {"timeframe": "15m", "count": 500}, ctx
            )
        assert len(result["candles"]) == 100
        assert result["requested_count"] == 500
        assert result["returned_count"] == 100

    async def test_count_clamped_to_min(self):
        ctx = ToolContext(db=None, user_id=1, product_id="ETH-USD", current_price=100.0)
        with patch(
            "app.indicators.ai_tools.candle_window.fetch_candles",
            new_callable=AsyncMock,
            return_value=_fake_candles(count=10),
        ):
            result = await execute("get_candle_window", {"timeframe": "15m", "count": 1}, ctx)
        assert result["returned_count"] == 10
        assert len(result["candles"]) == 10

    async def test_all_supported_timeframes(self):
        """Every advertised timeframe must map to a valid Coinbase granularity."""
        ctx = ToolContext(db=None, user_id=1, product_id="ETH-USD", current_price=100.0)
        expected = {
            "5m": "FIVE_MINUTE",
            "15m": "FIFTEEN_MINUTE",
            "1h": "ONE_HOUR",
            "6h": "SIX_HOUR",
            "1d": "ONE_DAY",
        }
        for tf, granularity in expected.items():
            with patch(
                "app.indicators.ai_tools.candle_window.fetch_candles",
                new_callable=AsyncMock,
                return_value=_fake_candles(count=10),
            ) as fetch:
                result = await execute(
                    "get_candle_window", {"timeframe": tf, "count": 10}, ctx
                )
            assert fetch.call_args.kwargs["granularity"] == granularity, tf
            assert result["timeframe"] == tf

    async def test_fetch_error_surfaced_as_error_dict(self):
        ctx = ToolContext(db=None, user_id=1, product_id="ETH-USD", current_price=100.0)
        with patch(
            "app.indicators.ai_tools.candle_window.fetch_candles",
            new_callable=AsyncMock,
            side_effect=RuntimeError("upstream down"),
        ):
            result = await execute(
                "get_candle_window", {"timeframe": "15m", "count": 20}, ctx
            )
        assert "error" in result
        assert "upstream down" in result["error"]


class TestRegistry:
    def test_tool_is_registered(self):
        assert "get_candle_window" in REGISTRY
