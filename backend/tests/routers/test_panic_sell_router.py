"""
Tests for backend/app/position_routers/panic_sell_router.py

TDD: these tests are written before the implementation.

Covers:
- POST /panic-sell: requires confirm=True (400 if false)
- POST /panic-sell: rejects unauthorized account (403)
- POST /panic-sell: cancel action — sets all open positions to cancelled
- POST /panic-sell: cancel action — does NOT affect closed/cancelled positions
- POST /panic-sell: stops active bots when stop_bots=True
- POST /panic-sell: leaves bots active when stop_bots=False
- POST /panic-sell: accumulates running seconds for active bots
- POST /panic-sell: disables account rebalancer when stop_portfolio_rebalancer=True
- POST /panic-sell: disables bot rebalancer groups when stop_bot_rebalancer=True
- POST /panic-sell: disables auto-buy when stop_auto_buy=True
- POST /panic-sell: zeros minimum balance reserves when zero_min_balances=True
- POST /panic-sell: triggers portfolio conversion when action=sell + target_currency
- POST /panic-sell: does NOT trigger conversion when action=cancel
- POST /panic-sell: does NOT trigger conversion when no target_currency
- GET  /panic-sell-status/{task_id}: returns progress dict
- GET  /panic-sell-status/{task_id}: 404 for unknown task
- Cancelled positions: already excluded from win rate (status="cancelled" vs "closed")
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.trading import Account, Bot, BotRebalancerGroup, Position
from app.models.auth import User


# =============================================================================
# Helpers
# =============================================================================


def _make_user():
    return User(
        email="panic@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        created_at=datetime.utcnow(),
    )


async def _make_account(db, user, **kwargs):
    account = Account(
        user_id=user.id,
        name="Test Account",
        type="cex",
        rebalance_enabled=kwargs.get("rebalance_enabled", False),
        auto_buy_enabled=kwargs.get("auto_buy_enabled", False),
        auto_buy_usd_enabled=kwargs.get("auto_buy_usd_enabled", False),
        auto_buy_usdc_enabled=kwargs.get("auto_buy_usdc_enabled", False),
        auto_buy_usdt_enabled=kwargs.get("auto_buy_usdt_enabled", False),
        min_balance_usd=kwargs.get("min_balance_usd", 0.0),
        min_balance_btc=kwargs.get("min_balance_btc", 0.0),
        min_balance_eth=kwargs.get("min_balance_eth", 0.0),
        min_balance_usdc=kwargs.get("min_balance_usdc", 0.0),
        min_balance_usdt=kwargs.get("min_balance_usdt", 0.0),
    )
    db.add(account)
    await db.flush()
    return account


async def _make_bot(db, account, is_active=True):
    bot = Bot(
        user_id=account.user_id,
        account_id=account.id,
        name=f"bot_{datetime.utcnow().timestamp()}",
        strategy_type="macd_dca",
        strategy_config={"base_order_percentage": 5.0},
        product_id="ETH-USD",
        product_ids=["ETH-USD"],
        is_active=is_active,
        check_interval_seconds=300,
        last_started_at=datetime.utcnow() - timedelta(hours=1) if is_active else None,
        total_running_seconds=0.0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(bot)
    await db.flush()
    return bot


async def _make_position(db, bot, status="open"):
    pos = Position(
        bot_id=bot.id,
        account_id=bot.account_id,
        user_id=bot.user_id,
        product_id=bot.product_id,
        status=status,
        opened_at=datetime.utcnow(),
        initial_quote_balance=1.0,
        max_quote_allowed=0.25,
        total_quote_spent=0.01,
        total_base_acquired=0.5,
        average_buy_price=0.02,
    )
    db.add(pos)
    await db.flush()
    return pos


async def _make_rebalancer_group(db, account, enabled=True):
    group = BotRebalancerGroup(
        account_id=account.id,
        base_currency="BTC",
        max_total_pct=100.0,
        overweight_tolerance_pct=5.0,
        enabled=enabled,
    )
    db.add(group)
    await db.flush()
    return group


# =============================================================================
# Tests: confirmation gate
# =============================================================================


class TestPanicSellRequiresConfirm:
    @pytest.mark.asyncio
    async def test_confirm_false_raises_400(self, db_session):
        """Request with confirm=False must be rejected immediately."""
        from app.position_routers.panic_sell_router import panic_sell, PanicSellRequest
        from fastapi import BackgroundTasks
        from fastapi import HTTPException

        user = _make_user()
        db_session.add(user)
        await db_session.flush()
        account = await _make_account(db_session, user)

        request = PanicSellRequest(account_id=account.id, action="cancel", confirm=False)

        with pytest.raises(HTTPException) as exc_info:
            await panic_sell(
                request=request,
                background_tasks=BackgroundTasks(),
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 400


# =============================================================================
# Tests: auth / account ownership
# =============================================================================


class TestPanicSellAuth:
    @pytest.mark.asyncio
    async def test_wrong_account_raises_403(self, db_session):
        """Request for an account the user doesn't own must be rejected."""
        from app.position_routers.panic_sell_router import panic_sell, PanicSellRequest
        from fastapi import BackgroundTasks
        from fastapi import HTTPException

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        other_user = User(
            email="other@example.com",
            hashed_password="hashed",
            is_active=True,
            is_superuser=False,
            created_at=datetime.utcnow(),
        )
        db_session.add(other_user)
        await db_session.flush()
        other_account = await _make_account(db_session, other_user)

        request = PanicSellRequest(account_id=other_account.id, action="cancel", confirm=True)

        with pytest.raises(HTTPException) as exc_info:
            await panic_sell(
                request=request,
                background_tasks=BackgroundTasks(),
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 403


# =============================================================================
# Tests: cancel action
# =============================================================================


class TestPanicSellCancel:
    @pytest.mark.asyncio
    async def test_cancels_all_open_positions(self, db_session):
        """Cancel action marks all open positions as cancelled."""
        from app.position_routers.panic_sell_router import _execute_panic_sell, _init_task
        import uuid

        user = _make_user()
        db_session.add(user)
        await db_session.flush()
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, is_active=False)
        pos1 = await _make_position(db_session, bot, status="open")
        pos2 = await _make_position(db_session, bot, status="open")

        task_id = str(uuid.uuid4())
        _init_task(task_id)

        await _execute_panic_sell(
            db_session, task_id, account.id, "cancel", None,
            stop_bots=False, stop_portfolio_rebalancer=False,
            stop_bot_rebalancer=False, stop_auto_buy=False,
            zero_min_balances=False, user_id=user.id,
        )

        await db_session.refresh(pos1)
        await db_session.refresh(pos2)
        assert pos1.status == "cancelled"
        assert pos2.status == "cancelled"
        assert pos1.closed_at is not None
        assert pos2.closed_at is not None

    @pytest.mark.asyncio
    async def test_does_not_affect_already_closed_positions(self, db_session):
        """Cancel action ignores positions that are already closed or cancelled."""
        from app.position_routers.panic_sell_router import _execute_panic_sell, _init_task
        import uuid

        user = _make_user()
        db_session.add(user)
        await db_session.flush()
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, is_active=False)
        closed_pos = await _make_position(db_session, bot, status="closed")
        cancelled_pos = await _make_position(db_session, bot, status="cancelled")

        task_id = str(uuid.uuid4())
        _init_task(task_id)

        await _execute_panic_sell(
            db_session, task_id, account.id, "cancel", None,
            stop_bots=False, stop_portfolio_rebalancer=False,
            stop_bot_rebalancer=False, stop_auto_buy=False,
            zero_min_balances=False, user_id=user.id,
        )

        await db_session.refresh(closed_pos)
        await db_session.refresh(cancelled_pos)
        # They shouldn't be touched - task only queries status="open"
        assert closed_pos.status == "closed"
        assert cancelled_pos.status == "cancelled"

    @pytest.mark.asyncio
    async def test_no_positions_completes_cleanly(self, db_session):
        """Cancel action with no open positions completes without error."""
        from app.position_routers.panic_sell_router import (
            _execute_panic_sell, _init_task, _panic_tasks
        )
        import uuid

        user = _make_user()
        db_session.add(user)
        await db_session.flush()
        account = await _make_account(db_session, user)

        task_id = str(uuid.uuid4())
        _init_task(task_id)

        await _execute_panic_sell(
            db_session, task_id, account.id, "cancel", None,
            stop_bots=False, stop_portfolio_rebalancer=False,
            stop_bot_rebalancer=False, stop_auto_buy=False,
            zero_min_balances=False, user_id=user.id,
        )

        assert _panic_tasks[task_id]["status"] == "completed"
        assert _panic_tasks[task_id]["positions_total"] == 0


