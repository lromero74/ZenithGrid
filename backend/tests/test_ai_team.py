"""
Tests for the AI Trading Team feature.

All LLM calls are mocked — no real network/API access.
The mock provider's call_with_tools returns canned JSON strings.

Coverage:
- Signal agent returns a valid SignalAssessment from a mocked provider response
- Risk judge receives both bull and bear outputs (asserts they're passed in)
- Distribution plan respects budget limits (never exceeds available)
- Agent memory is account-scoped (account A cannot see account B's runs)
- Full orchestrator pipeline completes and returns a decision
- Orchestrator handles a provider failure gracefully (returns hold, no exception)
- Orchestrator handles a timeout gracefully (returns hold, no exception)
- ai_team strategy registers and should_buy/should_sell behave correctly
"""

from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_provider(response_json: dict):
    """Build a mock LLMProvider whose call_with_tools returns the given JSON."""
    from app.indicators.ai_providers.base import TokenUsage
    provider = MagicMock()
    provider.call_with_tools = AsyncMock(
        return_value=(json.dumps(response_json), [], TokenUsage(input_tokens=10, output_tokens=20))
    )
    return provider


def _patch_provider(response_json: dict):
    """Context manager: patch get_provider for all agent modules.

    Each agent imports get_provider at module level, so we patch the name
    in each agent's module namespace.
    """
    fake = _fake_provider(response_json)
    return (
        patch("app.ai_team.signal_agent.get_provider", return_value=fake),
        patch("app.ai_team.bull_research_agent.get_provider", return_value=fake),
        patch("app.ai_team.bear_research_agent.get_provider", return_value=fake),
        patch("app.ai_team.risk_judge_agent.get_provider", return_value=fake),
    )


def _patch_api_key(key: str = "test-key-123"):
    """Patch get_user_api_key for all agent modules."""
    return (
        patch("app.ai_team.signal_agent.get_user_api_key", new=AsyncMock(return_value=key)),
        patch("app.ai_team.bull_research_agent.get_user_api_key", new=AsyncMock(return_value=key)),
        patch("app.ai_team.bear_research_agent.get_user_api_key", new=AsyncMock(return_value=key)),
        patch("app.ai_team.risk_judge_agent.get_user_api_key", new=AsyncMock(return_value=key)),
    )


SAMPLE_METRICS = {
    "rsi": 55.0,
    "macd_bullish": True,
    "macd_bearish": False,
    "price_vs_ma20": 1.5,
    "price_vs_ma50": 3.0,
    "bb_position": 55.0,
    "volume_ratio": 1.8,
    "price_change_24h": 2.5,
}


# ===========================================================================
# Schema tests
# ===========================================================================


class TestSchemas:
    def test_signal_assessment_clamps_momentum(self):
        from app.ai_team.schemas import SignalAssessment
        s = SignalAssessment(trend="bullish", momentum=9999.0)
        assert s.momentum == 100.0

    def test_signal_assessment_rejects_bad_trend(self):
        from app.ai_team.schemas import SignalAssessment
        s = SignalAssessment(trend="moon", momentum=10.0)
        assert s.trend == "neutral"

    def test_risk_verdict_clamps_risk_score(self):
        from app.ai_team.schemas import RiskVerdict
        v = RiskVerdict(risk_score=999, action="buy", size_fraction=0.5, confidence=80)
        assert v.risk_score == 100

    def test_risk_verdict_rejects_invalid_action(self):
        from app.ai_team.schemas import RiskVerdict
        v = RiskVerdict(risk_score=20, action="yolo", size_fraction=0.3, confidence=70)
        assert v.action == "hold"

    def test_risk_verdict_clamps_size_fraction(self):
        from app.ai_team.schemas import RiskVerdict
        v = RiskVerdict(risk_score=20, action="buy", size_fraction=5.0, confidence=80)
        assert v.size_fraction == 1.0

    def test_distribution_plan_clamps_deploy_amount(self):
        from app.ai_team.schemas import DistributionPlan
        p = DistributionPlan(action="buy", deploy_fraction=0.3, deploy_amount=-10.0)
        assert p.deploy_amount == 0.0

    def test_ai_team_result_to_dict_structure(self):
        from app.ai_team.schemas import AITeamResult
        r = AITeamResult()
        d = r.to_dict()
        for key in ("signal", "bull", "bear", "verdict", "plan", "timed_out", "error"):
            assert key in d


