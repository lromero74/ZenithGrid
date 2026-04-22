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
            offset=0,
            db=db_session,
            account_id=None,
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
            offset=0,
            db=db_session,
            account_id=None,
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
            offset=0,
            db=db_session,
            account_id=None,
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
            offset=0,
            db=db_session,
            account_id=None,
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
            offset=0,
            db=db_session,
            account_id=None,
            current_user=user,
        )
        assert "no-cache" in response_mock.headers.get("Cache-Control", "")

    @pytest.mark.asyncio
    @patch("app.position_routers.helpers.compute_resize_budget", return_value=0.0)
    async def test_filters_by_account_id(self, mock_resize, db_session):
        """Happy path: account_id param returns only that account's positions."""
        from app.position_routers.position_query_router import get_positions

        user, account1 = await _create_user_with_account(db_session, "user1@example.com")
        account2 = Account(
            user_id=user.id, name="Account 2", type="cex",
            exchange="coinbase", is_active=True,
        )
        db_session.add(account2)
        await db_session.flush()

        pos1 = await _create_position(db_session, account1, status="open", product_id="ETH-BTC")
        await _create_position(db_session, account2, status="open", product_id="SOL-USDC")

        response_mock = MagicMock()
        response_mock.headers = {}

        result = await get_positions(
            response=response_mock,
            status="open",
            limit=50,
            offset=0,
            account_id=account1.id,
            db=db_session,
            current_user=user,
        )

        assert len(result) == 1
        assert result[0].id == pos1.id

    @pytest.mark.asyncio
    @patch("app.position_routers.helpers.compute_resize_budget", return_value=0.0)
    async def test_account_id_filter_rejects_inaccessible_account(self, mock_resize, db_session):
        """Failure case: account_id belonging to a different user returns 403."""
        from fastapi import HTTPException
        from app.position_routers.position_query_router import get_positions

        user1, account1 = await _create_user_with_account(db_session, "owner@example.com")
        user2, _ = await _create_user_with_account(db_session, "intruder@example.com")

        response_mock = MagicMock()
        response_mock.headers = {}

        with pytest.raises(HTTPException) as exc_info:
            await get_positions(
                response=response_mock,
                status="open",
                limit=50,
                offset=0,
                account_id=account1.id,  # user2 does not own this account
                db=db_session,
                current_user=user2,
            )
        assert exc_info.value.status_code == 403

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
            offset=0,
            db=db_session,
            account_id=None,
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
# GET /positions/{position_id}/ai-opinion
# =============================================================================


