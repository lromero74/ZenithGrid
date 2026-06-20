"""
Tests for backend/app/indicators/fear_greed_indicator.py

Covers:
- API fetch and parsing
- Cache behavior (TTL respected, stale data not served)
- Classification thresholds
- Fallback behavior on API failure
- Integration with indicator_based strategy (needs_aggregate_indicators)
"""

import pytest
import time
from unittest.mock import AsyncMock, patch, MagicMock

from app.indicators.fear_greed_indicator import (
    FearGreedIndicatorEvaluator,
    FearGreedParams,
    _classify,
    clear_fear_greed_cache,
)


# =============================================================================
# Classification tests
# =============================================================================


def test_classify_extreme_fear():
    assert _classify(0) == "Extreme Fear"
    assert _classify(24) == "Extreme Fear"


def test_classify_fear():
    assert _classify(25) == "Fear"
    assert _classify(44) == "Fear"


def test_classify_neutral():
    assert _classify(45) == "Neutral"
    assert _classify(55) == "Neutral"


def test_classify_greed():
    assert _classify(56) == "Greed"
    assert _classify(75) == "Greed"


def test_classify_extreme_greed():
    assert _classify(76) == "Extreme Greed"
    assert _classify(100) == "Extreme Greed"


# =============================================================================
# Evaluator tests
# =============================================================================


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the Fear & Greed cache before each test."""
    clear_fear_greed_cache()
    yield
    clear_fear_greed_cache()


def _mock_api_response(value=42, classification="Fear"):
    """Build a mock alternative.me API response."""
    return {
        "data": [
            {"value": str(value), "value_classification": classification, "timestamp": "1700000000"}
        ]
    }


async def test_evaluate_fetches_from_api():
    """Evaluate returns the value from the API."""
    evaluator = FearGreedIndicatorEvaluator()

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=_mock_api_response(value=30, classification="Fear"))

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.get = MagicMock(return_value=mock_ctx)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await evaluator.evaluate()

    assert result.value == 30
    assert result.classification == "Fear"
    assert result.rejection_reason is None


async def test_evaluate_uses_cache_on_second_call():
    """Second call within TTL uses cached value without hitting the API."""
    evaluator = FearGreedIndicatorEvaluator()

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=_mock_api_response(value=50))

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.get = MagicMock(return_value=mock_ctx)

    with patch("aiohttp.ClientSession", return_value=mock_session) as mock_session_cls:
        # First call — hits API
        result1 = await evaluator.evaluate()
        assert result1.value == 50
        assert mock_session_cls.call_count == 1

        # Second call — should use cache, not create a new session
        result2 = await evaluator.evaluate()
        assert result2.value == 50
        assert mock_session_cls.call_count == 1  # Still only 1 API call


async def test_evaluate_cache_expires():
    """After TTL expires, a new API call is made."""
    evaluator = FearGreedIndicatorEvaluator()
    params = FearGreedParams(cache_ttl_seconds=0)  # Expire immediately

    # Manually populate cache with a stale value
    import app.indicators.fear_greed_indicator as fgi
    fgi._CACHE = {"value": 77, "fetched_at": time.time() - 1}

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=_mock_api_response(value=22))

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.get = MagicMock(return_value=mock_ctx)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await evaluator.evaluate(params)

    assert result.value == 22  # Fresh value, not the stale 77


async def test_evaluate_api_failure_returns_cached():
    """When API fails and a cached value exists, return the cached value."""
    import app.indicators.fear_greed_indicator as fgi
    # Set cache with an EXPIRED timestamp so the cache check fails (triggering
    # an API call) but _fallback still finds the cached value.
    fgi._CACHE = {"value": 33, "fetched_at": time.time() - 3700}

    evaluator = FearGreedIndicatorEvaluator()

    with patch("aiohttp.ClientSession", side_effect=Exception("Network error")):
        result = await evaluator.evaluate()

    assert result.value == 33
    assert result.rejection_reason is not None
    assert "cached" in result.rejection_reason.lower()


async def test_evaluate_api_failure_no_cache_returns_default():
    """When API fails and no cache exists, return neutral default."""
    evaluator = FearGreedIndicatorEvaluator()

    with patch("aiohttp.ClientSession", side_effect=Exception("Network error")):
        result = await evaluator.evaluate()

    assert result.value == 50
    assert result.classification == "Neutral"
    assert result.rejection_reason is not None
    assert "unavailable" in result.rejection_reason.lower()


async def test_evaluate_api_returns_non_200():
    """Non-200 API response falls back to cached or default."""
    evaluator = FearGreedIndicatorEvaluator()

    mock_resp = MagicMock()
    mock_resp.status = 500

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.get = MagicMock(return_value=mock_ctx)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await evaluator.evaluate()

    assert result.value == 50  # Default neutral
    assert result.rejection_reason is not None


async def test_evaluate_empty_api_response():
    """Empty data array from API falls back to default."""
    evaluator = FearGreedIndicatorEvaluator()

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"data": []})

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.get = MagicMock(return_value=mock_ctx)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await evaluator.evaluate()

    assert result.value == 50
    assert result.rejection_reason is not None


# =============================================================================
# needs_aggregate_indicators integration test
# =============================================================================


def test_needs_aggregate_indicators_detects_fear_greed():
    """needs_aggregate_indicators returns fear_greed=True when a condition uses it."""
    from app.strategies.indicator_based_helpers import needs_aggregate_indicators

    base_conditions = [{"type": "fear_greed", "operator": "<=", "threshold": 25}]
    needs = needs_aggregate_indicators(base_conditions, [], [])
    assert needs["fear_greed"] is True


def test_needs_aggregate_indicators_no_fear_greed():
    """needs_aggregate_indicators returns fear_greed=False when no condition uses it."""
    from app.strategies.indicator_based_helpers import needs_aggregate_indicators

    base_conditions = [{"type": "rsi", "operator": "<", "threshold": 30}]
    needs = needs_aggregate_indicators(base_conditions, [], [])
    assert needs["fear_greed"] is False
