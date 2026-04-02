"""
Add retention_count and retention_days columns to report_schedules.

Implements a per-schedule retention policy:
- retention_count (nullable int): keep only the last N reports
- retention_days  (nullable int): delete reports older than N days

Both null = keep forever (existing behaviour, no data change).
If both are set, a report is deleted only when BOTH limits are exceeded.
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from migrations.db_utils import get_migration_connection, safe_add_column  # noqa: E402


def run():
    print("Migration 079: Adding retention columns to report_schedules...")
    conn = get_migration_connection()

    columns = [
        "retention_count INTEGER",
        "retention_days INTEGER",
    ]

    for col_def in columns:
        col_name = col_def.split()[0]
        if safe_add_column(conn, "reporting.report_schedules", col_def):
            print(f"  Added column: {col_name}")
        else:
            print(f"  Column already exists: {col_name}")

    conn.close()
    print("Migration 079 complete")


if __name__ == "__main__":
    run()
