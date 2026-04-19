"""Tests for the LLMProvider base module.

Covers:
- NormalizedToolCall dataclass shape
- get_provider() dispatch: claude → AnthropicProvider, gpt/openai → OpenAIProvider,
  gemini → GeminiProvider, unknown → ValueError
- All providers expose `name` and `model` attributes
- All providers implement the async call_with_tools(system, user, tools, tool_ctx, max_turns) API
"""

import inspect

import pytest

from app.indicators.ai_providers import (
    AnthropicProvider,
    GeminiProvider,
    LLMProvider,
    NormalizedToolCall,
    OpenAIProvider,
    get_provider,
)


class TestNormalizedToolCall:
    def test_fields(self):
        tc = NormalizedToolCall(
            name="get_portfolio_context",
            input={"x": 1},
            output={"ok": True},
            output_summary="{'ok': True}",
            turn=0,
        )
        assert tc.name == "get_portfolio_context"
        assert tc.input == {"x": 1}
        assert tc.output == {"ok": True}
        assert tc.output_summary.startswith("{")
        assert tc.turn == 0


class TestGetProvider:
    def test_claude_returns_anthropic_provider(self):
        p = get_provider("claude", api_key="k")
        assert isinstance(p, AnthropicProvider)
        assert p.name == "claude"

    def test_gpt_returns_openai_provider(self):
        p = get_provider("gpt", api_key="k")
        assert isinstance(p, OpenAIProvider)
        assert p.name == "gpt"

    def test_openai_alias_returns_openai_provider(self):
        p = get_provider("openai", api_key="k")
        assert isinstance(p, OpenAIProvider)

    def test_gemini_returns_gemini_provider(self):
        p = get_provider("gemini", api_key="k")
        assert isinstance(p, GeminiProvider)
        assert p.name == "gemini"

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="unknown"):
            get_provider("cohere", api_key="k")

    def test_case_insensitive(self):
        assert isinstance(get_provider("CLAUDE", api_key="k"), AnthropicProvider)


class TestProviderContract:
    """Every provider exposes the same public API surface."""

    @pytest.mark.parametrize("cls", [AnthropicProvider, OpenAIProvider, GeminiProvider])
    def test_has_name_and_model(self, cls):
        p = cls(api_key="k")
        assert isinstance(p.name, str) and p.name
        assert isinstance(p.model, str) and p.model

    @pytest.mark.parametrize("cls", [AnthropicProvider, OpenAIProvider, GeminiProvider])
    def test_call_with_tools_is_async(self, cls):
        p = cls(api_key="k")
        assert inspect.iscoroutinefunction(p.call_with_tools)

    @pytest.mark.parametrize("cls", [AnthropicProvider, OpenAIProvider, GeminiProvider])
    def test_call_with_tools_signature(self, cls):
        p = cls(api_key="k")
        sig = inspect.signature(p.call_with_tools)
        assert set(sig.parameters) >= {"system", "user", "tools", "tool_ctx", "max_turns"}

    def test_runtime_isinstance_with_protocol(self):
        """LLMProvider is a runtime-checkable Protocol."""
        p = AnthropicProvider(api_key="k")
        assert isinstance(p, LLMProvider)
