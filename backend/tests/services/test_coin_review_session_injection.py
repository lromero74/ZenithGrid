"""
Tests for session_maker injection through the coin review service call chain.

Verifies that every function that touches the DB accepts session_maker=None
and uses the injected maker instead of the module-level default.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGetCoinbaseClientFromDbInjection:
    """get_coinbase_client_from_db() uses injected session_maker."""

    @pytest.mark.asyncio
    async def test_uses_injected_session_maker(self):
        """Happy path: get_coinbase_client_from_db uses the provided session maker."""
        calls = []

        mock_account = MagicMock()
        mock_account.api_key_name = "key"
        mock_account.api_private_key = "secret"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_account

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        class MockSM:
            def __call__(self):
                calls.append(1)
                return mock_db

        with patch("app.services.coin_review_service.is_encrypted", return_value=False), \
             patch("app.services.coin_review_service.create_exchange_client", return_value=MagicMock()):
            from app.services.coin_review_service import get_coinbase_client_from_db
            await get_coinbase_client_from_db(session_maker=MockSM())

        assert len(calls) == 1, "Injected session_maker was never called"


class TestUpdateCoinStatusesInjection:
    """update_coin_statuses() uses injected session_maker."""

    @pytest.mark.asyncio
    async def test_uses_injected_session_maker(self):
        """Happy path: update_coin_statuses uses the provided session maker."""
        calls = []

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        class MockSM:
            def __call__(self):
                calls.append(1)
                return mock_db

        from app.services.coin_review_service import update_coin_statuses
        await update_coin_statuses({"BTC": {"category": "APPROVED", "reason": "test"}}, session_maker=MockSM())

        assert len(calls) == 1, "Injected session_maker was never called"


class TestGetLastReviewTimestampInjection:
    """_get_last_review_timestamp() uses injected session_maker."""

    @pytest.mark.asyncio
    async def test_uses_injected_session_maker(self):
        """Happy path: _get_last_review_timestamp uses the provided session maker."""
        calls = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        class MockSM:
            def __call__(self):
                calls.append(1)
                return mock_db

        from app.services.coin_review_service import _get_last_review_timestamp
        await _get_last_review_timestamp(session_maker=MockSM())

        assert len(calls) == 1, "Injected session_maker was never called"


class TestRunCoinReviewSchedulerInjection:
    """run_coin_review_scheduler() threads session_maker to inner functions."""

    @pytest.mark.asyncio
    async def test_threads_session_maker_to_helpers(self):
        """Happy path: session_maker is passed through to _get_last_review_timestamp."""
        injected = []

        async def mock_get_last_review(session_maker=None):
            injected.append(session_maker)
            return None  # no prior review → triggers run_weekly_review

        async def mock_run_weekly_review(standalone=False, session_maker=None):
            return {"status": "success", "coins_analyzed": 0, "categories": {}}

        import asyncio
        mock_sm = object()

        with patch("app.services.coin_review_service._get_last_review_timestamp", mock_get_last_review), \
             patch("app.services.coin_review_service.run_weekly_review", mock_run_weekly_review), \
             patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
            from app.services.coin_review_service import run_coin_review_scheduler
            with pytest.raises(asyncio.CancelledError):
                await run_coin_review_scheduler(session_maker=mock_sm)

        assert len(injected) >= 1
        assert injected[0] is mock_sm, "session_maker not threaded to _get_last_review_timestamp"
