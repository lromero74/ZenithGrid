"""
Tests for backend/app/routers/blacklist_router.py

Covers blacklist CRUD endpoints: list/add/remove blacklisted coins,
user overrides, category settings, AI provider settings, and AI review trigger.
"""

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
            db=db_session, current_user=test_user,
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
            db=db_session, current_user=test_user,
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
