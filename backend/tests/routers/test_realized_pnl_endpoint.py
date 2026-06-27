"""
Tests for the /positions/realized-pnl endpoint.

Verifies that SQL conditional aggregation matches the previous
Python-loop logic for all time period buckets.
"""

import pytest
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Position, Account, User, Bot
from app.utils.timeutil import utcnow


@pytest.fixture
async def setup_closed_positions(db_session):
    """Create closed positions across multiple time periods for testing."""
    now = utcnow()
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Create a user and account
    user = User(email="test@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    account = Account(
        user_id=user.id, name="Test Account", type="cex", is_active=True,
    )
    db_session.add(account)
    await db_session.flush()

    bot = Bot(
        name="Test Bot", user_id=user.id, account_id=account.id,
        strategy_type="dca", strategy_config={}, product_id="ETH-BTC",
        is_active=False,
    )
    db_session.add(bot)
    await db_session.flush()

    positions = []

    # Closed today (USD pair)
    positions.append(Position(
        bot_id=bot.id, account_id=account.id, user_id=user.id,
        product_id="ETH-USD", status="closed",
        opened_at=start_of_today - timedelta(hours=2),
        closed_at=start_of_today + timedelta(hours=1),
        profit_usd=10.0, profit_quote=None,
        initial_quote_balance=100.0, max_quote_allowed=50.0,
        total_quote_spent=100.0, total_base_acquired=1.0,
    ))
    # Closed today (BTC pair)
    positions.append(Position(
        bot_id=bot.id, account_id=account.id, user_id=user.id,
        product_id="SOL-BTC", status="closed",
        opened_at=start_of_today - timedelta(hours=3),
        closed_at=start_of_today + timedelta(hours=2),
        profit_usd=5.0, profit_quote=0.0001,
        initial_quote_balance=0.01, max_quote_allowed=0.005,
        total_quote_spent=0.01, total_base_acquired=0.5,
    ))
    # Closed yesterday
    positions.append(Position(
        bot_id=bot.id, account_id=account.id, user_id=user.id,
        product_id="ADA-USDC", status="closed",
        opened_at=start_of_today - timedelta(days=2),
        closed_at=start_of_today - timedelta(hours=12),
        profit_usd=-3.0, profit_quote=None,
        initial_quote_balance=50.0, max_quote_allowed=25.0,
        total_quote_spent=50.0, total_base_acquired=100.0,
    ))
    # Closed last week
    positions.append(Position(
        bot_id=bot.id, account_id=account.id, user_id=user.id,
        product_id="MATIC-USDT", status="closed",
        opened_at=start_of_today - timedelta(days=10),
        closed_at=start_of_today - timedelta(days=4),
        profit_usd=7.0, profit_quote=None,
        initial_quote_balance=80.0, max_quote_allowed=40.0,
        total_quote_spent=80.0, total_base_acquired=50.0,
    ))
    # Closed last month
    positions.append(Position(
        bot_id=bot.id, account_id=account.id, user_id=user.id,
        product_id="DOT-BTC", status="closed",
        opened_at=start_of_today - timedelta(days=45),
        closed_at=start_of_today - timedelta(days=15),
        profit_usd=0.0, profit_quote=0.0005,
        initial_quote_balance=0.02, max_quote_allowed=0.01,
        total_quote_spent=0.02, total_base_acquired=2.0,
    ))
    # Closed 2 years ago (alltime only)
    positions.append(Position(
        bot_id=bot.id, account_id=account.id, user_id=user.id,
        product_id="BTC-USD", status="closed",
        opened_at=start_of_today - timedelta(days=800),
        closed_at=start_of_today - timedelta(days=730),
        profit_usd=-20.0, profit_quote=None,
        initial_quote_balance=200.0, max_quote_allowed=100.0,
        total_quote_spent=200.0, total_base_acquired=0.004,
    ))

    for p in positions:
        db_session.add(p)
    await db_session.flush()
    await db_session.commit()

    return {"user": user, "account": account, "positions": positions}


