"""Add webhook_token column to bots for TradingView webhook integration."""

from migrations.db_utils import get_migration_connection, is_postgres, safe_add_column


def run():
    conn = get_migration_connection()
    try:
        prefix = "trading." if is_postgres() else ""
        safe_add_column(conn, f"{prefix}bots", "webhook_token VARCHAR NULL")
        # Add index for fast webhook token lookup
        cursor = conn.cursor()
        try:
            index_name = "ix_bots_webhook_token"
            if is_postgres():
                cursor.execute(
                    "SELECT 1 FROM pg_indexes WHERE indexname = %s",
                    (index_name,),
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
                    (index_name,),
                )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"CREATE INDEX {index_name} ON {prefix}bots (webhook_token)"
                )
                conn.commit()
                print(f"  Created index {index_name}")
            else:
                print(f"  Index {index_name} already exists, skipping")
        finally:
            cursor.close()
    finally:
        conn.close()


if __name__ == "__main__":
    run()
