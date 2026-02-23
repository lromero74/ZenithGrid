"""
Tests for backend/app/coinbase_api/order_api.py

Covers order creation (market, limit, bracket, stop-limit),
order management (get, cancel, edit, list), and convenience trading methods.
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.coinbase_api.order_api import (
    buy_eth_with_btc,
    buy_with_usd,
    cancel_order,
    create_bracket_order,
    create_limit_order,
    create_market_order,
    create_stop_limit_order,
    edit_order,
    edit_order_preview,
    get_order,
    list_orders,
    sell_eth_for_btc,
    sell_for_usd,
)


# ---------------------------------------------------------------------------
# create_market_order
# ---------------------------------------------------------------------------


class TestCreateMarketOrder:
    """Tests for create_market_order()"""

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.time.time", return_value=1700000.000)
    async def test_buy_with_size(self, mock_time):
        """Happy path: creates market buy with base_size."""
        mock_request = AsyncMock(return_value={"success": True, "order_id": "ord-1"})

        result = await create_market_order(mock_request, "ETH-BTC", "BUY", size="1.5")

        assert result["success"] is True
        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        assert call_data["side"] == "BUY"
        assert call_data["product_id"] == "ETH-BTC"
        assert "base_size" in call_data["order_configuration"]["market_market_ioc"]

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.time.time", return_value=1700000.000)
    async def test_buy_with_funds(self, mock_time):
        """Happy path: creates market buy with quote_size (funds)."""
        mock_request = AsyncMock(return_value={"success": True})

        await create_market_order(mock_request, "ETH-BTC", "BUY", funds="0.01")

        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        assert "quote_size" in call_data["order_configuration"]["market_market_ioc"]

    @pytest.mark.asyncio
    async def test_raises_without_size_or_funds(self):
        """Failure: raises ValueError when neither size nor funds specified."""
        mock_request = AsyncMock()

        with pytest.raises(ValueError, match="Must specify either size or funds"):
            await create_market_order(mock_request, "ETH-BTC", "BUY")

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.time.time", return_value=1700000.123)
    async def test_client_order_id_is_timestamp(self, mock_time):
        """Edge case: client_order_id is derived from timestamp."""
        mock_request = AsyncMock(return_value={})

        await create_market_order(mock_request, "ETH-BTC", "SELL", size="1.0")

        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        assert call_data["client_order_id"] == str(int(1700000.123 * 1000))


# ---------------------------------------------------------------------------
# create_limit_order
# ---------------------------------------------------------------------------


class TestCreateLimitOrder:
    """Tests for create_limit_order()"""

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.time.time", return_value=1700000.000)
    async def test_gtc_limit_order_with_size(self, mock_time):
        """Happy path: creates GTC limit order with base_size."""
        mock_request = AsyncMock(return_value={"success": True})

        result = await create_limit_order(
            mock_request, "ETH-BTC", "BUY", limit_price=0.05, size="10.0"
        )

        assert result["success"] is True
        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        config = call_data["order_configuration"]
        assert "limit_limit_gtc" in config
        assert "base_size" in config["limit_limit_gtc"]

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.time.time", return_value=1700000.000)
    async def test_gtd_limit_order_with_end_time(self, mock_time):
        """Happy path: creates GTD limit order with end_time."""
        from datetime import datetime

        end = datetime(2025, 12, 31, 23, 59, 59)
        mock_request = AsyncMock(return_value={"success": True})

        await create_limit_order(
            mock_request, "ETH-BTC", "BUY", limit_price=0.05,
            size="5.0", time_in_force="gtd", end_time=end,
        )

        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        config = call_data["order_configuration"]
        assert "limit_limit_gtd" in config
        assert config["limit_limit_gtd"]["end_time"] == "2025-12-31T23:59:59Z"

    @pytest.mark.asyncio
    async def test_gtd_without_end_time_raises(self):
        """Failure: GTD order without end_time raises ValueError."""
        mock_request = AsyncMock()

        with pytest.raises(ValueError, match="end_time is required for GTD orders"):
            await create_limit_order(
                mock_request, "ETH-BTC", "BUY", limit_price=0.05,
                size="5.0", time_in_force="gtd",
            )

    @pytest.mark.asyncio
    async def test_raises_without_size_or_funds(self):
        """Failure: raises ValueError when neither size nor funds specified."""
        mock_request = AsyncMock()

        with pytest.raises(ValueError, match="Must specify either size or funds"):
            await create_limit_order(
                mock_request, "ETH-BTC", "BUY", limit_price=0.05,
            )

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.time.time", return_value=1700000.000)
    async def test_limit_order_with_funds_calculates_base_size(self, mock_time):
        """Edge case: funds are converted to base_size using limit price."""
        mock_request = AsyncMock(return_value={"success": True})

        await create_limit_order(
            mock_request, "ETH-BTC", "BUY", limit_price=0.05, funds="0.5",
        )

        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        config = call_data["order_configuration"]["limit_limit_gtc"]
        # 0.5 / 0.05 = 10.0
        base_size = float(config["base_size"])
        assert base_size == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# get_order
# ---------------------------------------------------------------------------


class TestGetOrder:
    """Tests for get_order()"""

    @pytest.mark.asyncio
    async def test_returns_order_from_nested_key(self):
        """Happy path: extracts order from nested 'order' key."""
        mock_request = AsyncMock(return_value={
            "order": {"order_id": "abc", "status": "FILLED"},
        })

        result = await get_order(mock_request, "hmac", "abc")
        assert result["status"] == "FILLED"

    @pytest.mark.asyncio
    async def test_returns_raw_result_when_no_order_key(self):
        """Edge case: returns raw result when 'order' key is missing."""
        mock_request = AsyncMock(return_value={
            "order_id": "abc", "status": "PENDING",
        })

        result = await get_order(mock_request, "cdp", "abc")
        assert result["status"] == "PENDING"


# ---------------------------------------------------------------------------
# cancel_order
# ---------------------------------------------------------------------------


class TestCancelOrder:
    """Tests for cancel_order()"""

    @pytest.mark.asyncio
    async def test_sends_batch_cancel_request(self):
        """Happy path: sends order_id in batch_cancel format."""
        mock_request = AsyncMock(return_value={
            "results": [{"success": True, "order_id": "ord-1"}],
        })

        result = await cancel_order(mock_request, "ord-1")
        assert result["results"][0]["success"] is True

        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        assert call_data["order_ids"] == ["ord-1"]


# ---------------------------------------------------------------------------
# edit_order / edit_order_preview
# ---------------------------------------------------------------------------


class TestEditOrder:
    """Tests for edit_order()"""

    @pytest.mark.asyncio
    async def test_edit_price(self):
        """Happy path: edits order price."""
        mock_request = AsyncMock(return_value={"success": True})

        result = await edit_order(mock_request, "ord-1", price="0.06")
        assert result["success"] is True

        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        assert call_data["price"] == "0.06"
        assert "size" not in call_data

    @pytest.mark.asyncio
    async def test_edit_size(self):
        """Happy path: edits order size."""
        mock_request = AsyncMock(return_value={"success": True})

        await edit_order(mock_request, "ord-1", size="5.0")
        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        assert call_data["size"] == "5.0"

    @pytest.mark.asyncio
    async def test_raises_without_price_or_size(self):
        """Failure: raises ValueError when neither price nor size given."""
        mock_request = AsyncMock()

        with pytest.raises(ValueError, match="Must specify either price or size to edit"):
            await edit_order(mock_request, "ord-1")


class TestEditOrderPreview:
    """Tests for edit_order_preview()"""

    @pytest.mark.asyncio
    async def test_preview_with_price(self):
        """Happy path: previews order edit with new price."""
        mock_request = AsyncMock(return_value={"slippage": "0.01"})

        result = await edit_order_preview(mock_request, "ord-1", price="0.07")
        assert result["slippage"] == "0.01"

    @pytest.mark.asyncio
    async def test_raises_without_price_or_size(self):
        """Failure: raises ValueError."""
        mock_request = AsyncMock()

        with pytest.raises(ValueError, match="Must specify either price or size to preview"):
            await edit_order_preview(mock_request, "ord-1")


# ---------------------------------------------------------------------------
# list_orders
# ---------------------------------------------------------------------------


class TestListOrders:
    """Tests for list_orders()"""

    @pytest.mark.asyncio
    async def test_returns_order_list(self):
        """Happy path: returns list of orders."""
        mock_request = AsyncMock(return_value={
            "orders": [
                {"order_id": "1", "status": "OPEN"},
                {"order_id": "2", "status": "FILLED"},
            ],
        })

        result = await list_orders(mock_request)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_filters_by_product_and_status(self):
        """Edge case: passes product_id and order_status filters."""
        mock_request = AsyncMock(return_value={"orders": []})

        await list_orders(
            mock_request, product_id="ETH-BTC", order_status=["OPEN"], limit=50
        )

        call_kwargs = mock_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["product_id"] == "ETH-BTC"
        assert params["order_status"] == ["OPEN"]
        assert params["limit"] == 50

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_orders_key(self):
        """Edge case: returns empty list when response has no orders key."""
        mock_request = AsyncMock(return_value={})

        result = await list_orders(mock_request)
        assert result == []


# ---------------------------------------------------------------------------
# create_bracket_order
# ---------------------------------------------------------------------------


class TestCreateBracketOrder:
    """Tests for create_bracket_order()"""

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.time.time", return_value=1700000.000)
    async def test_market_entry_with_tp_sl(self, mock_time):
        """Happy path: creates market entry with attached TP and SL."""
        mock_request = AsyncMock(return_value={"order_id": "bracket-1"})

        result = await create_bracket_order(
            mock_request,
            product_id="BTC-PERP-INTX",
            side="BUY",
            base_size="0.01",
            tp_price="70000",
            sl_price="60000",
            leverage="3",
            margin_type="CROSS",
        )

        assert result["order_id"] == "bracket-1"
        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        assert "market_market_ioc" in call_data["order_configuration"]
        assert call_data["leverage"] == "3"
        assert call_data["margin_type"] == "CROSS"
        bracket = call_data["attached_order_configuration"]["trigger_bracket_gtc"]
        assert bracket["limit_price"] == "70000"
        assert bracket["stop_trigger_price"] == "60000"

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.time.time", return_value=1700000.000)
    async def test_limit_entry_with_bracket(self, mock_time):
        """Edge case: limit entry with bracket orders."""
        mock_request = AsyncMock(return_value={})

        await create_bracket_order(
            mock_request,
            product_id="BTC-PERP-INTX",
            side="BUY",
            base_size="0.01",
            limit_price="65000",
            tp_price="70000",
        )

        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        assert "limit_limit_gtc" in call_data["order_configuration"]

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.time.time", return_value=1700000.000)
    async def test_no_bracket_when_no_tp_sl(self, mock_time):
        """Edge case: no attached_order_configuration when neither TP nor SL set."""
        mock_request = AsyncMock(return_value={})

        await create_bracket_order(
            mock_request, "BTC-PERP-INTX", "BUY", "0.01",
        )

        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        assert "attached_order_configuration" not in call_data


# ---------------------------------------------------------------------------
# create_stop_limit_order
# ---------------------------------------------------------------------------


class TestCreateStopLimitOrder:
    """Tests for create_stop_limit_order()"""

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.time.time", return_value=1700000.000)
    async def test_creates_stop_limit_order(self, mock_time):
        """Happy path: creates stop-limit order with correct structure."""
        mock_request = AsyncMock(return_value={"order_id": "sl-1"})

        result = await create_stop_limit_order(
            mock_request, "BTC-PERP-INTX", "SELL", "0.01", "60000", "59500",
        )

        assert result["order_id"] == "sl-1"
        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        config = call_data["order_configuration"]["stop_limit_stop_limit_gtc"]
        assert config["stop_price"] == "60000"
        assert config["limit_price"] == "59500"
        assert config["base_size"] == "0.01"


# ---------------------------------------------------------------------------
# Convenience trading methods
# ---------------------------------------------------------------------------


class TestConvenienceTradingMethods:
    """Tests for buy_eth_with_btc(), sell_eth_for_btc(), buy_with_usd(), sell_for_usd()"""

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.time.time", return_value=1700000.000)
    async def test_buy_eth_with_btc(self, mock_time):
        """Happy path: buys ETH with specified BTC amount."""
        mock_request = AsyncMock(return_value={"order_id": "buy-1"})

        result = await buy_eth_with_btc(mock_request, 0.01)
        assert result["order_id"] == "buy-1"

        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        assert call_data["side"] == "BUY"
        assert call_data["product_id"] == "ETH-BTC"

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.time.time", return_value=1700000.000)
    async def test_buy_eth_with_btc_custom_product(self, mock_time):
        """Edge case: supports custom product_id (e.g., AAVE-BTC)."""
        mock_request = AsyncMock(return_value={})

        await buy_eth_with_btc(mock_request, 0.005, product_id="AAVE-BTC")
        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        assert call_data["product_id"] == "AAVE-BTC"

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.time.time", return_value=1700000.000)
    async def test_sell_eth_for_btc(self, mock_time):
        """Happy path: sells ETH for BTC."""
        mock_request = AsyncMock(return_value={"order_id": "sell-1"})

        result = await sell_eth_for_btc(mock_request, 5.0)
        assert result["order_id"] == "sell-1"

        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        assert call_data["side"] == "SELL"

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.time.time", return_value=1700000.000)
    async def test_buy_with_usd(self, mock_time):
        """Happy path: buys crypto with USD."""
        mock_request = AsyncMock(return_value={})

        await buy_with_usd(mock_request, 100.0, "ETH-USD")
        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        assert call_data["side"] == "BUY"
        assert call_data["product_id"] == "ETH-USD"

    @pytest.mark.asyncio
    @patch("app.coinbase_api.order_api.time.time", return_value=1700000.000)
    async def test_sell_for_usd(self, mock_time):
        """Happy path: sells crypto for USD."""
        mock_request = AsyncMock(return_value={})

        await sell_for_usd(mock_request, 2.5, "ETH-USD")
        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        assert call_data["side"] == "SELL"
        assert call_data["product_id"] == "ETH-USD"
