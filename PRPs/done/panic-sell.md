# PRP: Panic Sell — Account-Wide Emergency Liquidation

## Feature Overview

An emergency liquidation button on the Positions page that lets a user, in a single flow:

1. **Cancel all deals** (marks positions cancelled, no exchange action) OR **Sell all positions at market** (executes exchange sells)
2. Optionally **sell proceeds to a target currency** (USD / USDC / USDT / BTC / ETH) by running portfolio conversion after positions close
3. Optionally **stop all active bots** so no new positions open
4. Optionally **stop the portfolio rebalancer** (both account-level and bot-level)
5. Optionally **stop auto-buy BTC** (`account.auto_buy_enabled = False`)
6. Optionally **zero out minimum balance reserves** (`min_balance_usd/btc/eth/usdc/usdt = 0.0`)
7. Shows a **live progress meter** tracking each phase to completion

## TDD Requirement
**Write failing tests FIRST before any implementation code.** Follow the TDD cycle: red → green → refactor. No feature code ships without a corresponding failing test written first.

The feature runs as a **background task** (like the existing portfolio conversion) so the UI can track multi-step progress.

---

## User Flow

```
Positions page header: [🚨 Panic Sell] button
  → PanicSellModal opens (multi-step)

Step 1 — Choose action:
  ○ Cancel All Deals     (no market orders)
  ● Sell All at Market   (executes exchange sells)

Step 2 (if sell) — Target currency:
  [USD] [USDC] [USDT] [BTC] [ETH]
  Note: "After positions close, all free balances will be
         converted to the selected currency"

Step 3 — Options:
  ☑ Stop all active bots (prevent new positions)
  ☑ Disable portfolio rebalancer
  ☑ Disable bot rebalancer groups
  ☑ Disable auto-buy BTC
  ☑ Zero out minimum balance reserves

Step 4 — Confirmation:
  Red warning box: summary of what will happen
  Type "CONFIRM" to enable submit button

Step 5 — Progress meter (after submit):
  Phase 1: Stopping bots...       [✓]
  Phase 2: Closing positions...   [████████░░] 8/10
  Phase 3: Disabling rebalancer...[✓]
  Phase 4: Converting portfolio...[running]
            → polls conversion status endpoint

Step 6 — Result summary:
  ✓ 3 bots stopped
  ✓ 10 positions cancelled/sold
  ✓ Rebalancer disabled
  ✓ Portfolio conversion started (task_id)
```

---

## Research Findings

### Existing Per-Bot Endpoints (to mirror)

**`POST /api/bots/{bot_id}/sell-all-positions`** — `bot_control_router.py` lines 244-338
- Uses `asyncio.gather()` to prefetch prices in parallel for all unique product_ids
- For each position: creates `StrategyTradingEngine` and calls `engine.execute_sell(position, current_price, signal_data=None)`
- **Does NOT set `exit_reason = "manual"`** before selling — positions will count in win rate denominator
- Returns `{sold_count, failed_count, total_profit_quote, errors}`

**`POST /api/bots/{bot_id}/cancel-all-positions`** — `bot_control_router.py` lines 189-241
- Sets `position.status = "cancelled"`, `position.closed_at = now`
- No exchange interaction
- Cancelled positions already excluded from win rate: `bot_crud_router.py` line 262: `closed_positions = [p for p in all_positions if p.status == "closed"]`

**`POST /api/bots/{bot_id}/stop`** — `bot_control_router.py` lines 110-148
- Sets `bot.is_active = False`, clears `last_started_at`, accumulates running seconds

### Win Rate — Confirmed Safe

`bot_stats_service.py` line 262: `closed_positions = [p for p in all_positions if p.status == "closed"]`
- Cancelled positions (`status == "cancelled"`) are **already excluded** from win rate. No bug.
- For sold positions via panic sell: **must set `position.exit_reason = "manual"` before `execute_sell()`** so they're excluded from the win rate denominator (see `position_actions_router.py` line 137: `position.exit_reason = "manual"`).

### Portfolio Conversion Service

**`portfolio_conversion_service.py`** — already handles intermediate pair routing:
- `_sell_currency_with_fallback(exchange, currency, available, target_currency)` — tries direct pair (`{currency}-{target}`), falls back to alternate intermediate pair if 400/403
- `_convert_intermediate_currency(exchange, from, to, errors)` — converts accumulated intermediate currency to final target
- Currently only supports `target_currency in ["BTC", "USD"]`
- `account_router.py` line 154: `if target_currency not in ["BTC", "USD"]` — validates and rejects others

