"""
Fear & Greed Index Indicator Evaluator

Provides FEAR_GREED as an aggregate indicator that returns the current
Fear & Greed Index value (0-100) from the alternative.me API.

The Fear & Greed Index is a market sentiment indicator:
  0-24: Extreme Fear (potentially good buy opportunity)
  25-44: Fear
  45-55: Neutral
  56-75: Greed
  76-100: Extreme Greed (potentially good sell opportunity)

This indicator can be used in the condition builder like any other:
    FEAR_GREED <= 25   (buy when market is in fear)
    FEAR_GREED >= 75   (sell when market is in greed)

Data is fetched from https://api.alternative.me/fng/ and cached for 1 hour
in the process-level cache.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 3600  # 1 hour
_CACHE: Optional[dict[str, Any]] = None  # {"value": int, "fetched_at": float}

_DEFAULT_VALUE = 50  # Neutral if API is unavailable


@dataclass
class FearGreedParams:
    """Parameters for Fear & Greed indicator evaluation."""
    cache_ttl_seconds: int = _CACHE_TTL_SECONDS

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "FearGreedParams":
        return cls(
            cache_ttl_seconds=int(config.get("fear_greed_cache_ttl", _CACHE_TTL_SECONDS)),
        )


@dataclass
class FearGreedResult:
    """Result of Fear & Greed index evaluation."""
    value: int  # 0-100
    classification: str  # "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
    rejection_reason: Optional[str] = None


def _classify(value: int) -> str:
    """Classify the Fear & Greed value into a sentiment label."""
    if value <= 24:
        return "Extreme Fear"
    elif value <= 44:
        return "Fear"
    elif value <= 55:
        return "Neutral"
    elif value <= 75:
        return "Greed"
    else:
        return "Extreme Greed"


class FearGreedIndicatorEvaluator:
    """Evaluates the Fear & Greed Index from the alternative.me API."""

    async def evaluate(self, params: Optional[FearGreedParams] = None) -> FearGreedResult:
        """Fetch the current Fear & Greed Index value.

        Uses a process-level cache to avoid hitting the API on every
        strategy evaluation cycle. Falls back to the last known value
        or a neutral default if the API is unavailable.
        """
        global _CACHE
        params = params or FearGreedParams()
        now = time.time()

        # Check cache
        if _CACHE and (now - _CACHE["fetched_at"]) < params.cache_ttl_seconds:
            value = _CACHE["value"]
            return FearGreedResult(value=value, classification=_classify(value))

        # Fetch from API
        try:
            import aiohttp

            url = "https://api.alternative.me/fng/?limit=1"
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"Fear & Greed API returned status {resp.status}")
                        return self._fallback(now)
                    data = await resp.json()
                    entries = data.get("data", [])
                    if not entries:
                        logger.warning("Fear & Greed API returned empty data")
                        return self._fallback(now)
                    value = int(entries[0].get("value", _DEFAULT_VALUE))
                    _CACHE = {"value": value, "fetched_at": now}
                    logger.info(f"Fear & Greed Index: {value} ({_classify(value)})")
                    return FearGreedResult(value=value, classification=_classify(value))

        except Exception as e:
            logger.warning(f"Fear & Greed API fetch failed: {e}")
            return self._fallback(now)

    def _fallback(self, now: float) -> FearGreedResult:
        """Return last known value or neutral default."""
        if _CACHE:
            value = _CACHE["value"]
            return FearGreedResult(
                value=value,
                classification=_classify(value),
                rejection_reason="Using cached value (API unavailable)",
            )
        return FearGreedResult(
            value=_DEFAULT_VALUE,
            classification=_classify(_DEFAULT_VALUE),
            rejection_reason="API unavailable and no cached value",
        )


def clear_fear_greed_cache() -> None:
    """Clear the process-level Fear & Greed cache. Used in tests."""
    global _CACHE
    _CACHE = None