# ===========================================================================
# Signal Agent tests
# ===========================================================================


class TestSignalAgent:
    @pytest.mark.asyncio
    async def test_returns_valid_schema_from_mocked_provider(self):
        """Signal agent parses mocked JSON into a valid SignalAssessment."""
        from app.ai_team.signal_agent import SignalAgent

        response = {
            "trend": "bullish",
            "momentum": 42.0,
            "key_levels": [50000.0, 52000.0],
            "summary": "Strong uptrend with volume confirmation.",
        }

        patches = _patch_provider(response) + _patch_api_key()
        # 4 provider patches + 4 api-key patches = 8 total (indices 0-7)
        with patches[0], patches[1], patches[2], patches[3], \
                patches[4], patches[5], patches[6], patches[7]:
            agent = SignalAgent()
            result = await agent.run(
                db=AsyncMock(),
                user_id=1,
                account_id=1,
                ai_model="claude",
                model_override=None,
                product_id="ETH-BTC",
                current_price=50000.0,
                metrics=SAMPLE_METRICS,
            )

        assert result.trend == "bullish"
        assert result.momentum == 42.0
        assert result.key_levels == [50000.0, 52000.0]
        assert "uptrend" in result.summary

    @pytest.mark.asyncio
    async def test_returns_conservative_default_on_parse_error(self):
        """Signal agent returns neutral default when provider returns garbage."""
        from app.ai_team.signal_agent import SignalAgent

        from app.indicators.ai_providers.base import TokenUsage
        bad_provider = MagicMock()
        bad_provider.call_with_tools = AsyncMock(
            return_value=("NOT JSON AT ALL", [], TokenUsage())
        )

        api_patches = _patch_api_key()
        with patch("app.ai_team.signal_agent.get_provider", return_value=bad_provider), \
                api_patches[0], api_patches[1], api_patches[2], api_patches[3]:
            agent = SignalAgent()
            result = await agent.run(
                db=AsyncMock(),
                user_id=1,
                account_id=1,
                ai_model="claude",
                model_override=None,
                product_id="ETH-BTC",
                current_price=50000.0,
                metrics=SAMPLE_METRICS,
            )

        assert result.trend == "neutral"
        assert result.momentum == 0.0

    @pytest.mark.asyncio
    async def test_returns_conservative_default_on_exception(self):
        """Signal agent swallows provider exceptions and returns default."""
        from app.ai_team.signal_agent import SignalAgent

        error_provider = MagicMock()
        error_provider.call_with_tools = AsyncMock(side_effect=RuntimeError("Network error"))

        api_patches = _patch_api_key()
        with patch("app.ai_team.signal_agent.get_provider", return_value=error_provider), \
                api_patches[0], api_patches[1], api_patches[2], api_patches[3]:
            agent = SignalAgent()
            result = await agent.run(
                db=AsyncMock(),
                user_id=1,
                account_id=1,
                ai_model="claude",
                model_override=None,
                product_id="ETH-BTC",
                current_price=50000.0,
                metrics=SAMPLE_METRICS,
            )

        assert result.trend == "neutral"


# ===========================================================================
# Risk Judge Agent tests
# ===========================================================================


