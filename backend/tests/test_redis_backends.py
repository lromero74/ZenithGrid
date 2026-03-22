"""
TDD tests for Redis-backed service implementations.

Written BEFORE implementation. Covers:
  1. RedisRateLimitBackend  — rate_limit_backend.py
  2. RedisBroadcast          — broadcast_backend.py
  3. RedisJobStore config    — scheduler.py
  4. redis_client module     — redis_client.py
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# RedisRateLimitBackend
# ---------------------------------------------------------------------------

class TestRedisRateLimitBackend:
    """Unit tests — Redis client is mocked, no real Redis needed."""

    def _make_backend(self, mock_redis):
        from app.auth_routers.rate_limit_backend import RedisRateLimitBackend
        backend = RedisRateLimitBackend()
        return backend

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.incr = AsyncMock(return_value=1)
        redis.expire = AsyncMock(return_value=True)
        redis.get = AsyncMock(return_value=None)
        redis.pipeline = MagicMock()
        return redis

    @pytest.mark.asyncio
    async def test_record_attempt_increments_key(self, mock_redis):
        """Happy path: record_attempt calls INCR on the namespaced key."""
        from app.auth_routers.rate_limit_backend import RedisRateLimitBackend
        backend = RedisRateLimitBackend()
        with patch("app.redis_client.get_redis", return_value=mock_redis):
            await backend.record_attempt("login", "1.2.3.4")
        mock_redis.incr.assert_called_once_with("rl:login:1.2.3.4")

    @pytest.mark.asyncio
    async def test_record_attempt_sets_ttl_on_first_increment(self, mock_redis):
        """Happy path: TTL is set when counter goes from 0 → 1 (first attempt)."""
        from app.auth_routers.rate_limit_backend import RedisRateLimitBackend
        mock_redis.incr.return_value = 1  # first attempt
        backend = RedisRateLimitBackend()
        with patch("app.redis_client.get_redis", return_value=mock_redis):
            await backend.record_attempt("login", "1.2.3.4")
        mock_redis.expire.assert_called_once()
        args = mock_redis.expire.call_args[0]
        assert args[0] == "rl:login:1.2.3.4"
        assert args[1] == 900  # login window

    @pytest.mark.asyncio
    async def test_record_attempt_no_ttl_on_subsequent_increments(self, mock_redis):
        """Edge case: TTL is NOT reset on subsequent increments (fixed window)."""
        from app.auth_routers.rate_limit_backend import RedisRateLimitBackend
        mock_redis.incr.return_value = 3  # already has attempts
        backend = RedisRateLimitBackend()
        with patch("app.redis_client.get_redis", return_value=mock_redis):
            await backend.record_attempt("login", "1.2.3.4")
        mock_redis.expire.assert_not_called()

    @pytest.mark.asyncio
    async def test_count_recent_returns_current_value(self, mock_redis):
        """Happy path: count_recent returns the integer from Redis GET."""
        from app.auth_routers.rate_limit_backend import RedisRateLimitBackend
        mock_redis.get.return_value = "3"
        backend = RedisRateLimitBackend()
        with patch("app.redis_client.get_redis", return_value=mock_redis):
            result = await backend.count_recent("login", "1.2.3.4", 900)
        assert result == 3
        mock_redis.get.assert_called_once_with("rl:login:1.2.3.4")

    @pytest.mark.asyncio
    async def test_count_recent_returns_zero_for_missing_key(self, mock_redis):
        """Edge case: missing key (None from GET) returns 0, not an error."""
        from app.auth_routers.rate_limit_backend import RedisRateLimitBackend
        mock_redis.get.return_value = None
        backend = RedisRateLimitBackend()
        with patch("app.redis_client.get_redis", return_value=mock_redis):
            result = await backend.count_recent("login", "new-ip", 900)
        assert result == 0

    @pytest.mark.asyncio
    async def test_cleanup_is_noop(self, mock_redis):
        """Edge case: cleanup does nothing — Redis TTL handles expiry."""
        from app.auth_routers.rate_limit_backend import RedisRateLimitBackend
        backend = RedisRateLimitBackend()
        with patch("app.redis_client.get_redis", return_value=mock_redis):
            await backend.cleanup()  # must not raise
        mock_redis.delete.assert_not_called()

    def test_implements_rate_limit_backend_protocol(self):
        """Happy path: RedisRateLimitBackend satisfies the RateLimitBackend protocol."""
        from app.auth_routers.rate_limit_backend import RedisRateLimitBackend, RateLimitBackend
        backend = RedisRateLimitBackend()
        assert isinstance(backend, RateLimitBackend)

    @pytest.mark.asyncio
    async def test_different_categories_use_different_ttls(self, mock_redis):
        """Edge case: signup window (3600s) differs from login window (900s)."""
        from app.auth_routers.rate_limit_backend import RedisRateLimitBackend
        mock_redis.incr.return_value = 1
        backend = RedisRateLimitBackend()
        with patch("app.redis_client.get_redis", return_value=mock_redis):
            await backend.record_attempt("signup", "1.2.3.4")
        args = mock_redis.expire.call_args[0]
        assert args[1] == 3600  # signup window

    @pytest.mark.asyncio
    async def test_mfa_category_uses_correct_window(self, mock_redis):
        """Edge case: MFA window is 300s (5 minutes)."""
        from app.auth_routers.rate_limit_backend import RedisRateLimitBackend
        mock_redis.incr.return_value = 1
        backend = RedisRateLimitBackend()
        with patch("app.redis_client.get_redis", return_value=mock_redis):
            await backend.record_attempt("mfa", "some-token")
        args = mock_redis.expire.call_args[0]
        assert args[1] == 300


# ---------------------------------------------------------------------------
# RedisBroadcast
# ---------------------------------------------------------------------------

class TestRedisBroadcast:
    """Unit tests — Redis PUBLISH is mocked."""

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.publish = AsyncMock(return_value=1)
        return redis

    @pytest.mark.asyncio
    async def test_send_to_user_publishes_to_correct_channel(self, mock_redis):
        """Happy path: send_to_user publishes to ws:user:{user_id}."""
        from app.services.broadcast_backend import RedisBroadcast
        backend = RedisBroadcast()
        msg = {"type": "test", "data": "hello"}
        with patch("app.redis_client.get_redis", return_value=mock_redis):
            await backend.send_to_user(42, msg)
        mock_redis.publish.assert_called_once()
        channel, payload = mock_redis.publish.call_args[0]
        assert channel == "ws:user:42"
        data = json.loads(payload)
        assert data["message"] == msg

    @pytest.mark.asyncio
    async def test_broadcast_publishes_to_broadcast_channel(self, mock_redis):
        """Happy path: broadcast() publishes to ws:broadcast."""
        from app.services.broadcast_backend import RedisBroadcast
        backend = RedisBroadcast()
        msg = {"type": "system", "text": "maintenance"}
        with patch("app.redis_client.get_redis", return_value=mock_redis):
            await backend.broadcast(msg)
        channel, payload = mock_redis.publish.call_args[0]
        assert channel == "ws:broadcast"
        data = json.loads(payload)
        assert data["message"] == msg
        assert data["user_id"] is None

    @pytest.mark.asyncio
    async def test_broadcast_with_user_id_filter(self, mock_redis):
        """Edge case: broadcast with user_id targets one user via ws:user channel."""
        from app.services.broadcast_backend import RedisBroadcast
        backend = RedisBroadcast()
        with patch("app.redis_client.get_redis", return_value=mock_redis):
            await backend.broadcast({"text": "hi"}, user_id=7)
        channel, payload = mock_redis.publish.call_args[0]
        assert channel == "ws:user:7"

    @pytest.mark.asyncio
    async def test_send_to_room_publishes_player_ids(self, mock_redis):
        """Happy path: send_to_room publishes to ws:room with player_ids."""
        from app.services.broadcast_backend import RedisBroadcast
        backend = RedisBroadcast()
        with patch("app.redis_client.get_redis", return_value=mock_redis):
            await backend.send_to_room({1, 2, 3}, {"type": "move"}, exclude_user=2)
        channel, payload = mock_redis.publish.call_args[0]
        assert channel == "ws:room"
        data = json.loads(payload)
        assert set(data["player_ids"]) == {1, 2, 3}
        assert data["exclude_user"] == 2

    @pytest.mark.asyncio
    async def test_broadcast_order_fill_publishes_to_user_channel(self, mock_redis):
        """Happy path: broadcast_order_fill publishes to ws:user:{user_id}."""
        from app.services.broadcast_backend import RedisBroadcast
        from app.services.websocket_manager import OrderFillEvent
        backend = RedisBroadcast()
        event = OrderFillEvent(
            user_id=5, position_id=10,
            fill_type="sell_order", product_id="BTC-USD",
            base_amount=0.001, quote_amount=50.0, price=50000.0,
        )
        with patch("app.redis_client.get_redis", return_value=mock_redis):
            await backend.broadcast_order_fill(event)
        channel, payload = mock_redis.publish.call_args[0]
        assert channel == "ws:user:5"
        data = json.loads(payload)
        assert data["type"] == "order_fill"

    def test_implements_broadcast_backend_protocol(self):
        """Happy path: RedisBroadcast satisfies the BroadcastBackend protocol."""
        from app.services.broadcast_backend import RedisBroadcast, BroadcastBackend
        backend = RedisBroadcast()
        assert isinstance(backend, BroadcastBackend)


# ---------------------------------------------------------------------------
# Redis subscriber routing
# ---------------------------------------------------------------------------

class TestRedisSubscriberRouting:
    """Unit tests for the subscriber dispatch logic (route_message)."""

    @pytest.mark.asyncio
    async def test_route_user_message_calls_send_to_user(self):
        """Happy path: ws:user:42 channel dispatches to ws_manager.send_to_user."""
        from app.services.broadcast_backend import route_redis_message
        mock_manager = AsyncMock()
        payload = json.dumps({"message": {"type": "ping"}})
        await route_redis_message("ws:user:42", payload, mock_manager)
        mock_manager.send_to_user.assert_called_once_with(42, {"type": "ping"})

    @pytest.mark.asyncio
    async def test_route_broadcast_calls_broadcast(self):
        """Happy path: ws:broadcast channel dispatches to ws_manager.broadcast."""
        from app.services.broadcast_backend import route_redis_message
        mock_manager = AsyncMock()
        payload = json.dumps({"message": {"type": "sys"}, "user_id": None})
        await route_redis_message("ws:broadcast", payload, mock_manager)
        mock_manager.broadcast.assert_called_once_with({"type": "sys"}, user_id=None)

    @pytest.mark.asyncio
    async def test_route_room_message_calls_send_to_room(self):
        """Happy path: ws:room channel dispatches to ws_manager.send_to_room."""
        from app.services.broadcast_backend import route_redis_message
        mock_manager = AsyncMock()
        payload = json.dumps({"message": {"type": "move"}, "player_ids": [1, 2, 3], "exclude_user": 2})
        await route_redis_message("ws:room", payload, mock_manager)
        mock_manager.send_to_room.assert_called_once_with(
            {1, 2, 3}, {"type": "move"}, exclude_user=2
        )

    @pytest.mark.asyncio
    async def test_route_unknown_channel_is_silently_ignored(self):
        """Edge case: unrecognized channel prefix doesn't raise."""
        from app.services.broadcast_backend import route_redis_message
        mock_manager = AsyncMock()
        await route_redis_message("ws:unknown:stuff", "{}", mock_manager)
        mock_manager.broadcast.assert_not_called()
        mock_manager.send_to_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_route_bad_json_is_logged_not_raised(self):
        """Failure case: malformed JSON in subscriber message doesn't crash."""
        from app.services.broadcast_backend import route_redis_message
        mock_manager = AsyncMock()
        await route_redis_message("ws:user:1", "not-json", mock_manager)
        mock_manager.send_to_user.assert_not_called()


