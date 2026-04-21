"""LLMProvider ABC + NormalizedToolCall dataclass.

The canonical tool schema (what adapters translate *from*) is Anthropic's:

    {
        "name": "get_portfolio_context",
        "description": "...",
        "input_schema": { ... JSON Schema ... },
    }

Each provider translates this into its own call format inside `call_with_tools`.
Tools themselves are provider-agnostic — they live in `app.indicators.ai_tools`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple, TYPE_CHECKING, runtime_checkable

if TYPE_CHECKING:
    from app.indicators.ai_tools import ToolContext

logger = logging.getLogger(__name__)

SUMMARY_LIMIT = 200


@dataclass
class NormalizedToolCall:
    """One tool invocation by the model, as observed after execution.

    All provider adapters produce this uniform record so upstream code (the
    evaluator, logging, the UI surface in Phase E) never has to branch on
    provider.
    """
    name: str
    input: Dict[str, Any]
    output: Dict[str, Any]
    output_summary: str
    turn: int


@dataclass
class TokenUsage:
    """Token accounting for a provider call, summed across every tool-loop turn.

    Providers report usage per HTTP round-trip. For Phase F we need a single
    (input, output) pair across the whole call so the cost dashboard can price
    it with one MODEL_PRICING lookup. Each adapter increments these counters
    after every SDK response; missing/None usage fields are treated as 0.
    """
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, input_tokens: Optional[int], output_tokens: Optional[int]) -> None:
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)


def summarize_output(output: Dict[str, Any]) -> str:
    """Serialize + truncate a tool result for logging. Same rule across providers."""
    as_json = json.dumps(output, default=str)
    if len(as_json) > SUMMARY_LIMIT:
        return as_json[:SUMMARY_LIMIT] + "…"
    return as_json


@runtime_checkable
class LLMProvider(Protocol):
    """Canonical provider interface. Every adapter conforms to this."""

    name: str
    model: str

    async def call_with_tools(
        self,
        *,
        system: Optional[str],
        user: str,
        tools: List[Dict[str, Any]],
        tool_ctx: "ToolContext",
        max_turns: int = 4,
    ) -> Tuple[str, List[NormalizedToolCall], TokenUsage]:
        """Run the provider's native tool-use loop.

        Returns (final_text, tool_calls, usage). `usage` sums input/output
        tokens across every turn of the loop so callers can price a single
        call with one MODEL_PRICING lookup. If `tools` is empty the call is
        effectively single-shot: one request, one text response, no tool calls.
        """
        ...


def get_provider(name: str, *, api_key: str, model: Optional[str] = None):
    """Dispatch a provider name → concrete adapter instance.

    Accepts `claude`, `gpt`, `openai`, `gemini` (case-insensitive). Raises
    ValueError for anything else — callers should validate user config before
    reaching this.

    `model` is an optional per-call SDK model override (Phase F). When None
    each adapter uses its hard-coded default. Adapters silently pin to their
    default if `model` is falsy, so callers can pass None without branching.
    """
    key = (name or "").lower()
    # Imports inside the function: each adapter pulls in its own SDK at import
    # time, so we don't want to pay that cost for providers the caller never
    # asks for.
    if key == "claude":
        from app.indicators.ai_providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(api_key=api_key, model=model)
    if key in ("gpt", "openai"):
        from app.indicators.ai_providers.openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=api_key, model=model, provider_name=key)
    if key == "gemini":
        from app.indicators.ai_providers.gemini_provider import GeminiProvider
        return GeminiProvider(api_key=api_key, model=model)
    raise ValueError(f"unknown AI provider: {name!r}")
