"""
Tests for backend/app/services/account_value_summary_service.py

Covers:
- cached summary fast path
- snapshot fallback for paper accounts
- live summary refresh path
- bounded concurrency for paper-asset price lookups
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGetAccountValueSummary:
    """Tests for get_account_value_summary()."""

    @pytest.mark.asyncio
    async def test_returns_cached_paper_summary_without_refresh(self):
        """Happy path: cached paper summary returns immediately."""
        from app.services.account_value_summary_service import get_account_value_summary

        db = AsyncMock()
        user = MagicMock()
        user.id = 5

        account = MagicMock()
        account.id = 7
        account.is_paper_trading = True
        account.type = "cex"
        account.name = "Demo USD Paper"

        result_obj = MagicMock()
        result_obj.scalar_one_or_none.return_value = account
        db.execute.return_value = result_obj

        cached = {
            "account_id": 7,
            "total_usd_value": 1234.56,
            "total_btc_value": 0.01234,
            "btc_usd_price": 100000.0,
            "as_of": "2026-04-21T12:00:00",
            "is_stale": False,
            "is_refreshing": False,
        }

        with patch(
            "app.services.account_value_summary_service.api_cache.get",
            new=AsyncMock(return_value=cached),
        ), patch(
            "app.services.account_value_summary_service._build_live_paper_account_value_summary",
            new=AsyncMock(),
        ) as mock_build_live:
            result = await get_account_value_summary(db, user, account_id=7)

        assert result == cached
        mock_build_live.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_snapshot_fallback_for_paper_account(self):
        """Edge case: paper account with no summary cache falls back to latest snapshot."""
        from app.services.account_value_summary_service import get_account_value_summary

        db = AsyncMock()
        user = MagicMock()
        user.id = 5

        account = MagicMock()
        account.id = 7
        account.is_paper_trading = True
        account.type = "cex"
        account.name = "Demo USD Paper"

        snapshot = MagicMock()
        snapshot.total_value_usd = 1073.69
        snapshot.total_value_btc = 0.0112
        snapshot.btc_usd_price = 95842.12
        snapshot.snapshot_date.isoformat.return_value = "2026-04-21T00:00:00"

        account_result = MagicMock()
        account_result.scalar_one_or_none.return_value = account
        snapshot_result = MagicMock()
        snapshot_result.scalar_one_or_none.return_value = snapshot

        db.execute.side_effect = [account_result, snapshot_result]

        with patch(
            "app.services.account_value_summary_service.api_cache.get",
            new=AsyncMock(return_value=None),
        ), patch(
            "app.services.account_value_summary_service._build_live_paper_account_value_summary",
            new=AsyncMock(),
        ) as mock_build_live:
            result = await get_account_value_summary(db, user, account_id=7)

        assert result["account_id"] == 7
        assert result["total_usd_value"] == pytest.approx(1073.69)
        assert result["is_stale"] is True
        assert result["is_refreshing"] is False
        mock_build_live.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_fresh_builds_and_caches_live_paper_summary(self):
        """Happy path: force_fresh bypasses snapshot fallback and rebuilds live summary."""
        from app.services.account_value_summary_service import get_account_value_summary

        db = AsyncMock()
        user = MagicMock()
        user.id = 5

        account = MagicMock()
        account.id = 7
        account.is_paper_trading = True
        account.type = "cex"
        account.name = "Demo USD Paper"

        account_result = MagicMock()
        account_result.scalar_one_or_none.return_value = account
        db.execute.return_value = account_result

        live_summary = {
            "account_id": 7,
            "total_usd_value": 1500.0,
            "total_btc_value": 0.015,
            "btc_usd_price": 100000.0,
            "as_of": "2026-04-21T12:05:00",
            "is_stale": False,
            "is_refreshing": False,
        }

        with patch(
            "app.services.account_value_summary_service.api_cache.get",
            new=AsyncMock(return_value=None),
        ), patch(
            "app.services.account_value_summary_service.api_cache.set",
            new=AsyncMock(),
        ) as mock_cache_set, patch(
            "app.services.account_value_summary_service._build_live_paper_account_value_summary",
            new=AsyncMock(return_value=live_summary),
        ) as mock_build_live:
            result = await get_account_value_summary(db, user, account_id=7, force_fresh=True)

        assert result == live_summary
        mock_build_live.assert_called_once_with(account)
        mock_cache_set.assert_called_once()


class TestBuildLivePaperAccountValueSummary:
    """Tests for _build_live_paper_account_value_summary()."""

    @pytest.mark.asyncio
    async def test_limits_concurrent_price_fetches(self):
        """Happy path: live summary never exceeds the configured concurrency cap."""
        from app.services.account_value_summary_service import _build_live_paper_account_value_summary

        balances = {f"COIN{i}": 1.0 for i in range(12)}
        account = MagicMock()
        account.id = 42
        account.paper_balances = json.dumps(balances)

        in_flight = 0
        max_in_flight = 0

        async def fake_price(product_id: str):
            nonlocal in_flight, max_in_flight
            if product_id == "BTC-USD":
                return 100000.0
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await __import__("asyncio").sleep(0.01)
            in_flight -= 1
            return 10.0

        with patch(
            "app.services.account_value_summary_service.get_public_btc_usd_price",
            new=AsyncMock(return_value=100000.0),
        ), patch(
            "app.services.account_value_summary_service.get_public_price",
            new=AsyncMock(side_effect=fake_price),
        ):
            result = await _build_live_paper_account_value_summary(account)

        assert result["account_id"] == 42
        assert result["is_stale"] is False
        assert max_in_flight <= 5

    @pytest.mark.asyncio
    async def test_unsupported_symbol_uses_negative_cached_zero(self):
        """Failure case: unsupported symbols resolve to zero instead of raising."""
        from app.services.account_value_summary_service import _build_live_paper_account_value_summary

        account = MagicMock()
        account.id = 99
        account.paper_balances = json.dumps({"RONIN": 10.0, "USD": 50.0})

        async def fake_price(product_id: str):
            if product_id == "BTC-USD":
                return 100000.0
            raise ValueError(f"{product_id} not found (negative cached)")

        with patch(
            "app.services.account_value_summary_service.get_public_btc_usd_price",
            new=AsyncMock(return_value=100000.0),
        ), patch(
            "app.services.account_value_summary_service.get_public_price",
            new=AsyncMock(side_effect=fake_price),
        ):
            result = await _build_live_paper_account_value_summary(account)

        assert result["total_usd_value"] == pytest.approx(50.0)
        assert result["total_btc_value"] == pytest.approx(0.0005)
