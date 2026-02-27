"""
Tests for backend/app/exchange_clients/base.py

Tests the ExchangeClient abstract base class, specifically the
default implementations of non-abstract methods.
"""

import pytest

from app.exchange_clients.base import ExchangeClient


# =========================================================
# Concrete subclass for testing
# =========================================================


class StubExchangeClient(ExchangeClient):
    """Minimal concrete implementation for testing base class defaults."""

    async def get_accounts(self, force_fresh=False):
        return []

    async def get_account(self, account_id):
        return {}

    async def get_btc_balance(self):
        return 0.0

    async def get_eth_balance(self):
        return 0.0

    async def get_usd_balance(self):
        return 0.0

    async def get_balance(self, currency):
        return {"currency": currency, "available": "0", "hold": "0"}

    async def invalidate_balance_cache(self):
        pass

    async def calculate_aggregate_btc_value(self, bypass_cache=False):
        return 0.0

    async def calculate_aggregate_usd_value(self):
        return 0.0

    async def calculate_aggregate_quote_value(self, quote_currency, bypass_cache=False):
        return 0.0

    async def list_products(self):
        return []

    async def get_product(self, product_id="ETH-BTC"):
        return {}

    async def get_ticker(self, product_id="ETH-BTC"):
        return {}

    async def get_current_price(self, product_id="ETH-BTC"):
        return 0.0

    async def get_btc_usd_price(self):
        return 0.0

    async def get_eth_usd_price(self):
        return 0.0

    async def get_product_stats(self, product_id="ETH-BTC"):
        return {}

    async def get_candles(self, product_id, start, end, granularity):
        return []

    async def create_market_order(self, product_id, side, size=None, funds=None):
        return {"success": True}

    async def create_limit_order(self, product_id, side, limit_price, size=None, funds=None):
        return {"success": True}

    async def get_order(self, order_id):
        return {}

    async def cancel_order(self, order_id):
        return {}

    async def list_orders(self, product_id=None, order_status=None, limit=100):
        return []

    async def buy_eth_with_btc(self, btc_amount, product_id="ETH-BTC"):
        return {}

    async def sell_eth_for_btc(self, eth_amount, product_id="ETH-BTC"):
        return {}

    async def buy_with_usd(self, usd_amount, product_id):
        return {}

    async def sell_for_usd(self, base_amount, product_id):
        return {}

    def get_exchange_type(self):
        return "cex"

    async def test_connection(self):
        return True


# =========================================================
# Tests for base class default methods
# =========================================================


class TestEditOrderDefault:
    """Tests for the default edit_order implementation."""

    @pytest.mark.asyncio
    async def test_edit_order_raises_not_implemented(self):
        """Happy path: default edit_order raises NotImplementedError."""
        client = StubExchangeClient()
        with pytest.raises(NotImplementedError, match="does not support edit_order"):
            await client.edit_order("order-1", price="50000")

    @pytest.mark.asyncio
    async def test_edit_order_includes_class_name(self):
        """Edge case: error message includes the class name."""
        client = StubExchangeClient()
        with pytest.raises(NotImplementedError, match="StubExchangeClient"):
            await client.edit_order("order-1")


class TestGetRecentTradesDefault:
    """Tests for the default get_recent_trades implementation."""

    @pytest.mark.asyncio
    async def test_get_recent_trades_returns_empty_list(self):
        """Happy path: default returns empty list (volume weighting disabled)."""
        client = StubExchangeClient()
        result = await client.get_recent_trades("BTC-USD")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_recent_trades_with_custom_hours(self):
        """Edge case: custom hours parameter accepted."""
        client = StubExchangeClient()
        result = await client.get_recent_trades("BTC-USD", hours=48)
        assert result == []


class TestAbstractInstantiation:
    """Tests that abstract class cannot be instantiated directly."""

    def test_cannot_instantiate_abstract_class(self):
        """Failure case: ExchangeClient cannot be instantiated directly."""
        with pytest.raises(TypeError):
            ExchangeClient()
