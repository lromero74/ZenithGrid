"""Anthropic (Claude) provider adapter.

The canonical schema already matches Anthropic's format, so translation is a
pass-through. The loop follows Anthropic's tool-use protocol:

1. messages.create(tools=[...], messages=[...])
2. If stop_reason == "tool_use", execute each tool_use block, append
   tool_result blocks to the message history, and continue.
3. Otherwise return the final text block.

On the last turn (`turn == max_turns`) we drop `tools=` from the call so the
model can't loop further — it must produce a text response.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Tuple

from app.indicators.ai_providers.base import NormalizedToolCall, summarize_output

if TYPE_CHECKING:
    from app.indicators.ai_tools import ToolContext

logger = logging.getLogger(__name__)


def translate_schema(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Anthropic uses the canonical schema as-is. Pass-through."""
    return list(tools or [])


class AnthropicProvider:
    name = "claude"
    model = "claude-sonnet-4-20250514"

    def __init__(self, api_key: str, model: Optional[str] = None):
        if not api_key:
            raise ValueError("Claude API key not configured for this user")
        self.api_key = api_key
        if model:
            self.model = model

    async def _execute_tool(
        self, name: str, inp: Dict[str, Any], ctx: "ToolContext"
    ) -> Dict[str, Any]:
        """Indirection so tests can patch tool execution on the provider instance."""
        from app.indicators.ai_tools import execute
        return await execute(name, inp, ctx)

    async def call_with_tools(
        self,
        *,
        system: Optional[str] = None,
        user: str,
        tools: List[Dict[str, Any]],
        tool_ctx: "ToolContext",
        max_turns: int = 4,
    ) -> Tuple[str, List[NormalizedToolCall]]:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=self.api_key)
        tool_schemas = translate_schema(tools)
        messages: List[Dict[str, Any]] = [{"role": "user", "content": user}]
        tool_calls: List[NormalizedToolCall] = []

        for turn in range(max_turns + 1):
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "max_tokens": 2048,
                "temperature": 0,
                "messages": messages,
            }
            if system:
                kwargs["system"] = system
            # On the final turn, drop tools= to force a text response.
            if tool_schemas and turn < max_turns:
                kwargs["tools"] = tool_schemas

            response = await client.messages.create(**kwargs)

            if response.stop_reason != "tool_use":
                text = ""
                for block in response.content:
                    if getattr(block, "type", None) == "text":
                        text = block.text
                        break
                return text, tool_calls

            tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
            tool_results_content: List[Dict[str, Any]] = []

            for block in tool_uses:
                tool_name = block.name
                tool_input = block.input or {}
                output = await self._execute_tool(tool_name, tool_input, tool_ctx)
                output_json = json.dumps(output, default=str)
                tool_results_content.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output_json,
                })
                tool_calls.append(NormalizedToolCall(
                    name=tool_name,
                    input=tool_input,
                    output=output,
                    output_summary=summarize_output(output),
                    turn=turn,
                ))

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results_content})

        return "", tool_calls
