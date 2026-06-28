"""Risk Judge Agent — receives bull + bear cases and returns a final verdict.

The judge is the most conservative node in the pipeline: when uncertain it
defaults to hold. On any parse failure it returns RiskVerdict.hold_default().
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.ai_team.schemas import BullCase, BearCase, RiskVerdict, SignalAssessment
from app.indicators.ai_providers import get_provider
from app.services.ai_credential_service import get_user_api_key
from app.utils.ai_credentials import credential_name_for

logger = logging.getLogger(__name__)


class RiskJudgeAgent:
    """Weighs bull vs. bear cases and issues a final risk verdict."""

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
        bull: BullCase,
        bear: BearCase,
    ) -> RiskVerdict:
        """Run the risk judge; returns RiskVerdict (never raises)."""
        try:
            prompt = self._build_prompt(product_id, current_price, signal, bull, bear)
            text = await self._call_llm(
                db=db, user_id=user_id, ai_model=ai_model,
                model_override=model_override, prompt=prompt,
            )
            return self._parse(text)
        except Exception:
            logger.exception("RiskJudgeAgent failed — returning hold default")
            return RiskVerdict.hold_default()

    @staticmethod
    def _build_prompt(
        product_id: str,
        current_price: float,
        signal: SignalAssessment,
        bull: BullCase,
        bear: BearCase,
    ) -> str:
        return f"""You are a senior risk manager adjudicating a trade debate for {product_id}.

Current price: {current_price}
Technical signal: {signal.trend}, momentum {signal.momentum:.1f}

BULL CASE (conviction {bull.conviction}/100):
{bull.reasoning}
Catalysts: {', '.join(bull.catalysts) or 'none cited'}

BEAR CASE (conviction {bear.conviction}/100):
{bear.reasoning}
Risks: {', '.join(bear.risks) or 'none cited'}

Your job: weigh both cases and decide:
- risk_score (0=safe, 100=extremely dangerous)
- action: "buy", "sell", or "hold"
- size_fraction: fraction of available budget to deploy (0.0 to 1.0)
  Use smaller fractions for higher risk. Never exceed 0.5 for risky setups.
- confidence (0-100)

Default to "hold" when conviction is weak or risks dominate.

Respond ONLY with valid JSON:
{{
  "risk_score": <0-100>,
  "action": "buy" | "sell" | "hold",
  "size_fraction": <0.0-1.0>,
  "confidence": <0-100>,
  "reasoning": "<verdict explanation in 2-3 sentences>"
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
    def _parse(text: str) -> RiskVerdict:
        raw = (text or "").strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if len(lines) > 2 else lines)
        try:
            data = json.loads(raw)
            return RiskVerdict.from_dict(data)
        except Exception as exc:
            logger.warning("RiskJudgeAgent parse error: %s — raw=%r", exc, text)
            return RiskVerdict.hold_default()
