"""
Tests for backend/app/position_routers/perps_router.py

Covers endpoints:
- GET /api/perps/products
- GET /api/perps/portfolio
- GET /api/perps/positions
- POST /api/perps/positions/{position_id}/modify-tp-sl
- POST /api/perps/positions/{position_id}/close

Also covers helper functions:
- _get_coinbase_client
- _get_portfolio_uuid
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Account, Position, User


# =============================================================================
# Helpers
# =============================================================================


async def _create_user_with_account(db_session, email="perps@example.com", **account_overrides):
    """Create a test user with an active CEX account."""
    user = User(
        email=email,
        hashed_password="hashed",
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.flush()

    defaults = dict(
        user_id=user.id,
        name="Test Account",
        type="cex",
        exchange="coinbase",
        is_active=True,
    )
    defaults.update(account_overrides)
    account = Account(**defaults)
    db_session.add(account)
    await db_session.flush()

    return user, account


async def _create_perps_position(db_session, account, bot=None, **overrides):
    """Create a test perpetual futures position."""
    defaults = dict(
        bot_id=bot.id if bot else None,
        account_id=account.id,
        product_id="BTC-PERP-INTX",
        product_type="future",
        status="open",
        direction="long",
        opened_at=datetime.utcnow(),
        initial_quote_balance=10000.0,
        max_quote_allowed=5000.0,
        total_quote_spent=1000.0,
        total_base_acquired=0.01,
        average_buy_price=100000.0,
        entry_price=100000.0,
        leverage=5,
        perps_margin_type="CROSS",
    )
    defaults.update(overrides)
    position = Position(**defaults)
    db_session.add(position)
    await db_session.flush()
    return position


# =============================================================================
# Helper: _get_coinbase_client
# =============================================================================


class TestGetCoinbaseClient:
    """Tests for _get_coinbase_client helper."""

    def test_extracts_client_from_underscore_client(self):
        """Happy path: extracts _client attribute."""
        from app.position_routers.perps_router import _get_coinbase_client

        inner = MagicMock()
        exchange = MagicMock()
        exchange._client = inner

        result = _get_coinbase_client(exchange)
        assert result is inner

    def test_extracts_client_from_client_attribute(self):
        """Edge case: extracts client attribute when _client is absent."""
        from app.position_routers.perps_router import _get_coinbase_client

        inner = MagicMock()
        exchange = MagicMock(spec=[])  # No automatic attributes
        exchange.client = inner

        result = _get_coinbase_client(exchange)
        assert result is inner

    def test_raises_503_when_no_client(self):
        """Failure: raises 503 when exchange has no client attribute."""
        from app.position_routers.perps_router import _get_coinbase_client
        from fastapi import HTTPException

        exchange = MagicMock(spec=[])  # No _client or client

        with pytest.raises(HTTPException) as exc_info:
            _get_coinbase_client(exchange)
        assert exc_info.value.status_code == 503


# =============================================================================
# Helper: _get_portfolio_uuid
# =============================================================================


class TestGetPortfolioUuid:
    """Tests for _get_portfolio_uuid helper."""

    @pytest.mark.asyncio
    async def test_returns_portfolio_uuid(self, db_session):
        """Happy path: returns perps_portfolio_uuid from user's active account."""
        from app.position_routers.perps_router import _get_portfolio_uuid

        user, account = await _create_user_with_account(
            db_session, email="uuid_ok@example.com",
            perps_portfolio_uuid="portfolio-uuid-abc",
        )

        result = await _get_portfolio_uuid(db_session, user)
        assert result == "portfolio-uuid-abc"

    @pytest.mark.asyncio
    async def test_raises_404_when_no_portfolio(self, db_session):
        """Failure: user has no perps portfolio configured."""
        from app.position_routers.perps_router import _get_portfolio_uuid
        from fastapi import HTTPException

        user, account = await _create_user_with_account(
            db_session, email="uuid_no@example.com",
            perps_portfolio_uuid=None,
        )

        with pytest.raises(HTTPException) as exc_info:
            await _get_portfolio_uuid(db_session, user)
        assert exc_info.value.status_code == 404
        assert "No perpetuals portfolio" in exc_info.value.detail


