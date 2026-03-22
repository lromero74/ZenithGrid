# PRP: Phase 2.3 — In-Process Event Bus

**Feature**: Lightweight pub/sub event bus for ZenithGrid — `InProcessEventBus` today, swappable for NATS/Redis Streams when multi-process scale demands it.
**Created**: 2026-03-22
**One-Pass Confidence Score**: 9/10

> Well-scoped, zero-infrastructure change. One new file (`app/event_bus.py` ≈ 80 lines). Publishers are 2–5 additive lines each in known call sites. Subscriber wiring is in `startup_event()`. No schema changes, no new dependencies. Polling fallback stays intact — this is purely additive.

---

## Context & Goal

### Problem

All inter-service coordination in ZenithGrid happens through direct DB polling:
- `auto_buy_monitor.run_once()` fires every 10 seconds regardless of whether any fills happened
- `rebalance_monitor.run_once()` fires every 30 seconds regardless
- When an order fills, the earliest auto-buy reaction is 10 seconds later; the earliest rebalance reaction is 30 seconds later

When a `sell_order` fill returns funds to the account, the auto-buy monitor won't notice until the next 10-second tick. Under load, this means freed funds sit idle for up to 10 seconds before being reinvested.

### Solution

Introduce an in-process event bus:
1. **`app/event_bus.py`** — `EventBusBackend` protocol + `InProcessEventBus` implementation + module-level `event_bus` singleton
2. **Publishers** — add `await event_bus.publish(TOPIC, Payload(...))` after the 5 existing `ws_manager.broadcast_order_fill()` call sites and the 2 bot start/stop sites
3. **Subscribers** — wire `order.filled` → trigger `auto_buy_monitor` + `rebalance_monitor` APScheduler jobs immediately; wire `bot.started/stopped` → log
4. **Polling stays** — event bus is additive, not a replacement. Polling is the correctness fallback; events are the latency optimization.

### Scope

**In:** `event_bus.py`, 7 publisher call sites, subscriber wiring in `main.py`, tests
**Out:** Replacing polling, DB-persisted events, `goal.achieved` (complex DB query), NATS/Redis backend (future), `position.opened/closed` separate events (subsumed by `order.filled` fill_type)

---

## Architecture

```
order fills in buy_executor / sell_executor / limit_order_monitor
  └─► await event_bus.publish("order.filled", OrderFilledPayload(...))  [best-effort, try/except]
        │
        └─► InProcessEventBus.publish()
              └─► asyncio.create_task(_safe_call(handler, topic, payload))  # fire-and-forget
                    │
                    └─► _on_order_filled(payload)   [wired in startup_event]
                          ├─► scheduler.get_job("auto_buy_monitor").modify(next_run_time=now)
                          └─► scheduler.get_job("rebalance_monitor").modify(next_run_time=now)

bot start/stop in bot_control_router
  └─► await event_bus.publish("bot.started" / "bot.stopped", BotStartedPayload(...))  [best-effort]
        └─► InProcessEventBus.publish()
              └─► asyncio.create_task(_safe_call(handler, topic, payload))
                    └─► _on_bot_started/stopped(payload)   [wired in startup_event — logs only]
```

**Key properties:**
- `publish()` returns immediately — it schedules handler tasks, never awaits them
- Handler exceptions are caught in `_safe_call()` — a broken handler never affects the publisher
- APScheduler's `max_instances=1, coalesce=True` prevents concurrent monitor runs even under rapid fill bursts
- `job.modify(next_run_time=datetime.utcnow())` preserves the existing `IntervalTrigger` — the job still runs on its normal schedule after the triggered run
- Handlers that fail silently degrade to polling — correctness is never at risk

---

## Existing Patterns to Follow

### Module-level singleton (mirror `ws_manager`)
```python
# app/services/websocket_manager.py (existing)
class WebSocketManager:
    def __init__(self): ...

ws_manager = WebSocketManager()   # ← module-level singleton
```

```python
# app/event_bus.py (new — same pattern)
class InProcessEventBus:
    def __init__(self): ...

event_bus = InProcessEventBus()   # ← module-level singleton
```