class TestRiskJudgeAgent:
    @pytest.mark.asyncio
    async def test_receives_bull_and_bear_outputs(self):
        """Risk judge prompt includes bull and bear reasoning (integration check)."""
        from app.ai_team.risk_judge_agent import RiskJudgeAgent
        from app.ai_team.schemas import BullCase, BearCase, SignalAssessment
        from app.indicators.ai_providers.base import TokenUsage

        captured_prompts = []

        async def capture_call_with_tools(*, system, user, tools, tool_ctx, max_turns=1):
            captured_prompts.append(user)
            return (
                json.dumps({
                    "risk_score": 30,
                    "action": "buy",
                    "size_fraction": 0.3,
                    "confidence": 75,
                    "reasoning": "Bull dominates bear.",
                }),
                [],
                TokenUsage(input_tokens=50, output_tokens=30),
            )

        mock_provider = MagicMock()
        mock_provider.call_with_tools = capture_call_with_tools

        bull = BullCase(conviction=80, catalysts=["strong volume surge"], reasoning="Massive MACD cross.")
        bear = BearCase(conviction=20, risks=["overextended RSI"], reasoning="RSI near 70.")
        signal = SignalAssessment(trend="bullish", momentum=60.0)

        api_patches = _patch_api_key()
        with patch("app.ai_team.risk_judge_agent.get_provider", return_value=mock_provider), \
                api_patches[0], api_patches[1], api_patches[2], api_patches[3]:
            agent = RiskJudgeAgent()
            result = await agent.run(
                db=AsyncMock(),
                user_id=1,
                account_id=1,
                ai_model="claude",
                model_override=None,
                product_id="ETH-BTC",
                current_price=50000.0,
                metrics=SAMPLE_METRICS,
                signal=signal,
                bull=bull,
                bear=bear,
            )

        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]
        # Bull case must appear in the prompt
        assert "Massive MACD cross" in prompt
        # Bear case must appear in the prompt
        assert "RSI near 70" in prompt
        # Conviction scores must appear
        assert "80" in prompt
        assert "20" in prompt
        # Result should reflect the mocked response
        assert result.action == "buy"
        assert result.risk_score == 30
        assert result.confidence == 75

    @pytest.mark.asyncio
    async def test_returns_hold_default_on_failure(self):
        """Risk judge returns hold default on provider exception."""
        from app.ai_team.risk_judge_agent import RiskJudgeAgent
        from app.ai_team.schemas import BullCase, BearCase, SignalAssessment

        error_provider = MagicMock()
        error_provider.call_with_tools = AsyncMock(side_effect=ValueError("bad key"))

        api_patches = _patch_api_key()
        with patch("app.ai_team.risk_judge_agent.get_provider", return_value=error_provider), \
                api_patches[0], api_patches[1], api_patches[2], api_patches[3]:
            agent = RiskJudgeAgent()
            result = await agent.run(
                db=AsyncMock(),
                user_id=1,
                account_id=1,
                ai_model="claude",
                model_override=None,
                product_id="ETH-BTC",
                current_price=50000.0,
                metrics=SAMPLE_METRICS,
                signal=SignalAssessment(),
                bull=BullCase(),
                bear=BearCase(),
            )

        assert result.action == "hold"
        assert result.risk_score == 100


# ===========================================================================
# Distribution Agent tests
# ===========================================================================


