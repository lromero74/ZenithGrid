"""
Tests for backend/app/routers/ai_credentials_router.py

Covers AI credential CRUD endpoints: list, create/update, get by provider,
update by provider, delete, provider status, and _api_key_preview helper.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.models import AIProviderCredential, User


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def test_user(db_session):
    user = User(
        id=1, email="test@test.com",
        hashed_password="hashed", is_active=True, is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def claude_credential(db_session, test_user):
    cred = AIProviderCredential(
        id=1, user_id=test_user.id, provider="claude",
        api_key="sk-ant-FAKEKEYVALUE1234567890",
        is_active=True,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db_session.add(cred)
    await db_session.flush()
    return cred


# =============================================================================
# _api_key_preview helper
# =============================================================================


class TestApiKeyPreview:
    """Tests for _api_key_preview utility function."""

    @patch("app.routers.ai_credentials_router.is_encrypted", return_value=False)
    @patch("app.routers.ai_credentials_router.decrypt_value", side_effect=lambda v: v)
    def test_preview_long_key(self, mock_decrypt, mock_enc):
        """Happy path: long key shows last 8 chars."""
        from app.routers.ai_credentials_router import _api_key_preview
        result = _api_key_preview("sk-ant-api-12345678abcdefgh")
        assert result.startswith("...")
        assert result.endswith("cdefgh")
        assert len(result) == 11  # "..." + 8 chars

    @patch("app.routers.ai_credentials_router.is_encrypted", return_value=False)
    @patch("app.routers.ai_credentials_router.decrypt_value", side_effect=lambda v: v)
    def test_preview_short_key(self, mock_decrypt, mock_enc):
        """Edge case: short key returns '...'."""
        from app.routers.ai_credentials_router import _api_key_preview
        result = _api_key_preview("short")
        assert result == "..."

    def test_preview_empty_key(self):
        """Failure case: empty key returns '...'."""
        from app.routers.ai_credentials_router import _api_key_preview
        result = _api_key_preview("")
        assert result == "..."


# =============================================================================
# list_ai_credentials
# =============================================================================


class TestListAICredentials:
    """Tests for list_ai_credentials endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.ai_credentials_router.is_encrypted", return_value=False)
    @patch("app.routers.ai_credentials_router.decrypt_value", side_effect=lambda v: v)
    async def test_list_credentials_returns_user_creds(
        self, mock_decrypt, mock_enc, db_session, test_user, claude_credential,
    ):
        """Happy path: returns credentials for current user."""
        from app.routers.ai_credentials_router import list_ai_credentials
        result = await list_ai_credentials(db=db_session, current_user=test_user)
        assert len(result) == 1
        assert result[0].provider == "claude"
        assert result[0].has_api_key is True

    @pytest.mark.asyncio
    async def test_list_credentials_empty(self, db_session, test_user):
        """Edge case: user with no credentials returns empty list."""
        from app.routers.ai_credentials_router import list_ai_credentials
        result = await list_ai_credentials(db=db_session, current_user=test_user)
        assert result == []


# =============================================================================
# create_or_update_ai_credential
# =============================================================================


