"""
Tests for backend/app/routers/accounts_router.py

Covers account CRUD endpoints: list, create, update, delete,
set_default, get_account_bots, get_account_portfolio, auto-buy settings,
link_perps_portfolio, and the _mask_key_name helper.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.models import Account, Bot, User


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def test_user(db_session):
    user = User(
        id=1, email="test@test.com",
        hashed_password="hashed", is_active=True, is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def test_account(db_session, test_user):
    account = Account(
        id=1, user_id=test_user.id, name="Main Account",
        type="cex", exchange="coinbase", is_default=True, is_active=True,
        api_key_name="my-api-key-name-12345",
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db_session.add(account)
    await db_session.flush()
    return account


@pytest.fixture
async def test_account_dex(db_session, test_user):
    account = Account(
        id=2, user_id=test_user.id, name="DEX Wallet",
        type="dex", is_default=False, is_active=True,
        wallet_address="0x1234567890abcdef1234567890abcdef12345678",
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db_session.add(account)
    await db_session.flush()
    return account


@pytest.fixture
async def test_bot(db_session, test_user, test_account):
    bot = Bot(
        id=1, user_id=test_user.id, name="Test Bot",
        account_id=test_account.id, strategy_type="macd_dca",
        strategy_config={}, is_active=True,
    )
    db_session.add(bot)
    await db_session.flush()
    return bot


# =============================================================================
# mask_api_key helper (moved to app.encryption)
# =============================================================================


class TestMaskApiKey:
    """Tests for the mask_api_key utility function."""

    def test_mask_api_key_normal_value(self):
        """Happy path: long key name is masked with first/last 4 chars."""
        from app.encryption import mask_api_key
        result = mask_api_key("my-long-api-key-name")
        assert result.startswith("my-l")
        assert result.endswith("name")
        assert "****" in result

    def test_mask_api_key_short_value(self):
        """Edge case: short key (<= 8 chars) returns ****."""
        from app.encryption import mask_api_key
        result = mask_api_key("short")
        assert result == "****"

    def test_mask_api_key_none(self):
        """Failure case: None input returns None."""
        from app.encryption import mask_api_key
        assert mask_api_key(None) is None

    def test_mask_api_key_empty_string(self):
        """Failure case: empty string returns None."""
        from app.encryption import mask_api_key
        assert mask_api_key("") is None


# =============================================================================
# list_accounts
# =============================================================================


class TestListAccounts:
    """Tests for the list_accounts endpoint."""

    @pytest.mark.asyncio
    async def test_list_accounts_returns_active(self, db_session, test_user, test_account):
        """Happy path: returns active accounts for the user."""
        from app.routers.accounts_router import list_accounts
        result = await list_accounts(
            include_inactive=False, db=db_session, current_user=test_user,
        )
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].name == "Main Account"

    @pytest.mark.asyncio
    async def test_list_accounts_includes_inactive(self, db_session, test_user):
        """Edge case: include_inactive=True returns disabled accounts."""
        inactive = Account(
            id=10, user_id=test_user.id, name="Disabled",
            type="cex", is_default=False, is_active=False,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db_session.add(inactive)
        await db_session.flush()

        from app.routers.accounts_router import list_accounts
        result = await list_accounts(
            include_inactive=True, db=db_session, current_user=test_user,
        )
        assert len(result) == 1
        assert result[0].name == "Disabled"

    @pytest.mark.asyncio
    async def test_list_accounts_empty(self, db_session, test_user):
        """Edge case: user with no accounts returns empty list."""
        from app.routers.accounts_router import list_accounts
        result = await list_accounts(
            include_inactive=False, db=db_session, current_user=test_user,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_list_accounts_includes_bot_count(
        self, db_session, test_user, test_account, test_bot,
    ):
        """Happy path: bot_count is correctly computed."""
        from app.routers.accounts_router import list_accounts
        result = await list_accounts(
            include_inactive=False, db=db_session, current_user=test_user,
        )
        assert result[0].bot_count == 1


# =============================================================================
# get_account
# =============================================================================


class TestGetAccount:
    """Tests for the get_account endpoint."""

    @pytest.mark.asyncio
    async def test_get_account_success(self, db_session, test_user, test_account):
        """Happy path: returns account by ID."""
        from app.routers.accounts_router import get_account
        result = await get_account(
            account_id=test_account.id, db=db_session, current_user=test_user,
        )
        assert result.id == test_account.id
        assert result.name == "Main Account"

    @pytest.mark.asyncio
    async def test_get_account_not_found(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_router import get_account
        with pytest.raises(HTTPException) as exc_info:
            await get_account(
                account_id=999, db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_account_wrong_user(self, db_session, test_account):
        """Failure case: account belonging to different user raises 404."""
        other_user = User(
            id=2, email="other@test.com",
            hashed_password="hashed", is_active=True,
        )
        db_session.add(other_user)
        await db_session.flush()

        from app.routers.accounts_router import get_account
        with pytest.raises(HTTPException) as exc_info:
            await get_account(
                account_id=test_account.id, db=db_session, current_user=other_user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# create_account
# =============================================================================


class TestCreateAccount:
    """Tests for the create_account endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.accounts_router.create_exchange_account", new_callable=AsyncMock)
    async def test_create_account_success(self, mock_create, db_session, test_user):
        """Happy path: creates account via service layer."""
        mock_account = Account(
            id=5, user_id=test_user.id, name="New Account",
            type="cex", exchange="coinbase", is_default=False, is_active=True,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        mock_create.return_value = mock_account

        from app.routers.accounts_router import create_account, AccountCreate
        account_data = AccountCreate(
            name="New Account", type="cex", exchange="coinbase",
        )
        result = await create_account(
            account_data=account_data, db=db_session, current_user=test_user,
        )
        assert result.name == "New Account"
        assert result.bot_count == 0
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.routers.accounts_router.create_exchange_account", new_callable=AsyncMock)
    async def test_create_account_service_error_raises_500(
        self, mock_create, db_session, test_user,
    ):
        """Failure case: unexpected service error raises 500."""
        mock_create.side_effect = RuntimeError("Unexpected error")

        from app.routers.accounts_router import create_account, AccountCreate
        account_data = AccountCreate(
            name="Bad Account", type="cex", exchange="coinbase",
        )
        with pytest.raises(HTTPException) as exc_info:
            await create_account(
                account_data=account_data, db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 500


# =============================================================================
# update_account
# =============================================================================


class TestUpdateAccount:
    """Tests for the update_account endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.accounts_router.clear_exchange_client_cache")
    @patch("app.routers.accounts_router.encrypt_value", side_effect=lambda v: f"enc:{v}")
    async def test_update_account_name(
        self, mock_encrypt, mock_clear, db_session, test_user, test_account,
    ):
        """Happy path: updates account name."""
        from app.routers.accounts_router import update_account, AccountUpdate
        update_data = AccountUpdate(name="Renamed Account")
        result = await update_account(
            account_id=test_account.id, account_data=update_data,
            db=db_session, current_user=test_user,
        )
        assert result.name == "Renamed Account"

    @pytest.mark.asyncio
    async def test_update_account_not_found(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_router import update_account, AccountUpdate
        update_data = AccountUpdate(name="X")
        with pytest.raises(HTTPException) as exc_info:
            await update_account(
                account_id=999, account_data=update_data,
                db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.routers.accounts_router.clear_exchange_client_cache")
    @patch("app.routers.accounts_router.encrypt_value", side_effect=lambda v: f"enc:{v}")
    async def test_update_account_invalid_prop_firm(
        self, mock_encrypt, mock_clear, db_session, test_user, test_account,
    ):
        """Failure case: invalid prop_firm raises 400."""
        from app.routers.accounts_router import update_account, AccountUpdate
        update_data = AccountUpdate(prop_firm="invalid_firm")
        with pytest.raises(HTTPException) as exc_info:
            await update_account(
                account_id=test_account.id, account_data=update_data,
                db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 400


# =============================================================================
# delete_account
# =============================================================================


class TestDeleteAccount:
    """Tests for the delete_account endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.accounts_router.clear_exchange_client_cache")
    async def test_delete_account_success(
        self, mock_clear, db_session, test_user, test_account,
    ):
        """Happy path: deletes account with no linked bots."""
        from app.routers.accounts_router import delete_account
        result = await delete_account(
            account_id=test_account.id, db=db_session, current_user=test_user,
        )
        assert "deleted successfully" in result["message"]
        mock_clear.assert_called_once_with(test_account.id)

    @pytest.mark.asyncio
    async def test_delete_account_with_linked_bots(
        self, db_session, test_user, test_account, test_bot,
    ):
        """Failure case: cannot delete account with linked bots."""
        from app.routers.accounts_router import delete_account
        with pytest.raises(HTTPException) as exc_info:
            await delete_account(
                account_id=test_account.id, db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 400
        assert "linked bots" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_delete_account_not_found(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_router import delete_account
        with pytest.raises(HTTPException) as exc_info:
            await delete_account(
                account_id=999, db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# set_default_account
# =============================================================================


class TestSetDefaultAccount:
    """Tests for the set_default_account endpoint."""

    @pytest.mark.asyncio
    async def test_set_default_success(self, db_session, test_user, test_account):
        """Happy path: sets account as default."""
        from app.routers.accounts_router import set_default_account
        result = await set_default_account(
            account_id=test_account.id, db=db_session, current_user=test_user,
        )
        assert "is now the default" in result["message"]

    @pytest.mark.asyncio
    async def test_set_default_not_found(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_router import set_default_account
        with pytest.raises(HTTPException) as exc_info:
            await set_default_account(
                account_id=999, db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# get_account_bots
# =============================================================================


class TestGetAccountBots:
    """Tests for the get_account_bots endpoint."""

    @pytest.mark.asyncio
    async def test_get_account_bots_with_bots(
        self, db_session, test_user, test_account, test_bot,
    ):
        """Happy path: returns bots for the account."""
        from app.routers.accounts_router import get_account_bots
        result = await get_account_bots(
            account_id=test_account.id, db=db_session, current_user=test_user,
        )
        assert result["bot_count"] == 1
        assert result["bots"][0]["name"] == "Test Bot"

    @pytest.mark.asyncio
    async def test_get_account_bots_empty(
        self, db_session, test_user, test_account,
    ):
        """Edge case: account with no bots returns empty list."""
        from app.routers.accounts_router import get_account_bots
        result = await get_account_bots(
            account_id=test_account.id, db=db_session, current_user=test_user,
        )
        assert result["bot_count"] == 0
        assert result["bots"] == []

    @pytest.mark.asyncio
    async def test_get_account_bots_not_found(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_router import get_account_bots
        with pytest.raises(HTTPException) as exc_info:
            await get_account_bots(
                account_id=999, db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# get_account_portfolio
# =============================================================================


class TestGetAccountPortfolio:
    """Tests for the get_account_portfolio endpoint."""

    @pytest.mark.asyncio
    @patch(
        "app.routers.accounts_router.get_portfolio_for_account",
        new_callable=AsyncMock,
    )
    async def test_get_portfolio_success(
        self, mock_portfolio, db_session, test_user,
    ):
        """Happy path: returns portfolio data from service."""
        mock_portfolio.return_value = {"total_usd": 50000.0, "assets": []}
        from app.routers.accounts_router import get_account_portfolio
        result = await get_account_portfolio(
            account_id=1, force_fresh=False,
            db=db_session, current_user=test_user,
        )
        assert result["total_usd"] == 50000.0
        mock_portfolio.assert_called_once()

    @pytest.mark.asyncio
    @patch(
        "app.routers.accounts_router.get_portfolio_for_account",
        new_callable=AsyncMock,
    )
    async def test_get_portfolio_service_raises_404(
        self, mock_portfolio, db_session, test_user,
    ):
        """Failure case: service raises HTTPException passes through."""
        mock_portfolio.side_effect = HTTPException(status_code=404, detail="Not found")
        from app.routers.accounts_router import get_account_portfolio
        with pytest.raises(HTTPException) as exc_info:
            await get_account_portfolio(
                account_id=999, force_fresh=False,
                db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# Auto-Buy Settings
# =============================================================================


class TestAutoBuySettings:
    """Tests for get/update auto-buy settings."""

    @pytest.mark.asyncio
    async def test_get_auto_buy_settings_defaults(
        self, db_session, test_user, test_account,
    ):
        """Happy path: returns default auto-buy settings."""
        from app.routers.accounts_router import get_auto_buy_settings
        result = await get_auto_buy_settings(
            account_id=test_account.id, db=db_session, current_user=test_user,
        )
        assert result.enabled is False
        assert result.check_interval_minutes == 5
        assert result.order_type == "market"

    @pytest.mark.asyncio
    async def test_get_auto_buy_settings_not_found(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_router import get_auto_buy_settings
        with pytest.raises(HTTPException) as exc_info:
            await get_auto_buy_settings(
                account_id=999, db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_auto_buy_settings(
        self, db_session, test_user, test_account,
    ):
        """Happy path: updates auto-buy settings."""
        from app.routers.accounts_router import (
            update_auto_buy_settings, AutoBuySettingsUpdate,
        )
        settings = AutoBuySettingsUpdate(enabled=True, usdc_enabled=True, usdc_min=25.0)
        result = await update_auto_buy_settings(
            account_id=test_account.id, settings=settings,
            db=db_session, current_user=test_user,
        )
        assert result.enabled is True
        assert result.usdc_enabled is True
        assert result.usdc_min == 25.0


# =============================================================================
# link_perps_portfolio
# =============================================================================


class TestLinkPerpsPortfolio:
    """Tests for the link_perps_portfolio endpoint."""

    @pytest.mark.asyncio
    async def test_link_perps_not_cex_raises_400(
        self, db_session, test_user, test_account_dex,
    ):
        """Failure case: DEX account raises 400."""
        from app.routers.accounts_router import link_perps_portfolio
        with pytest.raises(HTTPException) as exc_info:
            await link_perps_portfolio(
                account_id=test_account_dex.id, db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_link_perps_not_found(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_router import link_perps_portfolio
        with pytest.raises(HTTPException) as exc_info:
            await link_perps_portfolio(
                account_id=999, db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.routers.accounts_router.get_coinbase_for_account", new_callable=AsyncMock)
    async def test_link_perps_success(
        self, mock_coinbase, db_session, test_user, test_account,
    ):
        """Happy path: links perps portfolio UUID."""
        mock_client = AsyncMock()
        mock_client.get_portfolios = AsyncMock(return_value=[
            {"type": "PERPETUALS", "uuid": "test-uuid-123"},
        ])
        mock_client.get_perps_portfolio_summary = AsyncMock(return_value={})
        mock_coinbase.return_value = mock_client

        from app.routers.accounts_router import link_perps_portfolio
        result = await link_perps_portfolio(
            account_id=test_account.id, db=db_session, current_user=test_user,
        )
        assert result["success"] is True
        assert result["portfolio_uuid"] == "test-uuid-123"