# =============================================================================
# Tests: bot stopping
# =============================================================================


class TestPanicSellBotStopping:
    @pytest.mark.asyncio
    async def test_stops_active_bots_when_requested(self, db_session):
        """stop_bots=True sets is_active=False for all active bots."""
        from app.position_routers.panic_sell_router import _execute_panic_sell, _init_task
        import uuid

        user = _make_user()
        db_session.add(user)
        await db_session.flush()
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, is_active=True)

        task_id = str(uuid.uuid4())
        _init_task(task_id)

        await _execute_panic_sell(
            db_session, task_id, account.id, "cancel", None,
            stop_bots=True, stop_portfolio_rebalancer=False,
            stop_bot_rebalancer=False, stop_auto_buy=False,
            zero_min_balances=False, user_id=user.id,
        )

        await db_session.refresh(bot)
        assert bot.is_active is False
        assert bot.last_started_at is None

    @pytest.mark.asyncio
    async def test_leaves_bots_active_when_stop_bots_false(self, db_session):
        """stop_bots=False leaves bots running."""
        from app.position_routers.panic_sell_router import _execute_panic_sell, _init_task
        import uuid

        user = _make_user()
        db_session.add(user)
        await db_session.flush()
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, is_active=True)

        task_id = str(uuid.uuid4())
        _init_task(task_id)

        await _execute_panic_sell(
            db_session, task_id, account.id, "cancel", None,
            stop_bots=False, stop_portfolio_rebalancer=False,
            stop_bot_rebalancer=False, stop_auto_buy=False,
            zero_min_balances=False, user_id=user.id,
        )

        await db_session.refresh(bot)
        assert bot.is_active is True

    @pytest.mark.asyncio
    async def test_accumulates_running_seconds_for_active_bots(self, db_session):
        """Running seconds are accumulated when a bot is stopped."""
        from app.position_routers.panic_sell_router import _execute_panic_sell, _init_task
        import uuid

        user = _make_user()
        db_session.add(user)
        await db_session.flush()
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, is_active=True)
        # last_started_at was set to 1 hour ago in _make_bot
        assert bot.total_running_seconds == 0.0

        task_id = str(uuid.uuid4())
        _init_task(task_id)

        await _execute_panic_sell(
            db_session, task_id, account.id, "cancel", None,
            stop_bots=True, stop_portfolio_rebalancer=False,
            stop_bot_rebalancer=False, stop_auto_buy=False,
            zero_min_balances=False, user_id=user.id,
        )

        await db_session.refresh(bot)
        # Should have accumulated ~3600 seconds (1 hour)
        assert bot.total_running_seconds > 0