**Extension needed**: Add USDC, USDT, ETH as valid targets. Each needs:
- Direct pair attempt: `{currency}-USDC`, `{currency}-USDT`, `{currency}-ETH`
- Fallback to USD intermediate
- Final conversion: USD → target (buy `USDC-USD`, `USDT-USD`, `ETH-USD`)

USDC↔USD: On Coinbase, these can be converted via the `USDC-USD` pair or Coinbase's convert API. Use `create_market_order(product_id="USDC-USD", side="BUY", funds=...)` for the buy.

### Auth Pattern

`position_actions_router.py` dependencies.py:
```python
async def manager_account_ids(db, user_id) -> set[int]
```
Returns account IDs the user owns OR manages. Use this to validate `account_id` in request.

Permission needed: `require_permission(Perm.POSITIONS_WRITE, Perm.BOTS_WRITE)` — panic sell needs both.

### Progress Tracking Pattern

`portfolio_conversion_service.py` has in-memory `_conversion_tasks: Dict[str, Dict]`:
```python
{
  "task_id": str,
  "status": "running" | "completed" | "failed",
  "total": int,
  "current": int,
  "progress_pct": int,
  "sold_count": int,
  "failed_count": int,
  "errors": list[str],
  "message": str,
  "started_at": str,
  "completed_at": str | None
}
```
Follow the same pattern for panic sell progress tracking.

### Frontend Placement

`Positions.tsx` lines 283-310: header right side has `flex items-center gap-2 flex-wrap` container with the existing "Active" badge and a small button. Add the Panic Sell button here.

Pattern for modals: `useConfirm()` from `ConfirmContext`, `useNotifications()` for toasts. Example in `BotListItem.tsx` lines 725-764.

---

## Implementation Tasks (in order)

### Task 1: Extend portfolio_conversion_service.py for USDC/USDT/ETH

**File**: `backend/app/services/portfolio_conversion_service.py`

Change `_sell_currency_with_fallback` to handle 5 target currencies:

```python
SUPPORTED_TARGET_CURRENCIES = {"BTC", "USD", "USDC", "USDT", "ETH"}

# For each target that isn't USD, the fallback intermediate is USD.
# For USD target, fallback is BTC.
_FALLBACK_INTERMEDIATE = {
    "BTC": "USD",
    "USDC": "USD",
    "USDT": "USD",
    "ETH": "USD",
    "USD": "BTC",
}

async def _sell_currency_with_fallback(exchange, currency, available, target_currency):
    """Try direct pair first. Fall back to intermediate if direct fails.
    Returns: "direct" | "intermediate"
    """
    primary_pair = f"{currency}-{target_currency}"
    intermediate = _FALLBACK_INTERMEDIATE.get(target_currency, "USD")
    fallback_pair = f"{currency}-{intermediate}"

    try:
        await exchange.create_market_order(product_id=primary_pair, side="SELL", size=str(available))
        await asyncio.sleep(0.2)
        return "direct"
    except Exception as direct_error:
        if "403" in str(direct_error) or "400" in str(direct_error):
            await exchange.create_market_order(product_id=fallback_pair, side="SELL", size=str(available))
            await asyncio.sleep(0.2)
            return "intermediate"
        raise
```

Extend `_convert_intermediate_currency` for new targets:
```python
async def _convert_intermediate_currency(exchange, from_currency, to_currency, errors):
    """Convert accumulated intermediate (always USD or BTC) to final target."""
    await asyncio.sleep(1.0)
    try:
        accounts = await exchange.get_accounts(force_fresh=True)
        account = next((a for a in accounts if a.get("currency") == from_currency), None)
        if not account:
            return
        available = float(account.get("available_balance", {}).get("value", "0"))
        min_amounts = {"USD": 1.0, "BTC": 0.00001, "USDC": 1.0, "USDT": 1.0, "ETH": 0.0001}
        if available <= min_amounts.get(from_currency, 0):
            return

        if from_currency == "USD":
            # Buying target with USD (funds-based buy)
            spend_amount = round(available * 0.99, 2)
            if to_currency == "BTC":
                await exchange.create_market_order(product_id="BTC-USD", side="BUY", funds=str(spend_amount))
            elif to_currency == "USDC":
                await exchange.create_market_order(product_id="USDC-USD", side="BUY", funds=str(spend_amount))
            elif to_currency == "USDT":
                await exchange.create_market_order(product_id="USDT-USD", side="BUY", funds=str(spend_amount))
            elif to_currency == "ETH":
                await exchange.create_market_order(product_id="ETH-USD", side="BUY", funds=str(spend_amount))
        elif from_currency == "BTC":
            # Selling BTC to get USD
            await exchange.create_market_order(product_id="BTC-USD", side="SELL", size=str(available))
    except Exception as e:
        logger.error(f"Failed to convert {from_currency} to {to_currency}: {e}")
        errors.append(f"{from_currency}-to-{to_currency} conversion: {str(e)}")
```

