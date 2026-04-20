"""Tool: get_recent_news

Returns recent news articles whose title or summary mentions the base asset
of ctx.product_id. Uses the already-populated `content.news_articles` table —
no external fetch. Lets the model check for catalysts before confirming a
"metrics look clean" buy.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy import or_, select

from app.currency_utils import get_base_currency
from app.indicators.ai_tools.base import Tool, ToolContext, register
from app.models import NewsArticle


# Expand common tickers to full names so "ETH" also matches "Ethereum".
# Kept small on purpose — the point is reducing false negatives on the majors,
# not translating every alt. Unmapped tickers fall through to the ticker alone.
_TICKER_ALIASES: Dict[str, List[str]] = {
    "BTC": ["BTC", "Bitcoin"],
    "ETH": ["ETH", "Ethereum", "Ether"],
    "SOL": ["SOL", "Solana"],
    "ADA": ["ADA", "Cardano"],
    "DOGE": ["DOGE", "Dogecoin"],
    "XRP": ["XRP", "Ripple"],
    "LTC": ["LTC", "Litecoin"],
    "BCH": ["BCH", "Bitcoin Cash"],
    "AVAX": ["AVAX", "Avalanche"],
    "MATIC": ["MATIC", "Polygon"],
    "DOT": ["DOT", "Polkadot"],
    "LINK": ["LINK", "Chainlink"],
    "ATOM": ["ATOM", "Cosmos"],
}

_MIN_LIMIT = 1
_MAX_LIMIT = 20
_MIN_AGE_HOURS = 1
_MAX_AGE_HOURS = 168  # 7 days — matches the news cleanup retention


def _aliases_for(base: str) -> List[str]:
    return _TICKER_ALIASES.get(base.upper(), [base.upper()])


async def _run(input: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    max_age_hours = int(input.get("max_age_hours", 24))
    limit = int(input.get("limit", 5))

    max_age_hours = max(_MIN_AGE_HOURS, min(_MAX_AGE_HOURS, max_age_hours))
    limit = max(_MIN_LIMIT, min(_MAX_LIMIT, limit))

    base = get_base_currency(ctx.product_id)
    aliases = _aliases_for(base)
    cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)

    title_clauses = [NewsArticle.title.ilike(f"%{alias}%") for alias in aliases]
    summary_clauses = [NewsArticle.summary.ilike(f"%{alias}%") for alias in aliases]
    match_clause = or_(*(title_clauses + summary_clauses))

    stmt = (
        select(NewsArticle)
        .where(NewsArticle.published_at.isnot(None))
        .where(NewsArticle.published_at >= cutoff)
        .where(match_clause)
        .order_by(NewsArticle.published_at.desc())
        .limit(limit)
    )
    rows = (await ctx.db.execute(stmt)).scalars().all()

    articles = [
        {
            "title": a.title,
            "source": a.source,
            "published_at": a.published_at.isoformat() if a.published_at else None,
            "summary": (a.summary or "")[:400],  # truncate — prompts stay tight
            "url": a.url,
        }
        for a in rows
    ]
    return {
        "product_id": ctx.product_id,
        "base_currency": base.upper(),
        "aliases_matched": aliases,
        "max_age_hours": max_age_hours,
        "articles": articles,
    }


TOOL = Tool(
    name="get_recent_news",
    description=(
        "Fetch recent news headlines for this pair's base asset. Queries our "
        "cached news store (no external fetch). Each article: {title, source, "
        "published_at, summary (≤400 chars), url}. Call this when metrics look "
        "tradeable but you want to rule out a recent catalyst (hack, listing, "
        "regulatory headline). Prefer max_age_hours=6 for intraday setups."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "max_age_hours": {
                "type": "integer",
                "minimum": _MIN_AGE_HOURS,
                "maximum": _MAX_AGE_HOURS,
                "description": "Only include articles published within this window (1-168h).",
            },
            "limit": {
                "type": "integer",
                "minimum": _MIN_LIMIT,
                "maximum": _MAX_LIMIT,
                "description": "Max articles to return (clamped to 1-20).",
            },
        },
        "required": ["max_age_hours", "limit"],
    },
    fn=_run,
)

register(TOOL)