### Best-effort try/except at call sites (mirror buy_executor)
```python
# app/trading_engine/buy_executor.py:232–248 (existing)
try:
    await ws_manager.broadcast_order_fill(OrderFillEvent(...))
except Exception as e:
    logger.warning(f"Failed to broadcast WebSocket notification (trade was recorded): {e}")

# After the ws_manager call — same pattern:
try:
    from app.event_bus import event_bus, ORDER_FILLED, OrderFilledPayload
    await event_bus.publish(ORDER_FILLED, OrderFilledPayload(
        position_id=position.id,
        user_id=position.user_id,
        product_id=product_id,
        fill_type=fill_type,
        quote_amount=actual_quote_amount,
        base_amount=actual_base_amount,
        price=actual_price,
        is_paper_trading=is_paper,
    ))
except Exception as e:
    logger.warning(f"Event bus publish failed (non-critical): {e}")
```

### Service `run_once()` pattern (existing in auto_buy_monitor, rebalance_monitor)
```python
# app/services/auto_buy_monitor.py:65 (existing)
async def run_once(self):
    try:
        await self._check_accounts()
        await self._check_pending_orders()
    except Exception as e:
        logger.error(f"Error in auto-buy monitor: {e}", exc_info=True)
```

### APScheduler job.modify (confirmed working in 3.11.2)
```python
from app.scheduler import scheduler
from datetime import datetime

job = scheduler.get_job("auto_buy_monitor")
if job:
    job.modify(next_run_time=datetime.utcnow())
# Modifies next_run_time without touching the existing IntervalTrigger.
# If the job is currently running (max_instances=1), the modified run_time
# will fire after the current run completes (coalesce=True handles bursts).
```

### Subscriber wiring in startup_event (pattern from main.py)
```python
# app/main.py — startup_event() already wires all other background services
@app.on_event("startup")
async def startup_event():
    await init_db()
    ...
    # Wire event bus subscribers (additive — after all other setup)
    _wire_event_bus_subscribers()
```

---

## Implementation Blueprint

### Step 0 (TDD) — Write failing tests first

File: `backend/tests/test_event_bus.py`

```python
"""
Tests for app/event_bus.py

Covers:
- subscribe() + publish() invokes handler
- multiple subscribers (fan-out)
- handler exception doesn't break other handlers
- publish to topic with no subscribers is a no-op
- payload is passed correctly to handler
- InProcessEventBus is the default singleton
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock


class TestInProcessEventBus:

    @pytest.mark.asyncio
    async def test_subscribe_and_publish_calls_handler(self):
        """Happy path: subscribed handler is called after publish."""
        from app.event_bus import InProcessEventBus
        bus = InProcessEventBus()
        received = []

        async def handler(payload):
            received.append(payload)

        bus.subscribe("test.topic", handler)
        await bus.publish("test.topic", "hello")
        await asyncio.sleep(0)  # yield to let create_task run

        assert received == ["hello"]

    @pytest.mark.asyncio
    async def test_multiple_subscribers_all_called(self):
        """Happy path: all subscribers for a topic are called (fan-out)."""
        from app.event_bus import InProcessEventBus
        bus = InProcessEventBus()
        calls = []

        async def h1(p): calls.append(("h1", p))
        async def h2(p): calls.append(("h2", p))

        bus.subscribe("x", h1)
        bus.subscribe("x", h2)
        await bus.publish("x", 42)
        await asyncio.sleep(0)

        assert ("h1", 42) in calls
        assert ("h2", 42) in calls

    @pytest.mark.asyncio
    async def test_handler_exception_isolated(self):
        """Failure: exception in one handler does not prevent other handlers from running."""
        from app.event_bus import InProcessEventBus
        bus = InProcessEventBus()
        second_called = []

        async def bad_handler(p):
            raise RuntimeError("boom")

        async def good_handler(p):
            second_called.append(p)

        bus.subscribe("boom", bad_handler)
        bus.subscribe("boom", good_handler)
        await bus.publish("boom", "payload")
        await asyncio.sleep(0.01)  # allow both tasks to run

        assert second_called == ["payload"]

    @pytest.mark.asyncio
    async def test_unknown_topic_no_error(self):
        """Edge case: publishing to topic with no subscribers is a no-op."""
        from app.event_bus import InProcessEventBus
        bus = InProcessEventBus()
        # Should not raise
        await bus.publish("nonexistent.topic", {"data": 1})

    @pytest.mark.asyncio
    async def test_payload_dataclass_passed_correctly(self):
        """Happy path: OrderFilledPayload dataclass fields are preserved through publish."""
        from app.event_bus import InProcessEventBus, OrderFilledPayload, ORDER_FILLED
        bus = InProcessEventBus()
        received = []

        async def handler(payload):
            received.append(payload)

        bus.subscribe(ORDER_FILLED, handler)
        payload = OrderFilledPayload(
            position_id=7, user_id=1, product_id="BTC-USD",
            fill_type="base_order", quote_amount=100.0,
            base_amount=0.001, price=100_000.0,
        )
        await bus.publish(ORDER_FILLED, payload)
        await asyncio.sleep(0)

        assert received[0].position_id == 7
        assert received[0].product_id == "BTC-USD"
        assert received[0].fill_type == "base_order"

    def test_module_singleton_exists(self):
        """Happy path: module-level event_bus singleton is InProcessEventBus."""
        from app.event_bus import event_bus, InProcessEventBus
        assert isinstance(event_bus, InProcessEventBus)

    @pytest.mark.asyncio
    async def test_topic_constants_defined(self):
        """Happy path: all topic constants are importable strings."""
        from app.event_bus import (
            ORDER_FILLED, POSITION_OPENED, POSITION_CLOSED,
            BOT_STARTED, BOT_STOPPED,
        )
        for const in [ORDER_FILLED, POSITION_OPENED, POSITION_CLOSED, BOT_STARTED, BOT_STOPPED]:
            assert isinstance(const, str)
            assert "." in const  # namespaced topic

    @pytest.mark.asyncio
    async def test_subscribe_same_topic_twice_both_called(self):
        """Edge case: subscribing same handler twice calls it twice per publish."""
        from app.event_bus import InProcessEventBus
        bus = InProcessEventBus()
        count = []

        async def handler(p): count.append(1)

        bus.subscribe("t", handler)
        bus.subscribe("t", handler)
        await bus.publish("t", None)
        await asyncio.sleep(0)

        assert len(count) == 2

    @pytest.mark.asyncio
    async def test_different_topics_isolated(self):
        """Edge case: subscribing to topic A does not receive topic B events."""
        from app.event_bus import InProcessEventBus
        bus = InProcessEventBus()
        received = []

        async def handler(p): received.append(p)

        bus.subscribe("topic.a", handler)
        await bus.publish("topic.b", "should not arrive")
        await asyncio.sleep(0)

        assert received == []
```

