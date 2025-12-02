# Handoff Notes - December 2, 2025

## Issue 1: Force-Close 500 Error ("unexpected keyword argument 'coinbase'")

### Symptom
- User tried to force-close deal 46 at market price via the UI
- Got a 500 Internal Server Error
- Logs showed: `POST /api/positions/46/force-close HTTP/1.1" 500 Internal Server Error`

### Root Cause
In `backend/app/position_routers/position_actions_router.py`, line 84-86:

```python
engine = StrategyTradingEngine(
    db=db, coinbase=coinbase, bot=bot, strategy=strategy, product_id=position.product_id
)
```

The `StrategyTradingEngine.__init__()` expects parameter named `exchange=`, not `coinbase=`.

### Fix Applied ✅
Changed line 84-86 in `position_actions_router.py`:
```python
engine = StrategyTradingEngine(
    db=db, exchange=coinbase, bot=bot, strategy=strategy, product_id=position.product_id
)
```

**Commit**: `f56b5a7 Fix force-close 500 error and add BB% debug logging`

---

## Issue 2: BB% Auto-Sell Not Triggering for THREE_MINUTE Timeframe

### Symptom
- Deal 46 (AAVE-BTC) had custom sell condition: `BB% crossing_below 90 on THREE_MINUTE`
- Logs showed repeatedly: `[DEBUG] Condition bb_percent on THREE_MINUTE: indicator value is None`
- The BB% auto-sell never triggered despite the condition being set

### Root Cause (FOUND)
The bug was in `backend/app/multi_bot_monitor.py` lines 868-882.

**Data Flow:**
1. In batch mode, `pair_data` correctly contains `candles_by_timeframe` with THREE_MINUTE (line 530)
2. Line 807: `candles_by_timeframe = pair_data.get("candles_by_timeframe", ...)` correctly retrieves it
3. **THE BUG**: Line 882 unconditionally overwrote `candles_by_timeframe = {timeframe: candles}` with only a single timeframe, losing THREE_MINUTE

The else branch (for non-conditional_dca bots like ai_autonomous) was overwriting the pre-fetched multi-timeframe candle data with only the bot's primary timeframe.

### Fix Applied ✅
Modified lines 868-888 in `multi_bot_monitor.py`:

```python
# Get historical candles for signal analysis (if not already provided via pair_data)
if not candles:
    candles = await self.get_candles_cached(
        product_id=product_id, granularity=timeframe, lookback_candles=100
    )

if not candles:
    logger.warning(f"    No candles available for {product_id}")
    return {"error": "No candles available"}

# Only set default candles_by_timeframe if not already populated from pair_data
# This preserves THREE_MINUTE and other timeframes from batch mode
if not candles_by_timeframe or len(candles_by_timeframe) == 0:
    candles_by_timeframe = {timeframe: candles}
else:
    logger.info(f"  📊 Using pre-fetched candles_by_timeframe with {len(candles_by_timeframe)} timeframes: {list(candles_by_timeframe.keys())}")
```

**Commit**: `9fd8d87 Fix BB% THREE_MINUTE indicator not populating for AI bots`

---

## Other Issues Observed in Logs

### 401 Unauthorized Errors
```
Error calculating aggregate USD value using accounts endpoint: Client error '401 Unauthorized' for url 'https://api.coinbase.com/api/v3/brokerage/accounts?limit=250'
```
This suggests intermittent API key authentication issues with Coinbase. May be causing cascading failures.

### Error Calculating Budget
```
Error calculating budget for bot 4: No aggregate USD value available
```
This is a downstream effect of the 401 error - if aggregate USD value can't be calculated, budget calculations fail.

---

## Summary - All Issues Fixed ✅

1. **Force-Close Error**: Fixed - changed `coinbase=` to `exchange=` in position_actions_router.py
2. **BB% THREE_MINUTE Issue**: Fixed - preserved `candles_by_timeframe` from batch mode instead of overwriting it
3. **Monitor**: Continue watching for 401 Unauthorized errors - may indicate API key issues

---

## Session Context

- Position 46: AAVE-BTC, bot_id=3, opened 2025-11-27, closed 2025-12-02 (via limit sell at 20:17:37)
- Bot 3: ai_autonomous strategy with custom sell condition `bb_percent crossing_below 90 on THREE_MINUTE`
- User had to manually sell via limit order after force-close failed
- Both issues now fixed and deployed to testbot
