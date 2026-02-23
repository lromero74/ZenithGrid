"""
Tests for backend/app/services/ai_credential_service.py

Tests retrieval and decryption of per-user AI provider API keys.
"""

import pytest
from unittest.mock import patch

from app.models import AIProviderCredential, User
from app.services.ai_credential_service import get_user_api_key


class TestGetUserApiKey:
    """Tests for get_user_api_key()."""

    @pytest.mark.asyncio
    @patch("app.services.ai_credential_service.is_encrypted", return_value=False)
    async def test_returns_plaintext_key(self, mock_is_enc, db_session):
        """Happy path: returns unencrypted API key for active credential."""
        user = User(
            email="test@example.com",
            hashed_password="fakehash",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        cred = AIProviderCredential(
            user_id=user.id,
            provider="claude",
            api_key="sk-test-key-12345",
            is_active=True,
        )
        db_session.add(cred)
        await db_session.commit()

        result = await get_user_api_key(db_session, user.id, "claude")
        assert result == "sk-test-key-12345"

    @pytest.mark.asyncio
    @patch("app.services.ai_credential_service.decrypt_value", return_value="decrypted-key")
    @patch("app.services.ai_credential_service.is_encrypted", return_value=True)
    async def test_decrypts_encrypted_key(self, mock_is_enc, mock_decrypt, db_session):
        """Happy path: decrypts encrypted API key."""
        user = User(
            email="test2@example.com",
            hashed_password="fakehash",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        cred = AIProviderCredential(
            user_id=user.id,
            provider="gemini",
            api_key="gAAAAAB..encrypted..",
            is_active=True,
        )
        db_session.add(cred)
        await db_session.commit()

        result = await get_user_api_key(db_session, user.id, "gemini")
        assert result == "decrypted-key"
        mock_decrypt.assert_called_once_with("gAAAAAB..encrypted..")

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_credential(self, db_session):
        """Edge case: no credential for the provider returns None."""
        user = User(
            email="test3@example.com",
            hashed_password="fakehash",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()

        result = await get_user_api_key(db_session, user.id, "openai")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_inactive_credential(self, db_session):
        """Edge case: inactive credential returns None."""
        user = User(
            email="test4@example.com",
            hashed_password="fakehash",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        cred = AIProviderCredential(
            user_id=user.id,
            provider="grok",
            api_key="some-key",
            is_active=False,
        )
        db_session.add(cred)
        await db_session.commit()

        result = await get_user_api_key(db_session, user.id, "grok")
        assert result is None

    @pytest.mark.asyncio
    async def test_provider_name_case_insensitive(self, db_session):
        """Edge case: provider name is lowercased before lookup."""
        user = User(
            email="test5@example.com",
            hashed_password="fakehash",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        cred = AIProviderCredential(
            user_id=user.id,
            provider="claude",
            api_key="key-abc",
            is_active=True,
        )
        db_session.add(cred)
        await db_session.commit()

        with patch("app.services.ai_credential_service.is_encrypted", return_value=False):
            result = await get_user_api_key(db_session, user.id, "CLAUDE")
        assert result == "key-abc"

    @pytest.mark.asyncio
    @patch("app.services.ai_credential_service.is_encrypted", return_value=False)
    async def test_updates_last_used_at(self, mock_is_enc, db_session):
        """Happy path: retrieval updates last_used_at timestamp."""
        user = User(
            email="test6@example.com",
            hashed_password="fakehash",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        cred = AIProviderCredential(
            user_id=user.id,
            provider="groq",
            api_key="groq-key",
            is_active=True,
        )
        db_session.add(cred)
        await db_session.commit()

        assert cred.last_used_at is None
        await get_user_api_key(db_session, user.id, "groq")
        await db_session.refresh(cred)
        assert cred.last_used_at is not None

    @pytest.mark.asyncio
    async def test_returns_none_for_wrong_user(self, db_session):
        """Failure: credential from another user is not returned."""
        user1 = User(email="u1@ex.com", hashed_password="h", is_active=True)
        user2 = User(email="u2@ex.com", hashed_password="h", is_active=True)
        db_session.add_all([user1, user2])
        await db_session.flush()

        cred = AIProviderCredential(
            user_id=user1.id,
            provider="claude",
            api_key="user1-key",
            is_active=True,
        )
        db_session.add(cred)
        await db_session.commit()

        result = await get_user_api_key(db_session, user2.id, "claude")
        assert result is None
