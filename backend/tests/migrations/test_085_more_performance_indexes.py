"""
Tests for backend/migrations/085_more_performance_indexes.py

Covers:
- run(): creates both expected compound indexes (trades, pending_orders)
- run(): is idempotent — calling twice does not raise
- run(): skips pre-existing indexes

The _index_exists/_create_index helpers are identical to migration 077's and
are unit-tested in test_077_performance_indexes.py; this module exercises the
085 entry point.
"""

import importlib.util
import os
import sqlite3
import tempfile
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Import the migration module (name starts with a digit, so use importlib)
# ---------------------------------------------------------------------------

_MIGRATIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "migrations"))
_MIGRATION_PATH = os.path.join(_MIGRATIONS_DIR, "085_more_performance_indexes.py")


def _load_migration():
    """Load 085_more_performance_indexes as a module at runtime.

    Same loader pattern as test_077_performance_indexes.py: register the REAL
    backend/migrations/db_utils.py as ``migrations.db_utils`` first, because
    pytest treats tests/migrations/ as the ``migrations`` package.
    """
    import sys

    real_db_utils_path = os.path.join(_MIGRATIONS_DIR, "db_utils.py")
    if "migrations.db_utils" not in sys.modules:
        db_spec = importlib.util.spec_from_file_location(
            "migrations.db_utils", real_db_utils_path
        )
        if db_spec is None:
            raise ImportError(f"db_utils not found at: {real_db_utils_path}")
        db_mod = importlib.util.module_from_spec(db_spec)
        sys.modules["migrations.db_utils"] = db_mod
        db_spec.loader.exec_module(db_mod)

    spec = importlib.util.spec_from_file_location("migration_085", _MIGRATION_PATH)
    if spec is None:
        raise ImportError(f"Migration file not found: {_MIGRATION_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


migration = _load_migration()

_INDEX_NAMES = (
    "ix_trades_position_timestamp",
    "ix_pending_orders_position_status",
)

_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS trades (
        id          INTEGER PRIMARY KEY,
        position_id INTEGER,
        timestamp   TEXT,
        side        TEXT
    );
    CREATE TABLE IF NOT EXISTS pending_orders (
        id          INTEGER PRIMARY KEY,
        position_id INTEGER NOT NULL,
        bot_id      INTEGER NOT NULL,
        status      TEXT    NOT NULL
    );
"""


def _make_file_test_db():
    """Create a temp-file SQLite database with the required tables."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    conn.close()
    return path


class TestRun:
    """Integration tests for run(), the migration entry point."""

    def test_creates_both_indexes(self):
        """run() creates both compound indexes on a fresh database (happy path)."""
        db_path = _make_file_test_db()
        try:
            with patch.object(migration, "get_migration_connection",
                              side_effect=lambda: sqlite3.connect(db_path)), \
                 patch.object(migration, "is_postgres", return_value=False):
                migration.run()

            conn = sqlite3.connect(db_path)
            try:
                for name in _INDEX_NAMES:
                    assert migration._index_exists(conn, name) is True
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_run_is_idempotent(self):
        """Calling run() twice does not raise and leaves the indexes intact (edge case)."""
        db_path = _make_file_test_db()
        try:
            with patch.object(migration, "get_migration_connection",
                              side_effect=lambda: sqlite3.connect(db_path)), \
                 patch.object(migration, "is_postgres", return_value=False):
                migration.run()
                migration.run()  # must not raise

            conn = sqlite3.connect(db_path)
            try:
                for name in _INDEX_NAMES:
                    assert migration._index_exists(conn, name) is True
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_skips_pre_existing_indexes(self):
        """run() on an already-migrated DB skips both indexes (failure-avoidance path)."""
        db_path = _make_file_test_db()
        try:
            conn = sqlite3.connect(db_path)
            migration._create_index(
                conn, "ix_trades_position_timestamp", "trades", ["position_id", "timestamp"]
            )
            migration._create_index(
                conn, "ix_pending_orders_position_status", "pending_orders", ["position_id", "status"]
            )
            conn.close()

            with patch.object(migration, "get_migration_connection",
                              side_effect=lambda: sqlite3.connect(db_path)), \
                 patch.object(migration, "is_postgres", return_value=False), \
                 patch.object(migration, "_create_index", wraps=migration._create_index) as spy:
                migration.run()

            assert spy.call_count == 2
            verify_conn = sqlite3.connect(db_path)
            try:
                for name in _INDEX_NAMES:
                    assert migration._index_exists(verify_conn, name) is True
            finally:
                verify_conn.close()
        finally:
            os.unlink(db_path)
