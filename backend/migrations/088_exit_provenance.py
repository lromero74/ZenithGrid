"""Add durable exit provenance to positions."""

from migrations.db_utils import get_migration_connection, is_postgres, safe_add_column


def run():
    conn = get_migration_connection()
    try:
        table = "trading.positions" if is_postgres() else "positions"
        for column in (
            "exit_source VARCHAR(32)", "exit_trigger_reason TEXT", "exit_process_role VARCHAR(32)",
            "exit_hostname VARCHAR(255)", "exit_order_id VARCHAR(255)",
        ):
            safe_add_column(conn, table, column)
    finally:
        conn.close()


if __name__ == "__main__":
    run()
