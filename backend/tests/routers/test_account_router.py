"""
Tests for backend/app/routers/account_router.py

Covers account/portfolio endpoints: get_balances, aggregate_value,
portfolio, sell_portfolio_to_base, and helper functions
(get_user_paper_account, get_coinbase_from_db).
"""

import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Account, User


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def user_with_paper_account(db_session):
    """Create a user with only a paper trading account (no live account)."""
    user = User(
        email="paperonly@example.com",
        hashed_password="hashed",
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.flush()

    paper = Account(
        user_id=user.id,
        name="Paper Trading",
        type="cex",
        exchange="coinbase",
        is_default=True,
        is_active=True,
        is_paper_trading=True,
        paper_balances=json.dumps({
            "BTC": 0.5,
            "ETH": 5.0,
            "USD": 50000.0,
            "USDC": 1000.0,
            "USDT": 0.0,
        }),
    )
    db_session.add(paper)
    await db_session.flush()

    return user, paper


@pytest.fixture
async def user_with_live_account(db_session):
    """Create a user with a live CEX account."""
    user = User(
        email="livetrader@example.com",
        hashed_password="hashed",
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.flush()

    live = Account(
        user_id=user.id,
        name="Coinbase Live",
        type="cex",
        exchange="coinbase",
        is_default=True,
        is_active=True,
        is_paper_trading=False,
        api_key_name="test-key",
        api_private_key="test-private-key",
    )
    db_session.add(live)
    await db_session.flush()

    return user, live


# =============================================================================
# get_user_paper_account helper
# =============================================================================


class TestGetUserPaperAccount:
    """Tests for get_user_paper_account()"""

    @pytest.mark.asyncio
    async def test_returns_paper_account_for_paper_only_user(self, db_session, user_with_paper_account):
        """Happy path: returns paper account when user has no live account."""
        from app.routers.account_router import get_user_paper_account

        user, paper = user_with_paper_account
        result = await get_user_paper_account(db_session, user.id)
        assert result is not None
        assert result.id == paper.id
        assert result.is_paper_trading is True

    @pytest.mark.asyncio
    async def test_returns_none_when_live_account_exists(self, db_session, user_with_live_account):
        """Edge case: returns None when user has a live CEX account."""
        from app.routers.account_router import get_user_paper_account

        user, live = user_with_live_account
        result = await get_user_paper_account(db_session, user.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_user_without_accounts(self, db_session):
        """Edge case: returns None for user with no accounts at all."""
        from app.routers.account_router import get_user_paper_account

        user = User(
            email="noaccts@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        result = await get_user_paper_account(db_session, user.id)
        assert result is None


# =============================================================================
# get_coinbase_from_db helper
# =============================================================================


class TestGetCoinbaseFromDb:
    """Tests for get_coinbase_from_db()"""

    @pytest.mark.asyncio
    async def test_no_account_returns_503(self, db_session):
        """Failure: no CEX account returns 503."""
        from fastapi import HTTPException
        from app.routers.account_router import get_coinbase_from_db

        user = User(
            email="noacct_coinbase@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_coinbase_from_db(db_session, user.id)
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_account_without_credentials_returns_503(self, db_session):
        """Failure: account without API credentials returns 503."""
        from fastapi import HTTPException
        from app.routers.account_router import get_coinbase_from_db

        user = User(
            email="nocreds_coinbase@example.com",
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
            is_paper_trading=False,
            api_key_name=None,
            api_private_key=None,
        )
        db_session.add(account)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_coinbase_from_db(db_session, user.id)
        assert exc_info.value.status_code == 503
        assert "credentials" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_paper_trading_account_is_excluded(self, db_session, user_with_paper_account):
        """Edge case: paper trading account is not used by get_coinbase_from_db."""
        from fastapi import HTTPException
        from app.routers.account_router import get_coinbase_from_db

        user, _ = user_with_paper_account
        with pytest.raises(HTTPException) as exc_info:
            await get_coinbase_from_db(db_session, user.id)
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    @patch("app.routers.account_router.create_exchange_client")
    @patch("app.routers.account_router.is_encrypted", return_value=False)
    async def test_valid_account_returns_client(self, mock_encrypted, mock_create, db_session, user_with_live_account):
        """Happy path: valid account returns exchange client."""
        from app.routers.account_router import get_coinbase_from_db

        mock_client = MagicMock()
        mock_create.return_value = mock_client

        user, _ = user_with_live_account
        result = await get_coinbase_from_db(db_session, user.id)
        assert result is mock_client
        mock_create.assert_called_once()


# =============================================================================
# GET /api/account/balances
# =============================================================================


class TestGetBalances:
    """Tests for GET /api/account/balances"""

    @pytest.mark.asyncio
    @patch("app.routers.account_router.get_public_price", new_callable=AsyncMock, create=True)
    @patch("app.routers.account_router.get_public_btc_price", new_callable=AsyncMock, create=True)
    async def test_paper_trading_balances(self, mock_btc_price, mock_price, db_session, user_with_paper_account):
        """Happy path: paper trading account returns virtual balances."""
        from app.routers.account_router import get_balances

        user, paper_account = user_with_paper_account

        # We need to patch the imports inside the function
        with patch(
            "app.coinbase_api.public_market_data.get_current_price",
            new_callable=AsyncMock, return_value=0.035
        ), patch(
            "app.coinbase_api.public_market_data.get_btc_usd_price",
            new_callable=AsyncMock, return_value=60000.0
        ):
            result = await get_balances(
                account_id=paper_account.id,
                db=db_session,
                current_user=user,
            )

        assert result["btc"] == 0.5
        assert result["eth"] == 5.0
        assert result["usd"] == 50000.0
        assert "reserved_in_positions" in result
        assert "available_btc" in result

    @pytest.mark.asyncio
    async def test_no_account_returns_404(self, db_session):
        """Failure: no active account returns 404 or 500 (caught by exception handler)."""
        from fastapi import HTTPException
        from app.routers.account_router import get_balances

        user = User(
            email="nobalances@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_balances(account_id=None, db=db_session, current_user=user)
        # The function catches generic exceptions and raises 500, or raises 404 for no account
        assert exc_info.value.status_code in (404, 500)

    @pytest.mark.asyncio
    async def test_nonexistent_account_id_returns_error(self, db_session):
        """Failure: non-existent account_id returns 404 or 500."""
        from fastapi import HTTPException
        from app.routers.account_router import get_balances

        user = User(
            email="wrongid@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_balances(account_id=99999, db=db_session, current_user=user)
        assert exc_info.value.status_code in (404, 500)


# =============================================================================
# GET /api/account/aggregate-value
# =============================================================================


class TestGetAggregateValue:
    """Tests for GET /api/account/aggregate-value"""

    @pytest.mark.asyncio
    @patch("app.routers.account_router.get_exchange_client_for_account")
    async def test_paper_user_aggregate_value(self, mock_get_client, db_session, user_with_paper_account):
        """Happy path: paper-only user gets aggregate value from paper client."""
        from app.routers.account_router import get_aggregate_value

        user, _ = user_with_paper_account

        mock_client = MagicMock()
        mock_client.calculate_aggregate_btc_value = AsyncMock(return_value=1.5)
        mock_client.calculate_aggregate_usd_value = AsyncMock(return_value=90000.0)
        mock_client.get_btc_usd_price = AsyncMock(return_value=60000.0)
        mock_get_client.return_value = mock_client

        result = await get_aggregate_value(db=db_session, current_user=user)
        assert result["aggregate_btc_value"] == 1.5
        assert result["aggregate_usd_value"] == 90000.0
        assert result["btc_usd_price"] == 60000.0

    @pytest.mark.asyncio
    @patch("app.routers.account_router.get_exchange_client_for_account")
    async def test_paper_user_client_failure_returns_defaults(
        self, mock_get_client, db_session, user_with_paper_account
    ):
        """Edge case: paper user with failed client returns zero defaults."""
        from app.routers.account_router import get_aggregate_value

        user, _ = user_with_paper_account
        mock_get_client.return_value = None

        result = await get_aggregate_value(db=db_session, current_user=user)
        assert result["aggregate_btc_value"] == 0.0
        assert result["aggregate_usd_value"] == 0.0
        assert result["btc_usd_price"] == 0.0


# =============================================================================
# GET /api/account/conversion-status/{task_id}
# =============================================================================


class TestGetConversionStatus:
    """Tests for GET /api/account/conversion-status/{task_id}"""

    @pytest.mark.asyncio
    @patch("app.routers.account_router.pcs")
    async def test_existing_task_returns_progress(self, mock_pcs):
        """Happy path: returns progress for existing task."""
        from app.routers.account_router import get_conversion_status

        mock_pcs.get_task_progress.return_value = {
            "status": "running",
            "current": 5,
            "total": 10,
        }
        user = MagicMock(spec=User)
        result = await get_conversion_status(task_id="task-123", current_user=user)
        assert result["status"] == "running"

    @pytest.mark.asyncio
    @patch("app.routers.account_router.pcs")
    async def test_nonexistent_task_returns_404(self, mock_pcs):
        """Failure: non-existent task returns 404."""
        from fastapi import HTTPException
        from app.routers.account_router import get_conversion_status

        mock_pcs.get_task_progress.return_value = None
        user = MagicMock(spec=User)

        with pytest.raises(HTTPException) as exc_info:
            await get_conversion_status(task_id="nonexistent", current_user=user)
        assert exc_info.value.status_code == 404


# =============================================================================
# POST /api/account/sell-portfolio-to-base
# =============================================================================


class TestSellPortfolioToBase:
    """Tests for POST /api/account/sell-portfolio-to-base"""

    @pytest.mark.asyncio
    async def test_without_confirm_returns_400(self, db_session):
        """Failure: missing confirm=true returns 400."""
        from fastapi import HTTPException
        from app.routers.account_router import sell_portfolio_to_base_currency

        user = MagicMock(spec=User)
        user.id = 1

        # Create a mock BackgroundTasks
        bg = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await sell_portfolio_to_base_currency(
                background_tasks=bg,
                target_currency="BTC",
                confirm=False,
                account_id=None,
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_target_currency_returns_400(self, db_session):
        """Failure: invalid target currency returns 400."""
        from fastapi import HTTPException
        from app.routers.account_router import sell_portfolio_to_base_currency

        user = MagicMock(spec=User)
        user.id = 1
        bg = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await sell_portfolio_to_base_currency(
                background_tasks=bg,
                target_currency="DOGE",
                confirm=True,
                account_id=None,
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_no_account_returns_404(self, db_session):
        """Failure: no default account returns 404."""
        from fastapi import HTTPException
        from app.routers.account_router import sell_portfolio_to_base_currency

        user = User(
            email="noacct_sell@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        bg = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await sell_portfolio_to_base_currency(
                background_tasks=bg,
                target_currency="BTC",
                confirm=True,
                account_id=None,
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_successful_conversion_start(self, db_session, user_with_live_account):
        """Happy path: starts background conversion and returns task_id."""
        from app.routers.account_router import sell_portfolio_to_base_currency

        user, account = user_with_live_account
        # Mark account as default
        account.is_default = True
        await db_session.flush()

        bg = MagicMock()

        result = await sell_portfolio_to_base_currency(
            background_tasks=bg,
            target_currency="BTC",
            confirm=True,
            account_id=None,
            db=db_session,
            current_user=user,
        )
        assert "task_id" in result
        assert "started" in result["message"].lower()
        bg.add_task.assert_called_once()
