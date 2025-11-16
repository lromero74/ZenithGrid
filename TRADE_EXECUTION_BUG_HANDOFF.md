# Trade Execution Bug - Investigation Handoff

**Date**: 2025-11-15
**Status**: 🔴 CRITICAL BUG - Trades not executing
**Bot**: AI Autonomous Trading (Gemini/Claude)

---

## Problem Summary

AI bots are creating positions in the database but NOT executing actual buy trades. This leaves empty positions (total_btc_spent = 0) that block future trades.

### Symptoms
- ✅ Monitor runs every 60 seconds
- ✅ AI analyzes markets and decides "buy"
- ✅ Position gets created in database
- ❌ **execute_buy() never runs** - no trade happens
- ❌ Position sits empty (0 BTC spent, 0 ETH acquired)
- ❌ Bot sees existing position and won't create new ones

### Evidence
```sql
-- Example stuck position
SELECT id, bot_id, product_id, total_btc_spent, total_eth_acquired
FROM positions WHERE id = 1;
-- Result: 1|1|AAVE-BTC|0.0|0.0

-- AI said "buy" but no trade executed
SELECT decision, product_id FROM ai_bot_logs ORDER BY id DESC LIMIT 1;
-- Result: buy|AAVE-BTC
```

---

## Code Flow Analysis

### Expected Flow (What SHOULD Happen)
```python
# trading_engine_v2.py - process_signal()
1. AI analyzes → returns signal_data with "buy"
2. should_buy, btc_amount, reason = strategy.should_buy()  # Returns (True, 0.00057, "AI BUY")
3. if should_buy:
4.     position = create_position()  # ✅ This happens
5.     trade = execute_buy()         # ❌ This never happens
6.     Record signal
7.     Return {"action": "buy"}
```

### Actual Flow (What IS Happening)
```python
1. AI analyzes → "buy" signal ✅
2. should_buy check → ??? (unclear if True)
3. Position created → ✅ (we see it in DB)
4. execute_buy() → ❌ NEVER CALLED
5. Position sits empty forever
```

---

## Bugs Fixed (But Still Not Working)

### Fix #1: Database Transaction Conflicts ✅
**Commit**: e2f518f
**Issue**: Parallel processing caused concurrent DB operations
**Fix**: Changed from parallel to sequential batch processing
**Status**: Fixed, but trades still don't execute

### Fix #2: Nested Transaction Commits ✅
**Commit**: e2f518f
**Issue**: save_ai_log() was committing during active transactions
**Fix**: Removed commit from save_ai_log(), added final commit
**Status**: Fixed, but trades still don't execute

### Fix #3: Lazy Loading During Transactions ✅
**Commit**: e2f518f
**Issue**: position.trades access triggered lazy load
**Fix**: Check position.total_btc_spent instead
**Status**: Fixed, but trades still don't execute

---

## Investigation Steps Taken

### 1. Verified Monitor is Running
```bash
# Logs show monitor queries every ~60 seconds
2025-11-15 20:33:31 - SELECT bots WHERE is_active = 1
2025-11-15 20:33:31 - Fetching AAVE-BTC ticker
```

### 2. Verified AI is Analyzing
```sql
SELECT decision, confidence, product_id, timestamp
FROM ai_bot_logs
ORDER BY id DESC LIMIT 1;
-- buy|75.0|AAVE-BTC|2025-11-16 01:33:40
```

### 3. Checked Bot Status
```bash
curl http://localhost:8000/api/bots/1 | jq '.is_active'
# true
```

### 4. Added Debug Logging
**Commit**: cf5999a
Added extensive logging:
- "🤖 Bot active: {is_active}, Position exists: {exists}"
- "💰 BUY DECISION: will buy {amount} BTC"
- "📝 Creating new position"
- "🔨 Executing buy order"
- "✅ Trade executed"

**Next**: Restart and watch logs to see which log appears and which doesn't

---

## Hypotheses (What Might Be Wrong)

### Hypothesis #1: should_buy Never Returns True
**Theory**: The strategy.should_buy() method is returning False even when AI says "buy"
**Test**: Check if "💰 BUY DECISION" log appears
**Files**:
- `backend/app/strategies/ai_autonomous.py` - should_buy() method
- `backend/app/trading_engine_v2.py:333` - where should_buy is called

### Hypothesis #2: Exception During execute_buy
**Theory**: execute_buy() is called but throws exception that's caught
**Test**: Look for any error logs
**Files**:
- `backend/app/trading_engine_v2.py:140` - execute_buy() method
- Look for "Error executing buy order" (line 171)

### Hypothesis #3: Database Rollback
**Theory**: Transaction commits but then rolls back
**Test**: Check if position appears momentarily then disappears
**Status**: Unlikely - position persists

### Hypothesis #4: Monitor Not Processing Bots
**Theory**: Monitor queries bots but doesn't call process_bot()
**Test**: Check for "Processing bot: AI Bot" logs
**Files**:
- `backend/app/multi_bot_monitor.py:167` - should log this
- **OBSERVATION**: These logs are missing!

---

## Critical Missing Logs

The monitor should log these but doesn't:
```python
# multi_bot_monitor.py
logger.info(f"Processing bot: {bot.name} with {len(trading_pairs)} pair(s)")
logger.info(f"  Processing batch {batch_num} ({len(batch)} pairs): {batch}")
logger.info(f"  Evaluating pair: {product_id}")
logger.info(f"  Current {product_id} price: {current_price}")
logger.info(f"  Result: {result['action']} - {result['reason']}")
```

