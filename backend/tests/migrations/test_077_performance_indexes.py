"""
Tests for backend/migrations/077_performance_indexes.py

Covers:
- _index_exists(): returns False before index is created
- _index_exists(): returns True after index is created
- _create_index(): creates a new index, returns True
- _create_index(): skips existing index, returns False (idempotency)
- run(): creates all 3 expected indexes (signals, order_history, snapshots)
- run(): is idempotent — calling twice does not raise
"""

import importlib.util
import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import the migration module (name starts with a digit, so use importlib)
# ---------------------------------------------------------------------------

_MIGRATIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "migrations"))
_MIGRATION_PATH = os.path.join(_MIGRATIONS_DIR, "077_performance_indexes.py")


def _load_migration():
    """Load 077_performance_indexes as a module at runtime.

    Problem: pytest treats ``tests/migrations/`` as the ``migrations`` package
    (because ``tests/migrations/__init__.py`` exists), so
    ``from migrations.db_utils import …`` inside the migration would look in
    ``tests/migrations/`` — which has no ``db_utils`` module.

    Fix: load the REAL ``backend/migrations/db_utils.py`` and register it as
    ``migrations.db_utils`` in sys.modules *before* loading the migration.
    We do NOT clear the rest of sys.modules (that would break the test file's
    own identity as ``migrations.test_077_performance_indexes``).
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

    spec = importlib.util.spec_from_file_location("migration_077", _MIGRATION_PATH)
    if spec is None:
        raise ImportError(f"Migration file not found: {_MIGRATION_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Load once at module level — if the file doesn't exist the whole test module
# fails with ImportError, which is the correct TDD red state.
migration = _load_migration()


@pytest.fixture(autouse=True)
def _force_sqlite_mode():
    """Every test in this module operates on SQLite connections. The imported
    is_postgres() checks the runtime DATABASE_URL and returns True in prod
    environments, which routes _index_exists to the pg_indexes query — that
    fails against SQLite. Force it to False for the duration of each test."""
    with patch.object(migration, "is_postgres", return_value=False):
        yield


# ---------------------------------------------------------------------------
# In-memory SQLite DB with all three tables the migration touches
# ---------------------------------------------------------------------------


_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS signals (
        id          INTEGER PRIMARY KEY,
        position_id INTEGER,
        timestamp   TEXT,
        signal_type TEXT
    );
    CREATE TABLE IF NOT EXISTS order_history (
        id        INTEGER PRIMARY KEY,
        bot_id    INTEGER NOT NULL,
        timestamp TEXT    NOT NULL,
        status    TEXT    NOT NULL
    );
    CREATE TABLE IF NOT EXISTS account_value_snapshots (
        id            INTEGER PRIMARY KEY,
        account_id    INTEGER NOT NULL,
        user_id       INTEGER NOT NULL,
        snapshot_date TEXT    NOT NULL
    );
"""


def _make_test_db():
    """Create an in-memory SQLite database with the required tables."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    return conn


def _make_file_test_db():
    """Create a temp-file SQLite database with the required tables.

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
# TestIndexExists
# ---------------------------------------------------------------------------


class TestIndexExists:
    """Unit tests for the _index_exists() helper."""

    def test_returns_false_when_index_absent(self):
        """An index that was never created should not be found."""
        conn = _make_test_db()
        try:
            assert migration._index_exists(conn, "ix_signals_position_id") is False
        finally:
            conn.close()

    def test_returns_true_after_manual_creation(self):
        """An index created outside the migration is still detected."""
        conn = _make_test_db()
        try:
            conn.execute("CREATE INDEX ix_signals_position_id ON signals (position_id)")
            conn.commit()
            assert migration._index_exists(conn, "ix_signals_position_id") is True
        finally:
            conn.close()

    def test_different_index_names_are_independent(self):
        """Checking for index A does not collide with index B."""
        conn = _make_test_db()
        try:
            conn.execute("CREATE INDEX ix_signals_position_id ON signals (position_id)")
            conn.commit()
            assert migration._index_exists(conn, "ix_signals_position_id") is True
            assert migration._index_exists(conn, "ix_order_history_bot_id_timestamp") is False
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TestCreateIndex
# ---------------------------------------------------------------------------