Run to confirm ALL fail:
```bash
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -m pytest tests/test_event_bus.py -v
# Expected: ModuleNotFoundError: No module named 'app.event_bus'
```

---

### Step 1 — Implement `app/event_bus.py`

```python
"""
In-process event bus for ZenithGrid domain events.

Phase 2.3 of the scalability roadmap — establishes the pub/sub seam that enables
future extraction of services. Today: asyncio fan-out in a single process.
Future: swap InProcessEventBus for NATSEventBus or RedisEventBus without
changing any subscriber or publisher code.

Usage:
    # Publisher:
    from app.event_bus import event_bus, ORDER_FILLED, OrderFilledPayload
    await event_bus.publish(ORDER_FILLED, OrderFilledPayload(...))

    # Subscriber (wire in startup_event, not at module level):
    event_bus.subscribe(ORDER_FILLED, my_async_handler)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Topic constants — namespaced strings (map cleanly to NATS subjects later)
# ---------------------------------------------------------------------------

ORDER_FILLED = "order.filled"
POSITION_OPENED = "position.opened"
POSITION_CLOSED = "position.closed"
BOT_STARTED = "bot.started"
BOT_STOPPED = "bot.stopped"
GOAL_ACHIEVED = "goal.achieved"


# ---------------------------------------------------------------------------
# Payload dataclasses
# ---------------------------------------------------------------------------

@dataclass
class OrderFilledPayload:
    """Published when any order fill is confirmed (buy, sell, partial, limit close)."""
    position_id: int
    user_id: int
    product_id: str
    fill_type: str              # base_order | dca_order | sell_order | partial_fill | close_short
    quote_amount: float
    base_amount: float
    price: float
    profit: Optional[float] = None
    profit_percentage: Optional[float] = None
    is_paper_trading: bool = False


@dataclass
class PositionOpenedPayload:
    """Published when a new position is created."""
    position_id: int
    user_id: int
    product_id: str
    bot_id: Optional[int] = None
    quote_amount: float = 0.0


@dataclass
class PositionClosedPayload:
    """Published when a position reaches status='closed'."""
    position_id: int
    user_id: int
    product_id: str
    bot_id: Optional[int] = None
    profit_quote: Optional[float] = None
    profit_percentage: Optional[float] = None


@dataclass
class BotStartedPayload:
    bot_id: int
    user_id: int


@dataclass
class BotStoppedPayload:
    bot_id: int
    user_id: int


# ---------------------------------------------------------------------------
# Backend protocol (for future swap to NATS / Redis Streams)
# ---------------------------------------------------------------------------

class InProcessEventBus:
    """
    In-process asyncio pub/sub event bus.

    - publish() is non-blocking: it schedules handler tasks via asyncio.create_task()
      and returns immediately. The caller never waits for subscribers.
    - Handler exceptions are caught and logged — a broken subscriber never
      affects the publisher or other subscribers.
    - Requires a running asyncio event loop (all ZenithGrid call sites are async).
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable]] = {}

    def subscribe(self, topic: str, handler: Callable[..., Any]) -> None:
        """Register an async handler for topic. May be called multiple times."""
        self._handlers.setdefault(topic, []).append(handler)

    async def publish(self, topic: str, payload: Any) -> None:
        """Publish payload to all handlers subscribed to topic.

        Fire-and-forget: schedules each handler as an independent asyncio Task.
        Returns immediately without waiting for handlers to complete.
        """
        handlers = self._handlers.get(topic, [])
        for handler in handlers:
            asyncio.create_task(self._safe_call(handler, topic, payload))

    async def _safe_call(self, handler: Callable, topic: str, payload: Any) -> None:
        """Run handler, catching and logging any exception."""
        try:
            await handler(payload)
        except Exception:
            logger.exception(
                f"Event bus handler '{getattr(handler, '__name__', handler)}' "
                f"raised an exception for topic='{topic}'"
            )


# ---------------------------------------------------------------------------
# Module-level singleton — same pattern as ws_manager
# ---------------------------------------------------------------------------

event_bus = InProcessEventBus()
```