Update `run_portfolio_conversion` to remove the target_currency restriction (validation moves to the router layer):
- Remove the `used_intermediate = {"USD": [], "BTC": []}` hardcoded dict
- Replace with dynamic tracking based on `_FALLBACK_INTERMEDIATE[target_currency]`
- After main loop: if any positions went through intermediate, convert intermediate → target

Update `account_router.py` line 154:
```python
from app.services.portfolio_conversion_service import SUPPORTED_TARGET_CURRENCIES
if target_currency not in SUPPORTED_TARGET_CURRENCIES:
    raise HTTPException(status_code=400, detail=f"target_currency must be one of: {', '.join(SUPPORTED_TARGET_CURRENCIES)}")
```

### Task 2: Create panic_sell_router.py (NEW)

**File**: `backend/app/position_routers/panic_sell_router.py`

```python
"""
Panic Sell Router — Account-wide emergency liquidation.

POST /panic-sell          Initiate panic sell (returns task_id immediately)
GET  /panic-sell-status/{task_id}  Poll progress
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import Perm, get_current_user, manager_account_ids, require_permission
from app.database import get_db
from app.models.trading import Account, Bot, BotRebalancerGroup, Position
from app.models.user import User
from app.services.portfolio_conversion_service import (
    SUPPORTED_TARGET_CURRENCIES,
    run_portfolio_conversion,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ── In-memory progress tracking (mirrors portfolio_conversion_service pattern) ──
_panic_tasks: Dict[str, Dict] = {}


class PanicSellRequest(BaseModel):
    account_id: int
    action: Literal["cancel", "sell"]
    target_currency: Optional[Literal["USD", "USDC", "USDT", "BTC", "ETH"]] = None
    stop_bots: bool = True
    stop_portfolio_rebalancer: bool = True
    stop_bot_rebalancer: bool = True
    stop_auto_buy: bool = True
    zero_min_balances: bool = True
    confirm: bool = False


def _init_task(task_id: str) -> None:
    _panic_tasks[task_id] = {
        "task_id": task_id,
        "status": "running",
        "phase": "starting",
        "message": "Initializing...",
        "bots_stopped": 0,
        "positions_total": 0,
        "positions_current": 0,
        "positions_acted": 0,
        "positions_failed": 0,
        "portfolio_rebalancer_stopped": False,
        "bot_rebalancer_groups_stopped": 0,
        "auto_buy_stopped": False,
        "min_balances_zeroed": False,
        "conversion_task_id": None,
        "conversion_status_url": None,
        "errors": [],
        "progress_pct": 0,
        "started_at": datetime.utcnow().isoformat(),
        "completed_at": None,
    }


def _update_task(task_id: str, **kwargs) -> None:
    if task_id not in _panic_tasks:
        return
    task = _panic_tasks[task_id]
    task.update(kwargs)
    # Recompute progress_pct
    total = task.get("positions_total", 0)
    current = task.get("positions_current", 0)
    if total > 0:
        task["progress_pct"] = int((current / total) * 100)
    if kwargs.get("status") in ("completed", "failed"):
        task["completed_at"] = datetime.utcnow().isoformat()


@router.post("/panic-sell")
async def panic_sell(
    request: PanicSellRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.POSITIONS_WRITE, Perm.BOTS_WRITE)),
):
    """Initiate account-wide panic sell. Returns task_id immediately."""
    if not request.confirm:
        raise HTTPException(status_code=400, detail="confirm must be true")

    if request.target_currency and request.target_currency not in SUPPORTED_TARGET_CURRENCIES:
        raise HTTPException(
            status_code=400,
            detail=f"target_currency must be one of: {', '.join(SUPPORTED_TARGET_CURRENCIES)}",
        )

    # Validate account access
    account_ids = await manager_account_ids(db, current_user.id)
    if request.account_id not in account_ids:
        raise HTTPException(status_code=403, detail="Not authorized for this account")

    task_id = str(uuid.uuid4())
    _init_task(task_id)

    background_tasks.add_task(
        _run_panic_sell,
        task_id=task_id,
        account_id=request.account_id,
        action=request.action,
        target_currency=request.target_currency,
        stop_bots=request.stop_bots,
        stop_portfolio_rebalancer=request.stop_portfolio_rebalancer,
        stop_bot_rebalancer=request.stop_bot_rebalancer,
        user_id=current_user.id,
    )

    return {
        "task_id": task_id,
        "message": "Panic sell initiated",
        "status_url": f"/api/positions/panic-sell-status/{task_id}",
    }


@router.get("/panic-sell-status/{task_id}")
async def get_panic_sell_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """Poll panic sell progress."""
    progress = _panic_tasks.get(task_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Task not found")
    return progress


async def _run_panic_sell(
    task_id: str,
    account_id: int,
    action: str,
    target_currency: Optional[str],
    stop_bots: bool,
    stop_portfolio_rebalancer: bool,
    stop_bot_rebalancer: bool,
    user_id: int,
) -> None:
    """Background worker: executes all phases of the panic sell."""
    from app.database import get_db

    try:
        async for db in get_db():
            await _execute_panic_sell(
                db, task_id, account_id, action, target_currency,
                stop_bots, stop_portfolio_rebalancer, stop_bot_rebalancer, user_id,
            )
            break
    except Exception as e:
        logger.error(f"Panic sell task {task_id} failed: {e}")
        _update_task(task_id, status="failed", message=f"Panic sell failed: {str(e)}")


async def _execute_panic_sell(
    db, task_id, account_id, action, target_currency,
    stop_bots, stop_portfolio_rebalancer, stop_bot_rebalancer, user_id,
):
    errors = []

    # ── Phase 1: Stop all active bots ──────────────────────────────────────
    bots_stopped = 0
    if stop_bots:
        _update_task(task_id, phase="stopping_bots", message="Stopping all active bots...")
        bots_result = await db.execute(
            select(Bot).where(Bot.account_id == account_id, Bot.is_active == True)
        )
        active_bots = bots_result.scalars().all()
        now = datetime.utcnow()
        for bot in active_bots:
            try:
                if bot.last_started_at:
                    elapsed = (now - bot.last_started_at).total_seconds()
                    bot.total_running_seconds = (bot.total_running_seconds or 0.0) + elapsed
                bot.is_active = False
                bot.last_started_at = None
                bot.updated_at = now
                bots_stopped += 1
            except Exception as e:
                errors.append(f"Failed to stop bot {bot.id}: {str(e)}")
        await db.commit()
        _update_task(task_id, bots_stopped=bots_stopped)

    # ── Phase 2: Cancel or sell all open positions ──────────────────────────
    _update_task(task_id, phase="closing_positions", message="Loading open positions...")
    positions_result = await db.execute(
        select(Position).where(
            Position.account_id == account_id,
            Position.status == "open",
        )
    )
    positions = positions_result.scalars().all()
    total = len(positions)
    _update_task(task_id, positions_total=total, message=f"Closing {total} positions...")

    positions_acted = 0
    positions_failed = 0

    if action == "cancel":
        now = datetime.utcnow()
        for idx, position in enumerate(positions, 1):
            try:
                position.status = "cancelled"
                position.closed_at = now
                positions_acted += 1
            except Exception as e:
                positions_failed += 1
                errors.append(f"Cancel #{position.id}: {str(e)}")
            _update_task(
                task_id,
                positions_current=idx,
                positions_acted=positions_acted,
                positions_failed=positions_failed,
                message=f"Cancelling {idx}/{total}...",
            )
        await db.commit()

    elif action == "sell":
        from app.services.exchange_service import get_exchange_client_for_account
        from app.strategies import StrategyRegistry
        from app.trading_engine_v2 import StrategyTradingEngine

        exchange = await get_exchange_client_for_account(db, account_id)
        if not exchange:
            _update_task(task_id, status="failed", message="No exchange client for account")
            return

        # Group positions by bot so we can get per-bot strategy
        bots_result = await db.execute(
            select(Bot).where(Bot.account_id == account_id)
        )
        bots_map = {b.id: b for b in bots_result.scalars().all()}

        # Prefetch all prices in parallel
        unique_products = list({p.product_id for p in positions if p.product_id})

        async def _get_price(product_id):
            try:
                return (product_id, await exchange.get_current_price(product_id))
            except Exception:
                return (product_id, None)

        price_results = await asyncio.gather(*[_get_price(pid) for pid in unique_products])
        price_map = {pid: price for pid, price in price_results if price is not None}

        for idx, position in enumerate(positions, 1):
            try:
                bot = bots_map.get(position.bot_id)
                if not bot:
                    raise ValueError(f"Bot {position.bot_id} not found")
                current_price = price_map.get(position.product_id)
                if current_price is None:
                    raise ValueError(f"No price for {position.product_id}")

                strategy = StrategyRegistry.get_strategy(bot.strategy_type, bot.strategy_config)
                # Mark as manual close BEFORE execute_sell (matches force-close pattern)
                # so panic-sold positions are excluded from win rate denominator
                position.exit_reason = "manual"
                engine = StrategyTradingEngine(
                    db=db, exchange=exchange, bot=bot,
                    strategy=strategy, product_id=position.product_id,
                )
                await engine.execute_sell(
                    position=position, current_price=current_price, signal_data=None
                )
                positions_acted += 1
            except Exception as e:
                positions_failed += 1
                errors.append(f"Sell #{position.id} ({position.product_id}): {str(e)}")

            _update_task(
                task_id,
                positions_current=idx,
                positions_acted=positions_acted,
                positions_failed=positions_failed,
                message=f"Selling {idx}/{total}...",
            )

    # ── Phase 3: Stop rebalancers ───────────────────────────────────────────
    portfolio_rebalancer_stopped = False
    bot_rebalancer_groups_stopped = 0

    if stop_portfolio_rebalancer or stop_bot_rebalancer:
        _update_task(task_id, phase="stopping_rebalancers", message="Disabling rebalancers...")

    if stop_portfolio_rebalancer:
        try:
            account_result = await db.execute(
                select(Account).where(Account.id == account_id)
            )
            account = account_result.scalars().first()
            if account and account.rebalance_enabled:
                account.rebalance_enabled = False
                portfolio_rebalancer_stopped = True
            await db.commit()
        except Exception as e:
            errors.append(f"Failed to stop portfolio rebalancer: {str(e)}")

    if stop_bot_rebalancer:
        try:
            groups_result = await db.execute(
                select(BotRebalancerGroup).where(
                    BotRebalancerGroup.account_id == account_id,
                    BotRebalancerGroup.enabled == True,
                )
            )
            groups = groups_result.scalars().all()
            for group in groups:
                group.enabled = False
                bot_rebalancer_groups_stopped += 1
            await db.commit()
        except Exception as e:
            errors.append(f"Failed to stop bot rebalancer groups: {str(e)}")

    _update_task(
        task_id,
        portfolio_rebalancer_stopped=portfolio_rebalancer_stopped,
        bot_rebalancer_groups_stopped=bot_rebalancer_groups_stopped,
    )

    # ── Phase 4: Trigger portfolio conversion (optional) ───────────────────
    conversion_task_id = None
    if action == "sell" and target_currency:
        _update_task(task_id, phase="converting", message=f"Starting portfolio conversion to {target_currency}...")
        conversion_task_id = str(uuid.uuid4())
        # run_portfolio_conversion is a coroutine — run directly since we're already async
        asyncio.ensure_future(
            run_portfolio_conversion(
                task_id=conversion_task_id,
                account_id=account_id,
                target_currency=target_currency,
                user_id=user_id,
            )
        )
        _update_task(
            task_id,
            conversion_task_id=conversion_task_id,
            conversion_status_url=f"/api/account/conversion-status/{conversion_task_id}",
        )

    # ── Complete ────────────────────────────────────────────────────────────
    logger.warning(
        f"🚨 PANIC SELL task {task_id}: "
        f"action={action}, bots_stopped={bots_stopped}, "
        f"positions={positions_acted}/{total}, "
        f"rebalancer={'stopped' if portfolio_rebalancer_stopped else 'kept'}"
    )

    _update_task(
        task_id,
        status="completed",
        phase="completed",
        message=(
            f"Complete: {bots_stopped} bots stopped, "
            f"{positions_acted} positions {'cancelled' if action == 'cancel' else 'sold'}"
            + (f", converting to {target_currency}" if conversion_task_id else "")
        ),
        errors=errors,
        positions_current=total,
    )
```