@pytest.mark.asyncio
class TestRealizedPnlAggregation:
    """Tests for realized-pnl SQL conditional aggregation."""

    async def test_happy_path_all_periods(
        self, db_session, setup_closed_positions
    ):
        """Happy path: returns profit data for all time periods."""
        from app.position_routers.position_query_router import get_realized_pnl

        user = setup_closed_positions["user"]
        account = setup_closed_positions["account"]

        mock_user = MagicMock()
        mock_user.id = user.id

        result = await get_realized_pnl(
            account_id=account.id,
            db=db_session,
            current_user=mock_user,
        )

        # Should have keys for all 11 periods
        for period in [
            "daily", "yesterday", "last_week", "last_month",
            "last_quarter", "last_year", "wtd", "mtd", "qtd",
            "ytd", "alltime",
        ]:
            assert f"{period}_profit_usd" in result
            assert f"{period}_profit_btc" in result
            assert f"{period}_profit_by_quote" in result

        # Daily: 10.0 (ETH-USD) + 5.0 (SOL-BTC) = 15.0
        assert result["daily_profit_usd"] == pytest.approx(15.0)
        # alltime should include every position
        assert result["alltime_profit_usd"] == pytest.approx(
            10.0 + 5.0 - 3.0 + 7.0 + 0.0 - 20.0  # = -1.0
        )

    async def test_requested_account_excludes_same_and_different_user_accounts(
        self, db_session, setup_closed_positions
    ):
        """Financial aggregates never bleed across account boundaries."""
        from app.position_routers.position_query_router import get_realized_pnl

        owner = setup_closed_positions["user"]
        requested_account = setup_closed_positions["account"]
        other_user = User(email="other-pnl@example.com", hashed_password="x")
        db_session.add(other_user)
        await db_session.flush()

        for account_owner, suffix in ((owner, "same-user"), (other_user, "other-user")):
            account = Account(
                user_id=account_owner.id,
                name=f"Excluded {suffix}",
                type="cex",
                is_active=True,
            )
            db_session.add(account)
            await db_session.flush()
            bot = Bot(
                name=f"Excluded {suffix}",
                user_id=account_owner.id,
                account_id=account.id,
                strategy_type="dca",
                strategy_config={},
                product_id="BTC-USD",
                is_active=False,
            )
            db_session.add(bot)
            await db_session.flush()
            db_session.add(Position(
                bot_id=bot.id,
                account_id=account.id,
                user_id=account_owner.id,
                product_id="BTC-USD",
                status="closed",
                opened_at=utcnow() - timedelta(hours=2),
                closed_at=utcnow() - timedelta(hours=1),
                profit_usd=9999.0,
                initial_quote_balance=100.0,
                max_quote_allowed=50.0,
                total_quote_spent=100.0,
                total_base_acquired=0.001,
            ))
        await db_session.commit()

        current_user = MagicMock(id=owner.id)
        result = await get_realized_pnl(
            account_id=requested_account.id,
            db=db_session,
            current_user=current_user,
        )

        assert result["alltime_profit_usd"] == pytest.approx(-1.0)

    async def test_daily_excludes_yesterday_positions(
        self, db_session, setup_closed_positions
    ):
        """Daily should only include positions closed since midnight UTC."""
        from app.position_routers.position_query_router import get_realized_pnl

        user = setup_closed_positions["user"]
        account = setup_closed_positions["account"]

        mock_user = MagicMock()
        mock_user.id = user.id

        result = await get_realized_pnl(
            account_id=account.id,
            db=db_session,
            current_user=mock_user,
        )

        # Yesterday: only ADA-USDC at -3.0
        assert result["yesterday_profit_usd"] == pytest.approx(-3.0)
        # Daily should NOT include yesterday's -3.0
        assert result["daily_profit_usd"] == pytest.approx(15.0)

    async def test_per_quote_breakdown(
        self, db_session, setup_closed_positions
    ):
        """Per-quote breakdown correctly sums profit_quote per currency."""
        from app.position_routers.position_query_router import get_realized_pnl

        user = setup_closed_positions["user"]
        account = setup_closed_positions["account"]

        mock_user = MagicMock()
        mock_user.id = user.id

        result = await get_realized_pnl(
            account_id=account.id,
            db=db_session,
            current_user=mock_user,
        )

        daily_by_quote = result["daily_profit_by_quote"]
        # ETH-USD contributes USD, SOL-BTC contributes BTC
        assert "USD" in daily_by_quote
        assert "BTC" in daily_by_quote
        assert daily_by_quote["USD"] == pytest.approx(10.0)
        assert daily_by_quote["BTC"] == pytest.approx(0.0001)

    async def test_empty_positions_returns_zeros(
        self, db_session
    ):
        """No closed positions returns zero/empty for all periods."""
        from app.position_routers.position_query_router import get_realized_pnl

        user = User(email="empty@example.com", hashed_password="x")
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id, name="Empty Account", type="cex", is_active=True,
        )
        db_session.add(account)
        await db_session.flush()

        mock_user = MagicMock()
        mock_user.id = user.id

        result = await get_realized_pnl(
            account_id=account.id,
            db=db_session,
            current_user=mock_user,
        )

        for period in [
            "daily", "yesterday", "last_week", "alltime",
        ]:
            assert result[f"{period}_profit_usd"] == 0.0
            assert result[f"{period}_profit_btc"] == 0.0
            assert result[f"{period}_profit_by_quote"] == {}

    async def test_no_account_returns_empty(
        self, db_session
    ):
        """User with no accessible accounts returns empty result."""
        from app.position_routers.position_query_router import get_realized_pnl

        user = User(email="noacct@example.com", hashed_password="x")
        db_session.add(user)
        await db_session.flush()

        mock_user = MagicMock()
        mock_user.id = user.id

        result = await get_realized_pnl(
            account_id=None,
            db=db_session,
            current_user=mock_user,
        )

        assert result["alltime_profit_usd"] == 0.0
        assert result["daily_profit_btc"] == 0.0

    async def test_btc_profit_from_profit_quote(
        self, db_session, setup_closed_positions
    ):
        """BTC profit_btc column reads from native BTC in by_quote."""
        from app.position_routers.position_query_router import get_realized_pnl

        user = setup_closed_positions["user"]
        account = setup_closed_positions["account"]

        mock_user = MagicMock()
        mock_user.id = user.id

        result = await get_realized_pnl(
            account_id=account.id,
            db=db_session,
            current_user=mock_user,
        )

        # SOL-BTC has profit_quote=0.0001, DOT-BTC has profit_quote=0.0005
        assert result["alltime_profit_btc"] == pytest.approx(0.0001 + 0.0005)

    async def test_wtd_mtd_qtd_ytd_are_cumulative(
        self, db_session, setup_closed_positions
    ):
        """WTD/MTD/QTD/YTD should include all positions from period start."""
        from app.position_routers.position_query_router import get_realized_pnl

        user = setup_closed_positions["user"]
        account = setup_closed_positions["account"]

        mock_user = MagicMock()
        mock_user.id = user.id

        result = await get_realized_pnl(
            account_id=account.id,
            db=db_session,
            current_user=mock_user,
        )

        # YTD should include everything closed this year
        assert result["ytd_profit_usd"] >= result["daily_profit_usd"]
        assert result["ytd_profit_usd"] >= result["mtd_profit_usd"]


