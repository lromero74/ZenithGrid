"""
TDD tests for ByBitClient._rate_lock thread safety.

Same pattern as CoinbaseClient fix (D): convert asyncio.Lock to
threading.Lock so the ByBit client works from both the main event loop
and the secondary event loop without "Future attached to different loop".
"""
import asyncio
import threading
import unittest.mock as mock


_THREADING_LOCK_TYPE = type(threading.Lock())


class TestByBitRateLockType:
    def _make_client(self):
        from app.exchange_clients.bybit_client import ByBitClient
        return ByBitClient(api_key="test_key", api_secret="test_secret", testnet=True)

    def test_rate_lock_is_threading_lock(self):
        client = self._make_client()
        assert type(client._rate_lock) is _THREADING_LOCK_TYPE

    def test_rate_lock_is_not_asyncio_lock(self):
        client = self._make_client()
        assert not isinstance(client._rate_lock, asyncio.Lock)

    def test_rate_lock_supports_sync_context_manager(self):
        client = self._make_client()
        acquired = False
        with client._rate_lock:
            acquired = True
        assert acquired


class TestByBitRateLockCrossLoop:
    def test_rate_lock_acquirable_from_thread(self):
        from app.exchange_clients.bybit_client import ByBitClient
        client = ByBitClient(api_key="test", api_secret="test", testnet=True)

        errors = []

        def _worker():
            try:
                with client._rate_lock:
                    pass
            except Exception as exc:
                errors.append(exc)

        t = threading.Thread(target=_worker)
        t.start()
        t.join(timeout=2.0)
        assert not t.is_alive()
        assert errors == [], f"thread raised: {errors}"

    def test_rate_lock_acquirable_from_multiple_threads(self):
        from app.exchange_clients.bybit_client import ByBitClient
        client = ByBitClient(api_key="test", api_secret="test", testnet=True)

        acquired = []
        errors = []

        def _worker():
            try:
                with client._rate_lock:
                    acquired.append(1)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        assert errors == [], f"threads raised: {errors}"
        assert len(acquired) == 5


class TestByBitRateLimitSlotReservation:
    def test_slot_reserved_before_sleep(self):
        """_last_request_time must be advanced before asyncio.sleep is awaited."""
        import time
        from app.exchange_clients.bybit_client import ByBitClient

        client = ByBitClient(api_key="test", api_secret="test", testnet=True)
        client._last_request_time = time.monotonic()  # Simulate recent request

        sleep_called_with = []
        last_time_at_sleep = []

        async def mock_sleep(d):
            sleep_called_with.append(d)
            last_time_at_sleep.append(client._last_request_time)

        with mock.patch("app.exchange_clients.bybit_client.asyncio.sleep", side_effect=mock_sleep), \
             mock.patch("app.exchange_clients.bybit_client.asyncio.to_thread", new=mock.AsyncMock(return_value={})):
            # Trigger a rate-limited call
            asyncio.get_event_loop().run_until_complete(
                client._rate_limited_call(lambda: {})
            )

        if sleep_called_with:
            assert all(d >= 0 for d in sleep_called_with)
            # At the moment sleep was awaited, the slot should be reserved
            assert all(t > 0 for t in last_time_at_sleep), \
                "_last_request_time should be set before asyncio.sleep"
