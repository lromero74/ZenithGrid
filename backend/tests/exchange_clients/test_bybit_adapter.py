"""
Tests for backend/app/exchange_clients/bybit_adapter.py

Tests the ByBit adapter that wraps ByBitClient to implement the
ExchangeClient interface. All ByBitClient methods are mocked.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.exchange_clients.bybit_adapter import ByBitAdapter


# =========================================================
# Fixtures
# =========================================================


def _make_mock_bybit_client():
    """Create a fully mocked ByBitClient."""
    client = AsyncMock()
    client.get_wallet_balance = AsyncMock(return_value={
        "result": {
            "list": [{
                "totalEquity": "100000",
                "coin": [
                    {
                        "coin": "USDT",
                        "availableToWithdraw": "50000",
                        "locked": "1000",
                    },
                    {
                        "coin": "BTC",
                        "availableToWithdraw": "0.5",
                        "locked": "0",
                    },
                ],
            }]
        }
    })
    client.get_coin_balance = AsyncMock(return_value={
        "result": {
            "list": [{
                "coin": [
                    {"coin": "USDT", "availableToWithdraw": "50000"},
                ]
            }]
        }
    })
    client.get_instruments_info = AsyncMock(return_value={
        "result": {
            "list": [{
                "symbol": "BTCUSDT",
                "baseCoin": "BTC",
                "quoteCoin": "USDT",
                "status": "Trading",
                "lotSizeFilter": {
                    "minOrderQty": "0.001",
                    "maxOrderQty": "100",
                    "qtyStep": "0.001",
                },
                "priceFilter": {
                    "tickSize": "0.01",
                    "minNotionalValue": "10",
                },
            }]
        }
    })
    client.get_tickers = AsyncMock(return_value={
        "result": {
            "list": [{
                "lastPrice": "50000",
                "bid1Price": "49999",
                "ask1Price": "50001",
                "volume24h": "1000",
                "highPrice24h": "51000",
                "lowPrice24h": "49000",
                "prevPrice24h": "49500",
            }]
        }
    })
    client.get_kline = AsyncMock(return_value={
        "result": {
            "list": [
                ["1700000000000", "50000", "50100", "49900", "50050", "100"],
            ]
        }
    })
    client.normalize_candles = MagicMock(return_value=[
        {"start": "1700000000", "open": "50000", "high": "50100",
         "low": "49900", "close": "50050", "volume": "100"},
    ])
    client.map_granularity = MagicMock(return_value="60")
    client.place_order = AsyncMock(return_value={
        "result": {"orderId": "bb-order-1"},
    })
    client.get_order_history = AsyncMock(return_value={
        "result": {
            "list": [{
                "orderId": "bb-order-1",
                "symbol": "BTCUSDT",
                "side": "Buy",
                "orderType": "Market",
                "orderStatus": "Filled",
                "cumExecQty": "0.1",
                "cumExecValue": "5000",
                "avgPrice": "50000",
                "cumExecFee": "5.0",
                "createdTime": "1700000000000",
            }]
        }
    })
    client.get_open_orders = AsyncMock(return_value={
        "result": {"list": []}
    })
    client.get_positions = AsyncMock(return_value={
        "result": {
            "list": [{
                "symbol": "BTCUSDT",
                "side": "Buy",
                "size": "0.1",
                "avgPrice": "50000",
                "markPrice": "50500",
                "unrealisedPnl": "50",
                "leverage": "5",
                "liqPrice": "45000",
                "takeProfit": "55000",
                "stopLoss": "48000",
            }]
        }
    })
    client.amend_order = AsyncMock(return_value={
        "retCode": 0,
        "retMsg": "OK",
    })
    client.cancel_order = AsyncMock(return_value={
        "result": {"orderId": "bb-order-1"},
    })
    client.cancel_all_orders = AsyncMock(return_value={"retCode": 0})
    return client


# =========================================================
# Initialization & metadata
# =========================================================


class TestByBitAdapterInit:
    """Tests for ByBitAdapter initialization."""

    def test_adapter_exchange_type_is_cex(self):
        """Happy path: exchange type is 'cex'."""
        adapter = ByBitAdapter(_make_mock_bybit_client())
        assert adapter.get_exchange_type() == "cex"

    def test_adapter_stores_client(self):
        """Happy path: stores the underlying client."""
        client = _make_mock_bybit_client()
        adapter = ByBitAdapter(client)
        assert adapter._client is client


# =========================================================
# Account & balance
# =========================================================


class TestByBitBalance:
    """Tests for ByBit balance methods."""

    @pytest.mark.asyncio
    async def test_get_accounts(self):
        """Happy path: parses wallet balance into accounts list."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.get_accounts()
        assert len(result) == 2
        # Check USDT account
        usdt_accts = [a for a in result if a["currency"] == "USDT"]
        assert len(usdt_accts) == 1
        assert usdt_accts[0]["available_balance"]["value"] == "50000"
        assert usdt_accts[0]["uuid"] == "bybit-USDT"

    @pytest.mark.asyncio
    async def test_get_accounts_force_fresh(self):
        """Edge case: force_fresh clears balance cache."""
        client = _make_mock_bybit_client()
        adapter = ByBitAdapter(client)
        adapter._balance_cache = [{"old": "data"}]

        await adapter.get_accounts(force_fresh=True)
        assert adapter._balance_cache is not None  # Re-populated

    @pytest.mark.asyncio
    async def test_get_account_found(self):
        """Happy path: find specific account by uuid."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.get_account("bybit-USDT")
        assert result["currency"] == "USDT"

    @pytest.mark.asyncio
    async def test_get_account_not_found(self):
        """Edge case: account not found returns empty dict."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.get_account("bybit-DOGE")
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_usd_balance(self):
        """Happy path: USD balance maps to USDT."""
        client = _make_mock_bybit_client()
        client.get_coin_balance = AsyncMock(return_value={
            "result": {
                "list": [{"coin": [
                    {"coin": "USDT", "availableToWithdraw": "25000"}
                ]}]
            }
        })
        adapter = ByBitAdapter(client)

        result = await adapter.get_usd_balance()
        assert result == 25000.0

    @pytest.mark.asyncio
    async def test_get_balance_returns_dict(self):
        """Happy path: returns standardized balance dict."""
        client = _make_mock_bybit_client()
        client.get_coin_balance = AsyncMock(return_value={
            "result": {
                "list": [{"coin": [
                    {"coin": "BTC", "availableToWithdraw": "0.75"}
                ]}]
            }
        })
        adapter = ByBitAdapter(client)

        result = await adapter.get_balance("BTC")
        assert result["currency"] == "BTC"
        assert result["available"] == "0.75"

    @pytest.mark.asyncio
    async def test_invalidate_balance_cache(self):
        """Happy path: clears the balance cache."""
        adapter = ByBitAdapter(_make_mock_bybit_client())
        adapter._balance_cache = [{"cached": True}]

        await adapter.invalidate_balance_cache()
        assert adapter._balance_cache is None

    @pytest.mark.asyncio
    async def test_get_equity(self):
        """Happy path: extracts totalEquity from wallet balance."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.get_equity()
        assert result == 100000.0

    @pytest.mark.asyncio
    async def test_calculate_aggregate_usd_value(self):
        """Happy path: aggregate USD uses equity."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.calculate_aggregate_usd_value()
        assert result == 100000.0

    @pytest.mark.asyncio
    async def test_calculate_aggregate_btc_value(self):
        """Happy path: equity / BTC price."""
        client = _make_mock_bybit_client()
        # get_wallet_balance returns equity 100000
        # get_tickers for BTC-USD returns price 50000
        adapter = ByBitAdapter(client)

        result = await adapter.calculate_aggregate_btc_value()
        assert result == pytest.approx(2.0)  # 100000 / 50000


