"""Tests for app/order_validation.py"""

import pytest
from unittest.mock import AsyncMock, patch

from app.order_validation import validate_order_size, calculate_minimum_budget_percentage


# ---------------------------------------------------------------------------
# validate_order_size
# ---------------------------------------------------------------------------

class TestValidateOrderSize:
    @pytest.mark.asyncio
    async def test_valid_quote_amount(self):
        exchange = AsyncMock()
        with patch("app.order_validation.get_product_minimums", new_callable=AsyncMock) as mock_min:
            mock_min.return_value = {
                "quote_min_size": "0.0001",
                "base_min_size": "0.00000001",
                "quote_currency": "BTC",
                "base_currency": "ETH",
            }

            is_valid, error = await validate_order_size(exchange, "ETH-BTC", quote_amount=0.001)

            assert is_valid is True
            assert error is None

    @pytest.mark.asyncio
    async def test_quote_below_minimum_fails(self):
        exchange = AsyncMock()
        with patch("app.order_validation.get_product_minimums", new_callable=AsyncMock) as mock_min:
            mock_min.return_value = {
                "quote_min_size": "0.0001",
                "base_min_size": "0.00000001",
                "quote_currency": "BTC",
                "base_currency": "ETH",
            }

            is_valid, error = await validate_order_size(exchange, "ETH-BTC", quote_amount=0.00001)

            assert is_valid is False
            assert "below minimum" in error

    @pytest.mark.asyncio
    async def test_valid_base_amount(self):
        exchange = AsyncMock()
        with patch("app.order_validation.get_product_minimums", new_callable=AsyncMock) as mock_min:
            mock_min.return_value = {
                "quote_min_size": "1.00",
                "base_min_size": "0.001",
                "quote_currency": "USD",
                "base_currency": "ETH",
            }

            is_valid, error = await validate_order_size(exchange, "ETH-USD", base_amount=0.01)

            assert is_valid is True

    @pytest.mark.asyncio
    async def test_base_below_minimum_fails(self):
        exchange = AsyncMock()
        with patch("app.order_validation.get_product_minimums", new_callable=AsyncMock) as mock_min:
            mock_min.return_value = {
                "quote_min_size": "1.00",
                "base_min_size": "0.001",
                "quote_currency": "USD",
                "base_currency": "ETH",
            }

            is_valid, error = await validate_order_size(exchange, "ETH-USD", base_amount=0.0001)

            assert is_valid is False
            assert "below minimum" in error

    @pytest.mark.asyncio
    async def test_no_amounts_provided_passes(self):
        exchange = AsyncMock()
        with patch("app.order_validation.get_product_minimums", new_callable=AsyncMock) as mock_min:
            mock_min.return_value = {
                "quote_min_size": "0.0001",
                "base_min_size": "0.00000001",
                "quote_currency": "BTC",
                "base_currency": "ETH",
            }

            is_valid, error = await validate_order_size(exchange, "ETH-BTC")

            assert is_valid is True


# ---------------------------------------------------------------------------
# calculate_minimum_budget_percentage
# ---------------------------------------------------------------------------

class TestCalculateMinimumBudgetPercentage:
    @pytest.mark.asyncio
    async def test_calculates_min_percentage(self):
        exchange = AsyncMock()
        with patch("app.order_validation.get_product_minimums", new_callable=AsyncMock) as mock_min:
            mock_min.return_value = {
                "quote_min_size": "0.0001",
                "base_min_size": "0.00000001",
                "quote_currency": "BTC",
            }

            result = await calculate_minimum_budget_percentage(exchange, "ETH-BTC", 0.01)

            # min = 0.0001, balance = 0.01 → 1%
            assert result == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_zero_balance_returns_100(self):
        exchange = AsyncMock()

        result = await calculate_minimum_budget_percentage(exchange, "ETH-BTC", 0.0)

        assert result == 100.0

    @pytest.mark.asyncio
    async def test_negative_balance_returns_100(self):
        exchange = AsyncMock()

        result = await calculate_minimum_budget_percentage(exchange, "ETH-BTC", -1.0)

        assert result == 100.0


