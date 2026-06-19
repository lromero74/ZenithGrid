"""Persist quote-currency fees for fee-net spot P&L."""

from migrations.db_utils import get_migration_connection, is_postgres, safe_add_column


def run():
    conn = get_migration_connection()
    try:
        prefix = "trading." if is_postgres() else ""
        safe_add_column(conn, f"{prefix}trades", "fee_quote FLOAT NOT NULL DEFAULT 0.0")
        safe_add_column(conn, f"{prefix}positions", "entry_fees_quote FLOAT NOT NULL DEFAULT 0.0")
        safe_add_column(conn, f"{prefix}positions", "exit_fees_quote FLOAT NOT NULL DEFAULT 0.0")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
