"""
Encrypt existing plaintext API credentials in the database.

This migration encrypts:
- Account.api_private_key (exchange API keys)
- Account.wallet_private_key (DEX wallet keys)
- AIProviderCredential.api_key (AI provider keys)

Idempotent: Skips values that are already encrypted (Fernet tokens start with 'gAAAAA').
"""

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)


def run_migration(db_path: str = None):
    """Encrypt all existing plaintext credentials."""
    if db_path is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")

    # Import encryption utilities
    # We need to handle the case where ENCRYPTION_KEY may not be set
    try:
        from app.encryption import encrypt_value, is_encrypted
    except Exception as e:
        logger.warning(f"Skipping credential encryption migration: {e}")
        logger.warning("Set ENCRYPTION_KEY in .env and re-run to encrypt credentials.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    encrypted_count = 0

    try:
        # Encrypt Account.api_private_key
        try:
            cursor.execute("SELECT id, api_private_key FROM accounts WHERE api_private_key IS NOT NULL AND api_private_key != ''")
            for row_id, value in cursor.fetchall():
                if not is_encrypted(value):
                    encrypted = encrypt_value(value)
                    cursor.execute("UPDATE accounts SET api_private_key = ? WHERE id = ?", (encrypted, row_id))
                    encrypted_count += 1
                    logger.info(f"Encrypted api_private_key for account {row_id}")
        except sqlite3.OperationalError as e:
            if "no such table" not in str(e) and "no such column" not in str(e):
                raise

        # Encrypt Account.wallet_private_key
        try:
            cursor.execute("SELECT id, wallet_private_key FROM accounts WHERE wallet_private_key IS NOT NULL AND wallet_private_key != ''")
            for row_id, value in cursor.fetchall():
                if not is_encrypted(value):
                    encrypted = encrypt_value(value)
                    cursor.execute("UPDATE accounts SET wallet_private_key = ? WHERE id = ?", (encrypted, row_id))
                    encrypted_count += 1
                    logger.info(f"Encrypted wallet_private_key for account {row_id}")
        except sqlite3.OperationalError as e:
            if "no such table" not in str(e) and "no such column" not in str(e):
                raise

        # Encrypt AIProviderCredential.api_key
        try:
            cursor.execute("SELECT id, api_key FROM ai_provider_credentials WHERE api_key IS NOT NULL AND api_key != ''")
            for row_id, value in cursor.fetchall():
                if not is_encrypted(value):
                    encrypted = encrypt_value(value)
                    cursor.execute("UPDATE ai_provider_credentials SET api_key = ? WHERE id = ?", (encrypted, row_id))
                    encrypted_count += 1
                    logger.info(f"Encrypted api_key for AI credential {row_id}")
        except sqlite3.OperationalError as e:
            if "no such table" not in str(e) and "no such column" not in str(e):
                raise

        conn.commit()
        if encrypted_count > 0:
            logger.info(f"Encrypted {encrypted_count} credential(s) successfully")
        else:
            logger.info("No plaintext credentials found to encrypt")

    except Exception as e:
        conn.rollback()
        logger.error(f"Error encrypting credentials: {e}")
        raise
    finally:
        conn.close()
