"""Tests for evaluate() routing + Phase-A context injection in AISpotOpinionEvaluator.

Phase B moved the provider-specific tool loops into app.indicators.ai_providers,
so the direct Claude-loop tests now live in tests/indicators/ai_providers/. What
remains here is the evaluator's responsibility:
- evaluate() always goes single-shot through _call_llm in Phase A (no argument
  tools exist yet → no reason to enter the provider tool loop)
- _collect_auto_context pre-fetches portfolio + position for prompt injection
- _build_prompt renders that context as a JSON block
- Every provider receives the same context-injected prompt

Uses importlib.util.spec_from_file_location for the evaluator to stay consistent
with test_ai_spot_opinion.py's loading pattern; the cycle it originally worked
around is gone, but the direct-load approach still works.
"""

import importlib.util
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_spec = importlib.util.spec_from_file_location(
    "app.indicators.ai_spot_opinion",
    "/home/ec2-user/ZenithGrid/backend/app/indicators/ai_spot_opinion.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("app.indicators.ai_spot_opinion", _mod)
_spec.loader.exec_module(_mod)

AISpotOpinionEvaluator = _mod.AISpotOpinionEvaluator
AISpotOpinionParams = _mod.AISpotOpinionParams

from app.indicators.ai_tools import ToolContext  # noqa: E402


def _make_candles(count=60, base_price=100.0, volume=1500.0):
    return [
        {
            "open": (base_price + i * 0.5) * 0.999,
            "high": (base_price + i * 0.5) * 1.005,
            "low": (base_price + i * 0.5) * 0.995,
            "close": base_price + i * 0.5,
            "volume": volume,
        }
        for i in range(count)
    ]


class TestEvaluateRouting:
    """evaluate() always goes single-shot in Phase A — no argument-taking tools exist yet."""

    @pytest.mark.asyncio
    async def test_gpt_model_goes_single_shot(self):
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams(ai_model="gpt", enable_buy_prefilter=False)

        with patch.object(evaluator, "_call_llm",
                          new_callable=AsyncMock, return_value=("buy", 70, "r")) as single_shot:
            result = await evaluator.evaluate(
                candles=_make_candles(60), current_price=100.0,
                product_id="BTC-USD", db=MagicMock(), user_id=1,
                params=params, is_sell_check=False, account_id=1,
            )

        single_shot.assert_awaited_once()
        assert result["tool_calls"] == []
        assert result["signal"] == "buy"

    @pytest.mark.asyncio
    async def test_claude_without_account_id_goes_single_shot(self):
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams(ai_model="claude", enable_buy_prefilter=False)

        with patch.object(evaluator, "_call_llm",
                          new_callable=AsyncMock, return_value=("hold", 50, "r")) as single_shot:
            await evaluator.evaluate(
                candles=_make_candles(60), current_price=100.0,
                product_id="BTC-USD", db=MagicMock(), user_id=1,
                params=params, is_sell_check=False, account_id=None,
            )

        single_shot.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_claude_with_account_id_goes_single_shot_with_context(self):
        """Phase A: no argument-taking tools exist, so Claude+account_id still runs single-shot.
        Context is pre-injected into the prompt via _collect_auto_context."""
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams(ai_model="claude", enable_buy_prefilter=False)

        with patch.object(evaluator, "_call_llm",
                          new_callable=AsyncMock,
                          return_value=("buy", 82, "great setup")) as single_shot:
            result = await evaluator.evaluate(
                candles=_make_candles(60), current_price=100.0,
                product_id="BTC-USD", db=MagicMock(), user_id=1,
                params=params, is_sell_check=False, account_id=42,
            )

        single_shot.assert_awaited_once()
        assert result["signal"] == "buy"
        assert result["confidence"] == 82


class TestContextInjection:
    """Phase A: auto-context (portfolio + position) is pre-fetched and injected
    into the prompt for every provider on every call."""

    @pytest.mark.asyncio
    async def test_context_collected_when_account_id_provided(self):
        evaluator = AISpotOpinionEvaluator()
        ctx = ToolContext(
            db=MagicMock(), user_id=1, product_id="ETH-USD",
            current_price=100.0, account_id=5,
        )
        with patch.object(_mod, "execute_tool",
                          new_callable=AsyncMock,
                          return_value={"open_position_count_total": 3}) as tool:
            context = await evaluator._collect_auto_context(ctx)

        assert "portfolio" in context
        assert context["portfolio"] == {"open_position_count_total": 3}
        called_names = {c.args[0] for c in tool.await_args_list}
        assert "get_portfolio_context" in called_names
        assert "get_position_context" not in called_names

    @pytest.mark.asyncio
    async def test_context_omitted_when_no_account_id(self):
        evaluator = AISpotOpinionEvaluator()
        ctx = ToolContext(
            db=MagicMock(), user_id=1, product_id="ETH-USD",
            current_price=100.0, account_id=None,
        )
        with patch.object(_mod, "execute_tool",
                          new_callable=AsyncMock) as tool:
            context = await evaluator._collect_auto_context(ctx)

        assert context == {}
        tool.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_position_context_included_on_sell_check(self):
        evaluator = AISpotOpinionEvaluator()
        ctx = ToolContext(
            db=MagicMock(), user_id=1, product_id="ETH-USD",
            current_price=100.0, account_id=5, is_sell_check=True,
        )
        with patch.object(_mod, "execute_tool",
                          new_callable=AsyncMock,
                          return_value={"marker": "data"}) as tool:
            context = await evaluator._collect_auto_context(ctx)

        assert "position" in context
        called_names = {c.args[0] for c in tool.await_args_list}
        assert "get_position_context" in called_names

    @pytest.mark.asyncio
    async def test_position_context_included_when_position_present(self):
        evaluator = AISpotOpinionEvaluator()
        ctx = ToolContext(
            db=MagicMock(), user_id=1, product_id="ETH-USD",
            current_price=100.0, account_id=5, position=MagicMock(id=99),
        )
        with patch.object(_mod, "execute_tool",
                          new_callable=AsyncMock,
                          return_value={"marker": "data"}) as tool:
            context = await evaluator._collect_auto_context(ctx)

        assert "position" in context
        called_names = {c.args[0] for c in tool.await_args_list}
        assert "get_position_context" in called_names

    @pytest.mark.asyncio
    async def test_position_context_omitted_on_buy_check_with_no_position(self):
        evaluator = AISpotOpinionEvaluator()
        ctx = ToolContext(
            db=MagicMock(), user_id=1, product_id="ETH-USD",
            current_price=100.0, account_id=5, is_sell_check=False, position=None,
        )
        with patch.object(_mod, "execute_tool",
                          new_callable=AsyncMock,
                          return_value={"marker": "data"}) as tool:
            context = await evaluator._collect_auto_context(ctx)

        assert "position" not in context
        called_names = {c.args[0] for c in tool.await_args_list}
        assert "get_position_context" not in called_names

    def test_prompt_includes_json_context_block(self):
        context = {"portfolio": {"open_position_count_total": 3},
                   "position": {"minutes_held": 45}}
        prompt = AISpotOpinionEvaluator._build_prompt(
            product_id="ETH-USD",
            metrics={"rsi": 55.0, "volume_ratio": 1.5, "price_change_24h": 2.0,
                     "price_vs_ma20": 1.0, "price_vs_ma50": 2.0, "bb_position": 50.0,
                     "macd_bullish": True},
            is_sell_check=False,
            context=context,
        )
        assert "open_position_count_total" in prompt
        assert "minutes_held" in prompt
        assert "Available Context" in prompt

    def test_prompt_omits_context_section_when_empty(self):
        prompt = AISpotOpinionEvaluator._build_prompt(
            product_id="ETH-USD",
            metrics={"rsi": 55.0, "volume_ratio": 1.5, "price_change_24h": 2.0,
                     "price_vs_ma20": 1.0, "price_vs_ma50": 2.0, "bb_position": 50.0,
                     "macd_bullish": True},
            is_sell_check=False,
            context={},
        )
        assert "Available Context" not in prompt

    @pytest.mark.asyncio
    async def test_every_provider_receives_context_in_prompt(self):
        """Call evaluate() for each provider and confirm _call_llm sees a prompt
        with the injected context block."""
        evaluator = AISpotOpinionEvaluator()

        for model in ("claude", "gpt", "gemini"):
            evaluator._last_check_cache.clear()
            params = AISpotOpinionParams(ai_model=model, enable_buy_prefilter=False)

            portfolio_payload = {"open_position_count_total": 7, "provider_marker": model}
            captured = {}

            async def fake_execute_tool(name, inp, ctx):
                if name == "get_portfolio_context":
                    return portfolio_payload
                return {"error": "unexpected"}

            async def fake_call_llm(*, db, user_id, ai_model, prompt, tool_ctx=None):
                captured["prompt"] = prompt
                return "hold", 0, "ok"

            with patch.object(_mod, "execute_tool", side_effect=fake_execute_tool):
                with patch.object(evaluator, "_call_llm",
                                  new_callable=AsyncMock, side_effect=fake_call_llm):
                    await evaluator.evaluate(
                        candles=_make_candles(60), current_price=100.0,
                        product_id="BTC-USD", db=MagicMock(), user_id=1,
                        params=params, is_sell_check=False, account_id=99,
                    )

            assert captured["prompt"] is not None, f"{model}: prompt not passed to _call_llm"
            assert "open_position_count_total" in captured["prompt"], \
                f"{model}: portfolio not in prompt"
            assert "provider_marker" in captured["prompt"], \
                f"{model}: provider-specific marker missing"
