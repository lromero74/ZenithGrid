#!/usr/bin/env python3
"""
Test script for AI Spot Opinion Indicator

Tests the new unified AI indicator without requiring a full bot setup.
"""

import sys
import os
import asyncio
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import directly to avoid circular import issues in test
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app', 'indicators'))
from ai_spot_opinion import AISpotOpinionEvaluator, AISpotOpinionParams


def generate_sample_candles(num_candles=100, trend="neutral"):
    """Generate sample candle data for testing."""
    candles = []
    base_price = 50000.0
    base_volume = 1000.0

    for i in range(num_candles):
        # Generate trending data
        if trend == "bullish":
            price = base_price + (i * 100) + (i % 5 * 50)  # Uptrend
            volume = base_volume * (1.0 + i * 0.01)  # Increasing volume
        elif trend == "bearish":
            price = base_price - (i * 100) + (i % 5 * 50)  # Downtrend
            volume = base_volume * (1.0 + i * 0.01)
        else:  # neutral
            price = base_price + (i % 10 - 5) * 100  # Sideways
            volume = base_volume

        candle = {
            "time": int((datetime.utcnow() - timedelta(minutes=num_candles-i)).timestamp()),
            "open": price,
            "high": price * 1.01,
            "low": price * 0.99,
            "close": price,
            "volume": volume
        }
        candles.append(candle)

    return candles


def test_pre_filter():
    """Test the buy pre-filter logic."""
    print("\n" + "="*60)
    print("TEST 1: Pre-filter Logic")
    print("="*60)

    evaluator = AISpotOpinionEvaluator()

    # Test Case 1: Overbought (should fail)
    print("\nTest Case 1: Overbought scenario")
    candles = generate_sample_candles(100, trend="bullish")

    metrics = evaluator._calculate_metrics(candles)
    print(f"  RSI: {metrics.get('rsi', 'N/A'):.1f}")
    print(f"  Volume Ratio: {metrics.get('volume_ratio', 'N/A'):.2f}x")
    print(f"  24h Change: {metrics.get('price_change_24h', 'N/A'):.2f}%")

    params = AISpotOpinionParams(enable_buy_prefilter=True)
    passed, reason = evaluator._check_buy_prefilter(metrics, params)
    print(f"  ✓ Prefilter: {'PASS' if passed else 'FAIL'} - {reason}")

    # Test Case 2: Low volume (should fail)
    print("\nTest Case 2: Low volume scenario")
    candles = generate_sample_candles(100, trend="neutral")
    # Manually set last candle volume low
    candles[-1]["volume"] = 100.0  # Much lower than average

    metrics = evaluator._calculate_metrics(candles)
    print(f"  RSI: {metrics.get('rsi', 'N/A'):.1f}")
    print(f"  Volume Ratio: {metrics.get('volume_ratio', 'N/A'):.2f}x")
    print(f"  24h Change: {metrics.get('price_change_24h', 'N/A'):.2f}%")

    passed, reason = evaluator._check_buy_prefilter(metrics, params)
    print(f"  ✓ Prefilter: {'PASS' if passed else 'FAIL'} - {reason}")

    # Test Case 3: Good conditions (should pass)
    print("\nTest Case 3: Good buy conditions")
    candles = generate_sample_candles(100, trend="neutral")
    # Set good metrics
    candles[-1]["volume"] = 1500.0  # Above average

    metrics = evaluator._calculate_metrics(candles)
    print(f"  RSI: {metrics.get('rsi', 'N/A'):.1f}")
    print(f"  Volume Ratio: {metrics.get('volume_ratio', 'N/A'):.2f}x")
    print(f"  24h Change: {metrics.get('price_change_24h', 'N/A'):.2f}%")

    passed, reason = evaluator._check_buy_prefilter(metrics, params)
    print(f"  ✓ Prefilter: {'PASS' if passed else 'FAIL'} - {reason}")


