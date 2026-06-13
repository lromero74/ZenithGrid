"""Tests for migration add_account_value_snapshots.py
Tests that the account_value_snapshots table and indexes are properly created.
"""

import importlib.util
import os
import sqlite3
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Import the migration module (name starts with a letter, but we'll treat it as a file)
# ---------------------------------------------------------------------------

_MIGRATIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "migrations"))
_MIGRATION_PATH = os.path.join(_MIGRATIONS_DIR, "add_account_value_snapshots.py")


def _load_migration():
    """Load add_account_value_snapshots as a module at runtime."""
    import sys

    spec = importlib.util.spec_from_file_location("add_account_value_snapshots", _MIGRATION_PATH)
    if spec is None:
        raise ImportError(f"Migration file not found: {_MIGRATION_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["add_account_value_snapshots"] = mod
    spec.loader.exec_module(mod)
    return mod


migration = _load_migration()


# ---------------------------------------------------------------------------
# Helper to create a minimal schema for foreign key references
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS accounts (
        id    INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS users (
        id    INTEGER PRIMARY KEY
    );
"""


def _make_file_test_db():
    """Create a temp-file SQLite database with the minimal schema.

    Returns the file path as a Path object. The caller is responsible for removing it.
    """
    import tempfile
    import os
    import sqlite3
    from pathlib import Path

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    conn.close()
    # Return as Path object to match what get_db_path() returns
    return Path(path)


# ---------------------------------------------------------------------------
# TestAddAccountValueSnapshotsTable
# ---------------------------------------------------------------------------


class TestAddAccountValueSnapshotsTable:
    """Tests for the account_value_snapshots table migration."""

    def test_table_created_when_missing(self):
        """run_migration() creates the table and indexes when they don't exist."""
        db_path = _make_file_test_db()
        try:
            with patch.object(migration, "get_db_path", return_value=db_path):
                migration.run_migration()

            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.cursor()
                # Check table exists
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='account_value_snapshots'"
                )
                assert cursor.fetchone() is not None
                # Check indexes exist
                for index_name in [
                    "idx_account_value_snapshots_account_id",
                    "idx_account_value_snapshots_user_id",
                    "idx_account_value_snapshots_date",
                ]:
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                        (index_name,),
                    )
                    assert cursor.fetchone() is not None
                # Check table structure (columns)
                cursor.execute("PRAGMA table_info(account_value_snapshots)")
                columns = {row[1]: row for row in cursor.fetchall()}
                expected_columns = {
                    "id",
                    "account_id",
                    "user_id",
                    "snapshot_date",
                    "total_value_btc",
                    "total_value_usd",
                    "created_at",
                }
                assert expected_columns.issubset(set(columns.keys()))
                # Check foreign keys (sqlite3 doesn't enforce by default, but we can check the SQL)
                cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='account_value_snapshots'")
                create_sql = cursor.fetchone()[0]
                assert "FOREIGN KEY (account_id) REFERENCES accounts(id)" in create_sql
                assert "FOREIGN KEY (user_id) REFERENCES users(id)" in create_sql
                assert "UNIQUE (account_id, snapshot_date)" in create_sql
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_run_migration_is_idempotent(self):
        """Calling run_migration() twice does not raise and leaves table intact."""
        db_path = _make_file_test_db()
        try:
            with patch.object(migration, "get_db_path", return_value=db_path):
                migration.run_migration()
                migration.run_migration()  # must not raise

            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='account_value_snapshots'"
                )
                assert cursor.fetchone() is not None
                # Check indexes still exist
                for index_name in [
                    "idx_account_value_snapshots_account_id",
                    "idx_account_value_snapshots_user_id",
                    "idx_account_value_snapshots_date",
                ]:
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                        (index_name,),
                    )
                    assert cursor.fetchone() is not None
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_skips_when_table_exists(self):
        """run_migration() on an already-migrated DB does nothing (no error)."""
        db_path = _make_file_test_db()
        try:
            # Pre-create the table and indexes to simulate an already-migrated state
            conn = sqlite3.connect(db_path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE account_value_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        account_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        snapshot_date DATETIME NOT NULL,
                        total_value_btc REAL NOT NULL DEFAULT 0.0,
                        total_value_usd REAL NOT NULL DEFAULT 0.0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                        UNIQUE (account_id, snapshot_date)
                    );
                    CREATE INDEX idx_account_value_snapshots_account_id ON account_value_snapshots(account_id);
                    CREATE INDEX idx_account_value_snapshots_user_id ON account_value_snapshots(user_id);
                    CREATE INDEX idx_account_value_snapshots_date ON account_value_snapshots(snapshot_date);
                    """
                )
                conn.commit()
            finally:
                conn.close()

            # Spy on the execution to ensure no DDL is run (we can't easily spy
            # on sqlite3.execute, but we can check that the function returns True).
            # Instead, we'll just check that the function runs without error and
            # the table remains.
            with patch.object(migration, "get_db_path", return_value=db_path):
                result = migration.run_migration()
                # The function returns True on success (whether it created or skipped)
                assert result is True

            # Verify the table and indexes are still present (unchanged)
            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='account_value_snapshots'"
                )
                assert cursor.fetchone() is not None
                for index_name in [
                    "idx_account_value_snapshots_account_id",
                    "idx_account_value_snapshots_user_id",
                    "idx_account_value_snapshots_date",
                ]:
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                        (index_name,),
                    )
                    assert cursor.fetchone() is not None
            finally:
                conn.close()
        finally:
            os.unlink(db_path)
