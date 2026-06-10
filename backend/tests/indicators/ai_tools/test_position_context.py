"""Tests for the get_position_context tool.

Covers:
- Happy path — open position with entry, DCAs, and time held
- Edge — no position returns a note
- Edge — sub-minute hold returns zero minutes
- Failure — position with no trades returns dca_count=0
"""

from datetime import timedelta
from app.utils.timeutil import utcnow

import pytest

from app.indicators.ai_tools import REGISTRY, ToolContext, execute
from app.models import Account, Bot, Position, Trade, User


async def _make_user(db):
    user = User(email="t@t.com", hashed_password="x")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_account(db, user):
    account = Account(user_id=user.id, name="Test", type="cex", exchange="coinbase")
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def _make_bot(db, account, user):
    bot = Bot(account_id=account.id, user_id=user.id, name="Test Bot",
              product_id="ETH-USD", strategy_type="indicator_based", strategy_config={})
    db.add(bot)
    await db.commit()
    await db.refresh(bot)
    return bot


async def _make_position(db, bot, account, user, *, opened_minutes_ago=30, avg_price=100.0):
    position = Position(
        bot_id=bot.id,
        account_id=account.id,
        user_id=user.id,
        product_id="ETH-USD",
        status="open",
        opened_at=utcnow() - timedelta(minutes=opened_minutes_ago),
        average_buy_price=avg_price,
        entry_price=avg_price,
        total_quote_spent=100.0,
        total_base_acquired=1.0,
        highest_price_since_entry=avg_price * 1.05,
        entry_stop_loss=avg_price * 0.95,
        entry_take_profit_target=avg_price * 1.1,
    )
    db.add(position)
    await db.commit()
    await db.refresh(position)
    return position


async def _add_dca(db, position, *, count=1):
    for i in range(count):
        t = Trade(position_id=position.id, side="buy", quote_amount=50.0,
                  base_amount=0.5, price=100.0, trade_type="dca")
        db.add(t)
    await db.commit()


class TestGetPositionContext:
    async def test_returns_entry_time_held_and_dca_count(self, db_session):
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        position = await _make_position(db_session, bot, account, user,
                                        opened_minutes_ago=90, avg_price=100.0)
        await _add_dca(db_session, position, count=2)

        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD",
            current_price=110.0, bot=bot, position=position,
            account_id=account.id, is_sell_check=True,
        )
        result = await execute("get_position_context", {}, ctx)

        assert result["product_id"] == "ETH-USD"
        assert result["average_buy_price"] == 100.0
        assert 89 <= result["minutes_held"] <= 91
        assert result["dca_count"] == 2
        assert result["current_price"] == 110.0
        # 10% unrealized gain
        assert 9.9 <= result["unrealized_pnl_pct"] <= 10.1
        assert result["exit_targets"]["stop_loss"] == pytest.approx(95.0)
        assert result["exit_targets"]["take_profit"] == pytest.approx(110.0)

    async def test_no_position_returns_note(self, db_session):
        user = await _make_user(db_session)
        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD",
            current_price=100.0, position=None,
        )
        result = await execute("get_position_context", {}, ctx)
        assert "note" in result
        assert "position" in result["note"].lower()

    async def test_sub_minute_hold_returns_zero_minutes(self, db_session):
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        position = await _make_position(db_session, bot, account, user,
                                        opened_minutes_ago=0)
        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD",
            current_price=100.0, bot=bot, position=position, account_id=account.id,
        )
        result = await execute("get_position_context", {}, ctx)
        assert result["minutes_held"] == 0

    async def test_position_no_dca_returns_zero_count(self, db_session):
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        position = await _make_position(db_session, bot, account, user)
        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD",
            current_price=100.0, bot=bot, position=position, account_id=account.id,
        )
        result = await execute("get_position_context", {}, ctx)
        assert result["dca_count"] == 0


class TestRegistryExposure:
    def test_tool_is_registered(self):
        assert "get_position_context" in REGISTRY
        tool = REGISTRY["get_position_context"]
        assert tool.input_schema["type"] == "object"
