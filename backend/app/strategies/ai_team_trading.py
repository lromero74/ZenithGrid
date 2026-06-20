"""AI Team Trading Strategy — orchestrated multi-agent LLM debate.

Replaces the single-call AI-opinion approach with a 5-agent pipeline:
  Signal → (Bull + Bear concurrent) → Risk Judge → Distribution

Strategy id: ``ai_team``

Config keys:
    ai_model            LLM provider: "claude" | "gpt" | "gemini" (default: "claude")
    ai_model_override   Optional SDK model id string (default: "")
    min_confidence      Minimum Risk Judge confidence to act (0-100, default: 60)
    max_risk_score      Maximum risk score to allow a buy/sell (0-100, default: 70)
    max_deploy_fraction Maximum fraction of budget to deploy (0.0-1.0, default: 0.5)
    pipeline_timeout    Orchestrator timeout in seconds (default: 60)

analyze_signal runs the full orchestrator. should_buy / should_sell read
the result from the signal dict — no extra LLM calls.

Bots using this strategy start stopped. Nothing auto-executes without
an explicit bot start by the user.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.strategies import (
    StrategyDefinition,
    StrategyParameter,
    StrategyRegistry,
    TradingStrategy,
)

logger = logging.getLogger(__name__)


@StrategyRegistry.register
class AITeamTradingStrategy(TradingStrategy):
    """Multi-agent AI team trading strategy."""

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="ai_team",
            name="AI Trading Team",
            description=(
                "Five specialised LLM agents debate the trade before deciding: "
                "Signal Analyst → Bull & Bear Researchers (concurrent) → "
                "Risk Judge → Distribution Planner."
            ),
            parameters=[
                StrategyParameter(
                    name="ai_model",
                    display_name="AI Model",
                    description="LLM provider to use for all agents",
                    type="string",
                    default="claude",
                    options=["claude", "gpt", "gemini"],
                    group="AI Configuration",
                ),
                StrategyParameter(
                    name="ai_model_override",
                    display_name="Model Override (optional)",
                    description="Specific SDK model id (e.g. claude-opus-4-5). Leave blank for provider default.",
                    type="string",
                    default="",
                    required=False,
                    group="AI Configuration",
                ),
                StrategyParameter(
                    name="min_confidence",
                    display_name="Minimum Confidence",
                    description=(
                        "Risk Judge confidence must meet this threshold (0-100) "
                        "before a buy or sell is executed."
                    ),
                    type="int",
                    default=60,
                    min_value=0,
                    max_value=100,
                    group="Risk Controls",
                ),
                StrategyParameter(
                    name="max_risk_score",
                    display_name="Maximum Risk Score",
                    description=(
                        "If the Risk Judge assigns a score above this (0-100), "
                        "the strategy holds regardless of the action."
                    ),
                    type="int",
                    default=70,
                    min_value=0,
                    max_value=100,
                    group="Risk Controls",
                ),
                StrategyParameter(
                    name="max_deploy_fraction",
                    display_name="Max Deploy Fraction",
                    description=(
                        "Hard cap on the fraction of available budget the Distribution "
                        "agent may deploy in a single decision (0.0-1.0)."
                    ),
                    type="float",
                    default=0.5,
                    min_value=0.0,
                    max_value=1.0,
                    group="Risk Controls",
                ),
                StrategyParameter(
                    name="pipeline_timeout",
                    display_name="Pipeline Timeout (s)",
                    description="Maximum seconds to wait for the full agent pipeline before holding.",
                    type="float",
                    default=60.0,
                    min_value=10.0,
                    max_value=300.0,
                    group="AI Configuration",
                ),
            ],
        )

    def validate_config(self):
        min_conf = int(self.config.get("min_confidence", 60))
        if not (0 <= min_conf <= 100):
            logger.warning("ai_team: min_confidence out of range (%d) — clamping", min_conf)
        max_risk = int(self.config.get("max_risk_score", 70))
        if not (0 <= max_risk <= 100):
            logger.warning("ai_team: max_risk_score out of range (%d) — clamping", max_risk)
        frac = float(self.config.get("max_deploy_fraction", 0.5))
        if not (0.0 <= frac <= 1.0):
            logger.warning("ai_team: max_deploy_fraction out of range (%.2f) — clamping", frac)

    # ------------------------------------------------------------------
    # TradingStrategy interface
    # ------------------------------------------------------------------

    async def analyze_signal(
        self,
        candles: List[Dict[str, Any]],
        current_price: float,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """Run the full AI-team pipeline and return the result as a signal dict.

        Required kwargs:
            db           Async SQLAlchemy session
            user_id      User id (for API-key lookup)
            account_id   Account id (HARD RULE: all memory is scoped to this)
            available_budget  Quote-currency budget available

        Optional kwargs:
            bot_id       Bot id (for audit trail, default None)
            metrics      Pre-computed indicator dict (default {})
            product_id   Trading pair (default "ETH-BTC")
        """
        from app.ai_team.team_orchestrator import AITeamOrchestrator

        db = kwargs.get("db")
        user_id = kwargs.get("user_id")
        account_id = kwargs.get("account_id")
        available_budget = float(kwargs.get("available_budget", 0.0))
        bot_id = kwargs.get("bot_id")
        metrics = kwargs.get("metrics", {})
        product_id = kwargs.get("product_id", "ETH-BTC")

        if db is None or user_id is None or account_id is None:
            logger.warning("ai_team analyze_signal: missing db/user_id/account_id — holding")
            return _hold_signal("Missing required context")

        timeout = float(self.config.get("pipeline_timeout", 60.0))
        ai_model = str(self.config.get("ai_model", "claude"))
        model_override = self.config.get("ai_model_override") or None
        max_deploy_fraction = float(self.config.get("max_deploy_fraction", 0.5))

        # Cap available_budget by max_deploy_fraction so the orchestrator
        # can never exceed the strategy's own hard limit regardless of what
        # the distribution agent computes.
        capped_budget = available_budget * max_deploy_fraction

        orchestrator = AITeamOrchestrator(timeout=timeout)
        result = await orchestrator.run(
            db=db,
            user_id=user_id,
            account_id=account_id,
            bot_id=bot_id,
            product_id=product_id,
            current_price=current_price,
            metrics=metrics,
            available_budget=capped_budget,
            ai_model=ai_model,
            model_override=model_override,
            candles=candles,
        )

        return {
            "action": result.action,
            "deploy_amount": result.deploy_amount,
            "deploy_fraction": result.plan.deploy_fraction,
            "risk_score": result.verdict.risk_score,
            "confidence": result.verdict.confidence,
            "reasoning": result.verdict.reasoning,
            "signal_trend": result.signal.trend,
            "bull_conviction": result.bull.conviction,
            "bear_conviction": result.bear.conviction,
            "timed_out": result.timed_out,
            "error": result.error,
            "_result": result,  # full object for audit / tests
        }

    async def should_buy(
        self,
        signal_data: Dict[str, Any],
        position: Optional[Any],
        btc_balance: float,
    ) -> Tuple[bool, float, str]:
        """Return (should_buy, amount, reason) from the signal dict."""
        if not signal_data or signal_data.get("timed_out") or signal_data.get("error"):
            return False, 0.0, "Pipeline error or timeout — holding"

        if signal_data.get("action") != "buy":
            return False, 0.0, f"AI team action={signal_data.get('action')} — not a buy"

        min_conf = int(self.config.get("min_confidence", 60))
        max_risk = int(self.config.get("max_risk_score", 70))

        confidence = int(signal_data.get("confidence", 0))
        risk_score = int(signal_data.get("risk_score", 100))

        if confidence < min_conf:
            return False, 0.0, (
                f"Confidence {confidence} < min {min_conf} — holding"
            )
        if risk_score > max_risk:
            return False, 0.0, (
                f"Risk score {risk_score} > max {max_risk} — holding"
            )

        deploy_amount = float(signal_data.get("deploy_amount", 0.0))
        if deploy_amount <= 0.0:
            return False, 0.0, "Deploy amount is zero — nothing to buy"

        reason = (
            f"AI team BUY: confidence={confidence}, risk={risk_score}, "
            f"deploy={deploy_amount:.4f} | {signal_data.get('reasoning', '')}"
        )
        return True, deploy_amount, reason

    async def should_sell(
        self,
        signal_data: Dict[str, Any],
        position: Any,
        current_price: float,
    ) -> Tuple[bool, str]:
        """Return (should_sell, reason) from the signal dict."""
        if not signal_data or signal_data.get("timed_out") or signal_data.get("error"):
            return False, "Pipeline error or timeout — holding"

        if signal_data.get("action") != "sell":
            return False, f"AI team action={signal_data.get('action')} — not a sell"

        min_conf = int(self.config.get("min_confidence", 60))
        max_risk = int(self.config.get("max_risk_score", 70))

        confidence = int(signal_data.get("confidence", 0))
        risk_score = int(signal_data.get("risk_score", 100))

        if confidence < min_conf:
            return False, f"Confidence {confidence} < min {min_conf} — holding"
        if risk_score > max_risk:
            return False, f"Risk score {risk_score} > max {max_risk} — holding"

        reason = (
            f"AI team SELL: confidence={confidence}, risk={risk_score} | "
            f"{signal_data.get('reasoning', '')}"
        )
        return True, reason


def _hold_signal(reason: str) -> Dict[str, Any]:
    return {
        "action": "hold",
        "deploy_amount": 0.0,
        "deploy_fraction": 0.0,
        "risk_score": 100,
        "confidence": 0,
        "reasoning": reason,
        "signal_trend": "neutral",
        "bull_conviction": 0,
        "bear_conviction": 0,
        "timed_out": False,
        "error": reason,
    }
