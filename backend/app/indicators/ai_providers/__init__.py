"""AI provider adapters.

One concrete adapter per LLM vendor. Every adapter conforms to LLMProvider:
    async call_with_tools(system, user, tools, tool_ctx, max_turns) -> (text, calls, usage)

Canonical tool schema is Anthropic's shape. Adapters translate on the way in.
"""

from app.indicators.ai_providers.base import (
    LLMProvider,
    NormalizedToolCall,
    TokenUsage,
    get_provider,
    summarize_output,
)
from app.indicators.ai_providers.anthropic_provider import AnthropicProvider
from app.indicators.ai_providers.openai_provider import OpenAIProvider
from app.indicators.ai_providers.gemini_provider import GeminiProvider

__all__ = [
    "AnthropicProvider",
    "GeminiProvider",
    "LLMProvider",
    "NormalizedToolCall",
    "OpenAIProvider",
    "TokenUsage",
    "get_provider",
    "summarize_output",
]