class TestGetPositionAiOpinion:
    """Tests for GET /positions/{position_id}/ai-opinion — Phase E tool-use transparency."""

    @pytest.mark.asyncio
    async def test_returns_most_recent_opinion(self, db_session):
        """Happy path: returns the latest AIOpinionLog for the position with tool_calls."""
        from app.models import AIOpinionLog
        from app.position_routers.position_query_router import get_position_ai_opinion

        user, account = await _create_user_with_account(db_session, "opinion1@test.com")
        bot = await _create_bot(db_session, user, account)
        pos = await _create_position(db_session, account, bot=bot)

        older = AIOpinionLog(
            user_id=user.id, account_id=account.id, bot_id=bot.id, position_id=pos.id,
            product_id=pos.product_id, signal="buy", confidence=60,
            reasoning="early read", ai_model="claude",
            created_at=datetime.utcnow() - timedelta(minutes=10),
        )
        newer = AIOpinionLog(
            user_id=user.id, account_id=account.id, bot_id=bot.id, position_id=pos.id,
            product_id=pos.product_id, signal="hold", confidence=80,
            reasoning="look at recent volume",
            ai_model="claude",
            tool_calls=[{"name": "get_candle_window", "input": {"granularity": "ONE_HOUR"},
                         "output_summary": "last 24 candles", "turn": 1}],
            created_at=datetime.utcnow(),
        )
        db_session.add_all([older, newer])
        await db_session.flush()

        result = await get_position_ai_opinion(
            position_id=pos.id, db=db_session, current_user=user,
        )
        assert result.signal == "hold"
        assert result.confidence == 80
        assert result.reasoning == "look at recent volume"
        assert result.ai_model == "claude"
        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "get_candle_window"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_opinion_logged(self, db_session):
        """Edge: position exists but has no ai_opinion_log rows → returns None.

        The Positions page renders the AI-reasoning expander for every row, so
        a missing opinion is the common case. A 404 here would spam the
        browser console; the endpoint returns null so React Query caches the
        absence cleanly.
        """
        from app.position_routers.position_query_router import get_position_ai_opinion

        user, account = await _create_user_with_account(db_session, "opinion2@test.com")
        bot = await _create_bot(db_session, user, account)
        pos = await _create_position(db_session, account, bot=bot)

        result = await get_position_ai_opinion(
            position_id=pos.id, db=db_session, current_user=user,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_position_not_found_returns_404(self, db_session):
        """Failure: non-existent position → 404."""
        from fastapi import HTTPException
        from app.position_routers.position_query_router import get_position_ai_opinion

        user, _ = await _create_user_with_account(db_session, "opinion3@test.com")

        with pytest.raises(HTTPException) as exc_info:
            await get_position_ai_opinion(
                position_id=99999, db=db_session, current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_user_isolation(self, db_session):
        """Failure: a different user cannot read another user's opinion log → 404."""
        from fastapi import HTTPException
        from app.models import AIOpinionLog
        from app.position_routers.position_query_router import get_position_ai_opinion

        user1, account1 = await _create_user_with_account(db_session, "opinion-owner@test.com")
        user2, _ = await _create_user_with_account(db_session, "opinion-other@test.com")
        bot = await _create_bot(db_session, user1, account1)
        pos = await _create_position(db_session, account1, bot=bot)

        db_session.add(AIOpinionLog(
            user_id=user1.id, account_id=account1.id, bot_id=bot.id, position_id=pos.id,
            product_id=pos.product_id, signal="buy", confidence=90,
            reasoning="owner-only", ai_model="claude",
            created_at=datetime.utcnow(),
        ))
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_position_ai_opinion(
                position_id=pos.id, db=db_session, current_user=user2,
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

        # Pin "now" to a fixed past date at 15:00 UTC so boundaries are deterministic
        fixed_now = datetime(2025, 8, 20, 15, 0, 0)

        user, account = await _create_user_with_account(db_session)

        await _create_position(
            db_session, account,
            status="closed",
            closed_at=fixed_now - timedelta(days=400),
            profit_usd=100.0,
            product_id="ETH-USD",
            btc_usd_price_at_close=50000.0,
        )
        # Closed today at 10:00 — well after midnight, well before "now"
        await _create_position(
            db_session, account,
            status="closed",
            closed_at=fixed_now.replace(hour=10),
            profit_usd=50.0,
            product_id="ETH-USD",
            btc_usd_price_at_close=50000.0,
        )

        # Patch only within the specific module to avoid breaking SQLAlchemy's
        # datetime type processor which uses isinstance(value, datetime.datetime).
        with patch("app.position_routers.position_query_router.datetime") as mock_dt:
            mock_dt.utcnow.return_value = fixed_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
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

    @pytest.mark.asyncio
    async def test_null_profit_quote_falls_back_to_profit_usd_for_usd_pairs(self, db_session):
        """Bug fix: NULL profit_quote on USD pairs falls back to profit_usd."""
        from app.position_routers.position_query_router import get_realized_pnl

        user, account = await _create_user_with_account(db_session)

        # Position with profit_usd set but profit_quote=NULL (dust-closed/force-closed)
        await _create_position(
            db_session, account,
            status="closed",
            closed_at=datetime.utcnow(),
            product_id="BAND-USD",
            profit_usd=0.17,
            profit_quote=None,  # NULL — this is the bug scenario
        )

        result = await get_realized_pnl(
            account_id=None,
            db=db_session,
            current_user=user,
        )
        # Should use profit_usd as fallback for USD pair
        assert result["alltime_profit_usd"] == pytest.approx(0.17, abs=0.01)
        # by_quote should also reflect the fallback
        assert result["alltime_profit_by_quote"].get("USD", 0) == pytest.approx(0.17, abs=0.01)

    @pytest.mark.asyncio
    async def test_null_profit_quote_usdc_pair_falls_back(self, db_session):
        """Edge case: USDC pair with NULL profit_quote also falls back to profit_usd."""
        from app.position_routers.position_query_router import get_realized_pnl

        user, account = await _create_user_with_account(db_session)

        await _create_position(
            db_session, account,
            status="closed",
            closed_at=datetime.utcnow(),
            product_id="ETH-USDC",
            profit_usd=25.0,
            profit_quote=None,
        )

        result = await get_realized_pnl(
            account_id=None,
            db=db_session,
            current_user=user,
        )
        assert result["alltime_profit_by_quote"].get("USDC", 0) == pytest.approx(25.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_null_profit_quote_btc_pair_defaults_to_zero(self, db_session):
        """Edge case: BTC pair with NULL profit_quote defaults to 0 (no fallback)."""
        from app.position_routers.position_query_router import get_realized_pnl

        user, account = await _create_user_with_account(db_session)

        await _create_position(
            db_session, account,
            status="closed",
            closed_at=datetime.utcnow(),
            product_id="ETH-BTC",
            profit_usd=50.0,
            profit_quote=None,  # NULL on non-USD pair
        )

        result = await get_realized_pnl(
            account_id=None,
            db=db_session,
            current_user=user,
        )
        # BTC pair should NOT fall back — pq stays 0
        assert result["alltime_profit_by_quote"].get("BTC", 0) == 0.0
        # profit_usd is still counted
        assert result["alltime_profit_usd"] == pytest.approx(50.0, abs=0.01)


# =============================================================================
# coin_category population from blacklist
# =============================================================================


class TestCoinCategoryFromBlacklist:
    """Tests that coin_category is set correctly based on BlacklistedCoin reason prefix."""

    @pytest.mark.asyncio
    @patch("app.position_routers.helpers.compute_resize_budget", return_value=0.0)
    async def test_coin_category_approved_prefix(self, mock_resize, db_session):
        """Happy path: [APPROVED] reason sets coin_category='APPROVED'."""
        from app.position_routers.position_query_router import get_positions

        user, account = await _create_user_with_account(db_session, "cat_approved@example.com")
        await _create_position(db_session, account, status="open", product_id="LINK-USD")

        bl = BlacklistedCoin(
            user_id=user.id, symbol="LINK", reason="[APPROVED] solid fundamentals"
        )
        db_session.add(bl)
        await db_session.flush()

        response_mock = MagicMock()
        response_mock.headers = {}
        result = await get_positions(
            response=response_mock, status=None, limit=50, offset=0, db=db_session, account_id=None,
            current_user=user,
        )
        assert len(result) == 1
        assert result[0].coin_category == "APPROVED"
        assert result[0].is_blacklisted is True

    @pytest.mark.asyncio
    @patch("app.position_routers.helpers.compute_resize_budget", return_value=0.0)
    async def test_coin_category_meme_prefix(self, mock_resize, db_session):
        """Happy path: [MEME] reason sets coin_category='MEME'."""
        from app.position_routers.position_query_router import get_positions

        user, account = await _create_user_with_account(db_session, "cat_meme@example.com")
        await _create_position(db_session, account, status="open", product_id="DOGE-USD")

        bl = BlacklistedCoin(
            user_id=user.id, symbol="DOGE", reason="[MEME] dog coin"
        )
        db_session.add(bl)
        await db_session.flush()

        response_mock = MagicMock()
        response_mock.headers = {}
        result = await get_positions(
            response=response_mock, status=None, limit=50, offset=0, db=db_session, account_id=None,
            current_user=user,
        )
        assert len(result) == 1
        assert result[0].coin_category == "MEME"

    @pytest.mark.asyncio
    @patch("app.position_routers.helpers.compute_resize_budget", return_value=0.0)
    async def test_coin_category_no_prefix_falls_back_to_blacklisted(self, mock_resize, db_session):
        """Edge case: reason with no category prefix defaults to 'BLACKLISTED'."""
        from app.position_routers.position_query_router import get_positions

        user, account = await _create_user_with_account(db_session, "cat_nopfx@example.com")
        await _create_position(db_session, account, status="open", product_id="XYZ-USD")

        bl = BlacklistedCoin(
            user_id=user.id, symbol="XYZ", reason="some reason with no prefix"
        )
        db_session.add(bl)
        await db_session.flush()

        response_mock = MagicMock()
        response_mock.headers = {}
        result = await get_positions(
            response=response_mock, status=None, limit=50, offset=0, db=db_session, account_id=None,
            current_user=user,
        )
        assert len(result) == 1
        assert result[0].coin_category == "BLACKLISTED"

    @pytest.mark.asyncio
    @patch("app.position_routers.helpers.compute_resize_budget", return_value=0.0)
    async def test_coin_category_none_when_not_in_blacklist(self, mock_resize, db_session):
        """Failure case: position not in blacklist gets coin_category=None."""
        from app.position_routers.position_query_router import get_positions

        user, account = await _create_user_with_account(db_session, "cat_none@example.com")
        await _create_position(db_session, account, status="open", product_id="ETH-USD")

        response_mock = MagicMock()
        response_mock.headers = {}
        result = await get_positions(
            response=response_mock, status=None, limit=50, offset=0, db=db_session, account_id=None,
            current_user=user,
        )
        assert len(result) == 1
        assert result[0].coin_category is None
        assert result[0].is_blacklisted is False


# =============================================================================
# Pagination: offset parameter
# =============================================================================


class TestGetPositionsPagination:
    """Tests for limit/offset pagination on GET /positions/."""

    @pytest.mark.asyncio
    @patch("app.position_routers.helpers.compute_resize_budget", return_value=0.0)
    async def test_offset_skips_first_positions(self, mock_resize, db_session):
        """Happy path: offset skips the first N positions."""
        from app.position_routers.position_query_router import get_positions

        user, account = await _create_user_with_account(db_session, "pagination@example.com")
        # Create 5 positions
        for i in range(5):
            await _create_position(
                db_session, account, status="open",
                product_id="ETH-USD",
                opened_at=datetime(2025, 1, i + 1),
            )

        response_mock = MagicMock()
        response_mock.headers = {}

        # With offset=2, should get 3 positions (oldest 3 since order is desc by opened_at)
        result = await get_positions(
            response=response_mock, status=None, limit=50, offset=2,
            db=db_session, account_id=None,
            current_user=user,
        )
        assert len(result) == 3

    @pytest.mark.asyncio
    @patch("app.position_routers.helpers.compute_resize_budget", return_value=0.0)
    async def test_limit_caps_results(self, mock_resize, db_session):
        """Happy path: limit caps result count."""
        from app.position_routers.position_query_router import get_positions

        user, account = await _create_user_with_account(db_session, "paginat2@example.com")
        for i in range(5):
            await _create_position(db_session, account, status="open", product_id="ETH-USD")

        response_mock = MagicMock()
        response_mock.headers = {}

        result = await get_positions(
            response=response_mock, status=None, limit=3, offset=0,
            db=db_session, account_id=None,
            current_user=user,
        )
        assert len(result) == 3

    @pytest.mark.asyncio
    @patch("app.position_routers.helpers.compute_resize_budget", return_value=0.0)
    async def test_offset_beyond_count_returns_empty(self, mock_resize, db_session):
        """Edge case: offset larger than result count returns empty list."""
        from app.position_routers.position_query_router import get_positions

        user, account = await _create_user_with_account(db_session, "paginat3@example.com")
        await _create_position(db_session, account, status="open", product_id="ETH-USD")

        response_mock = MagicMock()
        response_mock.headers = {}

        result = await get_positions(
            response=response_mock, status=None, limit=50, offset=999,
            db=db_session, account_id=None,
            current_user=user,
        )
        assert result == []
