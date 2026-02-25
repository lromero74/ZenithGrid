"""
Tests for backend/app/trading_client.py

TradingClient is a currency-agnostic wrapper around ExchangeClient that
routes buy/sell/balance operations based on the quote currency of a product_id.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.trading_client import TradingClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def exchange():
    """Create a mock ExchangeClient with all methods the TradingClient uses."""
    mock = MagicMock()
    mock.get_btc_balance = AsyncMock(return_value=1.5)
    mock.get_usd_balance = AsyncMock(return_value=10000.0)
    mock.buy_eth_with_btc = AsyncMock(return_value={"order_id": "buy-btc-123", "success": True})
    mock.buy_with_usd = AsyncMock(return_value={"order_id": "buy-usd-456", "success": True})
    mock.sell_eth_for_btc = AsyncMock(return_value={"order_id": "sell-btc-789", "success": True})
    mock.sell_for_usd = AsyncMock(return_value={"order_id": "sell-usd-012", "success": True})
    mock.create_limit_order = AsyncMock(return_value={"order_id": "limit-345", "success": True})
    mock.get_order = AsyncMock(return_value={"order_id": "ord-1", "status": "FILLED"})
    mock.cancel_order = AsyncMock(return_value={"success": True})
    mock.invalidate_balance_cache = AsyncMock()
    mock.get_btc_usd_price = AsyncMock(return_value=65000.0)
    return mock


@pytest.fixture
def client(exchange):
    """Create a TradingClient wrapping the mock exchange."""
    return TradingClient(exchange)


# ===========================================================================
# get_balance
# ===========================================================================


class TestGetBalance:
    """Tests for TradingClient.get_balance()"""

    @pytest.mark.asyncio
    async def test_get_balance_btc_returns_btc_balance(self, client, exchange):
        """Happy path: BTC currency delegates to get_btc_balance."""
        result = await client.get_balance("BTC")
        assert result == 1.5
        exchange.get_btc_balance.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_balance_usd_returns_usd_balance(self, client, exchange):
        """Happy path: USD currency delegates to get_usd_balance."""
        result = await client.get_balance("USD")
        assert result == 10000.0
        exchange.get_usd_balance.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_balance_usdt_returns_usd_balance(self, client, exchange):
        """Edge case: USDT treated as stablecoin, uses get_usd_balance."""
        result = await client.get_balance("USDT")
        assert result == 10000.0
        exchange.get_usd_balance.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_balance_usdc_returns_usd_balance(self, client, exchange):
        """Edge case: USDC treated as stablecoin, uses get_usd_balance."""
        result = await client.get_balance("USDC")
        assert result == 10000.0
        exchange.get_usd_balance.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_balance_unsupported_currency_raises(self, client):
        """Failure: unsupported currency raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported quote currency: ETH"):
            await client.get_balance("ETH")

    @pytest.mark.asyncio
    async def test_get_balance_unsupported_currency_eur_raises(self, client):
        """Failure: EUR is not a supported currency."""
        with pytest.raises(ValueError, match="Unsupported quote currency: EUR"):
            await client.get_balance("EUR")


# ===========================================================================
# get_quote_balance
# ===========================================================================


class TestGetQuoteBalance:
    """Tests for TradingClient.get_quote_balance()"""

    @pytest.mark.asyncio
    async def test_get_quote_balance_btc_pair(self, client, exchange):
        """Happy path: BTC-quoted pair returns BTC balance."""
        result = await client.get_quote_balance("ETH-BTC")
        assert result == 1.5
        exchange.get_btc_balance.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_quote_balance_usd_pair(self, client, exchange):
        """Happy path: USD-quoted pair returns USD balance."""
        result = await client.get_quote_balance("BTC-USD")
        assert result == 10000.0
        exchange.get_usd_balance.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_quote_balance_usdt_pair(self, client, exchange):
        """Edge case: USDT pair returns USD balance via stablecoin mapping."""
        result = await client.get_quote_balance("ETH-USDT")
        assert result == 10000.0
        exchange.get_usd_balance.assert_awaited_once()


# ===========================================================================
# buy (market)
# ===========================================================================


