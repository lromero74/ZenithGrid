"""Add media_url column to chat_messages for GIF/image support."""

from migrations.db_utils import get_migration_connection, safe_add_column


def run():
    conn = get_migration_connection()
    try:
        safe_add_column(conn, "chat_messages", "media_url VARCHAR(500)")
        conn.commit()
        print("[add_chat_media_url] Migration complete.")
    except Exception as e:
        conn.rollback()
        print(f"[add_chat_media_url] Migration error: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run()
