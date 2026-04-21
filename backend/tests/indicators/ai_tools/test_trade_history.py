"""Tests for the get_trade_history tool.

Returns recent closed positions for the current product + user, plus a
summary stat block (count, win rate, avg PnL%, avg hold minutes).

Covers:
- Happy path — closed positions returned newest-first with summary stats
- Filter — only closed positions for this user + product
- Filter — lookback_days filters by closed_at
- Edge — no closed positions returns empty list + zeroed summary
- Validation — n clamped to 1..20
"""

from datetime import datetime, timedelta

from app.indicators.ai_tools import REGISTRY, ToolContext, execute
from app.models import Account, Bot, Position, User


async def _make_user(db, email="h@h.com"):
    user = User(email=email, hashed_password="x")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_account(db, user):
    account = Account(user_id=user.id, name="A", type="cex", exchange="coinbase")
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def _make_bot(db, account, user):
    bot = Bot(account_id=account.id, user_id=user.id, name="Bot",
              product_id="ETH-USD", strategy_type="indicator_based", strategy_config={})
    db.add(bot)
    await db.commit()
    await db.refresh(bot)
    return bot


async def _make_closed_position(
    db, bot, account, user, *,
    product_id="ETH-USD",
    profit_pct=1.5,
    hold_minutes=60,
    closed_days_ago=1,
    exit_reason="take_profit",
):
    closed_at = datetime.utcnow() - timedelta(days=closed_days_ago)
    opened_at = closed_at - timedelta(minutes=hold_minutes)
    p = Position(
        bot_id=bot.id,
        account_id=account.id,
        user_id=user.id,
        product_id=product_id,
        status="closed",
        opened_at=opened_at,
        closed_at=closed_at,
        average_buy_price=100.0,
        entry_price=100.0,
        sell_price=100.0 * (1 + profit_pct / 100),
        total_quote_spent=100.0,
        total_base_acquired=1.0,
        profit_percentage=profit_pct,
        exit_reason=exit_reason,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


class TestGetTradeHistory:
    async def test_happy_path_newest_first_with_summary(self, db_session):
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        await _make_closed_position(
            db_session, bot, account, user, profit_pct=2.0,
            hold_minutes=60, closed_days_ago=3,
        )
        await _make_closed_position(
            db_session, bot, account, user, profit_pct=-1.0,
            hold_minutes=120, closed_days_ago=2,
        )
        await _make_closed_position(
            db_session, bot, account, user, profit_pct=0.5,
            hold_minutes=30, closed_days_ago=1,
        )

        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_trade_history", {"lookback_days": 7, "n": 10}, ctx,
        )
        assert len(result["trades"]) == 3
        # Newest first: most recent closed_at is 1 day ago
        pnls = [t["profit_percentage"] for t in result["trades"]]
        assert pnls == [0.5, -1.0, 2.0]
        summary = result["summary"]
        assert summary["count"] == 3
        assert summary["win_count"] == 2
        assert summary["loss_count"] == 1
        assert abs(summary["avg_pnl_pct"] - ((2.0 - 1.0 + 0.5) / 3)) < 1e-6
        assert abs(summary["avg_hold_minutes"] - ((60 + 120 + 30) / 3)) < 1e-6

    async def test_filters_out_other_products(self, db_session):
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        await _make_closed_position(
            db_session, bot, account, user, product_id="ETH-USD",
        )
        await _make_closed_position(
            db_session, bot, account, user, product_id="BTC-USD",
        )

        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_trade_history", {"lookback_days": 7, "n": 10}, ctx,
        )
        assert result["summary"]["count"] == 1
        assert result["trades"][0]["product_id"] == "ETH-USD"

    async def test_filters_out_other_users(self, db_session):
        owner = await _make_user(db_session, email="owner@h.com")
        other = await _make_user(db_session, email="other@h.com")
        account = await _make_account(db_session, owner)
        bot = await _make_bot(db_session, account, owner)
        # other user has a position on the same product — must NOT be returned
        other_account = await _make_account(db_session, other)
        other_bot = await _make_bot(db_session, other_account, other)
        await _make_closed_position(db_session, bot, account, owner)
        await _make_closed_position(db_session, other_bot, other_account, other)

        ctx = ToolContext(
            db=db_session, user_id=owner.id, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_trade_history", {"lookback_days": 7, "n": 10}, ctx,
        )
        assert result["summary"]["count"] == 1

    async def test_open_positions_excluded(self, db_session):
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        await _make_closed_position(db_session, bot, account, user)
        # Open position on same product — must NOT be returned
        p = Position(
            bot_id=bot.id, account_id=account.id, user_id=user.id,
            product_id="ETH-USD", status="open",
            opened_at=datetime.utcnow(), average_buy_price=100.0,
            total_quote_spent=100.0, total_base_acquired=1.0,
        )
        db_session.add(p)
        await db_session.commit()

        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_trade_history", {"lookback_days": 7, "n": 10}, ctx,
        )
        assert result["summary"]["count"] == 1

    async def test_lookback_days_filters_old_trades(self, db_session):
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        await _make_closed_position(
            db_session, bot, account, user, closed_days_ago=30,
        )
        await _make_closed_position(
            db_session, bot, account, user, closed_days_ago=1,
        )

        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_trade_history", {"lookback_days": 7, "n": 10}, ctx,
        )
        assert result["summary"]["count"] == 1

    async def test_empty_history_returns_zeroed_summary(self, db_session):
        user = await _make_user(db_session)
        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_trade_history", {"lookback_days": 7, "n": 10}, ctx,
        )
        assert result["trades"] == []
        assert result["summary"] == {
            "count": 0, "win_count": 0, "loss_count": 0,
            "win_rate_pct": 0.0, "avg_pnl_pct": 0.0, "avg_hold_minutes": 0.0,
        }

    async def test_n_clamped_to_max(self, db_session):
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        for i in range(25):
            await _make_closed_position(
                db_session, bot, account, user, closed_days_ago=i % 6 + 1,
            )

        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD", current_price=100.0,
        )
        result = await execute(
            "get_trade_history", {"lookback_days": 30, "n": 100}, ctx,
        )
        assert len(result["trades"]) <= 20


class TestRegistry:
    def test_tool_is_registered(self):
        assert "get_trade_history" in REGISTRY
