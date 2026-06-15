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
import importlib.util
import os
import sys

import pytest

from app.models import (
    Trade, Position, PendingOrder, OrderHistory, Signal, AIOpinionLog,
)
from app.models.reporting import AccountValueSnapshot

_MIGRATIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "migrations"))


def _load_fk_migration():
    """Load backend/migrations/set_fk_delete_policies.py.

    pytest treats ``tests/migrations/`` as the ``migrations`` package (it has an
    __init__.py), so ``from migrations.db_utils import …`` inside the migration would
    look there. Register the REAL db_utils under that name first, then load the
    migration by file path under a unique module name. (Same idiom as test_077.)
    """
    if "migrations.db_utils" not in sys.modules:
        db_spec = importlib.util.spec_from_file_location(
            "migrations.db_utils", os.path.join(_MIGRATIONS_DIR, "db_utils.py")
        )
        db_mod = importlib.util.module_from_spec(db_spec)
        sys.modules["migrations.db_utils"] = db_mod
        db_spec.loader.exec_module(db_mod)

    spec = importlib.util.spec_from_file_location(
        "fk_policy_migration", os.path.join(_MIGRATIONS_DIR, "set_fk_delete_policies.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_FK_MIGRATION = _load_fk_migration()


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


# --- migration / model parity -------------------------------------------------
# The Postgres-aligning migration carries its own copy of the policy table; the
# SQLite test env can't exercise its DDL, so these guards at least keep that copy
# from drifting away from the models it's meant to mirror.

_MODELS_BY_TABLE = {
    m.__tablename__: m
    for m in (Trade, Position, PendingOrder, OrderHistory, Signal, AIOpinionLog)
}


def test_migration_policy_table_matches_models():
    for table, column, parent, target_rule, _strategy in _FK_MIGRATION.FK_POLICIES:
        model = _MODELS_BY_TABLE[table]
        fk = _foreign_key(model, column)
        assert fk.ondelete == target_rule, (
            f"migration declares {table}.{column} -> {target_rule}, "
            f"but the model declares {fk.ondelete}"
        )
        assert fk.target_fullname == f"trading.{parent}.id", (
            f"migration declares {table}.{column} -> trading.{parent}.id, "
            f"but the model targets {fk.target_fullname}"
        )


def test_migration_drop_not_null_columns_are_nullable_in_model():
    """A column the migration drops NOT NULL from must be nullable in the model,
    or the two init paths would disagree on the column's nullability."""
    for table, column in _FK_MIGRATION.DROP_NOT_NULL:
        model = _MODELS_BY_TABLE[table]
        assert model.__table__.c[column].nullable, (
            f"migration drops NOT NULL on {table}.{column} but the model keeps it NOT NULL"
        )
