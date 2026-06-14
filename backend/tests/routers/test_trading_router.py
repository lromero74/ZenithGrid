"""
Tests for backend/app/routers/trading_router.py

Covers trading endpoints: market sell order execution,
input validation, and error handling.
"""

import pytest
from app.utils.timeutil import utcnow
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Account, User
from app.models.sharing import AccountMembership
from app.routers.trading_router import MarketSellRequest


# =============================================================================
# Pydantic model validation
# =============================================================================


class TestMarketSellRequest:
    """Tests for MarketSellRequest Pydantic model."""

    def test_valid_request(self):
        """Happy path: valid request with all fields."""
        req = MarketSellRequest(product_id="BTC-USD", size=0.001)
        assert req.product_id == "BTC-USD"
        assert req.size == 0.001
        assert req.account_id is None

    def test_request_with_account_id(self):
        """Happy path: request with optional account_id."""
        req = MarketSellRequest(product_id="ETH-USD", size=1.0, account_id=5)
        assert req.account_id == 5

    def test_request_zero_size(self):
        """Edge case: zero size is accepted by Pydantic (validated in endpoint)."""
        req = MarketSellRequest(product_id="BTC-USD", size=0)
        assert req.size == 0


# =============================================================================
# POST /api/trading/market-sell
# =============================================================================


