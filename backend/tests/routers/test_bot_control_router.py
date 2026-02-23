"""
Tests for backend/app/bot_routers/bot_control_router.py

Covers bot start/stop/force-run/cancel-all-positions/sell-all-positions endpoints.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.models import Bot, BotProduct, Position, Settings, User


# =============================================================================
# Helpers
# =============================================================================


def _make_user():
    """Create a test user."""
    user = User(
        email="control@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        created_at=datetime.utcnow(),
    )
    return user


async def _make_bot(db_session, user, name="ControlBot", strategy_type="macd_dca",
                    is_active=False, product_id="ETH-BTC"):
    """Create, flush, and return a test bot."""
    bot = Bot(
        user_id=user.id,
        name=name,
        strategy_type=strategy_type,
        strategy_config={"base_order_percentage": 5.0},
        product_id=product_id,
        product_ids=[product_id],
        is_active=is_active,
        check_interval_seconds=300,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(bot)
    await db_session.flush()
    return bot


async def _make_position(db_session, bot, status="open"):
    """Create a test position for a bot."""
    pos = Position(
        bot_id=bot.id,
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
    db_session.add(pos)
    await db_session.flush()
    return pos


async def _enable_seasonality(db_session):
    """Insert the seasonality_enabled=true setting."""
    s = Settings(key="seasonality_enabled", value="true", value_type="bool")
    db_session.add(s)
    await db_session.flush()


# =============================================================================
# POST /{bot_id}/start
# =============================================================================


class TestStartBot:
    """Tests for POST /{bot_id}/start"""

    @pytest.mark.asyncio
    async def test_start_bot_success(self, db_session):
        """Happy path: inactive bot is started successfully."""
        from app.bot_routers.bot_control_router import start_bot

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user, is_active=False)

        result = await start_bot(bot_id=bot.id, db=db_session, current_user=user)

        assert "started successfully" in result["message"]
        assert bot.is_active is True

    @pytest.mark.asyncio
    async def test_start_bot_already_active(self, db_session):
        """Edge case: starting an already active bot returns 'already active' message."""
        from app.bot_routers.bot_control_router import start_bot

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user, is_active=True)

        result = await start_bot(bot_id=bot.id, db=db_session, current_user=user)

        assert "already active" in result["message"]

    @pytest.mark.asyncio
    async def test_start_bot_not_found_raises_404(self, db_session):
        """Failure: starting a nonexistent bot raises 404."""
        from app.bot_routers.bot_control_router import start_bot

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await start_bot(bot_id=99999, db=db_session, current_user=user)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_start_bot_wrong_user_raises_404(self, db_session):
        """Failure: user cannot start another user's bot."""
        from app.bot_routers.bot_control_router import start_bot

        owner = _make_user()
        other = User(
            email="other@example.com", hashed_password="hashed",
            is_active=True, created_at=datetime.utcnow(),
        )
        db_session.add_all([owner, other])
        await db_session.flush()

        bot = await _make_bot(db_session, owner, is_active=False)

        with pytest.raises(HTTPException) as exc_info:
            await start_bot(bot_id=bot.id, db=db_session, current_user=other)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_control_router.get_seasonality_status", new_callable=AsyncMock)
    async def test_start_bot_blocked_by_seasonality(self, mock_season, db_session):
        """Failure: seasonality restrictions block bot start with 403."""
        from app.bot_routers.bot_control_router import start_bot

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        await _enable_seasonality(db_session)
        bot = await _make_bot(db_session, user, is_active=False, product_id="ETH-BTC")
        bp = BotProduct(bot_id=bot.id, product_id="ETH-BTC")
        db_session.add(bp)
        await db_session.flush()

        # Mock seasonality status to block BTC bots
        mock_status = MagicMock()
        mock_status.btc_bots_allowed = False
        mock_status.usd_bots_allowed = True
        mock_status.mode = "risk_off"
        mock_status.season_info = MagicMock()
        mock_status.season_info.name = "Winter"
        mock_season.return_value = mock_status

        with pytest.raises(HTTPException) as exc_info:
            await start_bot(bot_id=bot.id, db=db_session, current_user=user)
        assert exc_info.value.status_code == 403
        assert "Cannot start bot" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_control_router.get_seasonality_status", new_callable=AsyncMock)
    async def test_start_grid_bot_exempt_from_seasonality(self, mock_season, db_session):
        """Edge case: grid_trading bots are exempt from seasonality restrictions."""
        from app.bot_routers.bot_control_router import start_bot

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        await _enable_seasonality(db_session)
        bot = await _make_bot(
            db_session, user, is_active=False,
            strategy_type="grid_trading", product_id="ETH-BTC"
        )

        # Even though seasonality would block, grid bots are exempt
        result = await start_bot(bot_id=bot.id, db=db_session, current_user=user)
        assert "started successfully" in result["message"]
        # get_seasonality_status should NOT be called for grid bots
        mock_season.assert_not_called()