@pytest.mark.asyncio
async def test_page_summary_passes_required_account_to_every_source():
    from app.position_routers.position_query_router import clear_positions_summary_cache, get_positions_summary

    clear_positions_summary_cache()
    db = MagicMock()
    user = MagicMock(id=3)
    with (
        patch(
            "app.position_routers.position_query_router.get_completed_trades_stats",
            new=AsyncMock(return_value={"total_trades": 2}),
        ) as completed,
        patch(
            "app.position_routers.position_query_router.get_realized_pnl",
            new=AsyncMock(return_value={"alltime_profit_usd": 4.0}),
        ) as realized,
        patch(
            "app.position_routers.position_query_router.get_account_balances",
            new=AsyncMock(return_value={"USD": 20.0}),
        ) as balances,
        patch(
            "app.position_routers.position_query_router.accessible_account_ids",
            new=AsyncMock(return_value=[7]),
        ),
    ):
        result = await get_positions_summary(account_id=7, db=db, current_user=user)

    completed.assert_awaited_once_with(7, db, user)
    realized.assert_awaited_once_with(7, db, user)
    balances.assert_awaited_once_with(db, user, 7)
    assert result == {
        "completed_stats": {"total_trades": 2},
        "realized_pnl": {"alltime_profit_usd": 4.0},
        "balances": {"USD": 20.0},
    }


@pytest.mark.asyncio
async def test_page_summary_reuses_short_account_cache():
    from app.position_routers.position_query_router import clear_positions_summary_cache, get_positions_summary

    clear_positions_summary_cache()
    db = MagicMock()
    user = MagicMock(id=3)
    with (
        patch(
            "app.position_routers.position_query_router.get_completed_trades_stats",
            new=AsyncMock(return_value={"total_trades": 2}),
        ) as completed,
        patch(
            "app.position_routers.position_query_router.get_realized_pnl",
            new=AsyncMock(return_value={"alltime_profit_usd": 4.0}),
        ) as realized,
        patch(
            "app.position_routers.position_query_router.get_account_balances",
            new=AsyncMock(return_value={"USD": 20.0}),
        ) as balances,
        patch(
            "app.position_routers.position_query_router.accessible_account_ids",
            new=AsyncMock(return_value=[7]),
        ),
    ):
        first = await get_positions_summary(account_id=7, db=db, current_user=user)
        second = await get_positions_summary(account_id=7, db=db, current_user=user)

    assert second == first
    completed.assert_awaited_once()
    realized.assert_awaited_once()
    balances.assert_awaited_once()
    clear_positions_summary_cache()
