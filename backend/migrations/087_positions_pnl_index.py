"""
Add positions(account_id, status, closed_at) compound index.

Realized-PnL aggregation (portfolio_service._query_closed_pnl) sums profit_quote
over an account's closed positions, optionally filtered by close time for the
"today" bucket. positions.account_id was indexed alone, so the query found the
account's rows by index then filtered status/closed_at in the heap. The compound
index lets the whole predicate ride the index as a range scan.

The index is also declared on the Position model (__table_args__) so fresh
installs get it via Base.metadata.create_all(); this migration covers existing
databases.

Idempotent: skips if the index already exists.
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


def run():
    print("Migration 087: Adding positions(account_id, status, closed_at) index...")
    conn = get_migration_connection()

    index_name = "ix_positions_account_status_closed"
    if _index_exists(conn, index_name):
        print(f"  Index {index_name} already exists, skipping")
        conn.close()
        return

    cursor = conn.cursor()
    try:
        # Unqualified table name — PostgreSQL search_path resolves it to schema
        # `trading`; SQLite has no schemas.
        cursor.execute(
            f"CREATE INDEX {index_name} ON positions (account_id, status, closed_at)"
        )
        conn.commit()
        print(f"  Created index {index_name}")
    except Exception as e:
        conn.rollback()
        print(f"  Failed to create index {index_name}: {e}")
        raise
    finally:
        cursor.close()
        conn.close()
    print("Migration 087 complete")


if __name__ == "__main__":
    run()
