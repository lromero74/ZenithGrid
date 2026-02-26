"""
Tests for backend/app/services/exchange_service.py

Tests exchange client creation, caching, account lookups, and
account creation/update logic.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.exceptions import ExchangeUnavailableError, ValidationError

from app.models import Account, User
from app.services.exchange_service import (
    get_coinbase_for_account,
    clear_exchange_client_cache,
    get_exchange_client_for_account,
    get_exchange_client_for_user,
    get_default_cex_account,
    create_or_update_cex_account,
    _exchange_client_cache,
)


async def _create_user_and_account(
    db_session,
    email="exch@test.com",
    account_type="cex",
    is_active=True,
    is_default=True,
    api_key="key123",
    api_private_key="secret123",
    exchange="coinbase",
    is_paper=False,
):
    """Helper to create a User and Account."""
    user = User(email=email, hashed_password="hash", is_active=True)
    db_session.add(user)
    await db_session.flush()

    account = Account(
        user_id=user.id,
        name="TestAccount",
        type=account_type,
        is_active=is_active,
        is_default=is_default,
        api_key_name=api_key,
        api_private_key=api_private_key,
        exchange=exchange,
        is_paper_trading=is_paper,
    )
    db_session.add(account)
    await db_session.flush()
    return user, account


# ---------------------------------------------------------------------------
# get_coinbase_for_account
# ---------------------------------------------------------------------------


class TestGetCoinbaseForAccount:
    """Tests for get_coinbase_for_account()."""

    @pytest.mark.asyncio
    @patch("app.services.exchange_service.create_exchange_client")
    @patch("app.services.exchange_service.is_encrypted", return_value=False)
    async def test_happy_path(self, mock_enc, mock_create, db_session):
        """Happy path: returns exchange client for valid CEX account."""
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        _, account = await _create_user_and_account(db_session)

        client = await get_coinbase_for_account(account)
        assert client is mock_client
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_cex_account_raises(self, db_session):
        """Failure: non-CEX account raises ValidationError."""
        _, account = await _create_user_and_account(
            db_session, email="dex@test.com", account_type="dex"
        )

        with pytest.raises(ValidationError) as exc_info:
            await get_coinbase_for_account(account)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_credentials_raises(self, db_session):
        """Failure: missing API credentials raises ExchangeUnavailableError."""
        _, account = await _create_user_and_account(
            db_session, email="nocred@test.com", api_key=None, api_private_key=None
        )

        with pytest.raises(ExchangeUnavailableError) as exc_info:
            await get_coinbase_for_account(account)
        assert exc_info.value.status_code == 503
        assert "missing API credentials" in exc_info.value.message

    @pytest.mark.asyncio
    @patch("app.services.exchange_service.create_exchange_client", return_value=None)
    @patch("app.services.exchange_service.is_encrypted", return_value=False)
    async def test_factory_returns_none_raises(self, mock_enc, mock_create, db_session):
        """Failure: factory returning None raises ExchangeUnavailableError."""
        _, account = await _create_user_and_account(db_session, email="badclient@test.com")

        with pytest.raises(ExchangeUnavailableError) as exc_info:
            await get_coinbase_for_account(account)
        assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# clear_exchange_client_cache
# ---------------------------------------------------------------------------


class TestClearExchangeClientCache:
    """Tests for clear_exchange_client_cache()."""

    def test_clear_specific_account(self):
        """Happy path: clears single account from cache."""
        _exchange_client_cache[99] = MagicMock()
        _exchange_client_cache[100] = MagicMock()

        with patch("app.services.exchange_service.clear_monitor_exchange_cache", create=True):
            clear_exchange_client_cache(account_id=99)

        assert 99 not in _exchange_client_cache
        assert 100 in _exchange_client_cache
        # Cleanup
        _exchange_client_cache.pop(100, None)

    def test_clear_all(self):
        """Happy path: clears entire cache."""
        _exchange_client_cache[101] = MagicMock()
        _exchange_client_cache[102] = MagicMock()

        with patch("app.services.exchange_service.clear_monitor_exchange_cache", create=True):
            clear_exchange_client_cache()

        assert len(_exchange_client_cache) == 0

    def test_clear_nonexistent_account_no_error(self):
        """Edge case: clearing nonexistent account doesn't error."""
        with patch("app.services.exchange_service.clear_monitor_exchange_cache", create=True):
            clear_exchange_client_cache(account_id=999)  # no-op


# ---------------------------------------------------------------------------
# get_exchange_client_for_account
# ---------------------------------------------------------------------------


