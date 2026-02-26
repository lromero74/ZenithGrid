"""
Tests for backend/app/routers/market_data_router.py

Covers market data endpoints: ticker, batch prices, candles,
products, coins, product precision, orderbook, and BTC/ETH prices.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# =============================================================================
# GET /api/ticker/{product_id}
# =============================================================================


class TestGetTicker:
    """Tests for GET /api/ticker/{product_id}"""

    @pytest.mark.asyncio
    async def test_returns_price(self):
        """Happy path: returns product price."""
        from app.routers.market_data_router import get_ticker

        mock_coinbase = MagicMock()
        mock_coinbase.get_current_price = AsyncMock(return_value=50000.0)

        result = await get_ticker(product_id="BTC-USD", coinbase=mock_coinbase)
        assert result["product_id"] == "BTC-USD"
        assert result["price"] == 50000.0
        assert "time" in result

    @pytest.mark.asyncio
    async def test_exchange_error_returns_500(self):
        """Failure: exchange error returns 500."""
        from fastapi import HTTPException
        from app.routers.market_data_router import get_ticker

        mock_coinbase = MagicMock()
        mock_coinbase.get_current_price = AsyncMock(side_effect=RuntimeError("timeout"))

        with pytest.raises(HTTPException) as exc_info:
            await get_ticker(product_id="BTC-USD", coinbase=mock_coinbase)
        assert exc_info.value.status_code == 500


# =============================================================================
# GET /api/prices/batch
# =============================================================================


class TestGetPricesBatch:
    """Tests for GET /api/prices/batch"""

    @pytest.mark.asyncio
    async def test_returns_multiple_prices(self):
        """Happy path: returns prices for multiple products."""
        from app.routers.market_data_router import get_prices_batch

        mock_coinbase = MagicMock()

        async def mock_price(product_id):
            prices = {"BTC-USD": 50000.0, "ETH-USD": 3000.0}
            return prices.get(product_id, 0)

        mock_coinbase.get_current_price = mock_price

        result = await get_prices_batch(products="BTC-USD,ETH-USD", coinbase=mock_coinbase)
        assert "BTC-USD" in result["prices"]
        assert "ETH-USD" in result["prices"]
        assert result["prices"]["BTC-USD"] == 50000.0

    @pytest.mark.asyncio
    async def test_empty_products_returns_400(self):
        """Failure: empty products string returns 400."""
        from fastapi import HTTPException
        from app.routers.market_data_router import get_prices_batch

        mock_coinbase = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_prices_batch(products="", coinbase=mock_coinbase)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_failed_price_excluded(self):
        """Edge case: products that fail are excluded from results."""
        from app.routers.market_data_router import get_prices_batch

        mock_coinbase = MagicMock()

        async def mock_price(product_id):
            if product_id == "BAD-USD":
                raise Exception("Not found")
            return 50000.0

        mock_coinbase.get_current_price = mock_price

        result = await get_prices_batch(products="BTC-USD,BAD-USD", coinbase=mock_coinbase)
        assert "BTC-USD" in result["prices"]
        assert "BAD-USD" not in result["prices"]


# =============================================================================
# GET /api/candles
# =============================================================================


class TestGetCandles:
    """Tests for GET /api/candles"""

    @pytest.mark.asyncio
    async def test_native_interval_candles(self):
        """Happy path: fetches and formats native interval candles."""
        from app.routers.market_data_router import get_candles, _candle_cache

        # Clear cache to avoid stale data
        _candle_cache._cache.clear()

        mock_coinbase = MagicMock()
        mock_coinbase.get_candles = AsyncMock(return_value=[
            {"start": "1700000600", "open": "0.035", "high": "0.036",
             "low": "0.034", "close": "0.0355", "volume": "100"},
            {"start": "1700000300", "open": "0.034", "high": "0.035",
             "low": "0.033", "close": "0.035", "volume": "150"},
        ])

        result = await get_candles(
            product_id="ETH-BTC",
            granularity="FIVE_MINUTE",
            limit=10,
            coinbase=mock_coinbase,
        )
        assert result["product_id"] == "ETH-BTC"
        assert result["interval"] == "FIVE_MINUTE"
        assert len(result["candles"]) == 2
        # Candles should be in chronological order (reversed)
        assert result["candles"][0]["time"] < result["candles"][1]["time"]

    @pytest.mark.asyncio
    async def test_candles_exchange_error_returns_500(self):
        """Failure: exchange error returns 500."""
        from fastapi import HTTPException
        from app.routers.market_data_router import get_candles, _candle_cache

        _candle_cache._cache.clear()

        mock_coinbase = MagicMock()
        mock_coinbase.get_candles = AsyncMock(side_effect=RuntimeError("API error"))

        with pytest.raises(HTTPException) as exc_info:
            await get_candles(
                product_id="ETH-BTC",
                granularity="ONE_HOUR",
                limit=10,
                coinbase=mock_coinbase,
            )
        assert exc_info.value.status_code == 500


# =============================================================================
# GET /api/product-precision/{product_id}
# =============================================================================


class TestGetProductPrecision:
    """Tests for GET /api/product-precision/{product_id}"""

    @pytest.mark.asyncio
    @patch("app.routers.market_data_router.get_precision_data", create=True)
    async def test_known_product(self, mock_get_precision):
        """Happy path: returns precision data for known product."""
        from app.routers.market_data_router import get_product_precision

        # Mock the import inside the function
        with patch("app.product_precision.get_precision_data", return_value={
            "BTC-USD": {
                "quote_increment": "0.01",
                "quote_decimals": 2,
                "base_increment": "0.00000001",
            }
        }):
            result = await get_product_precision(product_id="BTC-USD")
            assert result["product_id"] == "BTC-USD"
            assert result["quote_increment"] == "0.01"
            assert result["quote_decimals"] == 2

    @pytest.mark.asyncio
    async def test_unknown_product_usd_defaults(self):
        """Edge case: unknown USD product gets USD defaults."""
        from app.routers.market_data_router import get_product_precision

        with patch("app.product_precision.get_precision_data", return_value={}):
            result = await get_product_precision(product_id="NEW-USD")
            assert result["quote_increment"] == "0.01"
            assert result["quote_decimals"] == 2

    @pytest.mark.asyncio
    async def test_unknown_product_btc_defaults(self):
        """Edge case: unknown BTC product gets BTC defaults."""
        from app.routers.market_data_router import get_product_precision

        with patch("app.product_precision.get_precision_data", return_value={}):
            result = await get_product_precision(product_id="ETH-BTC")
            assert result["quote_increment"] == "0.00000001"
            assert result["quote_decimals"] == 8


# =============================================================================
# GET /api/orderbook/{product_id}
# =============================================================================


class TestGetOrderbook:
    """Tests for GET /api/orderbook/{product_id}"""

    def _mock_db_and_user(self, mock_coinbase):
        """Helper: create mock db session and user that return an authenticated exchange client."""
        mock_account = MagicMock()
        mock_account.id = 1

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_account

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_user = MagicMock()
        mock_user.id = 1

        return mock_db, mock_user

    @pytest.mark.asyncio
    @patch("app.routers.market_data_router.get_exchange_client_for_account")
    async def test_returns_formatted_orderbook(self, mock_get_client):
        """Happy path: returns formatted bids and asks."""
        from app.routers.market_data_router import get_orderbook

        mock_coinbase = MagicMock()
        mock_coinbase.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [
                    {"price": "50000", "size": "1.5"},
                    {"price": "49999", "size": "2.0"},
                ],
                "asks": [
                    {"price": "50001", "size": "0.5"},
                    {"price": "50002", "size": "1.0"},
                ],
            }
        })
        mock_get_client.return_value = mock_coinbase
        mock_db, mock_user = self._mock_db_and_user(mock_coinbase)

        result = await get_orderbook(
            product_id="BTC-USD", limit=25, db=mock_db, current_user=mock_user
        )
        assert result["product_id"] == "BTC-USD"
        assert len(result["bids"]) == 2
        assert len(result["asks"]) == 2
        assert result["bids"][0] == [50000.0, 1.5]
        assert result["asks"][0] == [50001.0, 0.5]

    @pytest.mark.asyncio
    @patch("app.routers.market_data_router.get_exchange_client_for_account")
    async def test_filters_zero_price_entries(self, mock_get_client):
        """Edge case: entries with zero price or size are filtered."""
        from app.routers.market_data_router import get_orderbook

        mock_coinbase = MagicMock()
        mock_coinbase.get_product_book = AsyncMock(return_value={
            "pricebook": {
                "bids": [
                    {"price": "0", "size": "1.5"},
                    {"price": "50000", "size": "0"},
                    {"price": "49999", "size": "2.0"},
                ],
                "asks": [],
            }
        })
        mock_get_client.return_value = mock_coinbase
        mock_db, mock_user = self._mock_db_and_user(mock_coinbase)

        result = await get_orderbook(
            product_id="BTC-USD", limit=25, db=mock_db, current_user=mock_user
        )
        assert len(result["bids"]) == 1
        assert result["bids"][0] == [49999.0, 2.0]

    @pytest.mark.asyncio
    @patch("app.routers.market_data_router.get_exchange_client_for_account")
    async def test_exchange_error_returns_500(self, mock_get_client):
        """Failure: exchange error returns 500."""
        from fastapi import HTTPException
        from app.routers.market_data_router import get_orderbook

        mock_coinbase = MagicMock()
        mock_coinbase.get_product_book = AsyncMock(side_effect=RuntimeError("timeout"))
        mock_get_client.return_value = mock_coinbase
        mock_db, mock_user = self._mock_db_and_user(mock_coinbase)

        with pytest.raises(HTTPException) as exc_info:
            await get_orderbook(product_id="BTC-USD", limit=25, db=mock_db, current_user=mock_user)
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_no_account_returns_503(self):
        """Failure: no exchange account configured returns 503."""
        from fastapi import HTTPException
        from app.routers.market_data_router import get_orderbook

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_user = MagicMock()
        mock_user.id = 1

        with pytest.raises(HTTPException) as exc_info:
            await get_orderbook(product_id="BTC-USD", limit=25, db=mock_db, current_user=mock_user)
        assert exc_info.value.status_code == 503


# =============================================================================
# GET /api/market/btc-usd-price
# =============================================================================


class TestGetBtcUsdPrice:
    """Tests for GET /api/market/btc-usd-price"""

    @pytest.mark.asyncio
    async def test_returns_btc_price(self):
        """Happy path: returns BTC/USD price."""
        from app.routers.market_data_router import get_btc_usd_price

        mock_coinbase = MagicMock()
        mock_coinbase.get_btc_usd_price = AsyncMock(return_value=65000.0)

        result = await get_btc_usd_price(coinbase=mock_coinbase)
        assert result["price"] == 65000.0
        assert "time" in result

    @pytest.mark.asyncio
    async def test_error_returns_500(self):
        """Failure: exchange error returns 500."""
        from fastapi import HTTPException
        from app.routers.market_data_router import get_btc_usd_price

        mock_coinbase = MagicMock()
        mock_coinbase.get_btc_usd_price = AsyncMock(side_effect=RuntimeError("api error"))

        with pytest.raises(HTTPException) as exc_info:
            await get_btc_usd_price(coinbase=mock_coinbase)
        assert exc_info.value.status_code == 500


# =============================================================================
# GET /api/market/eth-usd-price
# =============================================================================


class TestGetEthUsdPrice:
    """Tests for GET /api/market/eth-usd-price"""

    @pytest.mark.asyncio
    async def test_returns_eth_price(self):
        """Happy path: returns ETH/USD price."""
        from app.routers.market_data_router import get_eth_usd_price

        mock_coinbase = MagicMock()
        mock_coinbase.get_eth_usd_price = AsyncMock(return_value=3500.0)

        result = await get_eth_usd_price(coinbase=mock_coinbase)
        assert result["price"] == 3500.0
        assert "time" in result


# =============================================================================
# GET /api/coins
# =============================================================================


class TestGetUniqueCoins:
    """Tests for GET /api/coins"""

    @pytest.mark.asyncio
    async def test_returns_unique_coins(self):
        """Happy path: returns unique coin list."""
        from app.routers.market_data_router import get_unique_coins, _market_data_cache

        # Clear cache
        _market_data_cache._cache.clear()

        mock_coinbase = MagicMock()
        mock_coinbase.list_products = AsyncMock(return_value=[
            {"product_id": "ETH-USD", "base_currency_id": "ETH", "status": "online"},
            {"product_id": "ETH-BTC", "base_currency_id": "ETH", "status": "online"},
            {"product_id": "AAVE-USD", "base_currency_id": "AAVE", "status": "online"},
            {"product_id": "DOGE-EUR", "base_currency_id": "DOGE", "status": "online"},  # Excluded: not USD/USDC/BTC
            {"product_id": "SOL-USD", "base_currency_id": "SOL", "status": "offline"},  # Excluded: offline
        ])

        result = await get_unique_coins(coinbase=mock_coinbase)
        assert result["count"] == 2  # ETH (appears in both USD and BTC) + AAVE
        symbols = [c["symbol"] for c in result["coins"]]
        assert "ETH" in symbols
        assert "AAVE" in symbols
        assert "DOGE" not in symbols
        assert "SOL" not in symbols

    @pytest.mark.asyncio
    async def test_exchange_error_returns_500(self):
        """Failure: exchange error returns 500."""
        from fastapi import HTTPException
        from app.routers.market_data_router import get_unique_coins, _market_data_cache

        _market_data_cache._cache.clear()

        mock_coinbase = MagicMock()
        mock_coinbase.list_products = AsyncMock(side_effect=RuntimeError("down"))

        with pytest.raises(HTTPException) as exc_info:
            await get_unique_coins(coinbase=mock_coinbase)
        assert exc_info.value.status_code == 500
