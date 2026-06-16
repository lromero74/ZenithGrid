"""
Tests for backend/app/routers/account_router.py

Covers account/portfolio endpoints: get_balances, aggregate_value,
portfolio, sell_portfolio_to_base, and helper functions
(get_user_paper_account, get_coinbase_from_db).
"""

import json
from app.utils.timeutil import utcnow
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.models import Account, Bot, PendingOrder, Position, User


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
        created_at=utcnow(),
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
        created_at=utcnow(),
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
        from app.services.portfolio_service import get_user_paper_account

        user, paper = user_with_paper_account
        result = await get_user_paper_account(db_session, user.id)
        assert result is not None
        assert result.id == paper.id
        assert result.is_paper_trading is True

    @pytest.mark.asyncio
    async def test_returns_none_when_live_account_exists(self, db_session, user_with_live_account):
        """Edge case: returns None when user has a live CEX account."""
        from app.services.portfolio_service import get_user_paper_account

        user, live = user_with_live_account
        result = await get_user_paper_account(db_session, user.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_user_without_accounts(self, db_session):
        """Edge case: returns None for user with no accounts at all."""
        from app.services.portfolio_service import get_user_paper_account

        user = User(
            email="noaccts@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=utcnow(),
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
        from app.exceptions import ExchangeUnavailableError
        from app.services.portfolio_service import get_coinbase_from_db

        user = User(
            email="noacct_coinbase@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(ExchangeUnavailableError) as exc_info:
            await get_coinbase_from_db(db_session, user.id)
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_account_without_credentials_returns_503(self, db_session):
        """Failure: account without API credentials returns 503."""
        from app.exceptions import ExchangeUnavailableError
        from app.services.portfolio_service import get_coinbase_from_db

        user = User(
            email="nocreds_coinbase@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=utcnow(),
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

        with pytest.raises(ExchangeUnavailableError) as exc_info:
            await get_coinbase_from_db(db_session, user.id)
        assert exc_info.value.status_code == 503
        assert "credentials" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_paper_trading_account_is_excluded(self, db_session, user_with_paper_account):
        """Edge case: paper trading account is not used by get_coinbase_from_db."""
        from app.exceptions import ExchangeUnavailableError
        from app.services.portfolio_service import get_coinbase_from_db

        user, _ = user_with_paper_account
        with pytest.raises(ExchangeUnavailableError) as exc_info:
            await get_coinbase_from_db(db_session, user.id)
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    @patch("app.services.portfolio_service.create_exchange_client")
    @patch("app.services.portfolio_service.is_encrypted", return_value=False)
    async def test_valid_account_returns_client(self, mock_encrypted, mock_create, db_session, user_with_live_account):
        """Happy path: valid account returns exchange client."""
        from app.services.portfolio_service import get_coinbase_from_db

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
    async def test_paper_trading_balances(self, db_session, user_with_paper_account):
        """Happy path: paper trading account returns virtual balances."""
        from app.routers.account_router import get_balances

        user, paper_account = user_with_paper_account

        # Patch the deferred imports used inside portfolio_service.get_account_balances
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
    @patch("app.services.portfolio_service.get_coinbase_from_db", new_callable=AsyncMock)
    async def test_available_usd_excludes_open_position_spend(
        self, mock_get_cb, db_session, user_with_live_account
    ):
        """Available USD = wallet - pending only; a position's already-spent quote is
        NOT subtracted again (the $12.85-vs-$29.43 bug). Pending buys ARE subtracted."""
        user, account = user_with_live_account

        bot = Bot(account_id=account.id, user_id=user.id, name="B", strategy_type="rsi")
        db_session.add(bot)
        await db_session.flush()
        # Open USD position that already spent $30 buying its coin.
        position = Position(
            account_id=account.id, bot_id=bot.id, user_id=user.id, product_id="FOX-USD",
            status="open", direction="long", total_base_acquired=60.0,
            total_quote_spent=30.0, average_buy_price=0.5,
        )
        db_session.add(position)
        await db_session.flush()
        # $10 committed to an unfilled limit BUY.
        db_session.add(PendingOrder(
            position_id=position.id, bot_id=bot.id, order_id="o-1", product_id="FOX-USD",
            side="BUY", order_type="LIMIT", limit_price=0.4, quote_amount=10.0,
            base_amount=25.0, trade_type="safety_order_1", status="pending",
            reserved_amount_quote=10.0, created_at=utcnow(),
        ))
        await db_session.flush()

        fake = MagicMock()
        fake.get_btc_balance = AsyncMock(return_value=0.0)
        fake.get_eth_balance = AsyncMock(return_value=0.0)
        fake.get_usd_balance = AsyncMock(return_value=100.0)
        fake.get_usdc_balance = AsyncMock(return_value=0.0)
        fake.get_usdt_balance = AsyncMock(return_value=0.0)
        fake.get_current_price = AsyncMock(return_value=0.035)
        fake.get_btc_usd_price = AsyncMock(return_value=60000.0)
        mock_get_cb.return_value = fake

        from app.routers.account_router import get_balances
        result = await get_balances(account_id=account.id, db=db_session, current_user=user)

        # The position's $30 spend is still reported for the "In Pos." column...
        assert result["reserved_in_positions"]["USD"] == pytest.approx(30.0)
        assert result["reserved_in_pending_orders"]["USD"] == pytest.approx(10.0)
        # ...but available = wallet 100 - pending 10 = 90 (NOT 100 - 30 - 10 = 60).
        assert result["available_usd"] == pytest.approx(90.0)

    @pytest.mark.asyncio
    async def test_no_account_returns_404(self, db_session):
        """Failure: no active account raises an error."""
        from app.exceptions import AppError
        from app.routers.account_router import get_balances

        user = User(
            email="nobalances@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(AppError) as exc_info:
            await get_balances(account_id=None, db=db_session, current_user=user)
        assert exc_info.value.status_code in (404, 503)

    @pytest.mark.asyncio
    async def test_nonexistent_account_id_returns_error(self, db_session):
        """Failure: non-existent account_id raises an error."""
        from app.exceptions import AppError
        from app.routers.account_router import get_balances

        user = User(
            email="wrongid@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(AppError) as exc_info:
            await get_balances(account_id=99999, db=db_session, current_user=user)
        assert exc_info.value.status_code in (404, 503)


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
        mock_client.calculate_market_budget = AsyncMock(side_effect=lambda quote: {
            "BTC": 0.25,
            "USD": 1200.0,
            "USDC": 300.0,
            "ETH": 2.0,
            "USDT": 50.0,
            "EUR": 0.0,
            "GBP": 25.0,
        }[quote])
        mock_client.list_products = AsyncMock(return_value=[
            {"product_id": "BTC-USD", "quote_currency_id": "USD"},
            {"product_id": "ETH-USDC", "quote_currency_id": "USDC"},
            {"product_id": "BTC-GBP", "quote_currency": "GBP"},
        ])
        mock_client.get_btc_usd_price = AsyncMock(return_value=60000.0)
        mock_client.get_eth_usd_price = AsyncMock(return_value=3000.0)
        mock_get_client.return_value = mock_client

        result = await get_aggregate_value(account_id=None, db=db_session, current_user=user)
        assert result["aggregate_btc_value"] == 1.5
        assert result["aggregate_usd_value"] == 90000.0
        assert result["market_btc_value"] == 0.25
        assert result["market_usd_value"] == 1200.0
        assert result["market_usdc_value"] == 300.0
        assert result["market_eth_value"] == 2.0
        assert result["market_values"]["USDT"] == 50.0
        assert result["market_values"]["GBP"] == 25.0
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

        result = await get_aggregate_value(account_id=None, db=db_session, current_user=user)
        assert result["aggregate_btc_value"] == 0.0
        assert result["aggregate_usd_value"] == 0.0
        assert result["market_values"] == {}
        assert result["market_btc_value"] == 0.0
        assert result["market_usd_value"] == 0.0
        assert result["market_usdc_value"] == 0.0
        assert result["btc_usd_price"] == 0.0

    @pytest.mark.asyncio
    @patch("app.routers.account_router.get_exchange_client_for_account")
    async def test_explicit_account_id_scopes_to_that_account(
        self, mock_get_client, db_session, user_with_live_account
    ):
        """Happy path: an explicit account_id resolves the client for THAT
        account (not the user's first/default CEX account) so a multi-account
        user sees the correct per-account budget buckets."""
        from app.routers.account_router import get_aggregate_value

        user, live = user_with_live_account

        mock_client = MagicMock()
        mock_client.calculate_aggregate_btc_value = AsyncMock(return_value=0.1)
        mock_client.calculate_aggregate_usd_value = AsyncMock(return_value=50.0)
        mock_client.calculate_market_budget = AsyncMock(return_value=50.0)
        mock_client.list_products = AsyncMock(return_value=[])
        mock_client.get_btc_usd_price = AsyncMock(return_value=60000.0)
        mock_client.get_eth_usd_price = AsyncMock(return_value=3000.0)
        mock_get_client.return_value = mock_client

        result = await get_aggregate_value(
            account_id=live.id, db=db_session, current_user=user
        )

        # The client must be resolved for the requested account specifically.
        mock_get_client.assert_awaited_once_with(db_session, live.id)
        assert result["aggregate_usd_value"] == 50.0
        assert result["market_usd_value"] == 50.0

    @pytest.mark.asyncio
    @patch("app.routers.account_router.get_exchange_client_for_account")
    async def test_account_id_of_another_user_is_rejected(
        self, mock_get_client, db_session, user_with_live_account
    ):
        """Failure case (tenant isolation): requesting another user's account_id
        must NOT return that account's data — it raises NotFoundError and never
        builds a client for the foreign account."""
        from app.routers.account_router import get_aggregate_value
        from app.exceptions import NotFoundError

        _owner, foreign = user_with_live_account

        attacker = User(
            email="attacker@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=utcnow(),
        )
        db_session.add(attacker)
        await db_session.flush()

        with pytest.raises(NotFoundError):
            await get_aggregate_value(
                account_id=foreign.id, db=db_session, current_user=attacker
            )
        mock_get_client.assert_not_called()


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

    @pytest.mark.asyncio
    @patch("app.routers.account_router.pcs")
    async def test_wrong_user_cannot_access_task(self, mock_pcs):
        """IDOR: user B cannot poll user A's conversion task."""
        from fastapi import HTTPException
        from app.routers.account_router import get_conversion_status

        mock_pcs.get_task_progress.return_value = {
            "status": "running",
            "user_id": 1,
            "current": 5,
            "total": 10,
        }
        other_user = MagicMock(spec=User)
        other_user.id = 999  # Different user

        with pytest.raises(HTTPException) as exc_info:
            await get_conversion_status(task_id="task-123", current_user=other_user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("app.routers.account_router.pcs")
    async def test_correct_user_can_access_task(self, mock_pcs):
        """Owner can access their own conversion task."""
        from app.routers.account_router import get_conversion_status

        mock_pcs.get_task_progress.return_value = {
            "status": "running",
            "user_id": 42,
            "current": 5,
            "total": 10,
        }
        owner = MagicMock(spec=User)
        owner.id = 42

        result = await get_conversion_status(task_id="task-123", current_user=owner)
        assert result["status"] == "running"


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
                mfa_code=None,
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_target_currency_returns_400(self, db_session):
        """Failure: invalid target currency returns 400."""
        from app.routers.account_router import sell_portfolio_to_base_currency

        user = MagicMock(spec=User)
        user.id = 1
        bg = MagicMock()

        with patch("app.routers.account_router.verify_mfa", new_callable=AsyncMock):
            with pytest.raises(HTTPException) as exc_info:
                await sell_portfolio_to_base_currency(
                    background_tasks=bg,
                    target_currency="DOGE",
                    confirm=True,
                    account_id=None,
                    mfa_code="123456",
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
            created_at=utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        bg = MagicMock()

        with patch("app.routers.account_router.verify_mfa", new_callable=AsyncMock):
            with pytest.raises(HTTPException) as exc_info:
                await sell_portfolio_to_base_currency(
                    background_tasks=bg,
                    target_currency="BTC",
                    confirm=True,
                    account_id=None,
                    mfa_code="123456",
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

        with patch("app.routers.account_router.verify_mfa", new_callable=AsyncMock):
            result = await sell_portfolio_to_base_currency(
                background_tasks=bg,
                target_currency="BTC",
                confirm=True,
                account_id=None,
                mfa_code="123456",
                db=db_session,
                current_user=user,
            )
        assert "task_id" in result
        assert "started" in result["message"].lower()
        bg.add_task.assert_called_once()


# =============================================================================
# sell-portfolio-to-base MFA enforcement
# =============================================================================


class TestSellPortfolioMfa:
    """MFA must be verified before portfolio conversion starts."""

    @pytest.mark.asyncio
    async def test_sell_portfolio_without_mfa_code_returns_403(
        self, db_session, user_with_live_account
    ):
        """Request WITHOUT mfa_code when user has MFA enabled → 403."""
        from app.routers.account_router import sell_portfolio_to_base_currency

        user, account = user_with_live_account
        user.mfa_enabled = True
        user.totp_secret = "encrypted_secret"
        account.is_default = True
        await db_session.flush()

        bg = MagicMock()

        with patch("app.routers.account_router.verify_mfa", new_callable=AsyncMock) as mock_mfa:
            mock_mfa.side_effect = HTTPException(status_code=403, detail="MFA code required")
            with pytest.raises(HTTPException) as exc_info:
                await sell_portfolio_to_base_currency(
                    background_tasks=bg,
                    target_currency="USD",
                    confirm=True,
                    account_id=account.id,
                    mfa_code=None,
                    db=db_session,
                    current_user=user,
                )
            assert exc_info.value.status_code == 403
            assert "MFA" in exc_info.value.detail
            mock_mfa.assert_called_once_with(db_session, user, None)

    @pytest.mark.asyncio
    async def test_sell_portfolio_with_invalid_mfa_returns_403(
        self, db_session, user_with_live_account
    ):
        """Request with wrong mfa_code → 403."""
        from app.routers.account_router import sell_portfolio_to_base_currency

        user, account = user_with_live_account
        account.is_default = True
        await db_session.flush()

        bg = MagicMock()

        with patch("app.routers.account_router.verify_mfa", new_callable=AsyncMock) as mock_mfa:
            mock_mfa.side_effect = HTTPException(status_code=403, detail="Invalid MFA code")
            with pytest.raises(HTTPException) as exc_info:
                await sell_portfolio_to_base_currency(
                    background_tasks=bg,
                    target_currency="USD",
                    confirm=True,
                    account_id=account.id,
                    mfa_code="000000",
                    db=db_session,
                    current_user=user,
                )
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_sell_portfolio_with_valid_mfa_proceeds(
        self, db_session, user_with_live_account
    ):
        """Request with valid mfa_code → conversion starts."""
        from app.routers.account_router import sell_portfolio_to_base_currency

        user, account = user_with_live_account
        account.is_default = True
        await db_session.flush()

        bg = MagicMock()

        with patch("app.routers.account_router.verify_mfa", new_callable=AsyncMock) as mock_mfa:
            mock_mfa.return_value = None  # MFA passes
            result = await sell_portfolio_to_base_currency(
                background_tasks=bg,
                target_currency="USD",
                confirm=True,
                account_id=account.id,
                mfa_code="123456",
                db=db_session,
                current_user=user,
            )
            mock_mfa.assert_called_once_with(db_session, user, "123456")
            assert "task_id" in result
            assert result["message"] == "Portfolio conversion to USD started"
