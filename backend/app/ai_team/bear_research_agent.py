"""Bear Research Agent — builds the bearish case for a trade.

Returns BearCase with conviction score, risks, and floor price.
On any parse failure returns conservative default (conviction=50 = elevated risk).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.ai_team.schemas import BearCase, SignalAssessment
from app.indicators.ai_providers import get_provider
from app.services.ai_credential_service import get_user_api_key

logger = logging.getLogger(__name__)

_CREDENTIAL_NAMES = {"claude": "claude", "gpt": "openai", "openai": "openai", "gemini": "gemini"}


def _credential_name_for(ai_model: str) -> str:
    key = (ai_model or "").lower()
    try:
        return _CREDENTIAL_NAMES[key]
    except KeyError as exc:
        raise ValueError(f"Unknown AI model: {ai_model}") from exc


class BearResearchAgent:
    """Builds the bearish case given signal data."""

    async def run(
        self,
        *,
        db: Any,
        user_id: int,
        account_id: int,
        ai_model: str,
        model_override: Optional[str],
        product_id: str,
        current_price: float,
        metrics: Dict[str, Any],
        signal: SignalAssessment,
    ) -> BearCase:
        """Run the bear research agent; returns BearCase (never raises)."""
        try:
            prompt = self._build_prompt(product_id, current_price, metrics, signal)
            text = await self._call_llm(
                db=db, user_id=user_id, ai_model=ai_model,
                model_override=model_override, prompt=prompt,
            )
            return self._parse(text)
        except Exception:
            logger.exception("BearResearchAgent failed — returning conservative default")
            return BearCase.conservative_default()

    @staticmethod
    def _build_prompt(
        product_id: str,
        current_price: float,
        metrics: Dict[str, Any],
        signal: SignalAssessment,
    ) -> str:
        return f"""You are a bearish research analyst for {product_id}. \
Your job is to identify risks and build the strongest possible bearish case.

Current price: {current_price}
Technical trend: {signal.trend}, momentum: {signal.momentum:.1f}
RSI: {metrics.get('rsi', 'N/A')}, 24h change: {metrics.get('price_change_24h', 0):.2f}%
Volume ratio: {metrics.get('volume_ratio', 0):.2f}x
Price vs 20MA: {metrics.get('price_vs_ma20', 0):.2f}%

Respond ONLY with valid JSON:
{{
  "conviction": <0-100>,
  "risks": ["<risk1>", ...],
  "floor_price": <number or 0>,
  "reasoning": "<bearish argument in 2-3 sentences>"
}}
"""

    @staticmethod
    async def _call_llm(
        *,
        db: Any,
        user_id: int,
        ai_model: str,
        model_override: Optional[str],
        prompt: str,
    ) -> str:
        credential_name = _credential_name_for(ai_model)
        api_key = await get_user_api_key(db, user_id, credential_name)
        if not api_key:
            raise ValueError(f"No API key configured for {credential_name}")

        provider = get_provider(ai_model, api_key=api_key, model=model_override)
        text, _tool_calls, _usage = await provider.call_with_tools(
            system=None,
            user=prompt,
            tools=[],
            tool_ctx=None,
            max_turns=1,
        )
        return text

    @staticmethod
    def _parse(text: str) -> BearCase:
        raw = (text or "").strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if len(lines) > 2 else lines)
        try:
            data = json.loads(raw)
            return BearCase.from_dict(data)
        except Exception as exc:
            logger.warning("BearResearchAgent parse error: %s — raw=%r", exc, text)
            return BearCase.conservative_default()
