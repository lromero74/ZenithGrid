"""Tests that AISpotOpinionEvaluator writes to ai_opinion_log on every
successful evaluate() call.

Covers:
- Happy path: a row is written with signal/confidence/reasoning/tool_calls,
  and the user/account/bot/position IDs line up with what was passed in.
- Fire-and-forget: a failing log_opinion does NOT break the evaluate() return.
- Early-return paths (prefilter failed) also log — we still want the audit row.
"""

import importlib.util
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.models import Account, AIOpinionLog, Bot, Position, User

_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "app.indicators.ai_spot_opinion",
    os.path.join(_here, "../../app/indicators/ai_spot_opinion.py"),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("app.indicators.ai_spot_opinion", _mod)
_spec.loader.exec_module(_mod)

AISpotOpinionEvaluator = _mod.AISpotOpinionEvaluator
AISpotOpinionParams = _mod.AISpotOpinionParams

# Usage meta dict returned by `_call_llm` alongside (signal, confidence, reasoning, tool_calls).
_USAGE_META = {
    "model_used": "claude-opus-4-7",
    "input_tokens": 120,
    "output_tokens": 40,
    "cost_usd": 0.000123,
}


def _make_candles(count=60, base_price=100.0, volume=1500.0):
    return [
        {
            "open": (base_price + i * 0.5) * 0.999,
            "high": (base_price + i * 0.5) * 1.005,
            "low": (base_price + i * 0.5) * 0.995,
            "close": base_price + i * 0.5,
            "volume": volume,
        }
        for i in range(count)
    ]


async def _make_user(db, email="log@h.com"):
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


class TestEvaluateWritesLog:
    async def test_successful_evaluate_writes_log_row(self, db_session):
        user = await _make_user(db_session)
        account = await _make_account(db_session, user)
        bot = await _make_bot(db_session, account, user)
        pos = await _make_position(db_session, bot, account, user)

        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams(ai_model="claude", enable_buy_prefilter=False)

        with patch.object(evaluator, "_call_llm",
                          new_callable=AsyncMock,
                          return_value=("sell", 72, "take profit", [], _USAGE_META)):
            await evaluator.evaluate(
                candles=_make_candles(60), current_price=100.0,
                product_id="ETH-USD", db=db_session, user_id=user.id,
                params=params, is_sell_check=True,
                bot=bot, account_id=account.id, position=pos,
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
        assert row.confidence == 72
        assert row.reasoning == "take profit"
        assert row.ai_model == "claude"
        # tool_calls is empty list when the model didn't call any tools.
        assert row.tool_calls == []
        # Outcome is backfilled later via POSITION_CLOSED.
        assert row.outcome is None
        # Phase F: per-call cost accounting columns are populated from usage_meta.
        assert row.model_used == "claude-opus-4-7"
        assert row.input_tokens == 120
        assert row.output_tokens == 40
        assert row.cost_usd == 0.000123

    async def test_log_failure_does_not_break_evaluate(self, db_session):
        """If log_opinion raises, evaluate() must still return its result."""
        user = await _make_user(db_session)
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams(ai_model="claude", enable_buy_prefilter=False)

        async def boom(**_kwargs):
            raise RuntimeError("audit log offline")

        with patch.object(_mod, "log_opinion", side_effect=boom):
            with patch.object(evaluator, "_call_llm",
                              new_callable=AsyncMock,
                              return_value=("buy", 60, "looks ok", [], _USAGE_META)):
                result = await evaluator.evaluate(
                    candles=_make_candles(60), current_price=100.0,
                    product_id="ETH-USD", db=db_session, user_id=user.id,
                    params=params, is_sell_check=False, account_id=None,
                )

        assert result["signal"] == "buy"
        assert result["confidence"] == 60

    async def test_prefilter_failure_still_writes_log(self, db_session):
        """A rejected buy (prefilter failed) is still a decision worth auditing."""
        user = await _make_user(db_session)
        evaluator = AISpotOpinionEvaluator()
        # Prefilter enabled — metrics with extreme RSI will cause a reject.
        params = AISpotOpinionParams(ai_model="claude", enable_buy_prefilter=True)

        # Candles rigged so RSI is extreme and prefilter rejects.
        candles = _make_candles(60, volume=1.0)  # low volume → fail

        await evaluator.evaluate(
            candles=candles, current_price=candles[-1]["close"],
            product_id="BTC-USD", db=db_session, user_id=user.id,
            params=params, is_sell_check=False, account_id=None,
        )

        rows = (await db_session.execute(select(AIOpinionLog))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.signal == "hold"
        assert row.reasoning.startswith("Prefilter:")
