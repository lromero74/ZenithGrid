"""
Migration: Add chart display settings to report_schedules.

Adds chart_horizon and chart_lookahead_multiplier columns so chart
look-ahead can be configured per schedule (multiplier × period days).
"""

import sqlite3
from pathlib import Path


def get_db_path():
    """Get database path relative to script location."""
    backend_dir = Path(__file__).parent.parent
    return backend_dir / "trading.db"


def run_migration():
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    columns = [
        ("chart_horizon", "TEXT DEFAULT 'auto'"),
        ("chart_lookahead_multiplier", "REAL DEFAULT 1.0"),
    ]

    for col_name, col_def in columns:
        try:
            cursor.execute(
                f"ALTER TABLE report_schedules ADD COLUMN {col_name} {col_def}"
            )
            print(f"  Added column: {col_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"  Column {col_name} already exists, skipping")
            else:
                raise

    conn.commit()
    conn.close()
    print("Migration complete: add_schedule_chart_settings")


if __name__ == "__main__":
    run_migration()