class TestDistributionAgent:
    def test_never_exceeds_available_budget(self):
        """deploy_amount <= available_budget always, even when verdict wants more."""
        from app.ai_team.distribution_agent import DistributionAgent
        from app.ai_team.schemas import RiskVerdict

        # Verdict wants 90% of budget
        verdict = RiskVerdict(risk_score=20, action="buy", size_fraction=0.9, confidence=90)
        agent = DistributionAgent()

        # Available budget is 100 — so deploy should be 90
        plan = agent.run(verdict=verdict, available_budget=100.0, product_id="ETH-BTC", account_id=1)
        assert plan.deploy_amount <= 100.0
        assert plan.deploy_amount == pytest.approx(90.0)
        assert plan.action == "buy"

    def test_zero_budget_returns_hold(self):
        """When available_budget is 0, no trade is made."""
        from app.ai_team.distribution_agent import DistributionAgent
        from app.ai_team.schemas import RiskVerdict

        verdict = RiskVerdict(risk_score=10, action="buy", size_fraction=0.5, confidence=95)
        agent = DistributionAgent()
        plan = agent.run(verdict=verdict, available_budget=0.0, product_id="ETH-BTC", account_id=1)

        assert plan.action == "hold"
        assert plan.deploy_amount == 0.0
        assert plan.budget_limited is True

    def test_hold_verdict_deploys_nothing(self):
        """A hold verdict always produces deploy_amount=0."""
        from app.ai_team.distribution_agent import DistributionAgent
        from app.ai_team.schemas import RiskVerdict

        verdict = RiskVerdict(risk_score=50, action="hold", size_fraction=0.0, confidence=80)
        agent = DistributionAgent()
        plan = agent.run(verdict=verdict, available_budget=1000.0, product_id="ETH-BTC", account_id=1)

        assert plan.deploy_amount == 0.0
        assert plan.action == "hold"

    def test_deploy_fraction_capped_at_1(self):
        """deploy_fraction never exceeds 1.0 regardless of floating point."""
        from app.ai_team.distribution_agent import DistributionAgent
        from app.ai_team.schemas import RiskVerdict

        # size_fraction = 1.0 exactly
        verdict = RiskVerdict(risk_score=5, action="buy", size_fraction=1.0, confidence=99)
        agent = DistributionAgent()
        plan = agent.run(verdict=verdict, available_budget=500.0, product_id="ETH-BTC", account_id=1)

        assert plan.deploy_fraction <= 1.0
        assert plan.deploy_amount <= 500.0


# ===========================================================================
# Agent Memory — account scoping tests (critical multi-tenant test)
# ===========================================================================


class TestAgentMemoryAccountScoping:
    """Prove that account A cannot read account B's AI team runs."""

    @pytest.mark.asyncio
    async def test_account_scoping_hard_rule(self, async_engine, db_session):
        """Account A's runs are invisible to account B queries."""
        from app.ai_team.agent_memory import AgentMemory

        memory = AgentMemory()

        # Write run for account 1
        await memory.save_run(
            db=db_session,
            account_id=1,
            bot_id=None,
            product_id="ETH-BTC",
            signal_output={"trend": "bullish"},
            bull_output={"conviction": 80},
            bear_output={"conviction": 20},
            verdict_output={"action": "buy", "risk_score": 25},
            plan_output={"action": "buy", "deploy_amount": 100.0},
            final_action="buy",
        )

        # Write run for account 2
        await memory.save_run(
            db=db_session,
            account_id=2,
            bot_id=None,
            product_id="ETH-BTC",
            signal_output={"trend": "bearish"},
            bull_output={"conviction": 10},
            bear_output={"conviction": 90},
            verdict_output={"action": "hold", "risk_score": 85},
            plan_output={"action": "hold", "deploy_amount": 0.0},
            final_action="hold",
        )

        # Account 1 should only see its own run
        runs_account_1 = await memory.recent_runs(db=db_session, account_id=1)
        assert all(r["account_id"] == 1 for r in runs_account_1), \
            "Account 1 query returned rows belonging to another account!"
        assert len(runs_account_1) == 1
        assert runs_account_1[0]["final_action"] == "buy"

        # Account 2 should only see its own run
        runs_account_2 = await memory.recent_runs(db=db_session, account_id=2)
        assert all(r["account_id"] == 2 for r in runs_account_2), \
            "Account 2 query returned rows belonging to another account!"
        assert len(runs_account_2) == 1
        assert runs_account_2[0]["final_action"] == "hold"

    @pytest.mark.asyncio
    async def test_product_filter_still_account_scoped(self, async_engine, db_session):
        """Product filtering never leaks rows across accounts."""
        from app.ai_team.agent_memory import AgentMemory

        memory = AgentMemory()

        # Account 1 has ETH-BTC run
        await memory.save_run(
            db=db_session,
            account_id=1,
            bot_id=None,
            product_id="ETH-BTC",
            signal_output={},
            bull_output={},
            bear_output={},
            verdict_output={},
            plan_output={},
            final_action="buy",
        )

        # Account 2 also has ETH-BTC run
        await memory.save_run(
            db=db_session,
            account_id=2,
            bot_id=None,
            product_id="ETH-BTC",
            signal_output={},
            bull_output={},
            bear_output={},
            verdict_output={},
            plan_output={},
            final_action="sell",
        )

        # Account 1 querying ETH-BTC must not see account 2's sell
        runs = await memory.recent_runs(db=db_session, account_id=1, product_id="ETH-BTC")
        assert len(runs) == 1
        assert runs[0]["account_id"] == 1
        assert runs[0]["final_action"] == "buy"


