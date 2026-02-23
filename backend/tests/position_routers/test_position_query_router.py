"""
Tests for backend/app/position_routers/position_query_router.py

Covers position listing, details, trades, AI logs, P&L timeseries,
completed trade stats, and realized PnL endpoints.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.models import (
    Account, AIBotLog, BlacklistedCoin, Bot,
    Position, Trade, User,
)


# =============================================================================
# Helper: Create user + account for ownership tests
# =============================================================================


async def _create_user_with_account(db_session, email="test@example.com"):
    """Create a test user with an active CEX account."""
    user = User(
        email=email,
        hashed_password="hashed",
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.flush()

    account = Account(
        user_id=user.id,
        name="Test Account",
        type="cex",
        exchange="coinbase",
        is_active=True,
    )
    db_session.add(account)
    await db_session.flush()

    return user, account


async def _create_position(db_session, account, bot=None, **overrides):
    """Create a test position with sensible defaults."""
    defaults = dict(
        bot_id=bot.id if bot else None,
        account_id=account.id,
        product_id="ETH-BTC",
        status="open",
        opened_at=datetime.utcnow(),
        initial_quote_balance=1.0,
        max_quote_allowed=0.25,
        total_quote_spent=0.01,
        total_base_acquired=0.5,
        average_buy_price=0.02,
    )
    defaults.update(overrides)
    position = Position(**defaults)
    db_session.add(position)
    await db_session.flush()
    return position


async def _create_bot(db_session, user, account, **overrides):
    """Create a test bot."""
    defaults = dict(
        user_id=user.id,
        account_id=account.id,
        name="Test Bot",
        strategy_type="macd_dca",
        strategy_config={"base_order_fixed": 0.01},
    )
    defaults.update(overrides)
    bot = Bot(**defaults)
    db_session.add(bot)
    await db_session.flush()
    return bot


# =============================================================================
# GET /positions/
# =============================================================================


class TestGetPositions:
    """Tests for GET /positions/ endpoint"""

    @pytest.mark.asyncio
    @patch("app.position_routers.helpers.compute_resize_budget", return_value=0.05)
    async def test_returns_open_positions(self, mock_resize, db_session):
        """Happy path: returns positions for authenticated user."""
        from app.position_routers.position_query_router import get_positions

        user, account = await _create_user_with_account(db_session)
        pos = await _create_position(db_session, account, status="open")

        # Create a trade for the position
        trade = Trade(
            position_id=pos.id,
            side="buy",
            quote_amount=0.01,
            base_amount=0.5,
            price=0.02,
            trade_type="initial",
            timestamp=datetime.utcnow(),
        )
        db_session.add(trade)
        await db_session.flush()

        response_mock = MagicMock()
        response_mock.headers = {}

        result = await get_positions(
            response=response_mock,
            status=None,
            limit=50,
            db=db_session,
            current_user=user,
        )
        assert len(result) == 1
        assert result[0].id == pos.id

    @pytest.mark.asyncio
    async def test_returns_empty_for_user_without_accounts(self, db_session):
        """Edge case: user with no accounts gets empty list."""
        from app.position_routers.position_query_router import get_positions

        user = User(
            email="noaccount@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        response_mock = MagicMock()
        response_mock.headers = {}

        result = await get_positions(
            response=response_mock,
            status=None,
            limit=50,
            db=db_session,
            current_user=user,
        )
        assert result == []

    @pytest.mark.asyncio
    @patch("app.position_routers.helpers.compute_resize_budget", return_value=0.0)
    async def test_filters_by_status(self, mock_resize, db_session):
        """Happy path: filters positions by status parameter."""
        from app.position_routers.position_query_router import get_positions

        user, account = await _create_user_with_account(db_session)
        await _create_position(db_session, account, status="open")
        await _create_position(
            db_session, account, status="closed",
            closed_at=datetime.utcnow(),
            profit_usd=10.0,
        )

        response_mock = MagicMock()
        response_mock.headers = {}

        result = await get_positions(
            response=response_mock,
            status="closed",
            limit=50,
            db=db_session,
            current_user=user,
        )
        assert len(result) == 1
        assert result[0].status == "closed"

    @pytest.mark.asyncio
    @patch("app.position_routers.helpers.compute_resize_budget", return_value=0.0)
    async def test_user_isolation_cannot_see_other_users_positions(self, mock_resize, db_session):
        """Failure: user cannot see another user's positions."""
        from app.position_routers.position_query_router import get_positions

        user1, account1 = await _create_user_with_account(db_session, "user1@example.com")
        user2, account2 = await _create_user_with_account(db_session, "user2@example.com")

        await _create_position(db_session, account1, status="open")
        await _create_position(db_session, account2, status="open")

        response_mock = MagicMock()
        response_mock.headers = {}

        result = await get_positions(
            response=response_mock,
            status=None,
            limit=50,
            db=db_session,
            current_user=user1,
        )
        assert len(result) == 1  # Only user1's position

    @pytest.mark.asyncio
    @patch("app.position_routers.helpers.compute_resize_budget", return_value=0.0)
    async def test_sets_cache_control_headers(self, mock_resize, db_session):
        """Edge case: response headers prevent HTTP caching."""
        from app.position_routers.position_query_router import get_positions

        user, account = await _create_user_with_account(db_session)

        response_mock = MagicMock()
        response_mock.headers = {}

        await get_positions(
            response=response_mock,
            status=None,
            limit=50,
            db=db_session,
            current_user=user,
        )
        assert "no-cache" in response_mock.headers.get("Cache-Control", "")

    @pytest.mark.asyncio
    @patch("app.position_routers.helpers.compute_resize_budget", return_value=0.0)
    async def test_blacklisted_coin_flag(self, mock_resize, db_session):
        """Edge case: blacklisted coin flag is set correctly."""
        from app.position_routers.position_query_router import get_positions

        user, account = await _create_user_with_account(db_session)
        await _create_position(
            db_session, account, status="open", product_id="DOGE-BTC"
        )

        # Blacklist DOGE
        bl = BlacklistedCoin(
            user_id=user.id,
            symbol="DOGE",
            reason="Low liquidity",
        )
        db_session.add(bl)
        await db_session.flush()

        response_mock = MagicMock()
        response_mock.headers = {}

        result = await get_positions(
            response=response_mock,
            status=None,
            limit=50,
            db=db_session,
            current_user=user,
        )
        assert len(result) == 1
        assert result[0].is_blacklisted is True
        assert result[0].blacklist_reason == "Low liquidity"


