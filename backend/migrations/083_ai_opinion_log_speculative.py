"""
Migration 083: Speculative scorer fields on ai_opinion_log.

Phase F of the high-risk-doubling preset needs per-call persistence of the
speculative scorer output so speculative_calibration_monitor can compare
per-component win rates across closed positions.

Adds three nullable columns:
- doubling_probability_score  INTEGER NULL
    LLM's explicit 0-100 estimate of hitting the target multiple in the
    target horizon. Null on non-speculative evaluations and on classic-mode
    calls that never asked for the score.
- speculative_score           INTEGER NULL
    Deterministic 0-100 score from speculative_signals.score_speculative_setup.
- speculative_components      JSON NULL
    List of [name, fired, contribution] triples from components_for_log —
    the calibration monitor groups by name to compute component-level
    win rates.

Idempotent via safe_add_column.
"""

from migrations.db_utils import get_migration_connection, is_postgres, safe_add_column


def run():
    print("Migration 083: Adding speculative scorer columns to ai_opinion_log...")
    conn = get_migration_connection()
    try:
        if is_postgres():
            _run_postgres(conn)
        else:
            _run_sqlite(conn)
        conn.commit()
        print("Migration 083 complete")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _run_postgres(conn):
    table = "trading.ai_opinion_log"
    safe_add_column(conn, table, "doubling_probability_score INTEGER NULL")
    safe_add_column(conn, table, "speculative_score INTEGER NULL")
    safe_add_column(conn, table, "speculative_components JSONB NULL")


def _run_sqlite(conn):
    table = "ai_opinion_log"
    safe_add_column(conn, table, "doubling_probability_score INTEGER NULL")
    safe_add_column(conn, table, "speculative_score INTEGER NULL")
    safe_add_column(conn, table, "speculative_components TEXT NULL")


if __name__ == "__main__":
    run()
