"""
Helper functions for fetching AI provider credentials.

Provides a synchronous way to fetch API keys for AI providers,
checking the database first and falling back to .env settings.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Database path (relative to backend folder)
_DB_PATH = Path(__file__).parent.parent.parent.parent.parent / "trading.db"


def get_api_key_for_provider_sync(user_id: Optional[int], provider: str) -> Optional[str]:
    """
    Get API key for a provider, checking user's database entry first,
    then falling back to system .env key.

    This is a synchronous function that uses direct SQLite access,
    suitable for use in background tasks and strategies.

    Args:
        user_id: User ID to check credentials for (None for system-wide only)
        provider: AI provider name (claude, gemini, grok, groq, openai)

    Returns:
        API key string if found, None otherwise
    """
    provider = provider.lower()

    # Map provider names to settings attributes
    system_keys = {
        "claude": settings.anthropic_api_key,
        "gemini": settings.gemini_api_key,
        "grok": settings.grok_api_key,
        "groq": settings.groq_api_key,
        "openai": settings.openai_api_key,
    }

    # If no user_id, just return system key
    if user_id is None:
        return system_keys.get(provider) or None

    # Try to get from database first
    try:
        if not _DB_PATH.exists():
            logger.warning(f"Database not found at {_DB_PATH}, falling back to .env")
            return system_keys.get(provider) or None

        conn = sqlite3.connect(str(_DB_PATH))
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='ai_provider_credentials'
        """)
        if not cursor.fetchone():
            conn.close()
            logger.debug("ai_provider_credentials table not found, using .env fallback")
            return system_keys.get(provider) or None

        # Query for user's credential
        cursor.execute("""
            SELECT api_key FROM ai_provider_credentials
            WHERE user_id = ? AND provider = ? AND is_active = 1
        """, (user_id, provider))

        result = cursor.fetchone()

        if result and result[0]:
            # Update last_used_at
            cursor.execute("""
                UPDATE ai_provider_credentials
                SET last_used_at = datetime('now')
                WHERE user_id = ? AND provider = ?
            """, (user_id, provider))
            conn.commit()
            conn.close()
            logger.debug(f"Using database API key for {provider} (user_id={user_id})")
            return result[0]

        conn.close()

    except Exception as e:
        logger.warning(f"Error fetching API key from database: {e}, falling back to .env")

    # Fall back to system .env key
    system_key = system_keys.get(provider)
    if system_key:
        logger.debug(f"Using .env API key for {provider}")
    return system_key or None
