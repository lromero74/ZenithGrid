"""
Tests for accounts query + mutation routers (split from accounts_router.py)

Covers account CRUD endpoints: list, create, update, delete,
set_default, get_account_bots, get_account_portfolio, auto-buy settings,
link_perps_portfolio, and the _mask_key_name helper.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.models import Account, Bot, User


# =============================================================================
# Clear module-level TTL caches before each test to prevent cross-test leakage
# =============================================================================


@pytest.fixture(autouse=True)
def clear_accounts_router_caches():
    """Clear TTL caches in accounts_query_router before each test."""
    import app.routers.accounts_query_router as ar
    ar._TTL_REBALANCE_STATUS.clear()
    ar._TTL_DUST_SWEEP.clear()
    yield


def _bulk_products(prices: dict) -> list:
    """Build a fake list_products() response from a {product_id: price} dict.

    rebalance_service uses public_market_data.list_products() (bulk, cached 1hr)
    instead of per-pair get_current_price() calls.  Tests that set up price
    mocks must feed this format.
    """
    return [{"product_id": pid, "price": str(p)} for pid, p in prices.items()]


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
        from app.routers.accounts_query_router import list_accounts
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

        from app.routers.accounts_query_router import list_accounts
        result = await list_accounts(
            include_inactive=True, db=db_session, current_user=test_user,
        )
        assert len(result) == 1
        assert result[0].name == "Disabled"

    @pytest.mark.asyncio
    async def test_list_accounts_empty(self, db_session, test_user):
        """Edge case: user with no accounts returns empty list."""
        from app.routers.accounts_query_router import list_accounts
        result = await list_accounts(
            include_inactive=False, db=db_session, current_user=test_user,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_list_accounts_includes_bot_count(
        self, db_session, test_user, test_account, test_bot,
    ):
        """Happy path: bot_count is correctly computed."""
        from app.routers.accounts_query_router import list_accounts
        result = await list_accounts(
            include_inactive=False, db=db_session, current_user=test_user,
        )
        assert result[0].bot_count == 1


class TestListAccountsSharedOwnerBatch:
    """Owner display names for shared accounts come from ONE batched query.

    The old code called db.get(User, ...) inside the per-account loop — one
    SELECT per distinct owner (N+1).
    """

    async def _make_shared_accounts(self, db_session, viewer, n=3):
        from app.models.sharing import AccountMembership

        accounts = []
        for i in range(n):
            owner = User(
                id=100 + i, email=f"owner{i}@test.com", hashed_password="x",
                is_active=True, is_superuser=False, display_name=f"Owner {i}",
            )
            db_session.add(owner)
            await db_session.flush()
            account = Account(
                user_id=owner.id, name=f"Shared {i}", type="cex",
                exchange="coinbase", is_active=True,
            )
            db_session.add(account)
            await db_session.flush()
            db_session.add(AccountMembership(
                account_id=account.id, user_id=viewer.id,
                role="observer", expires_at=None,
            ))
            accounts.append(account)
        await db_session.flush()
        return accounts

    @staticmethod
    def _user_selects(statements):
        """SELECTs of user rows themselves — excludes the groups selectin-load
        that fires automatically whenever User objects materialize."""
        return [
            s for s in statements
            if "users" in s.lower()
            and "user_groups" not in s.lower()
            and s.lstrip().lower().startswith("select")
        ]

    @pytest.mark.asyncio
    async def test_shared_by_correct_for_each_owner(self, db_session, test_user):
        """Happy path: every shared account reports its own owner's name."""
        from app.routers.accounts_query_router import list_accounts

        await self._make_shared_accounts(db_session, test_user, n=3)

        result = await list_accounts(db=db_session, current_user=test_user)
        shared = {a.name: a.shared_by for a in result if a.name.startswith("Shared")}
        assert shared == {f"Shared {i}": f"Owner {i}" for i in range(3)}

    @pytest.mark.asyncio
    async def test_owner_lookup_is_single_query(self, db_session, test_user, async_engine):
        """The owner lookup must be one IN-clause SELECT, not one per owner."""
        from sqlalchemy import event
        from app.routers.accounts_query_router import list_accounts

        await self._make_shared_accounts(db_session, test_user, n=3)

        statements = []

        def _record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        sync_engine = async_engine.sync_engine
        event.listen(sync_engine, "before_cursor_execute", _record)
        try:
            await list_accounts(db=db_session, current_user=test_user)
        finally:
            event.remove(sync_engine, "before_cursor_execute", _record)

        user_selects = self._user_selects(statements)
        assert len(user_selects) <= 1, (
            f"Expected a single batched owner query, got {len(user_selects)}:\n"
            + "\n---\n".join(user_selects)
        )

    @pytest.mark.asyncio
    async def test_no_shared_accounts_skips_owner_query(
        self, db_session, test_user, test_account, async_engine,
    ):
        """Edge case: with only owned accounts, no owner query runs at all."""
        from sqlalchemy import event
        from app.routers.accounts_query_router import list_accounts

        statements = []

        def _record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        sync_engine = async_engine.sync_engine
        event.listen(sync_engine, "before_cursor_execute", _record)
        try:
            result = await list_accounts(db=db_session, current_user=test_user)
        finally:
            event.remove(sync_engine, "before_cursor_execute", _record)

        assert all(a.shared_by is None for a in result)
        assert self._user_selects(statements) == []


# =============================================================================
# get_account
# =============================================================================


