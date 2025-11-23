# STEP 5: multi_bot_monitor.py Refactoring Plan

**Original:** 892 lines
**Target:** <500 lines main file

## Strategy:
Extract the two largest methods (process_bot_batch: 273 lines, process_bot_pair: 202 lines) into a separate module.

**Result:**
- bot_processor.py (~475 lines) - process_bot_batch + process_bot_pair
- multi_bot_monitor.py (~417 lines) - everything else

Both files under 500 lines ✓

## Extraction:

### bot_processor.py
**Lines to extract:** 232-504 (process_bot_batch) + 565-766 (process_bot_pair)

**Methods:**
- `process_bot_batch()` - AI batch analysis for multiple pairs
- `process_bot_pair()` - Process single bot/pair combination

These methods need access to:
- `self.coinbase` - pass as parameter
- `self.get_candles_cached()` - pass as callback
- Various imports from trading_engine_v2, StrategyRegistry, models

### multi_bot_monitor.py (refactored)
Keep:
- Class init
- get_active_bots()
- timeframe_to_seconds()
- get_candles_cached()
- process_bot() - calls bot_processor methods
- log_ai_decision()
- execute_trading_logic()
- monitor_loop()
- start/stop/status methods

Update process_bot() to call bot_processor functions.

## Implementation:
1. Create app/bot_monitoring/bot_processor.py with extracted methods
2. Update multi_bot_monitor.py to import and delegate to bot_processor
3. Verify syntax
4. Backup original to _OLD_BACKUP.py
5. Commit
