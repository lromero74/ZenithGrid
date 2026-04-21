"""
Migration 080: ai_opinion_log — per-call audit log of AI indicator decisions.

Creates trading.ai_opinion_log for Phase D of the AI multi-provider tool-use
upgrade. Writes a row after every successful `AISpotOpinionEvaluator.evaluate()`
call; outcome fields are backfilled on POSITION_CLOSED.

Schema follows PRPs/ai-multi-provider-tools.md § Phase D "Migration".

Idempotent on both PostgreSQL and SQLite via CREATE TABLE IF NOT EXISTS /
CREATE INDEX IF NOT EXISTS.
"""

from migrations.db_utils import get_migration_connection, is_postgres


def run():
    print("Migration 080: Creating ai_opinion_log table...")
    conn = get_migration_connection()
    cur = conn.cursor()

    try:
        if is_postgres():
            _run_postgres(cur)
        else:
            _run_sqlite(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    print("Migration 080 complete")


def _run_postgres(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trading.ai_opinion_log (
            id                  SERIAL PRIMARY KEY,
            user_id             INTEGER NOT NULL
                REFERENCES auth.users(id) ON DELETE CASCADE,
            account_id          INTEGER
                REFERENCES trading.accounts(id) ON DELETE SET NULL,
            bot_id              INTEGER
                REFERENCES trading.bots(id) ON DELETE SET NULL,
            position_id         INTEGER
                REFERENCES trading.positions(id) ON DELETE SET NULL,
            product_id          VARCHAR(40) NOT NULL,
            is_sell_check       BOOLEAN NOT NULL DEFAULT FALSE,
            signal              VARCHAR(10) NOT NULL,
            confidence          INTEGER NOT NULL DEFAULT 0,
            reasoning           TEXT,
            ai_model            VARCHAR(20),
            tool_calls          JSONB,
            created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            outcome             VARCHAR(10),
            realized_pnl_pct    DOUBLE PRECISION,
            closed_at           TIMESTAMP
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_opinion_log_user_product_created "
        "ON trading.ai_opinion_log(user_id, product_id, created_at DESC)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_opinion_log_position "
        "ON trading.ai_opinion_log(position_id)"
    )

    # Grant privileges to app role (pattern from migration 069)
    app_role = "zenithgrid_app"
    cur.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE "
        f"ON trading.ai_opinion_log TO {app_role}"
    )
    cur.execute(
        f"GRANT USAGE, SELECT ON SEQUENCE trading.ai_opinion_log_id_seq TO {app_role}"
    )


def _run_sqlite(cur):
    """SQLite — flat namespace, no sequences, JSON stored as TEXT."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ai_opinion_log (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             INTEGER NOT NULL,
            account_id          INTEGER,
            bot_id              INTEGER,
            position_id         INTEGER,
            product_id          VARCHAR(40) NOT NULL,
            is_sell_check       BOOLEAN NOT NULL DEFAULT 0,
            signal              VARCHAR(10) NOT NULL,
            confidence          INTEGER NOT NULL DEFAULT 0,
            reasoning           TEXT,
            ai_model            VARCHAR(20),
            tool_calls          TEXT,
            created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            outcome             VARCHAR(10),
            realized_pnl_pct    REAL,
            closed_at           TIMESTAMP
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_opinion_log_user_product_created "
        "ON ai_opinion_log(user_id, product_id, created_at DESC)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_opinion_log_position "
        "ON ai_opinion_log(position_id)"
    )


if __name__ == "__main__":
    run()