class TestGetAccount:
    """Tests for the get_account endpoint."""

    @pytest.mark.asyncio
    async def test_get_account_success(self, db_session, test_user, test_account):
        """Happy path: returns account by ID."""
        from app.routers.accounts_query_router import get_account
        result = await get_account(
            account_id=test_account.id, db=db_session, current_user=test_user,
        )
        assert result.id == test_account.id
        assert result.name == "Main Account"
        # speculative_allocation_pct surfaces (default 0.0) so the UI can read it.
        assert result.speculative_allocation_pct == 0.0

    @pytest.mark.asyncio
    async def test_get_account_not_found(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_query_router import get_account
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

        from app.routers.accounts_query_router import get_account
        with pytest.raises(HTTPException) as exc_info:
            await get_account(
                account_id=test_account.id, db=db_session, current_user=other_user,
            )
        assert exc_info.value.status_code == 404


class TestGetAccountValueSummaryRoute:
    """Tests for the get_account_value_summary_route endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.accounts_query_router.get_account_value_summary", new_callable=AsyncMock)
    async def test_get_account_value_summary_success(
        self, mock_get_summary, db_session, test_user, test_account,
    ):
        """Happy path: delegates to service and returns summary payload."""
        mock_get_summary.return_value = {
            "account_id": test_account.id,
            "total_usd_value": 1234.56,
            "total_btc_value": 0.0123,
            "btc_usd_price": 100000.0,
            "as_of": "2026-04-21T12:00:00",
            "is_stale": False,
            "is_refreshing": False,
        }

        from app.routers.accounts_query_router import get_account_value_summary_route

        result = await get_account_value_summary_route(
            account_id=test_account.id,
            force_fresh=False,
            db=db_session,
            current_user=test_user,
        )

        assert result["account_id"] == test_account.id
        mock_get_summary.assert_called_once_with(db_session, test_user, test_account.id, False)

    @pytest.mark.asyncio
    @patch("app.routers.accounts_query_router.get_account_value_summary", new_callable=AsyncMock)
    async def test_get_account_value_summary_http_exception_bubbles(
        self, mock_get_summary, db_session, test_user, test_account,
    ):
        """Failure case: HTTPException from service is re-raised unchanged."""
        mock_get_summary.side_effect = HTTPException(status_code=404, detail="Not found")

        from app.routers.accounts_query_router import get_account_value_summary_route

        with pytest.raises(HTTPException) as exc_info:
            await get_account_value_summary_route(
                account_id=test_account.id,
                force_fresh=False,
                db=db_session,
                current_user=test_user,
            )

        assert exc_info.value.status_code == 404


# =============================================================================
# create_account
# =============================================================================


class TestCreateAccount:
    """Tests for the create_account endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.accounts_mutation_router.create_exchange_account", new_callable=AsyncMock)
    async def test_create_account_success(self, mock_create, db_session, test_user):
        """Happy path: creates account via service layer."""
        # Mark as superuser to bypass the privileged-group check (which would trigger
        # a lazy load of user.groups, causing MissingGreenlet outside async context).
        test_user.is_superuser = True

        mock_account = Account(
            id=5, user_id=test_user.id, name="New Account",
            type="cex", exchange="coinbase", is_default=False, is_active=True,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        mock_create.return_value = mock_account

        from app.routers.accounts_mutation_router import create_account
        from app.schemas.accounts import AccountCreate
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
    @patch("app.routers.accounts_mutation_router.create_exchange_account", new_callable=AsyncMock)
    async def test_create_account_service_error_raises_500(
        self, mock_create, db_session, test_user,
    ):
        """Failure case: unexpected service error raises 500."""
        # Mark as superuser to bypass the privileged-group check (lazy load outside async context).
        test_user.is_superuser = True
        mock_create.side_effect = RuntimeError("Unexpected error")

        from app.routers.accounts_mutation_router import create_account
        from app.schemas.accounts import AccountCreate
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
    @patch("app.routers.accounts_mutation_router.clear_exchange_client_cache")
    @patch("app.routers.accounts_mutation_router.encrypt_value", side_effect=lambda v: f"enc:{v}")
    async def test_update_account_name(
        self, mock_encrypt, mock_clear, db_session, test_user, test_account,
    ):
        """Happy path: updates account name."""
        from app.routers.accounts_mutation_router import update_account
        from app.schemas.accounts import AccountUpdate
        update_data = AccountUpdate(name="Renamed Account")
        result = await update_account(
            account_id=test_account.id, account_data=update_data,
            db=db_session, current_user=test_user,
        )
        assert result.name == "Renamed Account"

    @pytest.mark.asyncio
    async def test_update_account_not_found(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_mutation_router import update_account
        from app.schemas.accounts import AccountUpdate
        update_data = AccountUpdate(name="X")
        with pytest.raises(HTTPException) as exc_info:
            await update_account(
                account_id=999, account_data=update_data,
                db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.routers.accounts_mutation_router.clear_exchange_client_cache")
    @patch("app.routers.accounts_mutation_router.encrypt_value", side_effect=lambda v: f"enc:{v}")
    async def test_update_account_invalid_prop_firm(
        self, mock_encrypt, mock_clear, db_session, test_user, test_account,
    ):
        """Failure case: invalid prop_firm raises 400."""
        from app.routers.accounts_mutation_router import update_account
        from app.schemas.accounts import AccountUpdate
        update_data = AccountUpdate(prop_firm="invalid_firm")
        with pytest.raises(HTTPException) as exc_info:
            await update_account(
                account_id=test_account.id, account_data=update_data,
                db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("app.routers.accounts_mutation_router.clear_exchange_client_cache")
    @patch("app.routers.accounts_mutation_router.encrypt_value", side_effect=lambda v: f"enc:{v}")
    async def test_update_account_speculative_allocation(
        self, mock_encrypt, mock_clear, db_session, test_user, test_account,
    ):
        """Happy path: PATCH-style update writes speculative_allocation_pct and
        the response surfaces it. This is the plumbing that lets the Account
        Settings "Speculative Allocation %" field persist. See PRP §Task D1."""
        from app.routers.accounts_mutation_router import update_account
        from app.schemas.accounts import AccountUpdate
        update_data = AccountUpdate(speculative_allocation_pct=5.0)
        result = await update_account(
            account_id=test_account.id, account_data=update_data,
            db=db_session, current_user=test_user,
        )
        assert result.speculative_allocation_pct == 5.0
        # Re-read the row — the column persisted, not just echoed.
        await db_session.refresh(test_account)
        assert float(test_account.speculative_allocation_pct) == 5.0

    @pytest.mark.asyncio
    async def test_update_account_speculative_allocation_out_of_range(
        self, db_session, test_user, test_account,
    ):
        """Failure case: values outside [0, 100] are rejected by the schema."""
        from app.schemas.accounts import AccountUpdate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AccountUpdate(speculative_allocation_pct=150.0)
        with pytest.raises(ValidationError):
            AccountUpdate(speculative_allocation_pct=-1.0)


# =============================================================================
# delete_account
# =============================================================================


class TestDeleteAccount:
    """Tests for the delete_account endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.accounts_mutation_router.verify_mfa", new_callable=AsyncMock)
    @patch("app.routers.accounts_mutation_router.clear_exchange_client_cache")
    async def test_delete_account_success(
        self, mock_clear, mock_mfa, db_session, test_user, test_account,
    ):
        """Happy path: deletes account with no linked bots."""
        from app.routers.accounts_mutation_router import delete_account
        mock_mfa.return_value = None
        result = await delete_account(
            account_id=test_account.id, db=db_session, current_user=test_user,
            confirm=True, mfa_code="123456",
        )
        assert "deleted successfully" in result["message"]
        mock_clear.assert_called_once_with(test_account.id)

    @pytest.mark.asyncio
    @patch("app.routers.accounts_mutation_router.verify_mfa", new_callable=AsyncMock)
    async def test_delete_account_with_linked_bots(
        self, mock_mfa, db_session, test_user, test_account, test_bot,
    ):
        """Failure case: cannot delete account with linked bots."""
        from app.routers.accounts_mutation_router import delete_account
        mock_mfa.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            await delete_account(
                account_id=test_account.id, db=db_session, current_user=test_user,
                confirm=True, mfa_code="123456",
            )
        assert exc_info.value.status_code == 400
        assert "linked bots" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.routers.accounts_mutation_router.verify_mfa", new_callable=AsyncMock)
    async def test_delete_account_not_found(self, mock_mfa, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_mutation_router import delete_account
        with pytest.raises(HTTPException) as exc_info:
            await delete_account(
                account_id=999, db=db_session, current_user=test_user,
                confirm=True, mfa_code="123456",
            )
        assert exc_info.value.status_code == 404


class TestDeleteAccountMfa:
    """MFA must be verified before account deletion."""

    @pytest.mark.asyncio
    async def test_delete_without_mfa_code_returns_403(
        self, db_session, test_user, test_account,
    ):
        """Request WITHOUT mfa_code when user has MFA enabled → 403."""
        from app.routers.accounts_mutation_router import delete_account

        test_user.mfa_enabled = True
        test_user.totp_secret = "encrypted_secret"
        await db_session.flush()

        with patch("app.routers.accounts_mutation_router.verify_mfa", new_callable=AsyncMock) as mock_mfa:
            mock_mfa.side_effect = HTTPException(status_code=403, detail="MFA code required")
            with pytest.raises(HTTPException) as exc_info:
                await delete_account(
                    account_id=test_account.id, db=db_session,
                    current_user=test_user, confirm=True, mfa_code=None,
                )
            assert exc_info.value.status_code == 403
            assert "MFA" in exc_info.value.detail
            mock_mfa.assert_called_once_with(db_session, test_user, None)

    @pytest.mark.asyncio
    async def test_delete_with_invalid_mfa_returns_403(
        self, db_session, test_user, test_account,
    ):
        """Request with wrong mfa_code → 403."""
        from app.routers.accounts_mutation_router import delete_account

        with patch("app.routers.accounts_mutation_router.verify_mfa", new_callable=AsyncMock) as mock_mfa:
            mock_mfa.side_effect = HTTPException(status_code=403, detail="Invalid MFA code")
            with pytest.raises(HTTPException) as exc_info:
                await delete_account(
                    account_id=test_account.id, db=db_session,
                    current_user=test_user, confirm=True, mfa_code="000000",
                )
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("app.routers.accounts_mutation_router.clear_exchange_client_cache")
    async def test_delete_with_valid_mfa_succeeds(
        self, mock_clear, db_session, test_user, test_account,
    ):
        """Request with valid mfa_code + confirm=true → account deleted."""
        from app.routers.accounts_mutation_router import delete_account

        with patch("app.routers.accounts_mutation_router.verify_mfa", new_callable=AsyncMock) as mock_mfa:
            mock_mfa.return_value = None  # MFA passes
            result = await delete_account(
                account_id=test_account.id, db=db_session,
                current_user=test_user, confirm=True, mfa_code="123456",
            )
            mock_mfa.assert_called_once_with(db_session, test_user, "123456")
            assert "deleted successfully" in result["message"]

    @pytest.mark.asyncio
    async def test_delete_without_confirm_returns_400(
        self, db_session, test_user, test_account,
    ):
        """Request without confirm=true → 400."""
        from app.routers.accounts_mutation_router import delete_account

        with pytest.raises(HTTPException) as exc_info:
            await delete_account(
                account_id=test_account.id, db=db_session,
                current_user=test_user, confirm=False, mfa_code="123456",
            )
        assert exc_info.value.status_code == 400
        assert "confirm" in exc_info.value.detail.lower()


# =============================================================================
# set_default_account
# =============================================================================


class TestSetDefaultAccount:
    """Tests for the set_default_account endpoint."""

    @pytest.mark.asyncio
    async def test_set_default_success(self, db_session, test_user, test_account):
        """Happy path: sets account as default."""
        from app.routers.accounts_mutation_router import set_default_account
        result = await set_default_account(
            account_id=test_account.id, db=db_session, current_user=test_user,
        )
        assert "is now the default" in result["message"]

    @pytest.mark.asyncio
    async def test_set_default_not_found(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_mutation_router import set_default_account
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
        from app.routers.accounts_query_router import get_account_bots
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
        from app.routers.accounts_query_router import get_account_bots
        result = await get_account_bots(
            account_id=test_account.id, db=db_session, current_user=test_user,
        )
        assert result["bot_count"] == 0
        assert result["bots"] == []

    @pytest.mark.asyncio
    async def test_get_account_bots_not_found(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_query_router import get_account_bots
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
        "app.routers.accounts_query_router.get_portfolio_for_account",
        new_callable=AsyncMock,
    )
    async def test_get_portfolio_success(
        self, mock_portfolio, db_session, test_user,
    ):
        """Happy path: returns portfolio data from service."""
        mock_portfolio.return_value = {"total_usd": 50000.0, "assets": []}
        from app.routers.accounts_query_router import get_account_portfolio
        result = await get_account_portfolio(
            account_id=1, force_fresh=False,
            db=db_session, current_user=test_user,
        )
        assert result["total_usd"] == 50000.0
        mock_portfolio.assert_called_once()

    @pytest.mark.asyncio
    @patch(
        "app.routers.accounts_query_router.get_portfolio_for_account",
        new_callable=AsyncMock,
    )
    async def test_get_portfolio_service_raises_404(
        self, mock_portfolio, db_session, test_user,
    ):
        """Failure case: service raises HTTPException passes through."""
        mock_portfolio.side_effect = HTTPException(status_code=404, detail="Not found")
        from app.routers.accounts_query_router import get_account_portfolio
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
        from app.routers.accounts_query_router import get_auto_buy_settings
        result = await get_auto_buy_settings(
            account_id=test_account.id, db=db_session, current_user=test_user,
        )
        assert result.enabled is False
        assert result.check_interval_minutes == 5
        assert result.order_type == "market"

    @pytest.mark.asyncio
    async def test_get_auto_buy_settings_not_found(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_query_router import get_auto_buy_settings
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
        from app.routers.accounts_mutation_router import update_auto_buy_settings
        from app.schemas.accounts import AutoBuySettingsUpdate
        settings = AutoBuySettingsUpdate(enabled=True, usdc_enabled=True, usdc_min=25.0)
        result = await update_auto_buy_settings(
            account_id=test_account.id, settings=settings,
            db=db_session, current_user=test_user,
        )
        assert result.enabled is True
        assert result.usdc_enabled is True
        assert result.usdc_min == 25.0

    @pytest.mark.asyncio
    async def test_enable_autobuy_disables_rebalancing(
        self, db_session, test_user, test_account,
    ):
        """Mutual exclusivity: enabling auto-buy disables rebalancing."""
        # Pre-condition: rebalancing is enabled
        test_account.rebalance_enabled = True
        await db_session.flush()

        from app.routers.accounts_mutation_router import update_auto_buy_settings
        from app.schemas.accounts import AutoBuySettingsUpdate
        settings = AutoBuySettingsUpdate(enabled=True)
        result = await update_auto_buy_settings(
            account_id=test_account.id, settings=settings,
            db=db_session, current_user=test_user,
        )
        assert result.enabled is True
        # Rebalancing should now be disabled
        await db_session.refresh(test_account)
        assert test_account.rebalance_enabled is False


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
        from app.routers.accounts_mutation_router import link_perps_portfolio
        with pytest.raises(HTTPException) as exc_info:
            await link_perps_portfolio(
                account_id=test_account_dex.id, db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_link_perps_not_found(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_mutation_router import link_perps_portfolio
        with pytest.raises(HTTPException) as exc_info:
            await link_perps_portfolio(
                account_id=999, db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.routers.accounts_mutation_router.get_coinbase_for_account", new_callable=AsyncMock)
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

        from app.routers.accounts_mutation_router import link_perps_portfolio
        result = await link_perps_portfolio(
            account_id=test_account.id, db=db_session, current_user=test_user,
        )
        assert result["success"] is True
        assert result["portfolio_uuid"] == "test-uuid-123"


# =============================================================================
# Rebalance Settings
# =============================================================================


class TestRebalanceSettings:
    """Tests for get/update rebalance settings."""

    @pytest.mark.asyncio
    async def test_get_rebalance_settings_defaults(
        self, db_session, test_user, test_account,
    ):
        """Happy path: returns default rebalance settings."""
        from app.routers.accounts_query_router import get_rebalance_settings
        result = await get_rebalance_settings(
            account_id=test_account.id, db=db_session, current_user=test_user,
        )
        assert result.enabled is False
        assert result.target_usd_pct == pytest.approx(34.0)
        assert result.target_btc_pct == pytest.approx(33.0)
        assert result.target_eth_pct == pytest.approx(33.0)
        assert result.drift_threshold_pct == pytest.approx(5.0)
        assert result.check_interval_minutes == 60

    @pytest.mark.asyncio
    async def test_update_rebalance_settings_happy_path(
        self, db_session, test_user, test_account,
    ):
        """Happy path: updates and persists rebalance settings."""
        from app.routers.accounts_mutation_router import update_rebalance_settings
        from app.schemas.accounts import RebalanceSettingsUpdate
        settings = RebalanceSettingsUpdate(
            enabled=True, target_usd_pct=50.0, target_btc_pct=30.0, target_eth_pct=20.0,
        )
        result = await update_rebalance_settings(
            account_id=test_account.id, settings=settings,
            db=db_session, current_user=test_user,
        )
        assert result.enabled is True
        assert result.target_usd_pct == pytest.approx(50.0)
        assert result.target_btc_pct == pytest.approx(30.0)
        assert result.target_eth_pct == pytest.approx(20.0)

    @pytest.mark.asyncio
    async def test_enable_rebalancing_disables_autobuy(
        self, db_session, test_user, test_account,
    ):
        """Mutual exclusivity: enabling rebalancing disables auto-buy."""
        # Pre-condition: auto-buy is enabled
        test_account.auto_buy_enabled = True
        await db_session.flush()

        from app.routers.accounts_mutation_router import update_rebalance_settings
        from app.schemas.accounts import RebalanceSettingsUpdate
        settings = RebalanceSettingsUpdate(
            enabled=True, target_usd_pct=50.0, target_btc_pct=30.0, target_eth_pct=20.0,
        )
        result = await update_rebalance_settings(
            account_id=test_account.id, settings=settings,
            db=db_session, current_user=test_user,
        )
        assert result.enabled is True
        # Auto-buy should now be disabled
        await db_session.refresh(test_account)
        assert test_account.auto_buy_enabled is False

    @pytest.mark.asyncio
    async def test_update_rebalance_invalid_total(
        self, db_session, test_user, test_account,
    ):
        """Failure: percentages not summing to 100 raises 400."""
        from app.routers.accounts_mutation_router import update_rebalance_settings
        from app.schemas.accounts import RebalanceSettingsUpdate
        settings = RebalanceSettingsUpdate(
            target_usd_pct=50.0, target_btc_pct=40.0, target_eth_pct=20.0,
        )
        with pytest.raises(HTTPException) as exc_info:
            await update_rebalance_settings(
                account_id=test_account.id, settings=settings,
                db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 400
        assert "100%" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_rebalance_settings_not_found(self, db_session, test_user):
        """Failure: non-existent account raises 404."""
        from app.routers.accounts_query_router import get_rebalance_settings
        with pytest.raises(HTTPException) as exc_info:
            await get_rebalance_settings(
                account_id=999, db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_rebalance_negative_pct(
        self, db_session, test_user, test_account,
    ):
        """Failure: negative percentage is rejected by Pydantic validation."""
        from app.schemas.accounts import RebalanceSettingsUpdate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            RebalanceSettingsUpdate(target_usd_pct=-10.0)

    @pytest.mark.asyncio
    async def test_update_partial_only_interval(
        self, db_session, test_user, test_account,
    ):
        """Edge case: partial update with only interval changes."""
        from app.routers.accounts_mutation_router import update_rebalance_settings
        from app.schemas.accounts import RebalanceSettingsUpdate
        settings = RebalanceSettingsUpdate(
            check_interval_minutes=30, drift_threshold_pct=3.0,
        )
        result = await update_rebalance_settings(
            account_id=test_account.id, settings=settings,
            db=db_session, current_user=test_user,
        )
        assert result.check_interval_minutes == 30
        assert result.drift_threshold_pct == pytest.approx(3.0)
        # Percentages remain at defaults
        assert result.target_usd_pct == pytest.approx(34.0)


# =============================================================================
# Rebalance Status (paper trading support)
# =============================================================================


class TestRebalanceStatus:
    """Tests for GET /{account_id}/rebalance-status endpoint."""

    @pytest.fixture
    async def paper_account(self, db_session, test_user):
        import json
        account = Account(
            id=10, user_id=test_user.id, name="Paper Account",
            type="cex", is_paper_trading=True,
            paper_balances=json.dumps({"USD": 50000.0, "BTC": 0.5, "ETH": 5.0, "USDC": 10000.0}),
            rebalance_enabled=True,
            rebalance_target_usd_pct=25.0,
            rebalance_target_btc_pct=25.0,
            rebalance_target_eth_pct=25.0,
            rebalance_target_usdc_pct=25.0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db_session.add(account)
        await db_session.flush()
        return account

    @pytest.mark.asyncio
    async def test_paper_account_returns_allocation(
        self, db_session, test_user, paper_account,
    ):
        """Paper trading accounts should return current allocation from paper_balances."""
        from app.routers.accounts_query_router import get_rebalance_status

        # Mock the public price API — no exchange credentials needed
        with patch("app.services.rebalance_service.get_public_prices", new_callable=AsyncMock) as mock_prices:
            mock_prices.return_value = {"BTC-USD": 90000.0, "ETH-USD": 3000.0, "USDC-USD": 1.0}
            result = await get_rebalance_status(
                account_id=paper_account.id, db=db_session, current_user=test_user,
            )

        assert result["account_id"] == paper_account.id
        # BTC value: 0.5 * 90000 = 45000
        # ETH value: 5.0 * 3000 = 15000
        # USD value: 50000
        # USDC value: 10000 * 1.0 = 10000
        # Total: 120000
        assert result["total_value_usd"] == pytest.approx(120000.0)
        assert result["current_usd_pct"] == pytest.approx(41.67)
        assert result["current_btc_pct"] == pytest.approx(37.5)
        assert result["current_eth_pct"] == pytest.approx(12.5)
        assert result["current_usdc_pct"] == pytest.approx(8.33)

    @pytest.mark.asyncio
    async def test_paper_account_no_balances_returns_zeros(
        self, db_session, test_user,
    ):
        """Paper trading account with no balances returns zero allocation."""
        from app.routers.accounts_query_router import get_rebalance_status

        account = Account(
            id=11, user_id=test_user.id, name="Empty Paper",
            type="cex", is_paper_trading=True, paper_balances=None,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db_session.add(account)
        await db_session.flush()

        with patch("app.services.rebalance_service.get_public_prices", new_callable=AsyncMock) as mock_prices:
            mock_prices.return_value = {"BTC-USD": 90000.0, "ETH-USD": 3000.0, "USDC-USD": 1.0}
            result = await get_rebalance_status(
                account_id=account.id, db=db_session, current_user=test_user,
            )

        assert result["total_value_usd"] == 0.0
        assert result["current_usd_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_live_account_uses_coinbase(
        self, db_session, test_user, test_account,
    ):
        """Live (non-paper) accounts use Coinbase raw balances for physical holdings display."""
        from app.routers.accounts_query_router import get_rebalance_status

        mock_coinbase = AsyncMock()
        # Raw balance getters (physical holdings)
        mock_coinbase.get_usd_balance = AsyncMock(return_value=1000.0)
        mock_coinbase.get_btc_balance = AsyncMock(return_value=0.5)
        mock_coinbase.get_eth_balance = AsyncMock(return_value=2.0)
        mock_coinbase.get_usdc_balance = AsyncMock(return_value=500.0)
        mock_coinbase.get_current_price = AsyncMock(return_value=90000.0)

        with patch("app.services.exchange_service.get_coinbase_for_account", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_coinbase
            result = await get_rebalance_status(
                account_id=test_account.id, db=db_session, current_user=test_user,
            )

        mock_get.assert_called_once_with(test_account)
        assert result["account_id"] == test_account.id
        assert result["total_value_usd"] > 0

    @pytest.mark.asyncio
    async def test_live_account_allocation_uses_raw_balances_not_market_deployment(
        self, db_session, test_user, test_account,
    ):
        """Live account chart should show physical asset holdings, not market deployment.

        A user with 2 BTC (some acquired via BTC-USD bots) should see ~100% BTC,
        NOT 99% USD (the market-deployment view).
        """
        from app.routers.accounts_query_router import get_rebalance_status

        # Simulate: user physically holds 2 BTC, $0 USD, $0 ETH, $0 USDC
        # BTC price = $80,000 → total = $160,000, 100% BTC
        mock_coinbase = AsyncMock()
        mock_coinbase.get_usd_balance = AsyncMock(return_value=0.0)
        mock_coinbase.get_btc_balance = AsyncMock(return_value=2.0)
        mock_coinbase.get_eth_balance = AsyncMock(return_value=0.0)
        mock_coinbase.get_usdc_balance = AsyncMock(return_value=0.0)

        bulk = _bulk_products({"BTC-USD": 80000.0, "ETH-USD": 3000.0, "USDC-USD": 1.0})

        with patch("app.services.exchange_service.get_coinbase_for_account", new_callable=AsyncMock) as mock_get, \
             patch("app.coinbase_api.public_market_data.list_products", new_callable=AsyncMock, return_value=bulk):
            mock_get.return_value = mock_coinbase
            result = await get_rebalance_status(
                account_id=test_account.id, db=db_session, current_user=test_user,
            )

        # Should show ~100% BTC (physical holdings), NOT 99% USD (market deployment).
        # $1 tolerance absorbs minor rounding from bulk-price string→float conversion.
        assert result["total_value_usd"] == pytest.approx(160000.0, abs=5.0)
        assert result["current_btc_pct"] == pytest.approx(100.0, abs=0.01)
        assert result["current_usd_pct"] == pytest.approx(0.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_paper_account_altcoin_total_includes_altcoins(
        self, db_session, test_user,
    ):
        """Paper trading: total_value_usd must include altcoin balances, not just USD/BTC/ETH/USDC."""
        import json
        # USD=100, BTC=0.1 @ 50000 = 5000, SOL=10 @ 200 = 2000 → real total = 7100
        account = Account(
            id=12, user_id=test_user.id, name="Altcoin Paper",
            type="cex", is_paper_trading=True,
            paper_balances=json.dumps({"USD": 100.0, "BTC": 0.1, "SOL": 10.0}),
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db_session.add(account)
        await db_session.flush()

        from app.routers.accounts_query_router import get_rebalance_status

        bulk = _bulk_products({
            "BTC-USD": 50000.0, "ETH-USD": 3000.0, "USDC-USD": 1.0,
            "SOL-USD": 200.0,
        })
        with patch("app.services.rebalance_service.get_public_prices", new_callable=AsyncMock) as mock_prices, \
             patch("app.coinbase_api.public_market_data.list_products", new_callable=AsyncMock, return_value=bulk):
            mock_prices.return_value = {"BTC-USD": 50000.0, "ETH-USD": 3000.0, "USDC-USD": 1.0}

            result = await get_rebalance_status(
                account_id=account.id, db=db_session, current_user=test_user,
            )

        # Without fix: total = 100 + 5000 = 5100 (ignores SOL)
        # With fix: total = 100 + 5000 + 2000 = 7100
        assert result["total_value_usd"] == pytest.approx(7100.0), \
            f"Expected 7100 (includes SOL), got {result['total_value_usd']}"
        # BTC pct should be ~70.4% of 7100, not 98% of 5100
        assert result["current_btc_pct"] == pytest.approx(round(5000 / 7100 * 100, 2))

    @pytest.mark.asyncio
    async def test_paper_account_altcoin_btc_pair_valued_in_btc_bucket(
        self, db_session, test_user,
    ):
        """Free altcoin from a BTC-pair open position is folded into the BTC bucket.

        When an open RUNE-BTC position exists, the code classifies free RUNE as
        BTC-denominated.  RUNE-BTC rate × free RUNE quantity is added (in BTC units)
        to the BTC bucket, which is then converted to USD via BTC-USD.
        """
        import json
        from app.models.trading import Position

        account = Account(
            id=13, user_id=test_user.id, name="Altcoin BTC-pair Paper",
            type="cex", is_paper_trading=True,
            paper_balances=json.dumps({"USD": 0.0, "BTC": 0.0, "RUNE": 100.0}),
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db_session.add(account)
        await db_session.flush()

        # Open RUNE-BTC position so coin_quote["RUNE"] = "BTC"
        pos = Position(
            account_id=account.id, user_id=test_user.id,
            product_id="RUNE-BTC", status="open", direction="long",
            total_base_acquired=100.0,
            opened_at=datetime.utcnow(),
        )
        db_session.add(pos)
        await db_session.flush()

        from app.routers.accounts_query_router import get_rebalance_status

        bulk = _bulk_products({
            "BTC-USD": 50000.0, "ETH-USD": 3000.0, "USDC-USD": 1.0,
            "RUNE-BTC": 0.000030,
        })
        with patch("app.services.rebalance_service.get_public_prices", new_callable=AsyncMock) as mock_prices, \
             patch("app.coinbase_api.public_market_data.list_products", new_callable=AsyncMock, return_value=bulk):
            mock_prices.return_value = {"BTC-USD": 50000.0, "ETH-USD": 3000.0, "USDC-USD": 1.0}

            result = await get_rebalance_status(
                account_id=account.id, db=db_session, current_user=test_user,
            )

        # RUNE → BTC bucket: 100 * 0.000030 = 0.003 BTC → 0.003 * 50000 = $150 USD
        assert result["total_value_usd"] == pytest.approx(150.0)
        assert result["current_btc_pct"] == pytest.approx(100.0)


# =============================================================================
# Allocation includes open position market values (live accounts)
# =============================================================================


class TestAllocationIncludesOpenPositions:
    """Verify live-account allocation adds open position market values to quote buckets.

    Each test creates its own user + account inline (not using shared fixtures) to
    avoid cross-test position leakage when the in-memory SQLite engine is shared.
    """

    async def _make_account(self, db_session, email_suffix: str):
        """Helper: create a fresh user + CEX account for each test."""
        user = User(
            email=f"alloc_{email_suffix}@test.com",
            hashed_password="hashed", is_active=True,
        )
        db_session.add(user)
        await db_session.flush()
        account = Account(
            user_id=user.id, name=f"Alloc {email_suffix}",
            type="cex", exchange="coinbase", is_default=True, is_active=True,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db_session.add(account)
        await db_session.flush()
        return user, account

    @pytest.mark.asyncio
    async def test_usd_position_value_added_to_usd_bucket(self, db_session):
        """Happy path: open USD-pair position value is included in USD allocation bucket."""
        from app.models import Position
        from app.routers.accounts_query_router import get_rebalance_status
        user, account = await self._make_account(db_session, "usd")

        # $0 free USD, but 1 ETH open position at $2000 each → $2000 in the USD bucket
        pos = Position(
            account_id=account.id,
            product_id="ETH-USD",
            status="open",
            direction="long",
            total_base_acquired=1.0,
            entry_price=1800.0,
            initial_quote_balance=2000.0,
            max_quote_allowed=2000.0,
            total_quote_spent=2000.0,
            average_buy_price=2000.0,
            opened_at=datetime.utcnow(),
        )
        db_session.add(pos)
        await db_session.flush()

        mock_coinbase = AsyncMock()
        mock_coinbase.get_usd_balance = AsyncMock(return_value=0.0)
        mock_coinbase.get_btc_balance = AsyncMock(return_value=0.0)
        mock_coinbase.get_eth_balance = AsyncMock(return_value=0.0)
        mock_coinbase.get_usdc_balance = AsyncMock(return_value=0.0)
        bulk = _bulk_products({"BTC-USD": 50000.0, "ETH-USD": 2000.0, "USDC-USD": 1.0})

        with patch("app.services.exchange_service.get_coinbase_for_account", new_callable=AsyncMock) as mock_get, \
             patch("app.coinbase_api.public_market_data.list_products", new_callable=AsyncMock, return_value=bulk):
            mock_get.return_value = mock_coinbase
            result = await get_rebalance_status(
                account_id=account.id, db=db_session, current_user=user,
            )

        # $2000 from open ETH-USD position should appear in USD allocation
        assert result["total_value_usd"] == pytest.approx(2000.0, abs=1.0)
        assert result["current_usd_pct"] == pytest.approx(100.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_btc_position_value_added_to_btc_bucket(self, db_session):
        """Happy path: open BTC-pair position value is included in BTC allocation bucket."""
        from app.models import Position
        from app.routers.accounts_query_router import get_rebalance_status
        user, account = await self._make_account(db_session, "btc")

        # 0.01 free BTC, plus 1 ETH open at 0.05 BTC each → 0.05 BTC in position
        pos = Position(
            account_id=account.id,
            product_id="ETH-BTC",
            status="open",
            direction="long",
            total_base_acquired=1.0,
            entry_price=0.05,
            initial_quote_balance=0.05,
            max_quote_allowed=0.05,
            total_quote_spent=0.05,
            average_buy_price=0.05,
            opened_at=datetime.utcnow(),
        )
        db_session.add(pos)
        await db_session.flush()

        mock_coinbase = AsyncMock()
        mock_coinbase.get_usd_balance = AsyncMock(return_value=0.0)
        mock_coinbase.get_btc_balance = AsyncMock(return_value=0.01)
        mock_coinbase.get_eth_balance = AsyncMock(return_value=0.0)
        mock_coinbase.get_usdc_balance = AsyncMock(return_value=0.0)

        bulk = _bulk_products({
            "BTC-USD": 50000.0, "ETH-USD": 2500.0,
            "ETH-BTC": 0.05, "USDC-USD": 1.0,
        })

        with patch("app.services.exchange_service.get_coinbase_for_account", new_callable=AsyncMock) as mock_get, \
             patch("app.coinbase_api.public_market_data.list_products", new_callable=AsyncMock, return_value=bulk):
            mock_get.return_value = mock_coinbase
            result = await get_rebalance_status(
                account_id=account.id, db=db_session, current_user=user,
            )

        # BTC bucket = (0.01 free + 0.05 from position) * 50000 = $3000
        assert result["total_value_usd"] == pytest.approx(3000.0, abs=1.0)
        assert result["current_btc_pct"] == pytest.approx(100.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_closed_positions_not_counted(self, db_session):
        """Edge case: closed positions are NOT added to allocation buckets."""
        from app.models import Position
        from app.routers.accounts_query_router import get_rebalance_status
        user, account = await self._make_account(db_session, "closed")

        pos = Position(
            account_id=account.id,
            product_id="ETH-USD",
            status="closed",
            direction="long",
            total_base_acquired=1.0,
            entry_price=2000.0,
            initial_quote_balance=2000.0,
            max_quote_allowed=2000.0,
            total_quote_spent=2000.0,
            average_buy_price=2000.0,
            opened_at=datetime.utcnow(),
            closed_at=datetime.utcnow(),
        )
        db_session.add(pos)
        await db_session.flush()

        mock_coinbase = AsyncMock()
        mock_coinbase.get_usd_balance = AsyncMock(return_value=100.0)
        mock_coinbase.get_btc_balance = AsyncMock(return_value=0.0)
        mock_coinbase.get_eth_balance = AsyncMock(return_value=0.0)
        mock_coinbase.get_usdc_balance = AsyncMock(return_value=0.0)
        mock_coinbase.get_current_price = AsyncMock(
            side_effect=lambda pid: {"BTC-USD": 50000.0, "ETH-USD": 2000.0, "USDC-USD": 1.0}.get(pid, 0.0)
        )

        with patch("app.services.exchange_service.get_coinbase_for_account", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_coinbase
            result = await get_rebalance_status(
                account_id=account.id, db=db_session, current_user=user,
            )

        # Only $100 free USD; closed position value should NOT be included
        assert result["total_value_usd"] == pytest.approx(100.0, abs=1.0)

    @pytest.mark.asyncio
    async def test_position_price_fallback_to_entry_price(self, db_session):
        """Edge case: when live price fetch fails, falls back to position entry_price."""
        from app.models import Position
        from app.routers.accounts_query_router import get_rebalance_status
        user, account = await self._make_account(db_session, "fallback")

        pos = Position(
            account_id=account.id,
            product_id="LINK-USD",
            status="open",
            direction="long",
            total_base_acquired=10.0,
            entry_price=15.0,  # fallback price
            initial_quote_balance=150.0,
            max_quote_allowed=150.0,
            total_quote_spent=150.0,
            average_buy_price=15.0,
            opened_at=datetime.utcnow(),
        )
        db_session.add(pos)
        await db_session.flush()

        mock_coinbase = AsyncMock()
        mock_coinbase.get_usd_balance = AsyncMock(return_value=0.0)
        mock_coinbase.get_btc_balance = AsyncMock(return_value=0.0)
        mock_coinbase.get_eth_balance = AsyncMock(return_value=0.0)
        mock_coinbase.get_usdc_balance = AsyncMock(return_value=0.0)

        # Bulk price list omits LINK-USD — simulates missing/unavailable price
        # so the code falls back to position.entry_price.
        bulk = _bulk_products({"BTC-USD": 50000.0, "ETH-USD": 2000.0, "USDC-USD": 1.0})

        with patch("app.services.exchange_service.get_coinbase_for_account", new_callable=AsyncMock) as mock_get, \
             patch("app.coinbase_api.public_market_data.list_products", new_callable=AsyncMock, return_value=bulk):
            mock_get.return_value = mock_coinbase
            result = await get_rebalance_status(
                account_id=account.id, db=db_session, current_user=user,
            )

        # 10 tokens * $15 entry = $150 in USD bucket via fallback
        assert result["total_value_usd"] == pytest.approx(150.0, abs=1.0)


# =============================================================================
# _compute_allocation pure function unit tests
# =============================================================================


class TestComputeAllocation:
    """Direct unit tests for the _compute_allocation pure function."""

    def test_happy_path_mixed_portfolio(self):
        """Standard case: multiple currencies produce correct percentages."""
        from app.routers.accounts_query_router import _compute_allocation

        balances = {"USD": 5000.0, "BTC": 0.1, "ETH": 2.0, "USDC": 1000.0, "USDT": 0.0}
        prices = {"BTC-USD": 50000.0, "ETH-USD": 3000.0, "USDC-USD": 1.0, "USDT-USD": 1.0}
        result = _compute_allocation(balances, prices)

        # BTC = 0.1 * 50000 = 5000, ETH = 2 * 3000 = 6000
        # Total = 5000 + 5000 + 6000 + 1000 + 0 = 17000
        assert result["total_value_usd"] == pytest.approx(17000.0)
        assert result["current_usd_pct"] == pytest.approx(round(5000 / 17000 * 100, 2))
        assert result["current_btc_pct"] == pytest.approx(round(5000 / 17000 * 100, 2))
        assert result["current_eth_pct"] == pytest.approx(round(6000 / 17000 * 100, 2))
        assert result["current_usdc_pct"] == pytest.approx(round(1000 / 17000 * 100, 2))
        assert result["current_usdt_pct"] == pytest.approx(0.0)

    def test_zero_total_returns_all_zeros(self):
        """Edge case: zero balances produce 0% across the board."""
        from app.routers.accounts_query_router import _compute_allocation

        balances = {"USD": 0.0, "BTC": 0.0, "ETH": 0.0, "USDC": 0.0, "USDT": 0.0}
        prices = {"BTC-USD": 50000.0, "ETH-USD": 3000.0, "USDC-USD": 1.0, "USDT-USD": 1.0}
        result = _compute_allocation(balances, prices)

        assert result["total_value_usd"] == 0.0
        assert result["current_usd_pct"] == 0.0
        assert result["current_btc_pct"] == 0.0
        assert result["current_eth_pct"] == 0.0

    def test_total_override_uses_custom_denominator(self):
        """total_override replaces the computed total for percentage calculation."""
        from app.routers.accounts_query_router import _compute_allocation

        balances = {"USD": 500.0, "BTC": 0.0, "ETH": 0.0, "USDC": 0.0, "USDT": 0.0}
        prices = {"BTC-USD": 50000.0, "ETH-USD": 3000.0, "USDC-USD": 1.0, "USDT-USD": 1.0}
        result = _compute_allocation(balances, prices, total_override=10000.0)

        # USD pct should be 500/10000 = 5%, not 500/500 = 100%
        assert result["total_value_usd"] == pytest.approx(10000.0)
        assert result["current_usd_pct"] == pytest.approx(5.0)

    def test_missing_balance_keys_default_to_zero(self):
        """Balances dict missing keys should not crash — defaults to 0."""
        from app.routers.accounts_query_router import _compute_allocation

        balances = {"USD": 1000.0}  # Missing BTC, ETH, USDC, USDT
        prices = {"BTC-USD": 50000.0, "ETH-USD": 3000.0, "USDC-USD": 1.0, "USDT-USD": 1.0}
        result = _compute_allocation(balances, prices)

        assert result["total_value_usd"] == pytest.approx(1000.0)
        assert result["current_usd_pct"] == pytest.approx(100.0)
        assert result["current_btc_pct"] == pytest.approx(0.0)

    def test_missing_price_keys_default_to_zero(self):
        """Missing price keys default correctly (USDC/USDT fallback to 1.0 in caller)."""
        from app.routers.accounts_query_router import _compute_allocation

        balances = {"USD": 0.0, "BTC": 1.0, "ETH": 0.0, "USDC": 0.0, "USDT": 0.0}
        prices = {}  # No prices at all — BTC-USD defaults to 0
        result = _compute_allocation(balances, prices)

        # BTC * 0 = 0, USDC * 1.0 (default) = 0, total = 0
        assert result["total_value_usd"] == 0.0
        assert result["current_btc_pct"] == 0.0

    def test_single_currency_is_100_percent(self):
        """A portfolio with only one non-zero currency should be 100% that currency."""
        from app.routers.accounts_query_router import _compute_allocation

        balances = {"USD": 0.0, "BTC": 2.0, "ETH": 0.0, "USDC": 0.0, "USDT": 0.0}
        prices = {"BTC-USD": 80000.0, "ETH-USD": 3000.0, "USDC-USD": 1.0, "USDT-USD": 1.0}
        result = _compute_allocation(balances, prices)

        assert result["total_value_usd"] == pytest.approx(160000.0)
        assert result["current_btc_pct"] == pytest.approx(100.0)


# =============================================================================
# Reserve / deployable logic tests
# =============================================================================


class TestRebalanceReserveDeployable:
    """Tests for the reserve subtraction and deployable pool logic in rebalance status."""

    @pytest.mark.asyncio
    async def test_reserve_reduces_deployable(self, db_session, test_user):
        """Reserves are subtracted from total to compute deployable value."""
        import json
        from app.routers.accounts_query_router import get_rebalance_status

        account = Account(
            id=20, user_id=test_user.id, name="Reserve Test",
            type="cex", is_paper_trading=True,
            paper_balances=json.dumps({"USD": 10000.0, "BTC": 0.0}),
            rebalance_enabled=True,
            min_balance_usd=2000.0,
            min_balance_btc=0.0,
            min_balance_eth=0.0,
            min_balance_usdc=0.0,
            min_balance_usdt=0.0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db_session.add(account)
        await db_session.flush()

        with patch("app.services.rebalance_service.get_public_prices", new_callable=AsyncMock) as mock_prices:
            mock_prices.return_value = {"BTC-USD": 50000.0, "ETH-USD": 3000.0, "USDC-USD": 1.0, "USDT-USD": 1.0}
            result = await get_rebalance_status(
                account_id=account.id, db=db_session, current_user=test_user,
            )

        assert result["total_value_usd"] == pytest.approx(10000.0)
        assert result["reserve_value_usd"] == pytest.approx(2000.0)
        assert result["deployable_value_usd"] == pytest.approx(8000.0)

    @pytest.mark.asyncio
    async def test_reserve_exceeding_balance_caps_at_balance(self, db_session, test_user):
        """Reserve pct should be capped at actual balance, not exceed it."""
        import json
        from app.routers.accounts_query_router import get_rebalance_status

        account = Account(
            id=21, user_id=test_user.id, name="Over-Reserve",
            type="cex", is_paper_trading=True,
            paper_balances=json.dumps({"USD": 100.0, "BTC": 0.0}),
            rebalance_enabled=True,
            min_balance_usd=5000.0,  # Reserve > actual balance
            min_balance_btc=0.0, min_balance_eth=0.0,
            min_balance_usdc=0.0, min_balance_usdt=0.0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db_session.add(account)
        await db_session.flush()

        with patch("app.services.rebalance_service.get_public_prices", new_callable=AsyncMock) as mock_prices:
            mock_prices.return_value = {"BTC-USD": 50000.0, "ETH-USD": 3000.0, "USDC-USD": 1.0, "USDT-USD": 1.0}
            result = await get_rebalance_status(
                account_id=account.id, db=db_session, current_user=test_user,
            )

        # Reserve % capped at actual $100 balance, not $5000 setting
        assert result["reserve_usd_pct"] == pytest.approx(100.0)
        # Deployable can't go negative
        assert result["deployable_value_usd"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_default_targets_when_none(self, db_session, test_user):
        """When target percentages are None, defaults are applied (34/33/33/0/0)."""
        import json
        from app.routers.accounts_query_router import get_rebalance_status

        account = Account(
            id=22, user_id=test_user.id, name="Default Targets",
            type="cex", is_paper_trading=True,
            paper_balances=json.dumps({"USD": 1000.0}),
            rebalance_target_usd_pct=None,
            rebalance_target_btc_pct=None,
            rebalance_target_eth_pct=None,
            rebalance_target_usdc_pct=None,
            rebalance_target_usdt_pct=None,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db_session.add(account)
        await db_session.flush()

        with patch("app.services.rebalance_service.get_public_prices", new_callable=AsyncMock) as mock_prices:
            mock_prices.return_value = {"BTC-USD": 50000.0, "ETH-USD": 3000.0, "USDC-USD": 1.0, "USDT-USD": 1.0}
            result = await get_rebalance_status(
                account_id=account.id, db=db_session, current_user=test_user,
            )

        assert result["target_usd_pct"] == 34.0
        assert result["target_btc_pct"] == 33.0
        assert result["target_eth_pct"] == 33.0
        assert result["target_usdc_pct"] == 0.0
        assert result["target_usdt_pct"] == 0.0


# =============================================================================
# get_default_account
# =============================================================================


class TestGetDefaultAccount:
    """Tests for the /accounts/default endpoint."""

    @pytest.mark.asyncio
    async def test_get_default_returns_default_account(
        self, db_session, test_user, test_account,
    ):
        """Happy path: returns the account marked is_default=True."""
        from app.routers.accounts_query_router import get_default_account
        result = await get_default_account(db=db_session, current_user=test_user)
        assert result.id == test_account.id
        assert result.is_default is True

    @pytest.mark.asyncio
    async def test_get_default_falls_back_to_first_active(
        self, db_session, test_user,
    ):
        """Edge case: no is_default account → returns oldest active."""
        acct1 = Account(
            id=100, user_id=test_user.id, name="First", type="cex",
            is_default=False, is_active=True,
            created_at=datetime(2024, 1, 1), updated_at=datetime.utcnow(),
        )
        acct2 = Account(
            id=101, user_id=test_user.id, name="Second", type="cex",
            is_default=False, is_active=True,
            created_at=datetime(2024, 6, 1), updated_at=datetime.utcnow(),
        )
        db_session.add_all([acct1, acct2])
        await db_session.flush()

        from app.routers.accounts_query_router import get_default_account
        result = await get_default_account(db=db_session, current_user=test_user)
        assert result.id == 100  # earliest created_at

    @pytest.mark.asyncio
    async def test_get_default_no_accounts_raises_404(
        self, db_session, test_user,
    ):
        """Failure case: user with no accounts raises 404."""
        from app.routers.accounts_query_router import get_default_account
        with pytest.raises(HTTPException) as exc_info:
            await get_default_account(db=db_session, current_user=test_user)
        assert exc_info.value.status_code == 404


# =============================================================================
# get_perps_portfolio_status
# =============================================================================


class TestGetPerpsPortfolioStatus:
    """Tests for the /accounts/{id}/perps-portfolio endpoint."""

    @pytest.mark.asyncio
    async def test_returns_linking_status_unlinked(
        self, db_session, test_user, test_account,
    ):
        """Happy path: returns linked=False when perps_portfolio_uuid is None."""
        from app.routers.accounts_query_router import get_perps_portfolio_status
        result = await get_perps_portfolio_status(
            account_id=test_account.id, db=db_session, current_user=test_user,
        )
        assert result["linked"] is False
        assert result["account_id"] == test_account.id

    @pytest.mark.asyncio
    async def test_returns_linked_when_uuid_present(
        self, db_session, test_user, test_account,
    ):
        """Happy path: returns linked=True when perps_portfolio_uuid is set."""
        test_account.perps_portfolio_uuid = "test-uuid-abc"
        await db_session.flush()

        from app.routers.accounts_query_router import get_perps_portfolio_status
        result = await get_perps_portfolio_status(
            account_id=test_account.id, db=db_session, current_user=test_user,
        )
        assert result["linked"] is True
        assert result["perps_portfolio_uuid"] == "test-uuid-abc"

    @pytest.mark.asyncio
    async def test_not_found_raises_404(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_query_router import get_perps_portfolio_status
        with pytest.raises(HTTPException) as exc_info:
            await get_perps_portfolio_status(
                account_id=9999, db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_not_owner_raises_404(self, db_session, test_user):
        """Failure: another user's account returns 404 (not 403) so account
        IDs can't be enumerated from outside the ownership boundary.
        """
        other_user = User(
            id=999, email="other@test.com",
            hashed_password="x", is_active=True,
        )
        db_session.add(other_user)
        await db_session.flush()
        foreign_account = Account(
            id=500, user_id=other_user.id, name="Other",
            type="cex", is_active=True,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db_session.add(foreign_account)
        await db_session.flush()

        from app.routers.accounts_query_router import get_perps_portfolio_status
        with pytest.raises(HTTPException) as exc_info:
            await get_perps_portfolio_status(
                account_id=foreign_account.id, db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# Dust Sweep — GET settings
# =============================================================================


class TestGetDustSweepSettings:
    """Tests for /accounts/{id}/dust-sweep-settings (GET)."""

    @pytest.mark.asyncio
    async def test_returns_defaults_for_paper_account(
        self, db_session, test_user,
    ):
        """Happy path: paper account with empty balances returns defaults."""
        import json
        account = Account(
            id=700, user_id=test_user.id, name="Paper Dust",
            type="cex", is_paper_trading=True,
            paper_balances=json.dumps({"USD": 1000.0}),
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db_session.add(account)
        await db_session.flush()

        from app.routers.accounts_query_router import get_dust_sweep_settings
        result = await get_dust_sweep_settings(
            account_id=account.id, db=db_session, current_user=test_user,
        )
        assert result["enabled"] is False
        assert result["threshold_usd"] == 5.0
        assert result["dust_positions"] == []

    @pytest.mark.asyncio
    async def test_not_found_raises_404(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_query_router import get_dust_sweep_settings
        with pytest.raises(HTTPException) as exc_info:
            await get_dust_sweep_settings(
                account_id=9999, db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_paper_account_reports_dust_positions(
        self, db_session, test_user,
    ):
        """Happy path: paper account with small altcoin balance → dust position."""
        import json
        account = Account(
            id=701, user_id=test_user.id, name="Paper With Dust",
            type="cex", is_paper_trading=True,
            paper_balances=json.dumps({"USD": 100.0, "DOGE": 50.0}),
            dust_sweep_threshold_usd=1.0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db_session.add(account)
        await db_session.flush()

        # Mock prices: DOGE at $0.20 → $10 position, above $1 threshold
        with patch(
            "app.routers.accounts_query_router.get_public_prices",
            new_callable=AsyncMock,
            return_value={"DOGE-USD": 0.20},
        ):
            from app.routers.accounts_query_router import get_dust_sweep_settings
            result = await get_dust_sweep_settings(
                account_id=account.id, db=db_session, current_user=test_user,
            )

        assert any(p["coin"] == "DOGE" for p in result["dust_positions"])


# =============================================================================
# Dust Sweep — PUT settings
# =============================================================================


class TestUpdateDustSweepSettings:
    """Tests for PUT /accounts/{id}/dust-sweep-settings."""

    @pytest.mark.asyncio
    async def test_update_enabled_and_threshold(
        self, db_session, test_user, test_account,
    ):
        """Happy path: updates enabled + threshold fields."""
        from app.routers.accounts_mutation_router import (
            update_dust_sweep_settings,
        )
        from app.schemas.accounts import DustSweepSettingsUpdate
        settings = DustSweepSettingsUpdate(enabled=True, threshold_usd=25.0)
        result = await update_dust_sweep_settings(
            account_id=test_account.id, settings=settings,
            db=db_session, current_user=test_user,
        )
        assert result["enabled"] is True
        assert result["threshold_usd"] == 25.0

    @pytest.mark.asyncio
    async def test_update_not_found_raises_404(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_mutation_router import (
            update_dust_sweep_settings,
        )
        from app.schemas.accounts import DustSweepSettingsUpdate
        settings = DustSweepSettingsUpdate(enabled=True)
        with pytest.raises(HTTPException) as exc_info:
            await update_dust_sweep_settings(
                account_id=9999, settings=settings,
                db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_partial_only_threshold(
        self, db_session, test_user, test_account,
    ):
        """Edge case: omitting enabled leaves it unchanged."""
        test_account.dust_sweep_enabled = True
        await db_session.flush()

        from app.routers.accounts_mutation_router import (
            update_dust_sweep_settings,
        )
        from app.schemas.accounts import DustSweepSettingsUpdate
        settings = DustSweepSettingsUpdate(threshold_usd=10.0)
        result = await update_dust_sweep_settings(
            account_id=test_account.id, settings=settings,
            db=db_session, current_user=test_user,
        )
        assert result["enabled"] is True  # unchanged
        assert result["threshold_usd"] == 10.0


# =============================================================================
# Dust Sweep — POST execute
# =============================================================================


class TestSweepDust:
    """Tests for POST /accounts/{id}/dust-sweep."""

    @pytest.mark.asyncio
    async def test_sweep_not_cex_raises_400(
        self, db_session, test_user, test_account_dex,
    ):
        """Failure case: DEX account raises 400."""
        from app.routers.accounts_mutation_router import sweep_dust
        with pytest.raises(HTTPException) as exc_info:
            await sweep_dust(
                account_id=test_account_dex.id,
                db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_sweep_not_found_raises_404(self, db_session, test_user):
        """Failure case: non-existent account raises 404."""
        from app.routers.accounts_mutation_router import sweep_dust
        with pytest.raises(HTTPException) as exc_info:
            await sweep_dust(
                account_id=9999, db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch(
        "app.routers.accounts_mutation_router.get_coinbase_for_account",
        new_callable=AsyncMock,
    )
    @patch("app.services.rebalance_monitor.execute_dust_sweep", new_callable=AsyncMock)
    async def test_sweep_success_returns_summary(
        self, mock_sweep, mock_coinbase, db_session, test_user, test_account,
    ):
        """Happy path: sweep returns summary with successes + failures."""
        mock_coinbase.return_value = AsyncMock()
        mock_sweep.return_value = [
            {
                "status": "success", "coin": "DOGE",
                "amount": 10.0, "usd_value": 2.0,
                "target_currency": "USD", "order_id": "o-1",
            },
            {
                "status": "failed", "coin": "ADA",
                "amount": 5.0, "usd_value": 1.5,
                "error": "order rejected",
            },
        ]

        from app.routers.accounts_mutation_router import sweep_dust
        result = await sweep_dust(
            account_id=test_account.id, db=db_session, current_user=test_user,
        )
        assert result["swept"] == 1
        assert result["failed"] == 1
        assert result["details"][0]["coin"] == "DOGE"
        assert result["errors"][0]["coin"] == "ADA"