class TestCreateOrUpdateAICredential:
    """Tests for create_or_update_ai_credential endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.ai_credentials_router.encrypt_value", side_effect=lambda v: f"enc:{v}")
    @patch("app.routers.ai_credentials_router.is_encrypted", return_value=True)
    @patch("app.routers.ai_credentials_router.decrypt_value", side_effect=lambda v: v[4:])
    async def test_create_new_credential(
        self, mock_decrypt, mock_enc, mock_encrypt, db_session, test_user,
    ):
        """Happy path: creates a new credential."""
        from app.routers.ai_credentials_router import (
            create_or_update_ai_credential, AICredentialCreate,
        )
        data = AICredentialCreate(provider="openai", api_key="sk-test-key-12345678")
        result = await create_or_update_ai_credential(
            credential_data=data, db=db_session, current_user=test_user,
        )
        assert result.provider == "openai"
        assert result.is_active is True

    @pytest.mark.asyncio
    @patch("app.routers.ai_credentials_router.encrypt_value", side_effect=lambda v: f"enc:{v}")
    @patch("app.routers.ai_credentials_router.is_encrypted", return_value=True)
    @patch("app.routers.ai_credentials_router.decrypt_value", side_effect=lambda v: v[4:])
    async def test_update_existing_credential(
        self, mock_decrypt, mock_enc, mock_encrypt,
        db_session, test_user, claude_credential,
    ):
        """Edge case: updates existing credential for same provider."""
        from app.routers.ai_credentials_router import (
            create_or_update_ai_credential, AICredentialCreate,
        )
        data = AICredentialCreate(provider="claude", api_key="sk-new-key-12345678")
        result = await create_or_update_ai_credential(
            credential_data=data, db=db_session, current_user=test_user,
        )
        assert result.provider == "claude"
        assert result.id == claude_credential.id

    @pytest.mark.asyncio
    async def test_create_invalid_provider_raises_400(self, db_session, test_user):
        """Failure case: invalid provider raises 400."""
        from app.routers.ai_credentials_router import (
            create_or_update_ai_credential, AICredentialCreate,
        )
        data = AICredentialCreate(provider="invalid_provider", api_key="key")
        with pytest.raises(HTTPException) as exc_info:
            await create_or_update_ai_credential(
                credential_data=data, db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 400


# =============================================================================
# get_ai_credential
# =============================================================================


class TestGetAICredential:
    """Tests for get_ai_credential endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.ai_credentials_router.is_encrypted", return_value=False)
    @patch("app.routers.ai_credentials_router.decrypt_value", side_effect=lambda v: v)
    async def test_get_credential_success(
        self, mock_decrypt, mock_enc, db_session, test_user, claude_credential,
    ):
        """Happy path: returns credential by provider."""
        from app.routers.ai_credentials_router import get_ai_credential
        result = await get_ai_credential(
            provider="claude", db=db_session, current_user=test_user,
        )
        assert result.provider == "claude"

    @pytest.mark.asyncio
    async def test_get_credential_not_found(self, db_session, test_user):
        """Failure case: non-existent credential raises 404."""
        from app.routers.ai_credentials_router import get_ai_credential
        with pytest.raises(HTTPException) as exc_info:
            await get_ai_credential(
                provider="gemini", db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_credential_invalid_provider(self, db_session, test_user):
        """Failure case: invalid provider raises 400."""
        from app.routers.ai_credentials_router import get_ai_credential
        with pytest.raises(HTTPException) as exc_info:
            await get_ai_credential(
                provider="invalid", db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 400


# =============================================================================
# update_ai_credential
# =============================================================================


class TestUpdateAICredential:
    """Tests for update_ai_credential endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.ai_credentials_router.encrypt_value", side_effect=lambda v: f"enc:{v}")
    @patch("app.routers.ai_credentials_router.is_encrypted", return_value=True)
    @patch("app.routers.ai_credentials_router.decrypt_value", side_effect=lambda v: v[4:])
    async def test_update_credential_api_key(
        self, mock_decrypt, mock_enc, mock_encrypt,
        db_session, test_user, claude_credential,
    ):
        """Happy path: updates API key."""
        from app.routers.ai_credentials_router import (
            update_ai_credential, AICredentialUpdate,
        )
        data = AICredentialUpdate(api_key="sk-new-key-87654321")
        result = await update_ai_credential(
            provider="claude", credential_data=data,
            db=db_session, current_user=test_user,
        )
        assert result.provider == "claude"

    @pytest.mark.asyncio
    @patch("app.routers.ai_credentials_router.is_encrypted", return_value=False)
    @patch("app.routers.ai_credentials_router.decrypt_value", side_effect=lambda v: v)
    async def test_update_credential_deactivate(
        self, mock_decrypt, mock_enc,
        db_session, test_user, claude_credential,
    ):
        """Happy path: deactivates credential."""
        from app.routers.ai_credentials_router import (
            update_ai_credential, AICredentialUpdate,
        )
        data = AICredentialUpdate(is_active=False)
        result = await update_ai_credential(
            provider="claude", credential_data=data,
            db=db_session, current_user=test_user,
        )
        assert result.is_active is False

    @pytest.mark.asyncio
    async def test_update_credential_not_found(self, db_session, test_user):
        """Failure case: updating non-existent credential raises 404."""
        from app.routers.ai_credentials_router import (
            update_ai_credential, AICredentialUpdate,
        )
        data = AICredentialUpdate(is_active=False)
        with pytest.raises(HTTPException) as exc_info:
            await update_ai_credential(
                provider="gemini", credential_data=data,
                db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# delete_ai_credential
# =============================================================================


class TestDeleteAICredential:
    """Tests for delete_ai_credential endpoint."""

    @pytest.mark.asyncio
    async def test_delete_credential_success(
        self, db_session, test_user, claude_credential,
    ):
        """Happy path: deletes credential."""
        from app.routers.ai_credentials_router import delete_ai_credential
        result = await delete_ai_credential(
            provider="claude", db=db_session, current_user=test_user,
        )
        assert "deleted successfully" in result["message"]

    @pytest.mark.asyncio
    async def test_delete_credential_not_found(self, db_session, test_user):
        """Failure case: deleting non-existent credential raises 404."""
        from app.routers.ai_credentials_router import delete_ai_credential
        with pytest.raises(HTTPException) as exc_info:
            await delete_ai_credential(
                provider="gemini", db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_credential_invalid_provider(self, db_session, test_user):
        """Failure case: invalid provider raises 400."""
        from app.routers.ai_credentials_router import delete_ai_credential
        with pytest.raises(HTTPException) as exc_info:
            await delete_ai_credential(
                provider="invalid", db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 400


# =============================================================================
# get_ai_providers_status
# =============================================================================


class TestAIProvidersStatus:
    """Tests for get_ai_providers_status endpoint."""

    @pytest.mark.asyncio
    @patch("app.config.settings")
    async def test_providers_status_success(
        self, mock_settings, db_session, test_user, claude_credential,
    ):
        """Happy path: returns status for all providers."""
        mock_settings.anthropic_api_key = "sk-system-key"
        mock_settings.gemini_api_key = None
        mock_settings.grok_api_key = None
        mock_settings.groq_api_key = "gsk-system"
        mock_settings.openai_api_key = None

        from app.routers.ai_credentials_router import get_ai_providers_status
        result = await get_ai_providers_status(
            db=db_session, current_user=test_user,
        )
        assert len(result) == 5

        claude_status = next(s for s in result if s.provider == "claude")
        assert claude_status.has_user_key is True
        assert claude_status.has_system_key is True
        assert claude_status.is_active is True

        gemini_status = next(s for s in result if s.provider == "gemini")
        assert gemini_status.has_user_key is False
        assert gemini_status.has_system_key is False

    @pytest.mark.asyncio
    @patch("app.config.settings")
    async def test_providers_status_no_user_keys(
        self, mock_settings, db_session, test_user,
    ):
        """Edge case: user with no keys shows all inactive."""
        mock_settings.anthropic_api_key = None
        mock_settings.gemini_api_key = None
        mock_settings.grok_api_key = None
        mock_settings.groq_api_key = None
        mock_settings.openai_api_key = None

        from app.routers.ai_credentials_router import get_ai_providers_status
        result = await get_ai_providers_status(
            db=db_session, current_user=test_user,
        )
        for status in result:
            assert status.has_user_key is False
            assert status.is_active is False