class TestGetExchangeClientForAccount:
    """Tests for get_exchange_client_for_account()."""

    @pytest.mark.asyncio
    @patch("app.services.exchange_service.create_exchange_client")
    @patch("app.services.exchange_service.is_encrypted", return_value=False)
    async def test_creates_coinbase_client(self, mock_enc, mock_create, db_session):
        """Happy path: creates and caches Coinbase client."""
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        _, account = await _create_user_and_account(
            db_session, email="cb@test.com"
        )

        # Ensure not cached
        _exchange_client_cache.pop(account.id, None)

        client = await get_exchange_client_for_account(db_session, account.id)
        assert client is mock_client
        assert _exchange_client_cache.get(account.id) is mock_client

        # Cleanup
        _exchange_client_cache.pop(account.id, None)

    @pytest.mark.asyncio
    async def test_returns_cached_client(self, db_session):
        """Happy path: returns cached client without DB query."""
        mock_client = MagicMock()
        _exchange_client_cache[777] = mock_client

        client = await get_exchange_client_for_account(db_session, 777)
        assert client is mock_client

        # Cleanup
        _exchange_client_cache.pop(777, None)

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_account(self, db_session):
        """Edge case: nonexistent account returns None."""
        _exchange_client_cache.pop(99999, None)
        client = await get_exchange_client_for_account(db_session, 99999, use_cache=False)
        assert client is None

    @pytest.mark.asyncio
    async def test_returns_none_for_inactive_account(self, db_session):
        """Edge case: inactive account returns None."""
        _, account = await _create_user_and_account(
            db_session, email="inactive@test.com", is_active=False
        )
        _exchange_client_cache.pop(account.id, None)

        client = await get_exchange_client_for_account(db_session, account.id, use_cache=False)
        assert client is None

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_credentials(self, db_session):
        """Edge case: account without credentials returns None."""
        _, account = await _create_user_and_account(
            db_session, email="nokeys@test.com", api_key=None, api_private_key=None
        )
        _exchange_client_cache.pop(account.id, None)

        client = await get_exchange_client_for_account(db_session, account.id, use_cache=False)
        assert client is None

    @pytest.mark.asyncio
    @patch("app.services.exchange_service.PaperTradingClient")
    async def test_creates_paper_trading_client(self, mock_paper_cls, db_session):
        """Happy path: paper trading account creates PaperTradingClient."""
        mock_paper_instance = MagicMock()
        mock_paper_cls.return_value = mock_paper_instance

        user, paper_account = await _create_user_and_account(
            db_session, email="paper@test.com", is_paper=True
        )

        _exchange_client_cache.pop(paper_account.id, None)

        await get_exchange_client_for_account(db_session, paper_account.id, use_cache=False)
        # Paper trading clients should NOT be cached
        assert paper_account.id not in _exchange_client_cache


# ---------------------------------------------------------------------------
# get_exchange_client_for_user
# ---------------------------------------------------------------------------


class TestGetExchangeClientForUser:
    """Tests for get_exchange_client_for_user()."""

    @pytest.mark.asyncio
    @patch("app.services.exchange_service.get_exchange_client_for_account")
    async def test_returns_client_for_default_account(self, mock_get_client, db_session):
        """Happy path: returns client for user's default account."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        user, account = await _create_user_and_account(
            db_session, email="default@test.com", is_default=True
        )

        client = await get_exchange_client_for_user(db_session, user.id)
        assert client is mock_client

    @pytest.mark.asyncio
    async def test_returns_none_for_user_without_account(self, db_session):
        """Edge case: user with no accounts returns None."""
        user = User(email="noacct@test.com", hashed_password="hash", is_active=True)
        db_session.add(user)
        await db_session.flush()

        client = await get_exchange_client_for_user(db_session, user.id)
        assert client is None


# ---------------------------------------------------------------------------
# get_default_cex_account
# ---------------------------------------------------------------------------


class TestGetDefaultCexAccount:
    """Tests for get_default_cex_account()."""

    @pytest.mark.asyncio
    async def test_returns_default_account(self, db_session):
        """Happy path: returns user's default CEX account."""
        user, account = await _create_user_and_account(
            db_session, email="defcex@test.com", is_default=True
        )

        result = await get_default_cex_account(db_session, user.id)
        assert result is not None
        assert result.id == account.id

    @pytest.mark.asyncio
    async def test_returns_first_active_if_no_default(self, db_session):
        """Edge case: no default account, returns first active."""
        user, account = await _create_user_and_account(
            db_session, email="nodef@test.com", is_default=False
        )

        result = await get_default_cex_account(db_session, user.id)
        assert result is not None
        assert result.id == account.id

    @pytest.mark.asyncio
    async def test_returns_none_for_no_accounts(self, db_session):
        """Edge case: user with no CEX accounts returns None."""
        user = User(email="empty@test.com", hashed_password="hash", is_active=True)
        db_session.add(user)
        await db_session.flush()

        result = await get_default_cex_account(db_session, user.id)
        assert result is None


# ---------------------------------------------------------------------------
# create_or_update_cex_account
# ---------------------------------------------------------------------------


class TestCreateOrUpdateCexAccount:
    """Tests for create_or_update_cex_account()."""

    @pytest.mark.asyncio
    @patch("app.services.exchange_service.clear_exchange_client_cache")
    @patch("app.encryption.encrypt_value", return_value="encrypted_key")
    async def test_creates_new_account(self, mock_encrypt, mock_clear, db_session):
        """Happy path: creates new CEX account when none exists."""
        user = User(email="create@test.com", hashed_password="hash", is_active=True)
        db_session.add(user)
        await db_session.flush()

        account = await create_or_update_cex_account(
            db_session, user.id,
            name="My Coinbase",
            api_key_name="key-name",
            api_private_key="private-key",
        )

        assert account is not None
        assert account.name == "My Coinbase"
        assert account.type == "cex"
        assert account.is_default is True
        assert account.exchange == "coinbase"

    @pytest.mark.asyncio
    @patch("app.services.exchange_service.clear_exchange_client_cache")
    @patch("app.encryption.encrypt_value", return_value="new_encrypted_key")
    async def test_updates_existing_account(self, mock_encrypt, mock_clear, db_session):
        """Happy path: updates existing CEX account for same exchange."""
        user, existing_account = await _create_user_and_account(
            db_session, email="update@test.com"
        )

        account = await create_or_update_cex_account(
            db_session, user.id,
            name="Updated Name",
            api_key_name="new-key",
            api_private_key="new-secret",
        )

        assert account.id == existing_account.id
        assert account.name == "Updated Name"
        mock_clear.assert_called_once_with(existing_account.id)
