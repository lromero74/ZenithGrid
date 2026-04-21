"""Tool registry base — ToolContext, Tool dataclass, REGISTRY, schema helpers."""

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    """Everything a tool might need to look something up.

    Fields are optional where the tool can reasonably return a "no context" note
    instead of erroring. Tools should validate the fields they actually need and
    return a descriptive dict when preconditions aren't met (never raise).
    """
    db: AsyncSession
    user_id: int
    product_id: str
    current_price: float
    bot: Optional[Any] = None
    position: Optional[Any] = None
    account_id: Optional[int] = None
    is_sell_check: bool = False


ToolFn = Callable[[Dict[str, Any], ToolContext], Awaitable[Dict[str, Any]]]


@dataclass
class Tool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    fn: ToolFn


REGISTRY: Dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    if tool.name in REGISTRY:
        raise ValueError(f"Duplicate tool registration: {tool.name}")
    REGISTRY[tool.name] = tool
    return tool


def get_schemas_for(names: List[str]) -> List[Dict[str, Any]]:
    """Return Anthropic-format tool schemas for the named tools (unknowns skipped)."""
    schemas: List[Dict[str, Any]] = []
    for n in names:
        tool = REGISTRY.get(n)
        if tool is None:
            continue
        schemas.append({
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        })
    return schemas


async def execute(name: str, input: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    """Run a tool. Errors become `{"error": "..."}` so the model can continue."""
    tool = REGISTRY.get(name)
    if tool is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return await tool.fn(input or {}, ctx)
    except Exception as e:  # fail-open: never break the tool loop
        logger.warning(f"Tool {name} failed: {type(e).__name__}: {e}")
        return {"error": f"{type(e).__name__}: {e}"}
