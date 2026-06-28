"""Tests for app/services/rebalancer_gates.py — in-memory rebalancer gate
state, the mark_*/clear_* mutators, and the bot-rebalancer-group cache."""
import pytest
from unittest.mock import AsyncMock, MagicMock


# ===========================================================================
# Class: TestRebalancerFlags
# ===========================================================================


class TestRebalancerFlags:
    """Tests for is_rebalancer_gated() and is_rebalancer_bot_overweight()."""

    def test_is_rebalancer_gated_false_by_default(self):
        from app.services.rebalancer_gates import is_rebalancer_gated
        # Use a bot_id unlikely to be set by prior tests
        assert is_rebalancer_gated(98765) is False

    def test_is_rebalancer_gated_true_when_added(self):
        import app.services.rebalancer_gates as mod
        from app.services.rebalancer_gates import is_rebalancer_gated
        mod._gated_bots.add(99)
        try:
            assert is_rebalancer_gated(99) is True
        finally:
            mod._gated_bots.discard(99)

    def test_is_rebalancer_bot_overweight_false_by_default(self):
        from app.services.rebalancer_gates import is_rebalancer_bot_overweight
        assert is_rebalancer_bot_overweight(98765) is False

    def test_is_rebalancer_bot_overweight_true_when_added(self):
        import app.services.rebalancer_gates as mod
        from app.services.rebalancer_gates import is_rebalancer_bot_overweight
        mod._overweight_bots.add(77)
        try:
            assert is_rebalancer_bot_overweight(77) is True
        finally:
            mod._overweight_bots.discard(77)


# ===========================================================================
# Class: TestGetBotRebalancerGroup
# ===========================================================================


class TestGetBotRebalancerGroup:
    """Tests for get_bot_rebalancer_group() caching + DB fetch."""

    @pytest.mark.asyncio
    async def test_fetches_from_db_on_cache_miss(self, db_session):
        """Happy path: DB query runs on cache miss."""
        import app.services.rebalancer_gates as mod
        mod._group_cache.clear()

        from app.services.rebalancer_gates import get_bot_rebalancer_group

        # Mock the DB query path: return a fake group
        fake_group = MagicMock()
        fake_group.overweight_tolerance_pct = 7.0
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_group
        db = MagicMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_bot_rebalancer_group(db, 42, "USD")
        assert result is fake_group
        # Cache is populated
        assert (42, "USD") in mod._group_cache

    @pytest.mark.asyncio
    async def test_returns_cached_when_fresh(self, db_session):
        """Edge case: cached value returned without DB hit."""
        import time
        import app.services.rebalancer_gates as mod
        mod._group_cache.clear()

        cached_group = MagicMock()
        mod._group_cache[(42, "USD")] = (cached_group, time.monotonic())

        from app.services.rebalancer_gates import get_bot_rebalancer_group
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("should not be called"))

        result = await get_bot_rebalancer_group(db, 42, "USD")
        assert result is cached_group
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_refetches_when_cache_expired(self, db_session):
        """Edge case: expired cache triggers re-fetch."""
        import app.services.rebalancer_gates as mod
        mod._group_cache.clear()

        # Seed with a very old cache entry
        old_group = MagicMock()
        mod._group_cache[(42, "USD")] = (old_group, 0.0)  # monotonic=0 is ancient

        fresh_group = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fresh_group
        db = MagicMock()
        db.execute = AsyncMock(return_value=mock_result)

        from app.services.rebalancer_gates import get_bot_rebalancer_group
        result = await get_bot_rebalancer_group(db, 42, "USD")
        assert result is fresh_group


class TestClearFlushesGroupCache:
    """clear_rebalancer_gates_for_account must also flush that account's cached
    rebalancer-group rows (and only that account's)."""

    @pytest.mark.asyncio
    async def test_flushes_only_target_accounts_group_cache(self):
        import app.services.rebalancer_gates as mod
        mod._group_cache.clear()
        mod._group_cache[(42, "USD")] = ("group42", 123.0)
        mod._group_cache[(99, "USD")] = ("group99", 123.0)  # other account — must remain

        mock_result = MagicMock()
        mock_result.all.return_value = []  # no bots; cache flush is account-keyed
        db = MagicMock()
        db.execute = AsyncMock(return_value=mock_result)

        await mod.clear_rebalancer_gates_for_account(db, 42)

        assert (42, "USD") not in mod._group_cache
        assert (99, "USD") in mod._group_cache