# =============================================================================
# GET /api/perps/products
# =============================================================================


class TestListPerpsProducts:
    """Tests for list_perps_products endpoint."""

    @pytest.mark.asyncio
    async def test_list_products_succeeds(self, db_session):
        """Happy path: returns formatted list of perps products."""
        from app.position_routers.perps_router import list_perps_products

        mock_client = AsyncMock()
        mock_client.list_perps_products = AsyncMock(return_value=[
            {
                "product_id": "BTC-PERP-INTX",
                "display_name": "BTC Perpetual",
                "base_currency_id": "BTC",
                "quote_currency_id": "USDC",
                "status": "ONLINE",
                "price": "100000.00",
                "volume_24h": "500000000",
            },
        ])

        exchange = MagicMock()
        exchange._client = mock_client

        user = MagicMock()
        user.id = 1

        result = await list_perps_products(exchange=exchange, current_user=user)

        assert result["count"] == 1
        assert result["products"][0]["product_id"] == "BTC-PERP-INTX"
        assert result["products"][0]["base_currency"] == "BTC"

    @pytest.mark.asyncio
    async def test_list_products_empty(self, db_session):
        """Edge case: no products available."""
        from app.position_routers.perps_router import list_perps_products

        mock_client = AsyncMock()
        mock_client.list_perps_products = AsyncMock(return_value=[])

        exchange = MagicMock()
        exchange._client = mock_client

        user = MagicMock()
        user.id = 1

        result = await list_perps_products(exchange=exchange, current_user=user)

        assert result["count"] == 0
        assert result["products"] == []

    @pytest.mark.asyncio
    async def test_list_products_exchange_error(self, db_session):
        """Failure: exchange raises an exception."""
        from app.position_routers.perps_router import list_perps_products
        from fastapi import HTTPException

        mock_client = AsyncMock()
        mock_client.list_perps_products = AsyncMock(side_effect=Exception("Connection error"))

        exchange = MagicMock()
        exchange._client = mock_client

        user = MagicMock()
        user.id = 1

        with pytest.raises(HTTPException) as exc_info:
            await list_perps_products(exchange=exchange, current_user=user)
        assert exc_info.value.status_code == 500


# =============================================================================
# GET /api/perps/portfolio
# =============================================================================