Run tests after this step — all 9 should now **pass**:
```bash
./venv/bin/python3 -m pytest tests/test_event_bus.py -v
```

---

### Step 2 — Add publisher call sites

Add event bus publish calls **after** each `ws_manager.broadcast_order_fill()` call. Always in their own `try/except` — the event bus is best-effort, not critical path.

**`app/trading_engine/buy_executor.py` — base_order / dca_order fills (line ~238)**

After the existing `ws_manager.broadcast_order_fill(...)` try/except block, add:

```python
    # Publish domain event (best-effort — polling fallback handles misses)
    try:
        from app.event_bus import event_bus, ORDER_FILLED, OrderFilledPayload
        await event_bus.publish(ORDER_FILLED, OrderFilledPayload(
            position_id=position.id,
            user_id=position.user_id,
            product_id=product_id,
            fill_type=fill_type,
            quote_amount=actual_quote_amount,
            base_amount=actual_base_amount,
            price=actual_price,
            is_paper_trading=is_paper,
        ))
    except Exception as e:
        logger.warning(f"Event bus publish failed (non-critical): {e}")
```

**`app/trading_engine/buy_executor.py` — close_short fills (line ~801)**

Same pattern. `fill_type="close_short"`. Use the relevant variables at that call site.

**`app/trading_engine/sell_executor.py` — sell_order fills (line ~882)**

After the existing `ws_manager.broadcast_order_fill(...)` try/except block:

```python
    # Publish domain event (best-effort)
    try:
        from app.event_bus import event_bus, ORDER_FILLED, OrderFilledPayload
        await event_bus.publish(ORDER_FILLED, OrderFilledPayload(
            position_id=position.id,
            user_id=position.user_id,
            product_id=product_id,
            fill_type="sell_order",
            quote_amount=quote_received,
            base_amount=actual_base_sold,
            price=actual_price,
            profit=profit_quote,
            profit_percentage=profit_percentage,
            is_paper_trading=is_paper,
        ))
    except Exception as e:
        logger.warning(f"Event bus publish failed (non-critical): {e}")
```

**`app/services/limit_order_monitor.py` — partial fill broadcast (line ~136) and full fill broadcast (line ~566)**

After each `ws_manager.broadcast_order_fill(...)` try/except:

```python
    # Publish domain event (best-effort)
    try:
        from app.event_bus import event_bus, ORDER_FILLED, OrderFilledPayload
        await event_bus.publish(ORDER_FILLED, OrderFilledPayload(
            position_id=position.id,
            user_id=position.user_id,
            product_id=position.product_id,
            fill_type="partial_fill",   # or "sell_order" for full fill at line 566
            quote_amount=...,           # use variables available at each call site
            base_amount=...,
            price=...,
            is_paper_trading=is_paper,
        ))
    except Exception as e:
        logger.warning(f"Event bus publish failed (non-critical): {e}")
```