# =============================================================================
# POST /{bot_id}/stop
# =============================================================================


class TestStopBot:
    """Tests for POST /{bot_id}/stop"""

    @pytest.mark.asyncio
    async def test_stop_bot_success(self, db_session):
        """Happy path: active bot is stopped successfully."""
        from app.bot_routers.bot_control_router import stop_bot

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user, is_active=True)

        result = await stop_bot(bot_id=bot.id, db=db_session, current_user=user)

        assert "stopped successfully" in result["message"]
        assert bot.is_active is False

    @pytest.mark.asyncio
    async def test_stop_bot_already_inactive(self, db_session):
        """Edge case: stopping an already inactive bot returns 'already inactive' message."""
        from app.bot_routers.bot_control_router import stop_bot

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user, is_active=False)

        result = await stop_bot(bot_id=bot.id, db=db_session, current_user=user)

        assert "already inactive" in result["message"]

    @pytest.mark.asyncio
    async def test_stop_bot_not_found_raises_404(self, db_session):
        """Failure: stopping a nonexistent bot raises 404."""
        from app.bot_routers.bot_control_router import stop_bot

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await stop_bot(bot_id=99999, db=db_session, current_user=user)
        assert exc_info.value.status_code == 404


# =============================================================================
# POST /{bot_id}/force-run
# =============================================================================


class TestForceRunBot:
    """Tests for POST /{bot_id}/force-run"""

    @pytest.mark.asyncio
    async def test_force_run_success(self, db_session):
        """Happy path: force-run sets last_signal_check far enough in the past."""
        from app.bot_routers.bot_control_router import force_run_bot

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user, is_active=True)
        bot.last_signal_check = datetime.utcnow()

        result = await force_run_bot(bot_id=bot.id, db=db_session, current_user=user)

        assert "will run on next monitor cycle" in result["message"]
        assert result["note"] is not None
        # last_signal_check should be set far enough in the past
        expected_cutoff = datetime.utcnow() - timedelta(seconds=300)
        assert bot.last_signal_check < expected_cutoff

    @pytest.mark.asyncio
    async def test_force_run_inactive_bot_raises_400(self, db_session):
        """Failure: cannot force-run an inactive bot."""
        from app.bot_routers.bot_control_router import force_run_bot

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user, is_active=False)

        with pytest.raises(HTTPException) as exc_info:
            await force_run_bot(bot_id=bot.id, db=db_session, current_user=user)
        assert exc_info.value.status_code == 400
        assert "inactive bot" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_force_run_not_found_raises_404(self, db_session):
        """Failure: force-run on nonexistent bot raises 404."""
        from app.bot_routers.bot_control_router import force_run_bot

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await force_run_bot(bot_id=99999, db=db_session, current_user=user)
        assert exc_info.value.status_code == 404


# =============================================================================
# POST /{bot_id}/cancel-all-positions
# =============================================================================