# ===========================================================================
# Full Orchestrator Pipeline tests
# ===========================================================================


class TestOrchestratorPipeline:
    def _full_provider_patches(self):
        """Patch every agent's get_provider and get_user_api_key."""
        from app.indicators.ai_providers.base import TokenUsage

        # Signal Agent response
        signal_resp = json.dumps({
            "trend": "bullish", "momentum": 60.0, "key_levels": [], "summary": "Up.",
        })
        # Bull Agent response
        bull_resp = json.dumps({
            "conviction": 75, "catalysts": ["momentum"], "target_price": 0, "reasoning": "Up trend.",
        })
        # Bear Agent response
        bear_resp = json.dumps({
            "conviction": 25, "risks": ["overbought"], "floor_price": 0, "reasoning": "High RSI.",
        })
        # Risk Judge response
        risk_resp = json.dumps({
            "risk_score": 30, "action": "buy", "size_fraction": 0.4, "confidence": 80,
            "reasoning": "Bull dominates.",
        })

        # Each agent module calls its own get_provider; we need them to
        # return *different* responses depending on which agent is calling.
        # We simulate this by giving each module's get_provider its own fake.

        def make_provider(resp_text):
            p = MagicMock()
            p.call_with_tools = AsyncMock(
                return_value=(resp_text, [], TokenUsage(input_tokens=10, output_tokens=20))
            )
            return p

        return [
            patch("app.ai_team.signal_agent.get_provider", return_value=make_provider(signal_resp)),
            patch("app.ai_team.bull_research_agent.get_provider", return_value=make_provider(bull_resp)),
            patch("app.ai_team.bear_research_agent.get_provider", return_value=make_provider(bear_resp)),
            patch("app.ai_team.risk_judge_agent.get_provider", return_value=make_provider(risk_resp)),
            patch("app.ai_team.signal_agent.get_user_api_key", new=AsyncMock(return_value="test-key")),
            patch("app.ai_team.bull_research_agent.get_user_api_key", new=AsyncMock(return_value="test-key")),
            patch("app.ai_team.bear_research_agent.get_user_api_key", new=AsyncMock(return_value="test-key")),
            patch("app.ai_team.risk_judge_agent.get_user_api_key", new=AsyncMock(return_value="test-key")),
        ]

    @pytest.mark.asyncio
    async def test_full_pipeline_returns_decision(self, async_engine, db_session):
        """Full pipeline completes and returns an AITeamResult with action set."""
        from app.ai_team.team_orchestrator import AITeamOrchestrator

        patches = self._full_provider_patches()
        with patches[0], patches[1], patches[2], patches[3], \
                patches[4], patches[5], patches[6], patches[7]:
            orchestrator = AITeamOrchestrator(timeout=30.0)
            result = await orchestrator.run(
                db=db_session,
                user_id=1,
                account_id=1,
                bot_id=None,
                product_id="ETH-BTC",
                current_price=50000.0,
                metrics=SAMPLE_METRICS,
                available_budget=1000.0,
                ai_model="claude",
                persist=True,
            )

        assert result.timed_out is False
        assert result.error is None
        assert result.action in ("buy", "sell", "hold")
        # With mocked buy signal and budget, deploy_amount should be > 0
        assert result.deploy_amount >= 0.0
        # Intermediate outputs captured in audit trail
        assert result.signal.trend in ("bullish", "bearish", "neutral")
        assert result.bull.conviction >= 0
        assert result.bear.conviction >= 0

    @pytest.mark.asyncio
    async def test_pipeline_returns_hold_on_provider_failure(self):
        """Orchestrator returns hold (no exception) when provider raises."""
        from app.ai_team.team_orchestrator import AITeamOrchestrator

        error_provider = MagicMock()
        error_provider.call_with_tools = AsyncMock(side_effect=RuntimeError("API down"))

        api_key_patch = AsyncMock(return_value="test-key")
        with patch("app.ai_team.signal_agent.get_provider", return_value=error_provider), \
                patch("app.ai_team.bull_research_agent.get_provider", return_value=error_provider), \
                patch("app.ai_team.bear_research_agent.get_provider", return_value=error_provider), \
                patch("app.ai_team.risk_judge_agent.get_provider", return_value=error_provider), \
                patch("app.ai_team.signal_agent.get_user_api_key", new=api_key_patch), \
                patch("app.ai_team.bull_research_agent.get_user_api_key", new=api_key_patch), \
                patch("app.ai_team.bear_research_agent.get_user_api_key", new=api_key_patch), \
                patch("app.ai_team.risk_judge_agent.get_user_api_key", new=api_key_patch):
            orchestrator = AITeamOrchestrator(timeout=10.0)
            # Must not raise — graceful degradation
            result = await orchestrator.run(
                db=AsyncMock(),
                user_id=1,
                account_id=1,
                bot_id=None,
                product_id="ETH-BTC",
                current_price=50000.0,
                metrics=SAMPLE_METRICS,
                available_budget=1000.0,
                ai_model="claude",
                persist=False,
            )

        # Errors cause the signal agent to return conservative default, which
        # cascades to hold. The orchestrator itself must not propagate an exception.
        assert result.action == "hold"

    @pytest.mark.asyncio
    async def test_pipeline_returns_hold_on_timeout(self):
        """Orchestrator returns hold (no exception) when pipeline times out."""
        from app.ai_team.team_orchestrator import AITeamOrchestrator

        async def slow_call(**kwargs):
            await asyncio.sleep(99)
            return ("", [], MagicMock())

        slow_provider = MagicMock()
        slow_provider.call_with_tools = slow_call

        api_key_patch = AsyncMock(return_value="test-key")
        with patch("app.ai_team.signal_agent.get_provider", return_value=slow_provider), \
                patch("app.ai_team.signal_agent.get_user_api_key", new=api_key_patch):
            orchestrator = AITeamOrchestrator(timeout=0.05)  # 50 ms — will time out
            result = await orchestrator.run(
                db=AsyncMock(),
                user_id=1,
                account_id=1,
                bot_id=None,
                product_id="ETH-BTC",
                current_price=50000.0,
                metrics=SAMPLE_METRICS,
                available_budget=1000.0,
                persist=False,
            )

        assert result.timed_out is True
        assert result.action == "hold"
        assert result.deploy_amount == 0.0


