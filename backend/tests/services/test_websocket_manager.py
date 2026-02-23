"""
Tests for backend/app/services/websocket_manager.py

Tests the WebSocketManager class which manages WebSocket connections
and broadcasts order fill events to connected clients scoped by user_id.
"""

import pytest
from unittest.mock import AsyncMock

from app.services.websocket_manager import WebSocketManager, MAX_CONNECTIONS_PER_USER


def _make_ws(accept_side_effect=None, send_json_side_effect=None, close_side_effect=None):
    """Helper to create a mock WebSocket."""
    ws = AsyncMock()
    ws.accept = AsyncMock(side_effect=accept_side_effect)
    ws.send_json = AsyncMock(side_effect=send_json_side_effect)
    ws.close = AsyncMock(side_effect=close_side_effect)
    return ws


class TestWebSocketManagerConnect:
    """Tests for connect()."""

    @pytest.mark.asyncio
    async def test_connect_accepts_and_stores(self):
        """Happy path: connection is accepted and tracked."""
        mgr = WebSocketManager()
        ws = _make_ws()
        result = await mgr.connect(ws, user_id=1)
        assert result is True
        assert len(mgr.active_connections) == 1
        ws.accept.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_multiple_users(self):
        """Happy path: different users can connect independently."""
        mgr = WebSocketManager()
        ws1 = _make_ws()
        ws2 = _make_ws()
        await mgr.connect(ws1, user_id=1)
        await mgr.connect(ws2, user_id=2)
        assert len(mgr.active_connections) == 2

    @pytest.mark.asyncio
    async def test_connect_rejects_when_limit_reached(self):
        """Failure: rejects connection when user exceeds limit."""
        mgr = WebSocketManager()
        # Fill up to max
        for _ in range(MAX_CONNECTIONS_PER_USER):
            ws = _make_ws()
            await mgr.connect(ws, user_id=1)

        # One more should be rejected
        ws_extra = _make_ws()
        result = await mgr.connect(ws_extra, user_id=1)
        assert result is False
        ws_extra.close.assert_awaited_once()
        assert len(mgr.active_connections) == MAX_CONNECTIONS_PER_USER

    @pytest.mark.asyncio
    async def test_connect_limit_is_per_user(self):
        """Edge case: user 2 can still connect even if user 1 is at limit."""
        mgr = WebSocketManager()
        for _ in range(MAX_CONNECTIONS_PER_USER):
            await mgr.connect(_make_ws(), user_id=1)

        ws_user2 = _make_ws()
        result = await mgr.connect(ws_user2, user_id=2)
        assert result is True
        assert len(mgr.active_connections) == MAX_CONNECTIONS_PER_USER + 1


class TestWebSocketManagerDisconnect:
    """Tests for disconnect()."""

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self):
        """Happy path: disconnected socket is removed."""
        mgr = WebSocketManager()
        ws = _make_ws()
        await mgr.connect(ws, user_id=1)
        await mgr.disconnect(ws)
        assert len(mgr.active_connections) == 0

    @pytest.mark.asyncio
    async def test_disconnect_only_removes_specified_socket(self):
        """Edge case: other sockets remain after disconnect."""
        mgr = WebSocketManager()
        ws1 = _make_ws()
        ws2 = _make_ws()
        await mgr.connect(ws1, user_id=1)
        await mgr.connect(ws2, user_id=1)
        await mgr.disconnect(ws1)
        assert len(mgr.active_connections) == 1
        assert mgr.active_connections[0][0] is ws2

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_socket_no_error(self):
        """Edge case: disconnecting unknown socket does nothing."""
        mgr = WebSocketManager()
        ws = _make_ws()
        await mgr.disconnect(ws)  # should not raise
        assert len(mgr.active_connections) == 0