# =========================================================
# Market data
# =========================================================


class TestByBitMarketData:
    """Tests for ByBit market data methods."""

    @pytest.mark.asyncio
    async def test_list_products(self):
        """Happy path: lists instruments with normalized fields."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.list_products()
        assert len(result) == 1
        product = result[0]
        assert product["product_id"] == "BTC-USD"  # from_bybit_symbol("BTCUSDT")
        assert product["base_currency"] == "BTC"
        assert product["quote_currency"] == "USD"  # USDT -> USD normalization
        assert product["status"] == "online"  # Trading -> online

    @pytest.mark.asyncio
    async def test_get_product(self):
        """Happy path: gets single product details."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.get_product("BTC-USD")
        assert result["product_id"] == "BTC-USD"

    @pytest.mark.asyncio
    async def test_get_product_not_found(self):
        """Edge case: product not found returns minimal dict."""
        client = _make_mock_bybit_client()
        client.get_instruments_info = AsyncMock(return_value={
            "result": {"list": []}
        })
        adapter = ByBitAdapter(client)

        result = await adapter.get_product("UNKNOWN-PAIR")
        assert result == {"product_id": "UNKNOWN-PAIR"}

    @pytest.mark.asyncio
    async def test_get_ticker(self):
        """Happy path: returns normalized ticker data."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.get_ticker("BTC-USD")
        assert result["price"] == "50000"
        assert result["bid"] == "49999"
        assert result["ask"] == "50001"
        assert result["volume"] == "1000"

    @pytest.mark.asyncio
    async def test_get_ticker_not_found(self):
        """Edge case: ticker not found returns minimal dict."""
        client = _make_mock_bybit_client()
        client.get_tickers = AsyncMock(return_value={
            "result": {"list": []}
        })
        adapter = ByBitAdapter(client)

        result = await adapter.get_ticker("UNKNOWN-PAIR")
        assert result["price"] == "0"

    @pytest.mark.asyncio
    async def test_get_current_price(self):
        """Happy path: extracts float price from ticker."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.get_current_price("BTC-USD")
        assert result == 50000.0

    @pytest.mark.asyncio
    async def test_get_btc_usd_price(self):
        """Happy path: BTC-USD price."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.get_btc_usd_price()
        assert result == 50000.0

    @pytest.mark.asyncio
    async def test_get_product_stats(self):
        """Happy path: 24hr stats from ticker."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.get_product_stats("BTC-USD")
        assert result["high"] == "51000"
        assert result["low"] == "49000"

    @pytest.mark.asyncio
    async def test_get_candles(self):
        """Happy path: candles are normalized."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.get_candles("BTC-USD", 1000, 2000, "ONE_HOUR")
        assert len(result) == 1
        assert result[0]["close"] == "50050"


# =========================================================
# Order execution
# =========================================================


class TestByBitOrderExecution:
    """Tests for ByBit order methods."""

    @pytest.mark.asyncio
    async def test_create_market_order_with_size(self):
        """Happy path: market order with size."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.create_market_order(
            product_id="BTC-USD",
            side="BUY",
            size="0.1",
        )

        assert result["success"] is True
        assert result["order_id"] == "bb-order-1"
        assert result["filled_size"] == "0.1"

    @pytest.mark.asyncio
    async def test_create_market_order_with_funds(self):
        """Happy path: market order with funds (converts to size)."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.create_market_order(
            product_id="BTC-USD",
            side="BUY",
            funds="5000",
        )

        assert result["success"] is True
        # funds=5000 / price=50000 = 0.1

    @pytest.mark.asyncio
    async def test_create_market_order_no_size_no_funds_raises(self):
        """Failure case: neither size nor funds raises ValueError."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        with pytest.raises(ValueError, match="Either size or funds"):
            await adapter.create_market_order(
                product_id="BTC-USD",
                side="BUY",
            )

    @pytest.mark.asyncio
    async def test_create_market_order_zero_price_raises(self):
        """Failure case: zero price when converting funds raises."""
        client = _make_mock_bybit_client()
        client.get_tickers = AsyncMock(return_value={
            "result": {"list": [{"lastPrice": "0"}]}
        })
        adapter = ByBitAdapter(client)

        with pytest.raises(ValueError, match="Cannot determine qty"):
            await adapter.create_market_order(
                product_id="BTC-USD",
                side="BUY",
                funds="5000",
            )

    @pytest.mark.asyncio
    async def test_create_limit_order(self):
        """Happy path: limit order with size and price."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.create_limit_order(
            product_id="BTC-USD",
            side="BUY",
            limit_price=49000.0,
            size="0.1",
        )

        assert result["success"] is True
        assert result["type"] == "limit"
        assert result["limit_price"] == "49000.0"

    @pytest.mark.asyncio
    async def test_create_limit_order_with_funds(self):
        """Happy path: limit order with funds converts to qty."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.create_limit_order(
            product_id="BTC-USD",
            side="BUY",
            limit_price=50000.0,
            funds="5000",
        )

        assert result["success"] is True
        # funds=5000 / price=50000 = 0.1
        assert result["size"] == str(5000 / 50000)

    @pytest.mark.asyncio
    async def test_create_limit_order_no_size_no_funds_raises(self):
        """Failure case: neither size nor funds raises ValueError."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        with pytest.raises(ValueError, match="Either size or funds"):
            await adapter.create_limit_order(
                product_id="BTC-USD",
                side="BUY",
                limit_price=49000.0,
            )

    @pytest.mark.asyncio
    async def test_get_order_found(self):
        """Happy path: returns normalized order details."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.get_order("bb-order-1")
        assert result["order_id"] == "bb-order-1"
        assert result["status"] == "FILLED"
        assert result["filled_size"] == "0.1"
        assert result["total_fees"] == "5.0"

    @pytest.mark.asyncio
    async def test_get_order_not_found(self):
        """Edge case: order not found returns minimal dict."""
        client = _make_mock_bybit_client()
        client.get_order_history = AsyncMock(return_value={
            "result": {"list": []}
        })
        adapter = ByBitAdapter(client)

        result = await adapter.get_order("unknown-order")
        assert result["status"] == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_cancel_order_found_in_open(self):
        """Happy path: cancel order found in open orders."""
        client = _make_mock_bybit_client()
        client.get_open_orders = AsyncMock(return_value={
            "result": {"list": [
                {"orderId": "bb-order-1", "symbol": "BTCUSDT"}
            ]}
        })
        adapter = ByBitAdapter(client)

        result = await adapter.cancel_order("bb-order-1")
        assert result["success"] is True
        client.cancel_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self):
        """Failure case: order not found in open or history."""
        client = _make_mock_bybit_client()
        client.get_open_orders = AsyncMock(return_value={"result": {"list": []}})
        client.get_order_history = AsyncMock(return_value={"result": {"list": []}})
        adapter = ByBitAdapter(client)

        result = await adapter.cancel_order("unknown-order")
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_edit_order_found(self):
        """Happy path: edit order found in open orders."""
        client = _make_mock_bybit_client()
        client.get_open_orders = AsyncMock(return_value={
            "result": {"list": [
                {"orderId": "bb-order-1", "symbol": "BTCUSDT"}
            ]}
        })
        adapter = ByBitAdapter(client)

        result = await adapter.edit_order("bb-order-1", price="51000")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_edit_order_not_found_raises(self):
        """Failure case: order not in open orders raises ValueError."""
        client = _make_mock_bybit_client()
        client.get_open_orders = AsyncMock(return_value={"result": {"list": []}})
        adapter = ByBitAdapter(client)

        with pytest.raises(ValueError, match="not found in open orders"):
            await adapter.edit_order("unknown-order", price="51000")

    @pytest.mark.asyncio
    async def test_edit_order_api_error(self):
        """Failure case: ByBit API returns error code."""
        client = _make_mock_bybit_client()
        client.get_open_orders = AsyncMock(return_value={
            "result": {"list": [
                {"orderId": "bb-order-1", "symbol": "BTCUSDT"}
            ]}
        })
        client.amend_order = AsyncMock(return_value={
            "retCode": 10001,
            "retMsg": "Invalid parameter",
        })
        adapter = ByBitAdapter(client)

        result = await adapter.edit_order("bb-order-1", price="51000")
        assert "error_response" in result
        assert result["error_response"]["code"] == 10001

    @pytest.mark.asyncio
    async def test_list_orders_open(self):
        """Happy path: listing open orders."""
        client = _make_mock_bybit_client()
        client.get_open_orders = AsyncMock(return_value={
            "result": {"list": [
                {
                    "orderId": "bb-1",
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "orderType": "Limit",
                    "orderStatus": "New",
                    "qty": "0.1",
                    "price": "49000",
                    "cumExecQty": "0",
                    "cumExecValue": "0",
                    "createdTime": "1700000000",
                }
            ]}
        })
        adapter = ByBitAdapter(client)

        result = await adapter.list_orders(order_status=["OPEN"])
        assert len(result) == 1
        assert result[0]["status"] == "OPEN"