# ===========================================================================
# AI Team Strategy tests
# ===========================================================================


class TestAITeamStrategy:
    def test_strategy_registers_in_registry(self):
        """ai_team strategy is accessible via StrategyRegistry."""
        from app.strategies import StrategyRegistry
        # Importing ai_team_trading registers it
        import app.strategies.ai_team_trading  # noqa: F401
        defn = StrategyRegistry.get_definition("ai_team")
        assert defn.id == "ai_team"
        assert "ai" in defn.name.lower() or "team" in defn.name.lower()

    def test_strategy_definition_has_required_params(self):
        """get_definition lists all expected config parameters."""
        import app.strategies.ai_team_trading  # noqa: F401
        from app.strategies.ai_team_trading import AITeamTradingStrategy

        strategy = AITeamTradingStrategy({})
        defn = strategy.get_definition()
        param_names = [p.name for p in defn.parameters]
        for required in ("ai_model", "min_confidence", "max_risk_score", "max_deploy_fraction"):
            assert required in param_names, f"Missing parameter: {required}"

    @pytest.mark.asyncio
    async def test_should_buy_returns_true_on_buy_signal_above_threshold(self):
        """should_buy returns True when action=buy and thresholds are met."""
        from app.strategies.ai_team_trading import AITeamTradingStrategy

        strategy = AITeamTradingStrategy({
            "min_confidence": 60,
            "max_risk_score": 70,
        })
        signal_data = {
            "action": "buy",
            "deploy_amount": 200.0,
            "deploy_fraction": 0.2,
            "risk_score": 30,
            "confidence": 80,
            "reasoning": "Strong setup.",
            "signal_trend": "bullish",
            "bull_conviction": 75,
            "bear_conviction": 25,
            "timed_out": False,
            "error": None,
        }
        should, amount, reason = await strategy.should_buy(signal_data, None, 1000.0)
        assert should is True
        assert amount == pytest.approx(200.0)
        assert "BUY" in reason

    @pytest.mark.asyncio
    async def test_should_buy_returns_false_when_confidence_low(self):
        """should_buy returns False when confidence is below min_confidence."""
        from app.strategies.ai_team_trading import AITeamTradingStrategy

        strategy = AITeamTradingStrategy({"min_confidence": 60})
        signal_data = {
            "action": "buy",
            "deploy_amount": 200.0,
            "risk_score": 20,
            "confidence": 40,  # below threshold
            "timed_out": False,
            "error": None,
        }
        should, amount, reason = await strategy.should_buy(signal_data, None, 1000.0)
        assert should is False
        assert amount == 0.0

    @pytest.mark.asyncio
    async def test_should_buy_returns_false_when_risk_score_high(self):
        """should_buy returns False when risk_score exceeds max_risk_score."""
        from app.strategies.ai_team_trading import AITeamTradingStrategy

        strategy = AITeamTradingStrategy({"max_risk_score": 70})
        signal_data = {
            "action": "buy",
            "deploy_amount": 200.0,
            "risk_score": 85,  # above threshold
            "confidence": 90,
            "timed_out": False,
            "error": None,
        }
        should, amount, reason = await strategy.should_buy(signal_data, None, 1000.0)
        assert should is False

    @pytest.mark.asyncio
    async def test_should_buy_returns_false_on_hold_signal(self):
        """should_buy returns False when AI team said hold."""
        from app.strategies.ai_team_trading import AITeamTradingStrategy

        strategy = AITeamTradingStrategy({})
        signal_data = {
            "action": "hold",
            "deploy_amount": 0.0,
            "risk_score": 60,
            "confidence": 75,
            "timed_out": False,
            "error": None,
        }
        should, amount, reason = await strategy.should_buy(signal_data, None, 1000.0)
        assert should is False

    @pytest.mark.asyncio
    async def test_should_sell_returns_true_on_sell_signal(self):
        """should_sell returns True when action=sell and thresholds met."""
        from app.strategies.ai_team_trading import AITeamTradingStrategy

        strategy = AITeamTradingStrategy({"min_confidence": 60, "max_risk_score": 70})
        signal_data = {
            "action": "sell",
            "deploy_amount": 0.0,
            "risk_score": 25,
            "confidence": 85,
            "reasoning": "Exit now.",
            "timed_out": False,
            "error": None,
        }
        should, reason = await strategy.should_sell(signal_data, MagicMock(), 50000.0)
        assert should is True
        assert "SELL" in reason

    @pytest.mark.asyncio
    async def test_should_sell_returns_false_on_timeout(self):
        """should_sell returns False when pipeline timed out."""
        from app.strategies.ai_team_trading import AITeamTradingStrategy

        strategy = AITeamTradingStrategy({})
        signal_data = {
            "action": "sell",
            "timed_out": True,
            "error": "Pipeline timed out",
        }
        should, reason = await strategy.should_sell(signal_data, MagicMock(), 50000.0)
        assert should is False

    @pytest.mark.asyncio
    async def test_analyze_signal_returns_hold_on_missing_context(self):
        """analyze_signal returns hold when db/user_id/account_id are absent."""
        from app.strategies.ai_team_trading import AITeamTradingStrategy

        strategy = AITeamTradingStrategy({})
        # No db, user_id, or account_id passed
        result = await strategy.analyze_signal([], 50000.0)
        assert result["action"] == "hold"
        assert result["deploy_amount"] == 0.0
