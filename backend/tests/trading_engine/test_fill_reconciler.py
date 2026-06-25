"""
Tests for backend/app/trading_engine/fill_reconciler.py

Covers:
- reconcile_order_fill: retry logic, BTC fee adjustment, precision rounding,
  fallback handling, zero fill handling
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.trading_engine.fill_reconciler import (
    FillData,
    reconcile_order_fill,
)


# =============================================================================
# reconcile_order_fill
# =============================================================================


class TestReconcileOrderFill:
    """Tests for reconcile_order_fill()."""

    @pytest.mark.asyncio
    async def test_successful_fill_first_attempt(self):
        """Happy path: order fills on first attempt, returns fill data."""
        exchange = AsyncMock()
        exchange.get_order.return_value = {
            "filled_size": "0.01",
            "filled_value": "500.00",
            "average_filled_price": "50000.00",
            "total_fees": "2.50",
        }

        result = await reconcile_order_fill(
            exchange=exchange,
            order_id="order-123",
            product_id="BTC-USD",
            max_retries=3,
        )

        assert isinstance(result, FillData)
        assert result.filled_size == pytest.approx(0.01)
        assert result.filled_value == pytest.approx(500.0)
        assert result.average_price == pytest.approx(50000.0)
        assert result.total_fees == pytest.approx(2.5)
        exchange.get_order.assert_called_once_with("order-123")

    @pytest.mark.asyncio
    async def test_fill_on_retry(self):
        """Happy path: order fills on second attempt after first returns zeros."""
        exchange = AsyncMock()
        exchange.get_order.side_effect = [
            # First attempt: not filled yet
            {
                "filled_size": "0",
                "filled_value": "0",
                "average_filled_price": "0",
                "total_fees": "0",
            },
            # Second attempt: filled
            {
                "filled_size": "0.05",
                "filled_value": "2500.00",
                "average_filled_price": "50000.00",
                "total_fees": "12.50",
            },
        ]

        with patch("app.trading_engine.fill_reconciler.asyncio.sleep", new_callable=AsyncMock):
            result = await reconcile_order_fill(
                exchange=exchange,
                order_id="order-456",
                product_id="BTC-USD",
                max_retries=3,
            )

        assert result.filled_size == pytest.approx(0.05)
        assert exchange.get_order.call_count == 2

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_returns_zeros(self):
        """Failure: all retries return zero amounts, returns zero FillData."""
        exchange = AsyncMock()
        exchange.get_order.return_value = {
            "filled_size": "0",
            "filled_value": "0",
            "average_filled_price": "0",
            "total_fees": "0",
        }

        with patch("app.trading_engine.fill_reconciler.asyncio.sleep", new_callable=AsyncMock):
            result = await reconcile_order_fill(
                exchange=exchange,
                order_id="order-789",
                product_id="BTC-USD",
                max_retries=2,
            )

        assert result.filled_size == 0.0
        assert result.filled_value == 0.0
        assert result.average_price == 0.0
        assert result.total_fees == 0.0

    @pytest.mark.asyncio
    async def test_get_order_exception_retries(self):
        """Failure: get_order raises exception, retries, then succeeds."""
        exchange = AsyncMock()
        exchange.get_order.side_effect = [
            Exception("Network error"),
            {
                "filled_size": "1.0",
                "filled_value": "50000.00",
                "average_filled_price": "50000.00",
                "total_fees": "25.00",
            },
        ]

        with patch("app.trading_engine.fill_reconciler.asyncio.sleep", new_callable=AsyncMock):
            result = await reconcile_order_fill(
                exchange=exchange,
                order_id="order-err",
                product_id="BTC-USD",
                max_retries=3,
            )

        assert result.filled_size == pytest.approx(1.0)
        assert exchange.get_order.call_count == 2

    @pytest.mark.asyncio
    async def test_all_retries_get_order_exceptions(self):
        """Failure: all get_order calls raise exceptions, returns zeros."""
        exchange = AsyncMock()
        exchange.get_order.side_effect = Exception("Persistent network error")

        with patch("app.trading_engine.fill_reconciler.asyncio.sleep", new_callable=AsyncMock):
            result = await reconcile_order_fill(
                exchange=exchange,
                order_id="order-dead",
                product_id="BTC-USD",
                max_retries=2,
            )

        assert result.filled_size == 0.0
        assert result.filled_value == 0.0

    @pytest.mark.asyncio
    async def test_btc_pair_fee_adjustment(self):
        """Happy path: BTC pair fee adjustment deducts fees from base amount."""
        exchange = AsyncMock()
        exchange.get_order.return_value = {
            "filled_size": "10.0",
            "filled_value": "0.5",
            "average_filled_price": "0.05",
            "total_fees": "0.005",
        }

        result = await reconcile_order_fill(
            exchange=exchange,
            order_id="order-btc",
            product_id="ETH-BTC",
            max_retries=1,
            adjust_btc_fees=True,
        )

        # fee_rate = 0.005 / 0.5 = 0.01 (1%)
        # fee_in_base = 10.0 * 0.01 = 0.1
        # actual_base = 10.0 - 0.1 = 9.9
        assert result.filled_size == pytest.approx(9.9)

    @pytest.mark.asyncio
    async def test_btc_fee_adjustment_not_applied_to_usd_pair(self):
        """Edge case: adjust_btc_fees=True but USD pair skips adjustment."""
        exchange = AsyncMock()
        exchange.get_order.return_value = {
            "filled_size": "0.01",
            "filled_value": "500.00",
            "average_filled_price": "50000.00",
            "total_fees": "2.50",
        }

        result = await reconcile_order_fill(
            exchange=exchange,
            order_id="order-usd",
            product_id="BTC-USD",
            max_retries=1,
            adjust_btc_fees=True,
        )

        # Not a BTC pair, so no adjustment
        assert result.filled_size == pytest.approx(0.01)

    @pytest.mark.asyncio
    async def test_round_base_to_precision(self):
        """Happy path: base amount is floored to exchange precision."""
        exchange = AsyncMock()
        exchange.get_order.return_value = {
            "filled_size": "0.123456789",
            "filled_value": "500.00",
            "average_filled_price": "4050.00",
            "total_fees": "2.50",
        }

        with patch(
            "app.trading_engine.fill_reconciler.get_base_precision",
            return_value=6,
        ):
            result = await reconcile_order_fill(
                exchange=exchange,
                order_id="order-round",
                product_id="ETH-USD",
                max_retries=1,
                round_base_to_precision=True,
            )

        # 0.123456789 floored to 6 decimal places = 0.123456
        assert result.filled_size == pytest.approx(0.123456)

    @pytest.mark.asyncio
    async def test_fallback_values_used_when_fill_unavailable(self):
        """Edge case: fallback values used when order never fills."""
        exchange = AsyncMock()
        exchange.get_order.return_value = {
            "filled_size": "0",
            "filled_value": "0",
            "average_filled_price": "0",
            "total_fees": "0",
        }

        with patch("app.trading_engine.fill_reconciler.asyncio.sleep", new_callable=AsyncMock):
            result = await reconcile_order_fill(
                exchange=exchange,
                order_id="order-fallback",
                product_id="BTC-USD",
                max_retries=2,
                fallback_base=0.01,
                fallback_price=50000.0,
            )

        assert result.filled_size == pytest.approx(0.01)
        assert result.filled_value == pytest.approx(500.0)  # 0.01 * 50000
        assert result.average_price == pytest.approx(50000.0)
        assert result.total_fees == 0.0
        # A fabricated estimate must NOT be flagged as a confirmed fill — this is
        # what lets the sell/close path refuse to book a phantom sale.
        assert result.reconciled is False

    @pytest.mark.asyncio
    async def test_reconciled_true_only_for_real_fill(self):
        """A real exchange fill is flagged reconciled=True."""
        exchange = AsyncMock()
        exchange.get_order.return_value = {
            "filled_size": "0.01",
            "filled_value": "500.00",
            "average_filled_price": "50000.00",
            "total_fees": "2.50",
        }

        result = await reconcile_order_fill(
            exchange=exchange, order_id="order-real", product_id="BTC-USD", max_retries=1,
        )

        assert result.reconciled is True

    @pytest.mark.asyncio
    async def test_reconciled_false_when_zeros_no_fallback(self):
        """Zero fill with no fallback returns reconciled=False (caller must handle)."""
        exchange = AsyncMock()
        exchange.get_order.return_value = {
            "filled_size": "0", "filled_value": "0",
            "average_filled_price": "0", "total_fees": "0",
        }

        with patch("app.trading_engine.fill_reconciler.asyncio.sleep", new_callable=AsyncMock):
            result = await reconcile_order_fill(
                exchange=exchange, order_id="order-zero", product_id="BTC-USD", max_retries=2,
            )

        assert result.filled_size == 0.0
        assert result.reconciled is False

    @pytest.mark.asyncio
    async def test_fallback_only_base_without_price_returns_zeros(self):
        """Edge case: fallback_base without fallback_price returns zeros."""
        exchange = AsyncMock()
        exchange.get_order.return_value = {
            "filled_size": "0",
            "filled_value": "0",
            "average_filled_price": "0",
            "total_fees": "0",
        }

        with patch("app.trading_engine.fill_reconciler.asyncio.sleep", new_callable=AsyncMock):
            result = await reconcile_order_fill(
                exchange=exchange,
                order_id="order-partial-fallback",
                product_id="BTC-USD",
                max_retries=2,
                fallback_base=0.01,
                fallback_price=None,
            )

        assert result.filled_size == 0.0

    @pytest.mark.asyncio
    async def test_max_retries_one(self):
        """Edge case: max_retries=1 means only one attempt."""
        exchange = AsyncMock()
        exchange.get_order.return_value = {
            "filled_size": "0.5",
            "filled_value": "25000.00",
            "average_filled_price": "50000.00",
            "total_fees": "10.00",
        }

        result = await reconcile_order_fill(
            exchange=exchange,
            order_id="order-one",
            product_id="BTC-USD",
            max_retries=1,
        )

        assert result.filled_size == pytest.approx(0.5)
        exchange.get_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_btc_pair_fee_adjustment_with_zero_filled_value(self):
        """Edge case: BTC pair with zero filled_value skips fee adjustment."""
        exchange = AsyncMock()
        exchange.get_order.return_value = {
            "filled_size": "10.0",
            "filled_value": "0",
            "average_filled_price": "0.05",
            "total_fees": "0.005",
        }

        with patch("app.trading_engine.fill_reconciler.asyncio.sleep", new_callable=AsyncMock):
            result = await reconcile_order_fill(
                exchange=exchange,
                order_id="order-zero-val",
                product_id="ETH-BTC",
                max_retries=1,
                adjust_btc_fees=True,
            )

        # filled_value is 0, so no BTC fee deduction even though fees > 0
        # But also filled_value == 0 means the fill check fails
        assert result.filled_size == 0.0

    @pytest.mark.asyncio
    async def test_combined_btc_fees_and_precision_rounding(self):
        """Integration: BTC fee adjustment + precision rounding together."""
        exchange = AsyncMock()
        exchange.get_order.return_value = {
            "filled_size": "10.0",
            "filled_value": "0.5",
            "average_filled_price": "0.05",
            "total_fees": "0.005",
        }

        with patch(
            "app.trading_engine.fill_reconciler.get_base_precision",
            return_value=2,
        ):
            result = await reconcile_order_fill(
                exchange=exchange,
                order_id="order-combo",
                product_id="ETH-BTC",
                max_retries=1,
                adjust_btc_fees=True,
                round_base_to_precision=True,
            )

        # fee_rate = 0.005 / 0.5 = 0.01
        # fee_in_base = 10.0 * 0.01 = 0.1
        # after fee: 9.9
        # floor to 2 decimals: 9.9 -> 9.9 (already at precision)
        assert result.filled_size == pytest.approx(9.9)

    @pytest.mark.asyncio
    async def test_waits_for_terminal_status_then_returns_full_fill(self):
        """Regression (AERO 2026-06-24): a market order caught mid-fill reports a
        partial with a non-terminal status; the reconciler must wait for the
        terminal status and record the FULL fill, not the first partial."""
        exchange = AsyncMock()
        exchange.get_order.side_effect = [
            # First poll: order still OPEN, only 0.1 filled so far
            {
                "filled_size": "0.1", "filled_value": "0.0505",
                "average_filled_price": "0.505", "total_fees": "0.001",
                "status": "OPEN",
            },
            # Second poll: order now FILLED with the full 1.9
            {
                "filled_size": "1.9", "filled_value": "0.9587",
                "average_filled_price": "0.5046", "total_fees": "0.0115",
                "status": "FILLED",
            },
        ]

        with patch("app.trading_engine.fill_reconciler.asyncio.sleep", new_callable=AsyncMock):
            result = await reconcile_order_fill(
                exchange=exchange, order_id="order-aero", product_id="AERO-USD",
                max_retries=5,
            )

        assert result.filled_size == pytest.approx(1.9)
        assert result.reconciled is True
        assert exchange.get_order.call_count == 2

    @pytest.mark.asyncio
    async def test_terminal_status_first_attempt_returns_immediately(self):
        """Happy path: a FILLED order on the first poll returns immediately."""
        exchange = AsyncMock()
        exchange.get_order.return_value = {
            "filled_size": "1.9", "filled_value": "0.9587",
            "average_filled_price": "0.5046", "total_fees": "0.0115",
            "status": "FILLED",
        }

        result = await reconcile_order_fill(
            exchange=exchange, order_id="order-fast", product_id="AERO-USD",
            max_retries=5,
        )

        assert result.filled_size == pytest.approx(1.9)
        exchange.get_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_status_accepts_first_fill_backcompat(self):
        """Back-compat: when the exchange reports no status (paper/other clients),
        the first non-zero fill is accepted (prior behavior)."""
        exchange = AsyncMock()
        exchange.get_order.return_value = {
            "filled_size": "0.1", "filled_value": "0.0505",
            "average_filled_price": "0.505", "total_fees": "0.001",
        }

        result = await reconcile_order_fill(
            exchange=exchange, order_id="order-nostatus", product_id="AERO-USD",
            max_retries=5,
        )

        assert result.filled_size == pytest.approx(0.1)
        exchange.get_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_terminal_until_exhaustion_does_not_record_partial(self):
        """Edge case: order stays non-terminal (still filling) for every retry —
        the partial is NEVER recorded as a complete fill. The result is
        unconfirmed (reconciled=False, zero) so the buy's zero-guard refuses to
        book it and the order-reconciliation monitor corrects it once it settles."""
        exchange = AsyncMock()
        exchange.get_order.return_value = {
            "filled_size": "0.1", "filled_value": "0.0505",
            "average_filled_price": "0.505", "total_fees": "0.001",
            "status": "OPEN",
        }

        with patch("app.trading_engine.fill_reconciler.asyncio.sleep", new_callable=AsyncMock):
            result = await reconcile_order_fill(
                exchange=exchange, order_id="order-stuck", product_id="AERO-USD",
                max_retries=3,
            )

        assert result.filled_size == 0.0
        assert result.reconciled is False
        assert exchange.get_order.call_count == 3

    @pytest.mark.asyncio
    async def test_cancelled_with_partial_fill_returns_partial(self):
        """Edge case: a partially-filled order that terminates as CANCELLED
        (e.g. IOC remainder cancelled) records the executed partial immediately."""
        exchange = AsyncMock()
        exchange.get_order.return_value = {
            "filled_size": "0.1", "filled_value": "0.0505",
            "average_filled_price": "0.505", "total_fees": "0.001",
            "status": "CANCELLED",
        }

        result = await reconcile_order_fill(
            exchange=exchange, order_id="order-ioc", product_id="AERO-USD",
            max_retries=5,
        )

        assert result.filled_size == pytest.approx(0.1)
        exchange.get_order.assert_called_once()


# =============================================================================
# FillData dataclass
# =============================================================================


class TestFillData:
    """Tests for FillData dataclass."""

    def test_creation(self):
        """Happy path: FillData can be created with all fields."""
        fill = FillData(
            filled_size=0.01,
            filled_value=500.0,
            average_price=50000.0,
            total_fees=2.5,
        )
        assert fill.filled_size == 0.01
        assert fill.filled_value == 500.0
        assert fill.average_price == 50000.0
        assert fill.total_fees == 2.5

    def test_zero_fill_data(self):
        """Edge case: zero-filled FillData."""
        fill = FillData(
            filled_size=0.0,
            filled_value=0.0,
            average_price=0.0,
            total_fees=0.0,
        )
        assert fill.filled_size == 0.0
