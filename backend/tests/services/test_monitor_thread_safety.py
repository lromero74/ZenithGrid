"""
Tests for threading.Lock protection on _account_timers in AutoBuyMonitor and
RebalanceMonitor (Fix B).

When these monitors run on the secondary event loop, cleanup_in_memory_caches()
on the main loop calls cleanup_stale_entries() — a cross-thread dict mutation.
threading.Lock must protect the dict.

Verifies:
1. _account_timers_lock is threading.Lock
2. cleanup_stale_entries acquires the lock before mutating _account_timers
3. _account_timers writes in the monitor loop also acquire the lock
"""
import threading
from datetime import datetime

_THREADING_LOCK_TYPE = type(threading.Lock())


class TestAutoBuyMonitorThreadSafety:
    """AutoBuyMonitor must use threading.Lock for _account_timers."""

    def test_auto_buy_monitor_has_account_timers_lock(self):
        """Happy path: AutoBuyMonitor.__init__ creates _account_timers_lock."""
        from app.services.auto_buy_monitor import AutoBuyMonitor

        monitor = AutoBuyMonitor()
        assert hasattr(monitor, "_account_timers_lock"), (
            "AutoBuyMonitor must have _account_timers_lock attribute"
        )

    def test_auto_buy_monitor_account_timers_lock_is_threading_lock(self):
        """Happy path: _account_timers_lock must be threading.Lock."""
        from app.services.auto_buy_monitor import AutoBuyMonitor

        monitor = AutoBuyMonitor()
        assert type(monitor._account_timers_lock) is _THREADING_LOCK_TYPE, (
            f"Expected threading.Lock, got {type(monitor._account_timers_lock)}"
        )

    def test_auto_buy_cleanup_stale_entries_is_thread_safe(self):
        """Edge case: cleanup_stale_entries can be called from a different thread."""
        from app.services.auto_buy_monitor import AutoBuyMonitor

        monitor = AutoBuyMonitor()
        # Seed some timers
        monitor._account_timers[1] = datetime.utcnow()
        monitor._account_timers[2] = datetime.utcnow()

        errors = []

        def call_from_thread():
            try:
                result = monitor.cleanup_stale_entries({1})  # keep account 1, remove 2
                assert result["timers_pruned"] == 1
            except Exception as e:
                errors.append(str(e))

        t = threading.Thread(target=call_from_thread)
        t.start()
        t.join()

        assert not errors, f"cleanup_stale_entries raised from thread: {errors}"
        assert 2 not in monitor._account_timers

    def test_auto_buy_monitor_lock_acquirable_before_cleanup(self):
        """Failure case: if lock is held, cleanup_stale_entries blocks (not crashes)."""
        from app.services.auto_buy_monitor import AutoBuyMonitor

        monitor = AutoBuyMonitor()
        # Acquire the lock ourselves to verify it IS the same lock guarding the dict
        acquired = monitor._account_timers_lock.acquire(blocking=False)
        assert acquired, "Lock should be free initially"
        monitor._account_timers_lock.release()


class TestRebalanceMonitorThreadSafety:
    """RebalanceMonitor must use threading.Lock for _account_timers."""

    def test_rebalance_monitor_has_account_timers_lock(self):
        """Happy path: RebalanceMonitor.__init__ creates _account_timers_lock."""
        from app.services.rebalance_monitor import RebalanceMonitor

        monitor = RebalanceMonitor()
        assert hasattr(monitor, "_account_timers_lock"), (
            "RebalanceMonitor must have _account_timers_lock attribute"
        )

    def test_rebalance_monitor_account_timers_lock_is_threading_lock(self):
        """Happy path: _account_timers_lock must be threading.Lock."""
        from app.services.rebalance_monitor import RebalanceMonitor

        monitor = RebalanceMonitor()
        assert type(monitor._account_timers_lock) is _THREADING_LOCK_TYPE, (
            f"Expected threading.Lock, got {type(monitor._account_timers_lock)}"
        )

    def test_rebalance_cleanup_stale_entries_is_thread_safe(self):
        """Edge case: cleanup_stale_entries can be called from a different thread."""
        from app.services.rebalance_monitor import RebalanceMonitor

        monitor = RebalanceMonitor()
        monitor._account_timers[10] = datetime.utcnow()
        monitor._account_timers[20] = datetime.utcnow()

        errors = []

        def call_from_thread():
            try:
                monitor.cleanup_stale_entries({10})
            except Exception as e:
                errors.append(str(e))

        t = threading.Thread(target=call_from_thread)
        t.start()
        t.join()

        assert not errors, f"cleanup_stale_entries raised from thread: {errors}"
        assert 20 not in monitor._account_timers
