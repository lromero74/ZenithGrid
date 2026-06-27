from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _discard_task(coro):
    coro.close()
    return MagicMock()


@pytest.mark.asyncio
async def test_leader_lease_acquires_and_releases_only_its_token():
    from app.services.trading_leader import TradingLeaderLease

    redis = AsyncMock()
    redis.set.return_value = True
    redis.eval.return_value = 1
    lease = TradingLeaderLease(redis, token="leader-a", renew_interval_seconds=3600)

    await lease.acquire()
    await lease.release()

    redis.set.assert_awaited_once_with("zenith:trading-leader", "leader-a", nx=True, ex=30)
    assert redis.eval.await_args.args[2:] == ("zenith:trading-leader", "leader-a")


@pytest.mark.asyncio
async def test_leader_lease_fails_closed_when_another_process_holds_it():
    from app.services.trading_leader import TradingLeaderLease

    redis = AsyncMock()
    redis.set.return_value = None
    lease = TradingLeaderLease(redis, token="leader-b")

    with pytest.raises(RuntimeError, match="already active"):
        await lease.acquire()


@pytest.mark.asyncio
async def test_leader_lease_fails_closed_when_renewal_errors_past_ttl():
    """A Redis error during renewal must not silently kill the renew task — once
    the lease can no longer have been renewed within its TTL, fail closed."""
    from app.services.trading_leader import TradingLeaderLease

    redis = AsyncMock()
    redis.set.return_value = True
    redis.eval.side_effect = ConnectionError("redis unreachable")
    fatal = AsyncMock()
    lease = TradingLeaderLease(
        redis,
        token="leader-err",
        renew_interval_seconds=0,
        ttl_seconds=0,  # any elapsed >= ttl → fail closed immediately
        on_lease_lost=fatal,
    )

    await lease.acquire()
    await lease.wait_until_stopped()

    fatal.assert_awaited_once()


@pytest.mark.asyncio
async def test_leader_lease_invokes_fatal_callback_if_renewal_is_lost():
    from app.services.trading_leader import TradingLeaderLease

    redis = AsyncMock()
    redis.set.return_value = True
    redis.eval.return_value = 0
    fatal = AsyncMock()
    lease = TradingLeaderLease(
        redis,
        token="leader-c",
        renew_interval_seconds=0,
        on_lease_lost=fatal,
    )

    await lease.acquire()
    await lease.wait_until_stopped()

    fatal.assert_awaited_once()


def test_process_role_rejects_unknown_values():
    from app.config import Settings

    assert Settings(process_role="web").process_role == "web"
    assert Settings(process_role="trader").process_role == "trader"
    with pytest.raises(ValueError):
        Settings(process_role="anything")


@pytest.mark.asyncio
async def test_health_reports_process_role_for_split_verification():
    from app.config import settings
    from app.routers.system_router import health_check

    with (
        patch.object(settings, "process_role", "web"),
        patch("app.routers.system_router.get_git_version_cached", return_value="v-test"),
    ):
        health = await health_check()

    assert health["process_role"] == "web"


@pytest.mark.asyncio
async def test_web_role_never_starts_trading_monitors():
    from app.config import settings
    from app.main import app, startup_event

    price_monitor = MagicMock()
    price_monitor.start_async = AsyncMock()
    with (
        patch.object(settings, "process_role", "web"),
        patch.object(settings, "jwt_secret_key", "test-secret"),
        patch("app.redis_client.init_redis", new=AsyncMock()),
        patch("app.main.init_db", new=AsyncMock()),
        patch("app.main.asyncio.create_task", side_effect=_discard_task),
        patch("app.registry._default_registry"),
        patch("app.auth_routers.rate_limit_backend.rate_limit_backend"),
        patch("app.services.broadcast_backend.broadcast_backend"),
        patch("app.main.price_monitor", price_monitor),
        patch("app.main.build_changelog_cache"),
        patch("app.main.get_git_version_cached"),
        patch("app.main.get_latest_git_tag_cached"),
        patch("app.main._wire_event_bus_subscribers"),
    ):
        await startup_event()

    price_monitor.start_async.assert_not_awaited()
    del app.state.redis_subscriber_task


@pytest.mark.asyncio
async def test_trader_role_does_not_start_monitors_without_leadership():
    from app.config import settings
    from app.main import app, startup_event

    price_monitor = MagicMock()
    price_monitor.start_async = AsyncMock()
    lease = MagicMock()
    lease.acquire = AsyncMock(side_effect=RuntimeError("another trading process is already active"))
    with (
        patch.object(settings, "process_role", "trader"),
        patch.object(settings, "jwt_secret_key", "test-secret"),
        patch("app.redis_client.init_redis", new=AsyncMock()),
        patch("app.redis_client.get_redis", new=AsyncMock()),
        patch("app.main.init_db", new=AsyncMock()),
        patch("app.main.asyncio.create_task", side_effect=_discard_task),
        patch("app.registry._default_registry"),
        patch("app.auth_routers.rate_limit_backend.rate_limit_backend"),
        patch("app.services.broadcast_backend.broadcast_backend"),
        patch("app.main.TradingLeaderLease", return_value=lease),
        patch("app.main.price_monitor", price_monitor),
    ):
        with pytest.raises(RuntimeError, match="already active"):
            await startup_event()

    price_monitor.start_async.assert_not_awaited()
    del app.state.redis_subscriber_task
