"""Tool: get_candle_window

Argument-taking tool that fetches a compact OHLCV window on a requested
timeframe. Lets the model zoom in on short-term volatility or out to a daily
context without us pre-sending a big candle block on every call.

Returns a compact shape (t/o/h/l/c/v) to keep prompt size low.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.coinbase_api.public_market_data import get_candles as fetch_candles
from app.indicators.ai_tools.base import Tool, ToolContext, register


# Public Coinbase granularities — synthetic aggregations (4h, 1w, etc.) are
# intentionally excluded. The model can compose 1h windows if it needs 4h.
_TIMEFRAME_TO_GRANULARITY: Dict[str, str] = {
    "5m": "FIVE_MINUTE",
    "15m": "FIFTEEN_MINUTE",
    "1h": "ONE_HOUR",
    "6h": "SIX_HOUR",
    "1d": "ONE_DAY",
}

_GRANULARITY_TO_SECONDS: Dict[str, int] = {
    "FIVE_MINUTE": 300,
    "FIFTEEN_MINUTE": 900,
    "ONE_HOUR": 3600,
    "SIX_HOUR": 21600,
    "ONE_DAY": 86400,
}

_MIN_COUNT = 10
_MAX_COUNT = 100


def _compact(candle: Dict[str, Any]) -> Dict[str, Any]:
    """Coinbase returns strings; coerce to float for a tighter prompt payload."""
    def _f(key: str) -> float:
        v = candle.get(key)
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0
    return {
        "t": int(float(candle.get("start", 0))),
        "o": _f("open"),
        "h": _f("high"),
        "l": _f("low"),
        "c": _f("close"),
        "v": _f("volume"),
    }


async def _run(input: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    import time

    timeframe = str(input.get("timeframe", "")).lower()
    requested_count = int(input.get("count", 30))
    clamped_count = max(_MIN_COUNT, min(_MAX_COUNT, requested_count))

    granularity = _TIMEFRAME_TO_GRANULARITY.get(timeframe)
    if granularity is None:
        return {
            "error": (
                f"Unsupported timeframe '{timeframe}'. "
                f"Valid: {sorted(_TIMEFRAME_TO_GRANULARITY.keys())}"
            )
        }

    seconds = _GRANULARITY_TO_SECONDS[granularity]
    end = int(time.time())
    start = end - clamped_count * seconds

    raw = await fetch_candles(
        product_id=ctx.product_id,
        start=start,
        end=end,
        granularity=granularity,
    )
    # Coinbase returns newest-first — reverse to chronological so the model
    # reads left-to-right in time.
    raw = list(reversed(raw or []))[-clamped_count:]
    candles: List[Dict[str, Any]] = [_compact(c) for c in raw]

    return {
        "product_id": ctx.product_id,
        "timeframe": timeframe,
        "granularity": granularity,
        "requested_count": requested_count,
        "returned_count": len(candles),
        "candles": candles,
    }


TOOL = Tool(
    name="get_candle_window",
    description=(
        "Fetch a compact OHLCV window on the requested timeframe. Useful when "
        "summary metrics (RSI / MACD / BB) look ambiguous and you want to see "
        "the actual candle shapes — compressions, failed breakouts, wicks. "
        "Each candle is {t: unix-seconds, o, h, l, c, v}. Arguments: "
        "timeframe ∈ {5m, 15m, 1h, 6h, 1d}, count 10-100 (clamped)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "timeframe": {
                "type": "string",
                "enum": sorted(_TIMEFRAME_TO_GRANULARITY.keys()),
                "description": "Candle timeframe.",
            },
            "count": {
                "type": "integer",
                "minimum": _MIN_COUNT,
                "maximum": _MAX_COUNT,
                "description": "Number of candles to return (clamped to 10-100).",
            },
        },
        "required": ["timeframe", "count"],
    },
    fn=_run,
)

register(TOOL)
