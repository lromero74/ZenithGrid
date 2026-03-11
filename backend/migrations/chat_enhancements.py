"""
Migration: Chat enhancements — reactions, reply-to, pinned messages, search index.

Adds:
- chat_message_reactions table
- reply_to_id column on chat_messages
- is_pinned column on chat_messages
- Content search index on chat_messages
"""

from migrations.db_utils import (
    get_migration_connection, safe_add_column, is_postgres,
)


def run():
    conn = get_migration_connection()
    cursor = conn.cursor()

    try:
        # 1. Add reply_to_id to chat_messages
        safe_add_column(conn, "chat_messages", "reply_to_id INTEGER DEFAULT NULL")

        # 2. Add is_pinned to chat_messages
        if is_postgres():
            safe_add_column(conn, "chat_messages", "is_pinned BOOLEAN DEFAULT FALSE")
        else:
            safe_add_column(conn, "chat_messages", "is_pinned INTEGER DEFAULT 0")

        # 3. Create chat_message_reactions table
        if is_postgres():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_message_reactions (
                    id SERIAL PRIMARY KEY,
                    message_id INTEGER NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    emoji VARCHAR(32) NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT uq_chat_reaction UNIQUE (message_id, user_id, emoji)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS ix_chat_message_reactions_message_id
                ON chat_message_reactions(message_id)
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_message_reactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    emoji VARCHAR(32) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(message_id, user_id, emoji)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS ix_chat_message_reactions_message_id
                ON chat_message_reactions(message_id)
            """)

        # 4. Add content search index for message search
        if is_postgres():
            # PostgreSQL: use GIN index with tsvector for full-text search
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS ix_chat_messages_content_search
                ON chat_messages USING gin(to_tsvector('english', content))
            """)
        else:
            # SQLite: simple index on content (LIKE-based search)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS ix_chat_messages_content
                ON chat_messages(content)
            """)

        conn.commit()
        print("[chat_enhancements] Migration complete.")
    except Exception as e:
        conn.rollback()
        print(f"[chat_enhancements] Migration error: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    run()
