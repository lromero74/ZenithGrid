"""
Tests for backend/app/services/account_service.py

Covers:
- validate_prop_firm_config: schema/SSRF validation
- create_exchange_account: full creation flow with encryption/connectivity
- get_portfolio_for_account: routing to correct portfolio builder
- _build_paper_portfolio: virtual balance construction with real-time pricing
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.exceptions import NotFoundError, ValidationError
from app.services.account_service import (
    validate_prop_firm_config,
    create_exchange_account,
    get_portfolio_for_account,
    _build_paper_portfolio,
    VALID_EXCHANGES,
    VALID_PROP_FIRMS,
)


# =============================================================================
# validate_prop_firm_config
# =============================================================================


class TestValidatePropFirmConfig:
    """Tests for validate_prop_firm_config()."""

    def test_valid_config_mt5_bridge(self):
        """Happy path: valid MT5 bridge config passes."""
        config = {"bridge_url": "https://api.example.com/mt5", "testnet": True}
        # Should not raise
        validate_prop_firm_config(config, "mt5_bridge")

    def test_valid_config_coinbase(self):
        """Happy path: valid config for non-MT5 exchange passes."""
        config = {"api_key": "test-key", "api_secret": "test-secret"}
        validate_prop_firm_config(config, "coinbase")

    def test_non_dict_raises(self):
        """Failure: non-dict config raises ValidationError."""
        with pytest.raises(ValidationError, match="must be a JSON object"):
            validate_prop_firm_config("not a dict", "coinbase")

    def test_bridge_url_private_ip_localhost_raises(self):
        """Failure: bridge_url pointing to localhost is blocked (SSRF)."""
        config = {"bridge_url": "http://localhost:8080/api"}
        with pytest.raises(ValidationError, match="private/internal"):
            validate_prop_firm_config(config, "mt5_bridge")

    def test_bridge_url_private_ip_127_raises(self):
        """Failure: bridge_url pointing to 127.0.0.1 is blocked."""
        config = {"bridge_url": "http://127.0.0.1:8080/api"}
        with pytest.raises(ValidationError, match="private/internal"):
            validate_prop_firm_config(config, "mt5_bridge")

    def test_bridge_url_private_ip_10_raises(self):
        """Failure: bridge_url pointing to 10.x is blocked."""
        config = {"bridge_url": "http://10.0.0.1:8080/api"}
        with pytest.raises(ValidationError, match="private/internal"):
            validate_prop_firm_config(config, "mt5_bridge")

    def test_bridge_url_private_ip_192_168_raises(self):
        """Failure: bridge_url pointing to 192.168.x is blocked."""
        config = {"bridge_url": "http://192.168.1.1:8080/api"}
        with pytest.raises(ValidationError, match="private/internal"):
            validate_prop_firm_config(config, "mt5_bridge")

    def test_bridge_url_private_ip_172_16_raises(self):
        """Failure: bridge_url pointing to 172.16.x is blocked."""
        config = {"bridge_url": "http://172.16.0.1:8080/api"}
        with pytest.raises(ValidationError, match="private/internal"):
            validate_prop_firm_config(config, "mt5_bridge")

    def test_bridge_url_invalid_scheme_raises(self):
        """Failure: bridge_url with ftp:// scheme is blocked."""
        config = {"bridge_url": "ftp://files.example.com/data"}
        with pytest.raises(ValidationError, match="http:// or https://"):
            validate_prop_firm_config(config, "mt5_bridge")

    def test_testnet_non_boolean_raises(self):
        """Failure: testnet as string instead of bool raises."""
        config = {"testnet": "yes"}
        with pytest.raises(ValidationError, match="testnet must be a boolean"):
            validate_prop_firm_config(config, "coinbase")

    def test_unknown_keys_raises(self):
        """Failure: unknown keys in config raise ValidationError."""
        config = {"api_key": "k", "unknown_field": "bad"}
        with pytest.raises(ValidationError, match="Unknown keys"):
            validate_prop_firm_config(config, "coinbase")

    def test_empty_config_passes(self):
        """Edge case: empty dict passes validation."""
        validate_prop_firm_config({}, "coinbase")


