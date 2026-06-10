"""AI usage/cost summary endpoint (Phase F).

GET /api/ai/cost-summary?days=7 — aggregates the per-call audit rows in
`ai_opinion_log` for the current user into (provider, model) and provider-only
totals. Drives the Settings > AI dashboard.

Grouping rules:
- `by_model` keys on (ai_model → provider slug, model_used). Rows with
  model_used=NULL collapse into a single "(legacy)" model bucket per provider,
  so pre-Phase-F activity stays visible on the dashboard.
- `by_provider` sums every row for the provider, including legacy rows.

This router never writes — it's read-only aggregation over the user's own rows.
"""

from __future__ import annotations
from app.utils.timeutil import utcnow

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import AIOpinionLog, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai-cost"])

_MAX_DAYS = 365
_LEGACY_MODEL_LABEL = "(legacy)"


class ModelCostRow(BaseModel):
    provider: str
    model_used: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class ProviderCostRow(BaseModel):
    provider: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class CostSummary(BaseModel):
    days: int
    total_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    by_model: List[ModelCostRow]
    by_provider: List[ProviderCostRow]


@dataclass
class _Accumulator:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def merge(self, *, calls: int, input_tokens: Optional[int],
              output_tokens: Optional[int], cost_usd: Optional[float]) -> None:
        """Fold one SQL-aggregated (provider, model) row into this bucket.

        Multiple raw rows can normalize to the same bucket (e.g. ai_model
        'openai' and 'gpt' both slug to 'gpt'), so this accumulates.
        """
        self.calls += int(calls or 0)
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)
        self.cost_usd += float(cost_usd or 0.0)


def _provider_slug(ai_model: Optional[str]) -> str:
    """Normalize the user-facing model string to a provider slug.

    `ai_model` comes straight from the stored value — usually "claude" / "gpt"
    / "gemini". "openai" normalizes to "gpt" so the UI bucket matches what the
    user picked in the settings.
    """
    m = (ai_model or "").strip().lower()
    if m == "openai":
        return "gpt"
    return m or "unknown"


@router.get("/cost-summary", response_model=CostSummary)
async def cost_summary(
    days: int = 7,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CostSummary:
    """Aggregate the current user's AI usage/cost over the last `days` days."""
    if days < 1 or days > _MAX_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"`days` must be between 1 and {_MAX_DAYS}",
        )

    since = utcnow() - timedelta(days=days)
    # Aggregate in SQL — one row per raw (ai_model, model_used) pair instead of
    # one ORM object per logged call. Provider-slug normalization ('openai' →
    # 'gpt') happens in Python over the handful of aggregated rows, merging
    # buckets where slugs collide.
    stmt = (
        select(
            AIOpinionLog.ai_model,
            AIOpinionLog.model_used,
            func.count().label("calls"),
            func.sum(func.coalesce(AIOpinionLog.input_tokens, 0)).label("input_tokens"),
            func.sum(func.coalesce(AIOpinionLog.output_tokens, 0)).label("output_tokens"),
            func.sum(func.coalesce(AIOpinionLog.cost_usd, 0.0)).label("cost_usd"),
        )
        .where(
            and_(
                AIOpinionLog.user_id == current_user.id,
                AIOpinionLog.created_at >= since,
            )
        )
        .group_by(AIOpinionLog.ai_model, AIOpinionLog.model_used)
    )
    result = await db.execute(stmt)
    grouped_rows = result.all()

    by_model: Dict[Tuple[str, str], _Accumulator] = {}
    by_provider: Dict[str, _Accumulator] = {}

    for row in grouped_rows:
        provider = _provider_slug(row.ai_model)
        model_key = row.model_used or _LEGACY_MODEL_LABEL
        by_model.setdefault((provider, model_key), _Accumulator()).merge(
            calls=row.calls,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            cost_usd=row.cost_usd,
        )
        by_provider.setdefault(provider, _Accumulator()).merge(
            calls=row.calls,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            cost_usd=row.cost_usd,
        )

    model_rows = [
        ModelCostRow(
            provider=provider,
            model_used=model,
            calls=acc.calls,
            input_tokens=acc.input_tokens,
            output_tokens=acc.output_tokens,
            cost_usd=round(acc.cost_usd, 6),
        )
        for (provider, model), acc in sorted(by_model.items())
    ]
    provider_rows = [
        ProviderCostRow(
            provider=provider,
            calls=acc.calls,
            input_tokens=acc.input_tokens,
            output_tokens=acc.output_tokens,
            cost_usd=round(acc.cost_usd, 6),
        )
        for provider, acc in sorted(by_provider.items())
    ]

    return CostSummary(
        days=days,
        total_calls=sum(r.calls for r in provider_rows),
        total_input_tokens=sum(r.input_tokens for r in provider_rows),
        total_output_tokens=sum(r.output_tokens for r in provider_rows),
        total_cost_usd=round(sum(r.cost_usd for r in provider_rows), 6),
        by_model=model_rows,
        by_provider=provider_rows,
    )
