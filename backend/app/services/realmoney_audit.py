"""Real-money order audit trail.

Every order placed against a real exchange account is recorded here as one
JSON line — what was bought/sold, how much, the resulting order id, and (the
point of this module) **which subsystem initiated it**. Paper accounts never
reach this code: only the real CoinbaseUnifiedClient calls record_order.

Subsystem attribution rides a contextvar so callers don't have to thread a label
through every function. Each entry point (bot monitor, dust sweep, rebalancer,
panic sell, manual ops) wraps its work in ``subsystem(...)`` and any order placed
inside that scope is tagged accordingly.

The trail is written to ``backend/logs/real_money_trades.log`` (rotating) and
also propagates to the normal app log / journald for live visibility.
"""
import contextlib
import contextvars
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

from app.utils.timeutil import utcnow

_subsystem_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "realmoney_subsystem", default="unknown"
)

# Dedicated audit logger — file + propagation to the app log.
_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs"
)
_AUDIT_LOG_PATH = os.path.join(_LOG_DIR, "real_money_trades.log")

audit_logger = logging.getLogger("realmoney.audit")


def _ensure_handler() -> None:
    """Attach the rotating file handler once (idempotent across imports)."""
    if any(getattr(h, "_realmoney_audit", False) for h in audit_logger.handlers):
        return
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        handler = RotatingFileHandler(
            _AUDIT_LOG_PATH, maxBytes=10 * 1024 * 1024, backupCount=10
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._realmoney_audit = True  # type: ignore[attr-defined]
        audit_logger.addHandler(handler)
        audit_logger.setLevel(logging.INFO)
    except Exception:
        # Never let audit-log setup break trading; app-log propagation still works.
        logging.getLogger(__name__).warning(
            "Could not open real-money audit file %s", _AUDIT_LOG_PATH, exc_info=True
        )


_ensure_handler()


def current_subsystem() -> str:
    """The subsystem label in effect for the current async context."""
    return _subsystem_var.get()


@contextlib.contextmanager
def subsystem(name: str):
    """Tag every real-money order placed inside this scope with ``name``.

    Usage:
        with subsystem(f"bot:{bot.strategy_type}:{bot.id}"):
            ... place orders ...
    """
    token = _subsystem_var.set(name or "unknown")
    try:
        yield
    finally:
        _subsystem_var.reset(token)


def set_subsystem(name: str) -> contextvars.Token:
    """Imperatively set the subsystem; caller is responsible for reset().

    Prefer the ``subsystem(...)`` context manager. This exists for entry points
    that can't wrap their body in a ``with`` (e.g. a long-lived per-task setup).
    """
    return _subsystem_var.set(name or "unknown")


def _extract_order_id(result: Optional[Dict[str, Any]]) -> str:
    if not isinstance(result, dict):
        return ""
    return (
        result.get("success_response", {}).get("order_id", "")
        or result.get("order_id", "")
    )


def _extract_status(result: Optional[Dict[str, Any]]) -> str:
    if not isinstance(result, dict):
        return "unknown"
    if result.get("blocked_by"):
        return f"blocked:{result.get('blocked_by')}"
    if _extract_order_id(result):
        return "success"
    if result.get("error_response") or result.get("error"):
        return "failed"
    return "unknown"


def record_order(
    *,
    account_id: Optional[int],
    side: str,
    product_id: str,
    order_type: str = "market",
    size: Optional[Any] = None,
    funds: Optional[Any] = None,
    limit_price: Optional[Any] = None,
    result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write one audit record for a real-money order. Returns the record.

    Designed to never raise into the trading path: any failure is swallowed and
    logged at debug level. ``size`` is base-currency amount, ``funds`` is
    quote-currency amount (mutually exclusive per Coinbase's API).
    """
    status = _extract_status(result)
    order_id = _extract_order_id(result)
    error = None
    if isinstance(result, dict) and status.startswith(("failed", "blocked")):
        error = result.get("error_response") or result.get("error")

    record = {
        "ts": utcnow().isoformat(),
        "subsystem": current_subsystem(),
        "account_id": account_id,
        "side": (side or "").upper(),
        "product_id": product_id,
        "order_type": order_type,
        "size": str(size) if size is not None else None,
        "funds": str(funds) if funds is not None else None,
        "limit_price": str(limit_price) if limit_price is not None else None,
        "status": status,
        "order_id": order_id,
        "error": error,
    }
    try:
        audit_logger.info(json.dumps(record, default=str))
    except Exception:
        logging.getLogger(__name__).debug(
            "real-money audit emit failed", exc_info=True
        )
    return record


def record_event(event: str, **fields: Any) -> Dict[str, Any]:
    """Record a non-order trace event to the same audit trail.

    For anything that helps diagnose real-money trading problems but isn't an
    order placement — e.g. a close clamped because the wallet held less than the
    position recorded (today's INSUFFICIENT_FUND class of bug), a detected
    balance shortfall, or a skipped/aborted action. Tagged with the current
    subsystem and timestamp, same as orders. Never raises into the caller.
    """
    record = {
        "ts": utcnow().isoformat(),
        "subsystem": current_subsystem(),
        "event": event,
        **fields,
    }
    try:
        audit_logger.info(json.dumps(record, default=str))
    except Exception:
        logging.getLogger(__name__).debug(
            "real-money audit event emit failed", exc_info=True
        )
    return record
