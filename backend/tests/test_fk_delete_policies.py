"""Guard test: foreign-key ON DELETE policies are declared explicitly and consistently.

Financial-record tables (trades, positions, pending_orders, order_history) must use
RESTRICT so a stray parent delete can never silently cascade away trading history.
Nullable analysis-link FKs (signals.position_id, order_history.position_id, and the
ai_opinion_log links) use SET NULL — keep the analysis row, just unlink it when the
position/bot/account it referenced is deleted. Derived snapshots CASCADE.

This test inspects the SQLAlchemy models directly (zero DB access), so it catches a
regression the moment someone adds a FK without an explicit ``ondelete`` or flips one
to the wrong policy. The companion migration ``set_fk_delete_policies`` aligns the
live PostgreSQL schema with what these models declare.

See CLAUDE.md → "Foreign-key delete policy & account purge".
"""
import pytest

from app.models import (
    Trade, Position, PendingOrder, OrderHistory, Signal, AIOpinionLog,
)
from app.models.reporting import AccountValueSnapshot


# (model, column_name, expected_ondelete, expected_referenced_table.column)
RESTRICT_FKS = [
    (Trade, "position_id", "RESTRICT", "trading.positions.id"),
    (Position, "account_id", "RESTRICT", "trading.accounts.id"),
    (Position, "bot_id", "RESTRICT", "trading.bots.id"),
    (PendingOrder, "position_id", "RESTRICT", "trading.positions.id"),
    (PendingOrder, "bot_id", "RESTRICT", "trading.bots.id"),
]

SET_NULL_FKS = [
    (Signal, "position_id", "SET NULL", "trading.positions.id"),
    (OrderHistory, "position_id", "SET NULL", "trading.positions.id"),
    (OrderHistory, "bot_id", "SET NULL", "trading.bots.id"),
    (AIOpinionLog, "account_id", "SET NULL", "trading.accounts.id"),
    (AIOpinionLog, "bot_id", "SET NULL", "trading.bots.id"),
    (AIOpinionLog, "position_id", "SET NULL", "trading.positions.id"),
]

CASCADE_FKS = [
    (AccountValueSnapshot, "account_id", "CASCADE", "trading.accounts.id"),
]

ALL_FKS = RESTRICT_FKS + SET_NULL_FKS + CASCADE_FKS


def _foreign_key(model, column_name):
    """Return the single ForeignKey object on a model column."""
    column = model.__table__.c[column_name]
    fks = list(column.foreign_keys)
    assert len(fks) == 1, f"{model.__name__}.{column_name} should have exactly one FK, got {len(fks)}"
    return fks[0]


@pytest.mark.parametrize("model,column,expected_ondelete,expected_target", ALL_FKS)
def test_fk_declares_expected_ondelete(model, column, expected_ondelete, expected_target):
    fk = _foreign_key(model, column)
    assert fk.ondelete == expected_ondelete, (
        f"{model.__name__}.{column} ondelete is {fk.ondelete!r}, expected {expected_ondelete!r}"
    )
    assert fk.target_fullname == expected_target, (
        f"{model.__name__}.{column} targets {fk.target_fullname}, expected {expected_target}"
    )


def test_set_null_fk_columns_are_nullable():
    """SET NULL is only valid when the column can actually hold NULL."""
    for model, column, _, _ in SET_NULL_FKS:
        assert model.__table__.c[column].nullable, (
            f"{model.__name__}.{column} is SET NULL but not nullable"
        )
