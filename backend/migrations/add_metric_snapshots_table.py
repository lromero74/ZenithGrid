"""
Migration: Add metric_snapshots table for sparkline chart history

Creates a table to store rolling snapshots of market metrics
(BTC dominance, altseason index, hash rate, etc.) for sparkline display.
"""

import sqlite3
from pathlib import Path


def get_db_path():
    """Get database path relative to script location"""
    backend_dir = Path(__file__).parent.parent
    return backend_dir / "trading.db"


def run_migration():
    """Add metric_snapshots table"""
    db_path = get_db_path()

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return False

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='metric_snapshots'
        """)
        if cursor.fetchone():
            print("metric_snapshots table already exists")
            return True

        # Create table
        cursor.execute("""
            CREATE TABLE metric_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name VARCHAR NOT NULL,
                value FLOAT NOT NULL,
                recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX ix_metric_snapshots_metric_name
            ON metric_snapshots (metric_name)
        """)
        cursor.execute("""
            CREATE INDEX ix_metric_snapshots_recorded_at
            ON metric_snapshots (recorded_at)
        """)
        # Composite index for the common query pattern
        cursor.execute("""
            CREATE INDEX ix_metric_snapshots_name_date
            ON metric_snapshots (metric_name, recorded_at)
        """)

        conn.commit()
        print("Created metric_snapshots table with indexes")
        return True

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
