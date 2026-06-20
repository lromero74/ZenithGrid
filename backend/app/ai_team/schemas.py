"""Structured output schemas for each AI team agent.

Each dataclass represents the validated output of one specialist agent.
All fields have sensible defaults so a failed-parse can still return a
conservative neutral result without raising.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Signal Agent output
# ---------------------------------------------------------------------------

@dataclass
class SignalAssessment:
    """Technical-signal analysis produced by the Signal Agent.

    trend:      "bullish" | "bearish" | "neutral"
    momentum:   -100..+100 (positive = bullish momentum)
    key_levels: list of price levels the model flagged (support/resistance)
    summary:    brief human-readable explanation
    """
    trend: str = "neutral"
    momentum: float = 0.0
    key_levels: List[float] = field(default_factory=list)
    summary: str = ""

    def __post_init__(self):
        if self.trend not in ("bullish", "bearish", "neutral"):
            self.trend = "neutral"
        self.momentum = max(-100.0, min(100.0, float(self.momentum)))

    @classmethod
    def conservative_default(cls) -> "SignalAssessment":
        return cls(trend="neutral", momentum=0.0, summary="Signal agent unavailable — defaulting to neutral.")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SignalAssessment":
        return cls(
            trend=str(data.get("trend", "neutral")).lower(),
            momentum=float(data.get("momentum", 0.0)),
            key_levels=[float(v) for v in data.get("key_levels", [])],
            summary=str(data.get("summary", "")),
        )


# ---------------------------------------------------------------------------
# Bull Research Agent output
# ---------------------------------------------------------------------------

@dataclass
class BullCase:
    """Bullish thesis produced by the Bull Research Agent.

    conviction:    0-100 (higher = stronger bull case)
    catalysts:     list of bullish catalysts identified
    target_price:  near-term price target (optional, 0 = not specified)
    reasoning:     full argument
    """
    conviction: int = 0
    catalysts: List[str] = field(default_factory=list)
    target_price: float = 0.0
    reasoning: str = ""

    def __post_init__(self):
        self.conviction = max(0, min(100, int(self.conviction)))

    @classmethod
    def conservative_default(cls) -> "BullCase":
        return cls(conviction=0, reasoning="Bull agent unavailable — no bullish case.")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BullCase":
        return cls(
            conviction=int(data.get("conviction", 0)),
            catalysts=[str(c) for c in data.get("catalysts", [])],
            target_price=float(data.get("target_price", 0.0)),
            reasoning=str(data.get("reasoning", "")),
        )


# ---------------------------------------------------------------------------
# Bear Research Agent output
# ---------------------------------------------------------------------------

@dataclass
class BearCase:
    """Bearish thesis produced by the Bear Research Agent.

    conviction:   0-100 (higher = stronger bear case)
    risks:        list of risk factors identified
    floor_price:  near-term downside floor (optional, 0 = not specified)
    reasoning:    full argument
    """
    conviction: int = 0
    risks: List[str] = field(default_factory=list)
    floor_price: float = 0.0
    reasoning: str = ""

    def __post_init__(self):
        self.conviction = max(0, min(100, int(self.conviction)))

    @classmethod
    def conservative_default(cls) -> "BearCase":
        return cls(conviction=50, reasoning="Bear agent unavailable — defaulting to elevated risk.")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BearCase":
        return cls(
            conviction=int(data.get("conviction", 0)),
            risks=[str(r) for r in data.get("risks", [])],
            floor_price=float(data.get("floor_price", 0.0)),
            reasoning=str(data.get("reasoning", "")),
        )


# ---------------------------------------------------------------------------
# Risk Judge output
# ---------------------------------------------------------------------------

_VALID_ACTIONS = {"buy", "sell", "hold"}


@dataclass
class RiskVerdict:
    """Final risk/action verdict produced by the Risk Judge.

    risk_score:    0-100 (0=safe, 100=extremely risky)
    action:        "buy" | "sell" | "hold"
    size_fraction: 0.0-1.0 — fraction of available budget to deploy
    confidence:    0-100
    reasoning:     explanation of the verdict
    """
    risk_score: int = 100
    action: str = "hold"
    size_fraction: float = 0.0
    confidence: int = 0
    reasoning: str = ""

    def __post_init__(self):
        self.risk_score = max(0, min(100, int(self.risk_score)))
        if self.action not in _VALID_ACTIONS:
            self.action = "hold"
        self.size_fraction = max(0.0, min(1.0, float(self.size_fraction)))
        self.confidence = max(0, min(100, int(self.confidence)))

    @classmethod
    def hold_default(cls) -> "RiskVerdict":
        return cls(risk_score=100, action="hold", size_fraction=0.0, confidence=0,
                   reasoning="Risk judge unavailable — holding as a precaution.")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskVerdict":
        return cls(
            risk_score=int(data.get("risk_score", 100)),
            action=str(data.get("action", "hold")).lower(),
            size_fraction=float(data.get("size_fraction", 0.0)),
            confidence=int(data.get("confidence", 0)),
            reasoning=str(data.get("reasoning", "")),
        )


# ---------------------------------------------------------------------------
# Distribution Agent output
# ---------------------------------------------------------------------------

@dataclass
class DistributionPlan:
    """Allocation plan produced by the Distribution Agent.

    action:           mirrors RiskVerdict.action
    deploy_fraction:  0.0-1.0 — actual fraction of budget to deploy (may be
                      capped below RiskVerdict.size_fraction by budget limits)
    deploy_amount:    absolute quote-currency amount to deploy (0 = none)
    reasoning:        explanation of sizing
    budget_limited:   True if plan was capped by available budget
    """
    action: str = "hold"
    deploy_fraction: float = 0.0
    deploy_amount: float = 0.0
    reasoning: str = ""
    budget_limited: bool = False

    def __post_init__(self):
        if self.action not in _VALID_ACTIONS:
            self.action = "hold"
        self.deploy_fraction = max(0.0, min(1.0, float(self.deploy_fraction)))
        self.deploy_amount = max(0.0, float(self.deploy_amount))

    @classmethod
    def hold_default(cls) -> "DistributionPlan":
        return cls(action="hold", deploy_fraction=0.0, deploy_amount=0.0,
                   reasoning="Distribution agent unavailable — no allocation.")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DistributionPlan":
        return cls(
            action=str(data.get("action", "hold")).lower(),
            deploy_fraction=float(data.get("deploy_fraction", 0.0)),
            deploy_amount=float(data.get("deploy_amount", 0.0)),
            reasoning=str(data.get("reasoning", "")),
            budget_limited=bool(data.get("budget_limited", False)),
        )


# ---------------------------------------------------------------------------
# Full audit-trail result returned by the orchestrator
# ---------------------------------------------------------------------------

@dataclass
class AITeamResult:
    """Complete output of one AITeamOrchestrator run.

    Carries every agent's output for the audit trail, plus the final decision.
    """
    signal: SignalAssessment = field(default_factory=SignalAssessment.conservative_default)
    bull: BullCase = field(default_factory=BullCase.conservative_default)
    bear: BearCase = field(default_factory=BearCase.conservative_default)
    verdict: RiskVerdict = field(default_factory=RiskVerdict.hold_default)
    plan: DistributionPlan = field(default_factory=DistributionPlan.hold_default)
    timed_out: bool = False
    error: Optional[str] = None

    @property
    def action(self) -> str:
        return self.plan.action

    @property
    def deploy_amount(self) -> float:
        return self.plan.deploy_amount

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict suitable for JSON storage."""
        return {
            "signal": {
                "trend": self.signal.trend,
                "momentum": self.signal.momentum,
                "key_levels": self.signal.key_levels,
                "summary": self.signal.summary,
            },
            "bull": {
                "conviction": self.bull.conviction,
                "catalysts": self.bull.catalysts,
                "target_price": self.bull.target_price,
                "reasoning": self.bull.reasoning,
            },
            "bear": {
                "conviction": self.bear.conviction,
                "risks": self.bear.risks,
                "floor_price": self.bear.floor_price,
                "reasoning": self.bear.reasoning,
            },
            "verdict": {
                "risk_score": self.verdict.risk_score,
                "action": self.verdict.action,
                "size_fraction": self.verdict.size_fraction,
                "confidence": self.verdict.confidence,
                "reasoning": self.verdict.reasoning,
            },
            "plan": {
                "action": self.plan.action,
                "deploy_fraction": self.plan.deploy_fraction,
                "deploy_amount": self.plan.deploy_amount,
                "reasoning": self.plan.reasoning,
                "budget_limited": self.plan.budget_limited,
            },
            "timed_out": self.timed_out,
            "error": self.error,
        }
