# Candle Fetch Optimization Plan

**Date**: 2026-01-26
**Status**: Research & Planning Phase

## User's Questions Addressed

### Q1: Are candles fixed intervals or trailing?
**Answer**: Candles are **FIXED intervals** aligned to clock time, NOT trailing windows.

**How it works**:
- A 15-minute candle closes at **:00, :15, :30, :45** of every hour
- A 5-minute candle closes at **:00, :05, :10, :15, :20, :25, :30, :35, :40, :45, :50, :55**
- A 1-hour candle closes at **:00** of every hour
- Daily candles close at **00:00 UTC**

This is the **universal standard** across all major exchanges (Coinbase, Binance, Kraken, etc.) and charting platforms (TradingView).

**Source**: [TradingView Time Intervals Documentation](https://www.tradingview.com/support/solutions/43000747934-time-intervals-a-quick-introduction-and-tips/)

### Q2: User's scenario - 15min passes at 04:15, but 3min doesn't pass until 04:18. Is this a "go" or a "miss"?

**Answer**: This is a **"GO"** - industry standard behavior.

**Why**:
1. At 04:15, the 15-min candle (04:00-04:15) **closes** and becomes historical data
2. At 04:18, the 3-min candle (04:15-04:18) **closes**
3. When you check at 04:18:
   - 15-min condition: Uses the **closed** 04:00-04:15 candle (still valid, won't change)
   - 3-min condition: Uses the **closed** 04:15-04:18 candle (just became available)
4. Both conditions are met → **Trade executes**

The 15-min data is **cached/remembered** until the next 15-min candle closes at 04:30.

**Interesting Finding**: Research shows a ["turn-of-the-candle effect"](https://pmc.ncbi.nlm.nih.gov/articles/PMC10015199/) where positive returns in Bitcoin concentrate at candle close times (:00, :15, :30, :45 for 15-min candles) due to high-frequency bots executing at these exact moments.

### Q3: Should we check only at the longest timeframe interval?

**Answer**: **NO** - We should check at the **SHORTEST** timeframe interval, but only **FETCH** candles when they close.

**Example with 15-min SMA + 3-min RSI**:
- **Check frequency**: Every 3 minutes (when 3-min candles close)
- **Fetch 15-min candles**: Only at :00, :15, :30, :45 (when they close)
- **Fetch 3-min candles**: Only at :00, :03, :06, :09, ... (when they close)
- **Between fetches**: Use cached candle data

**Why not longest interval?**
- The 3-min RSI is your **trigger** - it's the fast-moving signal
- The 15-min SMA is your **filter** - it changes slowly
- You need to **act** when the fast signal changes, using the cached slow signal

## Current Implementation Issues

### Problem 1: Over-fetching
Currently we fetch candles on **every bot check** (~10 seconds for some bots):
```python
# From multi_bot_monitor.py line 664-674
candles = await self.get_candles_cached(product_id, "FIVE_MINUTE", 100)
one_min_candles = await self.get_candles_cached(product_id, "ONE_MINUTE", 300)
three_min_candles = await self.get_candles_cached(product_id, "THREE_MINUTE", 100)
one_hour_candles = await self.get_candles_cached(product_id, "ONE_HOUR", 100)
fifteen_min_candles = await self.get_candles_cached(product_id, "FIFTEEN_MINUTE", 100)
```

Even though we have `CANDLE_CACHE_TTL = 60`, we're still fetching multiple timeframes **per bot** **per check**.

### Problem 2: Cache expiration doesn't align with candle closes
- Current cache: 60 seconds
- 1-min candles close every 60 seconds ✅
- 3-min candles close every 180 seconds ❌ (we re-fetch 2x unnecessarily)
- 15-min candles close every 900 seconds ❌ (we re-fetch 14x unnecessarily)

### Problem 3: No check frequency optimization
Bots with only 1-hour indicators still check every 10-15 seconds, wasting CPU and API calls.

## Industry Best Practices (2025)

Based on research of production trading bots:

**1. Smart Caching** ([Source](https://www.weex.com/news/detail/overcoming-api-rate-limits-in-crypto-trading-essential-strategies-for-developers-and-traders-204708)):
- Cache 15-min candles for 15 minutes
- Cache 1-hour candles for 1 hour
- Only fetch when candles close

**2. API Rate Limit Strategies** ([Source](https://www.quantvps.com/blog/automated-trading-polymarket)):
- Implement exponential backoff on 429 errors
- Batch requests efficiently
- Prioritize critical operations
- Public APIs: ~100 requests/minute typical limit
- Trading endpoints: ~60 orders/minute typical limit

**3. Multi-Timeframe Analysis** ([Source](https://wundertrading.com/journal/en/reviews/article/best-ai-crypto-trading-bots)):
- Analyze multiple timeframes simultaneously
- Use weighted averages across timeframes for predictions
- Cache historical data, only fetch newest candle

## Proposed Optimization Strategy

### Phase 1: Intelligent Cache Expiration

**Concept**: Cache TTL = Candle interval duration

```python
CANDLE_CACHE_TTL = {
    "ONE_MINUTE": 60,       # 1 minute
    "THREE_MINUTE": 180,    # 3 minutes
    "FIVE_MINUTE": 300,     # 5 minutes
    "FIFTEEN_MINUTE": 900,  # 15 minutes
    "THIRTY_MINUTE": 1800,  # 30 minutes
    "ONE_HOUR": 3600,       # 1 hour
    "TWO_HOUR": 7200,       # 2 hours
    "FOUR_HOUR": 14400,     # 4 hours
    "SIX_HOUR": 21600,      # 6 hours
    "ONE_DAY": 86400,       # 24 hours
}
```

**Implementation**:
```python
async def get_candles_cached(self, product_id: str, granularity: str, lookback: int = 100):
    cache_key = f"{product_id}_{granularity}_{lookback}"
    now = datetime.utcnow()

    # Check if cached and still valid
    if cache_key in self._candle_cache:
        cached_data, cached_time = self._candle_cache[cache_key]
        ttl = CANDLE_CACHE_TTL.get(granularity, 60)
        if (now - cached_time).total_seconds() < ttl:
            return cached_data

    # Fetch fresh data
    candles = await self.exchange.get_candles(product_id, granularity, lookback)
    self._candle_cache[cache_key] = (candles, now)
    return candles
```

**Impact**:
- 15-min candles: 15x fewer API calls
- 1-hour candles: 60x fewer API calls
- 1-day candles: 1440x fewer API calls

### Phase 2: Smart Check Scheduling

**Concept**: Only check when the shortest timeframe candle closes

**Per-Bot Check Interval Calculation**:
```python
def calculate_bot_check_interval(bot: Bot) -> int:
    """Calculate minimum check interval based on bot's indicators"""
    timeframes = []

    # Parse all conditions for all phases
    for phase in ['base_order', 'safety_order', 'take_profit']:
        conditions = bot.strategy_config.get(f'{phase}_conditions', [])
        for cond in conditions:
            if 'timeframe' in cond:
                timeframes.append(cond['timeframe'])

    # Get shortest timeframe in seconds
    timeframe_seconds = {
        "ONE_MINUTE": 60,
        "THREE_MINUTE": 180,
        "FIVE_MINUTE": 300,
        "FIFTEEN_MINUTE": 900,
        "ONE_HOUR": 3600,
        # ... etc
    }

    intervals = [timeframe_seconds[tf] for tf in timeframes if tf in timeframe_seconds]
    return min(intervals) if intervals else 300  # Default 5 minutes
```

**Alignment to Candle Close Times**:
```python
def next_check_time(interval_seconds: int) -> datetime:
    """Calculate next check time aligned to candle close"""
    now = datetime.utcnow()

    # Align to interval boundaries
    # Example: 3-min interval should check at :00, :03, :06, :09, etc.
    seconds_since_hour = (now.minute * 60) + now.second
    next_boundary = ((seconds_since_hour // interval_seconds) + 1) * interval_seconds

    # Convert back to time
    minutes_to_add = next_boundary // 60
    seconds_remainder = next_boundary % 60

    next_time = now.replace(second=0, microsecond=0) + timedelta(minutes=minutes_to_add, seconds=seconds_remainder)
    return next_time
```

**Example**:
- Bot has 15-min SMA + 3-min RSI conditions
- Check interval: 180 seconds (3 minutes)
- Check times: :00, :03, :06, :09, :12, :15, :18, :21, ... (aligned to 3-min boundaries)

**Impact**:
- Bot with only 1-hour indicators: Checks every 60 minutes instead of every 10 seconds → 360x reduction
- Bot with 15-min + 3-min indicators: Checks every 3 minutes instead of every 10 seconds → 18x reduction

### Phase 3: Lazy Candle Fetching

**Concept**: Only fetch the timeframes actually needed for this check

**Current behavior**:
```python
# We fetch ALL timeframes regardless of which phase we're checking
candles = await self.get_candles_cached(product_id, "FIVE_MINUTE", 100)
one_min_candles = await self.get_candles_cached(product_id, "ONE_MINUTE", 300)
three_min_candles = await self.get_candles_cached(product_id, "THREE_MINUTE", 100)
one_hour_candles = await self.get_candles_cached(product_id, "ONE_HOUR", 100)
fifteen_min_candles = await self.get_candles_cached(product_id, "FIFTEEN_MINUTE", 100)
```

**Optimized behavior**:
```python
# Determine which phase we're checking
phase = "safety_order"  # or base_order, take_profit

# Get required timeframes for THIS phase
required_timeframes = get_required_timeframes_for_phase(bot, phase)

# Only fetch what we need
candles_by_timeframe = {}
for timeframe in required_timeframes:
    candles_by_timeframe[timeframe] = await self.get_candles_cached(
        product_id, timeframe, 100
    )
```

**Impact**: Fetch only 2-3 timeframes instead of 5-7 → 50-60% fewer API calls

## Implementation Phases

### Phase 1: Low-Hanging Fruit (Immediate - No Bot Behavior Changes)
**Effort**: 2-3 hours
**Impact**: 60-80% API call reduction

1. Update `CANDLE_CACHE_TTL` from fixed 60s to dict with per-timeframe values
2. Modify `get_candles_cached()` to use timeframe-specific TTL
3. Test with existing bots - no behavior changes, just fewer fetches

**Files to modify**:
- `backend/app/constants.py` - Change CANDLE_CACHE_TTL to dict
- `backend/app/multi_bot_monitor.py` - Update get_candles_cached()

### Phase 2: Smart Check Scheduling (Medium - Changes Bot Check Timing)
**Effort**: 4-6 hours
**Impact**: 10-300x reduction in unnecessary checks

1. Add `calculate_bot_check_interval()` function
2. Add `next_check_time()` alignment function
3. Modify bot monitoring loop to respect per-bot intervals
4. Align checks to candle close times

**Files to modify**:
- `backend/app/multi_bot_monitor.py` - Add scheduling logic
- `backend/app/models.py` - Add `next_check_at` field to Bot table?

**Migration needed**: Add `next_check_at` to bots table

### Phase 3: Lazy Fetching (Lower Priority - Optimization)
**Effort**: 2-3 hours
**Impact**: Additional 40-50% reduction on top of Phase 1

1. Add `get_required_timeframes_for_phase()` helper
2. Modify signal processing to fetch only needed timeframes
3. Test across all bot types

**Files to modify**:
- `backend/app/multi_bot_monitor.py` - Conditional fetching

## Estimated Impact

**Current State** (10-second bot check interval, 60s cache):
- Bot with 5 timeframes: ~300 API calls/hour
- 5 bots: ~1,500 API calls/hour

**After Phase 1** (smart caching):
- Same bot: ~50 API calls/hour (83% reduction)
- 5 bots: ~250 API calls/hour

**After Phase 2** (smart scheduling):
- Bot with 3-min shortest: ~20 checks/hour = ~40 API calls/hour
- Bot with 15-min shortest: ~4 checks/hour = ~8 API calls/hour
- Bot with 1-hour shortest: ~1 check/hour = ~2 API calls/hour
- 5 bots (mixed): ~50-100 API calls/hour (93% reduction)

**After Phase 3** (lazy fetching):
- Additional 40% reduction: ~30-60 API calls/hour (96% total reduction)

## Trade Execution Timing

**Will we miss trades?**

**No** - Actually we'll catch trades MORE accurately.

**Why?**
1. Currently checking every 10 seconds means we might check at :03, :13, :23, :33, :43, :53
2. A 15-min candle closes at :15 and :45
3. We'd catch it at :13 (before close, using incomplete candle) or :23 (8 seconds late)
4. **Aligned checking**: We check RIGHT when the candle closes (:00, :03, :06, :09, :12, :15...)
5. **Result**: We execute at :15 or :18 (worst case 3 minutes late for 3-min candle)

**Industry standard**: Most bots check within 1-60 seconds of candle close. Checking every 3 minutes for 3-min candles is **very competitive**.

## API Rate Limit Compliance

**Coinbase Rate Limits**:
- Public endpoints (candles, ticker): ~10 requests/second
- Private endpoints (orders, accounts): ~15 requests/second

**Current usage** (worst case, 5 bots, 10s checks):
- ~1,500 requests/hour = ~25 requests/minute = **0.4 requests/second** ✅

**After optimization**:
- ~60 requests/hour = ~1 request/minute = **0.016 requests/second** ✅✅✅

We're well under limits, but optimization still valuable for:
1. Server resource usage (CPU, memory)
2. Response time (fewer HTTP requests = faster checks)
3. Future scalability (support more bots)

## Risks & Mitigations

### Risk 1: Delayed Trade Execution
**Risk**: 3-min check interval means 3-min worst-case delay
**Mitigation**: This is industry-standard behavior and actually MORE accurate than checking mid-candle
**Severity**: Low

### Risk 2: Cache Desynchronization
**Risk**: Cached candles could become stale if system clock drifts
**Mitigation**: Use exchange timestamps, not local time; add cache validation
**Severity**: Low

### Risk 3: Complex Scheduling Logic
**Risk**: Per-bot scheduling could have edge cases
**Mitigation**: Thorough testing with multiple bot configurations; fallback to fixed interval
**Severity**: Medium

## Recommendations

1. **Start with Phase 1** - Immediate win, zero risk, huge impact
2. **Test Phase 1 for 1 week** - Monitor API usage, trade execution accuracy
3. **Implement Phase 2** if Phase 1 successful - Bigger win, slightly higher complexity
4. **Phase 3 is optional** - Diminishing returns, only if needed

## References

- [TradingView Time Intervals](https://www.tradingview.com/support/solutions/43000747934-time-intervals-a-quick-introduction-and-tips/)
- [Turn-of-the-Candle Effect Research](https://pmc.ncbi.nlm.nih.gov/articles/PMC10015199/)
- [API Rate Limit Optimization Strategies](https://www.weex.com/news/detail/overcoming-api-rate-limits-in-crypto-trading-essential-strategies-for-developers-and-traders-204708)
- [3Commas Bot Strategies](https://help.3commas.io/en/articles/3108986-dca-bot-start-close-conditions-via-indicators)
- [Multi-Timeframe Trading Bot Best Practices](https://wundertrading.com/journal/en/reviews/article/best-ai-crypto-trading-bots)

---

**Next Steps**: Review this plan, discuss approach, and proceed with Phase 1 implementation if approved.
