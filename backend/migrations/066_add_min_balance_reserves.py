"""
Add minimum balance reserve columns to accounts table.

Per-currency minimum free balance floors. The rebalancer will top up
currencies that fall below their minimum before running normal
percentage-based rebalancing.
"""

from migrations.db_utils import get_migration_connection, safe_add_column


def run():
    print("Migration 066: Adding min_balance reserve columns to accounts...")
    conn = get_migration_connection()

    columns = [
        "min_balance_usd FLOAT DEFAULT 0.0",
        "min_balance_btc FLOAT DEFAULT 0.0",
        "min_balance_eth FLOAT DEFAULT 0.0",
        "min_balance_usdc FLOAT DEFAULT 0.0",
    ]

    for col_def in columns:
        col_name = col_def.split()[0]
        if safe_add_column(conn, "accounts", col_def):
            print(f"  Added column: {col_name}")
        else:
            print(f"  Column already exists: {col_name}")

    conn.close()
    print("Migration 066 complete")


if __name__ == "__main__":
    run()
