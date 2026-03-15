"""
Tests for backend/app/coinbase_api/convert_api.py

Covers:
- create_convert_quote: constructs correct request payload and URL
- commit_convert_trade: constructs correct request payload and URL with trade_id
- Error propagation from request_func
- Edge cases: empty strings, special characters in IDs
"""

import pytest
from unittest.mock import AsyncMock

from app.coinbase_api.convert_api import create_convert_quote, commit_convert_trade


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request_func(return_value=None, side_effect=None):
    """Create a mock request function with optional return value or side effect."""
    mock = AsyncMock()
    if side_effect:
        mock.side_effect = side_effect
    else:
        mock.return_value = return_value or {"trade": {"id": "trade-123"}}
    return mock


# ---------------------------------------------------------------------------
# create_convert_quote
# ---------------------------------------------------------------------------


class TestCreateConvertQuote:
    """Tests for create_convert_quote()"""

    @pytest.mark.asyncio
    async def test_create_quote_happy_path(self):
        """Happy path: should call request_func with correct method, URL, and data."""
        expected_response = {
            "trade": {
                "id": "trade-abc-123",
                "status": "PENDING",
                "user_entered_amount": {"value": "100.00", "currency": "USD"},
            }
        }
        request_func = _make_request_func(return_value=expected_response)

        result = await create_convert_quote(
            request_func,
            from_account="acct-usd-001",
            to_account="acct-usdc-002",
            amount="100.00",
        )

        request_func.assert_called_once_with(
            "POST",
            "/api/v3/brokerage/convert/quote",
            data={
                "from_account": "acct-usd-001",
                "to_account": "acct-usdc-002",
                "amount": "100.00",
            },
        )
        assert result == expected_response

    @pytest.mark.asyncio
    async def test_create_quote_returns_response_directly(self):
        """Happy path: should return whatever request_func returns."""
        request_func = _make_request_func(return_value={"custom": "data"})

        result = await create_convert_quote(
            request_func, "acct-a", "acct-b", "50.00"
        )

        assert result == {"custom": "data"}

    @pytest.mark.asyncio
    async def test_create_quote_uses_post_method(self):
        """Happy path: should always use POST."""
        request_func = _make_request_func()

        await create_convert_quote(request_func, "a", "b", "1")

        args = request_func.call_args
        assert args[0][0] == "POST"

    @pytest.mark.asyncio
    async def test_create_quote_correct_endpoint(self):
        """Happy path: should target the convert/quote endpoint."""
        request_func = _make_request_func()

        await create_convert_quote(request_func, "a", "b", "1")

        args = request_func.call_args
        assert args[0][1] == "/api/v3/brokerage/convert/quote"

    @pytest.mark.asyncio
    async def test_create_quote_propagates_exception(self):
        """Failure: should propagate any exception from request_func."""
        request_func = _make_request_func(
            side_effect=Exception("API rate limit exceeded")
        )

        with pytest.raises(Exception, match="API rate limit exceeded"):
            await create_convert_quote(request_func, "a", "b", "100")

    @pytest.mark.asyncio
    async def test_create_quote_with_fractional_amount(self):
        """Edge case: amount with many decimal places."""
        request_func = _make_request_func()

        await create_convert_quote(
            request_func, "acct-1", "acct-2", "0.00000001"
        )

        data = request_func.call_args[1]["data"]
        assert data["amount"] == "0.00000001"

    @pytest.mark.asyncio
    async def test_create_quote_with_large_amount(self):
        """Edge case: very large conversion amount."""
        request_func = _make_request_func()

        await create_convert_quote(
            request_func, "acct-1", "acct-2", "9999999.99"
        )

        data = request_func.call_args[1]["data"]
        assert data["amount"] == "9999999.99"

    @pytest.mark.asyncio
    async def test_create_quote_with_empty_amount(self):
        """Edge case: empty string amount -- passes through, server validates."""
        request_func = _make_request_func()

        await create_convert_quote(request_func, "a", "b", "")

        data = request_func.call_args[1]["data"]
        assert data["amount"] == ""


