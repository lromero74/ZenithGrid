"""
Tests for backend/app/services/grid_rotation_service.py

Covers:
- evaluate_grid_rotation — time-based rotation evaluation
- execute_grid_rotation — profit locking and level closing
- check_and_run_rotation — orchestrator function
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.grid_rotation_service import (
    evaluate_grid_rotation,
    execute_grid_rotation,
    check_and_run_rotation,
)


def _make_bot(strategy_config=None):
    """Create a mock Bot with configurable strategy_config."""
    bot = MagicMock()
    bot.id = 1
    bot.product_id = "BTC-USD"
    bot.strategy_config = strategy_config or {}
    return bot


def _make_position():
    """Create a mock Position."""
    position = MagicMock()
    position.id = 1
    return position


# ---------------------------------------------------------------------------
# evaluate_grid_rotation
# ---------------------------------------------------------------------------


class TestEvaluateGridRotation:
    """Tests for evaluate_grid_rotation()"""

    @pytest.mark.asyncio
    async def test_rotation_disabled(self, db_session):
        """Happy path: rotation disabled returns False."""
        bot = _make_bot({"enable_time_rotation": False})
        result = await evaluate_grid_rotation(bot, _make_position(), AsyncMock(), db_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_rotation_not_initialized(self, db_session):
        """Edge case: grid not initialized returns False."""
        bot = _make_bot({
            "enable_time_rotation": True,
            "grid_state": {},  # No initialized_at
        })
        result = await evaluate_grid_rotation(bot, _make_position(), AsyncMock(), db_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_rotation_not_yet_time(self, db_session):
        """Edge case: interval not reached returns False."""
        recent = datetime.utcnow().isoformat()
        bot = _make_bot({
            "enable_time_rotation": True,
            "rotation_interval_hours": 48,
            "grid_state": {
                "initialized_at": recent,
            },
        })
        result = await evaluate_grid_rotation(bot, _make_position(), AsyncMock(), db_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_rotation_time_reached_sufficient_profit(self, db_session):
        """Happy path: interval reached with sufficient profit returns True."""
        old_time = (datetime.utcnow() - timedelta(hours=50)).isoformat()
        bot = _make_bot({
            "enable_time_rotation": True,
            "rotation_interval_hours": 48,
            "min_profit_to_rotate": 0.001,
            "grid_state": {
                "initialized_at": old_time,
                "total_profit_quote": 0.01,
            },
        })
        result = await evaluate_grid_rotation(bot, _make_position(), AsyncMock(), db_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_rotation_time_reached_insufficient_profit(self, db_session):
        """Edge case: interval reached but insufficient profit returns False."""
        old_time = (datetime.utcnow() - timedelta(hours=50)).isoformat()
        bot = _make_bot({
            "enable_time_rotation": True,
            "rotation_interval_hours": 48,
            "min_profit_to_rotate": 1.0,
            "grid_state": {
                "initialized_at": old_time,
                "total_profit_quote": 0.001,
            },
        })
        result = await evaluate_grid_rotation(bot, _make_position(), AsyncMock(), db_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_rotation_uses_last_rotation_over_initialized_at(self, db_session):
        """Edge case: prefers last_rotation time over initialized_at."""
        # Grid was initialized 100 hours ago, but last rotation was 10 hours ago
        old_init = (datetime.utcnow() - timedelta(hours=100)).isoformat()
        recent_rotation = (datetime.utcnow() - timedelta(hours=10)).isoformat()
        bot = _make_bot({
            "enable_time_rotation": True,
            "rotation_interval_hours": 48,
            "min_profit_to_rotate": 0.0,
            "grid_state": {
                "initialized_at": old_init,
                "last_rotation": recent_rotation,
                "total_profit_quote": 1.0,
            },
        })
        result = await evaluate_grid_rotation(bot, _make_position(), AsyncMock(), db_session)
        # 10 hours < 48 hours, so rotation not yet due
        assert result is False

    @pytest.mark.asyncio
    async def test_rotation_zero_profit_threshold(self, db_session):
        """Edge case: zero min_profit_to_rotate means any profit triggers rotation."""
        old_time = (datetime.utcnow() - timedelta(hours=50)).isoformat()
        bot = _make_bot({
            "enable_time_rotation": True,
            "rotation_interval_hours": 48,
            "min_profit_to_rotate": 0.0,
            "grid_state": {
                "initialized_at": old_time,
                "total_profit_quote": 0.0,
            },
        })
        result = await evaluate_grid_rotation(bot, _make_position(), AsyncMock(), db_session)
        assert result is True


# ---------------------------------------------------------------------------
# execute_grid_rotation
# ---------------------------------------------------------------------------


class TestExecuteGridRotation:
    """Tests for execute_grid_rotation()"""

    @pytest.mark.asyncio
    async def test_execute_with_profitable_levels(self, db_session):
        """Happy path: profitable levels are closed and profit is locked."""
        grid_levels = [
            {
                "level_index": 0, "status": "filled", "price": 40000.0,
                "filled_base_amount": 0.01,
            },
            {
                "level_index": 1, "status": "filled", "price": 42000.0,
                "filled_base_amount": 0.01,
            },
        ]
        bot = _make_bot({
            "profit_lock_percent": 100.0,  # Close all profitable
            "grid_state": {
                "grid_levels": grid_levels,
                "total_rotations": 0,
            },
        })

        position = _make_position()
        mock_client = AsyncMock()
        mock_client.create_market_order = AsyncMock(
            return_value={"success_response": {"order_id": "test-123"}}
        )

        # Mock Trade query
        mock_trades_result = MagicMock()
        mock_trades_result.scalars.return_value.all.return_value = []

        with patch.object(db_session, "execute", new_callable=AsyncMock, return_value=mock_trades_result):
            with patch.object(db_session, "commit", new_callable=AsyncMock):
                result = await execute_grid_rotation(
                    bot, position, mock_client, db_session, current_price=45000.0
                )

        assert result["rotated"] is True
        assert result["levels_closed"] == 2
        assert result["total_locked_profit"] > 0
        # Grid state should be updated
        assert bot.strategy_config["grid_state"]["total_rotations"] == 1
        assert "rotation_history" in bot.strategy_config["grid_state"]

    @pytest.mark.asyncio
    async def test_execute_with_no_filled_levels(self, db_session):
        """Edge case: no filled levels means nothing to close."""
        grid_levels = [
            {"level_index": 0, "status": "pending", "price": 40000.0, "filled_base_amount": 0},
        ]
        bot = _make_bot({
            "profit_lock_percent": 70.0,
            "grid_state": {"grid_levels": grid_levels, "total_rotations": 0},
        })

        mock_trades_result = MagicMock()
        mock_trades_result.scalars.return_value.all.return_value = []

        with patch.object(db_session, "execute", new_callable=AsyncMock, return_value=mock_trades_result):
            with patch.object(db_session, "commit", new_callable=AsyncMock):
                result = await execute_grid_rotation(
                    bot, _make_position(), AsyncMock(), db_session, current_price=45000.0
                )

        assert result["rotated"] is True
        assert result["levels_closed"] == 0
        assert result["total_locked_profit"] == 0.0

    @pytest.mark.asyncio
    async def test_execute_losing_levels_kept(self, db_session):
        """Edge case: losing levels are NOT closed."""
        grid_levels = [
            {
                "level_index": 0, "status": "filled", "price": 50000.0,
                "filled_base_amount": 0.01,
            },
        ]
        bot = _make_bot({
            "profit_lock_percent": 100.0,
            "grid_state": {"grid_levels": grid_levels, "total_rotations": 0},
        })

        mock_trades_result = MagicMock()
        mock_trades_result.scalars.return_value.all.return_value = []

        with patch.object(db_session, "execute", new_callable=AsyncMock, return_value=mock_trades_result):
            with patch.object(db_session, "commit", new_callable=AsyncMock):
                result = await execute_grid_rotation(
                    bot, _make_position(), AsyncMock(), db_session, current_price=45000.0
                )

        # Price dropped from 50000 to 45000, so this level is losing
        assert result["levels_closed"] == 0
        assert result["losing_levels_kept"] == 1

    @pytest.mark.asyncio
    async def test_execute_sell_order_failure_continues(self, db_session):
        """Failure: sell order failure for one level does not stop others."""
        grid_levels = [
            {
                "level_index": 0, "status": "filled", "price": 40000.0,
                "filled_base_amount": 0.01,
            },
            {
                "level_index": 1, "status": "filled", "price": 41000.0,
                "filled_base_amount": 0.01,
            },
        ]
        bot = _make_bot({
            "profit_lock_percent": 100.0,
            "grid_state": {"grid_levels": grid_levels, "total_rotations": 0},
        })

        mock_client = AsyncMock()
        # First call fails, second succeeds
        mock_client.create_market_order = AsyncMock(
            side_effect=[
                RuntimeError("Network error"),
                {"success_response": {"order_id": "test-123"}},
            ]
        )

        mock_trades_result = MagicMock()
        mock_trades_result.scalars.return_value.all.return_value = []

        with patch.object(db_session, "execute", new_callable=AsyncMock, return_value=mock_trades_result):
            with patch.object(db_session, "commit", new_callable=AsyncMock):
                result = await execute_grid_rotation(
                    bot, _make_position(), mock_client, db_session, current_price=45000.0
                )

        # One failed, one succeeded
        assert result["levels_closed"] == 1

    @pytest.mark.asyncio
    async def test_rotation_history_capped_at_10(self, db_session):
        """Edge case: rotation history is capped at 10 entries."""
        # Pre-fill with 10 entries
        existing_history = [{"timestamp": f"2025-01-{i:02d}"} for i in range(1, 11)]
        bot = _make_bot({
            "profit_lock_percent": 100.0,
            "grid_state": {
                "grid_levels": [],
                "total_rotations": 10,
                "rotation_history": existing_history,
            },
        })

        mock_trades_result = MagicMock()
        mock_trades_result.scalars.return_value.all.return_value = []

        with patch.object(db_session, "execute", new_callable=AsyncMock, return_value=mock_trades_result):
            with patch.object(db_session, "commit", new_callable=AsyncMock):
                await execute_grid_rotation(
                    bot, _make_position(), AsyncMock(), db_session, current_price=45000.0
                )

        history = bot.strategy_config["grid_state"]["rotation_history"]
        assert len(history) <= 10


# ---------------------------------------------------------------------------
# check_and_run_rotation
# ---------------------------------------------------------------------------


class TestCheckAndRunRotation:
    """Tests for check_and_run_rotation()"""

    @pytest.mark.asyncio
    async def test_check_no_rotation_needed(self, db_session):
        """Happy path: no rotation needed returns False."""
        bot = _make_bot({"enable_time_rotation": False})

        result = await check_and_run_rotation(
            bot, _make_position(), AsyncMock(), db_session, current_price=45000.0
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_check_rotation_executed(self, db_session):
        """Happy path: when evaluate returns True, rotation is executed."""
        with patch(
            "app.services.grid_rotation_service.evaluate_grid_rotation",
            new_callable=AsyncMock,
            return_value=True,
        ):
            with patch(
                "app.services.grid_rotation_service.execute_grid_rotation",
                new_callable=AsyncMock,
                return_value={"rotated": True, "levels_closed": 2},
            ):
                result = await check_and_run_rotation(
                    _make_bot(), _make_position(), AsyncMock(), db_session, current_price=45000.0
                )

        assert result is True
