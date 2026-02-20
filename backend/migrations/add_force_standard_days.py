"""
Migration: Add force_standard_days to report_schedules.

Stores a JSON array of days that should use the standard period window
instead of auto-switching to full prior period. Applies when a report
runs on a period-start day (e.g., 1st of month with MTD, Monday with WTD).
"""

import os
import sqlite3


def migrate():
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "trading.db"
    )
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Add force_standard_days column (idempotent)
    try:
        cursor.execute(
            "ALTER TABLE report_schedules "
            "ADD COLUMN force_standard_days TEXT"
        )
        print("[migration] Added force_standard_days to report_schedules")
    except Exception as e:
        if "duplicate column name" in str(e).lower():
            print("[migration] force_standard_days already exists, skipping")
        else:
            raise

    conn.commit()
    conn.close()


if __name__ == "__main__":
    migrate()
