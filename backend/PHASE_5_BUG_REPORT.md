# Phase 5: Potential Bugs Investigation Report

**Date:** 2025-11-23
**Branch:** HouseKeeping_1.1
**Status:** Investigation Complete - Awaiting User Review

---

## 🔴 CRITICAL BUGS (Runtime Errors - Would Crash)

### Bug #1: Wrong Class Name in Import (limit_order_monitor.py)

**Location:** `app/services/limit_order_monitor.py:16`

**Severity:** CRITICAL - ImportError on module load

**Current Code:**
```python
from app.coinbase_unified_client import CoinbaseUnifiedClient
```

**Problem:**
The class `CoinbaseUnifiedClient` does not exist in `app/coinbase_unified_client.py`. The actual class name is `CoinbaseClient`.

**Evidence:**
```bash
$ ./venv/bin/python -c "from app.services.limit_order_monitor import LimitOrderMonitor"
ImportError: cannot import name 'CoinbaseUnifiedClient' from 'app.coinbase_unified_client'
```

**Impact:**
- Module cannot be imported at all
- Any code trying to import `LimitOrderMonitor` will fail
- Currently dormant because module is not actively used yet

**Recommended Fix:**
```python
from app.coinbase_unified_client import CoinbaseClient
```
And update the type hint on line 24:
```python
def __init__(self, db: AsyncSession, coinbase_client: CoinbaseClient):
```

---

### Bug #2: Method Doesn't Exist (trading_client.py)

**Location:** `app/trading_client.py:51`

**Severity:** CRITICAL - AttributeError at runtime if triggered

**Current Code:**
```python
# Line 48-54
else:
    # For other currencies, use generic method if it exists
    # Otherwise, get from portfolio
    portfolio = await self.coinbase.get_portfolio()
    balances = portfolio.get("balances", {})
    currency_data = balances.get(currency, {})
    return float(currency_data.get("available", 0))
```

**Problem:**
`CoinbaseClient` does not have a `get_portfolio()` method (singular). The available methods are:
- `get_portfolios()` - Returns list of portfolios
- `get_portfolio_breakdown()` - Returns portfolio breakdown

**Call Chain:**
1. `get_balance(currency)` is called with non-BTC/non-USD currency
2. Falls through to else clause on line 48
3. Tries to call non-existent `get_portfolio()` method
4. Raises `AttributeError`

**Current Usage:**
- Only called from `get_quote_balance(product_id)`
- `get_quote_balance()` extracts quote currency from product_id
- Currently only BTC and USD pairs are used, so bug is dormant
- **WOULD TRIGGER** if anyone uses a trading pair with different quote currency (e.g., ETH-USDC)

**Recommended Fix:**
Depends on intended behavior. Options:
1. Use `get_portfolios()` and find the relevant portfolio
2. Use `get_portfolio_breakdown()` to get balances
3. Raise a clear error for unsupported quote currencies

---

### Bug #3: Outdated API Usage (position_manual_ops_router.py)

**Location:** `app/position_routers/position_manual_ops_router.py:46-72`

**Severity:** HIGH - Multiple runtime errors

**Problems:**

#### 3a. Non-existent Attributes (Lines 46, 49)
```python
if position.total_btc_spent + btc_amount > position.max_btc_allowed:
```
- `Position.total_btc_spent` doesn't exist → Should be `total_quote_spent`
- `Position.max_btc_allowed` doesn't exist → Should be `max_quote_allowed`
- Code wasn't updated when multi-currency support was added

#### 3b. Wrong Constructor Parameters (Lines 56-59)
```python
trading_client = TradingClient(coinbase)
engine = StrategyTradingEngine(
    db=db,
    trading_client=trading_client,  # WRONG - parameter doesn't exist
    bot=None,  # WRONG - bot is required, not Optional
    product_id=position.product_id
)
```

**Actual `StrategyTradingEngine.__init__` signature:**
```python
def __init__(
    self,
    db: AsyncSession,
    coinbase: CoinbaseClient,  # Not trading_client
    bot: Bot,  # Required, not Optional
    strategy: TradingStrategy,  # Missing!
    product_id: Optional[str] = None,
):
```

#### 3c. Non-existent Attribute (Line 72)
```python
"eth_acquired": trade.eth_amount,  # Trade.eth_amount doesn't exist
```
Should be `trade.base_amount` (multi-currency support)

**Impact:**
- Manual DCA add funds endpoint is completely broken
- Would fail on: attribute access, constructor call, and response building
- API endpoint exists but cannot work

**Recommended Fix:**
Complete rewrite of this endpoint to match current API:
1. Fix Position attribute names
2. Fix StrategyTradingEngine constructor call
3. Fix Trade attribute names
4. Test the endpoint thoroughly

---

## 🟡 TYPE HINT ISSUES (MyPy Warnings - Code Works But Type Unsafe)

### Issue #4: Method Signature Mismatch (ai_autonomous strategy)

**Location:** `app/strategies/ai_autonomous/__init__.py:251-258`

**Severity:** LOW - Type checker warning only

**Base Class Signature:**
```python
# app/strategies/__init__.py:69
async def analyze_signal(
    self,
    candles: List[Dict[str, Any]],
    current_price: float
) -> Optional[Dict[str, Any]]:
```

**AI Strategy Override:**
```python
# app/strategies/ai_autonomous/__init__.py:251
async def analyze_signal(
    self,
    candles: List[Dict[str, Any]],
    current_price: float,
    candles_by_timeframe: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    position: Optional[Any] = None,
    action_context: str = "hold",
) -> Optional[Dict[str, Any]]:
```

