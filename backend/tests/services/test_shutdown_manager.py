"""
Tests for backend/app/services/shutdown_manager.py

Tests the ShutdownManager class which tracks in-flight orders
and provides graceful shutdown with configurable timeout.
"""

import asyncio

import pytest

from app.services.shutdown_manager import ShutdownManager


class TestShutdownManagerInit:
    """Tests for ShutdownManager initialization and properties."""

    def test_initial_state_not_shutting_down(self):
        """Happy path: new manager is not in shutdown state."""
        mgr = ShutdownManager()
        assert mgr.is_shutting_down is False

    def test_initial_in_flight_count_zero(self):
        """Happy path: new manager has zero in-flight orders."""
        mgr = ShutdownManager()
        assert mgr.in_flight_count == 0

    def test_get_status_initial(self):
        """Happy path: get_status returns correct initial dict."""
        mgr = ShutdownManager()
        status = mgr.get_status()
        assert status["shutting_down"] is False
        assert status["in_flight_count"] == 0
        assert status["shutdown_requested_at"] is None


class TestIncrementDecrementInFlight:
    """Tests for increment_in_flight / decrement_in_flight."""

    @pytest.mark.asyncio
    async def test_increment_increases_count(self):
        """Happy path: incrementing raises in-flight count."""
        mgr = ShutdownManager()
        await mgr.increment_in_flight()
        assert mgr.in_flight_count == 1

    @pytest.mark.asyncio
    async def test_decrement_decreases_count(self):
        """Happy path: decrementing lowers in-flight count."""
        mgr = ShutdownManager()
        await mgr.increment_in_flight()
        await mgr.decrement_in_flight()
        assert mgr.in_flight_count == 0

    @pytest.mark.asyncio
    async def test_decrement_below_zero_clamps(self):
        """Edge case: decrementing past zero stays at zero."""
        mgr = ShutdownManager()
        await mgr.decrement_in_flight()
        assert mgr.in_flight_count == 0

    @pytest.mark.asyncio
    async def test_increment_during_shutdown_raises(self):
        """Failure: cannot start new orders during shutdown."""
        mgr = ShutdownManager()
        mgr._shutting_down = True
        with pytest.raises(RuntimeError, match="Cannot start new orders"):
            await mgr.increment_in_flight()


class TestOrderInFlightContextManager:
    """Tests for the order_in_flight() async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_increments_and_decrements(self):
        """Happy path: entering increments, exiting decrements."""
        mgr = ShutdownManager()
        async with mgr.order_in_flight():
            assert mgr.in_flight_count == 1
        assert mgr.in_flight_count == 0

    @pytest.mark.asyncio
    async def test_context_manager_decrements_on_exception(self):
        """Edge case: count decrements even if body raises."""
        mgr = ShutdownManager()
        with pytest.raises(ValueError):
            async with mgr.order_in_flight():
                assert mgr.in_flight_count == 1
                raise ValueError("boom")
        assert mgr.in_flight_count == 0

    @pytest.mark.asyncio
    async def test_context_manager_rejects_during_shutdown(self):
        """Failure: order_in_flight raises when shutting down."""
        mgr = ShutdownManager()
        mgr._shutting_down = True
        with pytest.raises(RuntimeError, match="Cannot start new orders"):
            async with mgr.order_in_flight():
                pass  # should never reach here


class TestPrepareShutdown:
    """Tests for prepare_shutdown()."""

    @pytest.mark.asyncio
    async def test_shutdown_ready_immediately_when_no_orders(self):
        """Happy path: immediate shutdown when nothing in-flight."""
        mgr = ShutdownManager()
        result = await mgr.prepare_shutdown(timeout=1.0)
        assert result["ready"] is True
        assert result["in_flight_count"] == 0
        assert result["waited_seconds"] == 0
        assert mgr.is_shutting_down is True

    @pytest.mark.asyncio
    async def test_shutdown_waits_for_in_flight_orders(self):
        """Happy path: waits for in-flight orders to complete."""
        mgr = ShutdownManager()
        await mgr.increment_in_flight()

        async def complete_order():
            await asyncio.sleep(0.1)
            await mgr.decrement_in_flight()

        task = asyncio.create_task(complete_order())
        result = await mgr.prepare_shutdown(timeout=5.0)
        await task
        assert result["ready"] is True
        assert result["in_flight_count"] == 0

    @pytest.mark.asyncio
    async def test_shutdown_timeout_with_stuck_orders(self):
        """Failure: timeout when in-flight orders don't complete."""
        mgr = ShutdownManager()
        await mgr.increment_in_flight()
        result = await mgr.prepare_shutdown(timeout=0.1)
        assert result["ready"] is False
        assert result["in_flight_count"] == 1
        assert "Timeout" in result["message"]


class TestCancelShutdown:
    """Tests for cancel_shutdown()."""

    @pytest.mark.asyncio
    async def test_cancel_shutdown_resets_state(self):
        """Happy path: cancelling shutdown resets the flag."""
        mgr = ShutdownManager()
        await mgr.prepare_shutdown(timeout=0.1)
        assert mgr.is_shutting_down is True
        await mgr.cancel_shutdown()
        assert mgr.is_shutting_down is False

    @pytest.mark.asyncio
    async def test_cancel_shutdown_clears_timestamp(self):
        """Edge case: cancel clears the requested_at timestamp."""
        mgr = ShutdownManager()
        await mgr.prepare_shutdown(timeout=0.1)
        await mgr.cancel_shutdown()
        status = mgr.get_status()
        assert status["shutdown_requested_at"] is None


class TestGetStatus:
    """Tests for get_status()."""

    @pytest.mark.asyncio
    async def test_get_status_after_shutdown(self):
        """Happy path: status reflects shutdown state."""
        mgr = ShutdownManager()
        await mgr.prepare_shutdown(timeout=0.1)
        status = mgr.get_status()
        assert status["shutting_down"] is True
        assert status["shutdown_requested_at"] is not None

    @pytest.mark.asyncio
    async def test_get_status_reflects_in_flight(self):
        """Edge case: status shows correct in-flight count."""
        mgr = ShutdownManager()
        await mgr.increment_in_flight()
        await mgr.increment_in_flight()
        status = mgr.get_status()
        assert status["in_flight_count"] == 2
