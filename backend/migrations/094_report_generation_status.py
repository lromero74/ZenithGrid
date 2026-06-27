"""Add generation lifecycle columns to reports (async manual generation).

Manual report generation became asynchronous: ``POST /api/reports/generate`` now
creates a ``pending`` report row and returns immediately while a background task
renders the AI summary + PDF, flipping the row to ``complete`` (or ``failed``).
This adds the two columns that track that lifecycle.

Idempotent and DB-agnostic:
- ``generation_status`` is ``NOT NULL DEFAULT 'complete'`` so every pre-existing
  row (all scheduler/synchronous reports) backfills to ``complete`` automatically.
- ``generation_error`` holds the failure reason for failed runs.
"""

from migrations.db_utils import get_migration_connection, is_postgres, safe_add_column


def run():
    conn = get_migration_connection()
    try:
        prefix = "reporting." if is_postgres() else ""
        table = f"{prefix}reports"
        added_status = safe_add_column(
            conn, table, "generation_status VARCHAR NOT NULL DEFAULT 'complete'"
        )
        added_error = safe_add_column(conn, table, "generation_error TEXT")
        if added_status or added_error:
            print("  Added report generation lifecycle columns")
        else:
            print("  report generation columns already present — skipping")
    finally:
        conn.close()
