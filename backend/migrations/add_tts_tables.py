"""
Migration: Add TTS persistence tables.

article_tts: Cached TTS audio files (per article × voice).
user_voice_subscriptions: Per-user voice preferences.
user_article_tts_history: Per-user last-played voice per article.

Idempotent: Safe to run multiple times.
"""

import logging
import os

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")


async def run(db_session):
    """Run migration using async session (called by update.py)."""
    import aiosqlite

    db_path = DB_PATH
    async with aiosqlite.connect(db_path) as db:
        # article_tts: cached TTS audio per article + voice
        try:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS article_tts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER NOT NULL
                        REFERENCES news_articles(id) ON DELETE CASCADE,
                    voice_id TEXT NOT NULL,
                    audio_path TEXT NOT NULL,
                    word_timings TEXT,
                    file_size_bytes INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    created_by_user_id INTEGER REFERENCES users(id),
                    UNIQUE(article_id, voice_id)
                )
            """)
            logger.info("Created article_tts table")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.debug("article_tts table already exists")
            else:
                logger.warning(f"Could not create article_tts: {e}")

        # user_voice_subscriptions: per-user voice preferences
        try:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_voice_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
                    voice_id TEXT NOT NULL,
                    is_enabled BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, voice_id)
                )
            """)
            logger.info("Created user_voice_subscriptions table")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.debug("user_voice_subscriptions table already exists")
            else:
                logger.warning(
                    f"Could not create user_voice_subscriptions: {e}"
                )

        # user_article_tts_history: last-used voice per article per user
        try:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_article_tts_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
                    article_id INTEGER NOT NULL
                        REFERENCES news_articles(id) ON DELETE CASCADE,
                    last_voice_id TEXT NOT NULL,
                    last_played_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, article_id)
                )
            """)
            logger.info("Created user_article_tts_history table")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.debug(
                    "user_article_tts_history table already exists"
                )
            else:
                logger.warning(
                    f"Could not create user_article_tts_history: {e}"
                )

        await db.commit()
        logger.info("Migration complete: TTS persistence tables created")