class TestCancelAllPositions:
    """Tests for POST /{bot_id}/cancel-all-positions"""

    @pytest.mark.asyncio
    async def test_cancel_all_positions_success(self, db_session):
        """Happy path: cancels all open positions for a bot."""
        from app.bot_routers.bot_control_router import cancel_all_positions

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user, is_active=True)
        await _make_position(db_session, bot, status="open")
        await _make_position(db_session, bot, status="open")

        result = await cancel_all_positions(
            bot_id=bot.id, confirm=True, db=db_session, current_user=user
        )

        assert result["cancelled_count"] == 2
        assert result["failed_count"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_cancel_all_positions_no_confirm_raises_400(self, db_session):
        """Failure: must confirm with confirm=true."""
        from app.bot_routers.bot_control_router import cancel_all_positions

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user, is_active=True)

        with pytest.raises(HTTPException) as exc_info:
            await cancel_all_positions(
                bot_id=bot.id, confirm=False, db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 400
        assert "confirm" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_cancel_all_positions_no_open_positions_raises_400(self, db_session):
        """Edge case: no open positions to cancel raises 400."""
        from app.bot_routers.bot_control_router import cancel_all_positions

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user, is_active=True)
        # Create a closed position - should not be found
        await _make_position(db_session, bot, status="closed")

        with pytest.raises(HTTPException) as exc_info:
            await cancel_all_positions(
                bot_id=bot.id, confirm=True, db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 400
        assert "No open positions" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_cancel_all_positions_not_found_raises_404(self, db_session):
        """Failure: cancel positions for nonexistent bot raises 404."""
        from app.bot_routers.bot_control_router import cancel_all_positions

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await cancel_all_positions(
                bot_id=99999, confirm=True, db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_only_affects_open_positions(self, db_session):
        """Edge case: closed positions are not affected by cancel-all."""
        from app.bot_routers.bot_control_router import cancel_all_positions

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user, is_active=True)
        open_pos = await _make_position(db_session, bot, status="open")
        closed_pos = await _make_position(db_session, bot, status="closed")

        result = await cancel_all_positions(
            bot_id=bot.id, confirm=True, db=db_session, current_user=user
        )

        assert result["cancelled_count"] == 1
        assert open_pos.status == "cancelled"
        assert closed_pos.status == "closed"  # Unchanged


# =============================================================================
# POST /{bot_id}/sell-all-positions
# =============================================================================


class TestSellAllPositions:
    """Tests for POST /{bot_id}/sell-all-positions"""

    @pytest.mark.asyncio
    async def test_sell_all_positions_no_confirm_raises_400(self, db_session):
        """Failure: must confirm with confirm=true."""
        from app.bot_routers.bot_control_router import sell_all_positions

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user, is_active=True)

        with pytest.raises(HTTPException) as exc_info:
            await sell_all_positions(
                bot_id=bot.id, confirm=False, db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_sell_all_positions_not_found_raises_404(self, db_session):
        """Failure: sell positions for nonexistent bot raises 404."""
        from app.bot_routers.bot_control_router import sell_all_positions

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await sell_all_positions(
                bot_id=99999, confirm=True, db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.services.exchange_service.get_exchange_client_for_account", new_callable=AsyncMock)
    async def test_sell_all_positions_no_exchange_raises_400(self, mock_get_exchange, db_session):
        """Failure: no exchange client for the bot's account raises 400."""
        from app.bot_routers.bot_control_router import sell_all_positions

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user, is_active=True)
        bot.account_id = 1
        await _make_position(db_session, bot, status="open")

        mock_get_exchange.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await sell_all_positions(
                bot_id=bot.id, confirm=True, db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 400
        assert "No exchange client" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.strategies.StrategyRegistry.get_strategy")
    @patch("app.services.exchange_service.get_exchange_client_for_account", new_callable=AsyncMock)
    async def test_sell_all_positions_no_open_positions_raises_400(
        self, mock_get_exchange, mock_get_strategy, db_session
    ):
        """Edge case: no open positions to sell raises 400."""
        from app.bot_routers.bot_control_router import sell_all_positions

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user, is_active=True)
        bot.account_id = 1

        mock_exchange = AsyncMock()
        mock_get_exchange.return_value = mock_exchange
        mock_get_strategy.return_value = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await sell_all_positions(
                bot_id=bot.id, confirm=True, db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 400
        assert "No open positions" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.StrategyTradingEngine")
    @patch("app.strategies.StrategyRegistry.get_strategy")
    @patch("app.services.exchange_service.get_exchange_client_for_account", new_callable=AsyncMock)
    async def test_sell_all_positions_success(
        self, mock_get_exchange, mock_get_strategy, mock_engine_cls, db_session
    ):
        """Happy path: sells all open positions and returns summary."""
        from app.bot_routers.bot_control_router import sell_all_positions

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user, is_active=True)
        bot.account_id = 1
        await _make_position(db_session, bot, status="open")

        mock_exchange = AsyncMock()
        mock_exchange.get_current_price = AsyncMock(return_value=50000.0)
        mock_get_exchange.return_value = mock_exchange

        mock_strategy = MagicMock()
        mock_get_strategy.return_value = mock_strategy

        mock_engine = AsyncMock()
        mock_trade = MagicMock()
        mock_engine.execute_sell = AsyncMock(return_value=(mock_trade, 0.001, 2.5))
        mock_engine_cls.return_value = mock_engine

        result = await sell_all_positions(
            bot_id=bot.id, confirm=True, db=db_session, current_user=user
        )

        assert result["sold_count"] == 1
        assert result["failed_count"] == 0
        assert result["total_profit_quote"] == pytest.approx(0.001)

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.StrategyTradingEngine")
    @patch("app.strategies.StrategyRegistry.get_strategy")
    @patch("app.services.exchange_service.get_exchange_client_for_account", new_callable=AsyncMock)
    async def test_sell_all_positions_partial_failure(
        self, mock_get_exchange, mock_get_strategy, mock_engine_cls, db_session
    ):
        """Edge case: some positions fail to sell, errors are reported."""
        from app.bot_routers.bot_control_router import sell_all_positions

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user, is_active=True)
        bot.account_id = 1
        await _make_position(db_session, bot, status="open")
        await _make_position(db_session, bot, status="open")

        mock_exchange = AsyncMock()
        mock_exchange.get_current_price = AsyncMock(return_value=50000.0)
        mock_get_exchange.return_value = mock_exchange

        mock_strategy = MagicMock()
        mock_get_strategy.return_value = mock_strategy

        # First call succeeds, second call raises
        mock_engine = AsyncMock()
        mock_engine.execute_sell = AsyncMock(
            side_effect=[
                (MagicMock(), 0.001, 2.5),
                Exception("Insufficient funds"),
            ]
        )
        mock_engine_cls.return_value = mock_engine

        result = await sell_all_positions(
            bot_id=bot.id, confirm=True, db=db_session, current_user=user
        )

        assert result["sold_count"] == 1
        assert result["failed_count"] == 1
        assert len(result["errors"]) == 1
        assert "Insufficient funds" in result["errors"][0]


