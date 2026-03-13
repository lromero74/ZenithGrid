"""
WebSocket Connection Manager for real-time notifications

Manages WebSocket connections and broadcasts order fill events to connected clients.
Connections are scoped by user_id so notifications only reach the owning user.
"""

import logging
import asyncio
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Limits
MAX_CONNECTIONS_PER_USER = 5
MAX_MESSAGE_SIZE = 32768  # 32 KB — game state broadcasts (spectator view) need headroom
RECEIVE_TIMEOUT_SECONDS = 300  # 5 minutes


@dataclass
class OrderFillEvent:
    """Data for an order fill WebSocket notification.

    Groups the fill-specific fields into a single object,
    reducing the parameter count of broadcast_order_fill from 10 to 2.
    """
    fill_type: str       # base_order, dca_order, sell_order, partial_fill, close_short
    product_id: str
    base_amount: float
    quote_amount: float
    price: float
    position_id: int
    profit: Optional[float] = None
    profit_percentage: Optional[float] = None
    user_id: Optional[int] = None
    is_paper_trading: bool = False


class WebSocketManager:
    """Manages WebSocket connections and broadcasts messages to clients.

    Uses Dict[int, Set[WebSocket]] for O(1) user lookups instead of
    scanning a flat list on every operation.
    """

    def __init__(self):
        # user_id → set of WebSocket connections
        self._user_connections: dict[int, set[WebSocket]] = {}
        # WebSocket → user_id (reverse lookup for disconnect)
        self._socket_owners: dict[WebSocket, int] = {}
        self._lock = asyncio.Lock()

    @property
    def active_connections(self) -> list[tuple[WebSocket, int]]:
        """Backward-compat property — returns flat list of (ws, uid) tuples."""
        return [
            (ws, uid)
            for uid, sockets in self._user_connections.items()
            for ws in sockets
        ]

    def _count_user_connections(self, user_id: int) -> int:
        """Count active connections for a specific user. O(1)."""
        return len(self._user_connections.get(user_id, ()))

    async def connect(self, websocket: WebSocket, user_id: int) -> bool:
        """
        Accept a new WebSocket connection for a specific user.

        Returns True if connected, False if rejected (too many connections).
        """
        async with self._lock:
            if self._count_user_connections(user_id) >= MAX_CONNECTIONS_PER_USER:
                await websocket.close(
                    code=4008, reason="Too many connections"
                )
                logger.warning(
                    f"WebSocket rejected for user {user_id}: "
                    f"exceeded {MAX_CONNECTIONS_PER_USER} connections"
                )
                return False

            await websocket.accept()
            self._user_connections.setdefault(user_id, set()).add(websocket)
            self._socket_owners[websocket] = user_id

        total = sum(len(s) for s in self._user_connections.values())
        logger.info(
            f"WebSocket connected for user {user_id}. "
            f"Total connections: {total}"
        )
        return True

    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection. O(1) via reverse lookup."""
        async with self._lock:
            user_id = self._socket_owners.pop(websocket, None)
            if user_id is not None:
                sockets = self._user_connections.get(user_id)
                if sockets:
                    sockets.discard(websocket)
                    if not sockets:
                        del self._user_connections[user_id]

        total = sum(len(s) for s in self._user_connections.values())
        logger.info(f"WebSocket disconnected. Total connections: {total}")

    async def broadcast(self, message: dict, user_id: Optional[int] = None):
        """
        Broadcast a message to connected clients.

        If user_id is provided, only send to that user's connections — O(Cu).
        If user_id is None, send to all (for system-wide messages) — O(C).
        """
        async with self._lock:
            if user_id is not None:
                sockets = list(self._user_connections.get(user_id, ()))
            else:
                sockets = [
                    ws
                    for s in self._user_connections.values()
                    for ws in s
                ]

        if not sockets:
            return

        disconnected = []
        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception as e:
                uid = self._socket_owners.get(ws, "?")
                logger.warning(f"Failed to send message to user {uid}: {e}")
                disconnected.append(ws)

        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    uid = self._socket_owners.pop(ws, None)
                    if uid is not None:
                        s = self._user_connections.get(uid)
                        if s:
                            s.discard(ws)
                            if not s:
                                del self._user_connections[uid]

    async def sweep_stale_connections(self) -> int:
        """Remove WebSocket connections that are no longer open. Returns count removed."""
        from starlette.websockets import WebSocketState
        stale = []
        async with self._lock:
            for ws in list(self._socket_owners.keys()):
                try:
                    if ws.client_state != WebSocketState.CONNECTED:
                        stale.append(ws)
                except Exception:
                    stale.append(ws)

        for ws in stale:
            await self.disconnect(ws)

        return len(stale)

    def get_connected_user_ids(self) -> set[int]:
        """Return the set of user IDs that have active WebSocket connections. O(1)."""
        return set(self._user_connections.keys())

    async def send_to_user(self, user_id: int, message: dict):
        """Send a message to a specific user's connections."""
        await self.broadcast(message, user_id=user_id)

    async def send_to_room(self, player_ids: set[int], message: dict, exclude_user: int | None = None):
        """Send a message to all players in a room."""
        for uid in player_ids:
            if uid != exclude_user:
                await self.send_to_user(uid, message)

    async def broadcast_order_fill(self, event: OrderFillEvent):
        """Broadcast an order fill event to the owning user's connections"""
        message = {
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
            "timestamp": datetime.utcnow().isoformat(),
        }
        logger.info(
            f"Broadcasting order fill: {event.fill_type} for {event.product_id} "
            f"(user_id={event.user_id})"
        )
        await self.broadcast(message, user_id=event.user_id)


# Global singleton instance
ws_manager = WebSocketManager()
