# Refactoring Completion Guide

**Purpose:** Step-by-step instructions to complete the remaining refactoring work
**Status:** STEPs 1-2 complete, STEP 3 partially done (2/6 modules)
**Remaining:** Complete STEP 3, then STEPs 4-13

---

## STEP 3: Complete trading_engine_v2.py (4 modules remaining)

### Current Status:
- ✅ position_manager.py (99 lines)
- ✅ order_logger.py (119 lines)
- ⏳ buy_executor.py (NEXT)
- ⏳ sell_executor.py
- ⏳ signal_processor.py
- ⏳ trading_engine_v2.py (refactored wrapper)

### 3.3: Extract buy_executor.py

**Lines to extract:** 209-539 (execute_buy + execute_limit_buy methods)

**Create:** `backend/app/trading_engine/buy_executor.py`

```python
"""
Buy order execution for trading engine
Handles market and limit buy orders
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.coinbase_unified_client import CoinbaseClient
from app.models import Bot, PendingOrder, Position, Trade
from app.trading_client import TradingClient
from app.order_validation import validate_order_size
from app.currency_utils import format_with_usd, get_quote_currency

logger = logging.getLogger(__name__)


async def execute_buy(
    db: AsyncSession,
    coinbase: CoinbaseClient,
    trading_client: TradingClient,
    bot: Bot,
    product_id: str,
    position: Position,
    quote_amount: float,
    current_price: float,
    trade_type: str,
    signal_data: Optional[Dict[str, Any]] = None,
    commit_on_error: bool = True
) -> Optional[Trade]:
    """
    Execute a buy order (market or limit based on configuration)

    Extract lines 209-473 from original file
    Replace all self.* references with passed parameters
    """
    # [COPY LINES 236-473 from original file]
    # Replace:
    #   self.db → db
    #   self.coinbase → coinbase
    #   self.trading_client → trading_client
    #   self.bot → bot
    #   self.product_id → product_id
    #   self.quote_currency → get_quote_currency(product_id)
    #   self.log_order_to_history() → from app.trading_engine.order_logger import log_order_to_history
    #   self.execute_limit_buy() → execute_limit_buy() (defined below)
    pass  # TODO: Copy implementation


async def execute_limit_buy(
    db: AsyncSession,
    coinbase: CoinbaseClient,
    bot: Bot,
    product_id: str,
    position: Position,
    quote_amount: float,
    limit_price: float,
    trade_type: str,
    signal_data: Optional[Dict[str, Any]] = None
) -> PendingOrder:
    """
    Place a limit buy order

    Extract lines 474-539 from original file
    """
    # [COPY LINES 474-539 from original file]
    pass  # TODO: Copy implementation
```

**Commands:**
```bash
cd /Users/louis/GetRidOf3CommasBecauseTheyGoDownTooOften/backend
python3 -m py_compile app/trading_engine/buy_executor.py
git add app/trading_engine/buy_executor.py
git commit -m "STEP 3.3: Extract buy_executor.py from trading_engine_v2.py (~330 lines)

- Extracted execute_buy() - Market buy with validation
- Extracted execute_limit_buy() - Limit buy order placement
- Handles order validation, error logging, position updates
- Part of STEP 3: Split trading_engine_v2.py"
```

---

### 3.4: Extract sell_executor.py

**Lines to extract:** 540-774 (execute_limit_sell + execute_sell methods)

**Create:** `backend/app/trading_engine/sell_executor.py`

Similar pattern - extract both methods, convert to standalone functions.

**Commands:**
```bash
python3 -m py_compile app/trading_engine/sell_executor.py
git add app/trading_engine/sell_executor.py
git commit -m "STEP 3.4: Extract sell_executor.py from trading_engine_v2.py (~235 lines)"
```

---

### 3.5: Extract signal_processor.py

**Lines to extract:** 775-1099 (process_signal method)

**Create:** `backend/app/trading_engine/signal_processor.py`

**Commands:**
```bash
python3 -m py_compile app/trading_engine/signal_processor.py
git add app/trading_engine/signal_processor.py
git commit -m "STEP 3.5: Extract signal_processor.py from trading_engine_v2.py (~325 lines)"
```

---

### 3.6: Create Refactored trading_engine_v2.py

**Create:** New `trading_engine_v2.py` that imports and wires everything

