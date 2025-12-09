"""
Graceful Shutdown Manager

Tracks in-flight operations and provides a safe shutdown mechanism.
Ensures no orders are mid-execution before allowing shutdown.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class ShutdownManager:
    """
    Manages graceful shutdown by tracking in-flight operations.

    Usage:
        # At start of order execution
        async with shutdown_manager.order_in_flight():
            await execute_order(...)

        # When shutting down
        await shutdown_manager.prepare_shutdown(timeout=60)
    """

    def __init__(self):
        self._shutting_down = False
        self._in_flight_count = 0
        self._lock = asyncio.Lock()
        self._shutdown_event = asyncio.Event()
        self._shutdown_requested_at: Optional[datetime] = None

    @property
    def is_shutting_down(self) -> bool:
        """Check if shutdown has been requested"""
        return self._shutting_down

    @property
    def in_flight_count(self) -> int:
        """Number of orders currently being executed"""
        return self._in_flight_count

    async def increment_in_flight(self):
        """Mark an order as starting execution"""
        async with self._lock:
            if self._shutting_down:
                raise RuntimeError("Cannot start new orders - shutdown in progress")
            self._in_flight_count += 1
            logger.debug(f"Order started - in-flight count: {self._in_flight_count}")

    async def decrement_in_flight(self):
        """Mark an order as finished execution"""
        async with self._lock:
            self._in_flight_count = max(0, self._in_flight_count - 1)
            logger.debug(f"Order completed - in-flight count: {self._in_flight_count}")

            # Signal if we're shutting down and no more in-flight orders
            if self._shutting_down and self._in_flight_count == 0:
                self._shutdown_event.set()

    class OrderInFlight:
        """Context manager for tracking in-flight orders"""
        def __init__(self, manager: 'ShutdownManager'):
            self.manager = manager

        async def __aenter__(self):
            await self.manager.increment_in_flight()
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            await self.manager.decrement_in_flight()
            return False

    def order_in_flight(self) -> 'OrderInFlight':
        """Get a context manager for tracking an in-flight order"""
        return self.OrderInFlight(self)

    async def prepare_shutdown(self, timeout: float = 60.0) -> dict:
        """
        Prepare for graceful shutdown.

        1. Prevents new orders from starting
        2. Waits for in-flight orders to complete
        3. Returns status when safe to shutdown

        Args:
            timeout: Maximum seconds to wait for in-flight orders

        Returns:
            dict with shutdown status:
            - ready: bool - True if safe to shutdown
            - in_flight_count: int - Orders still executing (if not ready)
            - waited_seconds: float - How long we waited
            - message: str - Human-readable status
        """
        self._shutting_down = True
        self._shutdown_requested_at = datetime.utcnow()
        self._shutdown_event.clear()

        logger.info(f"Shutdown requested - {self._in_flight_count} orders in-flight")

        # If no in-flight orders, we're ready immediately
        if self._in_flight_count == 0:
            logger.info("No in-flight orders - ready for shutdown")
            return {
                "ready": True,
                "in_flight_count": 0,
                "waited_seconds": 0,
                "message": "No in-flight orders - ready for shutdown"
            }

        # Wait for in-flight orders to complete
        logger.info(f"Waiting up to {timeout}s for {self._in_flight_count} in-flight orders...")

        try:
            await asyncio.wait_for(self._shutdown_event.wait(), timeout=timeout)
            waited = (datetime.utcnow() - self._shutdown_requested_at).total_seconds()
            logger.info(f"All in-flight orders completed after {waited:.1f}s - ready for shutdown")
            return {
                "ready": True,
                "in_flight_count": 0,
                "waited_seconds": waited,
                "message": f"All orders completed after {waited:.1f}s - ready for shutdown"
            }
        except asyncio.TimeoutError:
            waited = timeout
            logger.warning(
                f"Shutdown timeout after {timeout}s - {self._in_flight_count} orders still in-flight"
            )
            return {
                "ready": False,
                "in_flight_count": self._in_flight_count,
                "waited_seconds": waited,
                "message": f"Timeout: {self._in_flight_count} orders still in-flight after {timeout}s"
            }

    async def cancel_shutdown(self):
        """Cancel a pending shutdown request"""
        self._shutting_down = False
        self._shutdown_requested_at = None
        self._shutdown_event.clear()
        logger.info("Shutdown cancelled")

    def get_status(self) -> dict:
        """Get current shutdown manager status"""
        return {
            "shutting_down": self._shutting_down,
            "in_flight_count": self._in_flight_count,
            "shutdown_requested_at": self._shutdown_requested_at.isoformat() if self._shutdown_requested_at else None,
        }


# Global singleton instance
shutdown_manager = ShutdownManager()