# ---------------------------------------------------------------------------
# commit_convert_trade
# ---------------------------------------------------------------------------


class TestCommitConvertTrade:
    """Tests for commit_convert_trade()"""

    @pytest.mark.asyncio
    async def test_commit_trade_happy_path(self):
        """Happy path: should call request_func with correct method, URL, and data."""
        expected_response = {
            "trade": {
                "id": "trade-abc-123",
                "status": "COMPLETED",
            }
        }
        request_func = _make_request_func(return_value=expected_response)

        result = await commit_convert_trade(
            request_func,
            trade_id="trade-abc-123",
            from_account="acct-usd-001",
            to_account="acct-usdc-002",
        )

        request_func.assert_called_once_with(
            "POST",
            "/api/v3/brokerage/convert/trade/trade-abc-123",
            data={
                "from_account": "acct-usd-001",
                "to_account": "acct-usdc-002",
            },
        )
        assert result == expected_response

    @pytest.mark.asyncio
    async def test_commit_trade_url_contains_trade_id(self):
        """Happy path: URL should embed the trade_id."""
        request_func = _make_request_func()

        await commit_convert_trade(
            request_func,
            trade_id="my-trade-xyz",
            from_account="a",
            to_account="b",
        )

        url = request_func.call_args[0][1]
        assert "my-trade-xyz" in url
        assert url == "/api/v3/brokerage/convert/trade/my-trade-xyz"

    @pytest.mark.asyncio
    async def test_commit_trade_does_not_include_amount(self):
        """Edge case: commit payload should NOT include amount (only quote has it)."""
        request_func = _make_request_func()

        await commit_convert_trade(request_func, "tid", "a", "b")

        data = request_func.call_args[1]["data"]
        assert "amount" not in data

    @pytest.mark.asyncio
    async def test_commit_trade_propagates_exception(self):
        """Failure: should propagate errors from request_func."""
        request_func = _make_request_func(
            side_effect=ValueError("Invalid trade_id")
        )

        with pytest.raises(ValueError, match="Invalid trade_id"):
            await commit_convert_trade(request_func, "bad-id", "a", "b")

    @pytest.mark.asyncio
    async def test_commit_trade_with_uuid_trade_id(self):
        """Happy path: typical UUID-style trade_id."""
        request_func = _make_request_func()
        tid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        await commit_convert_trade(request_func, tid, "acct-1", "acct-2")

        url = request_func.call_args[0][1]
        assert url.endswith(tid)

    @pytest.mark.asyncio
    async def test_commit_trade_uses_post_method(self):
        """Happy path: should always use POST."""
        request_func = _make_request_func()

        await commit_convert_trade(request_func, "tid", "a", "b")

        assert request_func.call_args[0][0] == "POST"

    @pytest.mark.asyncio
    async def test_commit_trade_returns_response_directly(self):
        """Happy path: should return whatever request_func returns."""
        request_func = _make_request_func(return_value={"status": "ok"})

        result = await commit_convert_trade(request_func, "tid", "a", "b")

        assert result == {"status": "ok"}


# ---------------------------------------------------------------------------
# Integration-like: full two-step flow
# ---------------------------------------------------------------------------


class TestConvertFlow:
    """Tests simulating the full quote-then-commit flow."""

    @pytest.mark.asyncio
    async def test_full_convert_flow(self):
        """Happy path: create quote then commit using the returned trade_id."""
        quote_response = {"trade": {"id": "trade-999", "status": "PENDING"}}
        commit_response = {"trade": {"id": "trade-999", "status": "COMPLETED"}}

        request_func = AsyncMock(side_effect=[quote_response, commit_response])

        # Step 1: Quote
        quote = await create_convert_quote(
            request_func, "acct-usd", "acct-usdc", "500.00"
        )
        trade_id = quote["trade"]["id"]

        # Step 2: Commit
        result = await commit_convert_trade(
            request_func, trade_id, "acct-usd", "acct-usdc"
        )

        assert result["trade"]["status"] == "COMPLETED"
        assert request_func.call_count == 2
