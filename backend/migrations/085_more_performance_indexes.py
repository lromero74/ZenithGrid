"""
Add compound indexes for hot-path position queries (2026-06 optimization pass).

- trades(position_id, timestamp)
    Used by: position detail view — trades are filtered by position_id and
    ordered by timestamp (first/last buy price, trade history). position_id
    alone was indexed; the compound lets the sort ride the index.

- pending_orders(position_id, status)
    Used by: position list/detail — pending-order counts filter by
    position_id(s) AND status='pending'. position_id had NO index at all,
    so these were full table scans.

These indexes are also declared on the models (Trade / PendingOrder
__table_args__) so fresh installs get them via Base.metadata.create_all();
this migration covers existing databases.
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
    print("Migration 085: Adding compound indexes for position queries...")
    conn = get_migration_connection()

    # Table names are unqualified — search_path in PostgreSQL resolves them to
    # the correct schema (trading).  SQLite has no schemas.
    indexes = [
        (
            "ix_trades_position_timestamp",
            "trades",
            ["position_id", "timestamp"],
        ),
        (
            "ix_pending_orders_position_status",
            "pending_orders",
            ["position_id", "status"],
        ),
    ]

    created = 0
    for index_name, table, columns in indexes:
        if _create_index(conn, index_name, table, columns):
            created += 1

    conn.close()
    print(f"Migration 085 complete: {created} index(es) created")


if __name__ == "__main__":
    run()