class TestMarketSell:
    """Tests for POST /api/trading/market-sell"""

    @pytest.mark.asyncio
    @patch("app.routers.trading_router.get_exchange_client_for_account")
    async def test_market_sell_success(self, mock_get_client, db_session):
        """Happy path: successful market sell returns order details."""
        from app.routers.trading_router import market_sell

        user = User(
            email="trader@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id,
            name="Trading Account",
            type="cex",
            exchange="coinbase",
            is_default=True,
            is_active=True,
        )
        db_session.add(account)
        await db_session.flush()

        # Mock exchange client
        mock_exchange = MagicMock()
        mock_exchange.create_market_order = AsyncMock(return_value={
            "success_response": {
                "order_id": "order-abc-123",
                "filled_size": "0.001",
                "filled_value": "50.00",
                "average_filled_price": "50000.00",
                "status": "FILLED",
            },
            "error_response": {},
        })
        mock_get_client.return_value = mock_exchange

        request = MarketSellRequest(product_id="BTC-USD", size=0.001)
        result = await market_sell(request=request, current_user=user, db=db_session)

        assert result["success"] is True
        assert result["order_id"] == "order-abc-123"
        assert result["product_id"] == "BTC-USD"
        assert result["side"] == "SELL"
        assert result["size"] == 0.001

    @pytest.mark.asyncio
    async def test_market_sell_no_account(self, db_session):
        """Failure: no trading account returns 404."""
        from fastapi import HTTPException
        from app.routers.trading_router import market_sell

        user = User(
            email="noaccount@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        request = MarketSellRequest(product_id="BTC-USD", size=0.001)
        with pytest.raises(HTTPException) as exc_info:
            await market_sell(request=request, current_user=user, db=db_session)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.routers.trading_router.get_exchange_client_for_account")
    async def test_market_sell_no_exchange_client(self, mock_get_client, db_session):
        """Failure: exchange client creation fails returns 500."""
        from fastapi import HTTPException
        from app.routers.trading_router import market_sell

        user = User(
            email="noclient@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id,
            name="Broken Account",
            type="cex",
            exchange="coinbase",
            is_default=True,
            is_active=True,
        )
        db_session.add(account)
        await db_session.flush()

        mock_get_client.return_value = None

        request = MarketSellRequest(product_id="BTC-USD", size=0.001)
        with pytest.raises(HTTPException) as exc_info:
            await market_sell(request=request, current_user=user, db=db_session)
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    @patch("app.routers.trading_router.get_exchange_client_for_account")
    async def test_market_sell_invalid_product_id(self, mock_get_client, db_session):
        """Failure: invalid product_id format returns 400."""
        from fastapi import HTTPException
        from app.routers.trading_router import market_sell

        user = User(
            email="badproduct@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id,
            name="Account",
            type="cex",
            exchange="coinbase",
            is_default=True,
            is_active=True,
        )
        db_session.add(account)
        await db_session.flush()

        mock_exchange = MagicMock()
        mock_get_client.return_value = mock_exchange

        request = MarketSellRequest(product_id="BTCUSD", size=0.001)
        with pytest.raises(HTTPException) as exc_info:
            await market_sell(request=request, current_user=user, db=db_session)
        assert exc_info.value.status_code == 400
        assert "invalid product_id" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("app.routers.trading_router.get_exchange_client_for_account")
    async def test_market_sell_zero_size(self, mock_get_client, db_session):
        """Failure: zero size returns 400."""
        from fastapi import HTTPException
        from app.routers.trading_router import market_sell

        user = User(
            email="zerosize@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id,
            name="Account",
            type="cex",
            exchange="coinbase",
            is_default=True,
            is_active=True,
        )
        db_session.add(account)
        await db_session.flush()

        mock_exchange = MagicMock()
        mock_get_client.return_value = mock_exchange

        request = MarketSellRequest(product_id="BTC-USD", size=0)
        with pytest.raises(HTTPException) as exc_info:
            await market_sell(request=request, current_user=user, db=db_session)
        assert exc_info.value.status_code == 400
        assert "greater than 0" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("app.routers.trading_router.get_exchange_client_for_account")
    async def test_market_sell_negative_size(self, mock_get_client, db_session):
        """Failure: negative size returns 400."""
        from fastapi import HTTPException
        from app.routers.trading_router import market_sell

        user = User(
            email="negsize@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id,
            name="Account",
            type="cex",
            exchange="coinbase",
            is_default=True,
            is_active=True,
        )
        db_session.add(account)
        await db_session.flush()

        mock_exchange = MagicMock()
        mock_get_client.return_value = mock_exchange

        request = MarketSellRequest(product_id="BTC-USD", size=-0.5)
        with pytest.raises(HTTPException) as exc_info:
            await market_sell(request=request, current_user=user, db=db_session)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("app.routers.trading_router.get_exchange_client_for_account")
    async def test_market_sell_exchange_rejection(self, mock_get_client, db_session):
        """Failure: exchange rejects order (no order_id) returns 400."""
        from fastapi import HTTPException
        from app.routers.trading_router import market_sell

        user = User(
            email="rejected@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id,
            name="Account",
            type="cex",
            exchange="coinbase",
            is_default=True,
            is_active=True,
        )
        db_session.add(account)
        await db_session.flush()

        mock_exchange = MagicMock()
        mock_exchange.create_market_order = AsyncMock(return_value={
            "success_response": {},
            "error_response": {
                "message": "INSUFFICIENT_FUND",
            },
        })
        mock_get_client.return_value = mock_exchange

        request = MarketSellRequest(product_id="BTC-USD", size=0.001)
        with pytest.raises(HTTPException) as exc_info:
            await market_sell(request=request, current_user=user, db=db_session)
        assert exc_info.value.status_code == 400
        assert "INSUFFICIENT_FUND" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.routers.trading_router.get_exchange_client_for_account")
    async def test_market_sell_with_specific_account_id(self, mock_get_client, db_session):
        """Edge case: specifying account_id uses that account."""
        from app.routers.trading_router import market_sell

        user = User(
            email="specificacct@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id,
            name="Specific Account",
            type="cex",
            exchange="coinbase",
            is_default=False,
            is_active=True,
        )
        db_session.add(account)
        await db_session.flush()

        mock_exchange = MagicMock()
        mock_exchange.create_market_order = AsyncMock(return_value={
            "success_response": {
                "order_id": "order-specific-123",
                "status": "FILLED",
            },
            "error_response": {},
        })
        mock_get_client.return_value = mock_exchange

        request = MarketSellRequest(
            product_id="ETH-USD", size=1.0, account_id=account.id
        )
        result = await market_sell(request=request, current_user=user, db=db_session)
        assert result["success"] is True
        assert result["order_id"] == "order-specific-123"

    @pytest.mark.asyncio
    @patch("app.routers.trading_router.get_exchange_client_for_account")
    async def test_market_sell_exchange_exception(self, mock_get_client, db_session):
        """Failure: exchange raises an unexpected exception returns 500."""
        from fastapi import HTTPException
        from app.routers.trading_router import market_sell

        user = User(
            email="exception@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id,
            name="Account",
            type="cex",
            exchange="coinbase",
            is_default=True,
            is_active=True,
        )
        db_session.add(account)
        await db_session.flush()

        mock_exchange = MagicMock()
        mock_exchange.create_market_order = AsyncMock(
            side_effect=RuntimeError("Connection lost")
        )
        mock_get_client.return_value = mock_exchange

        request = MarketSellRequest(product_id="BTC-USD", size=0.001)
        with pytest.raises(HTTPException) as exc_info:
            await market_sell(request=request, current_user=user, db=db_session)
        assert exc_info.value.status_code == 500


# =============================================================================
# Shared-account scoping (manager / shadow / non-member)
# =============================================================================


class TestMarketSellSharedAccount:
    """Manager can market-sell a managed account; view-only / non-member cannot.

    Real-money endpoint — the broker must be built from the *owning* account,
    and the no-account_id convenience path must stay owner-only.
    """

    async def _make_user(self, db_session, email):
        user = User(
            email=email,
            hashed_password="hashed",
            is_active=True,
            created_at=utcnow(),
        )
        db_session.add(user)
        await db_session.flush()
        return user

    async def _make_account(self, db_session, owner, is_default=False):
        account = Account(
            user_id=owner.id,
            name="Owner Account",
            type="cex",
            exchange="coinbase",
            is_default=is_default,
            is_active=True,
        )
        db_session.add(account)
        await db_session.flush()
        return account

    @pytest.mark.asyncio
    @patch("app.routers.trading_router.get_exchange_client_for_account")
    async def test_manager_can_market_sell_managed_account(self, mock_get_client, db_session):
        """Manager + explicit account_id → sell proceeds, broker built from owner's account."""
        from app.routers.trading_router import market_sell

        owner = await self._make_user(db_session, "owner-mgr@example.com")
        manager = await self._make_user(db_session, "manager@example.com")
        account = await self._make_account(db_session, owner, is_default=True)

        db_session.add(AccountMembership(
            account_id=account.id,
            user_id=manager.id,
            role="manager",
            invited_by_user_id=owner.id,
            joined_at=utcnow(),
        ))
        await db_session.flush()

        mock_exchange = MagicMock()
        mock_exchange.create_market_order = AsyncMock(return_value={
            "success_response": {"order_id": "order-mgr-1", "status": "FILLED"},
            "error_response": {},
        })
        mock_get_client.return_value = mock_exchange

        request = MarketSellRequest(product_id="ETH-USD", size=1.0, account_id=account.id)
        result = await market_sell(request=request, current_user=manager, db=db_session)

        assert result["success"] is True
        assert result["order_id"] == "order-mgr-1"
        # Credential isolation: broker built from the OWNING account, not the caller.
        mock_get_client.assert_awaited_once_with(db_session, account.id)

    @pytest.mark.asyncio
    @patch("app.routers.trading_router.get_exchange_client_for_account")
    async def test_shadow_member_cannot_market_sell(self, mock_get_client, db_session):
        """View-only (shadow) member + explicit account_id → 404, no sell."""
        from fastapi import HTTPException
        from app.routers.trading_router import market_sell

        owner = await self._make_user(db_session, "owner-shadow@example.com")
        shadow = await self._make_user(db_session, "shadow@example.com")
        account = await self._make_account(db_session, owner)

        db_session.add(AccountMembership(
            account_id=account.id,
            user_id=shadow.id,
            role="shadow",
            invited_by_user_id=owner.id,
            joined_at=utcnow(),
        ))
        await db_session.flush()

        request = MarketSellRequest(product_id="ETH-USD", size=1.0, account_id=account.id)
        with pytest.raises(HTTPException) as exc_info:
            await market_sell(request=request, current_user=shadow, db=db_session)
        assert exc_info.value.status_code == 404
        mock_get_client.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.routers.trading_router.get_exchange_client_for_account")
    async def test_non_member_cannot_market_sell(self, mock_get_client, db_session):
        """Unrelated user + explicit account_id they don't own/manage → 404, no sell."""
        from fastapi import HTTPException
        from app.routers.trading_router import market_sell

        owner = await self._make_user(db_session, "owner-iso@example.com")
        stranger = await self._make_user(db_session, "stranger@example.com")
        account = await self._make_account(db_session, owner)

        request = MarketSellRequest(product_id="ETH-USD", size=1.0, account_id=account.id)
        with pytest.raises(HTTPException) as exc_info:
            await market_sell(request=request, current_user=stranger, db=db_session)
        assert exc_info.value.status_code == 404
        mock_get_client.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.routers.trading_router.get_exchange_client_for_account")
    async def test_manager_no_account_id_does_not_sell_owner_default(self, mock_get_client, db_session):
        """Manager + no account_id → owner-only default path → 404 (no silent sell of owner's default)."""
        from fastapi import HTTPException
        from app.routers.trading_router import market_sell

        owner = await self._make_user(db_session, "owner-def@example.com")
        manager = await self._make_user(db_session, "manager-def@example.com")
        account = await self._make_account(db_session, owner, is_default=True)

        db_session.add(AccountMembership(
            account_id=account.id,
            user_id=manager.id,
            role="manager",
            invited_by_user_id=owner.id,
            joined_at=utcnow(),
        ))
        await db_session.flush()

        request = MarketSellRequest(product_id="ETH-USD", size=1.0)  # no account_id
        with pytest.raises(HTTPException) as exc_info:
            await market_sell(request=request, current_user=manager, db=db_session)
        assert exc_info.value.status_code == 404
        mock_get_client.assert_not_called()
