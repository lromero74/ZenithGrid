"""
Database utilities for dual-mode migrations (SQLite + PostgreSQL).

Existing 59+ migration scripts are SQLite-only and won't re-run after
the PostgreSQL data migration. New migrations should use these helpers
for cross-database compatibility.

Usage in a migration script:
    from migrations.db_utils import get_migration_connection, column_exists, safe_add_column

    conn = get_migration_connection()
    if not column_exists(conn, "bots", "new_column"):
        safe_add_column(conn, "bots", "new_column TEXT DEFAULT ''")
    conn.close()
"""

import os
import sqlite3

from dotenv import load_dotenv

# Load .env from backend directory
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_backend_dir, ".env"))


def _get_database_url():
    """Read DATABASE_URL from environment."""
    return os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./trading.db")


def is_postgres():
    """Check if the configured database is PostgreSQL."""
    return "postgresql" in _get_database_url()


def get_migration_connection():
    """Get a sync DB connection for migrations.

    Returns sqlite3.Connection for SQLite or psycopg2 connection for PostgreSQL.
    Caller must close the connection when done.
    """
    url = _get_database_url()

    if "postgresql" in url:
        import psycopg2
        # Parse: postgresql+asyncpg://user:pass@host:port/dbname
        # or:   postgresql+psycopg2://user:pass@host/dbname
        clean = url.split("://", 1)[1]  # user:pass@host:port/dbname
        userpass, hostdb = clean.rsplit("@", 1)
        user, password = userpass.split(":", 1)
        if "/" in hostdb:
            host_port, dbname = hostdb.split("/", 1)
        else:
            host_port = hostdb
            dbname = "zenithgrid"
        host = host_port.split(":")[0] if ":" in host_port else host_port
        port = int(host_port.split(":")[1]) if ":" in host_port else 5432

        return psycopg2.connect(
            host=host, port=port, dbname=dbname,
            user=user, password=password
        )
    else:
        # SQLite
        db_path = os.path.join(_backend_dir, "trading.db")
        return sqlite3.connect(db_path)


def column_exists(conn, table, column):
    """Check if a column exists in a table (works for both SQLite and PostgreSQL)."""
    if is_postgres():
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = %s AND column_name = %s",
            (table, column)
        )
        result = cursor.fetchone()
        cursor.close()
        return result is not None
    else:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]
        cursor.close()
        return column in columns


def safe_add_column(conn, table, column_def):
    """Idempotent ADD COLUMN for both databases.

    Args:
        conn: Database connection
        table: Table name
        column_def: Column definition (e.g., "new_col TEXT DEFAULT ''")
    """
    col_name = column_def.split()[0]

    if column_exists(conn, table, col_name):
        return False  # Already exists

    cursor = conn.cursor()
    try:
        if is_postgres():
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
            conn.commit()
        else:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
            conn.commit()
    except Exception:
        conn.rollback()
        return False  # Already exists or other error
    finally:
        cursor.close()

    return True