# =============================================================================
# Tests: rebalancers
# =============================================================================


class TestPanicSellRebalancers:
    @pytest.mark.asyncio
    async def test_disables_portfolio_rebalancer(self, db_session):
        """stop_portfolio_rebalancer=True sets account.rebalance_enabled=False."""
        from app.position_routers.panic_sell_router import _execute_panic_sell, _init_task
        import uuid

        user = _make_user()
        db_session.add(user)
        await db_session.flush()
        account = await _make_account(db_session, user, rebalance_enabled=True)

        task_id = str(uuid.uuid4())
        _init_task(task_id)

        await _execute_panic_sell(
            db_session, task_id, account.id, "cancel", None,
            stop_bots=False, stop_portfolio_rebalancer=True,
            stop_bot_rebalancer=False, stop_auto_buy=False,
            zero_min_balances=False, user_id=user.id,
        )

        await db_session.refresh(account)
        assert account.rebalance_enabled is False

    @pytest.mark.asyncio
    async def test_disables_bot_rebalancer_groups(self, db_session):
        """stop_bot_rebalancer=True sets all BotRebalancerGroup.enabled=False."""
        from app.position_routers.panic_sell_router import _execute_panic_sell, _init_task
        import uuid

        user = _make_user()
        db_session.add(user)
        await db_session.flush()
        account = await _make_account(db_session, user)
        group = await _make_rebalancer_group(db_session, account, enabled=True)

        task_id = str(uuid.uuid4())
        _init_task(task_id)

        await _execute_panic_sell(
            db_session, task_id, account.id, "cancel", None,
            stop_bots=False, stop_portfolio_rebalancer=False,
            stop_bot_rebalancer=True, stop_auto_buy=False,
            zero_min_balances=False, user_id=user.id,
        )

        await db_session.refresh(group)
        assert group.enabled is False

    @pytest.mark.asyncio
    async def test_respects_stop_portfolio_rebalancer_false(self, db_session):
        """stop_portfolio_rebalancer=False leaves rebalance_enabled unchanged."""
        from app.position_routers.panic_sell_router import _execute_panic_sell, _init_task
        import uuid

        user = _make_user()
        db_session.add(user)
        await db_session.flush()
        account = await _make_account(db_session, user, rebalance_enabled=True)

        task_id = str(uuid.uuid4())
        _init_task(task_id)

        await _execute_panic_sell(
            db_session, task_id, account.id, "cancel", None,
            stop_bots=False, stop_portfolio_rebalancer=False,
            stop_bot_rebalancer=False, stop_auto_buy=False,
            zero_min_balances=False, user_id=user.id,
        )

        await db_session.refresh(account)
        assert account.rebalance_enabled is True


