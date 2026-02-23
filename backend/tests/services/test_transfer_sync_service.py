"""
Tests for backend/app/services/transfer_sync_service.py

Tests syncing deposit/withdrawal transactions from Coinbase,
deduplication by external_id, and multi-account sync.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from app.models import Account, AccountTransfer, User
from app.services.transfer_sync_service import sync_transfers, sync_all_user_transfers


async def _create_user_and_account(db_session, email="transfer@test.com"):
    """Helper to create a User and CEX Account."""
    user = User(email=email, hashed_password="hash", is_active=True)
    db_session.add(user)
    await db_session.flush()

    account = Account(
        user_id=user.id, name="TestAccount", type="cex",
        is_active=True, api_key_name="key", api_private_key="secret",
        is_paper_trading=False,
    )
    db_session.add(account)
    await db_session.flush()
    return user, account


# ---------------------------------------------------------------------------
# sync_transfers
# ---------------------------------------------------------------------------


class TestSyncTransfers:
    """Tests for sync_transfers()."""

    @pytest.mark.asyncio
    @patch("app.services.transfer_sync_service.get_coinbase_for_account")
    async def test_happy_path_new_transfers(self, mock_get_coinbase, db_session):
        """Happy path: inserts new transfers from Coinbase."""
        user, account = await _create_user_and_account(db_session)

        mock_client = AsyncMock()
        mock_client.get_accounts = AsyncMock(return_value=[
            {"uuid": "cb-acct-1"}
        ])
        mock_client.get_deposit_withdrawals = AsyncMock(return_value=[
            {
                "external_id": "txn-001",
                "status": "completed",
                "transfer_type": "deposit",
                "amount": 1000.0,
                "currency": "USD",
                "amount_usd": 1000.0,
                "occurred_at": "2024-01-15T10:00:00Z",
            },
            {
                "external_id": "txn-002",
                "status": "completed",
                "transfer_type": "withdrawal",
                "amount": 0.5,
                "currency": "BTC",
                "amount_usd": 25000.0,
                "occurred_at": "2024-01-16T12:00:00Z",
            },
        ])
        mock_get_coinbase.return_value = mock_client

        count = await sync_transfers(db_session, user.id, account)
        assert count == 2

    @pytest.mark.asyncio
    @patch("app.services.transfer_sync_service.get_coinbase_for_account")
    async def test_deduplicates_existing_transfers(self, mock_get_coinbase, db_session):
        """Edge case: existing transfers are not re-inserted."""
        user, account = await _create_user_and_account(db_session, email="dedup@test.com")

        # Pre-insert a transfer
        existing = AccountTransfer(
            user_id=user.id,
            account_id=account.id,
            external_id="txn-existing",
            transfer_type="deposit",
            amount=500.0,
            currency="USD",
            occurred_at=datetime(2024, 1, 10),
            source="coinbase_api",
        )
        db_session.add(existing)
        await db_session.commit()

        mock_client = AsyncMock()
        mock_client.get_accounts = AsyncMock(return_value=[{"uuid": "acct-1"}])
        mock_client.get_deposit_withdrawals = AsyncMock(return_value=[
            {
                "external_id": "txn-existing",  # same as above
                "status": "completed",
                "transfer_type": "deposit",
                "amount": 500.0,
                "currency": "USD",
                "occurred_at": "2024-01-10T00:00:00Z",
            },
        ])
        mock_get_coinbase.return_value = mock_client

        count = await sync_transfers(db_session, user.id, account)
        assert count == 0  # nothing new

    @pytest.mark.asyncio
    @patch("app.services.transfer_sync_service.get_coinbase_for_account")
    async def test_skips_pending_transactions(self, mock_get_coinbase, db_session):
        """Edge case: non-completed transactions are skipped."""
        user, account = await _create_user_and_account(db_session, email="pending@test.com")

        mock_client = AsyncMock()
        mock_client.get_accounts = AsyncMock(return_value=[{"uuid": "acct-1"}])
        mock_client.get_deposit_withdrawals = AsyncMock(return_value=[
            {
                "external_id": "txn-pending",
                "status": "pending",  # not completed
                "transfer_type": "deposit",
                "amount": 100.0,
                "currency": "USD",
                "occurred_at": "2024-01-15T10:00:00Z",
            },
        ])
        mock_get_coinbase.return_value = mock_client

        count = await sync_transfers(db_session, user.id, account)
        assert count == 0

    @pytest.mark.asyncio
    @patch("app.services.transfer_sync_service.get_coinbase_for_account")
    async def test_skips_no_external_id(self, mock_get_coinbase, db_session):
        """Edge case: transfers without external_id are skipped."""
        user, account = await _create_user_and_account(db_session, email="noid@test.com")

        mock_client = AsyncMock()
        mock_client.get_accounts = AsyncMock(return_value=[{"uuid": "acct-1"}])
        mock_client.get_deposit_withdrawals = AsyncMock(return_value=[
            {
                "external_id": None,
                "status": "completed",
                "transfer_type": "deposit",
                "amount": 100.0,
                "currency": "USD",
                "occurred_at": "2024-01-15T10:00:00Z",
            },
        ])
        mock_get_coinbase.return_value = mock_client

        count = await sync_transfers(db_session, user.id, account)
        assert count == 0

    @pytest.mark.asyncio
    @patch("app.services.transfer_sync_service.get_coinbase_for_account")
    async def test_handles_invalid_date(self, mock_get_coinbase, db_session):
        """Failure: invalid date is skipped gracefully."""
        user, account = await _create_user_and_account(db_session, email="baddate@test.com")

        mock_client = AsyncMock()
        mock_client.get_accounts = AsyncMock(return_value=[{"uuid": "acct-1"}])
        mock_client.get_deposit_withdrawals = AsyncMock(return_value=[
            {
                "external_id": "txn-baddate",
                "status": "completed",
                "transfer_type": "deposit",
                "amount": 100.0,
                "currency": "USD",
                "occurred_at": "not-a-date",
            },
        ])
        mock_get_coinbase.return_value = mock_client

        count = await sync_transfers(db_session, user.id, account)
        assert count == 0

    @pytest.mark.asyncio
    @patch("app.services.transfer_sync_service.get_coinbase_for_account")
    async def test_client_creation_error_returns_zero(self, mock_get_coinbase, db_session):
        """Failure: exchange client creation error returns 0."""
        user, account = await _create_user_and_account(db_session, email="clienterr@test.com")
        mock_get_coinbase.side_effect = Exception("auth failed")

        count = await sync_transfers(db_session, user.id, account)
        assert count == 0

    @pytest.mark.asyncio
    @patch("app.services.transfer_sync_service.get_coinbase_for_account")
    async def test_get_accounts_error_returns_zero(self, mock_get_coinbase, db_session):
        """Failure: error fetching Coinbase accounts returns 0."""
        user, account = await _create_user_and_account(db_session, email="accterr@test.com")

        mock_client = AsyncMock()
        mock_client.get_accounts = AsyncMock(side_effect=Exception("rate limited"))
        mock_get_coinbase.return_value = mock_client

        count = await sync_transfers(db_session, user.id, account)
        assert count == 0

    @pytest.mark.asyncio
    @patch("app.services.transfer_sync_service.get_coinbase_for_account")
    async def test_default_since_is_90_days(self, mock_get_coinbase, db_session):
        """Edge case: default since is ~90 days ago."""
        user, account = await _create_user_and_account(db_session, email="since@test.com")

        mock_client = AsyncMock()
        mock_client.get_accounts = AsyncMock(return_value=[])
        mock_get_coinbase.return_value = mock_client

        count = await sync_transfers(db_session, user.id, account, since=None)
        assert count == 0
        # Just verify it didn't error — the default since is calculated internally


# ---------------------------------------------------------------------------
# sync_all_user_transfers
# ---------------------------------------------------------------------------


class TestSyncAllUserTransfers:
    """Tests for sync_all_user_transfers()."""

    @pytest.mark.asyncio
    @patch("app.services.transfer_sync_service.sync_transfers")
    async def test_syncs_all_active_accounts(self, mock_sync, db_session):
        """Happy path: syncs all active non-paper accounts."""
        user, acct1 = await _create_user_and_account(db_session, email="allsync@test.com")

        acct2 = Account(
            user_id=user.id, name="Account2", type="cex",
            is_active=True, is_paper_trading=False,
        )
        db_session.add(acct2)
        await db_session.flush()

        mock_sync.return_value = 3  # 3 transfers per account

        total = await sync_all_user_transfers(db_session, user.id)
        assert total == 6  # 3 + 3
        assert mock_sync.call_count == 2

    @pytest.mark.asyncio
    @patch("app.services.transfer_sync_service.sync_transfers")
    async def test_skips_paper_trading_accounts(self, mock_sync, db_session):
        """Edge case: paper trading accounts are not synced."""
        user = User(email="paper@sync.com", hashed_password="hash", is_active=True)
        db_session.add(user)
        await db_session.flush()

        paper_acct = Account(
            user_id=user.id, name="Paper", type="cex",
            is_active=True, is_paper_trading=True,
        )
        db_session.add(paper_acct)
        await db_session.flush()

        total = await sync_all_user_transfers(db_session, user.id)
        assert total == 0
        mock_sync.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.transfer_sync_service.sync_transfers")
    async def test_error_in_one_account_continues(self, mock_sync, db_session):
        """Failure: error syncing one account doesn't stop the others."""
        user, acct1 = await _create_user_and_account(db_session, email="errsync@test.com")

        acct2 = Account(
            user_id=user.id, name="Account2", type="cex",
            is_active=True, is_paper_trading=False,
        )
        db_session.add(acct2)
        await db_session.flush()

        # First account errors, second succeeds
        mock_sync.side_effect = [Exception("API down"), 5]

        total = await sync_all_user_transfers(db_session, user.id)
        assert total == 5  # Only from second account
