"""
Migration 067: Add dust sweep fields to accounts table.

Adds columns for automatic dust sweeping:
- dust_sweep_enabled: toggle monthly auto-sweep
- dust_sweep_threshold_usd: minimum USD value to bother sweeping
- dust_last_sweep_at: track monthly cadence
"""

from migrations.db_utils import get_migration_connection, safe_add_column


def run():
    conn = get_migration_connection()
    try:
        safe_add_column(conn, "accounts", "dust_sweep_enabled BOOLEAN DEFAULT FALSE")
        safe_add_column(conn, "accounts", "dust_sweep_threshold_usd FLOAT DEFAULT 5.0")
        safe_add_column(conn, "accounts", "dust_last_sweep_at TIMESTAMP")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
    print("Migration 067 complete: dust sweep fields added.")
