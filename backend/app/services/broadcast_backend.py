"""
BroadcastBackend abstraction — Phase 2.5 / Phase 3 of the scalability roadmap.

Puts a protocol in front of WebSocketManager's fan-out methods so that
Phase 3 (multi-process) can swap InProcessBroadcast for RedisBroadcast
without touching any publisher code.

ws_manager remains the connection registry (connect/disconnect/sweep).
BroadcastBackend is the fan-out layer only.

Usage (new code should use this, not ws_manager directly for broadcasts):
    from app.services.broadcast_backend import broadcast_backend
    await broadcast_backend.send_to_user(user_id, {"type": "order_fill", ...})
    await broadcast_backend.broadcast_order_fill(event)
"""

from __future__ import annotations

import json
import logging
from typing import Optional, Protocol, runtime_checkable

from app.services.websocket_manager import OrderFillEvent, WebSocketManager, ws_manager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol — the interface any backend must satisfy
# ---------------------------------------------------------------------------

@runtime_checkable
class BroadcastBackend(Protocol):
    """Fan-out abstraction over WebSocket connections.

    Implementations:
    - InProcessBroadcast: delegates to WebSocketManager (single process, today)
    - RedisBroadcast:     publishes to Redis channel (multi-process, Phase 3)
    """

    async def broadcast(self, message: dict, user_id: Optional[int] = None) -> None:
        """Broadcast to all connected clients, or to one user if user_id given."""
        ...

    async def send_to_user(self, user_id: int, message: dict) -> None:
        """Send a message to all connections belonging to user_id."""
        ...

    async def send_to_room(
        self,
        player_ids: set,
        message: dict,
        exclude_user: Optional[int] = None,
    ) -> None:
        """Send a message to all players in a room (game lobby/spectator)."""
        ...

    async def broadcast_order_fill(self, event: OrderFillEvent) -> None:
        """Broadcast an order fill notification to the owning user."""
        ...


# ---------------------------------------------------------------------------
# In-process implementation — wraps WebSocketManager, zero behavior change
# ---------------------------------------------------------------------------

class InProcessBroadcast:
    """BroadcastBackend backed by the in-process WebSocketManager.

    All calls delegate 1-to-1 to ws_manager. The manager is injected so
    that tests can pass a mock without patching globals.
    """

    def __init__(self, manager: WebSocketManager) -> None:
        self._manager = manager

    async def broadcast(self, message: dict, user_id: Optional[int] = None) -> None:
        await self._manager.broadcast(message, user_id=user_id)

    async def send_to_user(self, user_id: int, message: dict) -> None:
        await self._manager.send_to_user(user_id, message)

    async def send_to_room(
        self,
        player_ids: set,
        message: dict,
        exclude_user: Optional[int] = None,
    ) -> None:
        await self._manager.send_to_room(player_ids, message, exclude_user=exclude_user)

    async def broadcast_order_fill(self, event: OrderFillEvent) -> None:
        await self._manager.broadcast_order_fill(event)


# ---------------------------------------------------------------------------
# Redis stub — documented seam for Phase 3 multi-process deployment
# ---------------------------------------------------------------------------

class RedisBroadcast:
    """BroadcastBackend backed by Redis pub/sub.

    Each method publishes a JSON payload to a Redis channel. A per-process
    subscriber task (started in main.py lifespan) receives messages and
    dispatches them to the local WebSocketManager.

    Channel scheme:
        ws:user:{user_id}  — direct message to one user
        ws:broadcast       — fan-out to all (user_id=None) or filtered (user_id=int)
        ws:room            — room message with player_ids list
    """

    async def broadcast(self, message: dict, user_id: Optional[int] = None) -> None:
        from app.redis_client import get_redis
        redis = await get_redis()
        if user_id is not None:
            channel = f"ws:user:{user_id}"
            payload = json.dumps({"message": message})
        else:
            channel = "ws:broadcast"
            payload = json.dumps({"message": message, "user_id": None})
        await redis.publish(channel, payload)

    async def send_to_user(self, user_id: int, message: dict) -> None:
        from app.redis_client import get_redis
        redis = await get_redis()
        await redis.publish(f"ws:user:{user_id}", json.dumps({"message": message}))

    async def send_to_room(
        self,
        player_ids: set,
        message: dict,
        exclude_user: Optional[int] = None,
    ) -> None:
        from app.redis_client import get_redis
        redis = await get_redis()
        payload = json.dumps({
            "message": message,
            "player_ids": list(player_ids),
            "exclude_user": exclude_user,
        })
        await redis.publish("ws:room", payload)

    async def broadcast_order_fill(self, event: OrderFillEvent) -> None:
        from app.redis_client import get_redis
        redis = await get_redis()
        payload = json.dumps({
            "type": "order_fill",
            "fill_type": event.fill_type,
            "product_id": event.product_id,
            "base_amount": event.base_amount,
            "quote_amount": event.quote_amount,
            "price": event.price,
            "position_id": event.position_id,
            "profit": event.profit,
            "profit_percentage": event.profit_percentage,
            "is_paper_trading": event.is_paper_trading,
            "user_id": event.user_id,
        })
        await redis.publish(f"ws:user:{event.user_id}", payload)


# ---------------------------------------------------------------------------
# Subscriber routing — called by the per-process subscriber loop in main.py
# ---------------------------------------------------------------------------

async def route_redis_message(channel: str, raw: str, manager: WebSocketManager) -> None:
    """Dispatch an incoming Redis pub/sub message to the local WebSocketManager.

    Called by the subscriber background task for every message received.
    Errors are logged and swallowed so one bad message doesn't kill the loop.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Redis subscriber: invalid JSON on channel %s", channel)
        return

    try:
        if channel.startswith("ws:user:"):
            user_id = int(channel.split(":")[-1])
            msg = data.get("message") or data  # order_fill payloads have no "message" key
            await manager.send_to_user(user_id, msg)

        elif channel == "ws:broadcast":
            await manager.broadcast(data["message"], user_id=data.get("user_id"))

        elif channel == "ws:room":
            await manager.send_to_room(
                set(data["player_ids"]),
                data["message"],
                exclude_user=data.get("exclude_user"),
            )

    except Exception:
        logger.exception("Redis subscriber: error routing message on channel %s", channel)


# ---------------------------------------------------------------------------
# Module-level singleton — same pattern as ws_manager and event_bus
# ---------------------------------------------------------------------------

broadcast_backend: BroadcastBackend = InProcessBroadcast(ws_manager)
