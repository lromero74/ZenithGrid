"""Signal Agent — analyses price/volume/indicators and returns SignalAssessment.

Uses the existing provider abstraction (get_provider / get_user_api_key) exactly
as ai_spot_opinion.py does. The prompt is a single-shot JSON request; no tool
use is needed here. On any parse failure the agent returns a conservative neutral
result so the orchestrator can still proceed.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.ai_team.schemas import SignalAssessment
from app.indicators.ai_providers import get_provider
from app.services.ai_credential_service import get_user_api_key

logger = logging.getLogger(__name__)

# Credential-name map mirrors ai_spot_opinion._credential_name_for
_CREDENTIAL_NAMES = {"claude": "claude", "gpt": "openai", "openai": "openai", "gemini": "gemini"}


def _credential_name_for(ai_model: str) -> str:
    key = (ai_model or "").lower()
    try:
        return _CREDENTIAL_NAMES[key]
    except KeyError as exc:
        raise ValueError(f"Unknown AI model: {ai_model}") from exc


class SignalAgent:
    """Analyses technical indicators and returns a SignalAssessment."""

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
        candles: Optional[List[Dict[str, Any]]] = None,
    ) -> SignalAssessment:
        """Run the signal agent; returns SignalAssessment (never raises)."""
        try:
            prompt = self._build_prompt(product_id, current_price, metrics)
            text = await self._call_llm(
                db=db, user_id=user_id, ai_model=ai_model,
                model_override=model_override, prompt=prompt,
            )
            return self._parse(text)
        except Exception:
            logger.exception("SignalAgent failed — returning neutral default")
            return SignalAssessment.conservative_default()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(
        product_id: str,
        current_price: float,
        metrics: Dict[str, Any],
    ) -> str:
        return f"""You are a technical-analysis specialist for {product_id}.

Current price: {current_price}
Indicators:
- RSI (14): {metrics.get('rsi', 'N/A')}
- MACD bullish: {metrics.get('macd_bullish', False)}
- Price vs 20MA: {metrics.get('price_vs_ma20', 0):.2f}%
- Price vs 50MA: {metrics.get('price_vs_ma50', 0):.2f}%
- Bollinger Band position: {metrics.get('bb_position', 50):.1f}%
- Volume ratio (vs 20-period avg): {metrics.get('volume_ratio', 0):.2f}x
- 24h price change: {metrics.get('price_change_24h', 0):.2f}%

Respond ONLY with valid JSON:
{{
  "trend": "bullish" | "bearish" | "neutral",
  "momentum": <number -100 to 100>,
  "key_levels": [<price>, ...],
  "summary": "<1-2 sentence explanation>"
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
    def _parse(text: str) -> SignalAssessment:
        raw = (text or "").strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if len(lines) > 2 else lines)
        try:
            data = json.loads(raw)
            return SignalAssessment.from_dict(data)
        except Exception as exc:
            logger.warning("SignalAgent parse error: %s — raw=%r", exc, text)
            return SignalAssessment.conservative_default()