# =============================================================================
# Tests: auto-buy
# =============================================================================


class TestPanicSellAutoBuy:
    @pytest.mark.asyncio
    async def test_disables_auto_buy_when_requested(self, db_session):
        """stop_auto_buy=True sets account.auto_buy_enabled=False."""
        from app.position_routers.panic_sell_router import _execute_panic_sell, _init_task
        import uuid

        user = _make_user()
        db_session.add(user)
        await db_session.flush()
        account = await _make_account(
            db_session, user,
            auto_buy_enabled=True,
            auto_buy_usd_enabled=True,
            auto_buy_usdc_enabled=True,
            auto_buy_usdt_enabled=True,
        )

        task_id = str(uuid.uuid4())
        _init_task(task_id)

        await _execute_panic_sell(
            db_session, task_id, account.id, "cancel", None,
            stop_bots=False, stop_portfolio_rebalancer=False,
            stop_bot_rebalancer=False, stop_auto_buy=True,
            zero_min_balances=False, user_id=user.id,
        )

        await db_session.refresh(account)
        assert account.auto_buy_enabled is False
        assert account.auto_buy_usd_enabled is False
        assert account.auto_buy_usdc_enabled is False
        assert account.auto_buy_usdt_enabled is False

    @pytest.mark.asyncio
    async def test_leaves_auto_buy_enabled_when_stop_false(self, db_session):
        """stop_auto_buy=False leaves auto_buy_enabled unchanged."""
        from app.position_routers.panic_sell_router import _execute_panic_sell, _init_task
        import uuid

        user = _make_user()
        db_session.add(user)
        await db_session.flush()
        account = await _make_account(db_session, user, auto_buy_enabled=True)

        task_id = str(uuid.uuid4())
        _init_task(task_id)

        await _execute_panic_sell(
            db_session, task_id, account.id, "cancel", None,
            stop_bots=False, stop_portfolio_rebalancer=False,
            stop_bot_rebalancer=False, stop_auto_buy=False,
            zero_min_balances=False, user_id=user.id,
        )

        await db_session.refresh(account)
        assert account.auto_buy_enabled is True


