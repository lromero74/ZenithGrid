"""Authoritative exit-origin metadata for closed positions."""

import socket
from typing import Optional

from app.config import settings


def record_exit_provenance(
    position,
    trigger_reason: str,
    order_id: Optional[str],
    process_role: Optional[str] = None,
) -> bool:
    """Persist exit origin and return whether an automatic exit came from the web role."""
    role = process_role or settings.process_role
    reason = (getattr(position, "exit_reason", None) or "").lower()
    trigger_lower = (trigger_reason or "").lower()
    if not reason:
        if "stop loss" in trigger_lower or "tsl" in trigger_lower:
            reason = "stop_loss"
        elif "take profit" in trigger_lower:
            reason = "take_profit"
        else:
            reason = "signal"
        position.exit_reason = reason

    source = "manual" if reason == "manual" else "automatic"
    position.exit_source = source
    position.exit_trigger_reason = trigger_reason
    position.exit_process_role = role
    position.exit_hostname = socket.gethostname()
    position.exit_order_id = order_id
    unexpected = source == "automatic" and (
        role == "web" or (settings.environment == "production" and role != "trader")
    )
    position.exit_was_unexpected = unexpected
    return unexpected