# =============================================================================
# create_exchange_account
# =============================================================================


class TestCreateExchangeAccount:
    """Tests for create_exchange_account()."""

    @pytest.mark.asyncio
    async def test_creates_cex_account_successfully(self):
        """Happy path: CEX account created, connection tested, returned."""
        db = AsyncMock()
        user = MagicMock()
        user.id = 1

        account_data = MagicMock()
        account_data.type = "cex"
        account_data.exchange = "coinbase"
        account_data.name = "Main Account"
        account_data.is_default = False
        account_data.api_key_name = "key-name"
        account_data.api_private_key = "private-key"
        account_data.chain_id = None
        account_data.wallet_address = None
        account_data.wallet_private_key = None
        account_data.rpc_url = None
        account_data.wallet_type = None
        account_data.prop_firm = None
        account_data.prop_firm_config = None
        account_data.prop_daily_drawdown_pct = None
        account_data.prop_total_drawdown_pct = None
        account_data.prop_initial_deposit = None

        mock_client = AsyncMock()
        mock_client.test_connection.return_value = True

        with patch(
            "app.services.account_service.encrypt_value",
            side_effect=lambda v: f"enc_{v}",
        ), patch(
            "app.services.account_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            result = await create_exchange_account(db, user, account_data)

        db.add.assert_called_once()
        db.commit.assert_called()
        db.refresh.assert_called()

    @pytest.mark.asyncio
    async def test_invalid_account_type_raises(self):
        """Failure: invalid account type raises ValidationError."""
        db = AsyncMock()
        user = MagicMock()
        user.id = 1

        account_data = MagicMock()
        account_data.type = "invalid"

        with pytest.raises(ValidationError, match="must be 'cex' or 'dex'"):
            await create_exchange_account(db, user, account_data)

    @pytest.mark.asyncio
    async def test_cex_without_exchange_raises(self):
        """Failure: CEX account without exchange field raises."""
        db = AsyncMock()
        user = MagicMock()
        user.id = 1

        account_data = MagicMock()
        account_data.type = "cex"
        account_data.exchange = None

        with pytest.raises(ValidationError, match="require 'exchange'"):
            await create_exchange_account(db, user, account_data)

    @pytest.mark.asyncio
    async def test_unsupported_exchange_raises(self):
        """Failure: unsupported exchange name raises ValidationError."""
        db = AsyncMock()
        user = MagicMock()
        user.id = 1

        account_data = MagicMock()
        account_data.type = "cex"
        account_data.exchange = "kraken"

        with pytest.raises(ValidationError, match="Unsupported exchange"):
            await create_exchange_account(db, user, account_data)

    @pytest.mark.asyncio
    async def test_dex_without_chain_id_raises(self):
        """Failure: DEX account without chain_id raises."""
        db = AsyncMock()
        user = MagicMock()
        user.id = 1

        account_data = MagicMock()
        account_data.type = "dex"
        account_data.exchange = None
        account_data.chain_id = None
        account_data.wallet_address = "0xabc"

        with pytest.raises(ValidationError, match="require 'chain_id'"):
            await create_exchange_account(db, user, account_data)

    @pytest.mark.asyncio
    async def test_dex_without_wallet_address_raises(self):
        """Failure: DEX account without wallet_address raises."""
        db = AsyncMock()
        user = MagicMock()
        user.id = 1

        account_data = MagicMock()
        account_data.type = "dex"
        account_data.exchange = None
        account_data.chain_id = 1
        account_data.wallet_address = None

        with pytest.raises(ValidationError, match="require 'wallet_address'"):
            await create_exchange_account(db, user, account_data)

    @pytest.mark.asyncio
    async def test_connection_test_failure_deletes_account(self):
        """Failure: failed connection test deletes account and raises."""
        db = AsyncMock()
        user = MagicMock()
        user.id = 1

        account_data = MagicMock()
        account_data.type = "cex"
        account_data.exchange = "coinbase"
        account_data.name = "Bad Account"
        account_data.is_default = False
        account_data.api_key_name = "key"
        account_data.api_private_key = "secret"
        account_data.chain_id = None
        account_data.wallet_address = None
        account_data.wallet_private_key = None
        account_data.rpc_url = None
        account_data.wallet_type = None
        account_data.prop_firm = None
        account_data.prop_firm_config = None
        account_data.prop_daily_drawdown_pct = None
        account_data.prop_total_drawdown_pct = None
        account_data.prop_initial_deposit = None

        mock_client = AsyncMock()
        mock_client.test_connection.return_value = False

        with patch(
            "app.services.account_service.encrypt_value",
            side_effect=lambda v: f"enc_{v}",
        ), patch(
            "app.services.account_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            with pytest.raises(ValidationError, match="Connection test failed"):
                await create_exchange_account(db, user, account_data)

        # Account should have been deleted
        db.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsupported_prop_firm_raises(self):
        """Failure: unsupported prop firm raises ValidationError."""
        db = AsyncMock()
        user = MagicMock()
        user.id = 1

        account_data = MagicMock()
        account_data.type = "cex"
        account_data.exchange = "coinbase"
        account_data.prop_firm = "unknown_firm"
        account_data.prop_firm_config = None

        with pytest.raises(ValidationError, match="Unsupported prop firm"):
            await create_exchange_account(db, user, account_data)


# =============================================================================
# get_portfolio_for_account
# =============================================================================


class TestGetPortfolioForAccount:
    """Tests for get_portfolio_for_account()."""

    @pytest.mark.asyncio
    async def test_account_not_found_raises(self):
        """Failure: non-existent account raises NotFoundError."""
        db = AsyncMock()
        user = MagicMock()
        user.id = 1

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        with pytest.raises(NotFoundError):
            await get_portfolio_for_account(db, user, account_id=999)

    @pytest.mark.asyncio
    async def test_paper_trading_routes_to_build_paper_portfolio(self):
        """Happy path: paper trading account calls _build_paper_portfolio."""
        db = AsyncMock()
        user = MagicMock()
        user.id = 1

        account = MagicMock()
        account.is_paper_trading = True
        account.paper_balances = json.dumps({"BTC": 1.0, "USD": 50000.0})

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = account
        db.execute.return_value = mock_result

        with patch(
            "app.services.account_service._build_paper_portfolio",
            new_callable=AsyncMock,
            return_value={"is_paper_trading": True},
        ) as mock_build:
            result = await get_portfolio_for_account(db, user, account_id=1)

        mock_build.assert_called_once_with(account)
        assert result["is_paper_trading"] is True

    @pytest.mark.asyncio
    async def test_cex_coinbase_routes_to_cex_portfolio(self):
        """Happy path: CEX coinbase account routes to get_cex_portfolio."""
        db = AsyncMock()
        user = MagicMock()
        user.id = 1

        account = MagicMock()
        account.is_paper_trading = False
        account.type = "cex"
        account.exchange = "coinbase"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = account
        db.execute.return_value = mock_result

        with patch(
            "app.services.account_service.get_cex_portfolio",
            new_callable=AsyncMock,
            return_value={"holdings": []},
        ) as mock_cex:
            result = await get_portfolio_for_account(db, user, account_id=1)

        mock_cex.assert_called_once()

    @pytest.mark.asyncio
    async def test_cex_bybit_routes_to_generic_portfolio(self):
        """Happy path: bybit account routes to get_generic_cex_portfolio."""
        db = AsyncMock()
        user = MagicMock()
        user.id = 1

        account = MagicMock()
        account.is_paper_trading = False
        account.type = "cex"
        account.exchange = "bybit"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = account
        db.execute.return_value = mock_result

        with patch(
            "app.services.account_service.get_generic_cex_portfolio",
            new_callable=AsyncMock,
            return_value={"holdings": []},
        ) as mock_generic:
            result = await get_portfolio_for_account(db, user, account_id=1)

        mock_generic.assert_called_once()

    @pytest.mark.asyncio
    async def test_dex_routes_to_dex_portfolio(self):
        """Happy path: DEX account routes to get_dex_portfolio."""
        db = AsyncMock()
        user = MagicMock()
        user.id = 1

        account = MagicMock()
        account.is_paper_trading = False
        account.type = "dex"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = account
        db.execute.return_value = mock_result

        with patch(
            "app.services.account_service.get_dex_portfolio",
            new_callable=AsyncMock,
            return_value={"holdings": []},
        ) as mock_dex:
            result = await get_portfolio_for_account(db, user, account_id=1)

        mock_dex.assert_called_once()


# =============================================================================
# _build_paper_portfolio
# =============================================================================


class TestBuildPaperPortfolio:
    """Tests for _build_paper_portfolio()."""

    @pytest.mark.asyncio
    async def test_builds_portfolio_with_balances(self):
        """Happy path: constructs portfolio from paper balances."""
        account = MagicMock()
        account.paper_balances = json.dumps({"BTC": 0.5, "USD": 25000.0})

        with patch(
            "app.coinbase_api.public_market_data.get_btc_usd_price",
            new_callable=AsyncMock,
            return_value=100000.0,
        ), patch(
            "app.coinbase_api.public_market_data.get_current_price",
            new_callable=AsyncMock,
            return_value=0.0,
        ):
            result = await _build_paper_portfolio(account)

        assert result["is_paper_trading"] is True
        assert result["btc_usd_price"] == 100000.0
        assert len(result["holdings"]) == 2
        assert result["total_usd_value"] > 0

    @pytest.mark.asyncio
    async def test_empty_balances_uses_defaults(self):
        """Edge case: None paper_balances uses default currencies."""
        account = MagicMock()
        account.paper_balances = None

        with patch(
            "app.coinbase_api.public_market_data.get_btc_usd_price",
            new_callable=AsyncMock,
            return_value=100000.0,
        ), patch(
            "app.coinbase_api.public_market_data.get_current_price",
            new_callable=AsyncMock,
            return_value=0.0,
        ):
            result = await _build_paper_portfolio(account)

        assert result["is_paper_trading"] is True
        # Default balances are all 0, so no holdings with value > 0
        assert result["holdings_count"] == 0

    @pytest.mark.asyncio
    async def test_stablecoin_value_calculation(self):
        """Happy path: USD/USDC/USDT treated as $1.00 each."""
        account = MagicMock()
        account.paper_balances = json.dumps({"USDC": 5000.0})

        with patch(
            "app.coinbase_api.public_market_data.get_btc_usd_price",
            new_callable=AsyncMock,
            return_value=100000.0,
        ), patch(
            "app.coinbase_api.public_market_data.get_current_price",
            new_callable=AsyncMock,
            return_value=0.0,
        ):
            result = await _build_paper_portfolio(account)

        assert result["total_usd_value"] == pytest.approx(5000.0)
        assert len(result["holdings"]) == 1
        assert result["holdings"][0]["asset"] == "USDC"
        assert result["holdings"][0]["current_price_usd"] == 1.0

    @pytest.mark.asyncio
    async def test_allocation_percentages_sum_to_100(self):
        """Edge case: allocation percentages should sum to ~100%."""
        account = MagicMock()
        account.paper_balances = json.dumps({"BTC": 0.5, "USD": 10000.0, "USDC": 5000.0})

        with patch(
            "app.coinbase_api.public_market_data.get_btc_usd_price",
            new_callable=AsyncMock,
            return_value=100000.0,
        ), patch(
            "app.coinbase_api.public_market_data.get_current_price",
            new_callable=AsyncMock,
            return_value=0.0,
        ):
            result = await _build_paper_portfolio(account)

        total_pct = sum(h["percentage"] for h in result["holdings"])
        assert total_pct == pytest.approx(100.0)
