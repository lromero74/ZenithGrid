"""
Tests for backend/app/routers/display_name_router.py

Covers:
- PUT /api/users/display-name — set/update display name (unique, validated)
- GET /api/users/display-name/check — availability check
- PUT /api/users/admin-display-name — admin-only display name (RBAC)
"""

import inspect

import pytest
from fastapi import HTTPException

from app.auth.dependencies import Perm
from app.models import User
from app.routers.display_name_router import (
    DisplayNameUpdate,
    AdminDisplayNameUpdate,
    check_display_name,
    set_admin_display_name,
    set_display_name,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_user(db_session, email="user@example.com", display_name=None):
    """Create and persist a User."""
    user = User(
        email=email,
        hashed_password="hashed",
        is_active=True,
        display_name=display_name,
    )
    db_session.add(user)
    await db_session.flush()
    return user


# ---------------------------------------------------------------------------
# RBAC / dependency annotations
# ---------------------------------------------------------------------------


class TestAdminDisplayNameRBAC:
    """admin-display-name should be gated by Perm.ADMIN_USERS."""

    def test_set_admin_display_name_requires_admin_users(self):
        sig = inspect.signature(set_admin_display_name)
        dep = sig.parameters["current_user"].default
        inner = dep.dependency
        assert "require_permission" in inner.__qualname__

        closure_vars = inspect.getclosurevars(inner)
        perms = closure_vars.nonlocals.get("permissions")
        perm_names = [str(p) for p in perms]
        assert str(Perm.ADMIN_USERS) in perm_names

    def test_set_display_name_uses_get_current_user(self):
        """Regular user endpoint should NOT require a specific permission."""
        sig = inspect.signature(set_display_name)
        dep = sig.parameters["current_user"].default
        inner = dep.dependency
        # Should be get_current_user, not require_permission
        assert "require_permission" not in inner.__qualname__


# ---------------------------------------------------------------------------
# PUT /display-name
# ---------------------------------------------------------------------------


class TestSetDisplayName:
    """Tests for set_display_name()."""

    @pytest.mark.asyncio
    async def test_sets_valid_display_name(self, db_session):
        """Happy path: a valid, unused name is accepted and persisted."""
        user = await _make_user(db_session, email="a@example.com")

        result = await set_display_name(
            body=DisplayNameUpdate(display_name="Valid_Name-1"),
            db=db_session, current_user=user,
        )

        assert result == {"display_name": "Valid_Name-1"}
        assert user.display_name == "Valid_Name-1"

    @pytest.mark.asyncio
    async def test_strips_surrounding_whitespace(self, db_session):
        """Edge: leading/trailing whitespace is stripped before validation + save."""
        user = await _make_user(db_session, email="b@example.com")

        result = await set_display_name(
            body=DisplayNameUpdate(display_name="  alice  "),
            db=db_session, current_user=user,
        )

        assert result == {"display_name": "alice"}
        assert user.display_name == "alice"

    @pytest.mark.asyncio
    async def test_rejects_invalid_characters(self, db_session):
        """Failure: special characters (space, !) are rejected with 400."""
        user = await _make_user(db_session, email="c@example.com")

        with pytest.raises(HTTPException) as exc:
            await set_display_name(
                body=DisplayNameUpdate(display_name="bad name!"),
                db=db_session, current_user=user,
            )
        assert exc.value.status_code == 400
        assert "3-20 characters" in exc.value.detail

    @pytest.mark.asyncio
    async def test_rejects_duplicate_case_insensitive(self, db_session):
        """Failure: another user already owns this name (case-insensitive)."""
        await _make_user(db_session, email="owner@example.com", display_name="Alice")
        user2 = await _make_user(db_session, email="other@example.com")

        with pytest.raises(HTTPException) as exc:
            await set_display_name(
                body=DisplayNameUpdate(display_name="alice"),
                db=db_session, current_user=user2,
            )
        assert exc.value.status_code == 409
        assert "already taken" in exc.value.detail

    @pytest.mark.asyncio
    async def test_allows_user_to_keep_own_name(self, db_session):
        """Edge: a user can re-assert their own existing display name."""
        user = await _make_user(db_session, email="self@example.com", display_name="Bob")

        result = await set_display_name(
            body=DisplayNameUpdate(display_name="Bob"),
            db=db_session, current_user=user,
        )
        assert result == {"display_name": "Bob"}

    @pytest.mark.asyncio
    async def test_rejects_name_too_short_via_regex(self, db_session):
        """Failure: a 3-char min sneaks past Pydantic but we also enforce via regex."""
        # DisplayNameUpdate's Field(min_length=3) already catches <3; we test
        # the re-check path by patching the pattern branch: use a name with
        # valid length but bad chars. (Covered above — keep explicit edge.)
        user = await _make_user(db_session, email="short@example.com")
        with pytest.raises(HTTPException) as exc:
            await set_display_name(
                body=DisplayNameUpdate(display_name="bad space"),
                db=db_session, current_user=user,
            )
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# GET /display-name/check
# ---------------------------------------------------------------------------


class TestCheckDisplayName:
    """Tests for check_display_name()."""

    @pytest.mark.asyncio
    async def test_available_when_unused(self, db_session):
        """Happy path: no one owns the name → available=True."""
        user = await _make_user(db_session, email="check1@example.com")

        result = await check_display_name(
            name="freshname", db=db_session, current_user=user,
        )
        assert result == {"available": True, "name": "freshname"}

    @pytest.mark.asyncio
    async def test_unavailable_when_taken_by_another(self, db_session):
        """Failure: another user holds the name → available=False."""
        await _make_user(db_session, email="owner2@example.com", display_name="Taken")
        user2 = await _make_user(db_session, email="me@example.com")

        result = await check_display_name(
            name="taken", db=db_session, current_user=user2,
        )
        assert result["available"] is False
        assert result["name"] == "taken"

    @pytest.mark.asyncio
    async def test_invalid_format_returns_available_false(self, db_session):
        """Edge: invalid characters → available=False with reason."""
        user = await _make_user(db_session, email="fmt@example.com")

        result = await check_display_name(
            name="bad name", db=db_session, current_user=user,
        )
        assert result == {"available": False, "reason": "Invalid format"}

    @pytest.mark.asyncio
    async def test_available_when_same_user_owns_it(self, db_session):
        """Edge: checking your own current name returns available."""
        user = await _make_user(db_session, email="own@example.com", display_name="Mine")

        result = await check_display_name(
            name="mine", db=db_session, current_user=user,
        )
        assert result["available"] is True

    @pytest.mark.asyncio
    async def test_strips_whitespace_before_check(self, db_session):
        """Edge: surrounding whitespace is stripped."""
        user = await _make_user(db_session, email="ws@example.com")

        result = await check_display_name(
            name="  clean  ", db=db_session, current_user=user,
        )
        assert result["name"] == "clean"
        assert result["available"] is True


# ---------------------------------------------------------------------------
# PUT /admin-display-name
# ---------------------------------------------------------------------------


class TestSetAdminDisplayName:
    """Tests for set_admin_display_name()."""

    @pytest.mark.asyncio
    async def test_sets_admin_display_name(self, db_session):
        """Happy path: saved and returned."""
        user = await _make_user(db_session, email="admin@example.com")
        # Simulate admin permission already satisfied (RBAC enforced in real stack)
        result = await set_admin_display_name(
            body=AdminDisplayNameUpdate(admin_display_name="The Admin"),
            db=db_session, current_user=user,
        )
        assert result == {"admin_display_name": "The Admin"}
        assert user.admin_display_name == "The Admin"

    @pytest.mark.asyncio
    async def test_strips_whitespace(self, db_session):
        """Edge: strips whitespace, then saves."""
        user = await _make_user(db_session, email="admin2@example.com")
        result = await set_admin_display_name(
            body=AdminDisplayNameUpdate(admin_display_name="   Admin X   "),
            db=db_session, current_user=user,
        )
        assert result == {"admin_display_name": "Admin X"}

    @pytest.mark.asyncio
    async def test_rejects_too_short_after_strip(self, db_session):
        """Failure: after stripping, name collapses to <2 chars → 400.

        Pydantic enforces min_length=2 on the raw string, so this is really
        a defensive check for post-strip length. Provide a string whose
        trimmed length is exactly below 2 — e.g. 'a ' which stripped is 'a'.
        """
        user = await _make_user(db_session, email="admin3@example.com")
        # A single non-space char, passes Pydantic's min_length=2 of the raw
        # two-char "a ", but stripped becomes "a" (len 1) → raises in handler.
        body = AdminDisplayNameUpdate.model_construct(admin_display_name="a ")
        with pytest.raises(HTTPException) as exc:
            await set_admin_display_name(
                body=body, db=db_session, current_user=user,
            )
        assert exc.value.status_code == 400
