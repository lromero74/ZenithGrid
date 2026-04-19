"""Google Gemini provider adapter.

Translates canonical Anthropic-style tool schemas into Gemini's FunctionDeclaration
dicts. The SDK accepts `tools=[{"function_declarations": [...]}]` on the model
constructor.

Loop protocol:
1. start_chat(...) to get a stateful chat object that preserves history.
2. send_message_async(prompt-or-function-response) returns a response whose
   `candidates[0].content.parts` is a list of parts; each part is either
   `.function_call` (with `.name` and `.args` dict) or `.text`.
3. If any part is a function_call, execute the tool and reply with a
   `function_response` part. Otherwise return the first text.

System prompt is passed as `system_instruction=` to GenerativeModel.
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
    """Convert canonical schema to Gemini's FunctionDeclaration dict list."""
    out: List[Dict[str, Any]] = []
    for t in tools or []:
        out.append({
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
        })
    return out


def _extract_function_calls(response) -> List[Any]:
    """Return the non-empty function_call parts from a Gemini response."""
    try:
        parts = response.candidates[0].content.parts
    except (AttributeError, IndexError):
        return []
    return [p for p in parts if getattr(p, "function_call", None) is not None]


def _extract_text(response) -> str:
    """First text part, or response.text as a fallback."""
    try:
        parts = response.candidates[0].content.parts
    except (AttributeError, IndexError):
        parts = []
    for p in parts:
        t = getattr(p, "text", None)
        if t:
            return t
    return getattr(response, "text", "") or ""


class GeminiProvider:
    name = "gemini"
    model = "gemini-2.0-flash"

    def __init__(self, api_key: str, model: Optional[str] = None):
        if not api_key:
            raise ValueError("Gemini API key not configured for this user")
        self.api_key = api_key
        if model:
            self.model = model

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
        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        tool_decls = translate_schema(tools)

        model_kwargs: Dict[str, Any] = {}
        if system:
            model_kwargs["system_instruction"] = system
        if tool_decls:
            model_kwargs["tools"] = [{"function_declarations": tool_decls}]

        model = genai.GenerativeModel(self.model, **model_kwargs)

        # No-tools path: plain generate_content_async, no chat state needed.
        if not tool_decls:
            response = await model.generate_content_async(user)
            return _extract_text(response), []

        chat = model.start_chat()
        tool_calls: List[NormalizedToolCall] = []
        next_message: Any = user

        for turn in range(max_turns + 1):
            response = await chat.send_message_async(next_message)
            fn_parts = _extract_function_calls(response)
            if not fn_parts or turn == max_turns:
                return _extract_text(response), tool_calls

            # Build a list of function_response parts — one per function_call.
            response_parts: List[Dict[str, Any]] = []
            for part in fn_parts:
                fc = part.function_call
                tool_name = fc.name
                tool_input = dict(fc.args or {})
                output = await self._execute_tool(tool_name, tool_input, tool_ctx)
                # Gemini's function_response expects a JSON-serializable dict;
                # `default=str` + re-parse normalizes any unexpected types.
                response_parts.append({
                    "function_response": {
                        "name": tool_name,
                        "response": json.loads(json.dumps(output, default=str)),
                    }
                })
                tool_calls.append(NormalizedToolCall(
                    name=tool_name,
                    input=tool_input,
                    output=output,
                    output_summary=summarize_output(output),
                    turn=turn,
                ))
            next_message = response_parts

        return "", tool_calls
