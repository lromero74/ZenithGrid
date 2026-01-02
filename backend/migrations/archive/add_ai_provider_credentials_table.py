"""
Migration: Add ai_provider_credentials table for per-user AI API keys

This allows each user to have their own AI provider credentials (Claude, Gemini, Grok, Groq, OpenAI)
for their trading bots. The .env file keys remain as system-wide fallback for services like
news analysis and coin categorization.
"""

import os
import sqlite3
from pathlib import Path


def run_migration():
    """Add ai_provider_credentials table for storing user AI API keys"""
    db_path = Path(__file__).parent.parent / "trading.db"

    print(f"Running migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='ai_provider_credentials'
        """)
        if cursor.fetchone():
            print("Table 'ai_provider_credentials' already exists, skipping...")
            return

        # Create ai_provider_credentials table
        cursor.execute("""
            CREATE TABLE ai_provider_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                api_key TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_used_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX ix_ai_provider_credentials_user_id
            ON ai_provider_credentials (user_id)
        """)
        cursor.execute("""
            CREATE INDEX ix_ai_provider_credentials_provider
            ON ai_provider_credentials (provider)
        """)
        # Unique constraint: one key per provider per user
        cursor.execute("""
            CREATE UNIQUE INDEX ix_ai_provider_credentials_user_provider
            ON ai_provider_credentials (user_id, provider)
        """)

        conn.commit()
        print("Migration completed successfully!")
        print("   - Created ai_provider_credentials table")
        print("   - Added indexes for user_id, provider")
        print("   - Added unique constraint on (user_id, provider)")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


def migrate_env_keys_to_database(user_id: int = 1):
    """
    Migrate API keys from .env file to database for a specific user.

    This is a one-time migration helper. After running, the keys will be
    in the database and the .env values become system-wide fallback only.

    Args:
        user_id: The user ID to assign the keys to (default: 1, first user)
    """
    db_path = Path(__file__).parent.parent / "trading.db"
    env_path = Path(__file__).parent.parent / ".env"

    print(f"Migrating API keys from {env_path} to database for user_id={user_id}")

    # Read .env file
    env_vars = {}
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()

    # Map env var names to provider names
    provider_map = {
        'ANTHROPIC_API_KEY': 'claude',
        'GEMINI_API_KEY': 'gemini',
        'GROK_API_KEY': 'grok',
        'GROQ_API_KEY': 'groq',
        'OPENAI_API_KEY': 'openai',
    }

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        migrated = []
        for env_key, provider in provider_map.items():
            api_key = env_vars.get(env_key, '')
            if api_key:
                # Insert or update
                cursor.execute("""
                    INSERT INTO ai_provider_credentials (user_id, provider, api_key, is_active)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(user_id, provider) DO UPDATE SET
                        api_key = excluded.api_key,
                        updated_at = CURRENT_TIMESTAMP
                """, (user_id, provider, api_key))
                migrated.append(provider)
                print(f"   - Migrated {provider} key")

        conn.commit()

        if migrated:
            print(f"Successfully migrated {len(migrated)} API keys: {', '.join(migrated)}")
        else:
            print("No API keys found in .env to migrate")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--migrate-keys":
        # First create the table
        run_migration()
        # Then migrate keys (default user_id=1)
        user_id = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        migrate_env_keys_to_database(user_id)
    else:
        # Just create the table
        run_migration()
        print("\nTo also migrate existing .env keys to database, run:")
        print("  python add_ai_provider_credentials_table.py --migrate-keys [user_id]")
