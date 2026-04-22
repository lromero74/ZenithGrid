"""
Migration 082: Speculative Bucket + Calibration Alert Cooldown.

Adds two nullable/defaulted columns to trading.accounts:
- speculative_allocation_pct FLOAT NOT NULL DEFAULT 0.0
  User's chosen % of portfolio allocated to speculative-preset bots.
  Zero (default) means speculative bots are soft-blocked from opening.
- speculative_calibration_last_alerted_at TIMESTAMP NULL
  Last time the user was emailed a signal-weight calibration alert.
  Used by speculative_calibration_monitor to enforce the 30-day cooldown.

Idempotent: safe_add_column skips if the column already exists.
"""

from migrations.db_utils import get_migration_connection, is_postgres, safe_add_column


def run():
    conn = get_migration_connection()
    cur = conn.cursor()
    try:
        if is_postgres():
            _run_postgres(conn)
        else:
            _run_sqlite(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def _run_postgres(conn):
    safe_add_column(
        conn,
        "trading.accounts",
        "speculative_allocation_pct FLOAT NOT NULL DEFAULT 0.0",
    )
    safe_add_column(
        conn,
        "trading.accounts",
        "speculative_calibration_last_alerted_at TIMESTAMP NULL",
    )


def _run_sqlite(conn):
    safe_add_column(
        conn,
        "accounts",
        "speculative_allocation_pct FLOAT NOT NULL DEFAULT 0.0",
    )
    safe_add_column(
        conn,
        "accounts",
        "speculative_calibration_last_alerted_at TIMESTAMP NULL",
    )


if __name__ == "__main__":
    run()
