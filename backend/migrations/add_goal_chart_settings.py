"""
Migration: Add chart display settings to report_goals.

Adds chart_horizon, show_minimap, and minimap_threshold_days columns
for configurable chart horizon and minimap rendering.
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
        ("show_minimap", "INTEGER DEFAULT 1"),
        ("minimap_threshold_days", "INTEGER DEFAULT 90"),
    ]

    for col_name, col_def in columns:
        try:
            cursor.execute(
                f"ALTER TABLE report_goals ADD COLUMN {col_name} {col_def}"
            )
            print(f"  Added column: {col_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"  Column {col_name} already exists, skipping")
            else:
                raise

    conn.commit()
    conn.close()
    print("Migration complete: add_goal_chart_settings")


if __name__ == "__main__":
    run_migration()