**NONE of these appear in logs!**

This suggests: **Monitor is running but NOT calling process_bot() or process_bot_pair()**

---

## Next Debugging Steps

### Step 1: Verify Monitor Loop
```bash
# Restart with debug logging
./bot.sh restart

# Watch for monitor logs
tail -f .pids/backend.log | grep -E "Monitoring|Processing bot|batch"
```

### Step 2: Check Monitor Startup
```python
# In main.py - is monitor started?
price_monitor = MultiBotMonitor(coinbase_client, interval_seconds=60)
# But is monitor.start() called? 🤔
```

### Step 3: Test Manual Signal Processing
```python
# Direct test in Python console
from app.trading_engine_v2 import StrategyTradingEngine
# ... create engine and call process_signal() directly
# Does it work when called manually?
```

---

## Files to Check

### Primary Suspects
1. **`backend/app/multi_bot_monitor.py`**
   - Line 341: monitor_loop() - is this running?
   - Line 356: for bot in bots - is this iterating?
   - Line 360: await self.process_bot() - is this called?

2. **`backend/app/main.py`**
   - Line 53: price_monitor created
   - **MISSING**: price_monitor.start() call? 🔍

3. **`backend/app/trading_engine_v2.py`**
   - Line 348: if should_buy - does this evaluate True?
   - Line 362: execute_buy() - is this reached?

### Supporting Files
- `backend/app/strategies/ai_autonomous.py` - AI buy logic
- `backend/app/coinbase_client.py` - Actual order execution
- `backend/app/models.py` - Position/Trade models

---

## Quick Commands Reference

### Check Database State
```bash
# Count positions and trades
sqlite3 backend/trading.db "SELECT COUNT(*) FROM positions; SELECT COUNT(*) FROM trades;"

# Check stuck positions
sqlite3 backend/trading.db "SELECT id, product_id, total_btc_spent FROM positions WHERE status='open';"

# Check recent AI logs
sqlite3 backend/trading.db "SELECT decision, product_id, timestamp FROM ai_bot_logs ORDER BY id DESC LIMIT 5;"

# Clean stuck positions
sqlite3 backend/trading.db "DELETE FROM positions WHERE total_btc_spent = 0; DELETE FROM ai_bot_logs;"
```

### Monitor Logs
```bash
# Watch for trading activity
tail -f .pids/backend.log | grep -E "Processing bot|BUY DECISION|execute_buy|Trade executed"

# Watch for errors
tail -f .pids/backend.log | grep -E "Error|Exception|Traceback"

# Check monitor activity
tail -f .pids/backend.log | grep -E "Monitoring|monitor_loop"
```

### API Checks
```bash
# Get bot status
curl -s http://localhost:8000/api/bots/1 | jq '{name, is_active}'

# Get positions
curl -s http://localhost:8000/api/positions?status=open | jq length

# Get AI logs
curl -s http://localhost:8000/api/bots/1/logs?limit=5 | jq '.[].decision'
```

---

## Git Commits

- `57b778f` - Fix product_id bug and implement parallel batch processing
- `21f3149` - Add profit calculation method option
- `861658b` - Add product_id to AI bot logs API response
- `e2f518f` - Fix critical database transaction conflicts
- `cf5999a` - Add debug logging to trace trade execution failure (CURRENT)

---

## Key Questions to Answer

1. **Is monitor.start() being called?**
   - Check main.py startup code
   - Look for "Multi-bot monitor task started" log

2. **Is monitor_loop() actually running?**
   - Should see "Monitoring X active bot(s)" every 60 seconds
   - Currently: logs show DB queries but not monitor logs

3. **Is process_bot() being called?**
   - Should see "Processing bot: AI Bot" logs
   - Currently: MISSING

4. **Does should_buy ever return True?**
   - Will see "💰 BUY DECISION" log after restart
   - If missing: bug is in should_buy() logic

5. **Does execute_buy() ever get called?**
   - Will see "🔨 Executing buy order" log
   - If missing: bug is between should_buy and execute_buy

---

## Recommended Next Actions

### Immediate (Next Session)
1. Restart backend with new debug logging
2. Turn on Gemini bot
3. Watch logs for 2 minutes
4. Identify which debug log is the LAST one to appear
5. That pinpoints the exact failure location

### If Monitor Not Starting
- Check main.py for monitor.start() call
- Add startup event handler to start monitor
- Verify asyncio task creation

### If should_buy Returns False
- Check ai_autonomous.py should_buy() logic
- Verify signal_data format from AI
- Check max_concurrent_deals logic
- Verify btc_balance is not 0

### If execute_buy Fails
- Check Coinbase API credentials
- Check BTC balance (might be insufficient)
- Check order size minimums
- Add try/except logging in execute_buy

---

## Environment Info

- **Python**: 3.13
- **FastAPI**: Running on port 8000
- **Database**: SQLite (backend/trading.db)
- **Bot Interval**: 60 seconds
- **Current BTC Balance**: 0.0017112674 BTC (~$163 USD)

---

## Contact Points

When resuming:
1. Read this document first
2. Check if debug logs were added (commit cf5999a)
3. Restart backend: `./bot.sh restart`
4. Watch logs: `tail -f .pids/backend.log | grep -E "🤖|💰|🔨|✅"`
5. Report which emoji logs appear (this tells us where it fails)

---

**End of Handoff Document**