class TestBuy:
    """Tests for TradingClient.buy()"""

    @pytest.mark.asyncio
    async def test_buy_btc_pair_calls_buy_eth_with_btc(self, client, exchange):
        """Happy path: BTC pair delegates to buy_eth_with_btc."""
        result = await client.buy("ETH-BTC", 0.01)
        assert result["order_id"] == "buy-btc-123"
        exchange.buy_eth_with_btc.assert_awaited_once_with(btc_amount=0.01, product_id="ETH-BTC")

    @pytest.mark.asyncio
    async def test_buy_usd_pair_calls_buy_with_usd(self, client, exchange):
        """Happy path: USD pair delegates to buy_with_usd."""
        result = await client.buy("ADA-USD", 50.0)
        assert result["order_id"] == "buy-usd-456"
        exchange.buy_with_usd.assert_awaited_once_with(usd_amount=50.0, product_id="ADA-USD")

    @pytest.mark.asyncio
    async def test_buy_usdc_pair_calls_buy_with_usd(self, client, exchange):
        """Edge case: USDC pair treated as USD pair."""
        result = await client.buy("SOL-USDC", 100.0)
        assert result["success"] is True
        exchange.buy_with_usd.assert_awaited_once_with(usd_amount=100.0, product_id="SOL-USDC")

    @pytest.mark.asyncio
    async def test_buy_unsupported_quote_raises(self, client):
        """Failure: unsupported quote currency raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported quote currency: EUR"):
            await client.buy("BTC-EUR", 100.0)


# ===========================================================================
# sell (market)
# ===========================================================================


class TestSell:
    """Tests for TradingClient.sell()"""

    @pytest.mark.asyncio
    async def test_sell_btc_pair_calls_sell_eth_for_btc(self, client, exchange):
        """Happy path: BTC pair delegates to sell_eth_for_btc."""
        result = await client.sell("ETH-BTC", 0.5)
        assert result["order_id"] == "sell-btc-789"
        exchange.sell_eth_for_btc.assert_awaited_once_with(eth_amount=0.5, product_id="ETH-BTC")

    @pytest.mark.asyncio
    async def test_sell_usd_pair_calls_sell_for_usd(self, client, exchange):
        """Happy path: USD pair delegates to sell_for_usd."""
        result = await client.sell("BTC-USD", 0.1)
        assert result["order_id"] == "sell-usd-012"
        exchange.sell_for_usd.assert_awaited_once_with(base_amount=0.1, product_id="BTC-USD")

    @pytest.mark.asyncio
    async def test_sell_usdt_pair_calls_sell_for_usd(self, client, exchange):
        """Edge case: USDT pair treated as USD pair."""
        result = await client.sell("ETH-USDT", 1.0)
        assert result["success"] is True
        exchange.sell_for_usd.assert_awaited_once_with(base_amount=1.0, product_id="ETH-USDT")

    @pytest.mark.asyncio
    async def test_sell_unsupported_quote_raises(self, client):
        """Failure: unsupported quote currency raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported quote currency: EUR"):
            await client.sell("BTC-EUR", 0.1)


# ===========================================================================
# buy_limit
# ===========================================================================


class TestBuyLimit:
    """Tests for TradingClient.buy_limit()"""

    @pytest.mark.asyncio
    async def test_buy_limit_delegates_to_create_limit_order(self, client, exchange):
        """Happy path: buy_limit creates BUY limit order with correct params."""
        result = await client.buy_limit("ETH-BTC", limit_price=0.035, quote_amount=0.01)
        assert result["order_id"] == "limit-345"
        exchange.create_limit_order.assert_awaited_once_with(
            product_id="ETH-BTC", side="BUY", limit_price=0.035, funds="0.01"
        )

    @pytest.mark.asyncio
    async def test_buy_limit_converts_funds_to_string(self, client, exchange):
        """Edge case: quote_amount float is converted to string for funds param."""
        await client.buy_limit("BTC-USD", limit_price=60000.0, quote_amount=500.0)
        call_kwargs = exchange.create_limit_order.call_args.kwargs
        assert call_kwargs["funds"] == "500.0"
        assert isinstance(call_kwargs["funds"], str)

    @pytest.mark.asyncio
    async def test_buy_limit_exchange_error_propagates(self, client, exchange):
        """Failure: exchange error propagates to caller."""
        exchange.create_limit_order = AsyncMock(side_effect=Exception("Exchange error"))
        with pytest.raises(Exception, match="Exchange error"):
            await client.buy_limit("ETH-BTC", limit_price=0.035, quote_amount=0.01)


# ===========================================================================
# sell_limit
# ===========================================================================


class TestSellLimit:
    """Tests for TradingClient.sell_limit()"""

    @pytest.mark.asyncio
    async def test_sell_limit_delegates_to_create_limit_order(self, client, exchange):
        """Happy path: sell_limit creates SELL limit order with correct params."""
        result = await client.sell_limit("ETH-BTC", limit_price=0.04, base_amount=2.0)
        assert result["order_id"] == "limit-345"
        exchange.create_limit_order.assert_awaited_once_with(
            product_id="ETH-BTC", side="SELL", limit_price=0.04, size="2.0"
        )

    @pytest.mark.asyncio
    async def test_sell_limit_converts_size_to_string(self, client, exchange):
        """Edge case: base_amount float is converted to string for size param."""
        await client.sell_limit("BTC-USD", limit_price=70000.0, base_amount=0.5)
        call_kwargs = exchange.create_limit_order.call_args.kwargs
        assert call_kwargs["size"] == "0.5"
        assert isinstance(call_kwargs["size"], str)

    @pytest.mark.asyncio
    async def test_sell_limit_exchange_error_propagates(self, client, exchange):
        """Failure: exchange error propagates to caller."""
        exchange.create_limit_order = AsyncMock(side_effect=RuntimeError("Timeout"))
        with pytest.raises(RuntimeError, match="Timeout"):
            await client.sell_limit("ETH-BTC", limit_price=0.04, base_amount=2.0)


