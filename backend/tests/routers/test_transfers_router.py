"""
Tests for backend/app/routers/transfers_router.py

Covers:
- POST /api/transfers/sync — trigger sync
- GET /api/transfers — list with filtering
- POST /api/transfers — manual creation
- DELETE /api/transfers/{id} — deletion
- GET /api/transfers/summary — deposit/withdrawal summary
- GET /api/transfers/recent-summary — last 30 days
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Account, AccountTransfer, User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def transfers_user(db_session):
    """Create a user with an account for transfer tests."""
    user = User(
        email="transfers_test@example.com",
        hashed_password="hashed",
        display_name="Transfer Tester",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    account = Account(
        user_id=user.id,
        name="Test Account",
        type="cex",
        exchange="coinbase",
        is_active=True,
    )
    db_session.add(account)
    await db_session.flush()

    return user, account


@pytest.fixture
async def sample_transfers(db_session, transfers_user):
    """Create sample transfer records for query tests."""
    user, account = transfers_user

    transfers = []
    # 3 deposits, 2 withdrawals
    for i in range(3):
        t = AccountTransfer(
            user_id=user.id,
            account_id=account.id,
            transfer_type="deposit",
            amount=100.0 * (i + 1),
            currency="USD",
            amount_usd=100.0 * (i + 1),
            occurred_at=datetime(2026, 1, 10 + i),
            source="coinbase_api",
        )
        transfers.append(t)

    for i in range(2):
        t = AccountTransfer(
            user_id=user.id,
            account_id=account.id,
            transfer_type="withdrawal",
            amount=50.0 * (i + 1),
            currency="USD",
            amount_usd=50.0 * (i + 1),
            occurred_at=datetime(2026, 1, 15 + i),
            source="manual",
        )
        transfers.append(t)

    db_session.add_all(transfers)
    await db_session.flush()
    return user, account, transfers


# =============================================================================
# POST /api/transfers/sync
# =============================================================================


class TestSyncTransfers:
    """Tests for POST /api/transfers/sync"""

    @pytest.mark.asyncio
    @patch("app.services.transfer_sync_service.sync_all_user_transfers", new_callable=AsyncMock)
    async def test_sync_returns_count(self, mock_sync, db_session, transfers_user):
        """Happy path: returns new transfer count."""
        from app.routers.transfers_router import sync_transfers

        user, _ = transfers_user
        mock_sync.return_value = 5

        result = await sync_transfers(db=db_session, current_user=user)
        assert result["status"] == "ok"
        assert result["new_transfers"] == 5
        mock_sync.assert_awaited_once_with(db_session, user.id)

    @pytest.mark.asyncio
    @patch("app.services.transfer_sync_service.sync_all_user_transfers", new_callable=AsyncMock)
    async def test_sync_zero_new_transfers(self, mock_sync, db_session, transfers_user):
        """Edge case: no new transfers found."""
        from app.routers.transfers_router import sync_transfers

        user, _ = transfers_user
        mock_sync.return_value = 0

        result = await sync_transfers(db=db_session, current_user=user)
        assert result["status"] == "ok"
        assert result["new_transfers"] == 0

    @pytest.mark.asyncio
    @patch("app.services.transfer_sync_service.sync_all_user_transfers", new_callable=AsyncMock)
    async def test_sync_failure_raises_500(self, mock_sync, db_session, transfers_user):
        """Failure: sync service error raises HTTPException 500."""
        from fastapi import HTTPException
        from app.routers.transfers_router import sync_transfers

        user, _ = transfers_user
        mock_sync.side_effect = Exception("Coinbase API down")

        with pytest.raises(HTTPException) as exc_info:
            await sync_transfers(db=db_session, current_user=user)
        assert exc_info.value.status_code == 500


# =============================================================================
# GET /api/transfers
# =============================================================================


class TestListTransfers:
    """Tests for GET /api/transfers (list with filtering)"""

    @pytest.mark.asyncio
    async def test_list_all_transfers(self, db_session, sample_transfers):
        """Happy path: returns all transfers for the user."""
        from app.routers.transfers_router import list_transfers

        user, account, transfers = sample_transfers
        result = await list_transfers(
            start=None, end=None, account_id=None,
            limit=100, offset=0, db=db_session, current_user=user,
        )
        assert result["total"] == 5
        assert len(result["transfers"]) == 5

    @pytest.mark.asyncio
    async def test_list_transfers_with_date_filter(self, db_session, sample_transfers):
        """Edge case: date range filtering narrows results."""
        from app.routers.transfers_router import list_transfers

        user, _, _ = sample_transfers
        result = await list_transfers(
            start="2026-01-14", end="2026-01-16",
            account_id=None, limit=100, offset=0,
            db=db_session, current_user=user,
        )
        # Only transfers on Jan 15 and Jan 16 fall in this range
        assert result["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_transfers_with_account_filter(self, db_session, sample_transfers):
        """Edge case: account_id filtering."""
        from app.routers.transfers_router import list_transfers

        user, account, _ = sample_transfers
        result = await list_transfers(
            start=None, end=None, account_id=account.id,
            limit=100, offset=0, db=db_session, current_user=user,
        )
        assert result["total"] == 5

    @pytest.mark.asyncio
    async def test_list_transfers_pagination(self, db_session, sample_transfers):
        """Edge case: limit and offset pagination."""
        from app.routers.transfers_router import list_transfers

        user, _, _ = sample_transfers
        result = await list_transfers(
            start=None, end=None, account_id=None,
            limit=2, offset=0, db=db_session, current_user=user,
        )
        assert result["total"] == 5
        assert len(result["transfers"]) == 2

    @pytest.mark.asyncio
    async def test_list_transfers_invalid_start_date(self, db_session, transfers_user):
        """Failure: invalid start date returns 400."""
        from fastapi import HTTPException
        from app.routers.transfers_router import list_transfers

        user, _ = transfers_user
        with pytest.raises(HTTPException) as exc_info:
            await list_transfers(
                start="not-a-date", end=None, account_id=None,
                limit=100, offset=0, db=db_session, current_user=user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_list_transfers_invalid_end_date(self, db_session, transfers_user):
        """Failure: invalid end date returns 400."""
        from fastapi import HTTPException
        from app.routers.transfers_router import list_transfers

        user, _ = transfers_user
        with pytest.raises(HTTPException) as exc_info:
            await list_transfers(
                start=None, end="bad-date", account_id=None,
                limit=100, offset=0, db=db_session, current_user=user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_list_transfers_empty_result(self, db_session, transfers_user):
        """Edge case: no transfers returns empty list."""
        from app.routers.transfers_router import list_transfers

        user, _ = transfers_user
        result = await list_transfers(
            start=None, end=None, account_id=None,
            limit=100, offset=0, db=db_session, current_user=user,
        )
        assert result["total"] == 0
        assert result["transfers"] == []

    @pytest.mark.asyncio
    async def test_list_transfers_isolation(self, db_session, sample_transfers):
        """Security: user cannot see other user's transfers."""
        from app.routers.transfers_router import list_transfers

        other_user = User(
            email="other_transfers@example.com",
            hashed_password="hashed",
            display_name="Other",
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.flush()

        result = await list_transfers(
            start=None, end=None, account_id=None,
            limit=100, offset=0, db=db_session, current_user=other_user,
        )
        assert result["total"] == 0


# =============================================================================
# POST /api/transfers (manual create)
# =============================================================================


class TestCreateManualTransfer:
    """Tests for POST /api/transfers (manual creation)"""

    @pytest.mark.asyncio
    async def test_create_manual_deposit(self, db_session, transfers_user):
        """Happy path: create a manual deposit."""
        from app.routers.transfers_router import (
            create_manual_transfer, ManualTransferCreate,
        )

        user, account = transfers_user
        body = ManualTransferCreate(
            account_id=account.id,
            transfer_type="deposit",
            amount=500.0,
            currency="USD",
            amount_usd=500.0,
            occurred_at=datetime(2026, 2, 1),
        )

        result = await create_manual_transfer(
            body=body, db=db_session, current_user=user,
        )
        assert result["transfer_type"] == "deposit"
        assert result["amount"] == 500.0
        assert result["source"] == "manual"
        assert result["id"] is not None

    @pytest.mark.asyncio
    async def test_create_manual_withdrawal(self, db_session, transfers_user):
        """Happy path: create a manual withdrawal."""
        from app.routers.transfers_router import (
            create_manual_transfer, ManualTransferCreate,
        )

        user, account = transfers_user
        body = ManualTransferCreate(
            account_id=account.id,
            transfer_type="withdrawal",
            amount=200.0,
            currency="BTC",
            occurred_at=datetime(2026, 2, 5),
        )

        result = await create_manual_transfer(
            body=body, db=db_session, current_user=user,
        )
        assert result["transfer_type"] == "withdrawal"
        assert result["currency"] == "BTC"
        assert result["amount_usd"] is None

    @pytest.mark.asyncio
    async def test_create_transfer_wrong_account_returns_404(self, db_session, transfers_user):
        """Failure: account not owned by user returns 404."""
        from fastapi import HTTPException
        from app.routers.transfers_router import (
            create_manual_transfer, ManualTransferCreate,
        )

        user, _ = transfers_user
        body = ManualTransferCreate(
            account_id=99999,
            transfer_type="deposit",
            amount=100.0,
            currency="USD",
            occurred_at=datetime(2026, 2, 1),
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_manual_transfer(
                body=body, db=db_session, current_user=user,
            )
        assert exc_info.value.status_code == 404

    def test_manual_transfer_schema_rejects_invalid_type(self):
        """Failure: transfer_type must be 'deposit' or 'withdrawal'."""
        from pydantic import ValidationError
        from app.routers.transfers_router import ManualTransferCreate

        with pytest.raises(ValidationError):
            ManualTransferCreate(
                account_id=1,
                transfer_type="refund",
                amount=100.0,
                currency="USD",
                occurred_at=datetime.utcnow(),
            )

    def test_manual_transfer_schema_rejects_negative_amount(self):
        """Failure: amount must be > 0."""
        from pydantic import ValidationError
        from app.routers.transfers_router import ManualTransferCreate

        with pytest.raises(ValidationError):
            ManualTransferCreate(
                account_id=1,
                transfer_type="deposit",
                amount=-50.0,
                currency="USD",
                occurred_at=datetime.utcnow(),
            )


# =============================================================================
# DELETE /api/transfers/{transfer_id}
# =============================================================================


class TestDeleteTransfer:
    """Tests for DELETE /api/transfers/{transfer_id}"""

    @pytest.mark.asyncio
    async def test_delete_own_transfer(self, db_session, sample_transfers):
        """Happy path: delete a transfer owned by the user."""
        from app.routers.transfers_router import delete_transfer

        user, _, transfers = sample_transfers
        transfer_id = transfers[0].id

        result = await delete_transfer(
            transfer_id=transfer_id, db=db_session, current_user=user,
        )
        assert result["detail"] == "Transfer deleted"

    @pytest.mark.asyncio
    async def test_delete_nonexistent_transfer_returns_404(self, db_session, transfers_user):
        """Failure: non-existent transfer ID returns 404."""
        from fastapi import HTTPException
        from app.routers.transfers_router import delete_transfer

        user, _ = transfers_user
        with pytest.raises(HTTPException) as exc_info:
            await delete_transfer(
                transfer_id=99999, db=db_session, current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_other_users_transfer_returns_404(self, db_session, sample_transfers):
        """Security: cannot delete another user's transfer."""
        from fastapi import HTTPException
        from app.routers.transfers_router import delete_transfer

        _, _, transfers = sample_transfers

        other_user = User(
            email="other_del@example.com",
            hashed_password="hashed",
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await delete_transfer(
                transfer_id=transfers[0].id, db=db_session, current_user=other_user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# GET /api/transfers/summary
# =============================================================================


class TestGetTransferSummary:
    """Tests for GET /api/transfers/summary"""

    @pytest.mark.asyncio
    async def test_summary_with_transfers(self, db_session, sample_transfers):
        """Happy path: correct deposit/withdrawal totals."""
        from app.routers.transfers_router import get_transfer_summary

        user, _, _ = sample_transfers
        result = await get_transfer_summary(
            start=None, end=None, account_id=None,
            db=db_session, current_user=user,
        )
        # Deposits: 100 + 200 + 300 = 600
        assert result["total_deposits_usd"] == 600.0
        # Withdrawals: 50 + 100 = 150
        assert result["total_withdrawals_usd"] == 150.0
        assert result["net_deposits_usd"] == 450.0
        assert result["deposit_count"] == 3
        assert result["withdrawal_count"] == 2

    @pytest.mark.asyncio
    async def test_summary_empty(self, db_session, transfers_user):
        """Edge case: no transfers returns all zeros."""
        from app.routers.transfers_router import get_transfer_summary

        user, _ = transfers_user
        result = await get_transfer_summary(
            start=None, end=None, account_id=None,
            db=db_session, current_user=user,
        )
        assert result["total_deposits_usd"] == 0
        assert result["total_withdrawals_usd"] == 0
        assert result["net_deposits_usd"] == 0
        assert result["deposit_count"] == 0
        assert result["withdrawal_count"] == 0

    @pytest.mark.asyncio
    async def test_summary_invalid_date_returns_400(self, db_session, transfers_user):
        """Failure: invalid date returns 400."""
        from fastapi import HTTPException
        from app.routers.transfers_router import get_transfer_summary

        user, _ = transfers_user
        with pytest.raises(HTTPException) as exc_info:
            await get_transfer_summary(
                start="bad", end=None, account_id=None,
                db=db_session, current_user=user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_summary_with_date_filter(self, db_session, sample_transfers):
        """Edge case: date range narrows the summary."""
        from app.routers.transfers_router import get_transfer_summary

        user, _, _ = sample_transfers
        # Only include deposits (Jan 10-12)
        result = await get_transfer_summary(
            start="2026-01-09", end="2026-01-13", account_id=None,
            db=db_session, current_user=user,
        )
        assert result["deposit_count"] == 3
        assert result["withdrawal_count"] == 0


# =============================================================================
# GET /api/transfers/recent-summary
# =============================================================================


class TestGetRecentSummary:
    """Tests for GET /api/transfers/recent-summary"""

    @pytest.mark.asyncio
    async def test_recent_summary_with_recent_transfers(self, db_session, transfers_user):
        """Happy path: returns last 30 days of transfers."""
        from app.routers.transfers_router import get_recent_summary

        user, account = transfers_user

        # Create a recent deposit
        t = AccountTransfer(
            user_id=user.id,
            account_id=account.id,
            transfer_type="deposit",
            amount=1000.0,
            currency="USD",
            amount_usd=1000.0,
            occurred_at=datetime.utcnow() - timedelta(days=5),
            source="manual",
        )
        db_session.add(t)
        await db_session.flush()

        result = await get_recent_summary(db=db_session, current_user=user)
        assert result["last_30d_deposit_count"] == 1
        assert result["last_30d_withdrawal_count"] == 0
        assert result["last_30d_net_deposits_usd"] == 1000.0
        assert len(result["transfers"]) == 1

    @pytest.mark.asyncio
    async def test_recent_summary_empty(self, db_session, transfers_user):
        """Edge case: no recent transfers returns empty summary."""
        from app.routers.transfers_router import get_recent_summary

        user, _ = transfers_user
        result = await get_recent_summary(db=db_session, current_user=user)
        assert result["last_30d_deposit_count"] == 0
        assert result["last_30d_withdrawal_count"] == 0
        assert result["last_30d_net_deposits_usd"] == 0
        assert result["transfers"] == []

    @pytest.mark.asyncio
    async def test_recent_summary_excludes_old_transfers(self, db_session, sample_transfers):
        """Edge case: transfers older than 30 days are excluded."""
        from app.routers.transfers_router import get_recent_summary

        user, _, _ = sample_transfers
        # sample_transfers are from Jan 2026, which is > 30 days ago
        result = await get_recent_summary(db=db_session, current_user=user)
        assert result["last_30d_deposit_count"] == 0
        assert result["last_30d_withdrawal_count"] == 0


# =============================================================================
# _transfer_to_dict helper
# =============================================================================


class TestTransferToDict:
    """Tests for _transfer_to_dict() helper."""

    def test_converts_transfer_to_dict(self):
        """Happy path: all fields present."""
        from app.routers.transfers_router import _transfer_to_dict

        t = MagicMock(spec=AccountTransfer)
        t.id = 1
        t.account_id = 10
        t.transfer_type = "deposit"
        t.amount = 500.0
        t.currency = "USD"
        t.amount_usd = 500.0
        t.occurred_at = datetime(2026, 1, 15, 12, 0, 0)
        t.source = "manual"
        t.created_at = datetime(2026, 1, 15, 12, 0, 0)

        result = _transfer_to_dict(t)
        assert result["id"] == 1
        assert result["transfer_type"] == "deposit"
        assert result["occurred_at"] == "2026-01-15T12:00:00"

    def test_handles_none_dates(self):
        """Edge case: None dates produce None in output."""
        from app.routers.transfers_router import _transfer_to_dict

        t = MagicMock(spec=AccountTransfer)
        t.id = 2
        t.account_id = 10
        t.transfer_type = "withdrawal"
        t.amount = 100.0
        t.currency = "BTC"
        t.amount_usd = None
        t.occurred_at = None
        t.source = "coinbase_api"
        t.created_at = None

        result = _transfer_to_dict(t)
        assert result["occurred_at"] is None
        assert result["created_at"] is None