### Task 3: Register panic_sell_router in positions_router.py

**File**: `backend/app/routers/positions_router.py`

Add:
```python
from app.position_routers import panic_sell_router
# ...
router.include_router(panic_sell_router.router)
```

### Task 4: Write tests FIRST (TDD)

**File**: `backend/tests/position_routers/test_panic_sell_router.py`

Test structure (write failing tests first, then implement):

```python
"""
Tests for panic_sell_router.py

Covers:
- POST /panic-sell: requires confirm=True (400 if false)
- POST /panic-sell: rejects unauthorized account (403)
- POST /panic-sell: cancel action — sets all open positions to cancelled
- POST /panic-sell: cancel action — does NOT affect closed/cancelled positions
- POST /panic-sell: stops active bots when stop_bots=True
- POST /panic-sell: disables account rebalancer when stop_portfolio_rebalancer=True
- POST /panic-sell: disables bot rebalancer groups when stop_bot_rebalancer=True
- POST /panic-sell: triggers portfolio conversion when action=sell + target_currency
- POST /panic-sell: does NOT trigger conversion when action=cancel
- POST /panic-sell: does NOT trigger conversion when no target_currency
- GET  /panic-sell-status/{task_id}: returns progress dict
- GET  /panic-sell-status/{task_id}: 404 for unknown task
- Cancelled positions: already excluded from win rate (status="cancelled" vs "closed")
"""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

# Helper fixtures (mirror bot_control_router test pattern)
async def _make_user(db): ...
async def _make_account(db, user): ...
async def _make_bot(db, account, is_active=True): ...
async def _make_position(db, bot, status="open"): ...
async def _make_bot_rebalancer_group(db, account, enabled=True): ...


class TestPanicSellRequiresConfirm:
    async def test_confirm_false_raises_400(self, db_session): ...

class TestPanicSellAuth:
    async def test_wrong_account_raises_403(self, db_session): ...

class TestPanicSellCancel:
    async def test_cancels_all_open_positions(self, db_session): ...
    async def test_does_not_affect_already_closed_positions(self, db_session): ...
    async def test_returns_task_id(self, db_session): ...
    async def test_no_positions_completes_cleanly(self, db_session): ...

class TestPanicSellBotStopping:
    async def test_stops_active_bots_when_requested(self, db_session): ...
    async def test_leaves_bots_active_when_stop_bots_false(self, db_session): ...
    async def test_accumulates_running_seconds_for_active_bots(self, db_session): ...

class TestPanicSellRebalancers:
    async def test_disables_portfolio_rebalancer(self, db_session): ...
    async def test_disables_bot_rebalancer_groups(self, db_session): ...
    async def test_respects_stop_portfolio_rebalancer_false(self, db_session): ...

class TestPanicSellConversion:
    async def test_triggers_conversion_when_sell_with_target(self, db_session): ...
    async def test_no_conversion_on_cancel_action(self, db_session): ...
    async def test_no_conversion_when_no_target_currency(self, db_session): ...

class TestPanicSellStatus:
    async def test_status_endpoint_returns_progress(self, db_session): ...
    async def test_status_404_for_unknown_task(self, db_session): ...

class TestWinRateExclusion:
    def test_cancelled_positions_excluded_from_win_rate(self): ...
    # Verifies bot_stats_service.py: closed_positions = [p for p in all if p.status == "closed"]
```

