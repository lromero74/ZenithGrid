"""
Tests for backend/app/routers/paper_trading_router.py

Covers paper trading endpoints: get balance, deposit, withdraw, and reset.
"""

import json
import pytest
from datetime import datetime

from app.models import Account, Position, User
from app.routers.paper_trading_router import DEFAULT_PAPER_BALANCES


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def paper_user(db_session):
    """Create a user with a paper trading account."""
    user = User(
        email="paper@example.com",
        hashed_password="hashed",
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.flush()

    account = Account(
        user_id=user.id,
        name="Paper Trading",
        type="cex",
        exchange="coinbase",
        is_default=True,
        is_active=True,
        is_paper_trading=True,
        paper_balances=json.dumps({
            "BTC": 1.0,
            "ETH": 10.0,
            "USD": 100000.0,
            "USDC": 0.0,
            "USDT": 0.0,
        }),
    )
    db_session.add(account)
    await db_session.flush()

    return user, account


@pytest.fixture
async def paper_user_no_account(db_session):
    """Create a user without any paper trading account."""
    user = User(
        email="nopaper@example.com",
        hashed_password="hashed",
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.flush()
    return user


# =============================================================================
# GET /api/paper-trading/balance
# =============================================================================


class TestGetPaperBalance:
    """Tests for GET /api/paper-trading/balance"""

    @pytest.mark.asyncio
    async def test_returns_balances(self, db_session, paper_user):
        """Happy path: returns paper trading balances."""
        from app.routers.paper_trading_router import get_paper_balance

        user, account = paper_user
        result = await get_paper_balance(current_user=user, db=db_session)

        assert result["account_id"] == account.id
        assert result["is_paper_trading"] is True
        assert result["balances"]["BTC"] == 1.0
        assert result["balances"]["USD"] == 100000.0

    @pytest.mark.asyncio
    async def test_no_paper_account_returns_404(self, db_session, paper_user_no_account):
        """Failure: user without paper account gets 404."""
        from fastapi import HTTPException
        from app.routers.paper_trading_router import get_paper_balance

        with pytest.raises(HTTPException) as exc_info:
            await get_paper_balance(current_user=paper_user_no_account, db=db_session)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_balances_get_defaults(self, db_session):
        """Edge case: account with no paper_balances JSON gets default balances."""
        from app.routers.paper_trading_router import get_paper_balance

        user = User(
            email="emptybalances@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id,
            name="Empty Paper",
            type="cex",
            is_active=True,
            is_paper_trading=True,
            paper_balances=None,
        )
        db_session.add(account)
        await db_session.flush()

        result = await get_paper_balance(current_user=user, db=db_session)
        assert result["balances"]["BTC"] == DEFAULT_PAPER_BALANCES["BTC"]
        assert result["balances"]["USD"] == DEFAULT_PAPER_BALANCES["USD"]


# =============================================================================
# POST /api/paper-trading/deposit
# =============================================================================


class TestDepositToPaperAccount:
    """Tests for POST /api/paper-trading/deposit"""

    @pytest.mark.asyncio
    async def test_deposit_success(self, db_session, paper_user):
        """Happy path: deposit adds to the currency balance."""
        from app.routers.paper_trading_router import deposit_to_paper_account

        user, _ = paper_user
        result = await deposit_to_paper_account(
            currency="BTC", amount=0.5, current_user=user, db=db_session
        )

        assert result["success"] is True
        assert result["currency"] == "BTC"
        assert result["deposited"] == 0.5
        assert result["new_balance"] == 1.5  # 1.0 + 0.5

    @pytest.mark.asyncio
    async def test_deposit_zero_amount_fails(self, db_session, paper_user):
        """Failure: zero deposit returns 400."""
        from fastapi import HTTPException
        from app.routers.paper_trading_router import deposit_to_paper_account

        user, _ = paper_user
        with pytest.raises(HTTPException) as exc_info:
            await deposit_to_paper_account(
                currency="USD", amount=0, current_user=user, db=db_session
            )
        assert exc_info.value.status_code == 400
        assert "positive" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_deposit_negative_amount_fails(self, db_session, paper_user):
        """Failure: negative deposit returns 400."""
        from fastapi import HTTPException
        from app.routers.paper_trading_router import deposit_to_paper_account

        user, _ = paper_user
        with pytest.raises(HTTPException) as exc_info:
            await deposit_to_paper_account(
                currency="ETH", amount=-5.0, current_user=user, db=db_session
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_deposit_unsupported_currency_fails(self, db_session, paper_user):
        """Failure: unsupported currency returns 400."""
        from fastapi import HTTPException
        from app.routers.paper_trading_router import deposit_to_paper_account

        user, _ = paper_user
        with pytest.raises(HTTPException) as exc_info:
            await deposit_to_paper_account(
                currency="DOGE", amount=100.0, current_user=user, db=db_session
            )
        assert exc_info.value.status_code == 400
        assert "unsupported" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_deposit_lowercase_currency_is_uppercased(self, db_session, paper_user):
        """Edge case: lowercase currency is converted to uppercase."""
        from app.routers.paper_trading_router import deposit_to_paper_account

        user, _ = paper_user
        result = await deposit_to_paper_account(
            currency="eth", amount=1.0, current_user=user, db=db_session
        )
        assert result["currency"] == "ETH"
        assert result["new_balance"] == 11.0  # 10.0 + 1.0

    @pytest.mark.asyncio
    async def test_deposit_no_paper_account_returns_404(self, db_session, paper_user_no_account):
        """Failure: user without paper account gets 404."""
        from fastapi import HTTPException
        from app.routers.paper_trading_router import deposit_to_paper_account

        with pytest.raises(HTTPException) as exc_info:
            await deposit_to_paper_account(
                currency="BTC", amount=1.0, current_user=paper_user_no_account, db=db_session
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# POST /api/paper-trading/withdraw
# =============================================================================


class TestWithdrawFromPaperAccount:
    """Tests for POST /api/paper-trading/withdraw"""

    @pytest.mark.asyncio
    async def test_withdraw_success(self, db_session, paper_user):
        """Happy path: withdrawal reduces the balance."""
        from app.routers.paper_trading_router import withdraw_from_paper_account

        user, _ = paper_user
        result = await withdraw_from_paper_account(
            currency="USD", amount=50000.0, current_user=user, db=db_session
        )

        assert result["success"] is True
        assert result["withdrawn"] == 50000.0
        assert result["new_balance"] == 50000.0

    @pytest.mark.asyncio
    async def test_withdraw_insufficient_funds(self, db_session, paper_user):
        """Failure: withdrawing more than available returns 400."""
        from fastapi import HTTPException
        from app.routers.paper_trading_router import withdraw_from_paper_account

        user, _ = paper_user
        with pytest.raises(HTTPException) as exc_info:
            await withdraw_from_paper_account(
                currency="BTC", amount=999.0, current_user=user, db=db_session
            )
        assert exc_info.value.status_code == 400
        assert "insufficient" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_withdraw_zero_amount_fails(self, db_session, paper_user):
        """Failure: zero withdrawal returns 400."""
        from fastapi import HTTPException
        from app.routers.paper_trading_router import withdraw_from_paper_account

        user, _ = paper_user
        with pytest.raises(HTTPException) as exc_info:
            await withdraw_from_paper_account(
                currency="USD", amount=0, current_user=user, db=db_session
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_withdraw_unsupported_currency_fails(self, db_session, paper_user):
        """Failure: unsupported currency returns 400."""
        from fastapi import HTTPException
        from app.routers.paper_trading_router import withdraw_from_paper_account

        user, _ = paper_user
        with pytest.raises(HTTPException) as exc_info:
            await withdraw_from_paper_account(
                currency="XRP", amount=10.0, current_user=user, db=db_session
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_withdraw_exact_balance(self, db_session, paper_user):
        """Edge case: withdrawing the exact balance leaves 0."""
        from app.routers.paper_trading_router import withdraw_from_paper_account

        user, _ = paper_user
        result = await withdraw_from_paper_account(
            currency="BTC", amount=1.0, current_user=user, db=db_session
        )
        assert result["new_balance"] == 0.0


# =============================================================================
# POST /api/paper-trading/reset
# =============================================================================


class TestResetPaperAccount:
    """Tests for POST /api/paper-trading/reset"""

    @pytest.mark.asyncio
    async def test_reset_success(self, db_session, paper_user):
        """Happy path: balances reset to defaults."""
        from app.routers.paper_trading_router import reset_paper_account

        user, _ = paper_user
        result = await reset_paper_account(current_user=user, db=db_session)

        assert result["success"] is True
        assert result["balances"]["BTC"] == DEFAULT_PAPER_BALANCES["BTC"]
        assert result["balances"]["USD"] == DEFAULT_PAPER_BALANCES["USD"]
        assert result["balances"]["ETH"] == DEFAULT_PAPER_BALANCES["ETH"]

    @pytest.mark.asyncio
    async def test_reset_deletes_positions(self, db_session, paper_user):
        """Happy path: reset deletes paper trading positions."""
        from app.routers.paper_trading_router import reset_paper_account

        user, account = paper_user

        # Create a position
        position = Position(
            account_id=account.id,
            product_id="BTC-USD",
            status="open",
            total_base_acquired=0.001,
            total_quote_spent=50.0,
            opened_at=datetime.utcnow(),
        )
        db_session.add(position)
        await db_session.flush()

        result = await reset_paper_account(current_user=user, db=db_session)
        assert result["deleted"]["positions"] == 1

    @pytest.mark.asyncio
    async def test_reset_no_paper_account_returns_404(self, db_session, paper_user_no_account):
        """Failure: user without paper account gets 404."""
        from fastapi import HTTPException
        from app.routers.paper_trading_router import reset_paper_account

        with pytest.raises(HTTPException) as exc_info:
            await reset_paper_account(current_user=paper_user_no_account, db=db_session)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_reset_with_no_positions(self, db_session, paper_user):
        """Edge case: reset with no positions reports 0 deleted."""
        from app.routers.paper_trading_router import reset_paper_account

        user, _ = paper_user
        result = await reset_paper_account(current_user=user, db=db_session)
        assert result["deleted"]["positions"] == 0
        assert result["deleted"]["pending_orders"] == 0
