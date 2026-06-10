"""Tool: get_trade_history

Returns recent *closed* positions for the current user on this product plus a
compact summary block (count, win rate, avg PnL%, avg hold minutes). Gives the
model empirical feedback on its own track record for this pair.

Uses `trading.positions` directly — no separate log table required.
"""

from __future__ import annotations
from app.utils.timeutil import utcnow

from datetime import timedelta
from typing import Any, Dict, List

from sqlalchemy import select

from app.indicators.ai_tools.base import Tool, ToolContext, register
from app.models import Position


_MIN_N = 1
_MAX_N = 20
_MIN_DAYS = 1
_MAX_DAYS = 90


def _hold_minutes(pos: Position) -> float:
    if not pos.opened_at or not pos.closed_at:
        return 0.0
    return (pos.closed_at - pos.opened_at).total_seconds() / 60.0


def _zero_summary() -> Dict[str, float]:
    return {
        "count": 0,
        "win_count": 0,
        "loss_count": 0,
        "win_rate_pct": 0.0,
        "avg_pnl_pct": 0.0,
        "avg_hold_minutes": 0.0,
    }


async def _run(input: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    lookback_days = int(input.get("lookback_days", 14))
    n = int(input.get("n", 10))

    lookback_days = max(_MIN_DAYS, min(_MAX_DAYS, lookback_days))
    n = max(_MIN_N, min(_MAX_N, n))

    cutoff = utcnow() - timedelta(days=lookback_days)
    stmt = (
        select(Position)
        .where(Position.user_id == ctx.user_id)
        .where(Position.product_id == ctx.product_id)
        .where(Position.status == "closed")
        .where(Position.closed_at.isnot(None))
        .where(Position.closed_at >= cutoff)
        .order_by(Position.closed_at.desc())
        .limit(n)
    )
    rows = (await ctx.db.execute(stmt)).scalars().all()

    trades: List[Dict[str, Any]] = []
    for p in rows:
        trades.append({
            "product_id": p.product_id,
            "opened_at": p.opened_at.isoformat() if p.opened_at else None,
            "closed_at": p.closed_at.isoformat() if p.closed_at else None,
            "hold_minutes": round(_hold_minutes(p), 1),
            "entry_price": p.average_buy_price,
            "exit_price": p.sell_price,
            "profit_percentage": p.profit_percentage,
            "exit_reason": p.exit_reason,
        })

    if not trades:
        return {
            "product_id": ctx.product_id,
            "lookback_days": lookback_days,
            "trades": [],
            "summary": _zero_summary(),
        }

    pnls = [t["profit_percentage"] or 0.0 for t in trades]
    holds = [t["hold_minutes"] or 0.0 for t in trades]
    win_count = sum(1 for x in pnls if x > 0)
    loss_count = sum(1 for x in pnls if x < 0)

    summary = {
        "count": len(trades),
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate_pct": round(win_count / len(trades) * 100, 2),
        "avg_pnl_pct": round(sum(pnls) / len(pnls), 4),
        "avg_hold_minutes": round(sum(holds) / len(holds), 2),
    }
    return {
        "product_id": ctx.product_id,
        "lookback_days": lookback_days,
        "trades": trades,
        "summary": summary,
    }


TOOL = Tool(
    name="get_trade_history",
    description=(
        "Return the last N closed positions this user has had on the current "
        "product, plus a summary stat block (count, win/loss count, win rate, "
        "avg PnL%, avg hold minutes). Use this to gauge recent real-world "
        "performance on this pair before sizing conviction. Arguments: "
        "lookback_days 1-90, n 1-20."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "lookback_days": {
                "type": "integer",
                "minimum": _MIN_DAYS,
                "maximum": _MAX_DAYS,
                "description": "How far back to search for closed positions.",
            },
            "n": {
                "type": "integer",
                "minimum": _MIN_N,
                "maximum": _MAX_N,
                "description": "Max trades to return (clamped to 1-20).",
            },
        },
        "required": ["lookback_days", "n"],
    },
    fn=_run,
)

register(TOOL)
