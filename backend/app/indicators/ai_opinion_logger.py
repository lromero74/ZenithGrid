"""AI opinion log writer + outcome backfill (Phase D).

Two responsibilities:

1. `log_opinion(...)` — write a row per `AISpotOpinionEvaluator.evaluate()`.
   Fire-and-forget from the evaluator's point of view: any DB error is caught
   and logged, never re-raised. A broken audit log must not break trading.

2. `backfill_outcome(...)` — called when a position closes (subscriber to
   POSITION_CLOSED in the event bus). Fills in outcome / realized_pnl_pct /
   closed_at on every log row tied to that position_id.

`classify_outcome(pct)` is split out as a pure helper so the mapping from
PnL% → "win"/"loss"/"breakeven" is trivially unit-testable.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, List, Optional

from sqlalchemy import update

from app.models import AIOpinionLog

logger = logging.getLogger(__name__)


def classify_outcome(pnl_pct: float) -> str:
    if pnl_pct > 0:
        return "win"
    if pnl_pct < 0:
        return "loss"
    return "breakeven"


async def log_opinion(
    *,
    db: Any,
    user_id: int,
    account_id: Optional[int],
    bot_id: Optional[int],
    position_id: Optional[int],
    product_id: str,
    is_sell_check: bool,
    signal: str,
    confidence: int,
    reasoning: str,
    tool_calls: List[Any],
    ai_model: Optional[str],
    model_used: Optional[str] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0.0,
) -> None:
    """Persist one AI decision row. Never raises.

    `model_used` / `input_tokens` / `output_tokens` / `cost_usd` are the Phase F
    cost-accounting fields. They default to zero so prefilter-reject rows (no
    LLM call) still satisfy the `DEFAULT 0` migration constraints.
    """
    try:
        row = AIOpinionLog(
            user_id=user_id,
            account_id=account_id,
            bot_id=bot_id,
            position_id=position_id,
            product_id=product_id,
            is_sell_check=is_sell_check,
            signal=signal,
            confidence=confidence,
            reasoning=reasoning,
            ai_model=ai_model,
            tool_calls=tool_calls,
            model_used=model_used,
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            cost_usd=float(cost_usd or 0.0),
        )
        db.add(row)
        await db.commit()
    except Exception:
        logger.exception(
            "ai_opinion_logger.log_opinion failed (product=%s, user=%s)",
            product_id, user_id,
        )


async def backfill_outcome(
    *,
    db: Any,
    position_id: int,
    realized_pnl_pct: float,
    closed_at: datetime,
) -> None:
    """Update every log row tied to this position with the realized outcome.

    No-op if there are no matching rows (position never had an AI log).
    Never raises — backfill failures must not break the position-close flow.
    """
    try:
        outcome = classify_outcome(realized_pnl_pct)
        stmt = (
            update(AIOpinionLog)
            .where(AIOpinionLog.position_id == position_id)
            .values(
                outcome=outcome,
                realized_pnl_pct=realized_pnl_pct,
                closed_at=closed_at,
            )
        )
        await db.execute(stmt)
        await db.commit()
    except Exception:
        logger.exception(
            "ai_opinion_logger.backfill_outcome failed (position_id=%s)",
            position_id,
        )


async def on_position_closed(
    payload: Any,
    session_factory: Optional[Callable[[], Any]] = None,
) -> None:
    """Event bus handler for POSITION_CLOSED.

    Fire-and-forget: subscribed via `event_bus.subscribe(POSITION_CLOSED, ...)`
    in startup. The handler runs on its own asyncio task, so it opens an
    independent DB session via `async_session_maker` (or the injected factory,
    for tests).

    No-op when `profit_percentage` is missing — we don't fabricate an outcome.
    """
    try:
        pnl_pct = getattr(payload, "profit_percentage", None)
        if pnl_pct is None:
            return

        if session_factory is None:
            from app.database import async_session_maker
            session_factory = async_session_maker

        async with session_factory() as session:
            await backfill_outcome(
                db=session,
                position_id=payload.position_id,
                realized_pnl_pct=float(pnl_pct),
                closed_at=datetime.utcnow(),
            )
    except Exception:
        logger.exception(
            "ai_opinion_logger.on_position_closed failed (position_id=%s)",
            getattr(payload, "position_id", None),
        )
