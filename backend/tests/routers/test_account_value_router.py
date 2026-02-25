"""
Tests for backend/app/routers/account_value_router.py

Covers:
- GET /api/account-value/history — historical snapshots
- GET /api/account-value/latest — most recent snapshot
- POST /api/account-value/capture — manual snapshot trigger
- GET /api/account-value/activity — daily activity markers
- GET /api/account-value/reservations — bidirectional bot reservations
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.models import Account, User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def av_user(db_session):
    """Create a user with an account for account value tests."""
    user = User(
        email="acctval_test@example.com",
        hashed_password="hashed",
        display_name="AV Tester",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    account = Account(
        user_id=user.id,
        name="Live Account",
        type="cex",
        exchange="coinbase",
        is_active=True,
        is_paper_trading=False,
    )
    db_session.add(account)
    await db_session.flush()

    return user, account


# =============================================================================
# GET /api/account-value/history
# =============================================================================


class TestGetAccountValueHistory:
    """Tests for GET /api/account-value/history"""

    @pytest.mark.asyncio
    @patch("app.routers.account_value_router.account_snapshot_service")
    async def test_returns_history(self, mock_service, db_session, av_user):
        """Happy path: returns historical snapshots."""
        from app.routers.account_value_router import get_account_value_history

        user, _ = av_user
        mock_service.get_account_value_history = AsyncMock(return_value=[
            {"date": "2026-01-01", "total_usd": 10000.0},
            {"date": "2026-01-02", "total_usd": 10500.0},
        ])

        result = await get_account_value_history(
            days=365, include_paper_trading=False, account_id=None,
            db=db_session, current_user=user,
        )
        assert len(result) == 2
        assert result[0]["total_usd"] == 10000.0
        mock_service.get_account_value_history.assert_awaited_once_with(
            db_session, user.id, 365, False, None,
        )

    @pytest.mark.asyncio
    @patch("app.routers.account_value_router.account_snapshot_service")
    async def test_returns_history_with_account_filter(self, mock_service, db_session, av_user):
        """Edge case: account_id filter passes through."""
        from app.routers.account_value_router import get_account_value_history

        user, account = av_user
        mock_service.get_account_value_history = AsyncMock(return_value=[])

        result = await get_account_value_history(
            days=30, include_paper_trading=True, account_id=account.id,
            db=db_session, current_user=user,
        )
        assert result == []
        mock_service.get_account_value_history.assert_awaited_once_with(
            db_session, user.id, 30, True, account.id,
        )

    @pytest.mark.asyncio
    @patch("app.routers.account_value_router.account_snapshot_service")
    async def test_history_service_error_raises_500(self, mock_service, db_session, av_user):
        """Failure: service error raises HTTPException 500."""
        from fastapi import HTTPException
        from app.routers.account_value_router import get_account_value_history

        user, _ = av_user
        mock_service.get_account_value_history = AsyncMock(
            side_effect=Exception("DB error")
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_account_value_history(
                days=365, include_paper_trading=False, account_id=None,
                db=db_session, current_user=user,
            )
        assert exc_info.value.status_code == 500


# =============================================================================
# GET /api/account-value/latest
# =============================================================================


class TestGetLatestSnapshot:
    """Tests for GET /api/account-value/latest"""

    @pytest.mark.asyncio
    @patch("app.routers.account_value_router.account_snapshot_service")
    async def test_returns_latest_snapshot(self, mock_service, db_session, av_user):
        """Happy path: returns most recent snapshot."""
        from app.routers.account_value_router import get_latest_snapshot

        user, _ = av_user
        mock_service.get_latest_snapshot = AsyncMock(return_value={
            "date": "2026-02-25",
            "total_usd": 15000.0,
            "btc_value": 0.5,
        })

        result = await get_latest_snapshot(
            include_paper_trading=False, db=db_session, current_user=user,
        )
        assert result["total_usd"] == 15000.0
        mock_service.get_latest_snapshot.assert_awaited_once_with(
            db_session, user.id, False,
        )

    @pytest.mark.asyncio
    @patch("app.routers.account_value_router.account_snapshot_service")
    async def test_latest_with_paper_trading(self, mock_service, db_session, av_user):
        """Edge case: include_paper_trading flag is forwarded."""
        from app.routers.account_value_router import get_latest_snapshot

        user, _ = av_user
        mock_service.get_latest_snapshot = AsyncMock(return_value={})

        await get_latest_snapshot(
            include_paper_trading=True, db=db_session, current_user=user,
        )
        mock_service.get_latest_snapshot.assert_awaited_once_with(
            db_session, user.id, True,
        )

    @pytest.mark.asyncio
    @patch("app.routers.account_value_router.account_snapshot_service")
    async def test_latest_service_error_raises_500(self, mock_service, db_session, av_user):
        """Failure: service error raises HTTPException 500."""
        from fastapi import HTTPException
        from app.routers.account_value_router import get_latest_snapshot

        user, _ = av_user
        mock_service.get_latest_snapshot = AsyncMock(
            side_effect=Exception("Timeout")
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_latest_snapshot(
                include_paper_trading=False, db=db_session, current_user=user,
            )
        assert exc_info.value.status_code == 500


# =============================================================================
# POST /api/account-value/capture
# =============================================================================


class TestCaptureSnapshots:
    """Tests for POST /api/account-value/capture"""

    @pytest.mark.asyncio
    @patch("app.routers.account_value_router.account_snapshot_service")
    async def test_capture_returns_result(self, mock_service, db_session, av_user):
        """Happy path: returns capture result."""
        from app.routers.account_value_router import capture_snapshots

        user, _ = av_user
        mock_service.capture_all_account_snapshots = AsyncMock(return_value={
            "captured": 2,
            "accounts": ["Live Account", "Paper Account"],
        })

        result = await capture_snapshots(db=db_session, current_user=user)
        assert result["captured"] == 2
        mock_service.capture_all_account_snapshots.assert_awaited_once_with(
            db_session, user.id,
        )

    @pytest.mark.asyncio
    @patch("app.routers.account_value_router.account_snapshot_service")
    async def test_capture_service_error_raises_500(self, mock_service, db_session, av_user):
        """Failure: service error raises HTTPException 500."""
        from fastapi import HTTPException
        from app.routers.account_value_router import capture_snapshots

        user, _ = av_user
        mock_service.capture_all_account_snapshots = AsyncMock(
            side_effect=Exception("Exchange down")
        )

        with pytest.raises(HTTPException) as exc_info:
            await capture_snapshots(db=db_session, current_user=user)
        assert exc_info.value.status_code == 500


# =============================================================================
# GET /api/account-value/activity
# =============================================================================


class TestGetDailyActivity:
    """Tests for GET /api/account-value/activity"""

    @pytest.mark.asyncio
    @patch("app.routers.account_value_router.account_snapshot_service")
    async def test_returns_activity(self, mock_service, db_session, av_user):
        """Happy path: returns daily activity data."""
        from app.routers.account_value_router import get_daily_activity

        user, _ = av_user
        mock_service.get_daily_activity = AsyncMock(return_value=[
            {"date": "2026-01-15", "trades": 3, "deposits": 1},
        ])

        result = await get_daily_activity(
            days=365, include_paper_trading=False, account_id=None,
            db=db_session, current_user=user,
        )
        assert len(result) == 1
        assert result[0]["trades"] == 3

    @pytest.mark.asyncio
    @patch("app.routers.account_value_router.account_snapshot_service")
    async def test_activity_with_params(self, mock_service, db_session, av_user):
        """Edge case: all parameters forwarded correctly."""
        from app.routers.account_value_router import get_daily_activity

        user, account = av_user
        mock_service.get_daily_activity = AsyncMock(return_value=[])

        await get_daily_activity(
            days=30, include_paper_trading=True, account_id=account.id,
            db=db_session, current_user=user,
        )
        mock_service.get_daily_activity.assert_awaited_once_with(
            db_session, user.id, 30, True, account.id,
        )

    @pytest.mark.asyncio
    @patch("app.routers.account_value_router.account_snapshot_service")
    async def test_activity_service_error_raises_500(self, mock_service, db_session, av_user):
        """Failure: service error raises HTTPException 500."""
        from fastapi import HTTPException
        from app.routers.account_value_router import get_daily_activity

        user, _ = av_user
        mock_service.get_daily_activity = AsyncMock(
            side_effect=Exception("Error")
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_daily_activity(
                days=365, include_paper_trading=False, account_id=None,
                db=db_session, current_user=user,
            )
        assert exc_info.value.status_code == 500


# =============================================================================
# GET /api/account-value/reservations
# =============================================================================


class TestGetBidirectionalReservations:
    """Tests for GET /api/account-value/reservations"""

    @pytest.mark.asyncio
    @patch("app.services.budget_calculator.calculate_available_btc", new_callable=AsyncMock)
    @patch("app.services.budget_calculator.calculate_available_usd", new_callable=AsyncMock)
    @patch("app.services.exchange_service.get_exchange_client_for_account", new_callable=AsyncMock)
    async def test_returns_reservations(
        self, mock_get_exchange, mock_avail_usd, mock_avail_btc,
        db_session, av_user,
    ):
        """Happy path: returns reservation breakdown."""
        from app.routers.account_value_router import get_bidirectional_reservations

        user, account = av_user

        mock_exchange = AsyncMock()
        mock_exchange.get_usd_balance = AsyncMock(return_value=5000.0)
        mock_exchange.get_usdc_balance = AsyncMock(return_value=3000.0)
        mock_exchange.get_usdt_balance = AsyncMock(return_value=0.0)
        mock_exchange.get_btc_balance = AsyncMock(return_value=1.5)
        mock_exchange.get_btc_usd_price = AsyncMock(return_value=50000.0)
        mock_get_exchange.return_value = mock_exchange

        mock_avail_usd.return_value = 6000.0  # 8000 total - 2000 reserved
        mock_avail_btc.return_value = 1.0  # 1.5 total - 0.5 reserved

        result = await get_bidirectional_reservations(
            account_id=account.id, db=db_session, current_user=user,
        )

        assert result["account_id"] == account.id
        assert result["account_name"] == "Live Account"
        assert result["total_usd"] == 8000.0
        assert result["available_usd"] == 6000.0
        assert result["reserved_usd"] == 2000.0
        assert result["total_btc"] == 1.5
        assert result["available_btc"] == 1.0
        assert result["reserved_btc"] == 0.5
        assert result["btc_usd_price"] == 50000.0

    @pytest.mark.asyncio
    async def test_reservations_account_not_found(self, db_session, av_user):
        """Failure: non-existent account returns 404."""
        from fastapi import HTTPException
        from app.routers.account_value_router import get_bidirectional_reservations

        user, _ = av_user
        with pytest.raises(HTTPException) as exc_info:
            await get_bidirectional_reservations(
                account_id=99999, db=db_session, current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_reservations_other_users_account(self, db_session, av_user):
        """Security: cannot access another user's account."""
        from fastapi import HTTPException
        from app.routers.account_value_router import get_bidirectional_reservations

        _, account = av_user

        other_user = User(
            email="other_av@example.com",
            hashed_password="hashed",
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_bidirectional_reservations(
                account_id=account.id, db=db_session, current_user=other_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.services.exchange_service.get_exchange_client_for_account", new_callable=AsyncMock)
    async def test_reservations_no_exchange_client(self, mock_get_exchange, db_session, av_user):
        """Failure: no exchange client returns 400."""
        from fastapi import HTTPException
        from app.routers.account_value_router import get_bidirectional_reservations

        user, account = av_user
        mock_get_exchange.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_bidirectional_reservations(
                account_id=account.id, db=db_session, current_user=user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("app.services.exchange_service.get_exchange_client_for_account", new_callable=AsyncMock)
    async def test_reservations_exchange_error_raises_500(self, mock_get_exchange, db_session, av_user):
        """Failure: exchange error raises HTTPException 500."""
        from fastapi import HTTPException
        from app.routers.account_value_router import get_bidirectional_reservations

        user, account = av_user
        mock_get_exchange.side_effect = RuntimeError("Connection refused")

        with pytest.raises(HTTPException) as exc_info:
            await get_bidirectional_reservations(
                account_id=account.id, db=db_session, current_user=user,
            )
        assert exc_info.value.status_code == 500
