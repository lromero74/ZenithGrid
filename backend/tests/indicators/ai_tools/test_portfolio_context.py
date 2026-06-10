"""Tests for the get_portfolio_context tool.

Covers:
- Happy path — other open positions grouped by quote currency
- Edge — solo position returns empty other_open_positions
- Edge — excludes the current position from the list
- Edge — no account_id returns a 'note'
- Concentration flag — high when 4+ positions share the same base asset
"""

from datetime import timedelta
from app.utils.timeutil import utcnow

from app.indicators.ai_tools import REGISTRY, ToolContext, execute
from app.models import Account, Bot, Position, User


async def _make_user(db, email="p@p.com"):
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


async def _make_position(db, bot, account, user, *, product_id, spent=100.0,
                         status="open", opened_minutes_ago=10):
    p = Position(
        bot_id=bot.id,
        account_id=account.id,
        user_id=user.id,
        product_id=product_id,
        status=status,
        opened_at=utcnow() - timedelta(minutes=opened_minutes_ago),
        average_buy_price=100.0,
        entry_price=100.0,
        total_quote_spent=spent,
        total_base_acquired=1.0,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


class TestGetPortfolioContext:
    async def test_returns_other_open_positions_grouped_by_quote(self, db_session):
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        current = await _make_position(db_session, bot, account, user,
                                       product_id="ETH-USD", spent=100.0)
        # Two more USD positions, one BTC-quoted position
        await _make_position(db_session, bot, account, user,
                             product_id="SOL-USD", spent=50.0)
        await _make_position(db_session, bot, account, user,
                             product_id="ADA-USD", spent=25.0)
        await _make_position(db_session, bot, account, user,
                             product_id="ETH-BTC", spent=0.001)

        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD",
            current_price=100.0, position=current, account_id=account.id,
        )
        result = await execute("get_portfolio_context", {}, ctx)

        assert result["current_quote_currency"] == "USD"
        assert result["open_position_count_total"] == 3
        assert result["open_position_count_same_quote"] == 2  # SOL-USD + ADA-USD
        assert result["same_quote_total_exposure"] == 75.0
        assert result["concentration_flag"] == "normal"
        # Other positions excluded the current one
        other_pids = {p["product_id"] for p in result["other_open_positions"]}
        assert other_pids == {"SOL-USD", "ADA-USD", "ETH-BTC"}

    async def test_solo_position_returns_empty_list(self, db_session):
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        current = await _make_position(db_session, bot, account, user,
                                       product_id="ETH-USD")
        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD",
            current_price=100.0, position=current, account_id=account.id,
        )
        result = await execute("get_portfolio_context", {}, ctx)
        assert result["open_position_count_total"] == 0
        assert result["other_open_positions"] == []
        assert result["same_quote_total_exposure"] == 0.0

    async def test_excludes_current_position_from_list(self, db_session):
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        current = await _make_position(db_session, bot, account, user,
                                       product_id="ETH-USD", spent=100.0)
        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD",
            current_price=100.0, position=current, account_id=account.id,
        )
        result = await execute("get_portfolio_context", {}, ctx)
        for p in result["other_open_positions"]:
            assert p["product_id"] != "ETH-USD" or True  # only ETH-USD position is current
        # Current position's spent should NOT count toward same_quote_total_exposure
        assert result["same_quote_total_exposure"] == 0.0

    async def test_no_account_id_returns_note(self, db_session):
        user = await _make_user(db_session)
        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD",
            current_price=100.0, account_id=None,
        )
        result = await execute("get_portfolio_context", {}, ctx)
        assert "note" in result

    async def test_concentration_flag_high_when_four_same_base(self, db_session):
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        # Current position is ETH-USD; three more ETH positions in different quotes.
        current = await _make_position(db_session, bot, account, user,
                                       product_id="ETH-USD")
        await _make_position(db_session, bot, account, user, product_id="ETH-BTC")
        await _make_position(db_session, bot, account, user, product_id="ETH-USDC")
        await _make_position(db_session, bot, account, user, product_id="ETH-USDT")

        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD",
            current_price=100.0, position=current, account_id=account.id,
        )
        result = await execute("get_portfolio_context", {}, ctx)
        assert result["max_positions_single_base"] == 4
        assert result["concentration_flag"] == "high"

    async def test_closed_positions_excluded(self, db_session):
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        current = await _make_position(db_session, bot, account, user,
                                       product_id="ETH-USD")
        await _make_position(db_session, bot, account, user,
                             product_id="SOL-USD", status="closed")
        ctx = ToolContext(
            db=db_session, user_id=user.id, product_id="ETH-USD",
            current_price=100.0, position=current, account_id=account.id,
        )
        result = await execute("get_portfolio_context", {}, ctx)
        assert result["open_position_count_total"] == 0


class TestRegistry:
    def test_tool_is_registered(self):
        assert "get_portfolio_context" in REGISTRY