**Key mock patterns to follow** (`test_bot_control_router.py`):
```python
# Direct function calls, not HTTP client
from app.position_routers.panic_sell_router import panic_sell, _execute_panic_sell

# Mock exchange
mock_exchange = MagicMock()
mock_exchange.get_current_price = AsyncMock(return_value=50000.0)
mock_exchange.create_market_order = AsyncMock(return_value={"order_id": "test"})

@patch("app.position_routers.panic_sell_router.get_exchange_client_for_account",
       new_callable=AsyncMock, return_value=mock_exchange)

# For background task testing, run _execute_panic_sell directly (not via BackgroundTasks)
await _execute_panic_sell(db_session, task_id, account_id, "cancel", None, True, True, True, user.id)
```

### Task 5: Frontend — API service

**File**: `frontend/src/services/api.ts`

Add to `positionsApi`:
```typescript
panicSell: (request: {
  account_id: number
  action: 'cancel' | 'sell'
  target_currency?: 'USD' | 'USDC' | 'USDT' | 'BTC' | 'ETH'
  stop_bots?: boolean
  stop_portfolio_rebalancer?: boolean
  stop_bot_rebalancer?: boolean
  confirm: boolean
}) =>
  api.post<{ task_id: string; message: string; status_url: string }>(
    '/positions/panic-sell',
    request
  ).then((res) => res.data),

panicSellStatus: (taskId: string) =>
  api.get<{
    task_id: string
    status: 'running' | 'completed' | 'failed'
    phase: string
    message: string
    bots_stopped: number
    positions_total: number
    positions_current: number
    positions_acted: number
    positions_failed: number
    portfolio_rebalancer_stopped: boolean
    bot_rebalancer_groups_stopped: number
    conversion_task_id: string | null
    conversion_status_url: string | null
    progress_pct: number
    errors: string[]
    started_at: string
    completed_at: string | null
  }>(`/positions/panic-sell-status/${taskId}`).then((res) => res.data),
```

