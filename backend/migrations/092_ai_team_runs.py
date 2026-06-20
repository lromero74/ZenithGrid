"""Add ai_team_runs table for AI-team orchestrator audit trail."""

from migrations.db_utils import get_migration_connection, is_postgres


def run():
    print("Migration 092: Creating ai_team_runs table...")
    conn = get_migration_connection()
    try:
        cursor = conn.cursor()
        try:
            if is_postgres():
                cursor.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'trading' AND table_name = 'ai_team_runs'"
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ai_team_runs'"
                )
            if cursor.fetchone() is not None:
                print("  Table ai_team_runs already exists, skipping")
                return

            if is_postgres():
                cursor.execute("""
                    CREATE TABLE trading.ai_team_runs (
                        id SERIAL PRIMARY KEY,
                        account_id INTEGER NOT NULL
                            REFERENCES trading.accounts(id) ON DELETE CASCADE,
                        bot_id INTEGER
                            REFERENCES trading.bots(id) ON DELETE SET NULL,
                        product_id VARCHAR NOT NULL,
                        signal_output JSON,
                        bull_output JSON,
                        bear_output JSON,
                        verdict_output JSON,
                        plan_output JSON,
                        final_action VARCHAR NOT NULL DEFAULT 'hold',
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                cursor.execute(
                    "CREATE INDEX ix_ai_team_runs_account_id "
                    "ON trading.ai_team_runs (account_id)"
                )
                cursor.execute(
                    "CREATE INDEX ix_ai_team_runs_bot_id "
                    "ON trading.ai_team_runs (bot_id)"
                )
                cursor.execute(
                    "CREATE INDEX ix_ai_team_runs_product_id "
                    "ON trading.ai_team_runs (product_id)"
                )
                cursor.execute(
                    "CREATE INDEX ix_ai_team_runs_created_at "
                    "ON trading.ai_team_runs (created_at)"
                )
            else:
                cursor.execute("""
                    CREATE TABLE ai_team_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        account_id INTEGER NOT NULL,
                        bot_id INTEGER,
                        product_id VARCHAR NOT NULL,
                        signal_output JSON,
                        bull_output JSON,
                        bear_output JSON,
                        verdict_output JSON,
                        plan_output JSON,
                        final_action VARCHAR NOT NULL DEFAULT 'hold',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute(
                    "CREATE INDEX ix_ai_team_runs_account_id "
                    "ON ai_team_runs (account_id)"
                )
                cursor.execute(
                    "CREATE INDEX ix_ai_team_runs_bot_id "
                    "ON ai_team_runs (bot_id)"
                )
                cursor.execute(
                    "CREATE INDEX ix_ai_team_runs_product_id "
                    "ON ai_team_runs (product_id)"
                )
                cursor.execute(
                    "CREATE INDEX ix_ai_team_runs_created_at "
                    "ON ai_team_runs (created_at)"
                )
            conn.commit()
            print("  Created table ai_team_runs")
        finally:
            cursor.close()
    finally:
        conn.close()
    print("Migration 092 complete")


if __name__ == "__main__":
    run()
