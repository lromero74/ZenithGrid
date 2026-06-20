"""Distribution Agent — translates a RiskVerdict into a concrete allocation plan.

Enforces the hard rule: deploy_amount can NEVER exceed available_budget.
Uses the verdict's size_fraction as the desired fraction; the actual deployed
amount is min(desired, available_budget). No external LLM call needed: the
sizing math is deterministic once the verdict is known.
"""

from __future__ import annotations

import logging

from app.ai_team.schemas import RiskVerdict, DistributionPlan

logger = logging.getLogger(__name__)


class DistributionAgent:
    """Converts a RiskVerdict into a DistributionPlan respecting budget limits."""

    def run(
        self,
        *,
        verdict: RiskVerdict,
        available_budget: float,
        product_id: str,
        account_id: int,
    ) -> DistributionPlan:
        """Compute the distribution plan (synchronous — no LLM needed).

        Args:
            verdict:          Final decision from the Risk Judge.
            available_budget: Quote-currency budget available for this trade.
            product_id:       Trading pair (for logging).
            account_id:       Account this plan is scoped to (for audit).

        Returns:
            DistributionPlan where deploy_amount <= available_budget always.
        """
        if verdict.action == "hold" or verdict.size_fraction <= 0.0:
            return DistributionPlan(
                action="hold",
                deploy_fraction=0.0,
                deploy_amount=0.0,
                reasoning="Risk judge said hold — no capital deployed.",
            )

        if available_budget <= 0.0:
            logger.info(
                "DistributionAgent: no budget available for %s (account_id=%d)",
                product_id, account_id,
            )
            return DistributionPlan(
                action="hold",
                deploy_fraction=0.0,
                deploy_amount=0.0,
                reasoning="No available budget — cannot execute trade.",
                budget_limited=True,
            )

        desired_amount = available_budget * verdict.size_fraction
        actual_amount = min(desired_amount, available_budget)
        actual_fraction = actual_amount / available_budget if available_budget > 0 else 0.0
        budget_limited = actual_amount < desired_amount

        reasoning = (
            f"Deploying {actual_fraction:.1%} of available budget "
            f"({actual_amount:.2f} of {available_budget:.2f}) — "
            f"risk score {verdict.risk_score}/100, action={verdict.action}."
        )
        if budget_limited:
            reasoning += " (capped at available budget)"

        logger.info(
            "DistributionAgent: %s account_id=%d action=%s deploy=%.2f budget=%.2f",
            product_id, account_id, verdict.action, actual_amount, available_budget,
        )

        return DistributionPlan(
            action=verdict.action,
            deploy_fraction=actual_fraction,
            deploy_amount=actual_amount,
            reasoning=reasoning,
            budget_limited=budget_limited,
        )
