"""
WebSocket Connection Manager for real-time notifications

Manages WebSocket connections and broadcasts order fill events to connected clients.
Connections are scoped by user_id so notifications only reach the owning user.
"""

import logging
import asyncio
from dataclasses import dataclass
from typing import List, Optional, Tuple
from datetime import datetime

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Limits
MAX_CONNECTIONS_PER_USER = 5
MAX_MESSAGE_SIZE = 4096  # 4 KB
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
    """Manages WebSocket connections and broadcasts messages to clients"""

    def __init__(self):
        # Store (websocket, user_id) tuples
        self.active_connections: List[Tuple[WebSocket, int]] = []
        self._lock = asyncio.Lock()

    def _count_user_connections(self, user_id: int) -> int:
        """Count active connections for a specific user (must be called under lock)."""
        return sum(1 for _, uid in self.active_connections if uid == user_id)

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
            self.active_connections.append((websocket, user_id))

        logger.info(
            f"WebSocket connected for user {user_id}. "
            f"Total connections: {len(self.active_connections)}"
        )
        return True

    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        async with self._lock:
            self.active_connections = [
                (ws, uid) for ws, uid in self.active_connections if ws is not websocket
            ]
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict, user_id: Optional[int] = None):
        """
        Broadcast a message to connected clients.

        If user_id is provided, only send to that user's connections.
        If user_id is None, send to all (for system-wide messages).
        """
        async with self._lock:
            if user_id is not None:
                connections = [(ws, uid) for ws, uid in self.active_connections if uid == user_id]
            else:
                connections = list(self.active_connections)

        if not connections:
            return

        disconnected = []
        for ws, uid in connections:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send message to user {uid}: {e}")
                disconnected.append(ws)

        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                self.active_connections = [
                    (ws, uid) for ws, uid in self.active_connections if ws not in disconnected
                ]

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
