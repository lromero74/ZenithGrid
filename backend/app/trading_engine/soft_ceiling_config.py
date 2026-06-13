"""Compatibility helpers for soft-ceiling bot settings."""

from typing import Any
from unittest.mock import Mock


def is_soft_ceiling_enabled(bot: Any) -> bool:
    """Return whether the bot's deal soft ceiling is enabled.

    Newer bots store this as a first-class column. Older snapshots/tests may
    still carry the flag in strategy_config, so keep both paths compatible.
    """
    column_value = getattr(bot, "enable_soft_ceiling", None)
    if column_value is not None and not isinstance(column_value, Mock):
        return bool(column_value)

    strategy_config = getattr(bot, "strategy_config", None) or {}
    return bool(strategy_config.get("enable_soft_ceiling", False))