# =============================================================================
# check_seasonality_allows_bot (helper function)
# =============================================================================


class TestCheckSeasonalityAllowsBot:
    """Tests for the check_seasonality_allows_bot helper function."""

    @pytest.mark.asyncio
    async def test_seasonality_disabled_always_allows(self, db_session):
        """Happy path: when seasonality is disabled, all bots are allowed."""
        from app.bot_routers.bot_control_router import check_seasonality_allows_bot

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        bot = await _make_bot(db_session, user)

        allowed, reason = await check_seasonality_allows_bot(db_session, bot)
        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_grid_trading_exempt_from_seasonality(self, db_session):
        """Edge case: grid_trading strategy is always exempt."""
        from app.bot_routers.bot_control_router import check_seasonality_allows_bot

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        await _enable_seasonality(db_session)
        bot = await _make_bot(db_session, user, strategy_type="grid_trading")

        allowed, reason = await check_seasonality_allows_bot(db_session, bot)
        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_control_router.get_seasonality_status", new_callable=AsyncMock)
    async def test_usd_bots_blocked_in_risk_off(self, mock_season, db_session):
        """Failure: USD bots blocked when usd_bots_allowed is False."""
        from app.bot_routers.bot_control_router import check_seasonality_allows_bot

        user = _make_user()
        db_session.add(user)
        await db_session.flush()

        await _enable_seasonality(db_session)
        bot = await _make_bot(db_session, user, product_id="ETH-USD")
        # Add BotProduct so get_quote_currency returns "USD"
        bp = BotProduct(bot_id=bot.id, product_id="ETH-USD")
        db_session.add(bp)
        await db_session.flush()
        # Refresh bot to load products relationship
        await db_session.refresh(bot, ["products"])

        mock_status = MagicMock()
        mock_status.btc_bots_allowed = True
        mock_status.usd_bots_allowed = False
        mock_status.mode = "risk_off"
        mock_status.season_info = MagicMock()
        mock_status.season_info.name = "Winter"
        mock_season.return_value = mock_status

        allowed, reason = await check_seasonality_allows_bot(db_session, bot)
        assert allowed is False
        assert "USD bots blocked" in reason
