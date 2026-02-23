"""
Tests for backend/app/position_routers/dependencies.py

Covers get_coinbase() dependency which retrieves the Coinbase client
for the authenticated user's active CEX account.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.models import Account, User


# =============================================================================
# get_coinbase dependency
# =============================================================================


class TestGetCoinbase:
    """Tests for get_coinbase()"""

    @pytest.mark.asyncio
    async def test_no_cex_account_raises_503(self, db_session):
        """Failure: user with no CEX account gets 503."""
        from fastapi import HTTPException
        from app.position_routers.dependencies import get_coinbase

        user = User(
            email="noaccount@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_coinbase(db=db_session, current_user=user)
        assert exc_info.value.status_code == 503
        assert "No Coinbase account" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_account_missing_api_key_raises_503(self, db_session):
        """Failure: account without API credentials returns 503."""
        from fastapi import HTTPException
        from app.position_routers.dependencies import get_coinbase

        user = User(
            email="nocreds@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id,
            name="No Creds",
            type="cex",
            exchange="coinbase",
            is_active=True,
            api_key_name=None,
            api_private_key=None,
        )
        db_session.add(account)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_coinbase(db=db_session, current_user=user)
        assert exc_info.value.status_code == 503
        assert "credentials" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_paper_trading_account_excluded(self, db_session):
        """Edge case: paper trading accounts are excluded from get_coinbase."""
        from fastapi import HTTPException
        from app.position_routers.dependencies import get_coinbase

        user = User(
            email="paperonly@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        # Only a paper trading account
        account = Account(
            user_id=user.id,
            name="Paper Account",
            type="cex",
            exchange="coinbase",
            is_active=True,
            is_paper_trading=True,
            api_key_name="key",
            api_private_key="secret",
        )
        db_session.add(account)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_coinbase(db=db_session, current_user=user)
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    @patch("app.position_routers.dependencies.create_exchange_client")
    @patch("app.position_routers.dependencies.is_encrypted", return_value=False)
    async def test_successful_client_creation(self, mock_is_enc, mock_create, db_session):
        """Happy path: returns exchange client for valid account."""
        from app.position_routers.dependencies import get_coinbase

        mock_client = MagicMock()
        mock_create.return_value = mock_client

        user = User(
            email="valid@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id,
            name="Real Account",
            type="cex",
            exchange="coinbase",
            is_active=True,
            api_key_name="my-key-name",
            api_private_key="my-private-key",
        )
        db_session.add(account)
        await db_session.flush()

        result = await get_coinbase(db=db_session, current_user=user)
        assert result == mock_client
        mock_create.assert_called_once_with(
            exchange_type="cex",
            coinbase_key_name="my-key-name",
            coinbase_private_key="my-private-key",
        )

    @pytest.mark.asyncio
    @patch("app.position_routers.dependencies.create_exchange_client")
    @patch("app.position_routers.dependencies.decrypt_value", return_value="decrypted-key")
    @patch("app.position_routers.dependencies.is_encrypted", return_value=True)
    async def test_decrypts_encrypted_private_key(self, mock_is_enc, mock_decrypt, mock_create, db_session):
        """Edge case: encrypted private key is decrypted before use."""
        from app.position_routers.dependencies import get_coinbase

        mock_client = MagicMock()
        mock_create.return_value = mock_client

        user = User(
            email="encrypted@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id,
            name="Encrypted Account",
            type="cex",
            exchange="coinbase",
            is_active=True,
            api_key_name="key-name",
            api_private_key="gAAAAA_encrypted_blob",
        )
        db_session.add(account)
        await db_session.flush()

        result = await get_coinbase(db=db_session, current_user=user)
        assert result == mock_client
        mock_decrypt.assert_called_once_with("gAAAAA_encrypted_blob")
        mock_create.assert_called_once_with(
            exchange_type="cex",
            coinbase_key_name="key-name",
            coinbase_private_key="decrypted-key",
        )

    @pytest.mark.asyncio
    @patch("app.position_routers.dependencies.create_exchange_client", return_value=None)
    @patch("app.position_routers.dependencies.is_encrypted", return_value=False)
    async def test_factory_returns_none_raises_503(self, mock_is_enc, mock_create, db_session):
        """Failure: exchange client factory returns None raises 503."""
        from fastapi import HTTPException
        from app.position_routers.dependencies import get_coinbase

        user = User(
            email="badclient@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id,
            name="Bad Client",
            type="cex",
            exchange="coinbase",
            is_active=True,
            api_key_name="key",
            api_private_key="secret",
        )
        db_session.add(account)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_coinbase(db=db_session, current_user=user)
        assert exc_info.value.status_code == 503
        assert "Failed to create" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_inactive_account_excluded(self, db_session):
        """Edge case: inactive accounts are excluded."""
        from fastapi import HTTPException
        from app.position_routers.dependencies import get_coinbase

        user = User(
            email="inactive@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id,
            name="Inactive",
            type="cex",
            exchange="coinbase",
            is_active=False,
            api_key_name="key",
            api_private_key="secret",
        )
        db_session.add(account)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_coinbase(db=db_session, current_user=user)
        assert exc_info.value.status_code == 503
