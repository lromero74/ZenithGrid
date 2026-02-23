"""
Tests for backend/app/services/account_snapshot_service.py

Covers:
- get_account_value_history — query snapshots by user, days, account, paper trading
- get_latest_snapshot — get most recent aggregated snapshot
- capture_account_snapshot (via mocked portfolio services)
- capture_all_account_snapshots aggregation
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.models import Account, AccountValueSnapshot, User
from app.services.account_snapshot_service import (
    get_account_value_history,
    get_latest_snapshot,
    capture_account_snapshot,
)


# ---------------------------------------------------------------------------
# Helper to seed test data
# ---------------------------------------------------------------------------


async def _create_user(db, email="test@example.com"):
    """Create a test user."""
    user = User(
        email=email,
        hashed_password="hashed",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _create_account(db, user_id, name="Test CEX", account_type="cex",
                          is_paper=False, is_active=True):
    """Create a test account."""
    account = Account(
        user_id=user_id,
        name=name,
        type=account_type,
        is_paper_trading=is_paper,
        is_active=is_active,
    )
    db.add(account)
    await db.flush()
    return account


async def _create_snapshot(db, account_id, user_id, date, btc_val, usd_val):
    """Create a test snapshot."""
    snap = AccountValueSnapshot(
        account_id=account_id,
        user_id=user_id,
        snapshot_date=date,
        total_value_btc=btc_val,
        total_value_usd=usd_val,
    )
    db.add(snap)
    await db.flush()
    return snap


# ---------------------------------------------------------------------------
# get_account_value_history
# ---------------------------------------------------------------------------


class TestGetAccountValueHistory:
    """Tests for get_account_value_history()"""

    @pytest.mark.asyncio
    async def test_returns_snapshots_for_user(self, db_session):
        """Happy path: returns snapshots ordered by date."""
        user = await _create_user(db_session)
        acct = await _create_account(db_session, user.id)
        date1 = datetime.utcnow() - timedelta(days=30)
        date2 = datetime.utcnow() - timedelta(days=29)
        await _create_snapshot(db_session, acct.id, user.id, date1, 1.0, 50000.0)
        await _create_snapshot(db_session, acct.id, user.id, date2, 1.1, 55000.0)
        await db_session.commit()

        result = await get_account_value_history(db_session, user.id, days=365)

        assert len(result) == 2
        assert len(result[0]["date"]) == 10  # YYYY-MM-DD format
        assert len(result[1]["date"]) == 10
        assert result[0]["total_value_btc"] == pytest.approx(1.0)
        assert result[1]["total_value_usd"] == pytest.approx(55000.0)

    @pytest.mark.asyncio
    async def test_filters_by_days(self, db_session):
        """Edge case: only snapshots within the day limit are returned."""
        user = await _create_user(db_session)
        acct = await _create_account(db_session, user.id)
        old_date = datetime.utcnow() - timedelta(days=400)
        recent_date = datetime.utcnow() - timedelta(days=10)
        await _create_snapshot(db_session, acct.id, user.id, old_date, 1.0, 50000.0)
        await _create_snapshot(db_session, acct.id, user.id, recent_date, 1.1, 55000.0)
        await db_session.commit()

        result = await get_account_value_history(db_session, user.id, days=30)

        assert len(result) == 1
        assert result[0]["total_value_btc"] == pytest.approx(1.1)

    @pytest.mark.asyncio
    async def test_excludes_paper_trading_by_default(self, db_session):
        """Edge case: paper trading accounts excluded by default."""
        user = await _create_user(db_session)
        real_acct = await _create_account(db_session, user.id, name="Real", is_paper=False)
        paper_acct = await _create_account(db_session, user.id, name="Paper", is_paper=True)
        date = datetime.utcnow() - timedelta(days=30)
        await _create_snapshot(db_session, real_acct.id, user.id, date, 1.0, 50000.0)
        await _create_snapshot(db_session, paper_acct.id, user.id, date, 10.0, 500000.0)
        await db_session.commit()

        result = await get_account_value_history(
            db_session, user.id, days=365, include_paper_trading=False
        )

        assert len(result) == 1
        assert result[0]["total_value_btc"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_includes_paper_trading_when_requested(self, db_session):
        """Edge case: paper trading included when flag is True."""
        user = await _create_user(db_session)
        real_acct = await _create_account(db_session, user.id, name="Real", is_paper=False)
        paper_acct = await _create_account(db_session, user.id, name="Paper", is_paper=True)
        date = datetime.utcnow() - timedelta(days=30)
        await _create_snapshot(db_session, real_acct.id, user.id, date, 1.0, 50000.0)
        await _create_snapshot(db_session, paper_acct.id, user.id, date, 10.0, 500000.0)
        await db_session.commit()

        result = await get_account_value_history(
            db_session, user.id, days=365, include_paper_trading=True
        )

        # Both accounts' snapshots are on the same date, so they should be aggregated
        assert len(result) == 1
        assert result[0]["total_value_btc"] == pytest.approx(11.0)

    @pytest.mark.asyncio
    async def test_single_account_mode(self, db_session):
        """Happy path: filter by specific account_id returns only that account."""
        user = await _create_user(db_session)
        acct1 = await _create_account(db_session, user.id, name="Acct1")
        acct2 = await _create_account(db_session, user.id, name="Acct2")
        date = datetime.utcnow() - timedelta(days=30)
        await _create_snapshot(db_session, acct1.id, user.id, date, 1.0, 50000.0)
        await _create_snapshot(db_session, acct2.id, user.id, date, 2.0, 100000.0)
        await db_session.commit()

        result = await get_account_value_history(
            db_session, user.id, days=365, account_id=acct1.id
        )

        assert len(result) == 1
        assert result[0]["total_value_btc"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_no_snapshots_returns_empty(self, db_session):
        """Failure: no snapshots for user returns empty list."""
        user = await _create_user(db_session)
        await db_session.commit()

        result = await get_account_value_history(db_session, user.id)
        assert result == []


# ---------------------------------------------------------------------------
# get_latest_snapshot
# ---------------------------------------------------------------------------


class TestGetLatestSnapshot:
    """Tests for get_latest_snapshot()"""

    @pytest.mark.asyncio
    async def test_returns_most_recent_snapshot(self, db_session):
        """Happy path: returns the latest snapshot."""
        user = await _create_user(db_session)
        acct = await _create_account(db_session, user.id)
        date1 = datetime.utcnow() - timedelta(days=30)
        date2 = datetime.utcnow() - timedelta(days=29)
        await _create_snapshot(db_session, acct.id, user.id, date1, 1.0, 50000.0)
        await _create_snapshot(db_session, acct.id, user.id, date2, 1.5, 75000.0)
        await db_session.commit()

        result = await get_latest_snapshot(db_session, user.id)

        assert result != {}
        assert result["date"] == date2.strftime("%Y-%m-%d")
        assert result["total_value_btc"] == pytest.approx(1.5)
        assert result["total_value_usd"] == pytest.approx(75000.0)

    @pytest.mark.asyncio
    async def test_no_snapshots_returns_empty_dict(self, db_session):
        """Failure: no snapshots returns empty dict."""
        user = await _create_user(db_session)
        await db_session.commit()

        result = await get_latest_snapshot(db_session, user.id)
        assert result == {}

    @pytest.mark.asyncio
    async def test_excludes_paper_trading_by_default(self, db_session):
        """Edge case: paper trading excluded from latest snapshot."""
        user = await _create_user(db_session)
        paper_acct = await _create_account(db_session, user.id, name="Paper", is_paper=True)
        date = datetime.utcnow() - timedelta(days=30)
        await _create_snapshot(db_session, paper_acct.id, user.id, date, 10.0, 500000.0)
        await db_session.commit()

        result = await get_latest_snapshot(db_session, user.id, include_paper_trading=False)
        assert result == {}


# ---------------------------------------------------------------------------
# capture_account_snapshot
# ---------------------------------------------------------------------------


class TestCaptureAccountSnapshot:
    """Tests for capture_account_snapshot()"""

    @pytest.mark.asyncio
    async def test_capture_paper_trading_snapshot(self, db_session):
        """Happy path: paper trading account creates snapshot via exchange client."""
        user = await _create_user(db_session)
        acct = await _create_account(db_session, user.id, name="Paper", is_paper=True)
        await db_session.commit()

        mock_client = AsyncMock()
        mock_client.calculate_aggregate_btc_value = AsyncMock(return_value=2.5)
        mock_client.calculate_aggregate_usd_value = AsyncMock(return_value=125000.0)

        with patch(
            "app.services.account_snapshot_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            result = await capture_account_snapshot(db_session, acct)

        assert result is True

        # Verify snapshot was created
        snaps = (await db_session.execute(
            select(AccountValueSnapshot).where(
                AccountValueSnapshot.account_id == acct.id
            )
        )).scalars().all()
        assert len(snaps) == 1
        assert snaps[0].total_value_btc == pytest.approx(2.5)
        assert snaps[0].total_value_usd == pytest.approx(125000.0)

    @pytest.mark.asyncio
    async def test_capture_paper_trading_no_client(self, db_session):
        """Failure: no exchange client returns False."""
        user = await _create_user(db_session)
        acct = await _create_account(db_session, user.id, name="Paper", is_paper=True)
        await db_session.commit()

        with patch(
            "app.services.account_snapshot_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await capture_account_snapshot(db_session, acct)

        assert result is False

    @pytest.mark.asyncio
    async def test_capture_unknown_account_type(self, db_session):
        """Failure: unknown account type returns False."""
        user = await _create_user(db_session)
        acct = await _create_account(db_session, user.id, name="Unknown", account_type="unknown")
        acct.is_paper_trading = False
        await db_session.commit()

        # Mock portfolio services to avoid import errors
        with patch(
            "app.services.account_snapshot_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
        ):
            result = await capture_account_snapshot(db_session, acct)

        assert result is False

    @pytest.mark.asyncio
    async def test_capture_updates_existing_snapshot(self, db_session):
        """Edge case: same-day snapshot is updated, not duplicated."""
        user = await _create_user(db_session)
        acct = await _create_account(db_session, user.id, name="Paper", is_paper=True)
        await db_session.commit()

        mock_client = AsyncMock()
        mock_client.calculate_aggregate_btc_value = AsyncMock(return_value=1.0)
        mock_client.calculate_aggregate_usd_value = AsyncMock(return_value=50000.0)

        with patch(
            "app.services.account_snapshot_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            # First capture
            await capture_account_snapshot(db_session, acct)

        # Update mock values
        mock_client.calculate_aggregate_btc_value = AsyncMock(return_value=2.0)
        mock_client.calculate_aggregate_usd_value = AsyncMock(return_value=100000.0)

        with patch(
            "app.services.account_snapshot_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            # Second capture same day
            await capture_account_snapshot(db_session, acct)

        # Should still be only one snapshot
        snaps = (await db_session.execute(
            select(AccountValueSnapshot).where(
                AccountValueSnapshot.account_id == acct.id
            )
        )).scalars().all()
        assert len(snaps) == 1
        assert snaps[0].total_value_btc == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_capture_exception_returns_false(self, db_session):
        """Failure: exception during capture returns False."""
        user = await _create_user(db_session)
        acct = await _create_account(db_session, user.id, name="Paper", is_paper=True)
        await db_session.commit()

        with patch(
            "app.services.account_snapshot_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Connection failed"),
        ):
            result = await capture_account_snapshot(db_session, acct)

        assert result is False
