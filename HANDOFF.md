# Major Refactoring: Multi-Quote Currency Support (BTC + USD)
**Date:** November 16, 2025
**Status:** IN PROGRESS 🚧

## Problem
Trading engine was hardcoded to only support BTC as quote currency. USD trading pairs were being treated as BTC pairs, causing:
- USD positions showing "0.00 USD" invested (storing tiny BTC amounts instead of USD)
- System trying to spend BTC to buy USD pairs (should spend USD)
- All variable names/columns assume BTC (btc_amount, total_btc_spent, etc.)

## Solution: Quote-Currency Agnostic Architecture
Refactoring entire system to support both BTC and USD (and future) quote currencies.

### Progress

**✅ Step 1: Database Migration**
- Created migration script: `backend/migrations/rename_btc_to_quote_currency.py`
- Renamed columns in `positions` table:
  - `initial_btc_balance` → `initial_quote_balance`
  - `max_btc_allowed` → `max_quote_allowed`
  - `total_btc_spent` → `total_quote_spent`
  - `total_eth_acquired` → `total_base_acquired`
  - `total_btc_received` → `total_quote_received`
  - `profit_btc` → `profit_quote`
- Renamed columns in `trades` table:
  - `btc_amount` → `quote_amount`
  - `eth_amount` → `base_amount`
- Migration executed successfully, data preserved

**✅ Step 2: Model Updates**
- Updated `Position` model in `backend/app/models.py`
  - Added `get_quote_currency()` method to extract quote from product_id
  - Updated `update_averages()` to use new column names
- Updated `Trade` model with new column names
- All SQLAlchemy models now use quote/base terminology

**🚧 Step 3: Trading Engine Refactoring** (IN PROGRESS)
- Need to update `backend/app/trading_engine_v2.py`:
  - Detect quote currency from product_id
  - Update `create_position()` to accept quote_balance and quote_amount
  - Update `execute_buy()` to be currency-agnostic
  - Update `execute_sell()` to be currency-agnostic
  - Replace all btc_* variable names with quote_*
  - Replace all eth_* variable names with base_*

**⏳ Step 4: Coinbase Client Updates** (PENDING)
- Need to update `backend/app/coinbase_client.py`:
  - Add `get_balance(currency)` method (generic)
  - Add `buy_with_quote()` method (detects BTC vs USD)
  - Keep backwards compatible methods (`get_btc_balance()`, `buy_eth_with_btc()`)

**⏳ Step 5: Bot Monitor Updates** (PENDING)
- Need to update `backend/app/multi_bot_monitor.py`:
  - Detect quote currency for each product_id
  - Fetch correct balance (USD for USD pairs, BTC for BTC pairs)
  - Pass correct balance to trading engine

**⏳ Step 6: Frontend Updates** (PENDING)
- Already partially done (formatQuoteAmount helper exists)
- Need to verify all displays use quote currency correctly

**⏳ Step 7: Testing** (PENDING)
- Test BTC pairs (ETH-BTC, SOL-BTC) still work
- Test USD pairs (AAVE-USD, ADA-USD) work correctly
- Verify invested amounts show correct currency
- Verify PnL calculations correct for both types

### Files Modified
1. ✅ `backend/migrations/rename_btc_to_quote_currency.py` - Created
2. ✅ `backend/app/models.py` - Position and Trade models updated
3. 🚧 `backend/app/trading_engine_v2.py` - IN PROGRESS
4. ⏳ `backend/app/coinbase_client.py` - PENDING
5. ⏳ `backend/app/multi_bot_monitor.py` - PENDING
6. ⏳ `frontend/src/pages/Positions.tsx` - Verify formatQuoteAmount usage

### Rollback Plan
If needed, run: `python3 backend/migrations/rename_btc_to_quote_currency.py rollback`

---

# AI Bot Price Data Issue - Investigation & Resolution
**Date:** November 16, 2025
**Status:** RESOLVED ✅

## Problem Report
AI Bot Reasoning Logs were showing `current_price: 0.0` for all trading pairs, causing AI to incorrectly conclude assets had "collapsed" or been "delisted".

## Investigation Timeline

### Initial Hypothesis (INCORRECT)
- Suspected Coinbase ticker API was returning malformed responses
- Tried fixing by changing from `get_ticker()` to `get_current_price()`
- Added validation to skip pairs with invalid prices
- **This fix didn't work** - still saw 0.0 prices

