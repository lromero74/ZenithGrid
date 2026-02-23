"""
Tests for backend/app/coinbase_api/transaction_api.py

Covers transaction fetching, pagination, transfer normalization,
and the deposit/withdrawal classification logic.
"""

import pytest
from unittest.mock import AsyncMock

from app.coinbase_api.transaction_api import (
    ALL_TRANSFER_TYPES,
    DEPOSIT_TYPES,
    WITHDRAWAL_TYPES,
    _normalize_transaction,
    get_all_transfers,
    get_transactions,
)


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Tests for module-level transfer type constants."""

    def test_deposit_types_are_defined(self):
        """Happy path: deposit types include expected values."""
        assert "fiat_deposit" in DEPOSIT_TYPES
        assert "exchange_deposit" in DEPOSIT_TYPES
        assert "send" in DEPOSIT_TYPES

    def test_withdrawal_types_are_defined(self):
        """Happy path: withdrawal types include expected values."""
        assert "fiat_withdrawal" in WITHDRAWAL_TYPES
        assert "exchange_withdrawal" in WITHDRAWAL_TYPES

    def test_all_transfer_types_is_union(self):
        """Edge case: ALL_TRANSFER_TYPES is union of deposits and withdrawals."""
        assert ALL_TRANSFER_TYPES == DEPOSIT_TYPES | WITHDRAWAL_TYPES


# ---------------------------------------------------------------------------
# get_transactions
# ---------------------------------------------------------------------------


class TestGetTransactions:
    """Tests for get_transactions()"""

    @pytest.mark.asyncio
    async def test_fetches_transactions(self):
        """Happy path: fetches transactions for an account."""
        mock_request = AsyncMock(return_value={
            "data": [{"id": "txn-1", "type": "fiat_deposit"}],
            "pagination": {"next_uri": None},
        })

        result = await get_transactions(mock_request, "acct-uuid-1")
        assert result["data"][0]["id"] == "txn-1"

    @pytest.mark.asyncio
    async def test_passes_pagination_cursor(self):
        """Edge case: starting_after cursor is appended to URL."""
        mock_request = AsyncMock(return_value={"data": [], "pagination": {}})

        await get_transactions(mock_request, "acct-uuid", starting_after="cursor-abc")
        call_url = mock_request.call_args[0][1]
        assert "starting_after=cursor-abc" in call_url

    @pytest.mark.asyncio
    async def test_custom_limit(self):
        """Edge case: custom limit is reflected in URL."""
        mock_request = AsyncMock(return_value={"data": [], "pagination": {}})

        await get_transactions(mock_request, "acct-uuid", limit=50)
        call_url = mock_request.call_args[0][1]
        assert "limit=50" in call_url


# ---------------------------------------------------------------------------
# _normalize_transaction
# ---------------------------------------------------------------------------


class TestNormalizeTransaction:
    """Tests for _normalize_transaction()"""

    def test_normalizes_fiat_deposit(self):
        """Happy path: normalizes a fiat_deposit correctly."""
        txn = {
            "id": "txn-1",
            "type": "fiat_deposit",
            "amount": {"amount": "100.00", "currency": "USD"},
            "native_amount": {"amount": "100.00", "currency": "USD"},
            "created_at": "2025-01-15T10:00:00Z",
            "status": "completed",
        }

        result = _normalize_transaction(txn)
        assert result is not None
        assert result["external_id"] == "txn-1"
        assert result["transfer_type"] == "deposit"
        assert result["amount"] == 100.0
        assert result["currency"] == "USD"
        assert result["amount_usd"] == 100.0

    def test_normalizes_fiat_withdrawal(self):
        """Happy path: normalizes a fiat_withdrawal."""
        txn = {
            "id": "txn-2",
            "type": "fiat_withdrawal",
            "amount": {"amount": "-500.00", "currency": "USD"},
            "native_amount": {"amount": "-500.00", "currency": "USD"},
            "created_at": "2025-01-16T10:00:00Z",
            "status": "completed",
        }

        result = _normalize_transaction(txn)
        assert result["transfer_type"] == "withdrawal"
        assert result["amount"] == 500.0  # abs value

    def test_send_positive_is_deposit(self):
        """Edge case: 'send' type with positive amount is a deposit."""
        txn = {
            "id": "txn-3",
            "type": "send",
            "amount": {"amount": "0.5", "currency": "BTC"},
            "native_amount": {"amount": "25000.00", "currency": "USD"},
            "created_at": "2025-01-17T10:00:00Z",
            "status": "completed",
        }

        result = _normalize_transaction(txn)
        assert result["transfer_type"] == "deposit"
        assert result["amount"] == 0.5

    def test_send_negative_is_withdrawal(self):
        """Edge case: 'send' type with negative amount is a withdrawal."""
        txn = {
            "id": "txn-4",
            "type": "send",
            "amount": {"amount": "-0.3", "currency": "BTC"},
            "native_amount": {"amount": "-15000.00", "currency": "USD"},
            "created_at": "2025-01-18T10:00:00Z",
            "status": "completed",
        }

        result = _normalize_transaction(txn)
        assert result["transfer_type"] == "withdrawal"
        assert result["amount"] == 0.3
        assert result["amount_usd"] == 15000.0  # abs of native

    def test_returns_none_for_unknown_type(self):
        """Edge case: unrecognized transaction type returns None."""
        txn = {
            "id": "txn-5",
            "type": "trade",
            "amount": {"amount": "1.0", "currency": "BTC"},
            "native_amount": {"amount": "50000", "currency": "USD"},
            "created_at": "2025-01-19T10:00:00Z",
            "status": "completed",
        }

        result = _normalize_transaction(txn)
        assert result is None

    def test_returns_none_for_invalid_amount(self):
        """Failure: returns None when amount is not a valid number."""
        txn = {
            "id": "txn-6",
            "type": "fiat_deposit",
            "amount": {"amount": "not-a-number", "currency": "USD"},
            "native_amount": {"amount": "100", "currency": "USD"},
            "created_at": "2025-01-20T10:00:00Z",
            "status": "completed",
        }

        result = _normalize_transaction(txn)
        assert result is None

    def test_amount_usd_none_for_non_usd_native(self):
        """Edge case: amount_usd is None when native currency is not USD."""
        txn = {
            "id": "txn-7",
            "type": "exchange_deposit",
            "amount": {"amount": "1.0", "currency": "BTC"},
            "native_amount": {"amount": "0.5", "currency": "EUR"},
            "created_at": "2025-01-21T10:00:00Z",
            "status": "completed",
        }

        result = _normalize_transaction(txn)
        assert result is not None
        assert result["amount_usd"] is None

    def test_handles_missing_native_amount(self):
        """Edge case: handles transaction with no native_amount gracefully."""
        txn = {
            "id": "txn-8",
            "type": "exchange_deposit",
            "amount": {"amount": "2.0", "currency": "ETH"},
            "native_amount": {},
            "created_at": "2025-01-22T10:00:00Z",
            "status": "completed",
        }

        result = _normalize_transaction(txn)
        assert result is not None
        assert result["amount_usd"] is None


# ---------------------------------------------------------------------------
# get_all_transfers
# ---------------------------------------------------------------------------


class TestGetAllTransfers:
    """Tests for get_all_transfers()"""

    @pytest.mark.asyncio
    async def test_fetches_and_normalizes_transfers(self):
        """Happy path: fetches transfers and normalizes them."""
        mock_request = AsyncMock(return_value={
            "data": [
                {
                    "id": "txn-1",
                    "type": "fiat_deposit",
                    "amount": {"amount": "1000", "currency": "USD"},
                    "native_amount": {"amount": "1000", "currency": "USD"},
                    "created_at": "2025-06-01T10:00:00Z",
                    "status": "completed",
                },
                {
                    "id": "txn-2",
                    "type": "trade",  # Should be skipped
                    "amount": {"amount": "0.1", "currency": "BTC"},
                    "native_amount": {"amount": "5000", "currency": "USD"},
                    "created_at": "2025-06-01T09:00:00Z",
                    "status": "completed",
                },
            ],
            "pagination": {"next_uri": None, "next_starting_after": None},
        })

        result = await get_all_transfers(mock_request, "acct-uuid")
        assert len(result) == 1
        assert result[0]["transfer_type"] == "deposit"

    @pytest.mark.asyncio
    async def test_paginates_through_pages(self):
        """Happy path: follows pagination cursors."""
        page1 = {
            "data": [
                {
                    "id": "txn-1", "type": "fiat_deposit",
                    "amount": {"amount": "100", "currency": "USD"},
                    "native_amount": {"amount": "100", "currency": "USD"},
                    "created_at": "2025-06-02T10:00:00Z",
                    "status": "completed",
                },
            ],
            "pagination": {
                "next_uri": "/v2/accounts/x/transactions?starting_after=txn-1",
                "next_starting_after": "txn-1",
            },
        }
        page2 = {
            "data": [
                {
                    "id": "txn-2", "type": "fiat_withdrawal",
                    "amount": {"amount": "-200", "currency": "USD"},
                    "native_amount": {"amount": "-200", "currency": "USD"},
                    "created_at": "2025-06-01T10:00:00Z",
                    "status": "completed",
                },
            ],
            "pagination": {"next_uri": None, "next_starting_after": None},
        }
        mock_request = AsyncMock(side_effect=[page1, page2])

        result = await get_all_transfers(mock_request, "acct-uuid")
        assert len(result) == 2
        assert result[0]["transfer_type"] == "deposit"
        assert result[1]["transfer_type"] == "withdrawal"

    @pytest.mark.asyncio
    async def test_stops_at_date_cutoff(self):
        """Edge case: stops paginating once transactions are before since_iso."""
        mock_request = AsyncMock(return_value={
            "data": [
                {
                    "id": "txn-new", "type": "fiat_deposit",
                    "amount": {"amount": "500", "currency": "USD"},
                    "native_amount": {"amount": "500", "currency": "USD"},
                    "created_at": "2025-06-15T10:00:00Z",
                    "status": "completed",
                },
                {
                    "id": "txn-old", "type": "fiat_deposit",
                    "amount": {"amount": "300", "currency": "USD"},
                    "native_amount": {"amount": "300", "currency": "USD"},
                    "created_at": "2025-01-01T10:00:00Z",  # Before cutoff
                    "status": "completed",
                },
            ],
            "pagination": {
                "next_uri": "/v2/accounts/x/transactions?starting_after=txn-old",
                "next_starting_after": "txn-old",
            },
        })

        result = await get_all_transfers(
            mock_request, "acct-uuid", since_iso="2025-03-01T00:00:00Z"
        )

        assert len(result) == 1
        assert result[0]["external_id"] == "txn-new"

    @pytest.mark.asyncio
    async def test_stops_at_max_pages(self):
        """Edge case: respects max_pages safety limit."""
        # Always return data with a next page
        mock_request = AsyncMock(return_value={
            "data": [
                {
                    "id": "txn-x", "type": "fiat_deposit",
                    "amount": {"amount": "10", "currency": "USD"},
                    "native_amount": {"amount": "10", "currency": "USD"},
                    "created_at": "2025-06-01T10:00:00Z",
                    "status": "completed",
                },
            ],
            "pagination": {
                "next_uri": "/v2/accounts/x/transactions?starting_after=txn-x",
                "next_starting_after": "txn-x",
            },
        })

        result = await get_all_transfers(mock_request, "acct-uuid", max_pages=3)
        assert len(result) == 3
        assert mock_request.call_count == 3

    @pytest.mark.asyncio
    async def test_handles_api_failure_gracefully(self):
        """Failure: returns partial results when API call fails mid-pagination."""
        page1 = {
            "data": [
                {
                    "id": "txn-ok", "type": "fiat_deposit",
                    "amount": {"amount": "100", "currency": "USD"},
                    "native_amount": {"amount": "100", "currency": "USD"},
                    "created_at": "2025-06-01T10:00:00Z",
                    "status": "completed",
                },
            ],
            "pagination": {
                "next_uri": "/next",
                "next_starting_after": "txn-ok",
            },
        }
        mock_request = AsyncMock(side_effect=[page1, Exception("API timeout")])

        result = await get_all_transfers(mock_request, "acct-uuid")
        # Should return the one transfer from page 1
        assert len(result) == 1
        assert result[0]["external_id"] == "txn-ok"

    @pytest.mark.asyncio
    async def test_empty_data_stops_pagination(self):
        """Edge case: empty data array stops pagination."""
        mock_request = AsyncMock(return_value={
            "data": [],
            "pagination": {"next_uri": "/should-not-follow"},
        })

        result = await get_all_transfers(mock_request, "acct-uuid")
        assert result == []
        assert mock_request.call_count == 1

    @pytest.mark.asyncio
    async def test_parses_cursor_from_next_uri(self):
        """Edge case: extracts cursor from next_uri when next_starting_after is missing."""
        page1 = {
            "data": [
                {
                    "id": "txn-1", "type": "fiat_deposit",
                    "amount": {"amount": "10", "currency": "USD"},
                    "native_amount": {"amount": "10", "currency": "USD"},
                    "created_at": "2025-06-01T10:00:00Z",
                    "status": "completed",
                },
            ],
            "pagination": {
                "next_uri": "/v2/accounts/x/transactions?starting_after=cursor123&limit=100",
                "next_starting_after": None,
            },
        }
        page2 = {
            "data": [],
            "pagination": {"next_uri": None},
        }
        mock_request = AsyncMock(side_effect=[page1, page2])

        result = await get_all_transfers(mock_request, "acct-uuid")
        assert len(result) == 1
        # Verify the second call used the extracted cursor
        second_call_url = mock_request.call_args_list[1][0][1]
        assert "starting_after=cursor123" in second_call_url
