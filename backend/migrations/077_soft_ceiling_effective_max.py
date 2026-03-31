"""
Migration 077: Add soft_ceiling_effective_max to trading.bots.

Stores the last computed soft-ceiling deal cap so the bot list can display it
without re-running the full calculation on every page load.
Nullable — NULL means the bot either has SC disabled or hasn't run a signal cycle yet.
Idempotent via safe_add_column.
"""

from migrations.db_utils import get_migration_connection, is_postgres, safe_add_column


def run():
    conn = get_migration_connection()
    try:
        if is_postgres():
            safe_add_column(conn, "trading.bots", "soft_ceiling_effective_max INTEGER")
        else:
            safe_add_column(conn, "bots", "soft_ceiling_effective_max INTEGER")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run()