### Key User Insight 💡
User asked: "Why don't you use the price from the chart? That's my question. Why do a fetch that doesn't work when we can use the price we can get from the chart."

**This was the breakthrough question** that led to the real solution.

### Root Cause Discovery

**The Charts page was working because it uses candle data**, not the ticker endpoint!

Testing revealed:
1. **Old Coinbase Exchange API** (api.exchange.coinbase.com):
   - PUBLIC endpoint, no auth required
   - Returns: `"price": "0.00000169"` ✅
   - **Works perfectly**

2. **New Coinbase Advanced Trade API v3** (api.coinbase.com):
   - AUTHENTICATED endpoint (our backend uses this)
   - Ticker endpoint: Returns empty or missing "price" field ❌
   - Candles endpoint: **Works perfectly!** Returns valid prices ✅

**The real issue:** Our code was calling `ticker.get('price', 0)` which defaulted to 0 when the ticker response didn't have a "price" field.

### The Actual Fix

**Changed from ticker-based pricing to candle-based pricing:**

```python
# OLD CODE (broken):
ticker = await self.coinbase.get_ticker(product_id)
current_price = float(ticker.get('price', 0))  # Defaults to 0!

# NEW CODE (working):
candles = await self.get_candles_cached(product_id, "FIVE_MINUTE", 100)
if not candles or len(candles) == 0:
    logger.warning(f"No candles available for {product_id}, skipping")
    continue
current_price = float(candles[-1].get("close", 0))  # Get from most recent candle
```

**Benefits:**
- More reliable (candles API works consistently)
- More efficient (we were fetching candles anyway for AI analysis)
- Matches what the Charts page uses (proven to work)

### Additional Issue: Old Backend Still Running

After implementing the fix, logs still showed 0.0 prices because:
- PID file said backend was 67810
- **Actual running process was PID 49358** (started at 1:34 AM!)
- Old backend from hours ago was still serving requests
- Our code changes weren't being used

**Solution:** Killed old process (49358) and restarted properly.

### Files Modified

1. `backend/app/multi_bot_monitor.py` (lines 277-295, 430-445):
   - Batch processing path: Get price from candles instead of ticker
   - Non-batch path: Get price from candles with fallback to ticker

2. `backend/app/coinbase_client.py` (lines 155-162):
   - Added debug logging to track ticker issues

### Commits
- `dacf777` - Use candle data for current price instead of unreliable ticker API
- `69a5029` - Fix AI bot logging to only process pairs with valid market data
- `67cfab9` - Fix AI Bot price data collection for batch analysis (first attempt, didn't work)

## Lessons Learned

1. **Listen to the user's perspective** - The question "why not use chart prices?" immediately revealed we had a working data source
2. **Check what's actually running** - The old backend process was still running hours later
3. **Don't assume API behavior** - The ticker endpoint response format was different than expected
4. **Use working patterns** - If the Charts page works, use the same data source

## Follow-Up Issues Discovered

### Duplicate AI Logs
After fixing prices, noticed duplicate entries for same pair/time:
- Bot 2 (Claude): Creating 2 logs per pair within 5 seconds
- Root cause: `_get_claude_batch_analysis()` not implemented, falls back to individual calls
- **Status:** Investigated, needs implementation of proper Claude batch analysis

### Grok Bot 404 Errors
- Bot 3 (Grok): Getting 404 "model grok-beta was not found"
- **Root Cause:** grok-beta was deprecated on 2025-09-15
- **Fix:** Updated model to "grok-3" in ai_autonomous.py:927
- **Status:** ✅ FIXED

### Claude Bot Duplicate Logs
- Bot 2 (Claude): Creating 2 logs per pair within 5 seconds
- **Root Cause:** `_get_claude_batch_analysis()` not implemented (lines 764-886)
- **Fix:** Implemented proper Claude batch analysis matching Gemini/Grok pattern
- **Benefits:** Single API call instead of 27 individual calls, eliminates duplicates, reduces costs
- **Status:** ✅ FIXED

## Current Status

✅ **FIXED:** AI Bot Reasoning Logs now show correct prices
✅ **VERIFIED:** Prices coming from candle data (e.g., YFI-BTC: 0.04820000 BTC)
✅ **FIXED:** Duplicate log entries (Claude batch now implemented)
✅ **FIXED:** Grok bot model name (grok-beta → grok-3)

---
**Total Debugging Time:** ~2 hours
**Key Breakthrough:** User's question about chart prices
**Final Solution:** 2-line code change (use candles instead of ticker)

