"""AI Team Orchestrator — runs the multi-agent DAG and returns AITeamResult.

DAG:
    SignalAgent
        ↓
    BullResearchAgent + BearResearchAgent  (concurrent via asyncio.gather)
        ↓
    RiskJudgeAgent
        ↓
    DistributionAgent

The entire pipeline is wrapped in asyncio.wait_for with a configurable timeout
(default 60 s). Any exception inside the pipeline — including a timeout — causes
the orchestrator to return a safe AITeamResult with action="hold" and a populated
error field. It never raises to the caller.

Audit trail: all intermediate outputs are captured in AITeamResult and
optionally persisted by AgentMemory.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from app.ai_team.schemas import (
    AITeamResult,
    SignalAssessment,
    RiskVerdict,
    DistributionPlan,
)
from app.ai_team.signal_agent import SignalAgent
from app.ai_team.bull_research_agent import BullResearchAgent
from app.ai_team.bear_research_agent import BearResearchAgent
from app.ai_team.risk_judge_agent import RiskJudgeAgent
from app.ai_team.distribution_agent import DistributionAgent
from app.ai_team.agent_memory import AgentMemory

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60.0  # seconds


class AITeamOrchestrator:
    """Runs the full AI-team pipeline and returns a complete AITeamResult."""

    def __init__(self, timeout: float = _DEFAULT_TIMEOUT):
        self.timeout = timeout
        self._signal_agent = SignalAgent()
        self._bull_agent = BullResearchAgent()
        self._bear_agent = BearResearchAgent()
        self._risk_judge = RiskJudgeAgent()
        self._distribution = DistributionAgent()
        self._memory = AgentMemory()

    async def run(
        self,
        *,
        db: Any,
        user_id: int,
        account_id: int,
        bot_id: Optional[int],
        product_id: str,
        current_price: float,
        metrics: Dict[str, Any],
        available_budget: float,
        ai_model: str = "claude",
        model_override: Optional[str] = None,
        candles: Optional[List[Dict[str, Any]]] = None,
        persist: bool = True,
    ) -> AITeamResult:
        """Run the full pipeline; always returns AITeamResult, never raises.

        Args:
            db:               Async SQLAlchemy session.
            user_id:          Owner's user id (for API-key lookup).
            account_id:       Account id — all memory writes/reads are scoped to this.
            bot_id:           Bot id (optional, for audit trail).
            product_id:       Trading pair e.g. "ETH-BTC".
            current_price:    Current market price.
            metrics:          Pre-computed indicator dict (from IndicatorCalculator).
            available_budget: Quote-currency budget available for this trade.
            ai_model:         LLM provider name: "claude", "gpt", "gemini".
            model_override:   Optional SDK model id override.
            candles:          Raw candle list (passed to signal agent).
            persist:          If True, persist the run to agent_memory.

        Returns:
            AITeamResult with full audit trail. action="hold" on any error.
        """
        common_kwargs = {
            "db": db,
            "user_id": user_id,
            "account_id": account_id,
            "ai_model": ai_model,
            "model_override": model_override,
            "product_id": product_id,
            "current_price": current_price,
            "metrics": metrics,
        }

        try:
            result = await asyncio.wait_for(
                self._run_pipeline(
                    common_kwargs=common_kwargs,
                    available_budget=available_budget,
                    candles=candles,
                    account_id=account_id,
                    product_id=product_id,
                ),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "AITeamOrchestrator timed out after %.0fs for %s (account_id=%d)",
                self.timeout, product_id, account_id,
            )
            result = AITeamResult(
                timed_out=True,
                error=f"Pipeline timed out after {self.timeout:.0f}s — holding.",
            )
        except Exception as exc:
            logger.exception(
                "AITeamOrchestrator unexpected error for %s (account_id=%d): %s",
                product_id, account_id, exc,
            )
            result = AITeamResult(error=str(exc))

        if persist and not result.timed_out and not result.error:
            run_dict = result.to_dict()
            await self._memory.save_run(
                db=db,
                account_id=account_id,
                bot_id=bot_id,
                product_id=product_id,
                signal_output=run_dict["signal"],
                bull_output=run_dict["bull"],
                bear_output=run_dict["bear"],
                verdict_output=run_dict["verdict"],
                plan_output=run_dict["plan"],
                final_action=result.action,
            )

        return result

    async def _run_pipeline(
        self,
        *,
        common_kwargs: Dict[str, Any],
        available_budget: float,
        candles: Optional[List[Dict[str, Any]]],
        account_id: int,
        product_id: str,
    ) -> AITeamResult:
        """Core DAG logic — may raise; caller wraps in wait_for + except."""
        # --- Step 1: Signal agent ---
        signal: SignalAssessment = await self._signal_agent.run(
            **common_kwargs, candles=candles
        )
        logger.debug("SignalAgent: %s momentum=%.1f", signal.trend, signal.momentum)

        # --- Step 2: Bull + Bear concurrently ---
        bull, bear = await asyncio.gather(
            self._bull_agent.run(**common_kwargs, signal=signal),
            self._bear_agent.run(**common_kwargs, signal=signal),
        )
        logger.debug(
            "BullAgent conviction=%d, BearAgent conviction=%d", bull.conviction, bear.conviction
        )

        # --- Step 3: Risk judge ---
        verdict: RiskVerdict = await self._risk_judge.run(
            **common_kwargs, signal=signal, bull=bull, bear=bear
        )
        logger.debug(
            "RiskJudge: action=%s risk=%d conf=%d",
            verdict.action, verdict.risk_score, verdict.confidence,
        )

        # --- Step 4: Distribution (sync, no LLM) ---
        plan: DistributionPlan = self._distribution.run(
            verdict=verdict,
            available_budget=available_budget,
            product_id=product_id,
            account_id=account_id,
        )
        logger.info(
            "AITeam %s account_id=%d → action=%s deploy=%.2f",
            product_id, account_id, plan.action, plan.deploy_amount,
        )

        return AITeamResult(signal=signal, bull=bull, bear=bear, verdict=verdict, plan=plan)
