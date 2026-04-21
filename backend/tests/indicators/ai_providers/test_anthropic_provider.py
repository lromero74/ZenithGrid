"""Tests for AnthropicProvider.call_with_tools.

Mocks anthropic.AsyncAnthropic at the provider level. Covers:
- Single tool turn → final text
- Multiple tools in one turn (parallel)
- MAX_TURNS cap drops tools= on last call
- Tool error surfaces as tool_result, loop continues
- No tools passed → single-shot behavior (one call, final text)
- NormalizedToolCall turn index increments across turns
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.indicators.ai_providers import AnthropicProvider, NormalizedToolCall, TokenUsage
from app.indicators.ai_tools import ToolContext


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(id_, name, input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def _response(stop_reason, content, input_tokens=0, output_tokens=0):
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(stop_reason=stop_reason, content=content, usage=usage)


def _ctx():
    return ToolContext(
        db=MagicMock(), user_id=1, product_id="ETH-USD",
        current_price=100.0, account_id=1,
    )


PORTFOLIO_SCHEMA = [{
    "name": "get_portfolio_context",
    "description": "Returns other open positions.",
    "input_schema": {"type": "object", "properties": {}},
}]


class TestAnthropicProvider:
    @pytest.mark.asyncio
    async def test_single_tool_turn(self):
        final_json = json.dumps({"signal": "buy", "confidence": 80, "reasoning": "ok"})
        scripted = [
            _response("tool_use", [_tool_use_block("u1", "get_portfolio_context", {})]),
            _response("end_turn", [_text_block(final_json)]),
        ]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=scripted)

        provider = AnthropicProvider(api_key="sk-test")
        with patch.object(provider, "_execute_tool",
                          new_callable=AsyncMock, return_value={"other_open_positions": []}):
            with patch("anthropic.AsyncAnthropic", return_value=mock_client):
                text, calls, _ = await provider.call_with_tools(
                    system=None, user="prompt", tools=PORTFOLIO_SCHEMA,
                    tool_ctx=_ctx(), max_turns=4,
                )

        assert text == final_json
        assert len(calls) == 1
        assert isinstance(calls[0], NormalizedToolCall)
        assert calls[0].name == "get_portfolio_context"
        assert calls[0].turn == 0
        assert mock_client.messages.create.await_count == 2

    @pytest.mark.asyncio
    async def test_multi_tool_single_turn(self):
        final_json = json.dumps({"signal": "hold", "confidence": 50, "reasoning": "m"})
        scripted = [
            _response("tool_use", [
                _tool_use_block("u1", "get_position_context", {}),
                _tool_use_block("u2", "get_portfolio_context", {}),
            ]),
            _response("end_turn", [_text_block(final_json)]),
        ]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=scripted)

        provider = AnthropicProvider(api_key="sk-test")
        tools = PORTFOLIO_SCHEMA + [{
            "name": "get_position_context",
            "description": "Position details.",
            "input_schema": {"type": "object", "properties": {}},
        }]
        with patch.object(provider, "_execute_tool",
                          new_callable=AsyncMock, return_value={"ok": True}):
            with patch("anthropic.AsyncAnthropic", return_value=mock_client):
                text, calls, _ = await provider.call_with_tools(
                    system=None, user="p", tools=tools, tool_ctx=_ctx(), max_turns=4,
                )

        assert text == final_json
        assert {c.name for c in calls} == {"get_position_context", "get_portfolio_context"}
        assert all(c.turn == 0 for c in calls)

    @pytest.mark.asyncio
    async def test_cap_reached_drops_tools(self):
        scripted = [
            _response("tool_use", [_tool_use_block(f"u{i}", "get_portfolio_context", {})])
            for i in range(4)
        ]
        final_json = json.dumps({"signal": "hold", "confidence": 0, "reasoning": "capped"})
        scripted.append(_response("end_turn", [_text_block(final_json)]))
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=scripted)

        provider = AnthropicProvider(api_key="sk-test")
        with patch.object(provider, "_execute_tool",
                          new_callable=AsyncMock, return_value={"ok": True}):
            with patch("anthropic.AsyncAnthropic", return_value=mock_client):
                text, _, _ = await provider.call_with_tools(
                    system=None, user="p", tools=PORTFOLIO_SCHEMA,
                    tool_ctx=_ctx(), max_turns=4,
                )

        assert text == final_json
        last_call = mock_client.messages.create.await_args_list[-1]
        assert "tools" not in last_call.kwargs

    @pytest.mark.asyncio
    async def test_tool_error_in_result(self):
        final_json = json.dumps({"signal": "hold", "confidence": 0, "reasoning": "no"})
        scripted = [
            _response("tool_use", [_tool_use_block("u1", "get_portfolio_context", {})]),
            _response("end_turn", [_text_block(final_json)]),
        ]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=scripted)

        provider = AnthropicProvider(api_key="sk-test")
        with patch.object(provider, "_execute_tool",
                          new_callable=AsyncMock, return_value={"error": "boom"}):
            with patch("anthropic.AsyncAnthropic", return_value=mock_client):
                text, calls, _ = await provider.call_with_tools(
                    system=None, user="p", tools=PORTFOLIO_SCHEMA,
                    tool_ctx=_ctx(), max_turns=4,
                )

        assert text == final_json
        assert calls[0].output == {"error": "boom"}
        assert calls[0].output_summary.startswith('{"error"')

    @pytest.mark.asyncio
    async def test_no_tools_is_single_shot(self):
        final_json = json.dumps({"signal": "buy", "confidence": 90, "reasoning": "go"})
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            return_value=_response("end_turn", [_text_block(final_json)])
        )

        provider = AnthropicProvider(api_key="sk-test")
        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            text, calls, _ = await provider.call_with_tools(
                system=None, user="p", tools=[], tool_ctx=_ctx(), max_turns=4,
            )

        assert text == final_json
        assert calls == []
        assert mock_client.messages.create.await_count == 1
        call = mock_client.messages.create.await_args_list[0]
        assert "tools" not in call.kwargs or call.kwargs.get("tools") == []

    @pytest.mark.asyncio
    async def test_turn_index_increments(self):
        final_json = json.dumps({"signal": "hold", "confidence": 0, "reasoning": ""})
        scripted = [
            _response("tool_use", [_tool_use_block("u1", "get_portfolio_context", {})]),
            _response("tool_use", [_tool_use_block("u2", "get_portfolio_context", {})]),
            _response("end_turn", [_text_block(final_json)]),
        ]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=scripted)

        provider = AnthropicProvider(api_key="sk-test")
        with patch.object(provider, "_execute_tool",
                          new_callable=AsyncMock, return_value={"ok": True}):
            with patch("anthropic.AsyncAnthropic", return_value=mock_client):
                _, calls, _ = await provider.call_with_tools(
                    system=None, user="p", tools=PORTFOLIO_SCHEMA,
                    tool_ctx=_ctx(), max_turns=4,
                )

        assert [c.turn for c in calls] == [0, 1]

    @pytest.mark.asyncio
    async def test_system_prompt_passed_through(self):
        final_json = json.dumps({"signal": "hold", "confidence": 0, "reasoning": ""})
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            return_value=_response("end_turn", [_text_block(final_json)])
        )
        provider = AnthropicProvider(api_key="sk-test")
        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            await provider.call_with_tools(
                system="You are an expert trader.", user="go",
                tools=[], tool_ctx=_ctx(), max_turns=4,
            )
        call = mock_client.messages.create.await_args_list[0]
        assert call.kwargs.get("system") == "You are an expert trader."


class TestAnthropicUsage:
    """Phase F: usage tokens are summed across every turn and returned."""

    @pytest.mark.asyncio
    async def test_usage_summed_across_tool_turns(self):
        """A tool-loop call sums input/output tokens from every round-trip."""
        final_json = json.dumps({"signal": "hold", "confidence": 0, "reasoning": ""})
        scripted = [
            _response("tool_use",
                      [_tool_use_block("u1", "get_portfolio_context", {})],
                      input_tokens=100, output_tokens=50),
            _response("end_turn", [_text_block(final_json)],
                      input_tokens=150, output_tokens=75),
        ]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=scripted)

        provider = AnthropicProvider(api_key="sk-test")
        with patch.object(provider, "_execute_tool",
                          new_callable=AsyncMock, return_value={"ok": True}):
            with patch("anthropic.AsyncAnthropic", return_value=mock_client):
                _, _, usage = await provider.call_with_tools(
                    system=None, user="p", tools=PORTFOLIO_SCHEMA,
                    tool_ctx=_ctx(), max_turns=4,
                )
        assert isinstance(usage, TokenUsage)
        assert usage.input_tokens == 250
        assert usage.output_tokens == 125

    @pytest.mark.asyncio
    async def test_usage_on_single_shot_call(self):
        final_json = json.dumps({"signal": "buy", "confidence": 80, "reasoning": ""})
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            return_value=_response("end_turn", [_text_block(final_json)],
                                   input_tokens=42, output_tokens=17)
        )
        provider = AnthropicProvider(api_key="sk-test")
        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            _, _, usage = await provider.call_with_tools(
                system=None, user="p", tools=[], tool_ctx=_ctx(), max_turns=4,
            )
        assert usage.input_tokens == 42
        assert usage.output_tokens == 17

    @pytest.mark.asyncio
    async def test_usage_defaults_to_zero_when_missing(self):
        """A response without a .usage attribute doesn't crash — it just counts 0."""
        final_json = json.dumps({"signal": "hold", "confidence": 0, "reasoning": ""})
        mock_client = MagicMock()
        # No usage attribute at all.
        mock_client.messages.create = AsyncMock(
            return_value=SimpleNamespace(
                stop_reason="end_turn", content=[_text_block(final_json)],
            )
        )
        provider = AnthropicProvider(api_key="sk-test")
        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            _, _, usage = await provider.call_with_tools(
                system=None, user="p", tools=[], tool_ctx=_ctx(), max_turns=4,
            )
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
