"""
Tests for backend/app/coinbase_api/perpetuals_api.py

Covers perpetual futures operations: portfolio summary, positions,
balances, allocation, and product listing.
"""

import pytest
from unittest.mock import AsyncMock

from app.coinbase_api.perpetuals_api import (
    allocate_portfolio,
    get_perps_portfolio_balances,
    get_perps_portfolio_summary,
    get_perps_position,
    list_perps_positions,
    list_perpetual_products,
)


@pytest.fixture(autouse=True)
async def clear_cache():
    """Clear the API cache before each test."""
    from app.cache import api_cache
    await api_cache.clear()
    yield
    await api_cache.clear()


# ---------------------------------------------------------------------------
# get_perps_portfolio_summary
# ---------------------------------------------------------------------------


class TestGetPerpsPortfolioSummary:
    """Tests for get_perps_portfolio_summary()"""

    @pytest.mark.asyncio
    async def test_returns_portfolio_from_nested_key(self):
        """Happy path: extracts portfolio from nested 'portfolio' key."""
        mock_request = AsyncMock(return_value={
            "portfolio": {
                "portfolio_uuid": "port-1",
                "margin_used": "500.00",
                "unrealized_pnl": "-12.50",
            },
        })

        result = await get_perps_portfolio_summary(mock_request, "port-1")
        assert result["margin_used"] == "500.00"

    @pytest.mark.asyncio
    async def test_returns_raw_result_when_no_portfolio_key(self):
        """Edge case: returns raw result when 'portfolio' key is missing."""
        mock_request = AsyncMock(return_value={
            "portfolio_uuid": "port-1",
            "margin_used": "0",
        })

        result = await get_perps_portfolio_summary(mock_request, "port-1")
        assert result["portfolio_uuid"] == "port-1"

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self):
        """Happy path: calls the correct INTX portfolio endpoint."""
        mock_request = AsyncMock(return_value={"portfolio": {}})

        await get_perps_portfolio_summary(mock_request, "uuid-abc")
        mock_request.assert_called_once_with(
            "GET", "/api/v3/brokerage/intx/portfolio/uuid-abc"
        )


# ---------------------------------------------------------------------------
# list_perps_positions
# ---------------------------------------------------------------------------


class TestListPerpsPositions:
    """Tests for list_perps_positions()"""

    @pytest.mark.asyncio
    async def test_returns_positions_list(self):
        """Happy path: returns list of open positions."""
        mock_request = AsyncMock(return_value={
            "positions": [
                {"symbol": "BTC-PERP-INTX", "size": "0.5", "entry_price": "65000"},
                {"symbol": "ETH-PERP-INTX", "size": "5.0", "entry_price": "3500"},
            ],
        })

        result = await list_perps_positions(mock_request, "port-1")
        assert len(result) == 2
        assert result[0]["symbol"] == "BTC-PERP-INTX"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_positions(self):
        """Edge case: returns empty list when 'positions' key is missing."""
        mock_request = AsyncMock(return_value={})

        result = await list_perps_positions(mock_request, "port-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self):
        """Happy path: calls correct positions endpoint."""
        mock_request = AsyncMock(return_value={"positions": []})

        await list_perps_positions(mock_request, "port-uuid")
        mock_request.assert_called_once_with(
            "GET", "/api/v3/brokerage/intx/positions/port-uuid"
        )


# ---------------------------------------------------------------------------
# get_perps_position
# ---------------------------------------------------------------------------


class TestGetPerpsPosition:
    """Tests for get_perps_position()"""

    @pytest.mark.asyncio
    async def test_returns_specific_position(self):
        """Happy path: returns position details for a specific symbol."""
        mock_request = AsyncMock(return_value={
            "position": {
                "symbol": "BTC-PERP-INTX",
                "size": "0.1",
                "unrealized_pnl": "150.00",
                "liquidation_price": "55000",
            },
        })

        result = await get_perps_position(mock_request, "port-1", "BTC-PERP-INTX")
        assert result["unrealized_pnl"] == "150.00"

    @pytest.mark.asyncio
    async def test_returns_raw_when_no_position_key(self):
        """Edge case: returns raw response when 'position' key missing."""
        mock_request = AsyncMock(return_value={
            "symbol": "ETH-PERP-INTX", "size": "0",
        })

        result = await get_perps_position(mock_request, "port-1", "ETH-PERP-INTX")
        assert result["symbol"] == "ETH-PERP-INTX"

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self):
        """Happy path: calls endpoint with portfolio UUID and symbol."""
        mock_request = AsyncMock(return_value={"position": {}})

        await get_perps_position(mock_request, "port-abc", "BTC-PERP-INTX")
        mock_request.assert_called_once_with(
            "GET", "/api/v3/brokerage/intx/positions/port-abc/BTC-PERP-INTX"
        )


