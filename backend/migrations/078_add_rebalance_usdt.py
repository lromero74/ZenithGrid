"""
Add rebalance_target_usdt_pct and min_balance_usdt columns to accounts table.

Separates USDT from USDC in rebalancing logic, treating it as its own
asset with separate targets and reserves.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from migrations.db_utils import get_migration_connection, safe_add_column


def run():
    print("Migration 078: Adding USDT rebalance and reserve columns to accounts...")
    conn = get_migration_connection()

    columns = [
        "rebalance_target_usdt_pct FLOAT DEFAULT 0.0",
        "min_balance_usdt FLOAT DEFAULT 0.0",
    ]

    for col_def in columns:
        col_name = col_def.split()[0]
        if safe_add_column(conn, "accounts", col_def):
            print(f"  Added column: {col_name}")
        else:
            print(f"  Column already exists: {col_name}")

    conn.close()
    print("Migration 078 complete")


if __name__ == "__main__":
    run()
