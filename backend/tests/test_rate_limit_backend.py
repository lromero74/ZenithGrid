"""
Tests for app/auth_routers/rate_limit_backend.py

TDD: these tests are written BEFORE implementation and must initially FAIL
with ModuleNotFoundError: No module named 'app.auth_routers.rate_limit_backend'.

Covers:
- PostgresRateLimitBackend.record_attempt delegates to _db_record(category, key)
- PostgresRateLimitBackend.count_recent delegates to _db_count and returns its result
- PostgresRateLimitBackend.cleanup delegates to _db_cleanup()
- Module-level singleton exists and is PostgresRateLimitBackend
- rate_limit_backend satisfies RateLimitBackend Protocol (isinstance)
- RedisRateLimitBackend is importable
- RedisRateLimitBackend.record_attempt raises NotImplementedError
- RedisRateLimitBackend.count_recent raises NotImplementedError
- RedisRateLimitBackend.cleanup raises NotImplementedError
- RedisRateLimitBackend satisfies RateLimitBackend Protocol (isinstance)
"""
import pytest
from unittest.mock import AsyncMock, patch


class TestPostgresRateLimitBackend:

    @pytest.mark.asyncio
    @patch('app.auth_routers.rate_limiters._db_record', new_callable=AsyncMock)
    async def test_record_attempt_delegates_to_db_record(self, mock_db_record):
        """Happy path: record_attempt(category, key) delegates to _db_record."""
        from app.auth_routers.rate_limit_backend import PostgresRateLimitBackend
        backend = PostgresRateLimitBackend()
        await backend.record_attempt("login", "1.2.3.4")
        mock_db_record.assert_awaited_once_with("login", "1.2.3.4")

    @pytest.mark.asyncio
    @patch('app.auth_routers.rate_limiters._db_count', new_callable=AsyncMock, return_value=3)
    async def test_count_recent_delegates_and_returns_value(self, mock_db_count):
        """Happy path: count_recent delegates to _db_count and returns its result."""
        from app.auth_routers.rate_limit_backend import PostgresRateLimitBackend
        backend = PostgresRateLimitBackend()
        result = await backend.count_recent("signup", "10.0.0.1", 3600)
        assert result == 3
        mock_db_count.assert_awaited_once_with("signup", "10.0.0.1", 3600)

    @pytest.mark.asyncio
    @patch('app.auth_routers.rate_limiters._db_count', new_callable=AsyncMock, return_value=0)
    async def test_count_recent_returns_zero_when_none(self, mock_db_count):
        """Edge case: count_recent returns 0 when no attempts recorded."""
        from app.auth_routers.rate_limit_backend import PostgresRateLimitBackend
        backend = PostgresRateLimitBackend()
        result = await backend.count_recent("mfa", "some-token", 300)
        assert result == 0

    @pytest.mark.asyncio
    @patch('app.auth_routers.rate_limiters._db_cleanup', new_callable=AsyncMock)
    async def test_cleanup_delegates_to_db_cleanup(self, mock_db_cleanup):
        """Happy path: cleanup() delegates to _db_cleanup()."""
        from app.auth_routers.rate_limit_backend import PostgresRateLimitBackend
        backend = PostgresRateLimitBackend()
        await backend.cleanup()
        mock_db_cleanup.assert_awaited_once()


class TestModuleSingleton:

    def test_singleton_exists_and_is_correct_type(self):
        """Happy path: module-level rate_limit_backend is PostgresRateLimitBackend."""
        from app.auth_routers.rate_limit_backend import rate_limit_backend, PostgresRateLimitBackend
        assert isinstance(rate_limit_backend, PostgresRateLimitBackend)

    def test_singleton_satisfies_protocol(self):
        """Happy path: rate_limit_backend isinstance check passes RateLimitBackend Protocol."""
        from app.auth_routers.rate_limit_backend import rate_limit_backend, RateLimitBackend
        assert isinstance(rate_limit_backend, RateLimitBackend)


class TestRedisRateLimitBackendStub:

    def test_redis_backend_is_importable(self):
        """Happy path: RedisRateLimitBackend class is importable."""
        from app.auth_routers.rate_limit_backend import RedisRateLimitBackend
        assert RedisRateLimitBackend is not None

    @pytest.mark.asyncio
    async def test_redis_record_attempt_raises(self):
        """Failure: RedisRateLimitBackend.record_attempt raises NotImplementedError."""
        from app.auth_routers.rate_limit_backend import RedisRateLimitBackend
        stub = RedisRateLimitBackend()
        with pytest.raises(NotImplementedError):
            await stub.record_attempt("login", "1.2.3.4")

    @pytest.mark.asyncio
    async def test_redis_count_recent_raises(self):
        """Failure: RedisRateLimitBackend.count_recent raises NotImplementedError."""
        from app.auth_routers.rate_limit_backend import RedisRateLimitBackend
        stub = RedisRateLimitBackend()
        with pytest.raises(NotImplementedError):
            await stub.count_recent("signup", "1.2.3.4", 3600)

    @pytest.mark.asyncio
    async def test_redis_cleanup_raises(self):
        """Failure: RedisRateLimitBackend.cleanup raises NotImplementedError."""
        from app.auth_routers.rate_limit_backend import RedisRateLimitBackend
        stub = RedisRateLimitBackend()
        with pytest.raises(NotImplementedError):
            await stub.cleanup()

    def test_redis_satisfies_protocol(self):
        """Edge case: RedisRateLimitBackend also satisfies RateLimitBackend Protocol."""
        from app.auth_routers.rate_limit_backend import RedisRateLimitBackend, RateLimitBackend
        assert isinstance(RedisRateLimitBackend(), RateLimitBackend)
