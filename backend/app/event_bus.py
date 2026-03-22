"""
In-process event bus for ZenithGrid domain events.

Phase 2.3 of the scalability roadmap — establishes the pub/sub seam that enables
future extraction of services. Today: asyncio fan-out in a single process.
Future: swap InProcessEventBus for NATSEventBus or RedisEventBus without
changing any subscriber or publisher code.

Usage:
    # Publisher (always best-effort, inside try/except):
    from app.event_bus import event_bus, ORDER_FILLED, OrderFilledPayload
    await event_bus.publish(ORDER_FILLED, OrderFilledPayload(...))

    # Subscriber (wire in startup_event, not at module level):
    event_bus.subscribe(ORDER_FILLED, my_async_handler)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
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
    fill_type: str          # base_order | dca_order | sell_order | partial_fill | close_short
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
# In-process pub/sub implementation
# ---------------------------------------------------------------------------

class InProcessEventBus:
    """
    In-process asyncio pub/sub event bus.

    - publish() is non-blocking: schedules handler tasks via asyncio.create_task()
      and returns immediately. The caller never waits for subscribers.
    - Handler exceptions are caught and logged — a broken subscriber never
      affects the publisher or other subscribers.
    - Requires a running asyncio event loop (all ZenithGrid call sites are async).

    Future: replace with NATSEventBus or RedisEventBus by swapping the
    module-level singleton in startup_event() — no publisher/subscriber changes needed.
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
                "Event bus handler '%s' raised an exception for topic='%s'",
                getattr(handler, "__name__", repr(handler)),
                topic,
            )


# ---------------------------------------------------------------------------
# Module-level singleton — same pattern as ws_manager
# ---------------------------------------------------------------------------

event_bus = InProcessEventBus()
