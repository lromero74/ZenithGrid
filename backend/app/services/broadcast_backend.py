"""
BroadcastBackend abstraction — Phase 2.5 of the scalability roadmap.

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
    """BroadcastBackend backed by Redis pub/sub (Phase 3).

    When ZenithGrid runs multiple backend workers, each process has its own
    WebSocketManager. Broadcasting to a user requires publishing to a shared
    Redis channel that ALL workers subscribe to. Each worker then delivers to
    locally-connected sockets.

    Architecture (Phase 3):
        Publisher → PUBLISH ws:user:{user_id} <message>
        Each worker subscribes: SUB ws:user:* → ws_manager.send_to_user()

    NOT IMPLEMENTED — raises NotImplementedError. Swap this in when Phase 3
    deploys multi-process uvicorn or adds a Celery/Dramatiq worker fleet.
    """

    async def broadcast(self, message: dict, user_id: Optional[int] = None) -> None:
        raise NotImplementedError("RedisBroadcast not yet implemented (Phase 3)")

    async def send_to_user(self, user_id: int, message: dict) -> None:
        raise NotImplementedError("RedisBroadcast not yet implemented (Phase 3)")

    async def send_to_room(
        self,
        player_ids: set,
        message: dict,
        exclude_user: Optional[int] = None,
    ) -> None:
        raise NotImplementedError("RedisBroadcast not yet implemented (Phase 3)")

    async def broadcast_order_fill(self, event: OrderFillEvent) -> None:
        raise NotImplementedError("RedisBroadcast not yet implemented (Phase 3)")


# ---------------------------------------------------------------------------
# Module-level singleton — same pattern as ws_manager and event_bus
# ---------------------------------------------------------------------------

broadcast_backend: BroadcastBackend = InProcessBroadcast(ws_manager)
