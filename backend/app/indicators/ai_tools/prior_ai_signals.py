"""Tool: get_prior_ai_signals

Returns the user's last N AI decisions on the current product over a lookback
window, with outcome backfill columns (win/loss/breakeven + realized_pnl_pct)
where available. Lets the model see whether its own recent calls on this pair
have paid off.

Querying `trading.ai_opinion_log` directly keeps this independent from the
`trading.positions` shape — an opinion is logged whether it turned into a
position or not (pre-filter failures are logged with signal='hold').
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy import select

from app.indicators.ai_tools.base import Tool, ToolContext, register
from app.models import AIOpinionLog


_MIN_LIMIT = 1
_MAX_LIMIT = 20
_MIN_DAYS = 1
_MAX_DAYS = 90  # matches the retention horizon


async def _run(input: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    days = int(input.get("days", 14))
    limit = int(input.get("limit", 10))

    days = max(_MIN_DAYS, min(_MAX_DAYS, days))
    limit = max(_MIN_LIMIT, min(_MAX_LIMIT, limit))

    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = (
        select(AIOpinionLog)
        .where(AIOpinionLog.user_id == ctx.user_id)
        .where(AIOpinionLog.product_id == ctx.product_id)
        .where(AIOpinionLog.created_at >= cutoff)
        .order_by(AIOpinionLog.created_at.desc())
        .limit(limit)
    )
    rows = (await ctx.db.execute(stmt)).scalars().all()

    signals: List[Dict[str, Any]] = []
    for r in rows:
        signals.append({
            "product_id": r.product_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "is_sell_check": bool(r.is_sell_check),
            "signal": r.signal,
            "confidence": r.confidence,
            "ai_model": r.ai_model,
            "outcome": r.outcome,
            "realized_pnl_pct": r.realized_pnl_pct,
            "closed_at": r.closed_at.isoformat() if r.closed_at else None,
        })

    return {
        "product_id": ctx.product_id,
        "days": days,
        "signals": signals,
    }


TOOL = Tool(
    name="get_prior_ai_signals",
    description=(
        "Return the user's recent AI decisions on the current product, newest "
        "first, with outcome backfill (win/loss/breakeven + realized PnL %) "
        "where a parent position has since closed. Use this to check whether "
        "your prior calls on this pair have been right. Each row: "
        "{created_at, is_sell_check, signal, confidence, ai_model, outcome, "
        "realized_pnl_pct, closed_at}. Arguments: days 1-90, limit 1-20."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "minimum": _MIN_DAYS,
                "maximum": _MAX_DAYS,
                "description": "Lookback window in days (1-90).",
            },
            "limit": {
                "type": "integer",
                "minimum": _MIN_LIMIT,
                "maximum": _MAX_LIMIT,
                "description": "Max rows to return (1-20).",
            },
        },
        "required": ["days", "limit"],
    },
    fn=_run,
)

register(TOOL)