# ---------------------------------------------------------------------------
# get_perps_portfolio_balances
# ---------------------------------------------------------------------------


class TestGetPerpsPortfolioBalances:
    """Tests for get_perps_portfolio_balances()"""

    @pytest.mark.asyncio
    async def test_returns_balance_data(self):
        """Happy path: returns balance breakdown."""
        mock_request = AsyncMock(return_value={
            "available_margin": "10000.00",
            "used_margin": "5000.00",
        })

        result = await get_perps_portfolio_balances(mock_request, "port-1")
        assert result["available_margin"] == "10000.00"

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self):
        """Happy path: calls correct balances endpoint."""
        mock_request = AsyncMock(return_value={})

        await get_perps_portfolio_balances(mock_request, "port-xyz")
        mock_request.assert_called_once_with(
            "GET", "/api/v3/brokerage/intx/balances/port-xyz"
        )


# ---------------------------------------------------------------------------
# allocate_portfolio
# ---------------------------------------------------------------------------


class TestAllocatePortfolio:
    """Tests for allocate_portfolio()"""

    @pytest.mark.asyncio
    async def test_allocates_funds(self):
        """Happy path: sends allocation request with correct data."""
        mock_request = AsyncMock(return_value={"success": True})

        result = await allocate_portfolio(
            mock_request, "port-1", "USDC", "1000", "USDC"
        )

        assert result["success"] is True
        call_data = mock_request.call_args[1].get("data") or mock_request.call_args[0][2]
        assert call_data["portfolio_uuid"] == "port-1"
        assert call_data["symbol"] == "USDC"
        assert call_data["amount"] == "1000"
        assert call_data["currency"] == "USDC"

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self):
        """Happy path: calls the INTX allocate endpoint."""
        mock_request = AsyncMock(return_value={})

        await allocate_portfolio(mock_request, "port-1", "USDC", "500", "USDC")
        assert mock_request.call_args[0][1] == "/api/v3/brokerage/intx/allocate"


# ---------------------------------------------------------------------------
# list_perpetual_products
# ---------------------------------------------------------------------------


class TestListPerpetualProducts:
    """Tests for list_perpetual_products()"""

    @pytest.mark.asyncio
    async def test_returns_perpetual_products(self):
        """Happy path: returns filtered perpetual futures products."""
        mock_request = AsyncMock(return_value={
            "products": [
                {"product_id": "BTC-PERP-INTX", "product_type": "FUTURE"},
                {"product_id": "ETH-PERP-INTX", "product_type": "FUTURE"},
            ],
        })

        result = await list_perpetual_products(mock_request)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_passes_correct_filters(self):
        """Edge case: sends product_type and contract_expiry_type params."""
        mock_request = AsyncMock(return_value={"products": []})

        await list_perpetual_products(mock_request)

        call_kwargs = mock_request.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["product_type"] == "FUTURE"
        assert params["contract_expiry_type"] == "PERPETUAL"

    @pytest.mark.asyncio
    async def test_caches_result(self):
        """Edge case: second call returns cached products."""
        mock_request = AsyncMock(return_value={
            "products": [{"product_id": "BTC-PERP-INTX"}],
        })

        result1 = await list_perpetual_products(mock_request)
        result2 = await list_perpetual_products(mock_request)

        assert result1 == result2
        assert mock_request.call_count == 1

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_products(self):
        """Edge case: returns empty list when no perpetual products available."""
        mock_request = AsyncMock(return_value={})

        result = await list_perpetual_products(mock_request)
        assert result == []