# ---------------------------------------------------------------------------
# get_product_minimums — real function with mocked exchange (v2.84.5)
# ---------------------------------------------------------------------------

class TestGetProductMinimumsReal:
    """Tests for get_product_minimums() exercising the real function (not mocked out).

    Covers the quote_currency_id key lookup fix from v2.84.5.
    """

    @pytest.mark.asyncio
    async def test_happy_path_quote_currency_id_used(self):
        """Happy path: exchange returns product with quote_currency_id -> used in minimums."""
        from app.order_validation import get_product_minimums
        from app.cache import api_cache

        # Clear cache so the function actually hits the exchange
        await api_cache.delete("product_minimums_DASH-BTC")

        exchange = AsyncMock()
        exchange.get_product.return_value = {
            "quote_min_size": "0.0001",
            "base_min_size": "0.00000001",
            "quote_currency_id": "BTC",
            "base_currency_id": "DASH",
            "quote_increment": "0.00000001",
            "base_increment": "0.001",
        }

        result = await get_product_minimums(exchange, "DASH-BTC")

        assert result["quote_currency"] == "BTC"
        assert result["base_currency"] == "DASH"
        assert result["quote_min_size"] == "0.0001"
        assert result["base_min_size"] == "0.00000001"

        # Clean up cache
        await api_cache.delete("product_minimums_DASH-BTC")

    @pytest.mark.asyncio
    async def test_fallback_when_exchange_raises_exception(self):
        """Fallback path: exchange raises exception -> uses DEFAULT_MINIMUMS with product_id split."""
        from app.order_validation import get_product_minimums
        from app.cache import api_cache

        await api_cache.delete("product_minimums_ETH-USD")

        exchange = AsyncMock()
        exchange.get_product.side_effect = Exception("Exchange API unavailable")

        result = await get_product_minimums(exchange, "ETH-USD")

        # Should use DEFAULT_MINIMUMS["USD"] with currency from product_id split
        assert result["quote_currency"] == "USD"
        assert result["base_currency"] == "ETH"
        assert result["quote_min_size"] == "1.00"

        await api_cache.delete("product_minimums_ETH-USD")

    @pytest.mark.asyncio
    async def test_fallback_quote_currency_when_no_id_field(self):
        """Edge case: product has quote_currency but NOT quote_currency_id -> falls back."""
        from app.order_validation import get_product_minimums
        from app.cache import api_cache

        await api_cache.delete("product_minimums_SOL-USDT")

        exchange = AsyncMock()
        exchange.get_product.return_value = {
            "quote_min_size": "10.00",
            "base_min_size": "0.01",
            "quote_currency": "USDT",
            "base_currency": "SOL",
            "quote_increment": "0.01",
            "base_increment": "0.01",
        }

        result = await get_product_minimums(exchange, "SOL-USDT")

        # product.get("quote_currency_id", product.get("quote_currency", "BTC"))
        # quote_currency_id is missing, so falls back to quote_currency
        assert result["quote_currency"] == "USDT"
        assert result["base_currency"] == "SOL"

        await api_cache.delete("product_minimums_SOL-USDT")

    @pytest.mark.asyncio
    async def test_fallback_uses_default_btc_for_unknown_quote(self):
        """Edge case: exception path with unknown quote currency uses BTC defaults."""
        from app.order_validation import get_product_minimums
        from app.cache import api_cache

        await api_cache.delete("product_minimums_XYZ-EUR")

        exchange = AsyncMock()
        exchange.get_product.side_effect = Exception("timeout")

        result = await get_product_minimums(exchange, "XYZ-EUR")

        # EUR is not in DEFAULT_MINIMUMS, so falls back to DEFAULT_MINIMUMS["BTC"]
        assert result["quote_currency"] == "EUR"
        assert result["base_currency"] == "XYZ"
        assert result["quote_min_size"] == "0.0001"  # BTC default

        await api_cache.delete("product_minimums_XYZ-EUR")
