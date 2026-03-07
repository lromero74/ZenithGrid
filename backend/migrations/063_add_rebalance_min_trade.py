"""
Add rebalance_min_trade_usd column to accounts table.

User-configurable minimum trade size for portfolio rebalancing.
"""

from migrations.db_utils import get_migration_connection, safe_add_column


def run():
    print("Migration 063: Adding rebalance_min_trade_usd to accounts...")
    conn = get_migration_connection()

    if safe_add_column(conn, "accounts", "rebalance_min_trade_usd FLOAT DEFAULT 50.0"):
        print("  Added column: rebalance_min_trade_usd")
    else:
        print("  Column already exists: rebalance_min_trade_usd")

    conn.close()
    print("Migration 063 complete")


if __name__ == "__main__":
    run()
