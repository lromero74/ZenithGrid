"""Guard test: integer primary keys keep their auto-increment sequence default.

A past out-of-band rebuild of the ``bots`` table on PostgreSQL left ``bots.id`` with
no ``DEFAULT`` (the serial sequence was detached). The primary key is still NOT NULL,
so every ``INSERT`` that omits ``id`` — bot creation and cloning from the UI — failed
with a NOT NULL violation instead of auto-assigning the next id. The companion
migration ``093_fix_bots_id_sequence`` restores the sequence and re-asserts it on every
deploy; this test fails loudly the moment any core financial table's id loses its
``nextval(...)`` default again.

PostgreSQL-only: SQLite uses ``INTEGER PRIMARY KEY`` (a rowid alias) which auto-assigns
without a sequence, so the test skips on the dev SQLite engine (keeping the bare-env
suite green with no .env / no PostgreSQL).

See CLAUDE.md → "Database & Migrations" and the bots.id-sequence regression.
"""
import importlib.util
import os
import sys

import pytest

from app.models import Account, Bot, OrderHistory, PendingOrder, Position, Signal, Trade

_MIGRATIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "migrations"))

# Core financial tables whose integer id MUST be auto-assigned by a sequence.
_SERIAL_PK_MODELS = [Account, Bot, Position, Trade, Signal, PendingOrder, OrderHistory]


def _get_migration_connection():
    """Load the real backend/migrations/db_utils and open a sync DB connection.

    pytest treats ``tests/migrations/`` as the ``migrations`` package, so register the
    real db_utils under that name first (same idiom as test_fk_delete_policies).
    """
    if "migrations.db_utils" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "migrations.db_utils", os.path.join(_MIGRATIONS_DIR, "db_utils.py")
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["migrations.db_utils"] = mod
        spec.loader.exec_module(mod)
    return sys.modules["migrations.db_utils"]


def _is_postgres():
    return "postgresql" in os.environ.get("DATABASE_URL", "")


@pytest.mark.skipif(not _is_postgres(), reason="sequence defaults are a PostgreSQL concern")
@pytest.mark.parametrize("model", _SERIAL_PK_MODELS, ids=lambda m: m.__tablename__)
def test_integer_pk_has_sequence_default(model):
    """Each core table's single-column integer id has a nextval(...) default."""
    table = model.__table__
    pk_cols = list(table.primary_key.columns)
    assert len(pk_cols) == 1, f"{table.name}: expected a single-column PK"
    pk = pk_cols[0]
    assert pk.name == "id"
    schema = table.schema or "public"

    db_utils = _get_migration_connection()
    conn = db_utils.get_migration_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s AND column_name = %s",
            (schema, table.name, pk.name),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    assert row is not None, f"{schema}.{table.name}.{pk.name} not found in DB"
    default = row[0]
    assert default and "nextval" in default, (
        f"{schema}.{table.name}.{pk.name} lost its sequence default "
        f"(got {default!r}); inserts that omit id will fail. "
        f"Run migration 093_fix_bots_id_sequence."
    )
