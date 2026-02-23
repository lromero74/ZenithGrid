"""Tests for app/encryption.py"""

import pytest
from unittest.mock import patch
from cryptography.fernet import Fernet, InvalidToken

import app.encryption as enc_module
from app.encryption import decrypt_value, encrypt_value, is_encrypted


@pytest.fixture(autouse=True)
def reset_fernet():
    """Reset the module-level _fernet singleton between tests."""
    enc_module._fernet = None
    yield
    enc_module._fernet = None


@pytest.fixture
def mock_settings():
    """Mock settings with a valid test encryption key."""
    key = Fernet.generate_key().decode()
    with patch.object(enc_module, "settings") as mock:
        mock.encryption_key = key
        yield mock


# ---------------------------------------------------------------------------
# encrypt_value / decrypt_value roundtrip
# ---------------------------------------------------------------------------

class TestEncryptDecrypt:
    def test_roundtrip_encryption(self, mock_settings):
        """Encrypt then decrypt returns original value"""
        plaintext = "my-secret-api-key-12345"
        encrypted = encrypt_value(plaintext)

        assert encrypted != plaintext
        assert encrypted.startswith("gAAAAA")

        decrypted = decrypt_value(encrypted)
        assert decrypted == plaintext

    def test_empty_string_passes_through(self, mock_settings):
        assert encrypt_value("") == ""
        assert decrypt_value("") == ""

    def test_none_passes_through(self, mock_settings):
        assert encrypt_value(None) is None
        assert decrypt_value(None) is None

    def test_different_plaintexts_produce_different_ciphertexts(self, mock_settings):
        enc1 = encrypt_value("secret1")
        enc2 = encrypt_value("secret2")
        assert enc1 != enc2

    def test_same_plaintext_produces_different_ciphertexts(self, mock_settings):
        """Fernet uses random IV, so same input → different output"""
        enc1 = encrypt_value("same_value")
        enc2 = encrypt_value("same_value")
        assert enc1 != enc2
        # But both decrypt to the same value
        assert decrypt_value(enc1) == decrypt_value(enc2) == "same_value"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestEncryptionErrors:
    def test_decrypt_wrong_key_raises(self):
        """Decrypting with a different key raises InvalidToken"""
        key1 = Fernet.generate_key().decode()
        key2 = Fernet.generate_key().decode()

        with patch.object(enc_module, "settings") as mock:
            mock.encryption_key = key1
            encrypted = encrypt_value("secret")

        enc_module._fernet = None  # Reset singleton

        with patch.object(enc_module, "settings") as mock:
            mock.encryption_key = key2
            with pytest.raises(InvalidToken):
                decrypt_value(encrypted)

    def test_missing_encryption_key_raises(self):
        with patch.object(enc_module, "settings") as mock:
            mock.encryption_key = ""
            with pytest.raises(RuntimeError, match="ENCRYPTION_KEY not set"):
                encrypt_value("secret")

    def test_decrypt_garbage_raises(self, mock_settings):
        with pytest.raises(Exception):
            decrypt_value("not_a_valid_fernet_token")


# ---------------------------------------------------------------------------
# is_encrypted
# ---------------------------------------------------------------------------

class TestIsEncrypted:
    def test_encrypted_value_detected(self, mock_settings):
        encrypted = encrypt_value("my_key")
        assert is_encrypted(encrypted) is True

    def test_plaintext_not_detected(self):
        assert is_encrypted("my_api_key_12345") is False

    def test_empty_string_returns_false(self):
        assert is_encrypted("") is False

    def test_none_returns_false(self):
        assert is_encrypted(None) is False

    def test_gAAAAA_prefix_detected(self):
        assert is_encrypted("gAAAAAB_fake_token_here") is True