# =========================================================
# Status normalization
# =========================================================


class TestNormalizeOrderStatus:
    """Tests for _normalize_order_status static method."""

    def test_filled(self):
        assert ByBitAdapter._normalize_order_status("Filled") == "FILLED"

    def test_new_is_open(self):
        assert ByBitAdapter._normalize_order_status("New") == "OPEN"

    def test_partially_filled_is_open(self):
        assert ByBitAdapter._normalize_order_status("PartiallyFilled") == "OPEN"

    def test_cancelled(self):
        assert ByBitAdapter._normalize_order_status("Cancelled") == "CANCELLED"

    def test_rejected_is_failed(self):
        assert ByBitAdapter._normalize_order_status("Rejected") == "FAILED"

    def test_deactivated_is_cancelled(self):
        assert ByBitAdapter._normalize_order_status("Deactivated") == "CANCELLED"

    def test_untriggered_is_pending(self):
        assert ByBitAdapter._normalize_order_status("Untriggered") == "PENDING"

    def test_triggered_is_open(self):
        assert ByBitAdapter._normalize_order_status("Triggered") == "OPEN"

    def test_unknown_status_uppercased(self):
        """Edge case: unknown status is uppercased."""
        assert ByBitAdapter._normalize_order_status("custom") == "CUSTOM"


