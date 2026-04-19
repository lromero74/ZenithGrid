"""Tests for GeminiProvider.call_with_tools.

Mocks google.generativeai at the provider level. Covers:
- Schema translation: {name, description, input_schema} → FunctionDeclaration dict
- Single function_call turn → function_response, then final text
- Multi function_call in one turn
- Text-only response terminates
- MAX_TURNS cap forces a final text call
- Tool error surfaces in function_response
- No tools → single shot (plain .text)
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.indicators.ai_providers import GeminiProvider, NormalizedToolCall
from app.indicators.ai_providers.gemini_provider import translate_schema
from app.indicators.ai_tools import ToolContext


def _ctx():
    return ToolContext(
        db=MagicMock(), user_id=1, product_id="ETH-USD",
        current_price=100.0, account_id=1,
    )


def _fc_part(name, args):
    fc = SimpleNamespace(name=name, args=args)
    return SimpleNamespace(function_call=fc, text=None)


def _text_part(text):
    return SimpleNamespace(function_call=None, text=text)


def _response(parts, text=None):
    content = SimpleNamespace(parts=parts)
    candidate = SimpleNamespace(content=content)
    resp = SimpleNamespace(candidates=[candidate], text=text or "")
    return resp


PORTFOLIO_SCHEMA = [{
    "name": "get_portfolio_context",
    "description": "Returns other open positions.",
    "input_schema": {"type": "object", "properties": {}},
}]


class TestTranslateSchema:
    def test_produces_function_declaration_list(self):
        out = translate_schema(PORTFOLIO_SCHEMA)
        assert len(out) == 1
        decl = out[0]
        assert decl["name"] == "get_portfolio_context"
        assert decl["description"] == "Returns other open positions."
        assert decl["parameters"] == {"type": "object", "properties": {}}

    def test_empty_returns_empty(self):
        assert translate_schema([]) == []


class TestGeminiProvider:
    @pytest.mark.asyncio
    async def test_single_tool_turn(self):
        final_json = json.dumps({"signal": "buy", "confidence": 80, "reasoning": "ok"})
        scripted = [
            _response([_fc_part("get_portfolio_context", {})]),
            _response([_text_part(final_json)], text=final_json),
        ]
        mock_chat = MagicMock()
        mock_chat.send_message_async = AsyncMock(side_effect=scripted)
        mock_model = MagicMock()
        mock_model.start_chat = MagicMock(return_value=mock_chat)

        provider = GeminiProvider(api_key="sk-test")
        with patch.object(provider, "_execute_tool",
                          new_callable=AsyncMock, return_value={"other_open_positions": []}):
            with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                with patch("google.generativeai.configure"):
                    text, calls = await provider.call_with_tools(
                        system=None, user="prompt", tools=PORTFOLIO_SCHEMA,
                        tool_ctx=_ctx(), max_turns=4,
                    )

        assert text == final_json
        assert len(calls) == 1
        assert isinstance(calls[0], NormalizedToolCall)
        assert calls[0].name == "get_portfolio_context"
        assert mock_chat.send_message_async.await_count == 2

    @pytest.mark.asyncio
    async def test_multi_tool_single_turn(self):
        final_json = json.dumps({"signal": "hold", "confidence": 50, "reasoning": "m"})
        scripted = [
            _response([
                _fc_part("get_position_context", {}),
                _fc_part("get_portfolio_context", {}),
            ]),
            _response([_text_part(final_json)], text=final_json),
        ]
        mock_chat = MagicMock()
        mock_chat.send_message_async = AsyncMock(side_effect=scripted)
        mock_model = MagicMock()
        mock_model.start_chat = MagicMock(return_value=mock_chat)

        tools = PORTFOLIO_SCHEMA + [{
            "name": "get_position_context",
            "description": "Position details.",
            "input_schema": {"type": "object", "properties": {}},
        }]
        provider = GeminiProvider(api_key="sk-test")
        with patch.object(provider, "_execute_tool",
                          new_callable=AsyncMock, return_value={"ok": True}):
            with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                with patch("google.generativeai.configure"):
                    text, calls = await provider.call_with_tools(
                        system=None, user="p", tools=tools, tool_ctx=_ctx(), max_turns=4,
                    )

        assert text == final_json
        assert {c.name for c in calls} == {"get_position_context", "get_portfolio_context"}

    @pytest.mark.asyncio
    async def test_cap_reached_forces_text(self):
        """After max_turns tool-call responses, provider must force a final text turn."""
        scripted = [
            _response([_fc_part("get_portfolio_context", {})])
            for _ in range(4)
        ]
        final_json = json.dumps({"signal": "hold", "confidence": 0, "reasoning": "capped"})
        scripted.append(_response([_text_part(final_json)], text=final_json))

        mock_chat = MagicMock()
        mock_chat.send_message_async = AsyncMock(side_effect=scripted)
        mock_model = MagicMock()
        mock_model.start_chat = MagicMock(return_value=mock_chat)

        provider = GeminiProvider(api_key="sk-test")
        with patch.object(provider, "_execute_tool",
                          new_callable=AsyncMock, return_value={"ok": True}):
            with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                with patch("google.generativeai.configure"):
                    text, _ = await provider.call_with_tools(
                        system=None, user="p", tools=PORTFOLIO_SCHEMA,
                        tool_ctx=_ctx(), max_turns=4,
                    )
        assert text == final_json

    @pytest.mark.asyncio
    async def test_tool_error_in_result(self):
        final_json = json.dumps({"signal": "hold", "confidence": 0, "reasoning": ""})
        scripted = [
            _response([_fc_part("get_portfolio_context", {})]),
            _response([_text_part(final_json)], text=final_json),
        ]
        mock_chat = MagicMock()
        mock_chat.send_message_async = AsyncMock(side_effect=scripted)
        mock_model = MagicMock()
        mock_model.start_chat = MagicMock(return_value=mock_chat)

        provider = GeminiProvider(api_key="sk-test")
        with patch.object(provider, "_execute_tool",
                          new_callable=AsyncMock, return_value={"error": "boom"}):
            with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                with patch("google.generativeai.configure"):
                    text, calls = await provider.call_with_tools(
                        system=None, user="p", tools=PORTFOLIO_SCHEMA,
                        tool_ctx=_ctx(), max_turns=4,
                    )
        assert text == final_json
        assert calls[0].output == {"error": "boom"}

    @pytest.mark.asyncio
    async def test_no_tools_is_single_shot(self):
        final_json = json.dumps({"signal": "buy", "confidence": 90, "reasoning": ""})
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(
            return_value=_response([_text_part(final_json)], text=final_json)
        )
        provider = GeminiProvider(api_key="sk-test")
        with patch("google.generativeai.GenerativeModel", return_value=mock_model):
            with patch("google.generativeai.configure"):
                text, calls = await provider.call_with_tools(
                    system=None, user="p", tools=[], tool_ctx=_ctx(), max_turns=4,
                )
        assert text == final_json
        assert calls == []

    @pytest.mark.asyncio
    async def test_system_prompt_becomes_system_instruction(self):
        final_json = json.dumps({"signal": "hold", "confidence": 0, "reasoning": ""})
        captured_kwargs = {}

        def _make_model(*args, **kwargs):
            captured_kwargs.update(kwargs)
            m = MagicMock()
            m.generate_content_async = AsyncMock(
                return_value=_response([_text_part(final_json)], text=final_json)
            )
            return m

        provider = GeminiProvider(api_key="sk-test")
        with patch("google.generativeai.GenerativeModel", side_effect=_make_model):
            with patch("google.generativeai.configure"):
                await provider.call_with_tools(
                    system="You are an expert trader.", user="go",
                    tools=[], tool_ctx=_ctx(), max_turns=4,
                )
        assert captured_kwargs.get("system_instruction") == "You are an expert trader."