class TestCreateIndex:
    """Unit tests for the _create_index() helper."""

    def test_creates_new_index_returns_true(self):
        """Creating a brand-new index returns True."""
        conn = _make_test_db()
        try:
            result = migration._create_index(
                conn, "ix_signals_position_id", "signals", ["position_id"]
            )
            assert result is True
        finally:
            conn.close()

    def test_created_index_is_detectable(self):
        """After _create_index(), _index_exists() confirms it exists."""
        conn = _make_test_db()
        try:
            migration._create_index(conn, "ix_signals_position_id", "signals", ["position_id"])
            assert migration._index_exists(conn, "ix_signals_position_id") is True
        finally:
            conn.close()

    def test_duplicate_call_returns_false(self):
        """Calling _create_index() a second time for the same index returns False."""
        conn = _make_test_db()
        try:
            migration._create_index(conn, "ix_signals_position_id", "signals", ["position_id"])
            result = migration._create_index(
                conn, "ix_signals_position_id", "signals", ["position_id"]
            )
            assert result is False
        finally:
            conn.close()

    def test_duplicate_call_does_not_raise(self):
        """Calling _create_index() twice does not raise any exception."""
        conn = _make_test_db()
        try:
            migration._create_index(conn, "ix_signals_position_id", "signals", ["position_id"])
            # Should be safe to call again
            migration._create_index(conn, "ix_signals_position_id", "signals", ["position_id"])
        finally:
            conn.close()

    def test_compound_index_created(self):
        """A multi-column index is created correctly."""
        conn = _make_test_db()
        try:
            result = migration._create_index(
                conn, "ix_order_history_bot_id_timestamp",
                "order_history", ["bot_id", "timestamp"]
            )
            assert result is True
            assert migration._index_exists(conn, "ix_order_history_bot_id_timestamp") is True
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TestRun
# ---------------------------------------------------------------------------


class TestRun:
    """Integration tests for run(), the migration entry point.

    Uses file-backed SQLite databases so run() can close the connection and
    we can reopen it for assertions — identical to how production runs.
    """

    def test_creates_all_three_indexes(self):
        """run() creates all three expected indexes on a fresh database."""
        db_path = _make_file_test_db()
        try:
            with patch.object(migration, "get_migration_connection",
                              side_effect=lambda: sqlite3.connect(db_path)), \
                 patch.object(migration, "is_postgres", return_value=False):
                migration.run()

            conn = sqlite3.connect(db_path)
            try:
                assert migration._index_exists(conn, "ix_signals_position_id") is True
                assert migration._index_exists(conn, "ix_order_history_bot_id_timestamp") is True
                assert migration._index_exists(conn, "ix_snapshot_user_date") is True
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_run_is_idempotent(self):
        """Calling run() twice does not raise and leaves all indexes intact."""
        db_path = _make_file_test_db()
        try:
            with patch.object(migration, "get_migration_connection",
                              side_effect=lambda: sqlite3.connect(db_path)), \
                 patch.object(migration, "is_postgres", return_value=False):
                migration.run()
                migration.run()  # must not raise

            conn = sqlite3.connect(db_path)
            try:
                assert migration._index_exists(conn, "ix_signals_position_id") is True
                assert migration._index_exists(conn, "ix_order_history_bot_id_timestamp") is True
                assert migration._index_exists(conn, "ix_snapshot_user_date") is True
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_skips_pre_existing_indexes(self):
        """run() on an already-migrated DB skips all three indexes."""
        db_path = _make_file_test_db()
        try:
            # Pre-create all indexes to simulate an already-migrated state
            conn = sqlite3.connect(db_path)
            migration._create_index(conn, "ix_signals_position_id", "signals", ["position_id"])
            migration._create_index(
                conn, "ix_order_history_bot_id_timestamp", "order_history", ["bot_id", "timestamp"]
            )
            migration._create_index(
                conn, "ix_snapshot_user_date", "account_value_snapshots", ["user_id", "snapshot_date"]
            )
            conn.close()

            with patch.object(migration, "get_migration_connection",
                              side_effect=lambda: sqlite3.connect(db_path)), \
                 patch.object(migration, "is_postgres", return_value=False), \
                 patch.object(migration, "_create_index", wraps=migration._create_index) as spy:
                migration.run()

            # _create_index was called exactly 3 times (once per index)
            assert spy.call_count == 3
            # After a no-op run, all 3 indexes are still present
            verify_conn = sqlite3.connect(db_path)
            try:
                assert migration._index_exists(verify_conn, "ix_signals_position_id") is True
                assert migration._index_exists(verify_conn, "ix_order_history_bot_id_timestamp") is True
                assert migration._index_exists(verify_conn, "ix_snapshot_user_date") is True
            finally:
                verify_conn.close()
        finally:
            os.unlink(db_path)
