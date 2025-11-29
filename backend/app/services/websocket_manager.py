"""
WebSocket Connection Manager for real-time notifications

Manages WebSocket connections and broadcasts order fill events to connected clients.
"""

import logging
import asyncio
from typing import List, Optional
from datetime import datetime

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections and broadcasts messages to clients"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients"""
        if not self.active_connections:
            return

        # Create a copy of connections to avoid modification during iteration
        async with self._lock:
            connections = list(self.active_connections)

        disconnected = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send message to client: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                for conn in disconnected:
                    if conn in self.active_connections:
                        self.active_connections.remove(conn)

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
    ):
        """Broadcast an order fill event to all connected clients"""
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
        logger.info(f"📢 Broadcasting order fill: {fill_type} for {product_id}")
        await self.broadcast(message)


# Global singleton instance
ws_manager = WebSocketManager()
