"""
WebSocket Connection Manager for real-time notifications

Manages WebSocket connections and broadcasts order fill events to connected clients.
Connections are scoped by user_id so notifications only reach the owning user.
"""

import logging
import asyncio
from typing import List, Optional, Tuple
from datetime import datetime

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections and broadcasts messages to clients"""

    def __init__(self):
        # Store (websocket, user_id) tuples
        self.active_connections: List[Tuple[WebSocket, int]] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: int):
        """Accept a new WebSocket connection for a specific user"""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append((websocket, user_id))
        logger.info(f"WebSocket connected for user {user_id}. Total connections: {len(self.active_connections)}")

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

    async def broadcast_order_fill(
        self,
        fill_type: str,
        product_id: str,
        base_amount: float,
        quote_amount: float,
        price: float,
        position_id: int,
        profit: Optional[float] = None,
        profit_percentage: Optional[float] = None,
        user_id: Optional[int] = None,
    ):
        """Broadcast an order fill event to the owning user's connections"""
        message = {
            "type": "order_fill",
            "fill_type": fill_type,  # base_order, dca_order, sell_order, partial_fill
            "product_id": product_id,
            "base_amount": base_amount,
            "quote_amount": quote_amount,
            "price": price,
            "position_id": position_id,
            "profit": profit,
            "profit_percentage": profit_percentage,
            "timestamp": datetime.utcnow().isoformat(),
        }
        logger.info(f"Broadcasting order fill: {fill_type} for {product_id} (user_id={user_id})")
        await self.broadcast(message, user_id=user_id)


# Global singleton instance
ws_manager = WebSocketManager()