# =============================================================================
# GET /positions/{position_id}
# =============================================================================


class TestGetPosition:
    """Tests for GET /positions/{position_id} endpoint"""

    @pytest.mark.asyncio
    async def test_returns_position_details(self, db_session):
        """Happy path: returns single position by ID."""
        from app.position_routers.position_query_router import get_position

        user, account = await _create_user_with_account(db_session)
        pos = await _create_position(db_session, account, status="open")

        result = await get_position(
            position_id=pos.id,
            db=db_session,
            current_user=user,
        )
        assert result.id == pos.id
        assert result.status == "open"

    @pytest.mark.asyncio
    async def test_position_not_found_raises_404(self, db_session):
        """Failure: non-existent position returns 404."""
        from fastapi import HTTPException
        from app.position_routers.position_query_router import get_position

        user, account = await _create_user_with_account(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await get_position(
                position_id=99999,
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_user_isolation_other_users_position_returns_404(self, db_session):
        """Failure: accessing another user's position returns 404."""
        from fastapi import HTTPException
        from app.position_routers.position_query_router import get_position

        user1, account1 = await _create_user_with_account(db_session, "user1@test.com")
        user2, account2 = await _create_user_with_account(db_session, "user2@test.com")

        pos = await _create_position(db_session, account1, status="open")

        with pytest.raises(HTTPException) as exc_info:
            await get_position(
                position_id=pos.id,
                db=db_session,
                current_user=user2,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_no_accounts_raises_404(self, db_session):
        """Failure: user with no accounts gets 404."""
        from fastapi import HTTPException
        from app.position_routers.position_query_router import get_position

        user = User(
            email="noaccounts@test.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_position(
                position_id=1,
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_includes_trade_count_and_buy_prices(self, db_session):
        """Edge case: trade count, first/last buy prices are set correctly."""
        from app.position_routers.position_query_router import get_position

        user, account = await _create_user_with_account(db_session)
        pos = await _create_position(db_session, account, status="open")

        # Create buy trades at different prices
        for i, price in enumerate([0.02, 0.018, 0.015]):
            trade = Trade(
                position_id=pos.id,
                side="buy",
                quote_amount=0.01,
                base_amount=0.5,
                price=price,
                trade_type="initial" if i == 0 else f"safety_order_{i}",
                timestamp=datetime.utcnow() + timedelta(minutes=i),
            )
            db_session.add(trade)
        await db_session.flush()

        result = await get_position(
            position_id=pos.id,
            db=db_session,
            current_user=user,
        )
        assert result.trade_count == 3
        assert result.first_buy_price == 0.02
        assert result.last_buy_price == 0.015


# =============================================================================
# GET /positions/{position_id}/trades
# =============================================================================


class TestGetPositionTrades:
    """Tests for GET /positions/{position_id}/trades endpoint"""

    @pytest.mark.asyncio
    async def test_returns_trades_for_position(self, db_session):
        """Happy path: returns all trades for a position."""
        from app.position_routers.position_query_router import get_position_trades

        user, account = await _create_user_with_account(db_session)
        pos = await _create_position(db_session, account)

        trade = Trade(
            position_id=pos.id,
            side="buy",
            quote_amount=0.01,
            base_amount=0.5,
            price=0.02,
            trade_type="initial",
            timestamp=datetime.utcnow(),
        )
        db_session.add(trade)
        await db_session.flush()

        result = await get_position_trades(
            position_id=pos.id,
            db=db_session,
            current_user=user,
        )
        assert len(result) == 1
        assert result[0].side == "buy"

    @pytest.mark.asyncio
    async def test_other_users_position_trades_returns_404(self, db_session):
        """Failure: cannot access another user's position trades."""
        from fastapi import HTTPException
        from app.position_routers.position_query_router import get_position_trades

        user1, account1 = await _create_user_with_account(db_session, "trader1@test.com")
        user2, account2 = await _create_user_with_account(db_session, "trader2@test.com")

        pos = await _create_position(db_session, account1)

        with pytest.raises(HTTPException) as exc_info:
            await get_position_trades(
                position_id=pos.id,
                db=db_session,
                current_user=user2,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_position_returns_404(self, db_session):
        """Failure: non-existent position returns 404."""
        from fastapi import HTTPException
        from app.position_routers.position_query_router import get_position_trades

        user, account = await _create_user_with_account(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await get_position_trades(
                position_id=99999,
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# GET /positions/{position_id}/ai-logs
# =============================================================================


class TestGetPositionAiLogs:
    """Tests for GET /positions/{position_id}/ai-logs endpoint"""

    @pytest.mark.asyncio
    async def test_returns_ai_logs_for_position(self, db_session):
        """Happy path: returns AI logs linked to the position."""
        from app.position_routers.position_query_router import get_position_ai_logs

        user, account = await _create_user_with_account(db_session)
        bot = await _create_bot(db_session, user, account)
        pos = await _create_position(db_session, account, bot=bot)

        log = AIBotLog(
            bot_id=bot.id,
            position_id=pos.id,
            timestamp=datetime.utcnow(),
            thinking="Market is bullish, RSI at 30",
            decision="buy",
            confidence=85.0,
            current_price=0.02,
            product_id="ETH-BTC",
        )
        db_session.add(log)
        await db_session.flush()

        result = await get_position_ai_logs(
            position_id=pos.id,
            include_before_open=False,
            db=db_session,
            current_user=user,
        )
        assert len(result) == 1
        assert result[0].decision == "buy"

    @pytest.mark.asyncio
    async def test_position_not_found_returns_404(self, db_session):
        """Failure: non-existent position returns 404."""
        from fastapi import HTTPException
        from app.position_routers.position_query_router import get_position_ai_logs

        user, account = await _create_user_with_account(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await get_position_ai_logs(
                position_id=99999,
                include_before_open=True,
                db=db_session,
                current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_user_isolation_for_ai_logs(self, db_session):
        """Failure: cannot access another user's position AI logs."""
        from fastapi import HTTPException
        from app.position_routers.position_query_router import get_position_ai_logs

        user1, account1 = await _create_user_with_account(db_session, "aiuser1@test.com")
        user2, account2 = await _create_user_with_account(db_session, "aiuser2@test.com")

        bot = await _create_bot(db_session, user1, account1, name="AI Bot 1")
        pos = await _create_position(db_session, account1, bot=bot)

        with pytest.raises(HTTPException) as exc_info:
            await get_position_ai_logs(
                position_id=pos.id,
                include_before_open=True,
                db=db_session,
                current_user=user2,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# GET /positions/pnl-timeseries
# =============================================================================


class TestGetPnlTimeseries:
    """Tests for GET /positions/pnl-timeseries endpoint"""

    @pytest.mark.asyncio
    async def test_returns_cumulative_pnl(self, db_session):
        """Happy path: returns cumulative PnL from closed positions."""
        from app.position_routers.position_query_router import get_pnl_timeseries

        user, account = await _create_user_with_account(db_session)
        bot = await _create_bot(db_session, user, account, name="PnL Bot")

        # Create two closed positions
        for i, profit in enumerate([5.0, -2.0]):
            await _create_position(
                db_session, account, bot=bot,
                status="closed",
                closed_at=datetime.utcnow() - timedelta(days=2 - i),
                profit_usd=profit,
                profit_quote=profit / 50000.0,
                btc_usd_price_at_close=50000.0,
                product_id="ETH-USD",
            )

        result = await get_pnl_timeseries(
            account_id=None,
            db=db_session,
            current_user=user,
        )
        assert "summary" in result
        assert "by_day" in result
        assert "by_pair" in result
        assert len(result["summary"]) == 2
        # Cumulative: 5.0 then 5.0 + (-2.0) = 3.0
        assert result["summary"][-1]["cumulative_pnl_usd"] == 3.0

    @pytest.mark.asyncio
    async def test_empty_result_for_no_positions(self, db_session):
        """Edge case: no closed positions returns empty data."""
        from app.position_routers.position_query_router import get_pnl_timeseries

        user, account = await _create_user_with_account(db_session)

        result = await get_pnl_timeseries(
            account_id=None,
            db=db_session,
            current_user=user,
        )
        assert result["summary"] == []
        assert result["by_day"] == []
        assert result["by_pair"] == []

    @pytest.mark.asyncio
    async def test_user_without_accounts_returns_default(self, db_session):
        """Edge case: user with no accounts returns default empty structure."""
        from app.position_routers.position_query_router import get_pnl_timeseries

        user = User(
            email="nopnl@test.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        result = await get_pnl_timeseries(
            account_id=None,
            db=db_session,
            current_user=user,
        )
        assert result["summary"] == []
        assert result["active_trades"] == 0

    @pytest.mark.asyncio
    async def test_btc_pair_uses_profit_quote_directly(self, db_session):
        """Edge case: BTC pairs use profit_quote as BTC profit."""
        from app.position_routers.position_query_router import get_pnl_timeseries

        user, account = await _create_user_with_account(db_session)
        bot = await _create_bot(db_session, user, account, name="BTC Bot")

        await _create_position(
            db_session, account, bot=bot,
            status="closed",
            closed_at=datetime.utcnow(),
            profit_usd=100.0,
            profit_quote=0.002,
            product_id="ETH-BTC",
            btc_usd_price_at_close=50000.0,
        )

        result = await get_pnl_timeseries(
            account_id=None,
            db=db_session,
            current_user=user,
        )
        assert len(result["summary"]) == 1
        # BTC pair: profit_btc should be profit_quote directly
        assert result["summary"][0]["profit_btc"] == 0.002


# =============================================================================
# GET /positions/completed/stats
# =============================================================================


class TestGetCompletedTradesStats:
    """Tests for GET /positions/completed/stats endpoint"""

    @pytest.mark.asyncio
    async def test_returns_stats_for_closed_positions(self, db_session):
        """Happy path: returns win rate and profit stats."""
        from app.position_routers.position_query_router import get_completed_trades_stats

        user, account = await _create_user_with_account(db_session)

        # 2 winning, 1 losing
        for profit in [10.0, 5.0, -3.0]:
            await _create_position(
                db_session, account,
                status="closed",
                closed_at=datetime.utcnow(),
                profit_usd=profit,
                product_id="ETH-USD",
                btc_usd_price_at_close=50000.0,
            )

        result = await get_completed_trades_stats(
            account_id=None,
            db=db_session,
            current_user=user,
        )
        assert result["total_trades"] == 3
        assert result["winning_trades"] == 2
        assert result["losing_trades"] == 1
        assert result["win_rate"] == pytest.approx(66.67, abs=0.01)
        assert result["total_profit_usd"] == 12.0
        assert result["average_profit_usd"] == 4.0

    @pytest.mark.asyncio
    async def test_returns_zeros_for_no_positions(self, db_session):
        """Edge case: no closed positions returns all zeros."""
        from app.position_routers.position_query_router import get_completed_trades_stats

        user, account = await _create_user_with_account(db_session)

        result = await get_completed_trades_stats(
            account_id=None,
            db=db_session,
            current_user=user,
        )
        assert result["total_trades"] == 0
        assert result["win_rate"] == 0.0
        assert result["total_profit_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_returns_zeros_for_user_without_accounts(self, db_session):
        """Failure: user with no accounts returns zero stats."""
        from app.position_routers.position_query_router import get_completed_trades_stats

        user = User(
            email="nostats@test.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        result = await get_completed_trades_stats(
            account_id=None,
            db=db_session,
            current_user=user,
        )
        assert result["total_trades"] == 0


# =============================================================================
# GET /positions/realized-pnl
# =============================================================================


class TestGetRealizedPnl:
    """Tests for GET /positions/realized-pnl endpoint"""

    @pytest.mark.asyncio
    async def test_returns_alltime_pnl(self, db_session):
        """Happy path: all-time PnL accumulates across all closed positions."""
        from app.position_routers.position_query_router import get_realized_pnl

        user, account = await _create_user_with_account(db_session)

        # Create positions closed at various times
        await _create_position(
            db_session, account,
            status="closed",
            closed_at=datetime.utcnow() - timedelta(days=400),
            profit_usd=100.0,
            product_id="ETH-USD",
            btc_usd_price_at_close=50000.0,
        )
        await _create_position(
            db_session, account,
            status="closed",
            closed_at=datetime.utcnow() - timedelta(hours=1),
            profit_usd=50.0,
            product_id="ETH-USD",
            btc_usd_price_at_close=50000.0,
        )

        result = await get_realized_pnl(
            account_id=None,
            db=db_session,
            current_user=user,
        )
        assert result["alltime_profit_usd"] == 150.0
        # Today's profit should only include the recent one
        assert result["daily_profit_usd"] == 50.0

    @pytest.mark.asyncio
    async def test_returns_zeros_for_no_accounts(self, db_session):
        """Failure: user with no accounts returns all zeros."""
        from app.position_routers.position_query_router import get_realized_pnl

        user = User(
            email="noreal@test.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        result = await get_realized_pnl(
            account_id=None,
            db=db_session,
            current_user=user,
        )
        assert result["alltime_profit_usd"] == 0.0
        assert result["daily_profit_usd"] == 0.0
        assert result["ytd_profit_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_btc_pair_uses_profit_quote(self, db_session):
        """Edge case: BTC pair profit uses profit_quote for BTC calculation."""
        from app.position_routers.position_query_router import get_realized_pnl

        user, account = await _create_user_with_account(db_session)

        await _create_position(
            db_session, account,
            status="closed",
            closed_at=datetime.utcnow(),
            profit_usd=50.0,
            profit_quote=0.001,
            product_id="ETH-BTC",
            btc_usd_price_at_close=50000.0,
        )

        result = await get_realized_pnl(
            account_id=None,
            db=db_session,
            current_user=user,
        )
        assert result["alltime_profit_btc"] == 0.001
        assert result["daily_profit_btc"] == 0.001
