"""Tests for migration 078_add_rebalance_usdt.py
Tests that the USDT rebalance columns are properly added to accounts table.
"""

import importlib.util
import os
import sqlite3
import tempfile
from unittest.mock import patch
# Import the migration module (name starts with a digit, so use importlib)
# ---------------------------------------------------------------------------

_MIGRATIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "migrations"))
_MIGRATION_PATH = os.path.join(_MIGRATIONS_DIR, "078_add_rebalance_usdt.py")


def _load_migration():
    """Load 078_add_rebalance_usdt as a module at runtime.

    Problem: pytest treats ``tests/migrations/`` as the ``migrations`` package
    (because ``tests/migrations/__init__.py`` exists), so
    ``from migrations.db_utils import …`` inside the migration would look in
    ``tests/migrations/`` — which has no ``db_utils`` module.

    Fix: load the REAL ``backend/migrations/db_utils.py`` and register it as
    ``migrations.db_utils`` in sys.modules *before* loading the migration.
    We do NOT clear the rest of sys.modules (that would break the test file's
    own identity as ``migrations.test_078_add_rebalance_usdt``).
    """
    import sys

    # Inject the real db_utils under the expected module name so that
    # ``from migrations.db_utils import …`` inside the migration finds it.
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

    spec = importlib.util.spec_from_file_location("migration_078", _MIGRATION_PATH)
    if spec is None:
        raise ImportError(f"Migration file not found: {_MIGRATION_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


migration = _load_migration()


# ---------------------------------------------------------------------------
# In-memory SQLite DB with accounts table (needs to match the real schema)
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS accounts (
        id            INTEGER PRIMARY KEY,
        user_id       INTEGER NOT NULL,
        email         TEXT    NOT NULL UNIQUE,
        api_key       TEXT,
        api_secret    TEXT,
        passphrase    TEXT,
        exchange      TEXT    NOT NULL,
        rebalance_target_btc_pct FLOAT DEFAULT 0.0,
        min_balance_btc FLOAT DEFAULT 0.0,
        rebalance_target_usdc_pct FLOAT DEFAULT 0.0,
        min_balance_usdc FLOAT DEFAULT 0.0,
        rebalance_target_eth_pct FLOAT DEFAULT 0.0,
        min_balance_eth FLOAT DEFAULT 0.0,
        is_active     BOOLEAN DEFAULT 1,
        created_at    TEXT    NOT NULL,
        updated_at    TEXT    NOT NULL
    );
"""


def _make_test_db():
    """Create an in-memory SQLite database with the accounts table."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    return conn


def _make_file_test_db():
    """Create a temp-file SQLite database with the accounts table.

    Returns the file path. The caller is responsible for removing it.
    Using a file-backed DB allows the connection to be closed (as run() does)
    and then reopened for assertions.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    conn.close()
    return path


# ---------------------------------------------------------------------------
# TestAddUSDTColumns
# ---------------------------------------------------------------------------


class TestAddUSDTColumns:
    """Tests for the USDT rebalance columns migration."""

    def test_columns_added_when_missing(self):
        """run() adds rebalance_target_usdt_pct and min_balance_usdt when they don't exist."""
        db_path = _make_file_test_db()
        try:
            with patch.object(migration, "get_migration_connection",
                              side_effect=lambda: sqlite3.connect(db_path)):
                migration.run()

            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(accounts)")
                columns = {row[1]: row for row in cursor.fetchall()}
                assert "rebalance_target_usdt_pct" in columns
                assert "min_balance_usdt" in columns
                # Check default values (should be 0.0)
                assert columns["rebalance_target_usdt_pct"][3] == 0  # default value
                assert columns["min_balance_usdt"][3] == 0
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_run_is_idempotent(self):
        """Calling run() twice does not raise and leaves columns intact."""
        db_path = _make_file_test_db()
        try:
            with patch.object(migration, "get_migration_connection",
                              side_effect=lambda: sqlite3.connect(db_path)):
                migration.run()
                migration.run()  # must not raise

            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(accounts)")
                columns = {row[1]: row for row in cursor.fetchall()}
                assert "rebalance_target_usdt_pct" in columns
                assert "min_balance_usdt" in columns
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_skips_pre_existing_columns(self):
        """run() on an already-migrated DB does nothing."""
        db_path = _make_file_test_db()
        try:
            # Pre-add the columns to simulate an already-migrated state
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("ALTER TABLE accounts ADD COLUMN rebalance_target_usdt_pct FLOAT DEFAULT 0.0")
                conn.execute("ALTER TABLE accounts ADD COLUMN min_balance_usdt FLOAT DEFAULT 0.0")
                conn.commit()
            finally:
                conn.close()

            # Spy on safe_add_column to ensure it's called but returns False (no-op)
            with patch.object(migration, "get_migration_connection",
                              side_effect=lambda: sqlite3.connect(db_path)), \
                 patch.object(migration, "safe_add_column", wraps=migration.safe_add_column) as spy:
                migration.run()

            # safe_add_column should have been called once for each column but returned False (no-op)
            assert spy.call_count == 2

            # Verify columns still exist
            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(accounts)")
                columns = {row[1]: row for row in cursor.fetchall()}
                assert "rebalance_target_usdt_pct" in columns
                assert "min_balance_usdt" in columns
            finally:
                conn.close()
        finally:
            os.unlink(db_path)
