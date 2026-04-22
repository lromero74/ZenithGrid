"""
Tests for backend/migrations/083_ai_opinion_log_speculative.py

Covers:
- run(): adds all three speculative columns to a fresh ai_opinion_log (SQLite path)
- run(): is idempotent — calling twice does not raise
- run(): does not clobber existing column values when re-run
"""

import importlib.util
import os
import sqlite3
import tempfile
from unittest.mock import patch


_MIGRATIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "migrations"))
_MIGRATION_PATH = os.path.join(_MIGRATIONS_DIR, "083_ai_opinion_log_speculative.py")


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

    spec = importlib.util.spec_from_file_location("migration_083", _MIGRATION_PATH)
    if spec is None:
        raise ImportError(f"Migration file not found: {_MIGRATION_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


migration = _load_migration()


_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS ai_opinion_log (
        id             INTEGER PRIMARY KEY,
        user_id        INTEGER,
        product_id     TEXT NOT NULL,
        is_sell_check  BOOLEAN NOT NULL DEFAULT 0,
        signal         TEXT NOT NULL,
        confidence     INTEGER NOT NULL DEFAULT 0,
        reasoning      TEXT
    );
    INSERT INTO ai_opinion_log (id, user_id, product_id, signal)
    VALUES (1, 42, 'HYPE-USD', 'buy');
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
    def test_adds_three_speculative_columns(self):
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
                cols = _columns(conn, "ai_opinion_log")
                assert "doubling_probability_score" in cols
                assert "speculative_score" in cols
                assert "speculative_components" in cols
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_idempotent(self):
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
                cols = _columns(conn, "ai_opinion_log")
                assert "doubling_probability_score" in cols
                assert "speculative_score" in cols
                assert "speculative_components" in cols
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_preserves_existing_row_values_on_rerun(self):
        """Backfilled rows must not lose their values when the migration re-runs."""
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
                conn.execute(
                    "UPDATE ai_opinion_log SET doubling_probability_score = 77, "
                    "speculative_score = 60 WHERE id = 1"
                )
                conn.commit()
                conn.close()

                migration.run()

            conn = sqlite3.connect(db_path)
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT doubling_probability_score, speculative_score FROM ai_opinion_log WHERE id = 1"
                )
                row = cur.fetchone()
                cur.close()
                assert row[0] == 77
                assert row[1] == 60
            finally:
                conn.close()
        finally:
            os.unlink(db_path)
