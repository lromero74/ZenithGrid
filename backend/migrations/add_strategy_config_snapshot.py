"""
Add strategy_config_snapshot column to positions table
This allows each position to freeze the bot's configuration at creation time
"""
import sqlite3
import json
from datetime import datetime

def upgrade():
    """Add strategy_config_snapshot column"""
    conn = sqlite3.connect('trading.db')
    cursor = conn.cursor()

    # Add column (nullable for existing positions)
    cursor.execute("""
        ALTER TABLE positions
        ADD COLUMN strategy_config_snapshot TEXT
    """)

    conn.commit()
    conn.close()
    print("✅ Added strategy_config_snapshot column to positions table")

def rollback():
    """Remove strategy_config_snapshot column"""
    # SQLite doesn't support DROP COLUMN easily
    # Would need to recreate table without the column
    print("⚠️  Manual rollback required for SQLite")
    print("To rollback, you would need to:")
    print("1. Create new table without strategy_config_snapshot column")
    print("2. Copy all data from old table to new table")
    print("3. Drop old table and rename new table")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        upgrade()
