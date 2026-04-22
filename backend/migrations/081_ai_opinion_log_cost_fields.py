"""
Migration 081: Add cost-tracking columns to ai_opinion_log.

Phase F of ai-multi-provider-tools PRP adds per-call cost accounting so users
can see how much their AI bots spend per provider / per model. New columns:

- model_used     : the specific SDK model string (e.g. 'claude-sonnet-4-20250514').
                   Distinct from the existing 'ai_model' column which holds the
                   provider slug ('claude' | 'gpt' | 'gemini').
- input_tokens   : total input tokens summed across every turn of the tool loop.
- output_tokens  : total output tokens summed across every turn of the tool loop.
- cost_usd       : computed at write time from tokens * pricing table. Stored so
                   the dashboard doesn't have to re-apply prices on every query.

Idempotent via safe_add_column; re-runs are no-ops.
"""

from migrations.db_utils import get_migration_connection, is_postgres, safe_add_column


def run():
    print("Migration 081: Adding cost-tracking columns to ai_opinion_log...")
    conn = get_migration_connection()
    try:
        table = "trading.ai_opinion_log" if is_postgres() else "ai_opinion_log"
        pricing_numeric = "DOUBLE PRECISION" if is_postgres() else "REAL"
        columns = [
            "model_used VARCHAR(80)",
            "input_tokens INTEGER DEFAULT 0",
            "output_tokens INTEGER DEFAULT 0",
            f"cost_usd {pricing_numeric} DEFAULT 0.0",
        ]
        added = 0
        for col_def in columns:
            if safe_add_column(conn, table, col_def):
                col_name = col_def.split()[0]
                print(f"  Added column: {col_name}")
                added += 1
        conn.commit()
        print(f"Migration 081 complete: {added} columns added")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run()