### Task 6: PanicSellModal component (NEW)

**File**: `frontend/src/components/PanicSellModal.tsx`

Multi-step modal using existing UI patterns. Key design:

```tsx
type Step = 'configure' | 'confirm' | 'progress' | 'done'

interface PanicSellModalProps {
  isOpen: boolean
  onClose: () => void
  accountId: number
}

const CURRENCIES = ['USD', 'USDC', 'USDT', 'BTC', 'ETH'] as const
```

**Step 1 — Configure** (choose action, currency, options):
- Red warning banner at top: "⚠️ Emergency Liquidation"
- Radio: Cancel All Deals / Sell All at Market
- If "Sell": currency grid (5 buttons: USD USDC USDT BTC ETH)
  - Note below: "Positions close to their quote currency first. Free balances are then converted to {target}. Assets without a direct {target} pair go through an intermediate pair automatically."
- Checkboxes: Stop all bots / Stop portfolio rebalancer / Stop bot rebalancer groups
- [Next →] button

**Step 2 — Confirm** (summary + type CONFIRM):
- Summary box showing what will happen
- Text input: "Type CONFIRM to proceed"
- [← Back] [🚨 Execute Panic Sell] (disabled until "CONFIRM" typed)

**Step 3 — Progress** (live polling):
```tsx
// Poll every 1.5s while status === "running"
const { data: progress } = useQuery({
  queryKey: ['panic-sell-status', taskId],
  queryFn: () => positionsApi.panicSellStatus(taskId!),
  enabled: !!taskId && status === 'running',
  refetchInterval: 1500,
  refetchIntervalInBackground: false,
})
```

