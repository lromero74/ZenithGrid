"""
Add rebalance_target_usdc_pct column to accounts table.

Adds USDC as a 4th rebalanceable asset alongside USD, BTC, and ETH.
Defaults to 0% so existing allocations are unaffected.
"""

from migrations.db_utils import get_migration_connection, safe_add_column


def run():
    print("Migration 065: Adding rebalance_target_usdc_pct to accounts...")
    conn = get_migration_connection()

    if safe_add_column(conn, "accounts", "rebalance_target_usdc_pct FLOAT DEFAULT 0.0"):
        print("  Added column: rebalance_target_usdc_pct")
    else:
        print("  Column already exists: rebalance_target_usdc_pct")

    conn.close()
    print("Migration 065 complete")


if __name__ == "__main__":
    run()
