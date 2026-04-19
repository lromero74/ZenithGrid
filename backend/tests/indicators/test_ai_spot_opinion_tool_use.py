"""Tests for the Claude tool-use loop in AISpotOpinionEvaluator.

Covers:
- Single tool turn — model requests one tool, then responds with JSON
- Multi tool in single turn — model requests two tools in parallel
- Cap reached — tool loop drops tools= on final turn to force text response
- Tool raises — error surfaces as tool_result, model continues
- Non-Claude model — evaluate() falls back to single-shot _call_llm
- account_id absent — evaluate() falls back to single-shot _call_llm

Uses importlib.util.spec_from_file_location to dodge the app.indicators.__init__
circular-import chain, matching the pattern in test_ai_spot_opinion.py.
"""

import importlib.util
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Load the evaluator module directly.
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

_API_KEY_PATCH = "app.services.ai_credential_service.get_user_api_key"


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


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(id_, name, input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def _response(stop_reason, content):
    return SimpleNamespace(stop_reason=stop_reason, content=content)


class TestToolUseLoop:
    """Exercise _call_claude_with_tools directly with a mocked AsyncAnthropic."""

    @pytest.mark.asyncio
    async def test_single_tool_turn_parses_final_response(self):
        evaluator = AISpotOpinionEvaluator()

        final_json = json.dumps({"signal": "buy", "confidence": 80, "reasoning": "ok"})
        scripted = [
            _response("tool_use", [_tool_use_block("u1", "get_portfolio_context", {})]),
            _response("end_turn", [_text_block(final_json)]),
        ]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=scripted)

        ctx = ToolContext(
            db=MagicMock(), user_id=1, product_id="ETH-USD",
            current_price=100.0, account_id=1,
        )

        with patch.object(_mod, "execute_tool",
                          new_callable=AsyncMock, return_value={"other_open_positions": []}):
            with patch("anthropic.AsyncAnthropic", return_value=mock_client):
                text, tool_calls = await evaluator._call_claude_with_tools(
                    prompt="prompt", api_key="sk-test", tool_ctx=ctx,
                    enabled_tools=["get_portfolio_context"],
                )

        assert text == final_json
        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "get_portfolio_context"
        assert mock_client.messages.create.await_count == 2

    @pytest.mark.asyncio
    async def test_multi_tool_single_turn(self):
        evaluator = AISpotOpinionEvaluator()
        final_json = json.dumps({"signal": "hold", "confidence": 50, "reasoning": "mixed"})
        scripted = [
            _response("tool_use", [
                _tool_use_block("u1", "get_position_context", {}),
                _tool_use_block("u2", "get_portfolio_context", {}),
            ]),
            _response("end_turn", [_text_block(final_json)]),
        ]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=scripted)

        ctx = ToolContext(
            db=MagicMock(), user_id=1, product_id="ETH-USD",
            current_price=100.0, account_id=1,
        )

        with patch.object(_mod, "execute_tool",
                          new_callable=AsyncMock, return_value={"ok": True}):
            with patch("anthropic.AsyncAnthropic", return_value=mock_client):
                text, tool_calls = await evaluator._call_claude_with_tools(
                    prompt="p", api_key="sk-test", tool_ctx=ctx,
                    enabled_tools=["get_position_context", "get_portfolio_context"],
                )

        assert text == final_json
        assert {tc["name"] for tc in tool_calls} == {
            "get_position_context", "get_portfolio_context",
        }

    @pytest.mark.asyncio
    async def test_tool_loop_cap_forces_final_response(self):
        """After MAX_TOOL_TURNS, tools are dropped so the model must respond."""
        evaluator = AISpotOpinionEvaluator()
        # Model keeps asking for tools on every turn; last call must NOT include tools=.
        scripted = [
            _response("tool_use", [_tool_use_block(f"u{i}", "get_portfolio_context", {})])
            for i in range(_mod.MAX_TOOL_TURNS)
        ]
        final_json = json.dumps({"signal": "hold", "confidence": 0, "reasoning": "capped"})
        scripted.append(_response("end_turn", [_text_block(final_json)]))

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=scripted)

        ctx = ToolContext(
            db=MagicMock(), user_id=1, product_id="ETH-USD",
            current_price=100.0, account_id=1,
        )

        with patch.object(_mod, "execute_tool",
                          new_callable=AsyncMock, return_value={"ok": True}):
            with patch("anthropic.AsyncAnthropic", return_value=mock_client):
                text, _ = await evaluator._call_claude_with_tools(
                    prompt="p", api_key="sk-test", tool_ctx=ctx,
                    enabled_tools=["get_portfolio_context"],
                )

        assert text == final_json
        # Last call's kwargs should NOT contain tools=
        last_call = mock_client.messages.create.await_args_list[-1]
        assert "tools" not in last_call.kwargs

    @pytest.mark.asyncio
    async def test_tool_error_returned_to_model_as_tool_result(self):
        """Tool failures become {"error": ...} in the tool_result. Loop continues."""
        evaluator = AISpotOpinionEvaluator()
        final_json = json.dumps({"signal": "hold", "confidence": 0, "reasoning": "no-op"})
        scripted = [
            _response("tool_use", [_tool_use_block("u1", "get_portfolio_context", {})]),
            _response("end_turn", [_text_block(final_json)]),
        ]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=scripted)

        ctx = ToolContext(
            db=MagicMock(), user_id=1, product_id="ETH-USD",
            current_price=100.0, account_id=1,
        )

        # Our execute_tool catches exceptions inside tools — patch it to simulate
        # an error return directly.
        with patch.object(_mod, "execute_tool",
                          new_callable=AsyncMock, return_value={"error": "boom"}):
            with patch("anthropic.AsyncAnthropic", return_value=mock_client):
                text, tool_calls = await evaluator._call_claude_with_tools(
                    prompt="p", api_key="sk-test", tool_ctx=ctx,
                    enabled_tools=["get_portfolio_context"],
                )

        assert text == final_json
        assert tool_calls[0]["output_summary"].startswith('{"error":')