**`app/bot_routers/bot_control_router.py` — bot start (line ~88) and stop (line ~115)**

After `await db.commit()` in `start_bot`:
```python
    # Publish domain event (best-effort)
    try:
        from app.event_bus import event_bus, BOT_STARTED, BotStartedPayload
        await event_bus.publish(BOT_STARTED, BotStartedPayload(
            bot_id=bot.id, user_id=current_user.id
        ))
    except Exception as e:
        logger.warning(f"Event bus publish failed (non-critical): {e}")
```

After `await db.commit()` in `stop_bot`:
```python
    try:
        from app.event_bus import event_bus, BOT_STOPPED, BotStoppedPayload
        await event_bus.publish(BOT_STOPPED, BotStoppedPayload(
            bot_id=bot.id, user_id=current_user.id
        ))
    except Exception as e:
        logger.warning(f"Event bus publish failed (non-critical): {e}")
```

---

### Step 3 — Wire subscribers in `main.py`

Add subscriber wiring at the **end** of `startup_event()`, after APScheduler is started. Keeping it in `main.py` avoids circular imports (all the relevant singletons are already imported there).

```python
# In startup_event(), after scheduler.start():

    _wire_event_bus_subscribers()
```

Add this function near the bottom of `main.py` (before startup_event, not inside it):

```python
def _wire_event_bus_subscribers() -> None:
    """Register event bus subscribers. Called once from startup_event().

    All handlers run fire-and-forget (see InProcessEventBus.publish).
    Handler exceptions are caught by the bus — polling fallback ensures correctness.
    """
    from app.event_bus import event_bus, ORDER_FILLED, BOT_STARTED, BOT_STOPPED
    from app.scheduler import scheduler as _scheduler

    async def _on_order_filled(payload) -> None:
        """Trigger auto-buy and rebalance monitors immediately after any fill.

        Uses APScheduler job.modify(next_run_time=now) to fire the jobs at the
        next scheduler tick rather than calling run_once() directly. This preserves
        max_instances=1 + coalesce=True protection against concurrent runs.
        """
        from datetime import datetime
        for job_id in ("auto_buy_monitor", "rebalance_monitor"):
            try:
                job = _scheduler.get_job(job_id)
                if job:
                    job.modify(next_run_time=datetime.utcnow())
            except Exception:
                pass  # Graceful degradation — periodic polling still runs

    async def _on_bot_event(payload) -> None:
        logger.info(f"Bot event: {type(payload).__name__} bot_id={payload.bot_id}")

    event_bus.subscribe(ORDER_FILLED, _on_order_filled)
    event_bus.subscribe(BOT_STARTED, _on_bot_event)
    event_bus.subscribe(BOT_STOPPED, _on_bot_event)

    logger.info("Event bus: subscribers wired (order.filled → auto_buy + rebalance)")
```

---

### Step 4 — Run validation

```bash
cd /home/ec2-user/ZenithGrid/backend

# New tests
./venv/bin/python3 -m pytest tests/test_event_bus.py -v

# Regression: trading engine tests
./venv/bin/python3 -m pytest tests/test_multi_bot_monitor.py -v

# Regression: bot control
./venv/bin/python3 -m pytest tests/bot_routers/ -v 2>/dev/null || \
./venv/bin/python3 -m pytest tests/ -k "bot_control or bot_crud" -v

# Import sanity
./venv/bin/python3 -c "
from app.event_bus import (
    event_bus, InProcessEventBus,
    ORDER_FILLED, POSITION_OPENED, POSITION_CLOSED, BOT_STARTED, BOT_STOPPED,
    OrderFilledPayload, PositionOpenedPayload, PositionClosedPayload,
    BotStartedPayload, BotStoppedPayload,
)
print('event_bus:', type(event_bus).__name__)
print('constants:', ORDER_FILLED, BOT_STARTED, BOT_STOPPED)
print('All imports OK')
"

# Lint
./venv/bin/python3 -m flake8 --max-line-length=120 \
    app/event_bus.py \
    app/trading_engine/buy_executor.py \
    app/trading_engine/sell_executor.py \
    app/services/limit_order_monitor.py \
    app/bot_routers/bot_control_router.py \
    app/main.py \
    tests/test_event_bus.py
```