# ===========================================================================
# get_order
# ===========================================================================


class TestGetOrder:
    """Tests for TradingClient.get_order()"""

    @pytest.mark.asyncio
    async def test_get_order_delegates_to_exchange(self, client, exchange):
        """Happy path: order details are fetched from exchange."""
        result = await client.get_order("ord-1")
        assert result["status"] == "FILLED"
        exchange.get_order.assert_awaited_once_with("ord-1")

    @pytest.mark.asyncio
    async def test_get_order_with_different_id(self, client, exchange):
        """Edge case: various order ID formats work."""
        exchange.get_order = AsyncMock(return_value={"order_id": "abc-def", "status": "PENDING"})
        result = await client.get_order("abc-def")
        assert result["order_id"] == "abc-def"

    @pytest.mark.asyncio
    async def test_get_order_exchange_error_propagates(self, client, exchange):
        """Failure: exchange error propagates."""
        exchange.get_order = AsyncMock(side_effect=ValueError("Order not found"))
        with pytest.raises(ValueError, match="Order not found"):
            await client.get_order("nonexistent")


# ===========================================================================
# cancel_order
# ===========================================================================


class TestCancelOrder:
    """Tests for TradingClient.cancel_order()"""

    @pytest.mark.asyncio
    async def test_cancel_order_delegates_to_exchange(self, client, exchange):
        """Happy path: cancel order delegates to exchange."""
        result = await client.cancel_order("ord-1")
        assert result["success"] is True
        exchange.cancel_order.assert_awaited_once_with("ord-1")

    @pytest.mark.asyncio
    async def test_cancel_order_exchange_error_propagates(self, client, exchange):
        """Failure: exchange cancel error propagates."""
        exchange.cancel_order = AsyncMock(side_effect=Exception("Cannot cancel filled order"))
        with pytest.raises(Exception, match="Cannot cancel filled order"):
            await client.cancel_order("filled-order-id")


# ===========================================================================
# invalidate_balance_cache
# ===========================================================================


class TestInvalidateBalanceCache:
    """Tests for TradingClient.invalidate_balance_cache()"""

    @pytest.mark.asyncio
    async def test_invalidate_balance_cache_delegates(self, client, exchange):
        """Happy path: invalidate cache delegates to exchange."""
        await client.invalidate_balance_cache()
        exchange.invalidate_balance_cache.assert_awaited_once()


# ===========================================================================
# get_btc_usd_price
# ===========================================================================


class TestGetBtcUsdPrice:
    """Tests for TradingClient.get_btc_usd_price()"""

    @pytest.mark.asyncio
    async def test_get_btc_usd_price_returns_exchange_price(self, client, exchange):
        """Happy path: BTC price returned from exchange."""
        result = await client.get_btc_usd_price()
        assert result == 65000.0
        exchange.get_btc_usd_price.assert_awaited_once()


# ===========================================================================
# Constructor
# ===========================================================================


class TestTradingClientInit:
    """Tests for TradingClient constructor."""

    def test_init_stores_exchange_reference(self, exchange):
        """Happy path: exchange is stored on the instance."""
        tc = TradingClient(exchange)
        assert tc.exchange is exchange

    def test_init_with_different_exchange_instance(self):
        """Edge case: works with any object (duck typing)."""
        mock_dex = MagicMock()
        tc = TradingClient(mock_dex)
        assert tc.exchange is mock_dex


# ===========================================================================
# Additional error propagation tests
# ===========================================================================


