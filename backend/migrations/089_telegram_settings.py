"""Add telegram_settings table for per-user Telegram notification config."""

from migrations.db_utils import get_migration_connection, is_postgres


def run():
    print("Migration 089: Creating telegram_settings table...")
    conn = get_migration_connection()
    try:
        cursor = conn.cursor()
        try:
            if is_postgres():
                # Check if table exists in the system schema
                cursor.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'system' AND table_name = 'telegram_settings'"
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='telegram_settings'"
                )
            if cursor.fetchone() is not None:
                print("  Table telegram_settings already exists, skipping")
                return

            if is_postgres():
                cursor.execute("""
                    CREATE TABLE system.telegram_settings (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
                        bot_token VARCHAR NOT NULL,
                        chat_id VARCHAR NOT NULL,
                        notify_order_filled BOOLEAN DEFAULT TRUE,
                        notify_position_opened BOOLEAN DEFAULT TRUE,
                        notify_position_closed BOOLEAN DEFAULT TRUE,
                        notify_bot_started BOOLEAN DEFAULT TRUE,
                        notify_bot_stopped BOOLEAN DEFAULT TRUE,
                        commands_enabled BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW(),
                        CONSTRAINT uq_telegram_settings_user UNIQUE (user_id)
                    )
                """)
                cursor.execute(
                    "CREATE INDEX ix_telegram_settings_user_id "
                    "ON system.telegram_settings (user_id)"
                )
            else:
                cursor.execute("""
                    CREATE TABLE telegram_settings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        bot_token VARCHAR NOT NULL,
                        chat_id VARCHAR NOT NULL,
                        notify_order_filled BOOLEAN DEFAULT 1,
                        notify_position_opened BOOLEAN DEFAULT 1,
                        notify_position_closed BOOLEAN DEFAULT 1,
                        notify_bot_started BOOLEAN DEFAULT 1,
                        notify_bot_stopped BOOLEAN DEFAULT 1,
                        commands_enabled BOOLEAN DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT uq_telegram_settings_user UNIQUE (user_id)
                    )
                """)
                cursor.execute(
                    "CREATE INDEX ix_telegram_settings_user_id "
                    "ON telegram_settings (user_id)"
                )
            conn.commit()
            print("  Created table telegram_settings")
        finally:
            cursor.close()
    finally:
        conn.close()
    print("Migration 089 complete")


if __name__ == "__main__":
    run()