class TestGetPerpsPortfolio:
    """Tests for get_perps_portfolio endpoint."""

    @pytest.mark.asyncio
    async def test_get_portfolio_succeeds(self, db_session):
        """Happy path: returns portfolio summary and balances."""
        from app.position_routers.perps_router import get_perps_portfolio

        user, account = await _create_user_with_account(
            db_session, email="port_ok@example.com",
            perps_portfolio_uuid="port-uuid-123",
        )

        mock_client = AsyncMock()
        mock_client.get_perps_portfolio_summary = AsyncMock(return_value={"total_margin": "5000"})
        mock_client.get_perps_balances = AsyncMock(return_value={"USDC": "10000"})

        exchange = MagicMock()
        exchange._client = mock_client

        result = await get_perps_portfolio(
            db=db_session,
            exchange=exchange,
            current_user=user,
        )

        assert result["portfolio_uuid"] == "port-uuid-123"
        assert result["summary"]["total_margin"] == "5000"
        assert result["balances"]["USDC"] == "10000"

    @pytest.mark.asyncio
    async def test_get_portfolio_no_uuid_returns_404(self, db_session):
        """Failure: user without perps portfolio configured gets 404."""
        from app.position_routers.perps_router import get_perps_portfolio
        from fastapi import HTTPException

        user, account = await _create_user_with_account(
            db_session, email="port_no@example.com",
            perps_portfolio_uuid=None,
        )

        exchange = MagicMock()
        exchange._client = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_perps_portfolio(
                db=db_session,
                exchange=exchange,
                current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_portfolio_exchange_error(self, db_session):
        """Failure: exchange client throws during summary fetch."""
        from app.position_routers.perps_router import get_perps_portfolio
        from fastapi import HTTPException

        user, account = await _create_user_with_account(
            db_session, email="port_err@example.com",
            perps_portfolio_uuid="port-uuid-456",
        )

        mock_client = AsyncMock()
        mock_client.get_perps_portfolio_summary = AsyncMock(side_effect=Exception("API down"))

        exchange = MagicMock()
        exchange._client = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await get_perps_portfolio(
                db=db_session,
                exchange=exchange,
                current_user=user,
            )
        assert exc_info.value.status_code == 500


# =============================================================================
# GET /api/perps/positions
# =============================================================================


class TestListPerpsPositions:
    """Tests for list_perps_positions endpoint."""

    @pytest.mark.asyncio
    async def test_list_positions_succeeds(self, db_session):
        """Happy path: returns open perps positions for the user."""
        from app.position_routers.perps_router import list_perps_positions

        user, account = await _create_user_with_account(db_session, email="lp_ok@example.com")
        await _create_perps_position(
            db_session, account,
            direction="long",
            leverage=5,
            tp_price=110000.0,
            sl_price=90000.0,
        )

        exchange = MagicMock()

        result = await list_perps_positions(
            db=db_session,
            exchange=exchange,
            current_user=user,
        )

        assert result["count"] == 1
        assert result["positions"][0]["product_id"] == "BTC-PERP-INTX"
        assert result["positions"][0]["direction"] == "long"
        assert result["positions"][0]["leverage"] == 5

    @pytest.mark.asyncio
    async def test_list_positions_excludes_spot(self, db_session):
        """Edge case: spot positions are not returned."""
        from app.position_routers.perps_router import list_perps_positions

        user, account = await _create_user_with_account(db_session, email="lp_spot@example.com")
        # Create a spot position (should be excluded)
        spot_pos = Position(
            account_id=account.id,
            product_id="ETH-BTC",
            product_type="spot",
            status="open",
            opened_at=datetime.utcnow(),
            initial_quote_balance=1.0,
            max_quote_allowed=0.25,
            total_quote_spent=0.01,
            total_base_acquired=0.5,
            average_buy_price=0.02,
        )
        db_session.add(spot_pos)
        await db_session.flush()

        exchange = MagicMock()

        result = await list_perps_positions(
            db=db_session,
            exchange=exchange,
            current_user=user,
        )

        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_list_positions_excludes_other_user(self, db_session):
        """Security: does not return positions from other users."""
        from app.position_routers.perps_router import list_perps_positions

        user1, account1 = await _create_user_with_account(db_session, email="lp_user1@example.com")
        user2, account2 = await _create_user_with_account(db_session, email="lp_user2@example.com")
        await _create_perps_position(db_session, account1)  # user1's position

        exchange = MagicMock()

        result = await list_perps_positions(
            db=db_session,
            exchange=exchange,
            current_user=user2,
        )

        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_list_positions_short_direction(self, db_session):
        """Edge case: short position uses short_total_sold_base for current_size."""
        from app.position_routers.perps_router import list_perps_positions

        user, account = await _create_user_with_account(db_session, email="lp_short@example.com")
        await _create_perps_position(
            db_session, account,
            direction="short",
            short_total_sold_base=0.05,
            short_total_sold_quote=5000.0,
        )

        exchange = MagicMock()

        result = await list_perps_positions(
            db=db_session,
            exchange=exchange,
            current_user=user,
        )

        assert result["count"] == 1
        assert result["positions"][0]["current_size"] == 0.05


# =============================================================================
# POST /api/perps/positions/{position_id}/modify-tp-sl
# =============================================================================


class TestModifyTpSl:
    """Tests for modify_tp_sl endpoint."""

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.create_stop_limit_order", new_callable=AsyncMock)
    async def test_modify_tp_sl_succeeds(self, mock_stop_limit, db_session):
        """Happy path: modifying TP/SL updates position and places new orders."""
        from app.position_routers.perps_router import modify_tp_sl, ModifyTpSlRequest

        mock_stop_limit.return_value = {"success_response": {"order_id": "tp-order-new"}}

        user, account = await _create_user_with_account(db_session, email="tpsl_ok@example.com")
        pos = await _create_perps_position(
            db_session, account,
            tp_price=110000.0,
            sl_price=90000.0,
            tp_order_id="old-tp",
            sl_order_id="old-sl",
        )

        mock_client = AsyncMock()
        mock_client.cancel_order = AsyncMock(return_value=True)
        mock_client._request = AsyncMock()

        exchange = MagicMock()
        exchange._client = mock_client

        request = ModifyTpSlRequest(tp_price=115000.0, sl_price=85000.0)

        result = await modify_tp_sl(
            position_id=pos.id,
            request=request,
            db=db_session,
            exchange=exchange,
            current_user=user,
        )

        assert result["success"] is True
        assert result["tp_price"] == 115000.0
        assert result["sl_price"] == 85000.0
        # Old orders should have been cancelled
        assert mock_client.cancel_order.await_count == 2

    @pytest.mark.asyncio
    async def test_modify_tp_sl_position_not_found(self, db_session):
        """Failure: modifying TP/SL on non-existent position returns 404."""
        from app.position_routers.perps_router import modify_tp_sl, ModifyTpSlRequest
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="tpsl_404@example.com")

        exchange = MagicMock()
        exchange._client = AsyncMock()

        request = ModifyTpSlRequest(tp_price=110000.0)

        with pytest.raises(HTTPException) as exc_info:
            await modify_tp_sl(
                position_id=99999,
                request=request,
                db=db_session,
                exchange=exchange,
                current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.create_stop_limit_order", new_callable=AsyncMock)
    async def test_modify_tp_only(self, mock_stop_limit, db_session):
        """Edge case: modifying only TP preserves existing SL."""
        from app.position_routers.perps_router import modify_tp_sl, ModifyTpSlRequest

        mock_stop_limit.return_value = {"success_response": {"order_id": "new-tp-order"}}

        user, account = await _create_user_with_account(db_session, email="tpsl_tp@example.com")
        pos = await _create_perps_position(
            db_session, account,
            tp_price=110000.0,
            sl_price=90000.0,
            tp_order_id=None,
            sl_order_id=None,
        )

        mock_client = AsyncMock()
        mock_client._request = AsyncMock()

        exchange = MagicMock()
        exchange._client = mock_client

        request = ModifyTpSlRequest(tp_price=120000.0)

        result = await modify_tp_sl(
            position_id=pos.id,
            request=request,
            db=db_session,
            exchange=exchange,
            current_user=user,
        )

        assert result["tp_price"] == 120000.0
        # SL stays at the old value since request.sl_price was None
        assert result["sl_price"] == 90000.0


# =============================================================================
# POST /api/perps/positions/{position_id}/close
# =============================================================================


class TestClosePerpsPosition:
    """Tests for close_perps_position endpoint."""

    @pytest.mark.asyncio
    @patch("app.trading_engine.perps_executor.execute_perps_close", new_callable=AsyncMock)
    async def test_close_succeeds(self, mock_execute_close, db_session):
        """Happy path: closing a perps position returns profit info."""
        from app.position_routers.perps_router import close_perps_position, ClosePositionRequest

        mock_execute_close.return_value = (True, 500.0, 5.0)

        user, account = await _create_user_with_account(db_session, email="close_ok@example.com")
        pos = await _create_perps_position(db_session, account)

        mock_client = AsyncMock()
        mock_client.get_current_price = AsyncMock(return_value=105000.0)

        exchange = MagicMock()
        exchange._client = mock_client

        request = ClosePositionRequest(reason="manual")

        result = await close_perps_position(
            position_id=pos.id,
            request=request,
            db=db_session,
            exchange=exchange,
            current_user=user,
        )

        assert result["success"] is True
        assert result["profit_usdc"] == 500.0
        assert result["profit_pct"] == 5.0

    @pytest.mark.asyncio
    async def test_close_position_not_found(self, db_session):
        """Failure: closing non-existent position returns 404."""
        from app.position_routers.perps_router import close_perps_position, ClosePositionRequest
        from fastapi import HTTPException

        user, account = await _create_user_with_account(db_session, email="close_404@example.com")

        exchange = MagicMock()
        exchange._client = AsyncMock()

        request = ClosePositionRequest(reason="manual")

        with pytest.raises(HTTPException) as exc_info:
            await close_perps_position(
                position_id=99999,
                request=request,
                db=db_session,
                exchange=exchange,
                current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.trading_engine.perps_executor.execute_perps_close", new_callable=AsyncMock)
    async def test_close_execution_fails_returns_500(self, mock_execute_close, db_session):
        """Failure: execute_perps_close returns failure."""
        from app.position_routers.perps_router import close_perps_position, ClosePositionRequest
        from fastapi import HTTPException

        mock_execute_close.return_value = (False, 0.0, 0.0)

        user, account = await _create_user_with_account(db_session, email="close_fail@example.com")
        pos = await _create_perps_position(db_session, account)

        mock_client = AsyncMock()
        mock_client.get_current_price = AsyncMock(return_value=100000.0)

        exchange = MagicMock()
        exchange._client = mock_client

        request = ClosePositionRequest(reason="manual")

        with pytest.raises(HTTPException) as exc_info:
            await close_perps_position(
                position_id=pos.id,
                request=request,
                db=db_session,
                exchange=exchange,
                current_user=user,
            )
        assert exc_info.value.status_code == 500
        assert "Failed to close" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.trading_engine.perps_executor.execute_perps_close", new_callable=AsyncMock)
    async def test_close_price_fetch_fallback(self, mock_execute_close, db_session):
        """Edge case: when price fetch fails, falls back to entry_price."""
        from app.position_routers.perps_router import close_perps_position, ClosePositionRequest

        mock_execute_close.return_value = (True, 100.0, 1.0)

        user, account = await _create_user_with_account(db_session, email="close_fb@example.com")
        pos = await _create_perps_position(db_session, account, entry_price=99000.0)

        mock_client = AsyncMock()
        mock_client.get_current_price = AsyncMock(side_effect=Exception("Price API down"))

        exchange = MagicMock()
        exchange._client = mock_client

        request = ClosePositionRequest(reason="manual")

        result = await close_perps_position(
            position_id=pos.id,
            request=request,
            db=db_session,
            exchange=exchange,
            current_user=user,
        )

        # Should succeed using fallback price
        assert result["success"] is True
        # Verify execute_perps_close was called with the fallback price
        call_kwargs = mock_execute_close.call_args
        assert call_kwargs.kwargs["current_price"] == 99000.0


# =============================================================================
# Additional edge-case and security tests
# =============================================================================


class TestModifyTpSlAdditional:
    """Additional tests for modify_tp_sl endpoint."""

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.create_stop_limit_order", new_callable=AsyncMock)
    async def test_modify_sl_only(self, mock_stop_limit, db_session):
        """Edge case: modifying only SL preserves existing TP."""
        from app.position_routers.perps_router import modify_tp_sl, ModifyTpSlRequest

        mock_stop_limit.return_value = {"success_response": {"order_id": "new-sl-order"}}

        user, account = await _create_user_with_account(
            db_session, email="tpsl_sl@example.com",
        )
        pos = await _create_perps_position(
            db_session, account,
            tp_price=110000.0,
            sl_price=90000.0,
            tp_order_id=None,
            sl_order_id=None,
        )

        mock_client = AsyncMock()
        mock_client._request = AsyncMock()

        exchange = MagicMock()
        exchange._client = mock_client

        request = ModifyTpSlRequest(sl_price=85000.0)

        result = await modify_tp_sl(
            position_id=pos.id,
            request=request,
            db=db_session,
            exchange=exchange,
            current_user=user,
        )

        # TP should stay at the old value
        assert result["tp_price"] == 110000.0
        assert result["sl_price"] == 85000.0

    @pytest.mark.asyncio
    async def test_modify_tp_sl_other_users_position_returns_404(self, db_session):
        """Security: cannot modify TP/SL on another user's position."""
        from app.position_routers.perps_router import modify_tp_sl, ModifyTpSlRequest
        from fastapi import HTTPException

        user1, account1 = await _create_user_with_account(
            db_session, email="tpsl_sec1@example.com",
        )
        user2, account2 = await _create_user_with_account(
            db_session, email="tpsl_sec2@example.com",
        )
        pos = await _create_perps_position(db_session, account1)

        exchange = MagicMock()
        exchange._client = AsyncMock()

        request = ModifyTpSlRequest(tp_price=999999.0)

        with pytest.raises(HTTPException) as exc_info:
            await modify_tp_sl(
                position_id=pos.id,
                request=request,
                db=db_session,
                exchange=exchange,
                current_user=user2,  # Wrong user
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.create_stop_limit_order", new_callable=AsyncMock)
    async def test_modify_tp_sl_cancel_failure_continues(self, mock_stop_limit, db_session):
        """Edge case: cancel of old orders fails but new orders still placed."""
        from app.position_routers.perps_router import modify_tp_sl, ModifyTpSlRequest

        mock_stop_limit.return_value = {"success_response": {"order_id": "tp-new"}}

        user, account = await _create_user_with_account(
            db_session, email="tpsl_cancel_fail@example.com",
        )
        pos = await _create_perps_position(
            db_session, account,
            tp_price=110000.0,
            tp_order_id="old-tp-id",
            sl_order_id=None,
        )

        mock_client = AsyncMock()
        mock_client.cancel_order = AsyncMock(side_effect=Exception("Cancel failed"))
        mock_client._request = AsyncMock()

        exchange = MagicMock()
        exchange._client = mock_client

        request = ModifyTpSlRequest(tp_price=115000.0)

        # Should not raise despite cancel failure
        result = await modify_tp_sl(
            position_id=pos.id,
            request=request,
            db=db_session,
            exchange=exchange,
            current_user=user,
        )

        assert result["success"] is True
        assert result["tp_price"] == 115000.0

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.create_stop_limit_order", new_callable=AsyncMock)
    async def test_modify_tp_sl_short_position(self, mock_stop_limit, db_session):
        """Edge case: short position uses SELL size from short_total_sold_base."""
        from app.position_routers.perps_router import modify_tp_sl, ModifyTpSlRequest

        mock_stop_limit.return_value = {"success_response": {"order_id": "short-tp"}}

        user, account = await _create_user_with_account(
            db_session, email="tpsl_short@example.com",
        )
        pos = await _create_perps_position(
            db_session, account,
            direction="short",
            short_total_sold_base=0.05,
            tp_price=None,
            sl_price=None,
        )

        mock_client = AsyncMock()
        mock_client._request = AsyncMock()

        exchange = MagicMock()
        exchange._client = mock_client

        request = ModifyTpSlRequest(tp_price=80000.0)

        result = await modify_tp_sl(
            position_id=pos.id,
            request=request,
            db=db_session,
            exchange=exchange,
            current_user=user,
        )

        assert result["success"] is True
        assert result["tp_price"] == 80000.0


class TestClosePerpsPositionAdditional:
    """Additional tests for close_perps_position endpoint."""

    @pytest.mark.asyncio
    async def test_close_other_users_position_returns_404(self, db_session):
        """Security: cannot close another user's position."""
        from app.position_routers.perps_router import close_perps_position, ClosePositionRequest
        from fastapi import HTTPException

        user1, account1 = await _create_user_with_account(
            db_session, email="close_sec1@example.com",
        )
        user2, account2 = await _create_user_with_account(
            db_session, email="close_sec2@example.com",
        )
        pos = await _create_perps_position(db_session, account1)

        exchange = MagicMock()
        exchange._client = AsyncMock()

        request = ClosePositionRequest(reason="manual")

        with pytest.raises(HTTPException) as exc_info:
            await close_perps_position(
                position_id=pos.id,
                request=request,
                db=db_session,
                exchange=exchange,
                current_user=user2,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_close_closed_position_returns_404(self, db_session):
        """Edge case: attempting to close already-closed position returns 404."""
        from app.position_routers.perps_router import close_perps_position, ClosePositionRequest
        from fastapi import HTTPException

        user, account = await _create_user_with_account(
            db_session, email="close_closed@example.com",
        )
        pos = await _create_perps_position(
            db_session, account,
            status="closed",
        )

        exchange = MagicMock()
        exchange._client = AsyncMock()

        request = ClosePositionRequest(reason="manual")

        with pytest.raises(HTTPException) as exc_info:
            await close_perps_position(
                position_id=pos.id,
                request=request,
                db=db_session,
                exchange=exchange,
                current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.trading_engine.perps_executor.execute_perps_close", new_callable=AsyncMock)
    async def test_close_with_custom_reason(self, mock_execute_close, db_session):
        """Happy path: custom reason string is passed to executor."""
        from app.position_routers.perps_router import close_perps_position, ClosePositionRequest

        mock_execute_close.return_value = (True, 200.0, 2.0)

        user, account = await _create_user_with_account(
            db_session, email="close_reason@example.com",
        )
        pos = await _create_perps_position(db_session, account)

        mock_client = AsyncMock()
        mock_client.get_current_price = AsyncMock(return_value=102000.0)

        exchange = MagicMock()
        exchange._client = mock_client

        request = ClosePositionRequest(reason="stop_loss_triggered")

        result = await close_perps_position(
            position_id=pos.id,
            request=request,
            db=db_session,
            exchange=exchange,
            current_user=user,
        )

        assert result["success"] is True
        call_kwargs = mock_execute_close.call_args.kwargs
        assert call_kwargs["reason"] == "stop_loss_triggered"


class TestListPerpsPositionsAdditional:
    """Additional tests for list_perps_positions endpoint."""

    @pytest.mark.asyncio
    async def test_multiple_positions_returned(self, db_session):
        """Happy path: multiple open perps positions returned for the user."""
        from app.position_routers.perps_router import list_perps_positions

        user, account = await _create_user_with_account(
            db_session, email="lp_multi@example.com",
        )
        await _create_perps_position(
            db_session, account,
            product_id="BTC-PERP-INTX",
            direction="long",
        )
        await _create_perps_position(
            db_session, account,
            product_id="ETH-PERP-INTX",
            direction="short",
            short_total_sold_base=1.0,
            short_total_sold_quote=4000.0,
        )

        exchange = MagicMock()

        result = await list_perps_positions(
            db=db_session,
            exchange=exchange,
            current_user=user,
        )

        assert result["count"] == 2
        product_ids = {p["product_id"] for p in result["positions"]}
        assert product_ids == {"BTC-PERP-INTX", "ETH-PERP-INTX"}

    @pytest.mark.asyncio
    async def test_no_accounts_returns_empty(self, db_session):
        """Edge case: user with no accounts returns empty positions."""
        from app.position_routers.perps_router import list_perps_positions

        user = User(
            email="lp_noacct@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        exchange = MagicMock()

        result = await list_perps_positions(
            db=db_session,
            exchange=exchange,
            current_user=user,
        )

        assert result["count"] == 0
