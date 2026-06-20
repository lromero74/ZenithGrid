"""AI Trading Team — orchestrated multi-agent debate before trade decisions.

Each specialist agent analyses a slice of the trading problem; the orchestrator
runs them in a DAG and returns a final decision with a full audit trail.

Public surface used by the ai_team_trading strategy:
    from app.ai_team.team_orchestrator import AITeamOrchestrator, AITeamResult
"""

from app.ai_team.schemas import (
    SignalAssessment,
    BullCase,
    BearCase,
    RiskVerdict,
    DistributionPlan,
    AITeamResult,
)
from app.ai_team.team_orchestrator import AITeamOrchestrator

__all__ = [
    "AITeamOrchestrator",
    "AITeamResult",
    "BearCase",
    "BullCase",
    "DistributionPlan",
    "RiskVerdict",
    "SignalAssessment",
]