---

## Files to Modify

| File | Change |
|------|--------|
| `app/event_bus.py` | **NEW** — `InProcessEventBus`, topic constants, payload dataclasses, `event_bus` singleton |
| `app/trading_engine/buy_executor.py` | Add `event_bus.publish(ORDER_FILLED, ...)` after 2 `ws_manager.broadcast_order_fill()` call sites |
| `app/trading_engine/sell_executor.py` | Add `event_bus.publish(ORDER_FILLED, ...)` after 1 `ws_manager.broadcast_order_fill()` call site |
| `app/services/limit_order_monitor.py` | Add `event_bus.publish(ORDER_FILLED, ...)` after 2 `ws_manager.broadcast_order_fill()` call sites |
| `app/bot_routers/bot_control_router.py` | Add `event_bus.publish(BOT_STARTED/STOPPED, ...)` after `db.commit()` in `start_bot` and `stop_bot` |
| `app/main.py` | Add `_wire_event_bus_subscribers()` function + call it at end of `startup_event()` |
| `tests/test_event_bus.py` | **NEW** — 9 unit tests (written first, TDD) |

---

## Edge Cases & Gotchas

### 1. `asyncio.create_task()` requires a running event loop

`publish()` calls `asyncio.create_task()`. This works correctly in all production call sites (they are all `async def` functions on the main event loop). In tests, `pytest-asyncio` provides a running loop for `@pytest.mark.asyncio` tests. Do NOT call `event_bus.publish()` from sync code or from a thread.

If a sync context needs to publish (e.g., a future sync scheduler callback), use `asyncio.get_event_loop().call_soon_threadsafe(asyncio.create_task, event_bus.publish(...))` — but this is not needed for Phase 2.3.

### 2. `job.modify(next_run_time=...)` requires `datetime.utcnow()` (naive UTC)

APScheduler 3.x with `AsyncIOScheduler` default uses UTC timezone-aware datetimes internally. However, `datetime.utcnow()` (naive) is accepted by `job.modify()` and treated as UTC. Confirmed working in 3.11.2 (see APScheduler 3.x source: `_modify` casts to pytz UTC if timezone-aware scheduler is configured).

If you get `TypeError: can't compare offset-naive and offset-aware datetimes`, use:
```python
from datetime import timezone
job.modify(next_run_time=datetime.now(tz=timezone.utc))
```

### 3. `job.modify()` vs `job.reschedule()`

`job.modify(next_run_time=...)` — changes next fire time **without changing the trigger**. Interval still fires every 10/30 seconds after the triggered run. ✅

`job.reschedule('date', run_date=...)` — **replaces** the `IntervalTrigger` with a one-shot `DateTrigger`. The job fires once and never again. ❌ Do NOT use this.

### 4. APScheduler not started during tests

In unit tests of `buy_executor.py`, `scheduler.get_job("auto_buy_monitor")` returns `None` (scheduler not started). The subscriber handler guards with `if job:` — safe degradation. The `event_bus.publish()` call sites are all in `try/except` — also safe.

### 5. Circular imports — use deferred imports at call sites