```python
"""
Strategy-Based Trading Engine (Refactored)

Wrapper class that coordinates all trading engine modules.
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.coinbase_unified_client import CoinbaseClient
from app.currency_utils import get_quote_currency
from app.models import Bot, Position
from app.strategies import TradingStrategy
from app.trading_client import TradingClient

# Import extracted modules
from app.trading_engine import position_manager
from app.trading_engine import order_logger
from app.trading_engine import buy_executor
from app.trading_engine import sell_executor
from app.trading_engine import signal_processor

logger = logging.getLogger(__name__)


class StrategyTradingEngine:
    """Strategy-agnostic trading engine - wrapper for modular functions"""

    def __init__(
        self,
        db: AsyncSession,
        coinbase: CoinbaseClient,
        bot: Bot,
        strategy: TradingStrategy,
        product_id: Optional[str] = None
    ):
        self.db = db
        self.coinbase = coinbase
        self.trading_client = TradingClient(coinbase)
        self.bot = bot
        self.strategy = strategy
        self.product_id = product_id or (bot.get_trading_pairs()[0] if hasattr(bot, 'get_trading_pairs') else bot.product_id)
        self.quote_currency = get_quote_currency(self.product_id)

    async def save_ai_log(self, signal_data, decision, current_price, position):
        """Delegate to order_logger module"""
        await order_logger.save_ai_log(
            self.db, self.bot, self.product_id, signal_data, decision, current_price, position
        )

    async def get_active_position(self):
        """Delegate to position_manager module"""
        return await position_manager.get_active_position(self.db, self.bot, self.product_id)

    async def get_open_positions_count(self):
        """Delegate to position_manager module"""
        return await position_manager.get_open_positions_count(self.db, self.bot)

    async def create_position(self, quote_balance, quote_amount):
        """Delegate to position_manager module"""
        return await position_manager.create_position(
            self.db, self.coinbase, self.bot, self.product_id, quote_balance, quote_amount
        )

    async def log_order_to_history(self, position, side, order_type, trade_type, quote_amount, price, status, **kwargs):
        """Delegate to order_logger module"""
        await order_logger.log_order_to_history(
            self.db, self.bot, self.product_id, position, side, order_type, trade_type,
            quote_amount, price, status, **kwargs
        )

    async def execute_buy(self, position, quote_amount, current_price, trade_type, signal_data=None, commit_on_error=True):
        """Delegate to buy_executor module"""
        return await buy_executor.execute_buy(
            self.db, self.coinbase, self.trading_client, self.bot, self.product_id,
            position, quote_amount, current_price, trade_type, signal_data, commit_on_error
        )

    async def execute_limit_buy(self, position, quote_amount, limit_price, trade_type, signal_data=None):
        """Delegate to buy_executor module"""
        return await buy_executor.execute_limit_buy(
            self.db, self.coinbase, self.bot, self.product_id,
            position, quote_amount, limit_price, trade_type, signal_data
        )

    async def execute_sell(self, position, current_price, signal_data=None):
        """Delegate to sell_executor module"""
        return await sell_executor.execute_sell(
            self.db, self.coinbase, self.trading_client, self.bot, self.product_id,
            position, current_price, signal_data
        )

    async def execute_limit_sell(self, position, limit_price, signal_data=None):
        """Delegate to sell_executor module"""
        return await sell_executor.execute_limit_sell(
            self.db, self.coinbase, self.bot, self.product_id,
            position, limit_price, signal_data
        )

    async def process_signal(self, candles, signal_data, current_price, position):
        """Delegate to signal_processor module"""
        return await signal_processor.process_signal(
            self.db, self.coinbase, self.trading_client, self.bot, self.strategy,
            self.product_id, candles, signal_data, current_price, position
        )
```

**Commands:**
```bash
mv app/trading_engine_v2.py app/trading_engine_v2_OLD_BACKUP.py
# Create new trading_engine_v2.py with above content
python3 -m py_compile app/trading_engine_v2.py
git add app/trading_engine_v2.py app/trading_engine_v2_OLD_BACKUP.py
git commit -m "STEP 3.6: Refactor trading_engine_v2.py into wrapper class (~150 lines)

- Created new wrapper that delegates to extracted modules
- Preserved public API (100% backward compatible)
- Original file moved to _OLD_BACKUP.py (1099 lines)
- New file: 150 lines of clean delegation
- STEP 3 COMPLETE: 1099 → 6 focused modules"
```

---

## STEP 4: coinbase_unified_client.py (868 lines)

### Analysis:
- Contains CDP (Cloud Development Platform) and HMAC auth
- Get/list methods for products, candles, orders, balances
- Calculate aggregate BTC/USD values
- Portfolio breakdown

### Proposed Split:
1. **auth_handler.py** (~150 lines) - CDP and HMAC authentication
2. **product_api.py** (~200 lines) - Product listings, candles, ticker
3. **order_api.py** (~200 lines) - Order creation, cancellation, fetching
4. **balance_api.py** (~200 lines) - Balances, portfolio, aggregates
5. **coinbase_unified_client.py** (~150 lines) - Main class wrapper

---

## STEP 5: multi_bot_monitor.py (801 lines)

### Proposed Split:
1. **bot_processor.py** (~300 lines) - Process individual bot logic
2. **monitor_loop.py** (~250 lines) - Main monitoring loop
3. **multi_bot_monitor.py** (~250 lines) - Coordinator class

---

## STEP 6-13: Remaining Files

Follow similar pattern for each:
1. Analyze structure and logical boundaries
2. Extract cohesive modules (200-400 lines each)
3. Create wrapper class that delegates
4. Move original to _OLD_BACKUP.py
5. Verify with git diff
6. Commit with detailed message

---

## Final Verification Checklist (Before Merge)

- [ ] All 13 files refactored
- [ ] All modules under 500 lines
- [ ] python3 -m py_compile passes on all files
- [ ] git diff shows no dropped functionality
- [ ] All _OLD_BACKUP.py files preserved
- [ ] Update HOUSEKEEPING_PROGRESS.md with completion
- [ ] Push to testbot production branch
- [ ] Manual testing by Louis
- [ ] Merge approval from Louis

---

**Estimated Remaining Work:**
- STEP 3: 4 modules (~2-3 hours)
- STEPs 4-13: 10 files (~10-15 hours)
- **Total: 12-18 hours of focused refactoring work**