# ---------------------------------------------------------------------------
# redis_client module
# ---------------------------------------------------------------------------

class TestRedisClient:
    """Unit tests for the redis_client singleton."""

    def test_get_redis_returns_client(self):
        """Happy path: get_redis returns an async Redis client."""
        from app import redis_client
        client = redis_client.get_redis_sync()
        assert client is not None

    @pytest.mark.asyncio
    async def test_get_redis_async_returns_client(self):
        """Happy path: async get_redis returns a client."""
        from app.redis_client import get_redis
        client = await get_redis()
        assert client is not None
        await client.aclose()

    @pytest.mark.asyncio
    async def test_redis_ping(self):
        """Integration: Redis responds to PING (requires Redis running)."""
        from app.redis_client import get_redis
        client = await get_redis()
        result = await client.ping()
        assert result is True
        await client.aclose()


# ---------------------------------------------------------------------------
# APScheduler jobstore
# ---------------------------------------------------------------------------

class TestSchedulerJobstore:
    """Verify scheduler uses MemoryJobStore (safe with threading.Lock jobs)."""

    def test_scheduler_does_not_use_redis_jobstore(self):
        """Happy path: scheduler must NOT use RedisJobStore.

        RedisJobStore was reverted: it pickles bound-method job targets, which
        fails when those objects hold threading.Lock attributes (all monitors do).
        MemoryJobStore never pickles — jobs run fresh each restart.
        """
        from app.scheduler import scheduler
        # RedisJobStore import should not appear in the scheduler module
        import app.scheduler as _sched_module
        assert not hasattr(_sched_module, "RedisJobStore"), (
            "RedisJobStore must not be imported in scheduler.py"
        )
        # Confirm no explicitly configured non-default jobstore
        assert scheduler._jobstores == {}, (
            "scheduler should use APScheduler default (MemoryJobStore), not a custom store"
        )

    def test_scheduler_is_asyncio_scheduler(self):
        """Edge case: scheduler must be AsyncIOScheduler to share the FastAPI loop."""
        from app.scheduler import scheduler
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        assert isinstance(scheduler, AsyncIOScheduler)