**Problem:**
AI strategy extends the base signature with additional optional parameters. This violates the Liskov Substitution Principle - you can't add required parameters to an overridden method.

**Why It Works:**
- Extra parameters have default values
- Python doesn't enforce type signatures at runtime
- Code using `strategy.analyze_signal(candles, current_price, position=x, action_context=y)` works fine

**MyPy Complaint:**
```
signal_processor.py:71: error: Unexpected keyword argument "position" for "analyze_signal"
signal_processor.py:71: error: Unexpected keyword argument "action_context" for "analyze_signal"
```

**Recommended Fix:**
Either:
1. Update base class to include optional parameters
2. Use `**kwargs` pattern in base class
3. Suppress mypy error with `# type: ignore` comment

---

### Issue #5: Incorrect Type Hint (models.py:89)

**Location:** `app/models.py:89`

**Severity:** LOW - Function definition type hint error

**Current Code:**
```python
def get_reserved_balance(self, aggregate_value: float = None):
```

**Problem:**
Type hint says `float` but default is `None`. Should be:
```python
def get_reserved_balance(self, aggregate_value: Optional[float] = None):
```

**Impact:**
- Function works correctly (accepts None)
- MyPy complains when None is passed
- Causes false positives in `signal_processor.py:93`

**Recommended Fix:**
```python
from typing import Optional

def get_reserved_balance(self, aggregate_value: Optional[float] = None):
```

---

### Bug #6: Missing Error Logging in Limit Close Endpoint

**Location:** `app/position_routers/position_limit_orders_router.py`

**Severity:** MEDIUM - Poor error handling, difficult debugging

**Problem:**
The `/limit-close` endpoint lacked proper error logging when limit order creation failed, making it difficult to diagnose issues.

**Fixed:** Added comprehensive logging and error handling in `HouseKeeping_1.1_bugfix` branch.

---

### Bug #7: AI Strategy Missing Method (multi_bot_monitor.py)

**Location:** `app/multi_bot_monitor.py:408`

**Severity:** CRITICAL - AttributeError preventing AI bot monitoring

**Current Code:**
```python
market_context = strategy._prepare_market_context(candles, current_price)
```

**Problem:**
- Code assumes `_prepare_market_context()` is a method on the strategy object
- This method doesn't exist on any strategy class
- The actual function is `prepare_market_context()` in `app.strategies.ai_autonomous.market_analysis` module
- Causes: `AttributeError: 'AIAutonomousStrategy' object has no attribute '_prepare_market_context'`

**Impact:**
- AI bot monitoring completely fails
- All positions using AI strategy cannot be monitored
- Prevents batch analysis of AI strategy positions

**Recommended Fix:**
```python
# Import at top of file
from app.strategies.ai_autonomous import market_analysis

# Line 408
market_context = market_analysis.prepare_market_context(candles, current_price)
```

**Fixed:** Implemented in `HouseKeeping_1.1_bugfix` branch (commit c9239ba).

---

## 📊 SUMMARY

| Bug | Severity | Impact | Runtime Error? | Status |
|-----|----------|--------|----------------|--------|
| #1: Wrong class import | CRITICAL | Cannot import module | YES | FIXED |
| #2: Method doesn't exist | CRITICAL | Would crash if triggered | YES (dormant) | FIXED |
| #3: Outdated API usage | HIGH | Endpoint completely broken | YES | FIXED |
| #4: Signature mismatch | LOW | Type checker warning only | NO | FIXED |
| #5: Incorrect type hint | LOW | Type checker warning only | NO | FIXED |
| #6: Missing error logging | MEDIUM | Hard to debug limit orders | NO | FIXED |
| #7: AI strategy method error | CRITICAL | AI bot monitoring fails | YES | FIXED |

---

## 🎯 RECOMMENDED ACTION PLAN

### Immediate (Must Fix Before Merge):
1. **Bug #1**: Fix import in `limit_order_monitor.py` (1 line change)
2. **Bug #3**: Fix or disable manual DCA endpoint in `position_manual_ops_router.py`

### High Priority (Before Using Feature):
3. **Bug #2**: Fix `get_balance()` method in `trading_client.py`

### Low Priority (Type Hint Cleanup):
4. **Issue #4**: Document signature override or update base class
5. **Issue #5**: Fix `get_reserved_balance()` type hint

---

## ✅ VERIFICATION STEPS

After fixes are implemented:

### Test Bug #1:
```bash
./venv/bin/python -c "from app.services.limit_order_monitor import LimitOrderMonitor; print('Import successful')"
```

### Test Bug #2:
```python
# Test that non-BTC/USD currencies either work or raise clear error
trading_client = TradingClient(coinbase)
balance = await trading_client.get_quote_balance("ETH-USDC")  # Should not crash
```

### Test Bug #3:
```bash
# Test manual DCA endpoint
curl -X POST http://localhost:8000/api/positions/{id}/add-funds \
  -H "Content-Type: application/json" \
  -d '{"btc_amount": 0.001}'
```

### Type Hints:
```bash
./venv/bin/mypy app --ignore-missing-imports | grep -E "(limit_order|trading_client|position_manual|signal_processor|models\.py:89)"
```

---

## 📝 NOTES

- All bugs were identified through static analysis (mypy + manual code review)
- No bugs were found through runtime testing (some endpoints may not be tested)
- Some bugs are dormant (not triggered by current usage patterns)
- Multi-currency refactoring left some files outdated
