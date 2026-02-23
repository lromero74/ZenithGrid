"""
Tests for backend/app/bot_routers/bot_validation_router.py

Covers bot configuration validation against exchange minimum order sizes.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.models import Account, User


# =============================================================================
# Helpers
# =============================================================================


def _make_user():
    """Create a test user."""
    user = User(
        email="validation@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        created_at=datetime.utcnow(),
    )
    return user


async def _make_cex_account(db_session, user, is_paper=False, api_key_name="key-name",
                            api_private_key="private-key"):
    """Create, flush, and return a CEX account."""
    account = Account(
        user_id=user.id,
        name="Test CEX" if not is_paper else "Test Paper",
        type="cex",
        is_default=True,
        is_active=True,
        is_paper_trading=is_paper,
        exchange="coinbase",
        api_key_name=api_key_name if not is_paper else None,
        api_private_key=api_private_key if not is_paper else None,
        created_at=datetime.utcnow(),
    )
    db_session.add(account)
    await db_session.flush()
    return account


# =============================================================================
# _get_exchange_client (helper function)
# =============================================================================


class TestGetExchangeClient:
    """Tests for the _get_exchange_client helper function."""

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_validation_router.create_exchange_client")
    @patch("app.bot_routers.bot_validation_router.is_encrypted", return_value=False)
    async def test_returns_cex_client_when_available(
        self, mock_is_encrypted, mock_create_client, db_session
    ):
        """Happy path: returns exchange client for a real CEX account."""
        from app.bot_routers.bot_validation_router import _get_exchange_client

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        await _make_cex_account(db_session, user)

        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        client, account = await _get_exchange_client(db_session, user.id)

        assert client is mock_client
        assert account is not None
        assert account.type == "cex"

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_validation_router.PaperTradingClient")
    async def test_falls_back_to_paper_trading(
        self, mock_paper_cls, db_session
    ):
        """Edge case: falls back to paper trading client when no CEX account."""
        from app.bot_routers.bot_validation_router import _get_exchange_client

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        await _make_cex_account(db_session, user, is_paper=True)

        mock_paper = MagicMock()
        mock_paper_cls.return_value = mock_paper

        client, account = await _get_exchange_client(db_session, user.id)

        assert client is mock_paper
        assert account.is_paper_trading is True

    @pytest.mark.asyncio
    async def test_returns_none_when_no_accounts(self, db_session):
        """Failure: returns (None, None) when no accounts exist."""
        from app.bot_routers.bot_validation_router import _get_exchange_client

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        client, account = await _get_exchange_client(db_session, user.id)

        assert client is None
        assert account is None

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_validation_router.create_exchange_client")
    @patch("app.bot_routers.bot_validation_router.decrypt_value", return_value="decrypted-key")
    @patch("app.bot_routers.bot_validation_router.is_encrypted", return_value=True)
    async def test_decrypts_encrypted_private_key(
        self, mock_is_encrypted, mock_decrypt, mock_create_client, db_session
    ):
        """Happy path: decrypts an encrypted private key before creating client."""
        from app.bot_routers.bot_validation_router import _get_exchange_client

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        await _make_cex_account(db_session, user, api_private_key="encrypted:abc123")

        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        client, account = await _get_exchange_client(db_session, user.id)

        mock_decrypt.assert_called_once_with("encrypted:abc123")
        mock_create_client.assert_called_once_with(
            exchange_type="cex",
            coinbase_key_name="key-name",
            coinbase_private_key="decrypted-key",
        )


# =============================================================================
# POST /validate-config
# =============================================================================


class TestValidateBotConfig:
    """Tests for POST /validate-config"""

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_validation_router._get_exchange_client", new_callable=AsyncMock)
    async def test_no_account_raises_400(self, mock_get_exchange, db_session):
        """Failure: no active exchange or paper account raises 400."""
        from app.bot_routers.bot_validation_router import validate_bot_config
        from app.bot_routers.schemas import ValidateBotConfigRequest

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        mock_get_exchange.return_value = (None, None)

        request = ValidateBotConfigRequest(
            product_ids=["ETH-BTC"],
            strategy_config={"base_order_percentage": 5.0},
        )

        with pytest.raises(HTTPException) as exc_info:
            await validate_bot_config(
                request=request, db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 400
        assert "No active exchange" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_validation_router._get_exchange_client", new_callable=AsyncMock)
    async def test_zero_balance_returns_invalid(self, mock_get_exchange, db_session):
        """Edge case: zero balance returns is_valid=False."""
        from app.bot_routers.bot_validation_router import validate_bot_config
        from app.bot_routers.schemas import ValidateBotConfigRequest

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        mock_client = AsyncMock()
        mock_client.get_btc_balance = AsyncMock(return_value=0.0)
        mock_account = MagicMock()
        mock_account.is_paper_trading = False
        mock_get_exchange.return_value = (mock_client, mock_account)

        request = ValidateBotConfigRequest(
            product_ids=["ETH-BTC"],
            strategy_config={"base_order_percentage": 5.0},
            quote_balance=0.0,
        )

        result = await validate_bot_config(
            request=request, db=db_session, current_user=user
        )

        assert result.is_valid is False
        assert "No quote currency balance" in result.message

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_validation_router._get_exchange_client", new_callable=AsyncMock)
    async def test_no_order_percentage_returns_invalid(self, mock_get_exchange, db_session):
        """Edge case: strategy_config with no order percentage returns is_valid=False."""
        from app.bot_routers.bot_validation_router import validate_bot_config
        from app.bot_routers.schemas import ValidateBotConfigRequest

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        mock_client = AsyncMock()
        mock_account = MagicMock()
        mock_account.is_paper_trading = False
        mock_get_exchange.return_value = (mock_client, mock_account)

        request = ValidateBotConfigRequest(
            product_ids=["ETH-BTC"],
            strategy_config={},  # No percentage configured
            quote_balance=1.0,
        )

        result = await validate_bot_config(
            request=request, db=db_session, current_user=user
        )

        assert result.is_valid is False
        assert "No order percentage" in result.message

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_validation_router.calculate_minimum_budget_percentage",
           new_callable=AsyncMock)
    @patch("app.bot_routers.bot_validation_router._get_exchange_client", new_callable=AsyncMock)
    async def test_valid_config_returns_valid(
        self, mock_get_exchange, mock_calc_min, db_session
    ):
        """Happy path: valid config with sufficient order size returns is_valid=True."""
        from app.bot_routers.bot_validation_router import validate_bot_config
        from app.bot_routers.schemas import ValidateBotConfigRequest

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        mock_client = AsyncMock()
        mock_account = MagicMock()
        mock_account.is_paper_trading = False
        mock_get_exchange.return_value = (mock_client, mock_account)

        # Order pct (5.0) > minimum (0.5) -> valid
        mock_calc_min.return_value = 0.5

        request = ValidateBotConfigRequest(
            product_ids=["ETH-BTC"],
            strategy_config={"base_order_percentage": 5.0},
            quote_balance=1.0,
        )

        result = await validate_bot_config(
            request=request, db=db_session, current_user=user
        )

        assert result.is_valid is True
        assert len(result.warnings) == 0
        assert "valid" in result.message.lower()

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_validation_router.calculate_minimum_budget_percentage",
           new_callable=AsyncMock)
    @patch("app.bot_routers.bot_validation_router._get_exchange_client", new_callable=AsyncMock)
    async def test_config_below_minimum_returns_warnings(
        self, mock_get_exchange, mock_calc_min, db_session
    ):
        """Edge case: order pct below exchange minimum produces a warning."""
        from app.bot_routers.bot_validation_router import validate_bot_config
        from app.bot_routers.schemas import ValidateBotConfigRequest

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        mock_client = AsyncMock()
        mock_account = MagicMock()
        mock_account.is_paper_trading = False
        mock_get_exchange.return_value = (mock_client, mock_account)

        # Order pct (0.1) < minimum (0.5) -> warning
        mock_calc_min.return_value = 0.5

        request = ValidateBotConfigRequest(
            product_ids=["ETH-BTC"],
            strategy_config={"base_order_percentage": 0.1},
            quote_balance=1.0,
        )

        result = await validate_bot_config(
            request=request, db=db_session, current_user=user
        )

        assert result.is_valid is False
        assert len(result.warnings) == 1
        assert result.warnings[0].product_id == "ETH-BTC"
        assert result.warnings[0].suggested_minimum_pct == pytest.approx(0.5)
        assert result.warnings[0].current_pct == pytest.approx(0.1)

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_validation_router.calculate_minimum_budget_percentage",
           new_callable=AsyncMock)
    @patch("app.bot_routers.bot_validation_router._get_exchange_client", new_callable=AsyncMock)
    async def test_multiple_products_mixed_warnings(
        self, mock_get_exchange, mock_calc_min, db_session
    ):
        """Edge case: multiple products can produce warnings for some but not all."""
        from app.bot_routers.bot_validation_router import validate_bot_config
        from app.bot_routers.schemas import ValidateBotConfigRequest

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        mock_client = AsyncMock()
        mock_account = MagicMock()
        mock_account.is_paper_trading = False
        mock_get_exchange.return_value = (mock_client, mock_account)

        # ETH-BTC needs 0.3 min (ok), SOL-BTC needs 2.0 min (warning)
        async def side_effect(client, product_id, balance):
            if product_id == "ETH-BTC":
                return 0.3
            return 2.0

        mock_calc_min.side_effect = side_effect

        request = ValidateBotConfigRequest(
            product_ids=["ETH-BTC", "SOL-BTC"],
            strategy_config={"base_order_percentage": 1.0},
            quote_balance=1.0,
        )

        result = await validate_bot_config(
            request=request, db=db_session, current_user=user
        )

        assert result.is_valid is False
        assert len(result.warnings) == 1
        assert result.warnings[0].product_id == "SOL-BTC"

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_validation_router.calculate_minimum_budget_percentage",
           new_callable=AsyncMock)
    @patch("app.bot_routers.bot_validation_router._get_exchange_client", new_callable=AsyncMock)
    async def test_calc_min_exception_is_swallowed(
        self, mock_get_exchange, mock_calc_min, db_session
    ):
        """Edge case: exception from calculate_minimum_budget_percentage is logged, not raised."""
        from app.bot_routers.bot_validation_router import validate_bot_config
        from app.bot_routers.schemas import ValidateBotConfigRequest

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        mock_client = AsyncMock()
        mock_account = MagicMock()
        mock_account.is_paper_trading = False
        mock_get_exchange.return_value = (mock_client, mock_account)

        mock_calc_min.side_effect = Exception("API timeout")

        request = ValidateBotConfigRequest(
            product_ids=["ETH-BTC"],
            strategy_config={"base_order_percentage": 5.0},
            quote_balance=1.0,
        )

        # Should not raise - exception is caught and logged
        result = await validate_bot_config(
            request=request, db=db_session, current_user=user
        )

        assert result.is_valid is True
        assert len(result.warnings) == 0

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_validation_router._get_exchange_client", new_callable=AsyncMock)
    async def test_auto_fetches_btc_balance(self, mock_get_exchange, db_session):
        """Edge case: when quote_balance is not provided, fetches BTC balance from exchange."""
        from app.bot_routers.bot_validation_router import validate_bot_config
        from app.bot_routers.schemas import ValidateBotConfigRequest

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        mock_client = AsyncMock()
        mock_client.get_btc_balance = AsyncMock(return_value=0.0)
        mock_account = MagicMock()
        mock_account.is_paper_trading = False
        mock_get_exchange.return_value = (mock_client, mock_account)

        request = ValidateBotConfigRequest(
            product_ids=["ETH-BTC"],
            strategy_config={"base_order_percentage": 5.0},
            # quote_balance not provided - should auto-fetch
        )

        result = await validate_bot_config(
            request=request, db=db_session, current_user=user
        )

        # Balance is 0 -> not valid
        mock_client.get_btc_balance.assert_called_once()
        assert result.is_valid is False

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_validation_router._get_exchange_client", new_callable=AsyncMock)
    async def test_uses_safety_order_percentage(self, mock_get_exchange, db_session):
        """Edge case: uses safety_order_percentage when base_order_percentage is zero."""
        from app.bot_routers.bot_validation_router import validate_bot_config
        from app.bot_routers.schemas import ValidateBotConfigRequest

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        mock_client = AsyncMock()
        mock_account = MagicMock()
        mock_account.is_paper_trading = False
        mock_get_exchange.return_value = (mock_client, mock_account)

        request = ValidateBotConfigRequest(
            product_ids=["ETH-BTC"],
            strategy_config={
                "base_order_percentage": 0,
                "safety_order_percentage": 3.0,
            },
            quote_balance=1.0,
        )

        # The function uses max(base, safety, initial) which should be 3.0
        # With no calculate_minimum_budget_percentage mock, it will try the real thing.
        # We need to patch it to avoid real API calls.
        with patch(
            "app.bot_routers.bot_validation_router.calculate_minimum_budget_percentage",
            new_callable=AsyncMock, return_value=0.5
        ):
            result = await validate_bot_config(
                request=request, db=db_session, current_user=user
            )

        assert result.is_valid is True

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_validation_router._get_exchange_client", new_callable=AsyncMock)
    async def test_paper_trading_reads_paper_balances(self, mock_get_exchange, db_session):
        """Edge case: paper trading account reads balance from paper_balances JSON."""
        from app.bot_routers.bot_validation_router import validate_bot_config
        from app.bot_routers.schemas import ValidateBotConfigRequest
        import json

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        mock_client = AsyncMock()
        mock_account = MagicMock()
        mock_account.is_paper_trading = True
        mock_account.paper_balances = json.dumps({"BTC": 0.5, "USD": 10000.0})
        mock_get_exchange.return_value = (mock_client, mock_account)

        request = ValidateBotConfigRequest(
            product_ids=["ETH-BTC"],
            strategy_config={"base_order_percentage": 5.0},
            # No quote_balance -> should read from paper_balances
        )

        with patch(
            "app.bot_routers.bot_validation_router.calculate_minimum_budget_percentage",
            new_callable=AsyncMock, return_value=0.5
        ):
            result = await validate_bot_config(
                request=request, db=db_session, current_user=user
            )

        assert result.is_valid is True
