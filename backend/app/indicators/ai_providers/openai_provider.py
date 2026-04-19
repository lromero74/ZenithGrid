"""OpenAI (GPT) provider adapter.

Translates canonical Anthropic-style tool schemas into OpenAI's function-calling
format:

    canonical:  {name, description, input_schema}
    openai:     {"type": "function", "function": {name, description, parameters}}

Loop protocol:
1. chat.completions.create(tools=[...], messages=[...])
2. If message.tool_calls is non-empty, execute each tool and feed results back
   as role="tool" messages referencing the same tool_call_id.
3. Terminate when finish_reason == "stop" (OpenAI's signal that the model is
   done) or when max_turns is reached (drop tools= to force a text response).

Argument parsing: OpenAI serializes tool arguments as a JSON string inside
`message.tool_calls[i].function.arguments`. We deserialize here so tools receive
a real dict.
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
    """Wrap each canonical tool into OpenAI's function-calling format."""
    out: List[Dict[str, Any]] = []
    for t in tools or []:
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return out


class OpenAIProvider:
    name = "gpt"
    model = "gpt-4o"

    def __init__(self, api_key: str, model: Optional[str] = None,
                 provider_name: Optional[str] = None):
        if not api_key:
            raise ValueError("OpenAI API key not configured for this user")
        self.api_key = api_key
        if model:
            self.model = model
        if provider_name:
            self.name = provider_name

    async def _execute_tool(
        self, name: str, inp: Dict[str, Any], ctx: "ToolContext"
    ) -> Dict[str, Any]:
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
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        tool_schemas = translate_schema(tools)

        messages: List[Dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        tool_calls: List[NormalizedToolCall] = []

        for turn in range(max_turns + 1):
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "max_tokens": 2048,
                "temperature": 0,
                "messages": messages,
            }
            if tool_schemas and turn < max_turns:
                kwargs["tools"] = tool_schemas

            response = await client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            msg = choice.message

            if choice.finish_reason == "stop" or not msg.tool_calls:
                return msg.content or "", tool_calls

            # Record the assistant's tool-call request in history before feeding
            # results back (required by OpenAI's API contract).
            messages.append({
                "role": "assistant",
                "content": msg.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_input = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    tool_input = {}
                    logger.warning(f"OpenAI returned non-JSON args for {tool_name}: "
                                   f"{tc.function.arguments!r}")

                output = await self._execute_tool(tool_name, tool_input, tool_ctx)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(output, default=str),
                })
                tool_calls.append(NormalizedToolCall(
                    name=tool_name,
                    input=tool_input,
                    output=output,
                    output_summary=summarize_output(output),
                    turn=turn,
                ))

        return "", tool_calls