class TestExchangeErrorPropagation:
    """Tests verifying exchange errors propagate through TradingClient."""

    @pytest.mark.asyncio
    async def test_get_balance_btc_exchange_error_propagates(self, client, exchange):
        """Failure: exchange error from get_btc_balance propagates."""
        exchange.get_btc_balance = AsyncMock(side_effect=ConnectionError("API unreachable"))
        with pytest.raises(ConnectionError, match="API unreachable"):
            await client.get_balance("BTC")

    @pytest.mark.asyncio
    async def test_get_balance_usd_exchange_error_propagates(self, client, exchange):
        """Failure: exchange error from get_usd_balance propagates."""
        exchange.get_usd_balance = AsyncMock(side_effect=TimeoutError("Timeout"))
        with pytest.raises(TimeoutError, match="Timeout"):
            await client.get_balance("USD")

    @pytest.mark.asyncio
    async def test_buy_exchange_error_propagates(self, client, exchange):
        """Failure: exchange error during buy propagates."""
        exchange.buy_eth_with_btc = AsyncMock(side_effect=RuntimeError("Insufficient funds"))
        with pytest.raises(RuntimeError, match="Insufficient funds"):
            await client.buy("ETH-BTC", 0.01)

    @pytest.mark.asyncio
    async def test_sell_exchange_error_propagates(self, client, exchange):
        """Failure: exchange error during sell propagates."""
        exchange.sell_for_usd = AsyncMock(side_effect=RuntimeError("Order rejected"))
        with pytest.raises(RuntimeError, match="Order rejected"):
            await client.sell("BTC-USD", 0.1)

    @pytest.mark.asyncio
    async def test_invalidate_balance_cache_error_propagates(self, client, exchange):
        """Failure: exchange error from invalidate_balance_cache propagates."""
        exchange.invalidate_balance_cache = AsyncMock(side_effect=RuntimeError("Cache error"))
        with pytest.raises(RuntimeError, match="Cache error"):
            await client.invalidate_balance_cache()

    @pytest.mark.asyncio
    async def test_get_btc_usd_price_error_propagates(self, client, exchange):
        """Failure: exchange error from get_btc_usd_price propagates."""
        exchange.get_btc_usd_price = AsyncMock(side_effect=ConnectionError("API down"))
        with pytest.raises(ConnectionError, match="API down"):
            await client.get_btc_usd_price()

    @pytest.mark.asyncio
    async def test_get_quote_balance_error_propagates(self, client, exchange):
        """Failure: error from underlying get_balance propagates through get_quote_balance."""
        exchange.get_btc_balance = AsyncMock(side_effect=Exception("Balance unavailable"))
        with pytest.raises(Exception, match="Balance unavailable"):
            await client.get_quote_balance("ETH-BTC")


# ===========================================================================
# Additional edge case tests
# ===========================================================================


class TestAdditionalEdgeCases:
    """Additional edge case tests for comprehensive coverage."""

    @pytest.mark.asyncio
    async def test_sell_btc_pair_non_eth_base(self, client, exchange):
        """Edge case: selling SOL on SOL-BTC pair routes to sell_eth_for_btc."""
        await client.sell("SOL-BTC", 10.0)
        exchange.sell_eth_for_btc.assert_awaited_once_with(
            eth_amount=10.0, product_id="SOL-BTC"
        )

    @pytest.mark.asyncio
    async def test_buy_btc_pair_non_eth_base(self, client, exchange):
        """Edge case: buying on ADA-BTC pair routes to buy_eth_with_btc."""
        await client.buy("ADA-BTC", 0.005)
        exchange.buy_eth_with_btc.assert_awaited_once_with(
            btc_amount=0.005, product_id="ADA-BTC"
        )

    @pytest.mark.asyncio
    async def test_get_quote_balance_usdc_pair(self, client, exchange):
        """Edge case: USDC pair returns USD balance."""
        result = await client.get_quote_balance("ETH-USDC")
        assert result == 10000.0
        exchange.get_usd_balance.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_buy_limit_zero_amount(self, client, exchange):
        """Edge case: zero quote amount is still forwarded (exchange should reject)."""
        await client.buy_limit("ETH-BTC", limit_price=0.05, quote_amount=0.0)
        exchange.create_limit_order.assert_awaited_once_with(
            product_id="ETH-BTC", side="BUY", limit_price=0.05, funds="0.0"
        )

    @pytest.mark.asyncio
    async def test_sell_limit_zero_amount(self, client, exchange):
        """Edge case: zero base amount is still forwarded (exchange should reject)."""
        await client.sell_limit("ETH-BTC", limit_price=0.05, base_amount=0.0)
        exchange.create_limit_order.assert_awaited_once_with(
            product_id="ETH-BTC", side="SELL", limit_price=0.05, size="0.0"
        )

    @pytest.mark.asyncio
    async def test_cancel_order_empty_id(self, client, exchange):
        """Edge case: empty string order ID is still forwarded to exchange."""
        await client.cancel_order("")
        exchange.cancel_order.assert_awaited_once_with("")

    @pytest.mark.asyncio
    async def test_get_balance_empty_string_raises(self, client):
        """Failure: empty string currency raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported quote currency"):
            await client.get_balance("")

    @pytest.mark.asyncio
    async def test_get_balance_lowercase_btc_raises(self, client):
        """Failure: currency matching is case-sensitive - lowercase 'btc' raises."""
        with pytest.raises(ValueError, match="Unsupported quote currency: btc"):
            await client.get_balance("btc")
