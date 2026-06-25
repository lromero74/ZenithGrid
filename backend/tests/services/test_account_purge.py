"""Integration tests for purge_account_history — real in-memory DB."""
import pytest
from datetime import datetime

from sqlalchemy import select, func

from app.models import (
    Account, Bot, Position, Trade, Signal, PendingOrder, OrderHistory,
    AIOpinionLog,
)
from app.models.reporting import AccountValueSnapshot
from app.services.account_purge import purge_account_history, count_account_history


async def _seed_account(db, account_id, user_id=1):
    """Create one account with a bot, a position, and a row in each history table."""
    db.add(Account(id=account_id, user_id=user_id, name=f"Acct{account_id}",
                   type="cex", is_paper_trading=False))
    db.add(Bot(id=account_id * 10, account_id=account_id, user_id=user_id,
               name=f"Bot{account_id}", strategy_type="rsi", is_active=True))
    db.add(Position(id=account_id * 100, account_id=account_id, bot_id=account_id * 10,
                    user_id=user_id, product_id="FOX-USD", status="open",
                    total_base_acquired=10.0, total_quote_spent=5.0,
                    average_buy_price=0.5, direction="long"))
    await db.flush()
    db.add(Trade(position_id=account_id * 100, side="buy", quote_amount=5.0,
                 base_amount=10.0, price=0.5, trade_type="base_order",
                 timestamp=datetime(2026, 1, 1)))
    db.add(Signal(position_id=account_id * 100))
    db.add(PendingOrder(position_id=account_id * 100, bot_id=account_id * 10,
                        order_id=f"o{account_id}", product_id="FOX-USD", side="SELL",
                        order_type="LIMIT", limit_price=0.5, quote_amount=5.0,
                        base_amount=10.0, trade_type="sell", status="pending",
                        created_at=datetime(2026, 1, 1)))
    db.add(OrderHistory(bot_id=account_id * 10, position_id=account_id * 100,
                        product_id="FOX-USD", side="SELL", order_type="MARKET",
                        trade_type="sell", quote_amount=5.0, base_amount=10.0,
                        price=0.5, status="filled", timestamp=datetime(2026, 1, 1)))
    db.add(AccountValueSnapshot(account_id=account_id, user_id=user_id,
                                snapshot_date=datetime(2026, 1, 1),
                                total_value_btc=1.0, total_value_usd=50.0))
    db.add(AIOpinionLog(account_id=account_id, bot_id=account_id * 10,
                        position_id=account_id * 100, user_id=user_id,
                        product_id="FOX-USD", signal="hold"))
    await db.flush()


async def _count_all(db, account_id):
    counts = await count_account_history(db, account_id)
    return counts


@pytest.mark.asyncio
class TestPurgeAccountHistory:
    async def test_purges_target_account_history(self, db_session):
        await _seed_account(db_session, 1)
        before = await _count_all(db_session, 1)
        assert all(v >= 1 for v in before.values()), before

        deleted = await purge_account_history(db_session, 1)

        after = await _count_all(db_session, 1)
        assert all(v == 0 for v in after.values()), after
        # Reported counts match what was there.
        assert deleted == before

    async def test_does_not_touch_other_account(self, db_session):
        await _seed_account(db_session, 1)
        await _seed_account(db_session, 2)

        await purge_account_history(db_session, 1)

        # Account 2's history is fully intact (cross-account safety).
        assert all(v >= 1 for v in (await _count_all(db_session, 2)).values())

    async def test_preserves_account_and_bot_rows(self, db_session):
        await _seed_account(db_session, 1)

        await purge_account_history(db_session, 1)

        # The account and its bot survive — only history is wiped, so it can
        # start fresh.
        acct = (await db_session.execute(
            select(func.count()).select_from(Account).where(Account.id == 1))).scalar()
        bot = (await db_session.execute(
            select(func.count()).select_from(Bot).where(Bot.account_id == 1))).scalar()
        assert acct == 1
        assert bot == 1

    async def test_purge_empty_account_is_noop(self, db_session):
        db_session.add(Account(id=9, user_id=1, name="Empty", type="cex",
                               is_paper_trading=False))
        await db_session.flush()
        deleted = await purge_account_history(db_session, 9)
        assert all(v == 0 for v in deleted.values())

    async def test_zeroes_bot_reserved_balances(self, db_session):
        """After purge the bot's reserved balances must be 0 — otherwise the bot
        thinks capital is still deployed and refuses to open new positions."""
        await _seed_account(db_session, 1)
        bot = (await db_session.execute(
            select(Bot).where(Bot.account_id == 1))).scalars().first()
        bot.reserved_btc_balance = 0.05
        bot.reserved_usd_balance = 123.45
        await db_session.flush()

        await purge_account_history(db_session, 1)

        await db_session.refresh(bot)
        assert bot.reserved_btc_balance == 0.0
        assert bot.reserved_usd_balance == 0.0
