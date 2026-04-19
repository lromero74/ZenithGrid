"""AI tools package — callable functions the AI indicator can invoke via tool use.

Each tool is a small module with a `TOOL` export (a `Tool` instance). Importing
the module registers it in the shared `REGISTRY`. Keep this package import chain
independent of `app.indicators.__init__` to avoid circular imports with strategies.
"""

from app.indicators.ai_tools.base import (
    REGISTRY,
    Tool,
    ToolContext,
    execute,
    get_schemas_for,
    register,
)

# Side-effect imports: each module calls register(...) at import time.
from app.indicators.ai_tools import position_context  # noqa: F401
from app.indicators.ai_tools import portfolio_context  # noqa: F401

__all__ = [
    "REGISTRY",
    "Tool",
    "ToolContext",
    "execute",
    "get_schemas_for",
    "register",
]
