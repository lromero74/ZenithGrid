"""Bull Research Agent — builds the bullish case for a trade.

Returns BullCase with conviction score, catalysts, and target price.
On any parse failure returns a conservative default (conviction=0).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.ai_team.schemas import BullCase, SignalAssessment
from app.indicators.ai_providers import get_provider
from app.services.ai_credential_service import get_user_api_key
from app.utils.ai_credentials import credential_name_for

logger = logging.getLogger(__name__)


class BullResearchAgent:
    """Builds the bullish case given signal data."""

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
    ) -> BullCase:
        """Run the bull research agent; returns BullCase (never raises)."""
        try:
            prompt = self._build_prompt(product_id, current_price, metrics, signal)
            text = await self._call_llm(
                db=db, user_id=user_id, ai_model=ai_model,
                model_override=model_override, prompt=prompt,
            )
            return self._parse(text)
        except Exception:
            logger.exception("BullResearchAgent failed — returning conservative default")
            return BullCase.conservative_default()

    @staticmethod
    def _build_prompt(
        product_id: str,
        current_price: float,
        metrics: Dict[str, Any],
        signal: SignalAssessment,
    ) -> str:
        return f"""You are a bullish research analyst for {product_id}. \
Your job is to build the strongest possible bullish case.

Current price: {current_price}
Technical trend: {signal.trend}, momentum: {signal.momentum:.1f}
RSI: {metrics.get('rsi', 'N/A')}, 24h change: {metrics.get('price_change_24h', 0):.2f}%
Volume ratio: {metrics.get('volume_ratio', 0):.2f}x

Respond ONLY with valid JSON:
{{
  "conviction": <0-100>,
  "catalysts": ["<catalyst1>", ...],
  "target_price": <number or 0>,
  "reasoning": "<bullish argument in 2-3 sentences>"
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
        credential_name = credential_name_for(ai_model)
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
    def _parse(text: str) -> BullCase:
        raw = (text or "").strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if len(lines) > 2 else lines)
        try:
            data = json.loads(raw)
            return BullCase.from_dict(data)
        except Exception as exc:
            logger.warning("BullResearchAgent parse error: %s — raw=%r", exc, text)
            return BullCase.conservative_default()