Progress display:
```
Phase indicators (with checkmarks when done):
  [✓] Stopping bots
  [●] Closing positions  [████████░░] 8/10
  [ ] Disabling rebalancer
  [ ] Converting portfolio

Current message: "Selling 8/10..."
Errors (if any): collapsible list
```

**Step 4 — Done** (summary):
- ✓ X bots stopped
- ✓ X positions cancelled/sold (Y failed)
- ✓ Rebalancer disabled / kept
- ✓ Portfolio conversion started → [View Progress] (links to conversion status)
- [Close]

**Error handling**:
- If `status === "failed"`: show error message in red, allow retry (close + reopen)
- Per-position errors: show in collapsible "X errors" section

**Styling guide** (follow existing patterns):
- Red accent for danger: `bg-red-500/20 border-red-500/30 text-red-400`
- Progress bar: `bg-slate-700 rounded-full` with `bg-red-500 h-2` fill
- Modal backdrop: `fixed inset-0 bg-black/50 z-50 flex items-center justify-center`
- Card: `bg-slate-800 border border-slate-700 rounded-xl w-full max-w-md mx-4 p-6`
- Button (danger): `bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg font-semibold disabled:opacity-50 disabled:cursor-not-allowed`

### Task 7: Wire button into Positions.tsx

**File**: `frontend/src/pages/Positions.tsx`

Add to imports:
```tsx
import { PanicSellModal } from '../components/PanicSellModal'
```

Add state:
```tsx
const [showPanicSell, setShowPanicSell] = useState(false)
```

Add button in header (line ~283, inside `flex items-center gap-2 flex-wrap`):
```tsx
{canWritePositions && openPositions.length > 0 && selectedAccount && (
  <button
    onClick={() => setShowPanicSell(true)}
    className="flex items-center gap-1.5 bg-red-600/20 hover:bg-red-600/40 text-red-400 hover:text-red-300 border border-red-500/30 px-3 py-1 rounded-full text-sm font-medium transition-colors"
  >
    <span>🚨</span>
    <span>Panic Sell</span>
  </button>
)}

{showPanicSell && selectedAccount && (
  <PanicSellModal
    isOpen={showPanicSell}
    onClose={() => setShowPanicSell(false)}
    accountId={selectedAccount.id}
  />
)}
```

### Task 8: Write frontend tests

**File**: `frontend/src/components/PanicSellModal.test.tsx`

```typescript
describe('PanicSellModal', () => {
  test('renders action choice on first step')
  test('shows currency selector after choosing sell')
  test('does not show currency selector for cancel action')
  test('requires typing CONFIRM to enable submit')
  test('calls positionsApi.panicSell with correct params on submit')
  test('shows progress phase indicator after submission')
  test('shows completion summary when status is completed')
  test('shows error state when status is failed')
  test('close button dismisses modal')
})
```

Mocks needed:
```typescript
vi.mock('../services/api', () => ({
  positionsApi: {
    panicSell: vi.fn().mockResolvedValue({ task_id: 'test-task-123', message: 'ok', status_url: '...' }),
    panicSellStatus: vi.fn().mockResolvedValue({ status: 'completed', ... }),
  },
}))
```

---

## Gotchas & Notes

### Intermediate Pair Routing
The `portfolio_conversion_service._sell_currency_with_fallback` already handles the case where a direct pair doesn't exist (e.g., `SOL-USDC` might not trade). It falls back to `SOL-USD` and then converts USD → USDC. The user explicitly asked for this. The extension to USDC/USDT/ETH follows this exact pattern.

