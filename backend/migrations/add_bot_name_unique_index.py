"""
Migration: Add unique index on bots.name column

The SQLAlchemy model declares unique=True on Bot.name but the actual
SQLite table was created without this constraint. This migration adds
a unique index to enforce bot name uniqueness at the database level.
"""

import sqlite3
from pathlib import Path


def get_db_path():
    """Get database path relative to script location"""
    backend_dir = Path(__file__).parent.parent
    return backend_dir / "trading.db"


def run_migration():
    """Add unique index on bots.name"""
    db_path = get_db_path()

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return False

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check if unique index already exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='ix_bots_name'"
        )
        if cursor.fetchone():
            print("  Unique index ix_bots_name already exists, skipping")
            return True

        # Check for duplicate names before creating unique index
        cursor.execute(
            "SELECT name, COUNT(*) as cnt FROM bots GROUP BY name HAVING cnt > 1"
        )
        duplicates = cursor.fetchall()
        if duplicates:
            print("  WARNING: Duplicate bot names found, deduplicating before adding unique index:")
            for name, count in duplicates:
                print(f"    '{name}' appears {count} times")
                # Rename duplicates by appending a suffix
                cursor.execute("SELECT id FROM bots WHERE name = ? ORDER BY id", (name,))
                ids = [row[0] for row in cursor.fetchall()]
                for i, bot_id in enumerate(ids[1:], start=2):
                    new_name = f"{name} ({i})"
                    cursor.execute("UPDATE bots SET name = ? WHERE id = ?", (new_name, bot_id))
                    print(f"    Renamed bot id={bot_id} to '{new_name}'")

        # Create unique index
        cursor.execute("CREATE UNIQUE INDEX ix_bots_name ON bots (name)")
        conn.commit()
        print("  Added unique index ix_bots_name on bots.name")
        return True

    except Exception as e:
        print(f"  Migration error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
