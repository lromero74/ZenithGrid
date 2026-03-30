"""
Migration 073: Backfill last_started_at for bots that were active when migration 072 ran

Migration 072 added last_started_at and total_running_seconds columns with NULL/0 defaults
on all existing rows, including bots that were already active at that moment.

Any bot that was is_active=True with last_started_at=NULL never had its session start
recorded. When the user stops such a bot, stop_bot() sees last_started_at=None and skips
accumulation — so total_running_seconds stays at 0 and Days Active resets to 0 on the
next start/stop cycle.

Fix: for every currently-active bot where last_started_at IS NULL, use updated_at as a
best-effort proxy for when the run session began. This isn't perfectly accurate (updated_at
also changes on config edits), but it's far better than NULL — the next stop will
accumulate at least some meaningful elapsed time, and all subsequent start/stop cycles will
track exactly.

Idempotent: only touches rows where is_active=TRUE AND last_started_at IS NULL.
"""

import logging
from migrations.db_utils import get_migration_connection, is_postgres

logger = logging.getLogger(__name__)


def run():
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


def _run_postgres(cur):
    cur.execute("""
        UPDATE trading.bots
        SET last_started_at = updated_at
        WHERE is_active = TRUE
          AND last_started_at IS NULL
          AND updated_at IS NOT NULL
    """)
    print(f"[073] Backfilled last_started_at for {cur.rowcount} active bot(s) (PostgreSQL)")


def _run_sqlite(cur):
    cur.execute("""
        UPDATE bots
        SET last_started_at = updated_at
        WHERE is_active = 1
          AND last_started_at IS NULL
          AND updated_at IS NOT NULL
    """)
    print(f"[073] Backfilled last_started_at for {cur.rowcount} active bot(s) (SQLite)")


if __name__ == "__main__":
    run()