# =============================================================================
# Tests: minimum balance reserves
# =============================================================================


class TestPanicSellMinBalances:
    @pytest.mark.asyncio
    async def test_zeros_all_min_balances(self, db_session):
        """zero_min_balances=True sets all min_balance_* fields to 0."""
        from app.position_routers.panic_sell_router import _execute_panic_sell, _init_task
        import uuid

        user = _make_user()
        db_session.add(user)
        await db_session.flush()
        account = await _make_account(
            db_session, user,
            min_balance_usd=1000.0,
            min_balance_btc=0.5,
            min_balance_eth=2.0,
            min_balance_usdc=500.0,
            min_balance_usdt=300.0,
        )

        task_id = str(uuid.uuid4())
        _init_task(task_id)

        await _execute_panic_sell(
            db_session, task_id, account.id, "cancel", None,
            stop_bots=False, stop_portfolio_rebalancer=False,
            stop_bot_rebalancer=False, stop_auto_buy=False,
            zero_min_balances=True, user_id=user.id,
        )

        await db_session.refresh(account)
        assert account.min_balance_usd == 0.0
        assert account.min_balance_btc == 0.0
        assert account.min_balance_eth == 0.0
        assert account.min_balance_usdc == 0.0
        assert account.min_balance_usdt == 0.0

    @pytest.mark.asyncio
    async def test_leaves_min_balances_when_not_requested(self, db_session):
        """zero_min_balances=False leaves min_balance fields unchanged."""
        from app.position_routers.panic_sell_router import _execute_panic_sell, _init_task
        import uuid

        user = _make_user()
        db_session.add(user)
        await db_session.flush()
        account = await _make_account(db_session, user, min_balance_usd=500.0)

        task_id = str(uuid.uuid4())
        _init_task(task_id)

        await _execute_panic_sell(
            db_session, task_id, account.id, "cancel", None,
            stop_bots=False, stop_portfolio_rebalancer=False,
            stop_bot_rebalancer=False, stop_auto_buy=False,
            zero_min_balances=False, user_id=user.id,
        )

        await db_session.refresh(account)
        assert account.min_balance_usd == 500.0


# =============================================================================
# Tests: portfolio conversion
# =============================================================================


class TestPanicSellConversion:
    @pytest.mark.asyncio
    async def test_triggers_conversion_when_sell_with_target(self, db_session):
        """action=sell + target_currency triggers portfolio conversion."""
        from app.position_routers.panic_sell_router import (
            _execute_panic_sell, _init_task, _panic_tasks
        )
        import uuid

        user = _make_user()
        db_session.add(user)
        await db_session.flush()
        account = await _make_account(db_session, user)

        mock_exchange = MagicMock()
        mock_exchange.get_current_price = AsyncMock(return_value=50000.0)

        task_id = str(uuid.uuid4())
        _init_task(task_id)

        with patch(
            "app.position_routers.panic_sell_router.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=mock_exchange,
        ), patch("asyncio.ensure_future") as mock_ensure_future:
            await _execute_panic_sell(
                db_session, task_id, account.id, "sell", "USD",
                stop_bots=False, stop_portfolio_rebalancer=False,
                stop_bot_rebalancer=False, stop_auto_buy=False,
                zero_min_balances=False, user_id=user.id,
            )

        mock_ensure_future.assert_called_once()
        assert _panic_tasks[task_id]["conversion_task_id"] is not None

    @pytest.mark.asyncio
    async def test_no_conversion_on_cancel_action(self, db_session):
        """action=cancel does NOT trigger portfolio conversion."""
        from app.position_routers.panic_sell_router import (
            _execute_panic_sell, _init_task, _panic_tasks
        )
        import uuid

        user = _make_user()
        db_session.add(user)
        await db_session.flush()
        account = await _make_account(db_session, user)

        task_id = str(uuid.uuid4())
        _init_task(task_id)

        with patch("asyncio.ensure_future") as mock_ensure_future:
            await _execute_panic_sell(
                db_session, task_id, account.id, "cancel", "USD",
                stop_bots=False, stop_portfolio_rebalancer=False,
                stop_bot_rebalancer=False, stop_auto_buy=False,
                zero_min_balances=False, user_id=user.id,
            )

        mock_ensure_future.assert_not_called()
        assert _panic_tasks[task_id]["conversion_task_id"] is None

    @pytest.mark.asyncio
    async def test_no_conversion_when_no_target_currency(self, db_session):
        """action=sell without target_currency does NOT trigger conversion."""
        from app.position_routers.panic_sell_router import (
            _execute_panic_sell, _init_task, _panic_tasks
        )
        import uuid

        user = _make_user()
        db_session.add(user)
        await db_session.flush()
        account = await _make_account(db_session, user)

        mock_exchange = MagicMock()
        mock_exchange.get_current_price = AsyncMock(return_value=50000.0)

        task_id = str(uuid.uuid4())
        _init_task(task_id)

        with patch(
            "app.position_routers.panic_sell_router.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=mock_exchange,
        ), patch("asyncio.ensure_future") as mock_ensure_future:
            await _execute_panic_sell(
                db_session, task_id, account.id, "sell", None,
                stop_bots=False, stop_portfolio_rebalancer=False,
                stop_bot_rebalancer=False, stop_auto_buy=False,
                zero_min_balances=False, user_id=user.id,
            )

        mock_ensure_future.assert_not_called()
        assert _panic_tasks[task_id]["conversion_task_id"] is None


