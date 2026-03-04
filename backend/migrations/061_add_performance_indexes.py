"""
Add performance indexes for hot-path queries.

Addresses missing indexes on frequently-queried columns identified
in the Big O performance audit (2026-03-03):
- positions(bot_id, status) — queried every bot cycle
- positions(account_id, status) — queried every position API call
- positions(user_id, status, closed_at) — queried by report range queries
- trades(position_id) — queried per position detail
- bots(account_id) — queried by list_accounts bot counts
"""

from migrations.db_utils import get_migration_connection, is_postgres


def _index_exists(conn, index_name):
    """Check if an index already exists (idempotent)."""
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
    """Create an index if it doesn't already exist."""
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
    print("Migration 061: Adding performance indexes...")
    conn = get_migration_connection()

    indexes = [
        ("ix_positions_bot_id_status", "positions", ["bot_id", "status"]),
        ("ix_positions_account_id_status", "positions", ["account_id", "status"]),
        ("ix_positions_user_status_closed_at", "positions", ["user_id", "status", "closed_at"]),
        ("ix_trades_position_id", "trades", ["position_id"]),
        ("ix_bots_account_id", "bots", ["account_id"]),
    ]

    created = 0
    for index_name, table, columns in indexes:
        if _create_index(conn, index_name, table, columns):
            created += 1

    conn.close()
    print(f"Migration 061 complete: {created} indexes created")


if __name__ == "__main__":
    run()
