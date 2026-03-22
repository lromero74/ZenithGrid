"""
Tests for app/services/credentials_provider.py

TDD: these tests are written BEFORE implementation and must initially FAIL
with ModuleNotFoundError: No module named 'app.services.credentials_provider'.

Covers:
- LocalCredentialsProvider.get_exchange_client with db provided → delegates
- LocalCredentialsProvider with session_maker (no db) → opens session, delegates
- LocalCredentialsProvider with no db, no session_maker → falls back to async_session_maker
- LocalCredentialsProvider passes use_cache=False through
- LocalCredentialsProvider returns None when underlying function returns None
- Module-level singleton exists and is LocalCredentialsProvider
- credentials_provider satisfies CredentialsProvider Protocol (isinstance)
- RemoteCredentialsProvider is importable
- RemoteCredentialsProvider.get_exchange_client raises NotImplementedError
- RemoteCredentialsProvider satisfies CredentialsProvider Protocol (isinstance)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_async_cm(return_value):
    """Helper: build a mock async context manager that yields return_value."""
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=return_value)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


class TestLocalCredentialsProvider:

    @pytest.mark.asyncio
    @patch('app.services.exchange_service.get_exchange_client_for_account',
           new_callable=AsyncMock)
    async def test_delegates_with_db_provided(self, mock_fn):
        """Happy path: get_exchange_client with db calls get_exchange_client_for_account(db, ...)."""
        from app.services.credentials_provider import LocalCredentialsProvider
        mock_db = AsyncMock()
        mock_client = MagicMock()
        mock_fn.return_value = mock_client

        provider = LocalCredentialsProvider()
        result = await provider.get_exchange_client(42, db=mock_db)

        assert result is mock_client
        mock_fn.assert_awaited_once_with(mock_db, 42, use_cache=True, session_maker=None)

    @pytest.mark.asyncio
    @patch('app.services.exchange_service.get_exchange_client_for_account',
           new_callable=AsyncMock)
    async def test_delegates_with_session_maker_no_db(self, mock_fn):
        """Happy path: no db provided → opens session from session_maker, delegates."""
        from app.services.credentials_provider import LocalCredentialsProvider
        mock_db = AsyncMock()
        mock_sm = MagicMock()
        mock_sm.return_value = _make_async_cm(mock_db)
        mock_fn.return_value = MagicMock()

        provider = LocalCredentialsProvider()
        await provider.get_exchange_client(7, session_maker=mock_sm)

        mock_sm.assert_called_once()
        mock_fn.assert_awaited_once_with(mock_db, 7, use_cache=True, session_maker=mock_sm)

    @pytest.mark.asyncio
    @patch('app.services.exchange_service.get_exchange_client_for_account',
           new_callable=AsyncMock)
    @patch('app.database.async_session_maker')
    async def test_fallback_to_default_session_maker(self, mock_default_sm, mock_fn):
        """Edge case: neither db nor session_maker → falls back to async_session_maker."""
        from app.services.credentials_provider import LocalCredentialsProvider
        mock_db = AsyncMock()
        mock_default_sm.return_value = _make_async_cm(mock_db)
        mock_fn.return_value = None

        provider = LocalCredentialsProvider()
        result = await provider.get_exchange_client(99)

        assert result is None
        mock_default_sm.assert_called_once()
        mock_fn.assert_awaited_once_with(
            mock_db, 99, use_cache=True, session_maker=mock_default_sm
        )

    @pytest.mark.asyncio
    @patch('app.services.exchange_service.get_exchange_client_for_account',
           new_callable=AsyncMock)
    async def test_passes_use_cache_false(self, mock_fn):
        """Happy path: use_cache=False is forwarded to the underlying function."""
        from app.services.credentials_provider import LocalCredentialsProvider
        mock_db = AsyncMock()
        mock_fn.return_value = MagicMock()

        provider = LocalCredentialsProvider()
        await provider.get_exchange_client(5, db=mock_db, use_cache=False)

        mock_fn.assert_awaited_once_with(mock_db, 5, use_cache=False, session_maker=None)

    @pytest.mark.asyncio
    @patch('app.services.exchange_service.get_exchange_client_for_account',
           new_callable=AsyncMock, return_value=None)
    async def test_returns_none_when_underlying_returns_none(self, mock_fn):
        """Edge case: None passthrough when account not found or credentials missing."""
        from app.services.credentials_provider import LocalCredentialsProvider
        mock_db = AsyncMock()

        provider = LocalCredentialsProvider()
        result = await provider.get_exchange_client(404, db=mock_db)

        assert result is None

    @pytest.mark.asyncio
    @patch('app.services.exchange_service.get_exchange_client_for_account',
           new_callable=AsyncMock)
    async def test_passes_session_maker_kwarg_through_when_db_provided(self, mock_fn):
        """Happy path: session_maker is passed through even when db is also provided."""
        from app.services.credentials_provider import LocalCredentialsProvider
        mock_db = AsyncMock()
        mock_sm = MagicMock()
        mock_fn.return_value = MagicMock()

        provider = LocalCredentialsProvider()
        await provider.get_exchange_client(3, db=mock_db, session_maker=mock_sm)

        mock_fn.assert_awaited_once_with(mock_db, 3, use_cache=True, session_maker=mock_sm)


class TestModuleSingleton:

    def test_singleton_exists_and_is_correct_type(self):
        """Happy path: module-level credentials_provider is LocalCredentialsProvider."""
        from app.services.credentials_provider import credentials_provider, LocalCredentialsProvider
        assert isinstance(credentials_provider, LocalCredentialsProvider)

    def test_singleton_satisfies_protocol(self):
        """Happy path: credentials_provider isinstance check passes CredentialsProvider Protocol."""
        from app.services.credentials_provider import credentials_provider, CredentialsProvider
        assert isinstance(credentials_provider, CredentialsProvider)


class TestRemoteCredentialsProviderStub:

    def test_remote_provider_is_importable(self):
        """Happy path: RemoteCredentialsProvider class is importable."""
        from app.services.credentials_provider import RemoteCredentialsProvider
        assert RemoteCredentialsProvider is not None

    @pytest.mark.asyncio
    async def test_remote_raises_not_implemented(self):
        """Failure: RemoteCredentialsProvider.get_exchange_client raises NotImplementedError."""
        from app.services.credentials_provider import RemoteCredentialsProvider
        stub = RemoteCredentialsProvider()
        with pytest.raises(NotImplementedError):
            await stub.get_exchange_client(1)

    def test_remote_satisfies_protocol(self):
        """Edge case: RemoteCredentialsProvider also satisfies CredentialsProvider Protocol."""
        from app.services.credentials_provider import RemoteCredentialsProvider, CredentialsProvider
        assert isinstance(RemoteCredentialsProvider(), CredentialsProvider)
