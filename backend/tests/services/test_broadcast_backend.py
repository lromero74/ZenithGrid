"""
Tests for app/services/broadcast_backend.py

TDD: these tests are written BEFORE implementation and must initially FAIL
with ModuleNotFoundError: No module named 'app.services.broadcast_backend'.

Covers:
- InProcessBroadcast.broadcast() delegates to manager.broadcast() — no user_id
- InProcessBroadcast.broadcast() delegates with user_id
- InProcessBroadcast.send_to_user() delegates to manager
- InProcessBroadcast.send_to_room() delegates with exclude_user
- InProcessBroadcast.broadcast_order_fill() delegates to manager
- Module-level singleton exists and is InProcessBroadcast
- broadcast_backend satisfies BroadcastBackend Protocol (isinstance check)
- RedisBroadcast is importable and raises NotImplementedError on all methods
- InProcessBroadcast accepts injected manager (not global)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


class TestInProcessBroadcast:

    @pytest.mark.asyncio
    async def test_broadcast_no_user_delegates(self):
        """Happy path: broadcast(message) with no user_id delegates to manager.broadcast()."""
        from app.services.broadcast_backend import InProcessBroadcast
        mock_manager = MagicMock()
        mock_manager.broadcast = AsyncMock()

        backend = InProcessBroadcast(mock_manager)
        msg = {"type": "ping"}
        await backend.broadcast(msg)

        mock_manager.broadcast.assert_awaited_once_with(msg, user_id=None)

    @pytest.mark.asyncio
    async def test_broadcast_with_user_id_delegates(self):
        """Happy path: broadcast(message, user_id=42) delegates with user_id."""
        from app.services.broadcast_backend import InProcessBroadcast
        mock_manager = MagicMock()
        mock_manager.broadcast = AsyncMock()

        backend = InProcessBroadcast(mock_manager)
        msg = {"type": "update"}
        await backend.broadcast(msg, user_id=42)

        mock_manager.broadcast.assert_awaited_once_with(msg, user_id=42)

    @pytest.mark.asyncio
    async def test_send_to_user_delegates(self):
        """Happy path: send_to_user() delegates to manager.send_to_user()."""
        from app.services.broadcast_backend import InProcessBroadcast
        mock_manager = MagicMock()
        mock_manager.send_to_user = AsyncMock()

        backend = InProcessBroadcast(mock_manager)
        msg = {"type": "notification"}
        await backend.send_to_user(7, msg)

        mock_manager.send_to_user.assert_awaited_once_with(7, msg)

    @pytest.mark.asyncio
    async def test_send_to_room_delegates(self):
        """Happy path: send_to_room() delegates to manager.send_to_room() with exclude_user."""
        from app.services.broadcast_backend import InProcessBroadcast
        mock_manager = MagicMock()
        mock_manager.send_to_room = AsyncMock()

        backend = InProcessBroadcast(mock_manager)
        players = {1, 2, 3}
        msg = {"type": "game_state"}
        await backend.send_to_room(players, msg, exclude_user=2)

        mock_manager.send_to_room.assert_awaited_once_with(players, msg, exclude_user=2)

    @pytest.mark.asyncio
    async def test_send_to_room_no_exclude(self):
        """Edge case: send_to_room() with no exclude_user passes exclude_user=None."""
        from app.services.broadcast_backend import InProcessBroadcast
        mock_manager = MagicMock()
        mock_manager.send_to_room = AsyncMock()

        backend = InProcessBroadcast(mock_manager)
        players = {1, 2}
        msg = {"type": "start"}
        await backend.send_to_room(players, msg)

        mock_manager.send_to_room.assert_awaited_once_with(players, msg, exclude_user=None)

    @pytest.mark.asyncio
    async def test_broadcast_order_fill_delegates(self):
        """Happy path: broadcast_order_fill() delegates to manager.broadcast_order_fill()."""
        from app.services.broadcast_backend import InProcessBroadcast
        from app.services.websocket_manager import OrderFillEvent
        mock_manager = MagicMock()
        mock_manager.broadcast_order_fill = AsyncMock()

        backend = InProcessBroadcast(mock_manager)
        event = OrderFillEvent(
            fill_type="sell_order",
            product_id="BTC-USD",
            base_amount=0.001,
            quote_amount=100.0,
            price=100_000.0,
            position_id=5,
            user_id=1,
        )
        await backend.broadcast_order_fill(event)

        mock_manager.broadcast_order_fill.assert_awaited_once_with(event)


class TestModuleSingleton:

    def test_module_singleton_exists_and_is_correct_type(self):
        """Happy path: module-level broadcast_backend singleton is InProcessBroadcast."""
        from app.services.broadcast_backend import broadcast_backend, InProcessBroadcast
        assert isinstance(broadcast_backend, InProcessBroadcast)

    def test_singleton_satisfies_protocol(self):
        """Happy path: broadcast_backend isinstance check passes BroadcastBackend Protocol."""
        from app.services.broadcast_backend import broadcast_backend, BroadcastBackend
        assert isinstance(broadcast_backend, BroadcastBackend)

    def test_inprocess_accepts_injected_manager(self):
        """Edge case: InProcessBroadcast can be constructed with a custom manager."""
        from app.services.broadcast_backend import InProcessBroadcast
        custom_manager = MagicMock()
        backend = InProcessBroadcast(custom_manager)
        assert backend._manager is custom_manager


class TestRedisBroadcastStub:

    @pytest.mark.asyncio
    async def test_redis_broadcast_is_importable(self):
        """Happy path: RedisBroadcast class is importable."""
        from app.services.broadcast_backend import RedisBroadcast
        assert RedisBroadcast is not None

    @pytest.mark.asyncio
    async def test_redis_broadcast_raises_on_broadcast(self):
        """Failure: RedisBroadcast.broadcast raises NotImplementedError."""
        from app.services.broadcast_backend import RedisBroadcast
        stub = RedisBroadcast()
        with pytest.raises(NotImplementedError):
            await stub.broadcast({"type": "test"})

    @pytest.mark.asyncio
    async def test_redis_broadcast_raises_on_send_to_user(self):
        """Failure: RedisBroadcast.send_to_user raises NotImplementedError."""
        from app.services.broadcast_backend import RedisBroadcast
        stub = RedisBroadcast()
        with pytest.raises(NotImplementedError):
            await stub.send_to_user(1, {"type": "test"})

    @pytest.mark.asyncio
    async def test_redis_broadcast_raises_on_send_to_room(self):
        """Failure: RedisBroadcast.send_to_room raises NotImplementedError."""
        from app.services.broadcast_backend import RedisBroadcast
        stub = RedisBroadcast()
        with pytest.raises(NotImplementedError):
            await stub.send_to_room({1, 2}, {"type": "test"})

    @pytest.mark.asyncio
    async def test_redis_broadcast_raises_on_broadcast_order_fill(self):
        """Failure: RedisBroadcast.broadcast_order_fill raises NotImplementedError."""
        from app.services.broadcast_backend import RedisBroadcast
        from app.services.websocket_manager import OrderFillEvent
        stub = RedisBroadcast()
        event = OrderFillEvent(
            fill_type="base_order",
            product_id="ETH-USD",
            base_amount=0.1,
            quote_amount=50.0,
            price=500.0,
            position_id=3,
        )
        with pytest.raises(NotImplementedError):
            await stub.broadcast_order_fill(event)

    def test_redis_broadcast_satisfies_protocol(self):
        """Edge case: RedisBroadcast also satisfies BroadcastBackend Protocol."""
        from app.services.broadcast_backend import RedisBroadcast, BroadcastBackend
        assert isinstance(RedisBroadcast(), BroadcastBackend)