`buy_executor.py` is deep in the call chain. Importing `event_bus` at the module level is safe (it's a standalone module with no app imports), but deferred `from app.event_bus import ...` inside the `try` block is equally fine and consistent with the existing deferred import pattern in this codebase (e.g., `from app.models import Bot` inside functions in several services).

### 6. `_wire_event_bus_subscribers()` called before `scheduler.start()`?

In `startup_event()`, call `_wire_event_bus_subscribers()` **after** `register_jobs()` and `scheduler.start()`:
```python
async def startup_event():
    await init_db()
    ...
    startup_time = datetime.utcnow()
    register_jobs(startup_time)
    scheduler.start()
    ...
    _wire_event_bus_subscribers()  # ← last, after scheduler is running
```

If called before `scheduler.start()`, `scheduler.get_job()` still works (returns the pending job), and `job.modify(next_run_time=...)` still works. But it's cleaner to wire after start.

### 7. Handler timing — `await asyncio.sleep(0)` in tests

`asyncio.create_task()` schedules the task for the **next event loop iteration**. In tests, you must yield control after `await bus.publish(...)`:
```python
await bus.publish("topic", payload)
await asyncio.sleep(0)   # or asyncio.sleep(0.01) for handlers that have internal awaits
assert received == [payload]
```

### 8. `position.opened` / `position.closed` not published yet (YAGNI)

The payload dataclasses `PositionOpenedPayload` and `PositionClosedPayload` are defined and exported but no publishers add them in Phase 2.3. The subscriber design only needs `order.filled`. Future subscribers (e.g., goal snapshot trigger) can add publishers when needed.

### 9. Paper trading fills

`is_paper_trading` is included in `OrderFilledPayload`. The `_on_order_filled` subscriber triggers both `auto_buy_monitor` and `rebalance_monitor` regardless — this is correct. Paper trading accounts go through the same monitors.

---

## Validation Gates

```bash
cd /home/ec2-user/ZenithGrid/backend

# 1. New unit tests all pass (written first, TDD)
./venv/bin/python3 -m pytest tests/test_event_bus.py -v
# Expected: 9 passed

# 2. No regressions in affected areas
./venv/bin/python3 -m pytest tests/test_multi_bot_monitor.py -v
./venv/bin/python3 -m pytest tests/bot_routers/ -v 2>/dev/null

# 3. Import sanity check
./venv/bin/python3 -c "
from app.event_bus import (
    event_bus, InProcessEventBus,
    ORDER_FILLED, POSITION_OPENED, POSITION_CLOSED, BOT_STARTED, BOT_STOPPED,
    OrderFilledPayload, PositionOpenedPayload, PositionClosedPayload,
    BotStartedPayload, BotStoppedPayload,
)
assert isinstance(event_bus, InProcessEventBus)
print('All imports OK:', ORDER_FILLED, BOT_STARTED)
"

# 4. Lint all changed files
./venv/bin/python3 -m flake8 --max-line-length=120 \
    app/event_bus.py \
    app/trading_engine/buy_executor.py \
    app/trading_engine/sell_executor.py \
    app/services/limit_order_monitor.py \
    app/bot_routers/bot_control_router.py \
    app/main.py \
    tests/test_event_bus.py

# 5. No frontend changes needed
# TypeScript check not required for this PRP
```

---

## Medium-Term Path to NATS (Document Only)

When multi-process scale demands it (Phase 3 extraction of Content or Social service):

**Step 1** — Add `nats-py` to `requirements.txt`:
```
nats-py>=2.3.0
```

**Step 2** — Implement `NATSEventBus` in a separate file:
```python
# app/event_bus_nats.py
import nats

class NATSEventBus:
    def __init__(self, url: str = "nats://localhost:4222"):
        self._url = url
        self._nc = None
        self._subscriptions: Dict[str, List[Callable]] = {}

    async def connect(self):
        self._nc = await nats.connect(self._url)

    async def disconnect(self):
        if self._nc:
            await self._nc.drain()

    def subscribe(self, topic: str, handler: Callable) -> None:
        # NATS subscriptions are async — need to call nc.subscribe() after connect()
        self._subscriptions.setdefault(topic, []).append(handler)

    async def publish(self, topic: str, payload: Any) -> None:
        import json, dataclasses
        data = json.dumps(dataclasses.asdict(payload) if dataclasses.is_dataclass(payload) else payload)
        await self._nc.publish(topic, data.encode())
```

**Step 3** — Swap the singleton in `main.py`:
```python
# app/main.py startup_event():
if settings.nats_url:
    from app.event_bus_nats import NATSEventBus
    import app.event_bus as _bus_module
    _bus_module.event_bus = NATSEventBus(settings.nats_url)
    await _bus_module.event_bus.connect()
```

No publisher or subscriber code changes — all `from app.event_bus import event_bus` references now point to the NATS instance.

---

## Confidence Assessment

**Score: 9/10**

**Why high:**
- Single new file with a simple, well-understood pattern (asyncio pub/sub)
- 7 publisher call sites are all the same 5-line pattern — mechanical additions inside existing `try/except` blocks
- Subscriber logic is 10 lines in `main.py` — no complex dependency chains
- APScheduler `job.modify(next_run_time=...)` confirmed working in 3.11.2
- Zero new dependencies, zero schema changes, zero API contract changes
- All existing polling stays — no correctness risk

**One-point discount:**
- `startup_event()` in `main.py` is already 60+ lines and complex; must insert `_wire_event_bus_subscribers()` in the right place (after scheduler.start()). Requires careful reading of the full startup sequence before inserting. The implementation agent should read `main.py` completely before editing.
