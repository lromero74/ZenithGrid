"""
Encryption utilities for storing sensitive data at rest.

Uses Fernet symmetric encryption (AES-128-CBC with HMAC-SHA256)
to encrypt API keys and other credentials stored in the database.
"""

import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger(__name__)

_fernet = None


def _get_fernet() -> Fernet:
    """Get or create the Fernet instance from the configured encryption key."""
    global _fernet
    if _fernet is None:
        key = settings.encryption_key
        if not key:
            raise RuntimeError(
                "ENCRYPTION_KEY not set in .env. "
                "Run setup.py to generate one, or set ENCRYPTION_KEY manually."
            )
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a plaintext string and return the ciphertext as a string.

    Args:
        plaintext: The value to encrypt (e.g., an API key)

    Returns:
        Encrypted string (Fernet token, starts with 'gAAAAA')
    """
    if not plaintext:
        return plaintext
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """
    Decrypt a ciphertext string and return the plaintext.

    Args:
        ciphertext: The encrypted value to decrypt

    Returns:
        Decrypted plaintext string
    """
    if not ciphertext:
        return ciphertext
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.error("Failed to decrypt value — invalid token or wrong encryption key")
        raise


def is_encrypted(value: str) -> bool:
    """
    Check if a value appears to already be encrypted (Fernet tokens start with 'gAAAAA').

    Args:
        value: The string to check

    Returns:
        True if the value looks like a Fernet token
    """
    if not value:
        return False
    return value.startswith("gAAAAA")
