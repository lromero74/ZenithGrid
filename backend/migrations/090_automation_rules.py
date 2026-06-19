"""Add automation_rules table for user-configurable if-then rules."""

from migrations.db_utils import get_migration_connection, is_postgres


def run():
    print("Migration 090: Creating automation_rules table...")
    conn = get_migration_connection()
    try:
        cursor = conn.cursor()
        try:
            if is_postgres():
                cursor.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'trading' AND table_name = 'automation_rules'"
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='automation_rules'"
                )
            if cursor.fetchone() is not None:
                print("  Table automation_rules already exists, skipping")
                return

            if is_postgres():
                cursor.execute("""
                    CREATE TABLE trading.automation_rules (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES auth.users(id),
                        account_id INTEGER NOT NULL REFERENCES trading.accounts(id),
                        name VARCHAR NOT NULL,
                        description TEXT,
                        trigger_type VARCHAR NOT NULL,
                        trigger_config JSON NOT NULL,
                        action_type VARCHAR NOT NULL,
                        action_config JSON,
                        enabled BOOLEAN DEFAULT TRUE,
                        last_fired_at TIMESTAMP,
                        fire_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                cursor.execute(
                    "CREATE INDEX ix_automation_rules_user_id "
                    "ON trading.automation_rules (user_id)"
                )
                cursor.execute(
                    "CREATE INDEX ix_automation_rules_account_id "
                    "ON trading.automation_rules (account_id)"
                )
            else:
                cursor.execute("""
                    CREATE TABLE automation_rules (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        account_id INTEGER NOT NULL,
                        name VARCHAR NOT NULL,
                        description TEXT,
                        trigger_type VARCHAR NOT NULL,
                        trigger_config JSON NOT NULL,
                        action_type VARCHAR NOT NULL,
                        action_config JSON,
                        enabled BOOLEAN DEFAULT 1,
                        last_fired_at TIMESTAMP,
                        fire_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute(
                    "CREATE INDEX ix_automation_rules_user_id "
                    "ON automation_rules (user_id)"
                )
                cursor.execute(
                    "CREATE INDEX ix_automation_rules_account_id "
                    "ON automation_rules (account_id)"
                )
            conn.commit()
            print("  Created table automation_rules")
        finally:
            cursor.close()
    finally:
        conn.close()
    print("Migration 090 complete")


if __name__ == "__main__":
    run()
