"""
Add rebalance_min_trade_pct column to accounts table.

User-configurable minimum trade size as a percentage of portfolio value.
Replaces the USD-based minimum which didn't scale with portfolio size.
"""

from migrations.db_utils import get_migration_connection, safe_add_column


def run():
    print("Migration 064: Adding rebalance_min_trade_pct to accounts...")
    conn = get_migration_connection()

    if safe_add_column(conn, "accounts", "rebalance_min_trade_pct FLOAT DEFAULT 5.0"):
        print("  Added column: rebalance_min_trade_pct")
    else:
        print("  Column already exists: rebalance_min_trade_pct")

    conn.close()
    print("Migration 064 complete")


if __name__ == "__main__":
    run()
