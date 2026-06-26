"""Tests for the direction-aware ``deployed_quote`` helper (sweep #4, rule 13).

This is the single source of truth for "how much quote is deployed into a position",
consumed by the batch budget gate (batch_analyzer) and the per-position safety-order
remainder (signal_processor/_shared). The SQL pair-level aggregate mirrors it.
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import case, func, select

from app.models import Position
from app.trading_engine.position_quote import deployed_quote


def _pos(**kw):
    return SimpleNamespace(**kw)


class TestDeployedQuote:
    def test_long_uses_total_quote_spent(self):
        """Happy path (long): deployed quote is total_quote_spent."""
        assert deployed_quote(_pos(direction="long", total_quote_spent=1234.5)) == 1234.5

    def test_short_uses_short_total_sold_quote(self):
        """Happy path (short): deployed quote is short_total_sold_quote, not the
        (always-zero) total_quote_spent."""
        assert deployed_quote(
            _pos(direction="short", short_total_sold_quote=900.0, total_quote_spent=0.0)
        ) == 900.0

    def test_short_ignores_total_quote_spent(self):
        """Edge: even if a short's long field is non-zero, the short field wins."""
        assert deployed_quote(
            _pos(direction="short", short_total_sold_quote=500.0, total_quote_spent=9999.0)
        ) == 500.0

    def test_none_fields_coerce_to_zero(self):
        """Edge: None deployed fields coerce to 0.0 (no TypeError)."""
        assert deployed_quote(_pos(direction="short", short_total_sold_quote=None)) == 0.0
        assert deployed_quote(_pos(direction="long", total_quote_spent=None)) == 0.0

    def test_missing_direction_defaults_to_long(self):
        """Failure/edge: a position without a direction attribute is treated as long."""
        assert deployed_quote(_pos(total_quote_spent=42.0)) == 42.0

    def test_missing_short_field_defaults_to_zero(self):
        """Failure/edge: a short missing short_total_sold_quote reads 0.0, not an error."""
        assert deployed_quote(_pos(direction="short")) == 0.0


class TestDeployedQuoteSqlParity:
    """G (sweep #4): the pair-level SQL aggregate in signal_processor/_shared must
    mirror deployed_quote — a short contributes short_total_sold_quote, not its
    (always-zero) total_quote_spent — or concurrent same-pair shorts over-allocate."""

    @pytest.mark.asyncio
    async def test_sql_case_matches_python_helper(self, db_session):
        rows = [
            Position(bot_id=1, product_id="BTC-USD", status="open", direction="long",
                     total_quote_spent=100.0, short_total_sold_quote=0.0),
            Position(bot_id=1, product_id="BTC-USD", status="open", direction="short",
                     total_quote_spent=0.0, short_total_sold_quote=200.0),
            Position(bot_id=1, product_id="BTC-USD", status="open", direction="short",
                     total_quote_spent=0.0, short_total_sold_quote=300.0),
            # Noise rows the WHERE must exclude (different pair, and a closed one).
            Position(bot_id=1, product_id="ETH-USD", status="open", direction="short",
                     total_quote_spent=0.0, short_total_sold_quote=999.0),
            Position(bot_id=1, product_id="BTC-USD", status="closed", direction="short",
                     total_quote_spent=0.0, short_total_sold_quote=888.0),
        ]
        for r in rows:
            db_session.add(r)
        await db_session.flush()

        deployed_col = case(
            (Position.direction == "short", Position.short_total_sold_quote),
            else_=Position.total_quote_spent,
        )
        result = await db_session.execute(
            select(func.coalesce(func.sum(deployed_col), 0.0)).where(
                Position.bot_id == 1, Position.status == "open", Position.product_id == "BTC-USD",
            )
        )
        sql_total = result.scalar()
        python_total = sum(deployed_quote(p) for p in rows[:3])
        assert sql_total == python_total == 600.0
