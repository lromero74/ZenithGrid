"""
Add portfolio rebalancing columns to accounts table.

Allows per-account target allocation percentages for USD, BTC, and ETH
with configurable drift threshold and check interval.
"""

from migrations.db_utils import get_migration_connection, safe_add_column


def run():
    print("Migration 062: Adding rebalance columns to accounts...")
    conn = get_migration_connection()

    columns = [
        "rebalance_enabled BOOLEAN DEFAULT FALSE",
        "rebalance_target_usd_pct FLOAT DEFAULT 34.0",
        "rebalance_target_btc_pct FLOAT DEFAULT 33.0",
        "rebalance_target_eth_pct FLOAT DEFAULT 33.0",
        "rebalance_drift_threshold_pct FLOAT DEFAULT 5.0",
        "rebalance_check_interval_minutes INTEGER DEFAULT 60",
    ]

    added = 0
    for col_def in columns:
        if safe_add_column(conn, "accounts", col_def):
            col_name = col_def.split()[0]
            print(f"  Added column: {col_name}")
            added += 1

    conn.close()
    print(f"Migration 062 complete: {added} columns added")


if __name__ == "__main__":
    run()