### exit_reason = "manual" MUST be set before execute_sell
See `position_actions_router.py` line 137. The `StrategyTradingEngine.execute_sell()` does not automatically set `exit_reason`. Setting it before the call ensures panic-sold positions are excluded from the win rate denominator (`bot_stats_service.py` line 147: `[p for p in closed_positions if p.exit_reason != "manual"]`).

### Cancelled positions already excluded from win rate
`bot_crud_router.py` line 262: `closed_positions = [p for p in all_positions if p.status == "closed"]`. Status "cancelled" is not "closed", so they're already excluded. Include a test that documents/verifies this invariant.

### Auto-buy BTC fields
`Account.auto_buy_enabled` (Boolean) — set to False to disable.
`Account.auto_buy_usd_enabled`, `auto_buy_usdc_enabled`, `auto_buy_usdt_enabled` — also set False.

### Minimum balance reserves
Five fields on Account: `min_balance_usd`, `min_balance_btc`, `min_balance_eth`, `min_balance_usdc`, `min_balance_usdt` — set all to 0.0.

### asyncio.ensure_future for conversion task
When running inside a FastAPI BackgroundTask (which runs in the main asyncio event loop), use `asyncio.ensure_future()` to fire the conversion coroutine without waiting for it.

### PostgreSQL schema — BotRebalancerGroup
`BotRebalancerGroup` is in schema `trading`. All FK queries must be schema-qualified (already handled by SQLAlchemy model `__table_args__ = {'schema': 'trading'}`).

### Test setup
The `tests/position_routers/` directory may not exist yet. Check if `tests/position_routers/__init__.py` needs to be created. Mirror the structure from `tests/bot_routers/`.

### Frontend: Don't re-mount QueryClient between steps
Pass the same `queryClient` context through all steps so the polling query for panic-sell-status works correctly.

### Modal blocking
During step 3 (progress), the modal should NOT be closeable via backdrop click or X button. Only show Close after status is "completed" or "failed".

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `backend/app/services/portfolio_conversion_service.py` | MODIFY — add USDC/USDT/ETH support |
| `backend/app/routers/account_router.py` | MODIFY — update target_currency validation |
| `backend/app/position_routers/panic_sell_router.py` | **CREATE** |
| `backend/app/routers/positions_router.py` | MODIFY — register panic_sell_router |
| `backend/tests/position_routers/__init__.py` | CREATE (empty, if needed) |
| `backend/tests/position_routers/test_panic_sell_router.py` | **CREATE** |
| `frontend/src/services/api.ts` | MODIFY — add panicSell + panicSellStatus |
| `frontend/src/components/PanicSellModal.tsx` | **CREATE** |
| `frontend/src/components/PanicSellModal.test.tsx` | **CREATE** |
| `frontend/src/pages/Positions.tsx` | MODIFY — add panic button + modal |

---

## Validation Gates

```bash
# ── Backend: TDD cycle ──────────────────────────────────────────────────────
cd /home/ec2-user/ZenithGrid/backend

# Run failing tests first (TDD red state)
./venv/bin/python3 -m pytest tests/position_routers/test_panic_sell_router.py -v

# After implementation — all should pass
./venv/bin/python3 -m pytest tests/position_routers/test_panic_sell_router.py -v

# Regression: existing position and bot control tests unchanged
./venv/bin/python3 -m pytest tests/position_routers/ tests/routers/test_bot_control_router.py -v

# Lint
./venv/bin/python3 -m flake8 \
  app/position_routers/panic_sell_router.py \
  app/services/portfolio_conversion_service.py \
  app/routers/account_router.py \
  app/routers/positions_router.py \
  --max-line-length=120

# ── Frontend ────────────────────────────────────────────────────────────────
cd /home/ec2-user/ZenithGrid/frontend

# Unit tests
npx vitest run src/components/PanicSellModal.test.tsx

# Regression: existing position filter tests still pass
npx vitest run src/pages/positions/hooks/

# TypeScript check
./node_modules/.bin/tsc --noEmit
```

---

## PRP Score

**9/10** — All patterns are well-understood from existing code. The main complexity is the multi-phase background task with live polling (modelled directly on `portfolio_conversion_service.py`) and the multi-step modal (modelled on existing BotListItem confirm patterns extended to a full wizard). The intermediate-pair routing for USDC/USDT/ETH follows the existing fallback pattern exactly. Only risk: Coinbase pair availability for `USDC-USD`, `USDT-USD` buy orders — if these don't behave as standard market orders, the conversion step may need a fallback. Scoped to handle gracefully with per-currency error tracking.
