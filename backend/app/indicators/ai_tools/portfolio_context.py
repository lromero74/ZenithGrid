"""get_portfolio_context — expose other open positions on the same account to the AI."""

from app.utils.timeutil import utcnow
from typing import Any, Dict, List

from sqlalchemy import select

from app.currency_utils import get_quote_currency
from app.indicators.ai_tools.base import Tool, ToolContext, register


_INPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
}

_DESCRIPTION = (
    "Return context on other open positions on the same account: count by quote "
    "currency, total quote exposure, base-asset concentration, and a list of the "
    "other open positions (excluding the current one). Use this to avoid adding "
    "correlated exposure or over-concentrating in a single asset family."
)


_CONCENTRATION_THRESHOLD = 4  # >=4 positions sharing the same base asset → 'high'


def _base_asset(product_id: str) -> str:
    """'ETH-BTC' -> 'ETH'. Returns empty string if malformed."""
    if not product_id or "-" not in product_id:
        return ""
    return product_id.split("-", 1)[0]


async def _run(input: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    if ctx.account_id is None:
        return {"note": "No account_id in context — portfolio context unavailable."}

    from app.models import Position

    current_id = ctx.position.id if ctx.position is not None else -1
    current_quote = get_quote_currency(ctx.product_id)

    stmt = select(Position).where(
        Position.account_id == ctx.account_id,
        Position.status == "open",
        Position.id != current_id,
    )
    rows = (await ctx.db.execute(stmt)).scalars().all()

    now = utcnow()
    others: List[Dict[str, Any]] = []
    same_quote_exposure = 0.0
    same_quote_count = 0
    base_counts: Dict[str, int] = {}

    for p in rows:
        q = get_quote_currency(p.product_id)
        base = _base_asset(p.product_id)
        base_counts[base] = base_counts.get(base, 0) + 1
        minutes_held = (
            int((now - p.opened_at).total_seconds() // 60) if p.opened_at else 0
        )
        entry = float(p.average_buy_price or p.entry_price or 0.0)
        others.append({
            "product_id": p.product_id,
            "quote_currency": q,
            "entry_price": round(entry, 8),
            "total_quote_spent": round(float(p.total_quote_spent or 0.0), 8),
            "minutes_held": max(0, minutes_held),
        })
        if q == current_quote:
            same_quote_count += 1
            same_quote_exposure += float(p.total_quote_spent or 0.0)

    # Count the current position's base asset in concentration too
    if ctx.position is not None:
        current_base = _base_asset(ctx.product_id)
        if current_base:
            base_counts[current_base] = base_counts.get(current_base, 0) + 1

    max_base_count = max(base_counts.values()) if base_counts else 0
    concentration_flag = "high" if max_base_count >= _CONCENTRATION_THRESHOLD else "normal"

    return {
        "current_quote_currency": current_quote,
        "open_position_count_total": len(others),
        "open_position_count_same_quote": same_quote_count,
        "same_quote_total_exposure": round(same_quote_exposure, 8),
        "concentration_flag": concentration_flag,
        "max_positions_single_base": max_base_count,
        "other_open_positions": others,
    }


TOOL = Tool(
    name="get_portfolio_context",
    description=_DESCRIPTION,
    input_schema=_INPUT_SCHEMA,
    fn=_run,
)

register(TOOL)
