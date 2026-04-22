"""
Tests for backend/migrations/082_speculative_bucket.py

Covers:
- run(): adds both columns to a fresh accounts table (SQLite path)
- run(): is idempotent — calling twice does not raise, columns stay present
- run(): does not clobber existing column values when re-run
"""

import importlib.util
import os
import sqlite3
import tempfile
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Import the migration module (name starts with a digit, so use importlib).
# Reuses the same trick as test_077_performance_indexes.py.
# ---------------------------------------------------------------------------

_MIGRATIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "migrations"))
_MIGRATION_PATH = os.path.join(_MIGRATIONS_DIR, "082_speculative_bucket.py")


def _load_migration():
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

    spec = importlib.util.spec_from_file_location("migration_082", _MIGRATION_PATH)
    if spec is None:
        raise ImportError(f"Migration file not found: {_MIGRATION_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


migration = _load_migration()


_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS accounts (
        id      INTEGER PRIMARY KEY,
        user_id INTEGER,
        name    TEXT NOT NULL,
        type    TEXT NOT NULL
    );
    -- Seed one row so we can verify the default is applied / preserved.
    INSERT INTO accounts (id, user_id, name, type) VALUES (1, 42, 'Test', 'cex');
"""


def _make_file_test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    conn.close()
    return path


def _columns(conn, table):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}
    cur.close()
    return cols


class TestRun:
    def test_adds_both_columns(self):
        db_path = _make_file_test_db()
        try:
            import sys
            db_utils_mod = sys.modules["migrations.db_utils"]
            with patch.object(migration, "get_migration_connection",
                              side_effect=lambda: sqlite3.connect(db_path)), \
                 patch.object(migration, "is_postgres", return_value=False), \
                 patch.object(db_utils_mod, "is_postgres", return_value=False):
                migration.run()

            conn = sqlite3.connect(db_path)
            try:
                cols = _columns(conn, "accounts")
                assert "speculative_allocation_pct" in cols
                assert "speculative_calibration_last_alerted_at" in cols
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_idempotent(self):
        """Running twice does not raise and leaves both columns present."""
        db_path = _make_file_test_db()
        try:
            import sys
            db_utils_mod = sys.modules["migrations.db_utils"]
            with patch.object(migration, "get_migration_connection",
                              side_effect=lambda: sqlite3.connect(db_path)), \
                 patch.object(migration, "is_postgres", return_value=False), \
                 patch.object(db_utils_mod, "is_postgres", return_value=False):
                migration.run()
                migration.run()

            conn = sqlite3.connect(db_path)
            try:
                cols = _columns(conn, "accounts")
                assert "speculative_allocation_pct" in cols
                assert "speculative_calibration_last_alerted_at" in cols
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_default_allocation_is_zero(self):
        """Pre-existing rows pick up the DEFAULT 0.0 after the column is added."""
        db_path = _make_file_test_db()
        try:
            import sys
            db_utils_mod = sys.modules["migrations.db_utils"]
            with patch.object(migration, "get_migration_connection",
                              side_effect=lambda: sqlite3.connect(db_path)), \
                 patch.object(migration, "is_postgres", return_value=False), \
                 patch.object(db_utils_mod, "is_postgres", return_value=False):
                migration.run()

            conn = sqlite3.connect(db_path)
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT speculative_allocation_pct, speculative_calibration_last_alerted_at "
                    "FROM accounts WHERE id = 1"
                )
                row = cur.fetchone()
                cur.close()
                assert row[0] == 0.0
                assert row[1] is None
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_preserves_user_set_allocation_on_rerun(self):
        """If a user has set a non-default allocation, re-running must not reset it."""
        db_path = _make_file_test_db()
        try:
            import sys
            db_utils_mod = sys.modules["migrations.db_utils"]
            with patch.object(migration, "get_migration_connection",
                              side_effect=lambda: sqlite3.connect(db_path)), \
                 patch.object(migration, "is_postgres", return_value=False), \
                 patch.object(db_utils_mod, "is_postgres", return_value=False):
                migration.run()

                # User sets a non-default allocation
                conn = sqlite3.connect(db_path)
                conn.execute(
                    "UPDATE accounts SET speculative_allocation_pct = 5.5 WHERE id = 1"
                )
                conn.commit()
                conn.close()

                # Migration re-runs
                migration.run()

            conn = sqlite3.connect(db_path)
            try:
                cur = conn.cursor()
                cur.execute("SELECT speculative_allocation_pct FROM accounts WHERE id = 1")
                assert cur.fetchone()[0] == 5.5
                cur.close()
            finally:
                conn.close()
        finally:
            os.unlink(db_path)