class TestEvaluateRouting:
    """evaluate() should always go single-shot in Phase A (no argument-taking tools yet)."""

    @pytest.mark.asyncio
    async def test_gpt_model_goes_single_shot(self):
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams(ai_model="gpt", enable_buy_prefilter=False)

        with patch.object(evaluator, "_call_llm",
                          new_callable=AsyncMock, return_value=("buy", 70, "r")) as single_shot:
            with patch.object(evaluator, "_call_claude_tools_path",
                              new_callable=AsyncMock) as tools_path:
                result = await evaluator.evaluate(
                    candles=_make_candles(60), current_price=100.0,
                    product_id="BTC-USD", db=MagicMock(), user_id=1,
                    params=params, is_sell_check=False, account_id=1,
                )

        single_shot.assert_awaited_once()
        tools_path.assert_not_awaited()
        assert result["tool_calls"] == []
        assert result["signal"] == "buy"

    @pytest.mark.asyncio
    async def test_claude_without_account_id_goes_single_shot(self):
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams(ai_model="claude", enable_buy_prefilter=False)

        with patch.object(evaluator, "_call_llm",
                          new_callable=AsyncMock, return_value=("hold", 50, "r")) as single_shot:
            with patch.object(evaluator, "_call_claude_tools_path",
                              new_callable=AsyncMock) as tools_path:
                await evaluator.evaluate(
                    candles=_make_candles(60), current_price=100.0,
                    product_id="BTC-USD", db=MagicMock(), user_id=1,
                    params=params, is_sell_check=False, account_id=None,
                )

        single_shot.assert_awaited_once()
        tools_path.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_claude_with_account_id_goes_single_shot_with_context(self):
        """Phase A: no argument-taking tools exist, so even Claude+account_id runs single-shot.
        Context is pre-injected into the prompt via _collect_auto_context."""
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams(ai_model="claude", enable_buy_prefilter=False)

        with patch.object(evaluator, "_call_llm",
                          new_callable=AsyncMock, return_value=("buy", 82, "great setup")) as single_shot:
            with patch.object(evaluator, "_call_claude_tools_path",
                              new_callable=AsyncMock) as tools_path:
                result = await evaluator.evaluate(
                    candles=_make_candles(60), current_price=100.0,
                    product_id="BTC-USD", db=MagicMock(), user_id=1,
                    params=params, is_sell_check=False, account_id=42,
                )

        single_shot.assert_awaited_once()
        tools_path.assert_not_awaited()
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
        # Portfolio tool got called; position tool did not (no position, not a sell check).
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

            async def fake_call_llm(*, db, user_id, product_id, metrics, ai_model, is_sell_check,
                                    tool_ctx=None, prompt=None):
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
