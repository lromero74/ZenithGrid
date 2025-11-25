# STEP 3: trading_engine_v2.py Refactoring Plan

## Status: IN PROGRESS (2/6 modules completed)

## Completed Modules:
1. ✅ **position_manager.py** (99 lines) - Position CRUD operations
2. ✅ **order_logger.py** (119 lines) - Order history and AI logging

## Remaining Modules to Extract:

### 3. buy_executor.py (~300 lines)
**Location:** Lines 209-473 (execute_buy) + Lines 474-539 (execute_limit_buy)
**Functions to extract:**
- `execute_buy()` - Market buy order execution with position updates
- `execute_limit_buy()` - Limit buy order execution

**Key responsibilities:**
- Validate order sizes
- Execute market/limit buy orders via TradingClient
- Update position balances (total_quote_spent, total_base_acquired, average_buy_price)
- Create Trade records
- Log to OrderHistory
- Calculate USD values for tracking

### 4. sell_executor.py (~250 lines)
**Location:** Lines 540-608 (execute_limit_sell) + Lines 609-774 (execute_sell)
**Functions to extract:**
- `execute_sell()` - Market sell order execution with profit calculation
- `execute_limit_sell()` - Limit sell order execution

**Key responsibilities:**
- Execute market/limit sell orders
- Calculate profit (quote currency and USD)
- Close positions (update status, profit, closed_at)
- Create Trade records
- Update bot statistics (wins, losses, total profit)
- Log to OrderHistory

### 5. signal_processor.py (~300 lines)
**Location:** Lines 775-1099 (process_signal)
**Functions to extract:**
- `process_signal()` - Main orchestration logic

**Key responsibilities:**
- Get candle data from Coinbase
- Call strategy.analyze_signal()
- Determine buy/sell decisions via strategy.should_buy() / should_sell()
- Create new positions or manage existing ones
- Coordinate buy/sell execution
- Save AI logs
- Handle Signal records

### 6. trading_engine_v2.py (Refactored, ~200 lines)
**What remains:**
- StrategyTradingEngine class definition
- __init__() method
- Import all extracted modules
- Wire methods to call extracted functions
- Maintain same public API

## Extraction Pattern (Consistent across all modules):

```python
# BEFORE (instance method):
class StrategyTradingEngine:
    async def execute_buy(self, position, quote_amount, ...):
        # Uses: self.db, self.coinbase, self.bot, self.product_id, etc.
        ...

# AFTER (standalone function):
async def execute_buy(
    db: AsyncSession,
    coinbase: CoinbaseClient,
    trading_client: TradingClient,
    bot: Bot,
    product_id: str,
    position: Position,
    quote_amount: float,
    ...
):
    # All dependencies passed as parameters
    ...

# MAIN CLASS (wires everything):
class StrategyTradingEngine:
    async def execute_buy(self, position, quote_amount, ...):
        from app.trading_engine.buy_executor import execute_buy
        return await execute_buy(
            self.db,
            self.coinbase,
            self.trading_client,
            self.bot,
            self.product_id,
            position,
            quote_amount,
            ...
        )
```

## Benefits of This Refactoring:

1. **Testability**: Each function can be unit tested independently
2. **Readability**: Each module focuses on one responsibility
3. **Maintainability**: Changes to buy logic don't affect sell logic
4. **AI-friendly**: All files under 500 lines can be read by AI in one shot
5. **No circular imports**: Clean dependency tree

## Estimated Final Structure:

```
backend/app/
├── trading_engine/
│   ├── __init__.py
│   ├── position_manager.py      (99 lines)   ✅
│   ├── order_logger.py           (119 lines)  ✅
│   ├── buy_executor.py           (~300 lines) TODO
│   ├── sell_executor.py          (~250 lines) TODO
│   └── signal_processor.py       (~300 lines) TODO
├── trading_engine_v2.py          (~200 lines) TODO - Refactored wrapper
└── trading_engine_v2_OLD_BACKUP.py (1099 lines) - Preserved original
```

## Total Reduction:
- **Before**: 1099 lines in one file
- **After**: ~200 lines main + 1068 lines across 5 focused modules
- **Largest module**: ~300 lines (well under 500-line limit)

## Next Steps to Complete STEP 3:

1. Extract `buy_executor.py`
2. Extract `sell_executor.py`
3. Extract `signal_processor.py`
4. Create refactored `trading_engine_v2.py` wrapper
5. Rename original to `trading_engine_v2_OLD_BACKUP.py`
6. Verify with git diff - ensure no functionality dropped
7. Test syntax on all new files
8. Commit with detailed message

## Risk Mitigation:

- Each extraction is a separate commit
- Original file preserved as _OLD_BACKUP.py
- Git diff verification before final commit
- Public API remains unchanged (existing code still imports StrategyTradingEngine)
- All dependencies explicitly passed (no hidden state)
