"""get_position_context — expose entry, time held, unrealized PnL, DCAs to the AI."""

from datetime import datetime
from typing import Any, Dict

from sqlalchemy import func, select

from app.indicators.ai_tools.base import Tool, ToolContext, register


_INPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
}

_DESCRIPTION = (
    "Return context on the currently-held position: entry price, minutes held, "
    "unrealized PnL %, DCA count, highest price since entry, and configured "
    "stop-loss / take-profit targets. Returns a 'note' field if there is no "
    "open position (i.e., during buy-side checks)."
)


async def _run(input: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    position = ctx.position
    if position is None:
        return {"note": "No open position — call this tool only during sell-side checks."}

    # DCA count = number of Trade rows for this position with trade_type='dca'.
    # Lazy import to avoid pulling the full models chain at module load.
    from app.models import Trade

    stmt = select(func.count()).select_from(Trade).where(
        Trade.position_id == position.id,
        Trade.trade_type == "dca",
    )
    dca_count = int((await ctx.db.execute(stmt)).scalar() or 0)

    opened_at: datetime = position.opened_at or datetime.utcnow()
    minutes_held = max(0, int((datetime.utcnow() - opened_at).total_seconds() // 60))

    avg_price = float(position.average_buy_price or position.entry_price or 0.0)
    current_price = float(ctx.current_price or 0.0)
    unrealized_pnl_pct = (
        ((current_price - avg_price) / avg_price * 100.0) if avg_price > 0 else 0.0
    )
    total_quote_spent = float(position.total_quote_spent or 0.0)
    unrealized_pnl_quote = (
        (current_price - avg_price) * float(position.total_base_acquired or 0.0)
        if avg_price > 0 else 0.0
    )

    high = float(position.highest_price_since_entry or current_price or 0.0)
    drawdown_from_high_pct = (
        ((current_price - high) / high * 100.0) if high > 0 else 0.0
    )

    return {
        "product_id": position.product_id,
        "entry_price": float(position.entry_price) if position.entry_price else None,
        "average_buy_price": round(avg_price, 8),
        "total_quote_spent": round(total_quote_spent, 8),
        "total_base_acquired": float(position.total_base_acquired or 0.0),
        "opened_at_iso": opened_at.isoformat(),
        "minutes_held": minutes_held,
        "current_price": round(current_price, 8),
        "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
        "unrealized_pnl_quote": round(unrealized_pnl_quote, 8),
        "highest_price_since_entry": round(high, 8),
        "drawdown_from_high_pct": round(drawdown_from_high_pct, 2),
        "dca_count": dca_count,
        "exit_targets": {
            "stop_loss": float(position.entry_stop_loss) if position.entry_stop_loss else None,
            "take_profit": (
                float(position.entry_take_profit_target)
                if position.entry_take_profit_target else None
            ),
            "trailing_tp_active": bool(position.trailing_tp_active),
            "trailing_sl_active": bool(position.trailing_stop_loss_active),
            "trailing_sl_price": (
                float(position.trailing_stop_loss_price)
                if position.trailing_stop_loss_price else None
            ),
        },
    }


TOOL = Tool(
    name="get_position_context",
    description=_DESCRIPTION,
    input_schema=_INPUT_SCHEMA,
    fn=_run,
)

register(TOOL)
