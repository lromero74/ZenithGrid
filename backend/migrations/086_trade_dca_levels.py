"""
Add trades.dca_levels — number of safety-order levels a trade deployed.

A "cascade" fills several safety-order levels in a SINGLE order when price drops
past multiple trigger levels between evaluations. Counting completed safety
orders by trade rows (len(buy_trades) - 1) therefore under-reports, and the
engine could re-place an already-deployed level. dca_levels records how many SO
levels each trade covers (1 for normal trades, >1 for cascades); the deployed
count is then the sum of dca_levels minus the base order.

The column is also declared on the Trade model, so fresh installs get it via
Base.metadata.create_all(); this migration covers existing databases.

Existing rows default to 1. Historical cascade trades are NOT auto-detected
(their level count can't be reliably reverse-engineered); only trades recorded
after this change carry an accurate count.

Idempotent: skips if the column already exists.
"""

from migrations.db_utils import get_migration_connection, is_postgres


def _column_exists(conn, table, column):
    cursor = conn.cursor()
    try:
        if is_postgres():
            cursor.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = %s AND column_name = %s",
                (table, column),
            )
            return cursor.fetchone() is not None
        cursor.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cursor.fetchall())
    finally:
        cursor.close()


def run():
    print("Migration 086: Adding trades.dca_levels...")
    conn = get_migration_connection()

    if _column_exists(conn, "trades", "dca_levels"):
        print("  Column trades.dca_levels already exists, skipping")
        conn.close()
        return

    cursor = conn.cursor()
    try:
        # Unqualified table name — PostgreSQL search_path resolves it to schema
        # `trading`; SQLite has no schemas. NOT NULL DEFAULT 1 backfills existing
        # rows in a single statement on both engines.
        cursor.execute(
            "ALTER TABLE trades ADD COLUMN dca_levels INTEGER NOT NULL DEFAULT 1"
        )
        conn.commit()
        print("  Added column trades.dca_levels (default 1)")
    except Exception as e:
        conn.rollback()
        print(f"  Failed to add trades.dca_levels: {e}")
        raise
    finally:
        cursor.close()
        conn.close()
    print("Migration 086 complete")


if __name__ == "__main__":
    run()
