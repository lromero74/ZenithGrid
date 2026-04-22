"""
Tests for backend/app/services/paper_valuation_service.py

Covers:
- shared paper-account valuation totals
- negative-cache reuse for unsupported symbols
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


class TestBuildPaperHoldingsAndTotals:
    """Tests for build_paper_holdings_and_totals()."""

    @pytest.mark.asyncio
    async def test_builds_holdings_and_totals_for_mixed_balances(self):
        """Happy path: shared helper returns holdings and totals for mixed assets."""
        from app.services.paper_valuation_service import build_paper_holdings_and_totals

        account = MagicMock()
        account.paper_balances = json.dumps({
            "BTC": 0.1,
            "ETH": 2.0,
            "USDC": 500.0,
        })

        async def fake_price(product_id: str):
            prices = {
                "ETH-USD": 3000.0,
            }
            return prices[product_id]

        with patch(
            "app.services.paper_valuation_service.get_public_btc_usd_price",
            new=AsyncMock(return_value=100000.0),
        ), patch(
            "app.services.paper_valuation_service.get_public_price",
            new=AsyncMock(side_effect=fake_price),
        ):
            result = await build_paper_holdings_and_totals(account)

        assert result["holdings_count"] == 3
        assert result["total_usd_value"] == pytest.approx(16500.0)
        assert result["total_btc_value"] == pytest.approx(0.165)

    @pytest.mark.asyncio
    async def test_unsupported_symbols_use_negative_cache_on_repeat_valuations(self):
        """Failure case: repeated valuations do not re-hit Coinbase for cached 404 pairs."""
        from app.cache import api_cache
        from app.services.paper_valuation_service import build_paper_holdings_and_totals

        account = MagicMock()
        account.paper_balances = json.dumps({"RONIN": 10.0, "USD": 50.0})

        error_response = MagicMock()
        error_response.status_code = 404
        error_response.text = "Not Found"
        http_error = httpx.HTTPStatusError("404", request=MagicMock(), response=error_response)

        async def fake_public_request(endpoint: str, params=None):
            if endpoint.endswith("/BTC-USD/ticker"):
                return {"best_bid": "100000", "best_ask": "100000"}
            raise http_error

        await api_cache.clear()
        try:
            with patch(
                "app.coinbase_api.public_market_data._public_request",
                new=AsyncMock(side_effect=fake_public_request),
            ) as mock_request:
                first = await build_paper_holdings_and_totals(account)
                second = await build_paper_holdings_and_totals(account)

            assert first["total_usd_value"] == pytest.approx(50.0)
            assert second["total_usd_value"] == pytest.approx(50.0)
            assert mock_request.await_count == 3
        finally:
            await api_cache.clear()
