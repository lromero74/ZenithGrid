"""Tests for app.indicators.ai_opinion_logger.

Writes a row to trading.ai_opinion_log per evaluate() and backfills the
outcome fields when the parent position closes.

Covers:
- log_opinion — writes all expected fields, tool_calls persisted, open fields null
- log_opinion — swallows exceptions (never bubbles up to the evaluator caller)
- backfill_outcome — updates every open row for a given position_id
- backfill_outcome — classifies win / loss / breakeven correctly
- backfill_outcome — does nothing when there are no logs for that position
- classify helper — edge: 0.0 is breakeven, tiny positive is win
"""

from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import select

from app.event_bus import PositionClosedPayload
from app.indicators.ai_opinion_logger import (
    classify_outcome, log_opinion, backfill_outcome,
    on_position_closed,
)
from app.models import Account, AIOpinionLog, Bot, Position, User


async def _make_user(db, email="opin@h.com"):
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
              product_id="ETH-USD", strategy_type="indicator_based",
              strategy_config={})
    db.add(bot)
    await db.commit()
    await db.refresh(bot)
    return bot


async def _make_position(db, bot, account, user):
    p = Position(
        bot_id=bot.id, account_id=account.id, user_id=user.id,
        product_id="ETH-USD", status="open",
        opened_at=datetime.utcnow(), average_buy_price=100.0,
        total_quote_spent=100.0, total_base_acquired=1.0,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


class TestClassifyOutcome:
    def test_positive_is_win(self):
        assert classify_outcome(0.5) == "win"
        assert classify_outcome(10.0) == "win"

    def test_negative_is_loss(self):
        assert classify_outcome(-0.1) == "loss"
        assert classify_outcome(-10.0) == "loss"

    def test_zero_is_breakeven(self):
        assert classify_outcome(0.0) == "breakeven"


class TestLogOpinion:
    async def test_writes_row_with_all_fields(self, db_session):
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        pos = await _make_position(db_session, bot, account, user)
        tool_calls = [{"name": "get_candle_window", "input": {"timeframe": "1h"},
                       "output_summary": "trend=up", "turn": 1}]

        await log_opinion(
            db=db_session, user_id=user.id, account_id=account.id,
            bot_id=bot.id, position_id=pos.id, product_id="ETH-USD",
            is_sell_check=True, signal="sell", confidence=74,
            reasoning="macd rolled over", tool_calls=tool_calls,
            ai_model="claude",
        )

        rows = (await db_session.execute(select(AIOpinionLog))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.user_id == user.id
        assert row.account_id == account.id
        assert row.bot_id == bot.id
        assert row.position_id == pos.id
        assert row.product_id == "ETH-USD"
        assert row.is_sell_check is True
        assert row.signal == "sell"
        assert row.confidence == 74
        assert row.reasoning == "macd rolled over"
        assert row.ai_model == "claude"
        assert row.tool_calls == tool_calls
        # Outcome fields start null, filled in on POSITION_CLOSED.
        assert row.outcome is None
        assert row.realized_pnl_pct is None
        assert row.closed_at is None

    async def test_writes_without_position_or_bot(self, db_session):
        """Pure buy-check that didn't enter — no position yet."""
        user = await _make_user(db_session)
        await log_opinion(
            db=db_session, user_id=user.id, account_id=None, bot_id=None,
            position_id=None, product_id="BTC-USD", is_sell_check=False,
            signal="hold", confidence=0, reasoning="prefilter failed",
            tool_calls=[], ai_model="gpt",
        )
        rows = (await db_session.execute(select(AIOpinionLog))).scalars().all()
        assert len(rows) == 1
        assert rows[0].position_id is None
        assert rows[0].bot_id is None
        assert rows[0].tool_calls == []

    async def test_swallows_exceptions(self, db_session):
        """log_opinion must never raise — the evaluator treats it as fire-and-forget."""
        class BoomSession:
            def add(self, *a, **kw):
                raise RuntimeError("db down")

            async def commit(self):
                raise RuntimeError("db down")

        # Should not raise:
        await log_opinion(
            db=BoomSession(), user_id=1, account_id=None, bot_id=None,
            position_id=None, product_id="BTC-USD", is_sell_check=False,
            signal="hold", confidence=0, reasoning="r", tool_calls=[],
            ai_model="claude",
        )


class TestBackfillOutcome:
    async def test_backfills_all_rows_for_position(self, db_session):
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        pos = await _make_position(db_session, bot, account, user)

        # Two logs tied to the same position — e.g., a sell_check at open + later.
        for _ in range(2):
            await log_opinion(
                db=db_session, user_id=user.id, account_id=account.id,
                bot_id=bot.id, position_id=pos.id, product_id="ETH-USD",
                is_sell_check=True, signal="hold", confidence=40,
                reasoning="r", tool_calls=[], ai_model="claude",
            )

        closed_at = datetime.utcnow()
        await backfill_outcome(
            db=db_session, position_id=pos.id,
            realized_pnl_pct=2.5, closed_at=closed_at,
        )

        rows = (await db_session.execute(
            select(AIOpinionLog).where(AIOpinionLog.position_id == pos.id)
        )).scalars().all()
        assert len(rows) == 2
        for row in rows:
            assert row.outcome == "win"
            assert row.realized_pnl_pct == 2.5
            assert row.closed_at is not None

    async def test_loss_classified_correctly(self, db_session):
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        pos = await _make_position(db_session, bot, account, user)
        await log_opinion(
            db=db_session, user_id=user.id, account_id=account.id,
            bot_id=bot.id, position_id=pos.id, product_id="ETH-USD",
            is_sell_check=True, signal="hold", confidence=40,
            reasoning="r", tool_calls=[], ai_model="claude",
        )

        await backfill_outcome(
            db=db_session, position_id=pos.id,
            realized_pnl_pct=-3.2,
            closed_at=datetime.utcnow() - timedelta(minutes=1),
        )
        row = (await db_session.execute(
            select(AIOpinionLog).where(AIOpinionLog.position_id == pos.id)
        )).scalar_one()
        assert row.outcome == "loss"
        assert row.realized_pnl_pct == -3.2

    async def test_no_logs_for_position_is_noop(self, db_session):
        # Should not raise, nothing to update.
        await backfill_outcome(
            db=db_session, position_id=99999,
            realized_pnl_pct=1.0, closed_at=datetime.utcnow(),
        )
        rows = (await db_session.execute(select(AIOpinionLog))).scalars().all()
        assert rows == []

    async def test_only_matching_position_updated(self, db_session):
        """Rows on other positions must not be touched by backfill."""
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        pos_a = await _make_position(db_session, bot, account, user)
        pos_b = await _make_position(db_session, bot, account, user)

        await log_opinion(
            db=db_session, user_id=user.id, account_id=account.id,
            bot_id=bot.id, position_id=pos_a.id, product_id="ETH-USD",
            is_sell_check=True, signal="hold", confidence=40,
            reasoning="r", tool_calls=[], ai_model="claude",
        )
        await log_opinion(
            db=db_session, user_id=user.id, account_id=account.id,
            bot_id=bot.id, position_id=pos_b.id, product_id="ETH-USD",
            is_sell_check=True, signal="hold", confidence=40,
            reasoning="r", tool_calls=[], ai_model="claude",
        )

        await backfill_outcome(
            db=db_session, position_id=pos_a.id,
            realized_pnl_pct=1.0, closed_at=datetime.utcnow(),
        )

        row_a = (await db_session.execute(
            select(AIOpinionLog).where(AIOpinionLog.position_id == pos_a.id)
        )).scalar_one()
        row_b = (await db_session.execute(
            select(AIOpinionLog).where(AIOpinionLog.position_id == pos_b.id)
        )).scalar_one()
        assert row_a.outcome == "win"
        assert row_b.outcome is None


class TestOnPositionClosed:
    """Event-bus handler: PositionClosedPayload → backfill_outcome.

    Opens its own session via session_factory so it can run on an
    independent asyncio task (publish is fire-and-forget)."""

    async def test_handler_calls_backfill_with_payload_fields(self):
        captured = {}

        async def fake_backfill(*, db, position_id, realized_pnl_pct, closed_at):
            captured["position_id"] = position_id
            captured["realized_pnl_pct"] = realized_pnl_pct
            captured["closed_at"] = closed_at

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        def fake_factory():
            return FakeSession()

        payload = PositionClosedPayload(
            position_id=42, user_id=1, product_id="ETH-USD",
            bot_id=7, profit_quote=3.0, profit_percentage=1.5,
        )

        with patch(
            "app.indicators.ai_opinion_logger.backfill_outcome",
            new=fake_backfill,
        ):
            await on_position_closed(payload, session_factory=fake_factory)

        assert captured["position_id"] == 42
        assert captured["realized_pnl_pct"] == 1.5
        assert isinstance(captured["closed_at"], datetime)

    async def test_handler_noop_when_profit_percentage_missing(self):
        """If the publisher didn't supply profit_percentage, we have no outcome
        to record — skip the backfill rather than writing a bogus zero."""
        called = {"n": 0}

        async def fake_backfill(**_kwargs):
            called["n"] += 1

        def fake_factory():
            raise AssertionError("session_factory must not be touched on noop")

        payload = PositionClosedPayload(
            position_id=42, user_id=1, product_id="ETH-USD",
            bot_id=7, profit_quote=None, profit_percentage=None,
        )

        with patch(
            "app.indicators.ai_opinion_logger.backfill_outcome",
            new=fake_backfill,
        ):
            await on_position_closed(payload, session_factory=fake_factory)

        assert called["n"] == 0

    async def test_handler_swallows_exceptions(self):
        """A broken handler must never leak into the publisher's task."""

        def broken_factory():
            raise RuntimeError("session factory failed")

        payload = PositionClosedPayload(
            position_id=42, user_id=1, product_id="ETH-USD",
            bot_id=7, profit_percentage=1.0,
        )
        # Should not raise:
        await on_position_closed(payload, session_factory=broken_factory)