def test_time_gating():
    """Test the time-gating mechanism."""
    print("\n" + "="*60)
    print("TEST 2: Time-Gating Mechanism")
    print("="*60)

    evaluator = AISpotOpinionEvaluator()

    # Test 15m timeframe
    print("\nTest Case 1: 15-minute timeframe")
    product_id = "ETH-BTC"
    timeframe = "15m"

    # First check - should return True
    should_check = evaluator._should_check_now(product_id, timeframe)
    print(f"  First check: {should_check} (expected: True)")

    # Update last check
    evaluator._update_last_check(product_id, timeframe)

    # Immediate second check - should return False
    should_check = evaluator._should_check_now(product_id, timeframe)
    print(f"  Immediate check: {should_check} (expected: False)")

    # Manually set last check to 16 minutes ago
    evaluator._last_check_cache[f"{product_id}:{timeframe}"] = datetime.utcnow() - timedelta(minutes=16)

    # Check again - should return True
    should_check = evaluator._should_check_now(product_id, timeframe)
    print(f"  After 16 minutes: {should_check} (expected: True)")

    # Test different timeframes
    print("\nTest Case 2: Different timeframes")
    for tf in ["5m", "15m", "1h", "4h"]:
        seconds = evaluator._timeframe_to_seconds(tf)
        minutes = seconds / 60
        print(f"  {tf} = {seconds}s ({minutes:.0f} minutes)")


async def test_llm_integration():
    """Test LLM integration if API keys are available."""
    print("\n" + "="*60)
    print("TEST 3: LLM Integration")
    print("="*60)

    from app.config import settings

    # Check which API keys are available
    available_models = []
    if settings.anthropic_api_key:
        available_models.append("claude")
    if settings.openai_api_key:
        available_models.append("gpt")
    if settings.gemini_api_key:
        available_models.append("gemini")

    if not available_models:
        print("  ⚠️  No API keys configured - skipping LLM test")
        print("     Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY to test")
        return

    print(f"  Available models: {', '.join(available_models)}")

    # Test with first available model
    model = available_models[0]
    print(f"\n  Testing with {model}...")

    evaluator = AISpotOpinionEvaluator()
    candles = generate_sample_candles(100, trend="bullish")

    params = AISpotOpinionParams(
        ai_model=model,
        ai_timeframe="15m",
        ai_min_confidence=60,
        enable_buy_prefilter=False  # Disable to force LLM call
    )

    try:
        result = await evaluator.evaluate(
            candles=candles,
            current_price=candles[-1]["close"],
            product_id="ETH-BTC",
            params=params,
            is_sell_check=False
        )

        print(f"  ✓ Signal: {result['signal']}")
        print(f"  ✓ Confidence: {result['confidence']}%")
        print(f"  ✓ Reasoning: {result['reasoning']}")
        print(f"  ✓ Prefilter Passed: {result['prefilter_passed']}")

    except Exception as e:
        print(f"  ✗ Error: {e}")


async def test_full_evaluation():
    """Test full evaluation without LLM (prefilter only)."""
    print("\n" + "="*60)
    print("TEST 4: Full Evaluation (Prefilter Mode)")
    print("="*60)

    evaluator = AISpotOpinionEvaluator()

    # Test bullish scenario
    print("\nTest Case 1: Bullish trend (good volume)")
    candles = generate_sample_candles(100, trend="bullish")
    candles[-1]["volume"] = 1500.0  # Good volume

    params = AISpotOpinionParams(
        ai_model="claude",
        ai_timeframe="15m",
        enable_buy_prefilter=True
    )

    result = await evaluator.evaluate(
        candles=candles,
        current_price=candles[-1]["close"],
        product_id="ETH-BTC",
        params=params,
        is_sell_check=False
    )

    print(f"  Signal: {result['signal']}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  Reasoning: {result['reasoning']}")
    print(f"  Prefilter: {result['prefilter_passed']}")

    # Test bearish scenario
    print("\nTest Case 2: Bearish trend (failing)")
    candles = generate_sample_candles(100, trend="bearish")

    result = await evaluator.evaluate(
        candles=candles,
        current_price=candles[-1]["close"],
        product_id="ADA-BTC",
        params=params,
        is_sell_check=False
    )

    print(f"  Signal: {result['signal']}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  Reasoning: {result['reasoning']}")
    print(f"  Prefilter: {result['prefilter_passed']}")


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("AI SPOT OPINION INDICATOR - TEST SUITE")
    print("="*60)

    # Run synchronous tests
    test_pre_filter()
    test_time_gating()

    # Run async tests
    await test_full_evaluation()
    await test_llm_integration()

    print("\n" + "="*60)
    print("ALL TESTS COMPLETE")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