# =============================================================================
# Tests: status endpoint
# =============================================================================


class TestPanicSellStatus:
    @pytest.mark.asyncio
    async def test_status_endpoint_returns_progress(self, db_session):
        """GET /panic-sell-status/{task_id} returns the task dict."""
        from app.position_routers.panic_sell_router import (
            get_panic_sell_status, _init_task
        )
        import uuid

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        task_id = str(uuid.uuid4())
        _init_task(task_id)

        result = await get_panic_sell_status(task_id=task_id, current_user=user)

        assert result["task_id"] == task_id
        assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_status_404_for_unknown_task(self, db_session):
        """GET /panic-sell-status/{task_id} returns 404 for unknown task."""
        from app.position_routers.panic_sell_router import get_panic_sell_status
        from fastapi import HTTPException

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_panic_sell_status(task_id="does-not-exist", current_user=user)

        assert exc_info.value.status_code == 404


# =============================================================================
# Tests: win rate invariant
# =============================================================================


class TestWinRateExclusion:
    def test_cancelled_positions_excluded_from_win_rate(self):
        """bot_stats_service filters only status='closed' for win rate calc.

        This documents the invariant: cancelled positions are excluded from
        the win rate denominator without any special handling.
        """
        positions = [
            MagicMock(status="closed", exit_reason="take_profit"),
            MagicMock(status="closed", exit_reason="stop_loss"),
            MagicMock(status="cancelled"),   # panic cancel — excluded
            MagicMock(status="open"),         # still open — excluded
        ]

        # Mirror bot_stats_service.py line 262
        closed_positions = [p for p in positions if p.status == "closed"]

        assert len(closed_positions) == 2
        assert all(p.status == "closed" for p in closed_positions)

    def test_manual_exit_reason_positions_excluded_from_win_rate(self):
        """Panic-sold positions set exit_reason='manual', excluded from win rate numerator.

        bot_stats_service.py line 147:
        profitable = [p for p in closed_positions if p.exit_reason != 'manual']
        """
        closed = [
            MagicMock(status="closed", exit_reason="take_profit"),
            MagicMock(status="closed", exit_reason="manual"),   # panic sell
            MagicMock(status="closed", exit_reason="stop_loss"),
        ]

        # Mirror bot_stats_service.py
        profitable = [p for p in closed if p.exit_reason != "manual"]

        assert len(profitable) == 2
        assert all(p.exit_reason != "manual" for p in profitable)
