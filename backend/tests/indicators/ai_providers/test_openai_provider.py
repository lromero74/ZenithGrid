"""Tests for OpenAIProvider.call_with_tools.

Mocks openai.AsyncOpenAI at the provider level. Covers:
- Schema translation: {name, description, input_schema} → {"type":"function","function":{...}}
- Single tool turn → tool_call, feed back as role=tool, then final text
- Multi tool in one turn
- finish_reason="stop" terminates
- MAX_TURNS cap drops tools= on last call
- Tool error surfaces as JSON content in role=tool message
- No tools → single shot
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.indicators.ai_providers import NormalizedToolCall, OpenAIProvider
from app.indicators.ai_providers.openai_provider import translate_schema
from app.indicators.ai_tools import ToolContext


def _ctx():
    return ToolContext(
        db=MagicMock(), user_id=1, product_id="ETH-USD",
        current_price=100.0, account_id=1,
    )


def _tool_call(id_, name, args_dict):
    return SimpleNamespace(
        id=id_, type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(args_dict)),
    )


def _choice(finish_reason, content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls or None)
    return SimpleNamespace(finish_reason=finish_reason, message=message)


def _completion(choices):
    return SimpleNamespace(choices=choices)


PORTFOLIO_SCHEMA = [{
    "name": "get_portfolio_context",
    "description": "Returns other open positions.",
    "input_schema": {"type": "object", "properties": {}},
}]


class TestTranslateSchema:
    def test_wraps_in_function_object(self):
        out = translate_schema(PORTFOLIO_SCHEMA)
        assert len(out) == 1
        assert out[0]["type"] == "function"
        assert out[0]["function"]["name"] == "get_portfolio_context"
        assert out[0]["function"]["description"] == "Returns other open positions."
        assert out[0]["function"]["parameters"] == {"type": "object", "properties": {}}

    def test_empty_returns_empty(self):
        assert translate_schema([]) == []


class TestOpenAIProvider:
    @pytest.mark.asyncio
    async def test_single_tool_turn(self):
        final_json = json.dumps({"signal": "buy", "confidence": 80, "reasoning": "ok"})
        scripted = [
            _completion([_choice("tool_calls",
                                 tool_calls=[_tool_call("call_1", "get_portfolio_context", {})])]),
            _completion([_choice("stop", content=final_json)]),
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=scripted)

        provider = OpenAIProvider(api_key="sk-test")
        with patch.object(provider, "_execute_tool",
                          new_callable=AsyncMock, return_value={"other_open_positions": []}):
            with patch("openai.AsyncOpenAI", return_value=mock_client):
                text, calls = await provider.call_with_tools(
                    system=None, user="prompt", tools=PORTFOLIO_SCHEMA,
                    tool_ctx=_ctx(), max_turns=4,
                )

        assert text == final_json
        assert len(calls) == 1
        assert isinstance(calls[0], NormalizedToolCall)
        assert calls[0].name == "get_portfolio_context"
        assert calls[0].turn == 0
        assert mock_client.chat.completions.create.await_count == 2

    @pytest.mark.asyncio
    async def test_multi_tool_single_turn(self):
        final_json = json.dumps({"signal": "hold", "confidence": 50, "reasoning": "m"})
        scripted = [
            _completion([_choice("tool_calls", tool_calls=[
                _tool_call("c1", "get_position_context", {}),
                _tool_call("c2", "get_portfolio_context", {}),
            ])]),
            _completion([_choice("stop", content=final_json)]),
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=scripted)

        tools = PORTFOLIO_SCHEMA + [{
            "name": "get_position_context",
            "description": "Position details.",
            "input_schema": {"type": "object", "properties": {}},
        }]
        provider = OpenAIProvider(api_key="sk-test")
        with patch.object(provider, "_execute_tool",
                          new_callable=AsyncMock, return_value={"ok": True}):
            with patch("openai.AsyncOpenAI", return_value=mock_client):
                text, calls = await provider.call_with_tools(
                    system=None, user="p", tools=tools, tool_ctx=_ctx(), max_turns=4,
                )

        assert text == final_json
        assert {c.name for c in calls} == {"get_position_context", "get_portfolio_context"}

    @pytest.mark.asyncio
    async def test_cap_reached_drops_tools(self):
        scripted = [
            _completion([_choice("tool_calls",
                                 tool_calls=[_tool_call(f"c{i}", "get_portfolio_context", {})])])
            for i in range(4)
        ]
        final_json = json.dumps({"signal": "hold", "confidence": 0, "reasoning": "capped"})
        scripted.append(_completion([_choice("stop", content=final_json)]))
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=scripted)

        provider = OpenAIProvider(api_key="sk-test")
        with patch.object(provider, "_execute_tool",
                          new_callable=AsyncMock, return_value={"ok": True}):
            with patch("openai.AsyncOpenAI", return_value=mock_client):
                text, _ = await provider.call_with_tools(
                    system=None, user="p", tools=PORTFOLIO_SCHEMA,
                    tool_ctx=_ctx(), max_turns=4,
                )

        assert text == final_json
        last_call = mock_client.chat.completions.create.await_args_list[-1]
        assert "tools" not in last_call.kwargs or not last_call.kwargs.get("tools")

    @pytest.mark.asyncio
    async def test_tool_error_in_result(self):
        final_json = json.dumps({"signal": "hold", "confidence": 0, "reasoning": "no"})
        scripted = [
            _completion([_choice("tool_calls",
                                 tool_calls=[_tool_call("c1", "get_portfolio_context", {})])]),
            _completion([_choice("stop", content=final_json)]),
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=scripted)

        provider = OpenAIProvider(api_key="sk-test")
        with patch.object(provider, "_execute_tool",
                          new_callable=AsyncMock, return_value={"error": "boom"}):
            with patch("openai.AsyncOpenAI", return_value=mock_client):
                text, calls = await provider.call_with_tools(
                    system=None, user="p", tools=PORTFOLIO_SCHEMA,
                    tool_ctx=_ctx(), max_turns=4,
                )

        assert text == final_json
        assert calls[0].output == {"error": "boom"}

    @pytest.mark.asyncio
    async def test_no_tools_is_single_shot(self):
        final_json = json.dumps({"signal": "buy", "confidence": 90, "reasoning": "go"})
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_completion([_choice("stop", content=final_json)])
        )
        provider = OpenAIProvider(api_key="sk-test")
        with patch("openai.AsyncOpenAI", return_value=mock_client):
            text, calls = await provider.call_with_tools(
                system=None, user="p", tools=[], tool_ctx=_ctx(), max_turns=4,
            )
        assert text == final_json
        assert calls == []
        assert mock_client.chat.completions.create.await_count == 1

    @pytest.mark.asyncio
    async def test_system_prompt_becomes_system_message(self):
        final_json = json.dumps({"signal": "hold", "confidence": 0, "reasoning": ""})
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_completion([_choice("stop", content=final_json)])
        )
        provider = OpenAIProvider(api_key="sk-test")
        with patch("openai.AsyncOpenAI", return_value=mock_client):
            await provider.call_with_tools(
                system="You are an expert trader.", user="go",
                tools=[], tool_ctx=_ctx(), max_turns=4,
            )
        call = mock_client.chat.completions.create.await_args_list[0]
        msgs = call.kwargs["messages"]
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "You are an expert trader."
        assert msgs[1]["role"] == "user"
        assert msgs[1]["content"] == "go"

    @pytest.mark.asyncio
    async def test_tool_args_parsed_from_json_string(self):
        """OpenAI sends tool args as a JSON string in .function.arguments."""
        final_json = json.dumps({"signal": "buy", "confidence": 70, "reasoning": ""})
        scripted = [
            _completion([_choice("tool_calls", tool_calls=[
                _tool_call("c1", "get_candle_window",
                           {"timeframe": "1h", "count": 20})
            ])]),
            _completion([_choice("stop", content=final_json)]),
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=scripted)

        provider = OpenAIProvider(api_key="sk-test")
        with patch.object(provider, "_execute_tool",
                          new_callable=AsyncMock, return_value={"candles": []}) as exec_mock:
            with patch("openai.AsyncOpenAI", return_value=mock_client):
                await provider.call_with_tools(
                    system=None, user="p", tools=PORTFOLIO_SCHEMA,
                    tool_ctx=_ctx(), max_turns=4,
                )
        exec_mock.assert_awaited_once()
        args = exec_mock.await_args_list[0].args
        assert args[0] == "get_candle_window"
        assert args[1] == {"timeframe": "1h", "count": 20}
