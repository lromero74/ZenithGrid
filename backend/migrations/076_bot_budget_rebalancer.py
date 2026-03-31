"""
Migration 076: Bot Budget Rebalancer.

Adds two new columns to trading.bots and creates trading.bot_rebalancer_groups.
Idempotent: safe_add_column + CREATE TABLE IF NOT EXISTS.
"""

from migrations.db_utils import get_migration_connection, is_postgres, safe_add_column


def run():
    conn = get_migration_connection()
    cur = conn.cursor()
    try:
        if is_postgres():
            _run_postgres(cur, conn)
        else:
            _run_sqlite(cur, conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def _run_postgres(cur, conn):
    safe_add_column(conn, "trading.bots", "bot_rebalancer_enabled BOOLEAN NOT NULL DEFAULT FALSE")
    safe_add_column(conn, "trading.bots", "bot_rebalancer_target_pct FLOAT NOT NULL DEFAULT 0.0")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS trading.bot_rebalancer_groups (
            id                          SERIAL PRIMARY KEY,
            account_id                  INTEGER NOT NULL
                REFERENCES trading.accounts(id) ON DELETE CASCADE,
            base_currency               VARCHAR(20) NOT NULL,
            max_total_pct               FLOAT NOT NULL DEFAULT 100.0,
            overweight_tolerance_pct    FLOAT NOT NULL DEFAULT 5.0,
            enabled                     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at                  TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_rebalancer_group UNIQUE (account_id, base_currency)
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_rebalancer_groups_account "
        "ON trading.bot_rebalancer_groups(account_id)"
    )

    app_role = "zenithgrid_app"
    cur.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE "
        f"ON trading.bot_rebalancer_groups TO {app_role}"
    )
    cur.execute(
        f"GRANT USAGE, SELECT ON SEQUENCE trading.bot_rebalancer_groups_id_seq TO {app_role}"
    )


def _run_sqlite(cur, conn):
    safe_add_column(conn, "bots", "bot_rebalancer_enabled BOOLEAN NOT NULL DEFAULT 0")
    safe_add_column(conn, "bots", "bot_rebalancer_target_pct FLOAT NOT NULL DEFAULT 0.0")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_rebalancer_groups (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id                  INTEGER NOT NULL,
            base_currency               VARCHAR(20) NOT NULL,
            max_total_pct               FLOAT NOT NULL DEFAULT 100.0,
            overweight_tolerance_pct    FLOAT NOT NULL DEFAULT 5.0,
            enabled                     BOOLEAN NOT NULL DEFAULT 1,
            created_at                  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (account_id, base_currency)
        )
    """)
