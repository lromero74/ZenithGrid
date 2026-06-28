"""
Add trigger_reason column to trades table.

Human-readable reason an order fired, captured at execution time (entry signal,
safety-order price deviation, exit reason). Surfaced in the position Decision
History. Nullable — existing trades keep NULL and the UI derives a reason.
"""

from migrations.db_utils import get_migration_connection, safe_add_column


def run():
    print("Migration 095: Adding trigger_reason to trades...")
    conn = get_migration_connection()

    if safe_add_column(conn, "trades", "trigger_reason TEXT"):
        print("  Added column: trigger_reason")
    else:
        print("  Column already exists: trigger_reason")

    conn.close()
    print("Migration 095 complete")


if __name__ == "__main__":
    run()
