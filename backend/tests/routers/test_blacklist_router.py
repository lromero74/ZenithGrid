"""
Tests for backend/app/routers/blacklist_router.py

Covers blacklist CRUD endpoints: list/add/remove blacklisted coins,
user overrides, category settings, AI provider settings, and AI review trigger.
"""

import inspect

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.models import BlacklistedCoin, User


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
async def admin_user(db_session):
    user = User(
        id=2, email="admin@test.com",
        hashed_password="hashed", is_active=True, is_superuser=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def global_blacklist_entry(db_session):
    entry = BlacklistedCoin(
        id=1, symbol="DOGE", reason="[QUESTIONABLE] Meme coin",
        user_id=None, created_at=datetime.utcnow(),
    )
    db_session.add(entry)
    await db_session.flush()
    return entry


@pytest.fixture
async def user_override(db_session, test_user):
    entry = BlacklistedCoin(
        id=10, symbol="SHIB", reason="[BLACKLISTED] Too risky",
        user_id=test_user.id, created_at=datetime.utcnow(),
    )
    db_session.add(entry)
    await db_session.flush()
    return entry


# =============================================================================
# _extract_category helper
# =============================================================================


class TestExtractCategory:
    """Tests for _extract_category helper."""

    def test_extract_approved(self):
        from app.routers.blacklist_router import _extract_category
        assert _extract_category("[APPROVED] Good coin") == "APPROVED"

    def test_extract_blacklisted(self):
        from app.routers.blacklist_router import _extract_category
        assert _extract_category("[BLACKLISTED] Bad coin") == "BLACKLISTED"

    def test_extract_none_reason(self):
        from app.routers.blacklist_router import _extract_category
        assert _extract_category(None) == "BLACKLISTED"

    def test_extract_no_prefix(self):
        from app.routers.blacklist_router import _extract_category
        assert _extract_category("Just some reason") == "BLACKLISTED"


# =============================================================================
# list_user_overrides
# =============================================================================


class TestListUserOverrides:
    """Tests for list_user_overrides endpoint."""

    @pytest.mark.asyncio
    async def test_list_overrides_returns_user_entries(
        self, db_session, test_user, user_override,
    ):
        """Happy path: returns overrides for current user."""
        from app.routers.blacklist_router import list_user_overrides
        result = await list_user_overrides(db=db_session, current_user=test_user)
        assert len(result) == 1
        assert result[0].symbol == "SHIB"
        assert result[0].category == "BLACKLISTED"

    @pytest.mark.asyncio
    async def test_list_overrides_empty(self, db_session, test_user):
        """Edge case: user with no overrides returns empty list."""
        from app.routers.blacklist_router import list_user_overrides
        result = await list_user_overrides(db=db_session, current_user=test_user)
        assert result == []


# =============================================================================
# set_user_override
# =============================================================================


class TestSetUserOverride:
    """Tests for set_user_override endpoint."""

    @pytest.mark.asyncio
    async def test_set_override_creates_new(self, db_session, test_user):
        """Happy path: creates new override entry."""
        from app.routers.blacklist_router import set_user_override, UserOverrideRequest
        request = UserOverrideRequest(category="APPROVED", reason="Looks safe")
        result = await set_user_override(
            symbol="ETH", request=request,
            db=db_session, current_user=test_user,
        )
        assert result.symbol == "ETH"
        assert result.category == "APPROVED"
        assert result.reason == "Looks safe"

    @pytest.mark.asyncio
    async def test_set_override_updates_existing(
        self, db_session, test_user, user_override,
    ):
        """Edge case: updates existing override for same symbol."""
        from app.routers.blacklist_router import set_user_override, UserOverrideRequest
        request = UserOverrideRequest(category="APPROVED", reason="Changed mind")
        result = await set_user_override(
            symbol="SHIB", request=request,
            db=db_session, current_user=test_user,
        )
        assert result.category == "APPROVED"

    @pytest.mark.asyncio
    async def test_set_override_invalid_category(self, db_session, test_user):
        """Failure case: invalid category raises 400."""
        from app.routers.blacklist_router import set_user_override, UserOverrideRequest
        request = UserOverrideRequest(category="INVALID")
        with pytest.raises(HTTPException) as exc_info:
            await set_user_override(
                symbol="BTC", request=request,
                db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_set_override_empty_symbol(self, db_session, test_user):
        """Failure case: empty symbol raises 400."""
        from app.routers.blacklist_router import set_user_override, UserOverrideRequest
        request = UserOverrideRequest(category="APPROVED")
        with pytest.raises(HTTPException) as exc_info:
            await set_user_override(
                symbol="  ", request=request,
                db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 400


# =============================================================================
# remove_user_override
# =============================================================================


class TestRemoveUserOverride:
    """Tests for remove_user_override endpoint."""

    @pytest.mark.asyncio
    async def test_remove_override_success(
        self, db_session, test_user, user_override,
    ):
        """Happy path: removes existing override."""
        from app.routers.blacklist_router import remove_user_override
        result = await remove_user_override(
            symbol="SHIB", db=db_session, current_user=test_user,
        )
        assert "removed" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_remove_override_not_found(self, db_session, test_user):
        """Failure case: removing non-existent override raises 404."""
        from app.routers.blacklist_router import remove_user_override
        with pytest.raises(HTTPException) as exc_info:
            await remove_user_override(
                symbol="UNKNOWN", db=db_session, current_user=test_user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# list_blacklisted_coins
# =============================================================================


class TestListBlacklistedCoins:
    """Tests for list_blacklisted_coins endpoint."""

    @pytest.mark.asyncio
    async def test_list_returns_global_entries(
        self, db_session, test_user, global_blacklist_entry,
    ):
        """Happy path: returns global (user_id=None) entries."""
        from app.routers.blacklist_router import list_blacklisted_coins
        result = await list_blacklisted_coins(
            db=db_session, current_user=test_user, account_id=None,
        )
        assert len(result) == 1
        assert result[0].symbol == "DOGE"
        assert result[0].is_global is True

    @pytest.mark.asyncio
    async def test_list_annotates_user_overrides(
        self, db_session, test_user, global_blacklist_entry, user_override,
    ):
        """Edge case: user override on global DOGE is annotated."""
        # Create a user override for DOGE specifically
        doge_override = BlacklistedCoin(
            id=20, symbol="DOGE", reason="[APPROVED] I like it",
            user_id=test_user.id, created_at=datetime.utcnow(),
        )
        db_session.add(doge_override)
        await db_session.flush()

        from app.routers.blacklist_router import list_blacklisted_coins
        result = await list_blacklisted_coins(
            db=db_session, current_user=test_user, account_id=None,
        )
        assert len(result) == 1
        assert result[0].user_override_category == "APPROVED"


# =============================================================================
# add_to_blacklist
# =============================================================================


class TestAddToBlacklist:
    """Tests for add_to_blacklist endpoint."""

    @pytest.mark.asyncio
    async def test_add_coins_admin(self, db_session, admin_user):
        """Happy path: admin can add coins to global blacklist."""
        from app.routers.blacklist_router import add_to_blacklist, BlacklistAddRequest
        request = BlacklistAddRequest(
            symbols=["XRP", "ADA"], reason="[BORDERLINE] Monitor closely",
        )
        result = await add_to_blacklist(
            request=request, db=db_session, current_user=admin_user,
        )
        assert len(result) == 2
        assert {e.symbol for e in result} == {"XRP", "ADA"}

    @pytest.mark.asyncio
    async def test_add_coins_non_admin_raises_403(self, db_session, test_user):
        """Failure case: non-admin user raises 403 via require_superuser dependency."""
        from app.auth.dependencies import require_superuser
        with pytest.raises(HTTPException) as exc_info:
            await require_superuser(current_user=test_user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_add_duplicate_skipped(
        self, db_session, admin_user, global_blacklist_entry,
    ):
        """Edge case: duplicate symbols are silently skipped."""
        from app.routers.blacklist_router import add_to_blacklist, BlacklistAddRequest
        request = BlacklistAddRequest(symbols=["DOGE"])
        result = await add_to_blacklist(
            request=request, db=db_session, current_user=admin_user,
        )
        assert len(result) == 0


# =============================================================================
# remove_from_blacklist
# =============================================================================


class TestRemoveFromBlacklist:
    """Tests for remove_from_blacklist endpoint."""

    @pytest.mark.asyncio
    async def test_remove_coin_admin(
        self, db_session, admin_user, global_blacklist_entry,
    ):
        """Happy path: admin removes coin from global blacklist."""
        from app.routers.blacklist_router import remove_from_blacklist
        result = await remove_from_blacklist(
            symbol="DOGE", db=db_session, current_user=admin_user,
        )
        assert "removed" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_remove_coin_non_admin_raises_403(self, db_session, test_user):
        """Failure case: non-admin raises 403 via require_superuser dependency."""
        from app.auth.dependencies import require_superuser
        with pytest.raises(HTTPException) as exc_info:
            await require_superuser(current_user=test_user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_remove_coin_not_found(self, db_session, admin_user):
        """Failure case: removing non-categorized coin raises 404."""
        from app.routers.blacklist_router import remove_from_blacklist
        with pytest.raises(HTTPException) as exc_info:
            await remove_from_blacklist(
                symbol="UNKNOWN", db=db_session, current_user=admin_user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# Category Settings
# =============================================================================


class TestCategorySettings:
    """Tests for get/update category settings."""

    @pytest.mark.asyncio
    @patch(
        "app.routers.blacklist_router.get_allowed_categories",
        new_callable=AsyncMock,
        return_value=["APPROVED", "BORDERLINE"],
    )
    async def test_get_category_settings(self, mock_cats, db_session, test_user):
        """Happy path: returns current category settings."""
        from app.routers.blacklist_router import get_category_settings
        result = await get_category_settings(db=db_session, current_user=test_user)
        assert result.allowed_categories == ["APPROVED", "BORDERLINE"]
        assert "BLACKLISTED" in result.all_categories

    @pytest.mark.asyncio
    async def test_update_category_settings_invalid(self, db_session, admin_user):
        """Failure case: invalid category raises 400."""
        from app.routers.blacklist_router import (
            update_category_settings, CategorySettingsRequest,
        )
        request = CategorySettingsRequest(allowed_categories=["INVALID"])
        with pytest.raises(HTTPException) as exc_info:
            await update_category_settings(
                request=request, db=db_session, current_user=admin_user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_update_category_settings_success(self, db_session, admin_user):
        """Happy path: admin updates allowed categories."""
        from app.routers.blacklist_router import (
            update_category_settings, CategorySettingsRequest,
        )
        request = CategorySettingsRequest(
            allowed_categories=["APPROVED", "BORDERLINE"],
        )
        result = await update_category_settings(
            request=request, db=db_session, current_user=admin_user,
        )
        assert result.allowed_categories == ["APPROVED", "BORDERLINE"]

    def test_update_category_settings_requires_superuser(self):
        """Sweep v2.160.4: global Settings mutation must be superuser-gated,
        not guarded by a per-user permission that any BLACKLIST_WRITE user has."""
        from app.auth.dependencies import require_superuser
        from app.routers.blacklist_router import update_category_settings
        sig = inspect.signature(update_category_settings)
        dep = sig.parameters["current_user"].default.dependency
        assert dep is require_superuser

    def test_update_ai_provider_setting_requires_superuser(self):
        """Sweep v2.160.4: global AI-provider setting write must be superuser-only."""
        from app.auth.dependencies import require_superuser
        from app.routers.blacklist_router import update_ai_provider_setting
        sig = inspect.signature(update_ai_provider_setting)
        dep = sig.parameters["current_user"].default.dependency
        assert dep is require_superuser


# =============================================================================
# AI Review Trigger
# =============================================================================


class TestTriggerAIReview:
    """Tests for trigger_ai_review endpoint."""

    @pytest.mark.asyncio
    @patch(
        "app.services.coin_review_service.run_weekly_review",
        new_callable=AsyncMock,
    )
    async def test_trigger_ai_review_admin(self, mock_review, admin_user):
        """Happy path: admin triggers AI review."""
        mock_review.return_value = {"status": "success", "reviewed": 50}
        from app.routers.blacklist_router import trigger_ai_review
        result = await trigger_ai_review(current_user=admin_user)
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_trigger_ai_review_non_admin_raises_403(self, test_user):
        """Failure case: non-admin raises 403 via require_superuser dependency."""
        from app.auth.dependencies import require_superuser
        with pytest.raises(HTTPException) as exc_info:
            await require_superuser(current_user=test_user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch(
        "app.services.coin_review_service.run_weekly_review",
        new_callable=AsyncMock,
    )
    async def test_trigger_ai_review_error_raises_500(
        self, mock_review, admin_user,
    ):
        """Failure case: service returns error raises 500."""
        mock_review.return_value = {"status": "error", "message": "API timeout"}
        from app.routers.blacklist_router import trigger_ai_review
        with pytest.raises(HTTPException) as exc_info:
            await trigger_ai_review(current_user=admin_user)
        assert exc_info.value.status_code == 500


# =============================================================================
# AI Provider Settings
# =============================================================================


class TestAIProviderSettings:
    """Tests for get/update AI provider settings (coin review)."""

    @pytest.mark.asyncio
    @patch(
        "app.routers.blacklist_router.get_configured_ai_providers",
        return_value=["claude", "openai"],
    )
    @patch(
        "app.routers.blacklist_router.get_ai_review_provider",
        new_callable=AsyncMock,
        return_value="claude",
    )
    async def test_get_ai_provider_returns_configured(
        self, mock_get_prov, mock_configured, db_session, test_user,
    ):
        """Happy path: returns configured provider + list of available."""
        from app.routers.blacklist_router import get_ai_provider_setting
        result = await get_ai_provider_setting(db=db_session, current_user=test_user)
        assert result.provider == "claude"
        assert "claude" in result.available_providers

    @pytest.mark.asyncio
    @patch(
        "app.routers.blacklist_router.get_configured_ai_providers",
        return_value=["openai"],
    )
    @patch(
        "app.routers.blacklist_router.get_ai_review_provider",
        new_callable=AsyncMock,
        return_value="claude",
    )
    async def test_get_ai_provider_falls_back_when_not_configured(
        self, mock_get_prov, mock_configured, db_session, test_user,
    ):
        """Edge case: current provider missing → fall back to first configured."""
        from app.routers.blacklist_router import get_ai_provider_setting
        result = await get_ai_provider_setting(db=db_session, current_user=test_user)
        assert result.provider == "openai"

    @pytest.mark.asyncio
    @patch(
        "app.routers.blacklist_router.get_configured_ai_providers",
        return_value=["claude", "openai"],
    )
    async def test_update_ai_provider_success(
        self, mock_configured, db_session, admin_user,
    ):
        """Happy path: admin updates AI provider to a configured one."""
        from app.routers.blacklist_router import (
            update_ai_provider_setting, AIProviderSettingsRequest,
        )
        request = AIProviderSettingsRequest(provider="openai")
        result = await update_ai_provider_setting(
            request=request, db=db_session, current_user=admin_user,
        )
        assert result.provider == "openai"

    @pytest.mark.asyncio
    @patch(
        "app.routers.blacklist_router.get_configured_ai_providers",
        return_value=["claude"],
    )
    async def test_update_ai_provider_unconfigured_raises_400(
        self, mock_configured, db_session, admin_user,
    ):
        """Failure case: unconfigured provider raises 400."""
        from app.routers.blacklist_router import (
            update_ai_provider_setting, AIProviderSettingsRequest,
        )
        request = AIProviderSettingsRequest(provider="nonexistent")
        with pytest.raises(HTTPException) as exc_info:
            await update_ai_provider_setting(
                request=request, db=db_session, current_user=admin_user,
            )
        assert exc_info.value.status_code == 400


# =============================================================================
# add_single_to_blacklist
# =============================================================================


class TestAddSingleToBlacklist:
    """Tests for add_single_to_blacklist endpoint."""

    @pytest.mark.asyncio
    async def test_add_single_success(self, db_session, admin_user):
        """Happy path: adds one coin with its own reason."""
        from app.routers.blacklist_router import (
            add_single_to_blacklist, BlacklistAddSingleRequest,
        )
        request = BlacklistAddSingleRequest(
            symbol="LTC", reason="[APPROVED] Solid coin",
        )
        result = await add_single_to_blacklist(
            request=request, db=db_session, current_user=admin_user,
        )
        assert result.symbol == "LTC"
        assert "[APPROVED]" in result.reason

    @pytest.mark.asyncio
    async def test_add_single_empty_symbol_raises_400(
        self, db_session, admin_user,
    ):
        """Failure case: empty symbol raises 400."""
        from app.routers.blacklist_router import (
            add_single_to_blacklist, BlacklistAddSingleRequest,
        )
        request = BlacklistAddSingleRequest(symbol="   ", reason="Blank")
        with pytest.raises(HTTPException) as exc_info:
            await add_single_to_blacklist(
                request=request, db=db_session, current_user=admin_user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_add_single_duplicate_raises_409(
        self, db_session, admin_user, global_blacklist_entry,
    ):
        """Failure case: adding existing global entry raises 409."""
        from app.routers.blacklist_router import (
            add_single_to_blacklist, BlacklistAddSingleRequest,
        )
        request = BlacklistAddSingleRequest(symbol="DOGE", reason="[MEME] dup")
        with pytest.raises(HTTPException) as exc_info:
            await add_single_to_blacklist(
                request=request, db=db_session, current_user=admin_user,
            )
        assert exc_info.value.status_code == 409


# =============================================================================
# update_blacklist_reason
# =============================================================================


class TestUpdateBlacklistReason:
    """Tests for update_blacklist_reason endpoint."""

    @pytest.mark.asyncio
    async def test_update_reason_success(
        self, db_session, admin_user, global_blacklist_entry,
    ):
        """Happy path: admin updates the category/reason text."""
        from app.routers.blacklist_router import (
            update_blacklist_reason, BlacklistUpdateRequest,
        )
        request = BlacklistUpdateRequest(reason="[APPROVED] Reversed decision")
        result = await update_blacklist_reason(
            symbol="DOGE", request=request,
            db=db_session, current_user=admin_user,
        )
        assert result.reason == "[APPROVED] Reversed decision"

    @pytest.mark.asyncio
    async def test_update_reason_not_found_raises_404(
        self, db_session, admin_user,
    ):
        """Failure case: non-existent symbol raises 404."""
        from app.routers.blacklist_router import (
            update_blacklist_reason, BlacklistUpdateRequest,
        )
        request = BlacklistUpdateRequest(reason="[APPROVED] New")
        with pytest.raises(HTTPException) as exc_info:
            await update_blacklist_reason(
                symbol="UNKNOWN", request=request,
                db=db_session, current_user=admin_user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# check_if_blacklisted
# =============================================================================


class TestCheckIfBlacklisted:
    """Tests for check_if_blacklisted endpoint."""

    @pytest.mark.asyncio
    async def test_check_returns_category_for_entry(
        self, db_session, test_user, global_blacklist_entry,
    ):
        """Happy path: categorized coin returns its category."""
        from app.routers.blacklist_router import check_if_blacklisted
        result = await check_if_blacklisted(
            symbol="doge", db=db_session, current_user=test_user,
        )
        assert result["is_categorized"] is True
        assert result["category"] == "QUESTIONABLE"
        assert result["symbol"] == "DOGE"

    @pytest.mark.asyncio
    async def test_check_uncategorized_returns_false(
        self, db_session, test_user,
    ):
        """Edge case: uncategorized coin returns is_categorized=False, category=None."""
        from app.routers.blacklist_router import check_if_blacklisted
        result = await check_if_blacklisted(
            symbol="XYZ", db=db_session, current_user=test_user,
        )
        assert result["is_categorized"] is False
        assert result["category"] is None

    @pytest.mark.asyncio
    async def test_check_reason_without_prefix_is_blacklisted(
        self, db_session, test_user,
    ):
        """Edge case: entry with unprefixed reason defaults to BLACKLISTED."""
        entry = BlacklistedCoin(
            symbol="BAD", reason="just a plain reason",
            user_id=None, created_at=datetime.utcnow(),
        )
        db_session.add(entry)
        await db_session.flush()

        from app.routers.blacklist_router import check_if_blacklisted
        result = await check_if_blacklisted(
            symbol="BAD", db=db_session, current_user=test_user,
        )
        assert result["is_categorized"] is True
        assert result["category"] == "BLACKLISTED"


# =============================================================================
# Tenant Isolation — list_blacklisted_coins with account_id
# =============================================================================


class TestListBlacklistedCoinsTenantIsolation:
    """Tests for account-scoped blacklist visibility and access control."""

    @pytest.mark.asyncio
    async def test_list_account_id_not_found_raises_404(
        self, db_session, test_user,
    ):
        """Failure case: non-existent account_id raises 404."""
        from app.routers.blacklist_router import list_blacklisted_coins
        with pytest.raises(HTTPException) as exc_info:
            await list_blacklisted_coins(
                db=db_session, current_user=test_user, account_id=9999,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_non_member_raises_403(
        self, db_session, test_user,
    ):
        """Failure case: user is not owner and not member of the account → 403."""
        # Create another user's account
        from app.models import Account
        other_user = User(
            id=42, email="other@test.com",
            hashed_password="x", is_active=True,
        )
        db_session.add(other_user)
        await db_session.flush()
        acct = Account(
            id=500, user_id=other_user.id, name="Other's Account",
            type="cex", is_active=True,
        )
        db_session.add(acct)
        await db_session.flush()

        from app.routers.blacklist_router import list_blacklisted_coins
        with pytest.raises(HTTPException) as exc_info:
            await list_blacklisted_coins(
                db=db_session, current_user=test_user, account_id=acct.id,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_list_owner_sees_own_overrides_via_account_id(
        self, db_session, test_user, global_blacklist_entry,
    ):
        """Happy path: passing your own account_id shows your overrides (not errored)."""
        from app.models import Account
        acct = Account(
            id=600, user_id=test_user.id, name="My Account",
            type="cex", is_active=True,
        )
        db_session.add(acct)
        # Create user override on DOGE
        override = BlacklistedCoin(
            symbol="DOGE", reason="[APPROVED] Ownr override",
            user_id=test_user.id, created_at=datetime.utcnow(),
        )
        db_session.add(override)
        await db_session.flush()

        from app.routers.blacklist_router import list_blacklisted_coins
        result = await list_blacklisted_coins(
            db=db_session, current_user=test_user, account_id=acct.id,
        )
        assert len(result) == 1
        assert result[0].user_override_category == "APPROVED"


# =============================================================================
# remove_user_override edge cases
# =============================================================================


class TestRemoveUserOverrideEdgeCases:
    """Additional edge cases for remove_user_override."""

    @pytest.mark.asyncio
    async def test_remove_normalizes_symbol_casing(
        self, db_session, test_user, user_override,
    ):
        """Edge case: lowercase input is normalized to match stored override."""
        from app.routers.blacklist_router import remove_user_override
        result = await remove_user_override(
            symbol="shib", db=db_session, current_user=test_user,
        )
        assert "removed" in result["message"].lower()


# =============================================================================
# get_category_settings shape
# =============================================================================


class TestGetCategorySettingsShape:
    """Tests for the shape of get_category_settings response."""

    @pytest.mark.asyncio
    @patch(
        "app.routers.blacklist_router.get_allowed_categories",
        new_callable=AsyncMock,
        return_value=[],
    )
    async def test_empty_allowed_categories_still_has_full_list(
        self, mock_cats, db_session, test_user,
    ):
        """Edge case: empty allowed_categories still returns all known categories."""
        from app.routers.blacklist_router import get_category_settings
        result = await get_category_settings(db=db_session, current_user=test_user)
        assert result.allowed_categories == []
        assert len(result.all_categories) > 0
        assert "APPROVED" in result.all_categories
