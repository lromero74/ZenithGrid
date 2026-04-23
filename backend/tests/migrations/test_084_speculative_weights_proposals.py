"""
Tests for backend/migrations/084_speculative_weights_proposals.py

Covers:
- run(): creates the table with all expected columns on SQLite
- run(): is idempotent — calling twice does not raise or duplicate
- run(): also creates the user_status index
"""

import importlib.util
import os
import sqlite3
import tempfile
from unittest.mock import patch


_MIGRATIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "migrations"))
_MIGRATION_PATH = os.path.join(_MIGRATIONS_DIR, "084_speculative_weights_proposals.py")


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

    spec = importlib.util.spec_from_file_location("migration_084", _MIGRATION_PATH)
    if spec is None:
        raise ImportError(f"Migration file not found: {_MIGRATION_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


migration = _load_migration()


def _make_file_test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


def _columns(conn, table):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}
    cur.close()
    return cols


def _indexes(conn, table):
    cur = conn.cursor()
    cur.execute(f"PRAGMA index_list({table})")
    idx_names = {row[1] for row in cur.fetchall()}
    cur.close()
    return idx_names


class TestRun:
    def test_creates_table_with_expected_columns(self):
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
                cols = _columns(conn, "speculative_weights_proposals")
                expected = {
                    "id", "user_id", "account_id", "status", "algorithm",
                    "sample_size", "overall_win_rate_pct",
                    "baseline_weights", "proposed_weights",
                    "divergence_pp", "reason",
                    "created_at", "decided_at", "decided_by",
                    "reverted_by_proposal_id",
                }
                assert expected.issubset(cols), (
                    f"missing cols: {expected - cols}"
                )
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
                cols = _columns(conn, "speculative_weights_proposals")
                assert "proposed_weights" in cols
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_creates_user_status_index(self):
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
                idx = _indexes(conn, "speculative_weights_proposals")
                assert "idx_spec_prop_user_status" in idx
            finally:
                conn.close()
        finally:
            os.unlink(db_path)
