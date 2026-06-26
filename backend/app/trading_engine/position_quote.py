"""Direction-aware "deployed quote" for a position — single source of truth.

A long position accumulates the quote it spent in ``total_quote_spent``; a short
accumulates the quote it received in ``short_total_sold_quote`` (its
``total_quote_spent`` stays 0). Budget/remainder math must pick the right field per
direction — otherwise a short's deployed capital reads as 0 and the budget gate
over-allocates. The SQL aggregate in ``signal_processor/_shared`` mirrors this with a
CASE expression, kept honest by ``tests/trading_engine/test_position_quote.py``.

See CLAUDE.md rule 13 (one source of truth for every financial calculation).
"""
from typing import Any


def deployed_quote(position: Any) -> float:
    """Quote actually deployed into ``position``, direction-aware (shorts use
    ``short_total_sold_quote``, longs use ``total_quote_spent``)."""
    if getattr(position, "direction", "long") == "short":
        return float(getattr(position, "short_total_sold_quote", 0.0) or 0.0)
    return float(getattr(position, "total_quote_spent", 0.0) or 0.0)