class TestWebSocketManagerBroadcast:
    """Tests for broadcast()."""

    @pytest.mark.asyncio
    async def test_broadcast_to_all(self):
        """Happy path: broadcast without user_id sends to all."""
        mgr = WebSocketManager()
        ws1 = _make_ws()
        ws2 = _make_ws()
        await mgr.connect(ws1, user_id=1)
        await mgr.connect(ws2, user_id=2)

        msg = {"type": "test"}
        await mgr.broadcast(msg)
        ws1.send_json.assert_awaited_once_with(msg)
        ws2.send_json.assert_awaited_once_with(msg)

    @pytest.mark.asyncio
    async def test_broadcast_to_specific_user(self):
        """Happy path: broadcast with user_id only sends to that user."""
        mgr = WebSocketManager()
        ws1 = _make_ws()
        ws2 = _make_ws()
        await mgr.connect(ws1, user_id=1)
        await mgr.connect(ws2, user_id=2)

        msg = {"type": "test"}
        await mgr.broadcast(msg, user_id=1)
        ws1.send_json.assert_awaited_once_with(msg)
        ws2.send_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_broadcast_no_connections_does_nothing(self):
        """Edge case: broadcast with no connections doesn't error."""
        mgr = WebSocketManager()
        await mgr.broadcast({"type": "test"})  # should not raise

    @pytest.mark.asyncio
    async def test_broadcast_cleans_up_disconnected(self):
        """Failure: disconnected sockets are cleaned up on send failure."""
        mgr = WebSocketManager()
        ws_good = _make_ws()
        ws_bad = _make_ws(send_json_side_effect=ConnectionError("gone"))
        await mgr.connect(ws_good, user_id=1)
        await mgr.connect(ws_bad, user_id=1)

        await mgr.broadcast({"type": "test"})
        # Bad socket should be removed
        assert len(mgr.active_connections) == 1
        assert mgr.active_connections[0][0] is ws_good


class TestBroadcastOrderFill:
    """Tests for broadcast_order_fill()."""

    @pytest.mark.asyncio
    async def test_broadcast_order_fill_happy_path(self):
        """Happy path: order fill message is structured correctly."""
        mgr = WebSocketManager()
        ws = _make_ws()
        await mgr.connect(ws, user_id=1)

        await mgr.broadcast_order_fill(
            fill_type="base_order",
            product_id="BTC-USD",
            base_amount=0.001,
            quote_amount=50.0,
            price=50000.0,
            position_id=42,
            profit=5.0,
            profit_percentage=10.0,
            user_id=1,
        )

        ws.send_json.assert_awaited_once()
        msg = ws.send_json.call_args[0][0]
        assert msg["type"] == "order_fill"
        assert msg["fill_type"] == "base_order"
        assert msg["product_id"] == "BTC-USD"
        assert msg["base_amount"] == 0.001
        assert msg["quote_amount"] == 50.0
        assert msg["price"] == 50000.0
        assert msg["position_id"] == 42
        assert msg["profit"] == 5.0
        assert msg["profit_percentage"] == 10.0
        assert "timestamp" in msg

    @pytest.mark.asyncio
    async def test_broadcast_order_fill_without_profit(self):
        """Edge case: order fill without profit fields (base order)."""
        mgr = WebSocketManager()
        ws = _make_ws()
        await mgr.connect(ws, user_id=1)

        await mgr.broadcast_order_fill(
            fill_type="base_order",
            product_id="ETH-BTC",
            base_amount=1.0,
            quote_amount=0.05,
            price=0.05,
            position_id=1,
            user_id=1,
        )

        msg = ws.send_json.call_args[0][0]
        assert msg["profit"] is None
        assert msg["profit_percentage"] is None

    @pytest.mark.asyncio
    async def test_broadcast_order_fill_no_matching_user(self):
        """Edge case: no connected user means no send."""
        mgr = WebSocketManager()
        ws = _make_ws()
        await mgr.connect(ws, user_id=1)

        await mgr.broadcast_order_fill(
            fill_type="sell_order",
            product_id="BTC-USD",
            base_amount=0.001,
            quote_amount=50.0,
            price=50000.0,
            position_id=42,
            user_id=999,  # no such user connected
        )

        ws.send_json.assert_not_awaited()


class TestCountUserConnections:
    """Tests for _count_user_connections()."""

    @pytest.mark.asyncio
    async def test_count_user_connections_empty(self):
        """Edge case: zero connections returns zero."""
        mgr = WebSocketManager()
        assert mgr._count_user_connections(1) == 0

    @pytest.mark.asyncio
    async def test_count_user_connections_mixed(self):
        """Happy path: counts only specified user's connections."""
        mgr = WebSocketManager()
        await mgr.connect(_make_ws(), user_id=1)
        await mgr.connect(_make_ws(), user_id=1)
        await mgr.connect(_make_ws(), user_id=2)
        assert mgr._count_user_connections(1) == 2
        assert mgr._count_user_connections(2) == 1
