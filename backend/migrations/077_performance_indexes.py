"""
Add missing performance indexes identified in the Big-O audit (2026-04-02).

The following indexes were absent and affect hot-path queries:

- signals(position_id)
    Used by: position detail view — SELECT * FROM signals WHERE position_id = ?
    Without an index this is a full table scan on an ever-growing table.

- order_history(bot_id, timestamp)
    Used by: GET /api/order-history — JOINs on bot_id then sorts by timestamp DESC.
    bot_id had no individual index; status and timestamp were indexed separately
    but a compound index enables the join+sort in a single range scan.

- account_value_snapshots(user_id, snapshot_date)
    Used by: account snapshot aggregation — WHERE user_id = ? GROUP BY snapshot_date.
    Individual indexes on user_id and snapshot_date exist, but the planner cannot
    use both in a GROUP BY covering-index scan without the compound.

Note: positions compound indexes (bot_id, status), (account_id, status) and
(user_id, status, closed_at) were already added in Migration 061.
"""

from migrations.db_utils import get_migration_connection, is_postgres


def _index_exists(conn, index_name):
    """Check whether an index already exists in the database."""
    cursor = conn.cursor()
    try:
        if is_postgres():
            cursor.execute(
                "SELECT 1 FROM pg_indexes WHERE indexname = %s",
                (index_name,)
            )
        else:
            cursor.execute(
                "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
                (index_name,)
            )
        return cursor.fetchone() is not None
    finally:
        cursor.close()


def _create_index(conn, index_name, table, columns):
    """Create an index if it does not already exist.

    Returns True if created, False if it already existed (idempotent).
    """
    if _index_exists(conn, index_name):
        print(f"  Index {index_name} already exists, skipping")
        return False

    col_list = ", ".join(columns)
    cursor = conn.cursor()
    try:
        cursor.execute(f"CREATE INDEX {index_name} ON {table} ({col_list})")
        conn.commit()
        print(f"  Created index {index_name} on {table}({col_list})")
        return True
    except Exception as e:
        conn.rollback()
        print(f"  Failed to create index {index_name}: {e}")
        return False
    finally:
        cursor.close()


def run():
    print("Migration 077: Adding missing performance indexes...")
    conn = get_migration_connection()

    # Table names are unqualified — search_path in PostgreSQL resolves them to
    # the correct schema (trading / reporting).  SQLite has no schemas.
    indexes = [
        (
            "ix_signals_position_id",
            "signals",
            ["position_id"],
        ),
        (
            "ix_order_history_bot_id_timestamp",
            "order_history",
            ["bot_id", "timestamp"],
        ),
        (
            "ix_snapshot_user_date",
            "account_value_snapshots",
            ["user_id", "snapshot_date"],
        ),
    ]

    created = 0
    for index_name, table, columns in indexes:
        if _create_index(conn, index_name, table, columns):
            created += 1

    conn.close()
    print(f"Migration 077 complete: {created} index(es) created")


if __name__ == "__main__":
    run()
