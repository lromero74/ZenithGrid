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
