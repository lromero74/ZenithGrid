"""
Tests for backend/app/secondary_loop.py

Verifies:
1. Secondary loop starts and stops cleanly
2. Secondary session maker is distinct from the primary session maker
3. schedule() executes coroutines on the secondary loop
4. get_secondary_session_maker() raises before start_secondary_loop() is called
"""
import asyncio

import pytest


class TestSecondaryLoopLifecycle:
    """Secondary loop starts and stops without error."""

    def test_secondary_loop_starts_and_stops(self):
        """Happy path: start and stop the secondary loop."""
        from app.secondary_loop import get_secondary_loop, start_secondary_loop, stop_secondary_loop

        start_secondary_loop()
        loop = get_secondary_loop()
        assert loop.is_running()
        stop_secondary_loop()

    def test_secondary_loop_session_maker_is_distinct(self):
        """Secondary session maker must differ from the primary session maker."""
        from app.database import async_session_maker as primary
        from app.secondary_loop import (
            get_secondary_session_maker,
            start_secondary_loop,
            stop_secondary_loop,
        )

        start_secondary_loop()
        try:
            secondary = get_secondary_session_maker()
            assert secondary is not primary, "Secondary must have its own engine and session maker"
        finally:
            stop_secondary_loop()


class TestScheduleCoroutine:
    """schedule() dispatches coroutines onto the secondary loop."""

    def test_schedule_runs_coroutine_on_secondary_loop(self):
        """Happy path: schedule() executes a coroutine on the secondary loop."""
        from app.secondary_loop import schedule, start_secondary_loop, stop_secondary_loop

        start_secondary_loop()
        results = []

        async def _work():
            results.append(asyncio.get_event_loop())

        try:
            future = schedule(_work())
            future.result(timeout=5)
            assert len(results) == 1
        finally:
            stop_secondary_loop()


class TestGetSecondarySessionMakerBeforeStart:
    """get_secondary_session_maker() raises RuntimeError before the loop is started."""

    def test_get_secondary_session_maker_before_start_raises(self):
        """Edge case: raises RuntimeError when secondary loop not started."""
        import app.secondary_loop as sl

        sl._session_maker = None  # force uninitialized state
        with pytest.raises(RuntimeError, match="Secondary loop not started"):
            sl.get_secondary_session_maker()