# =========================================================
# Connection
# =========================================================


class TestByBitConnection:
    """Tests for connection testing."""

    @pytest.mark.asyncio
    async def test_connection_success(self):
        """Happy path: connection test succeeds."""
        adapter = ByBitAdapter(_make_mock_bybit_client())
        result = await adapter.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_connection_failure(self):
        """Failure case: connection test fails."""
        client = _make_mock_bybit_client()
        client.get_wallet_balance = AsyncMock(
            side_effect=Exception("Connection refused")
        )
        adapter = ByBitAdapter(client)

        result = await adapter.test_connection()
        assert result is False


# =========================================================
# ByBit-specific methods
# =========================================================


class TestByBitSpecificMethods:
    """Tests for ByBit-specific methods."""

    @pytest.mark.asyncio
    async def test_get_positions_info(self):
        """Happy path: returns open positions."""
        adapter = ByBitAdapter(_make_mock_bybit_client())

        result = await adapter.get_positions_info()
        assert len(result) == 1
        pos = result[0]
        assert pos["symbol"] == "BTC-USD"  # from_bybit_symbol("BTCUSDT")
        assert pos["side"] == "Buy"
        assert pos["size"] == "0.1"
        assert pos["entry_price"] == "50000"
        assert pos["unrealized_pnl"] == "50"

    @pytest.mark.asyncio
    async def test_get_positions_info_filters_zero_size(self):
        """Edge case: positions with size 0 are excluded."""
        client = _make_mock_bybit_client()
        client.get_positions = AsyncMock(return_value={
            "result": {"list": [
                {"symbol": "BTCUSDT", "size": "0", "side": "Buy"},
                {"symbol": "ETHUSDT", "size": "5.0", "side": "Sell",
                 "avgPrice": "3000", "markPrice": "3100",
                 "unrealisedPnl": "-500", "leverage": "3",
                 "liqPrice": "3500", "takeProfit": "", "stopLoss": ""},
            ]}
        })
        adapter = ByBitAdapter(client)

        result = await adapter.get_positions_info()
        assert len(result) == 1
        assert result[0]["symbol"] == "ETH-USD"

    @pytest.mark.asyncio
    async def test_close_all_positions(self):
        """Happy path: closes all open positions and cancels orders."""
        client = _make_mock_bybit_client()
        adapter = ByBitAdapter(client)

        await adapter.close_all_positions()

        # Should have placed a closing order for the single position
        client.place_order.assert_called_once()
        call_kwargs = client.place_order.call_args[1]
        assert call_kwargs["side"] == "Sell"  # Reverse of Buy
        assert call_kwargs["reduce_only"] is True
        # Should also cancel all orders
        client.cancel_all_orders.assert_called_once()
