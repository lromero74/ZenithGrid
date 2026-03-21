"""
Tests for the separate read connection pool introduced in Phase 1.3.

Verifies:
1. read_engine and engine are distinct objects
2. read_async_session_maker and async_session_maker are distinct objects
3. get_read_db() yields a session backed by the read engine
4. get_db() yields a session backed by the write engine
5. The read engine has postgresql_readonly execution option set (PostgreSQL only)
6. The read engine pool is smaller than the write engine pool
"""
import pytest

from app.database import (
    async_session_maker,
    engine,
    get_db,
    get_read_db,
    read_async_session_maker,
    read_engine,
)


class TestReadEngineIsDistinct:
    """read_engine must be a separate engine object from the write engine."""

    def test_read_engine_is_not_write_engine(self):
        """Happy path: read_engine and engine are different objects."""
        assert read_engine is not engine

    def test_read_session_maker_is_not_write_session_maker(self):
        """Happy path: read_async_session_maker differs from async_session_maker."""
        assert read_async_session_maker is not async_session_maker


class TestReadEnginePoolConfig:
    """Read pool is sized smaller than the write pool (PostgreSQL only)."""

    def test_read_pool_size_is_smaller_than_write_pool(self):
        """Happy path: read pool_size <= write pool_size."""
        from app.config import settings

        if not settings.is_postgres:
            pytest.skip("Pool size check only applies to PostgreSQL")

        write_pool = engine.pool
        read_pool = read_engine.pool

        assert read_pool.size() <= write_pool.size()

    def test_read_pool_max_overflow_is_smaller_than_write(self):
        """Edge case: read max_overflow <= write max_overflow."""
        from app.config import settings

        if not settings.is_postgres:
            pytest.skip("Pool overflow check only applies to PostgreSQL")

        write_pool = engine.pool
        read_pool = read_engine.pool

        assert read_pool._max_overflow <= write_pool._max_overflow


class TestGetReadDbDependency:
    """get_read_db() must yield an AsyncSession from the read pool."""

    @pytest.mark.asyncio
    async def test_get_read_db_yields_session(self):
        """Happy path: get_read_db() yields an AsyncSession."""
        from sqlalchemy.ext.asyncio import AsyncSession

        gen = get_read_db()
        session = await gen.__anext__()
        assert isinstance(session, AsyncSession)
        try:
            await gen.aclose()
        except StopAsyncIteration:
            pass

    @pytest.mark.asyncio
    async def test_get_db_and_get_read_db_yield_different_sessions(self):
        """Happy path: get_db() and get_read_db() yield sessions from different pools."""
        write_gen = get_db()
        read_gen = get_read_db()

        write_session = await write_gen.__anext__()
        read_session = await read_gen.__anext__()

        # They must be distinct session objects
        assert write_session is not read_session

        # They must be bound to different engines
        assert write_session.bind is not read_session.bind

        try:
            await write_gen.aclose()
            await read_gen.aclose()
        except StopAsyncIteration:
            pass

    @pytest.mark.asyncio
    async def test_get_read_db_session_is_bound_to_read_engine(self):
        """Edge case: read session's engine is read_engine, not engine."""
        gen = get_read_db()
        session = await gen.__anext__()

        # The session's bind should trace back to read_engine
        assert session.get_bind() is read_engine.sync_engine or \
               session.sync_session.bind is read_engine.sync_engine

        try:
            await gen.aclose()
        except StopAsyncIteration:
            pass


class TestReadOnlyExecutionOption:
    """The read engine has postgresql_readonly set (PostgreSQL only)."""

    def test_read_engine_has_readonly_execution_option(self):
        """Happy path: read_engine carries postgresql_readonly=True."""
        from app.config import settings

        if not settings.is_postgres:
            pytest.skip("postgresql_readonly only applies to PostgreSQL")

        opts = read_engine.get_execution_options()
        assert opts.get("postgresql_readonly") is True

    def test_write_engine_does_not_have_readonly_option(self):
        """Edge case: the write engine must NOT have postgresql_readonly set."""
        opts = engine.get_execution_options()
        assert opts.get("postgresql_readonly") is not True
