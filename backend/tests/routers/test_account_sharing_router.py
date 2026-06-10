"""
Tests for backend/app/routers/account_sharing_router.py
and backend/app/services/account_sharing_service.py

TDD: these tests were written before the implementation.

Coverage:
  - create_invitation (service)
  - preview_invitation / accept / decline
  - revoke_invitation
  - list_members / update_member_role / remove_member
  - get_account_role dependency
  - Access control: owner vs manager vs observer vs unrelated user
  - Security: email mismatch, expired tokens, double-accept
"""

import pytest
from app.utils.timeutil import utcnow
from datetime import timedelta

from app.models import Account, User
from app.models.sharing import AccountInvitation, AccountMembership, AccountMembershipEvent


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def owner(db_session):
    """The account owner."""
    user = User(
        email="owner@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def member_user(db_session):
    """A user who will be invited."""
    user = User(
        email="member@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def observer_user(db_session):
    """A second invitee for multi-member tests."""
    user = User(
        email="observer@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def outsider(db_session):
    """A user with no relationship to the account."""
    user = User(
        email="outsider@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def shared_account(db_session, owner):
    """A CEX account owned by `owner`."""
    account = Account(
        user_id=owner.id,
        name="Coinbase Main",
        type="cex",
        exchange="coinbase",
        is_default=True,
        is_active=True,
    )
    db_session.add(account)
    await db_session.flush()
    return account


@pytest.fixture
async def manager_membership(db_session, shared_account, member_user, owner):
    """A manager membership for member_user on shared_account."""
    m = AccountMembership(
        account_id=shared_account.id,
        user_id=member_user.id,
        role="manager",
        invited_by_user_id=owner.id,
    )
    db_session.add(m)
    await db_session.flush()
    return m


@pytest.fixture
async def observer_membership(db_session, shared_account, observer_user, owner):
    """A shadow membership for observer_user on shared_account."""
    m = AccountMembership(
        account_id=shared_account.id,
        user_id=observer_user.id,
        role="shadow",
        invited_by_user_id=owner.id,
    )
    db_session.add(m)
    await db_session.flush()
    return m


@pytest.fixture
async def pending_invitation(db_session, shared_account, owner):
    """A valid pending invitation for member@example.com."""
    inv = AccountInvitation(
        account_id=shared_account.id,
        invited_email="member@example.com",
        invited_by_user_id=owner.id,
        role="manager",
        token="validtoken123abc",
        expires_at=utcnow() + timedelta(days=7),
    )
    db_session.add(inv)
    await db_session.flush()
    return inv


@pytest.fixture
async def expired_invitation(db_session, shared_account, owner):
    """An invitation that has already expired."""
    inv = AccountInvitation(
        account_id=shared_account.id,
        invited_email="member@example.com",
        invited_by_user_id=owner.id,
        role="manager",
        token="expiredtoken456def",
        expires_at=utcnow() - timedelta(days=1),
    )
    db_session.add(inv)
    await db_session.flush()
    return inv


# =============================================================================
# Service: create_invitation
# =============================================================================


class TestCreateInvitation:
    """Tests for account_sharing_service.create_invitation()"""

    @pytest.mark.asyncio
    async def test_create_invitation_happy_path(self, db_session, shared_account, owner):
        """Happy path: owner creates a valid invitation for a new email."""
        from app.services.account_sharing_service import create_invitation

        inv = await create_invitation(db_session, shared_account.id, "newuser@example.com", "manager", owner)
        await db_session.flush()

        assert inv.id is not None
        assert inv.invited_email == "newuser@example.com"
        assert inv.role == "manager"
        assert inv.token is not None
        assert len(inv.token) >= 32
        assert inv.accepted_at is None
        assert inv.is_pending is True

    @pytest.mark.asyncio
    async def test_create_invitation_shadow_role(self, db_session, shared_account, owner):
        """Happy path: can invite as shadow."""
        from app.services.account_sharing_service import create_invitation

        inv = await create_invitation(db_session, shared_account.id, "watcher@example.com", "shadow", owner)
        assert inv.role == "shadow"

    @pytest.mark.asyncio
    async def test_create_invitation_self_raises(self, db_session, shared_account, owner):
        """Failure: cannot invite yourself."""
        from app.services.account_sharing_service import create_invitation

        with pytest.raises(ValueError, match="cannot invite yourself"):
            await create_invitation(db_session, shared_account.id, owner.email, "manager", owner)

    @pytest.mark.asyncio
    async def test_create_invitation_invalid_role_raises(self, db_session, shared_account, owner):
        """Failure: invalid role raises ValueError."""
        from app.services.account_sharing_service import create_invitation

        with pytest.raises(ValueError, match="Invalid role"):
            await create_invitation(db_session, shared_account.id, "x@example.com", "owner", owner)

    @pytest.mark.asyncio
    async def test_create_invitation_existing_member_raises(
        self, db_session, shared_account, owner, member_user, manager_membership
    ):
        """Failure: cannot invite someone already a member."""
        from app.services.account_sharing_service import create_invitation

        with pytest.raises(ValueError, match="already a member"):
            await create_invitation(db_session, shared_account.id, member_user.email, "shadow", owner)

    @pytest.mark.asyncio
    async def test_create_invitation_duplicate_pending_raises(
        self, db_session, shared_account, owner, pending_invitation
    ):
        """Failure: cannot create a second pending invitation for the same email."""
        from app.services.account_sharing_service import create_invitation

        with pytest.raises(ValueError, match="pending invitation"):
            await create_invitation(db_session, shared_account.id, "member@example.com", "shadow", owner)

    @pytest.mark.asyncio
    async def test_create_invitation_email_normalized_to_lowercase(
        self, db_session, shared_account, owner
    ):
        """Edge case: email is stored lowercase regardless of input case."""
        from app.services.account_sharing_service import create_invitation

        inv = await create_invitation(db_session, shared_account.id, "NewUser@Example.COM", "manager", owner)
        assert inv.invited_email == "newuser@example.com"

    @pytest.mark.asyncio
    async def test_create_invitation_logs_audit_event(self, db_session, shared_account, owner):
        """Happy path: creates an audit event of type 'invited'."""
        from sqlalchemy import select
        from app.services.account_sharing_service import create_invitation

        await create_invitation(db_session, shared_account.id, "audit@example.com", "manager", owner)
        await db_session.flush()

        result = await db_session.execute(
            select(AccountMembershipEvent).where(
                AccountMembershipEvent.account_id == shared_account.id,
                AccountMembershipEvent.event_type == "invited",
            )
        )
        event = result.scalar_one_or_none()
        assert event is not None
        assert event.actor_user_id == owner.id
        assert event.new_role == "manager"


# =============================================================================
# Service: preview_invitation
# =============================================================================


class TestPreviewInvitation:
    """Tests for account_sharing_service.preview_invitation()"""

    @pytest.mark.asyncio
    async def test_preview_valid_token_correct_email(
        self, db_session, shared_account, owner, member_user, pending_invitation
    ):
        """Happy path: member_user previews their own invitation."""
        from app.services.account_sharing_service import preview_invitation

        result = await preview_invitation(db_session, pending_invitation.token, member_user)

        assert result["role"] == "manager"
        assert "Coinbase Main" in result["account_name"]
        assert result["invited_by"] is not None

    @pytest.mark.asyncio
    async def test_preview_wrong_email_raises(
        self, db_session, outsider, pending_invitation
    ):
        """Failure: user with wrong email gets PermissionError."""
        from app.services.account_sharing_service import preview_invitation

        with pytest.raises(PermissionError, match="different email"):
            await preview_invitation(db_session, pending_invitation.token, outsider)

    @pytest.mark.asyncio
    async def test_preview_expired_token_raises(
        self, db_session, member_user, expired_invitation
    ):
        """Failure: expired invitation raises ValueError."""
        from app.services.account_sharing_service import preview_invitation

        with pytest.raises(ValueError, match="expired"):
            await preview_invitation(db_session, expired_invitation.token, member_user)

    @pytest.mark.asyncio
    async def test_preview_nonexistent_token_raises(self, db_session, member_user):
        """Failure: unknown token raises ValueError."""
        from app.services.account_sharing_service import preview_invitation

        with pytest.raises(ValueError, match="Invalid"):
            await preview_invitation(db_session, "doesnotexist", member_user)


# =============================================================================
# Service: accept_invitation
# =============================================================================


class TestAcceptInvitation:
    """Tests for account_sharing_service.accept_invitation()"""

    @pytest.mark.asyncio
    async def test_accept_creates_membership(
        self, db_session, shared_account, member_user, pending_invitation
    ):
        """Happy path: accepting creates an AccountMembership record."""
        from app.services.account_sharing_service import accept_invitation

        membership = await accept_invitation(db_session, pending_invitation.token, member_user)
        await db_session.flush()

        assert membership.account_id == shared_account.id
        assert membership.user_id == member_user.id
        assert membership.role == "manager"

    @pytest.mark.asyncio
    async def test_accept_marks_invitation_used(
        self, db_session, member_user, pending_invitation
    ):
        """Happy path: invitation.accepted_at is set after accept."""
        from app.services.account_sharing_service import accept_invitation

        await accept_invitation(db_session, pending_invitation.token, member_user)
        await db_session.flush()

        assert pending_invitation.accepted_at is not None
        assert pending_invitation.is_pending is False

    @pytest.mark.asyncio
    async def test_accept_wrong_email_raises(
        self, db_session, outsider, pending_invitation
    ):
        """Security: user with non-matching email cannot accept."""
        from app.services.account_sharing_service import accept_invitation

        with pytest.raises(PermissionError, match="different email"):
            await accept_invitation(db_session, pending_invitation.token, outsider)

    @pytest.mark.asyncio
    async def test_accept_expired_invitation_raises(
        self, db_session, member_user, expired_invitation
    ):
        """Failure: cannot accept expired invitation."""
        from app.services.account_sharing_service import accept_invitation

        with pytest.raises(ValueError, match="expired"):
            await accept_invitation(db_session, expired_invitation.token, member_user)

    @pytest.mark.asyncio
    async def test_accept_already_accepted_raises(
        self, db_session, member_user, pending_invitation
    ):
        """Failure: double-accept raises ValueError."""
        from app.services.account_sharing_service import accept_invitation

        await accept_invitation(db_session, pending_invitation.token, member_user)
        await db_session.flush()

        with pytest.raises(ValueError, match="already been accepted"):
            await accept_invitation(db_session, pending_invitation.token, member_user)

    @pytest.mark.asyncio
    async def test_accept_revoked_invitation_raises(
        self, db_session, shared_account, owner, member_user
    ):
        """Failure: cannot accept a revoked invitation."""
        from app.services.account_sharing_service import accept_invitation

        inv = AccountInvitation(
            account_id=shared_account.id,
            invited_email=member_user.email,
            invited_by_user_id=owner.id,
            role="shadow",
            token="revokedtoken789",
            expires_at=utcnow() + timedelta(days=7),
            revoked_at=utcnow(),
        )
        db_session.add(inv)
        await db_session.flush()

        with pytest.raises(ValueError, match="revoked"):
            await accept_invitation(db_session, inv.token, member_user)

    @pytest.mark.asyncio
    async def test_accept_logs_audit_event(
        self, db_session, member_user, pending_invitation
    ):
        """Happy path: accept creates an 'accepted' audit event."""
        from sqlalchemy import select
        from app.services.account_sharing_service import accept_invitation

        await accept_invitation(db_session, pending_invitation.token, member_user)
        await db_session.flush()

        result = await db_session.execute(
            select(AccountMembershipEvent).where(
                AccountMembershipEvent.account_id == pending_invitation.account_id,
                AccountMembershipEvent.event_type == "accepted",
            )
        )
        assert result.scalar_one_or_none() is not None


# =============================================================================
# Service: decline_invitation
# =============================================================================


class TestDeclineInvitation:
    """Tests for account_sharing_service.decline_invitation()"""

    @pytest.mark.asyncio
    async def test_decline_marks_invitation_declined(
        self, db_session, member_user, pending_invitation
    ):
        """Happy path: declined_at is set and is_pending becomes False."""
        from app.services.account_sharing_service import decline_invitation

        await decline_invitation(db_session, pending_invitation.token, member_user)
        await db_session.flush()

        assert pending_invitation.declined_at is not None
        assert pending_invitation.is_pending is False

    @pytest.mark.asyncio
    async def test_decline_wrong_email_raises(
        self, db_session, outsider, pending_invitation
    ):
        """Security: wrong email cannot decline."""
        from app.services.account_sharing_service import decline_invitation

        with pytest.raises(PermissionError, match="different email"):
            await decline_invitation(db_session, pending_invitation.token, outsider)


# =============================================================================
# Service: revoke_invitation
# =============================================================================


class TestRevokeInvitation:
    """Tests for account_sharing_service.revoke_invitation()"""

    @pytest.mark.asyncio
    async def test_revoke_pending_invitation_succeeds(
        self, db_session, shared_account, owner, pending_invitation
    ):
        """Happy path: owner can revoke a pending invitation."""
        from app.services.account_sharing_service import revoke_invitation

        await revoke_invitation(db_session, pending_invitation.id, shared_account.id, owner)
        await db_session.flush()

        assert pending_invitation.revoked_at is not None
        assert pending_invitation.is_pending is False

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_raises(self, db_session, shared_account, owner):
        """Failure: revoking nonexistent invitation raises ValueError."""
        from app.services.account_sharing_service import revoke_invitation

        with pytest.raises(ValueError, match="not found"):
            await revoke_invitation(db_session, 99999, shared_account.id, owner)

    @pytest.mark.asyncio
    async def test_revoke_already_accepted_raises(
        self, db_session, shared_account, owner, member_user, pending_invitation
    ):
        """Failure: cannot revoke an already-accepted invitation."""
        from app.services.account_sharing_service import (
            accept_invitation, revoke_invitation,
        )

        await accept_invitation(db_session, pending_invitation.token, member_user)
        await db_session.flush()

        with pytest.raises(ValueError, match="no longer pending"):
            await revoke_invitation(db_session, pending_invitation.id, shared_account.id, owner)


# =============================================================================
# Service: list_members
# =============================================================================


class TestListMembers:
    """Tests for account_sharing_service.list_members()"""

    @pytest.mark.asyncio
    async def test_list_members_returns_active_members(
        self, db_session, shared_account, manager_membership, member_user
    ):
        """Happy path: returns members with correct fields."""
        from app.services.account_sharing_service import list_members

        members = await list_members(db_session, shared_account.id)

        assert len(members) == 1
        assert members[0]["user_id"] == member_user.id
        assert members[0]["role"] == "manager"
        assert members[0]["email"] == member_user.email

    @pytest.mark.asyncio
    async def test_list_members_excludes_expired(
        self, db_session, shared_account, owner, member_user
    ):
        """Edge case: expired memberships are excluded from the list."""
        from app.services.account_sharing_service import list_members

        expired = AccountMembership(
            account_id=shared_account.id,
            user_id=member_user.id,
            role="shadow",
            invited_by_user_id=owner.id,
            expires_at=utcnow() - timedelta(hours=1),
        )
        db_session.add(expired)
        await db_session.flush()

        members = await list_members(db_session, shared_account.id)
        assert len(members) == 0

    @pytest.mark.asyncio
    async def test_list_members_empty_account(self, db_session, shared_account):
        """Edge case: account with no members returns empty list."""
        from app.services.account_sharing_service import list_members

        members = await list_members(db_session, shared_account.id)
        assert members == []

    @pytest.mark.asyncio
    async def test_list_members_redacts_email_for_non_owner(
        self, db_session, shared_account, manager_membership, member_user
    ):
        """Privacy: non-owner callers see display_name only; email is null."""
        from app.services.account_sharing_service import list_members

        members = await list_members(
            db_session, shared_account.id, caller_role="shadow"
        )
        assert len(members) == 1
        assert members[0]["email"] is None
        assert members[0]["display_name"] == member_user.display_name
        # invited_by must not fall back to inviter email either
        if members[0]["invited_by"] is not None:
            assert "@" not in members[0]["invited_by"]

    @pytest.mark.asyncio
    async def test_list_members_owner_sees_email(
        self, db_session, shared_account, manager_membership, member_user
    ):
        """Happy path: owner caller sees the full email field (default role="owner")."""
        from app.services.account_sharing_service import list_members

        members = await list_members(
            db_session, shared_account.id, caller_role="owner"
        )
        assert len(members) == 1
        assert members[0]["email"] == member_user.email


# =============================================================================
# Service: update_member_role
# =============================================================================


class TestUpdateMemberRole:
    """Tests for account_sharing_service.update_member_role()"""

    @pytest.mark.asyncio
    async def test_update_role_succeeds(
        self, db_session, shared_account, owner, member_user, manager_membership
    ):
        """Happy path: owner can change manager to shadow."""
        from app.services.account_sharing_service import update_member_role

        updated = await update_member_role(
            db_session, shared_account.id, member_user.id, "shadow", owner
        )
        await db_session.flush()

        assert updated.role == "shadow"

    @pytest.mark.asyncio
    async def test_update_role_invalid_role_raises(
        self, db_session, shared_account, owner, member_user, manager_membership
    ):
        """Failure: invalid role string raises ValueError."""
        from app.services.account_sharing_service import update_member_role

        with pytest.raises(ValueError, match="Invalid role"):
            await update_member_role(
                db_session, shared_account.id, member_user.id, "owner", owner
            )

    @pytest.mark.asyncio
    async def test_update_role_nonexistent_member_raises(
        self, db_session, shared_account, owner
    ):
        """Failure: membership not found raises ValueError."""
        from app.services.account_sharing_service import update_member_role

        with pytest.raises(ValueError, match="not found"):
            await update_member_role(db_session, shared_account.id, 99999, "shadow", owner)

    @pytest.mark.asyncio
    async def test_update_role_logs_audit_event(
        self, db_session, shared_account, owner, member_user, manager_membership
    ):
        """Happy path: role change creates audit event."""
        from sqlalchemy import select
        from app.services.account_sharing_service import update_member_role

        await update_member_role(db_session, shared_account.id, member_user.id, "shadow", owner)
        await db_session.flush()

        result = await db_session.execute(
            select(AccountMembershipEvent).where(
                AccountMembershipEvent.account_id == shared_account.id,
                AccountMembershipEvent.event_type == "role_changed",
            )
        )
        event = result.scalar_one_or_none()
        assert event is not None
        assert event.old_role == "manager"
        assert event.new_role == "shadow"


# =============================================================================
# Service: remove_member
# =============================================================================


class TestRemoveMember:
    """Tests for account_sharing_service.remove_member()"""

    @pytest.mark.asyncio
    async def test_owner_can_remove_member(
        self, db_session, shared_account, owner, member_user, manager_membership
    ):
        """Happy path: owner removes a member successfully."""
        from sqlalchemy import select
        from app.services.account_sharing_service import remove_member

        await remove_member(db_session, shared_account.id, member_user.id, owner)
        await db_session.flush()

        result = await db_session.execute(
            select(AccountMembership).where(
                AccountMembership.account_id == shared_account.id,
                AccountMembership.user_id == member_user.id,
            )
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_member_can_remove_themselves(
        self, db_session, shared_account, member_user, manager_membership
    ):
        """Happy path: a member can leave by removing themselves."""
        from sqlalchemy import select
        from app.services.account_sharing_service import remove_member

        await remove_member(db_session, shared_account.id, member_user.id, member_user)
        await db_session.flush()

        result = await db_session.execute(
            select(AccountMembership).where(
                AccountMembership.account_id == shared_account.id,
                AccountMembership.user_id == member_user.id,
            )
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_cannot_remove_account_owner(
        self, db_session, shared_account, owner, member_user, manager_membership
    ):
        """Security: cannot remove the account owner (account.user_id)."""
        from app.services.account_sharing_service import remove_member

        with pytest.raises(ValueError, match="owner cannot be removed"):
            await remove_member(db_session, shared_account.id, owner.id, owner)

    @pytest.mark.asyncio
    async def test_remove_nonexistent_member_raises(
        self, db_session, shared_account, owner
    ):
        """Failure: removing a non-member raises ValueError."""
        from app.services.account_sharing_service import remove_member

        with pytest.raises(ValueError, match="not found"):
            await remove_member(db_session, shared_account.id, 99999, owner)

    @pytest.mark.asyncio
    async def test_self_removal_logs_left_event(
        self, db_session, shared_account, member_user, manager_membership
    ):
        """Happy path: self-removal logs event_type='left'."""
        from sqlalchemy import select
        from app.services.account_sharing_service import remove_member

        await remove_member(db_session, shared_account.id, member_user.id, member_user)
        await db_session.flush()

        result = await db_session.execute(
            select(AccountMembershipEvent).where(
                AccountMembershipEvent.account_id == shared_account.id,
                AccountMembershipEvent.event_type == "left",
            )
        )
        assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_owner_removal_logs_removed_event(
        self, db_session, shared_account, owner, member_user, manager_membership
    ):
        """Happy path: owner removing a member logs event_type='removed'."""
        from sqlalchemy import select
        from app.services.account_sharing_service import remove_member

        await remove_member(db_session, shared_account.id, member_user.id, owner)
        await db_session.flush()

        result = await db_session.execute(
            select(AccountMembershipEvent).where(
                AccountMembershipEvent.account_id == shared_account.id,
                AccountMembershipEvent.event_type == "removed",
            )
        )
        assert result.scalar_one_or_none() is not None


# =============================================================================
# Auth dependency: get_account_role
# =============================================================================


class TestGetAccountRole:
    """Tests for auth.dependencies.get_account_role()"""

    @pytest.mark.asyncio
    async def test_owner_returns_owner_role(self, db_session, shared_account, owner):
        """Happy path: account owner gets role='owner'."""
        from app.auth.dependencies import get_account_role

        role = await get_account_role(shared_account.id, owner, db_session)
        assert role == "owner"

    @pytest.mark.asyncio
    async def test_manager_returns_manager_role(
        self, db_session, shared_account, member_user, manager_membership
    ):
        """Happy path: manager member gets role='manager'."""
        from app.auth.dependencies import get_account_role

        role = await get_account_role(shared_account.id, member_user, db_session)
        assert role == "manager"

    @pytest.mark.asyncio
    async def test_shadow_returns_shadow_role(
        self, db_session, shared_account, observer_user, observer_membership
    ):
        """Happy path: shadow member gets role='shadow'."""
        from app.auth.dependencies import get_account_role

        role = await get_account_role(shared_account.id, observer_user, db_session)
        assert role == "shadow"

    @pytest.mark.asyncio
    async def test_unrelated_user_returns_none(
        self, db_session, shared_account, outsider
    ):
        """Security: user with no access returns None."""
        from app.auth.dependencies import get_account_role

        role = await get_account_role(shared_account.id, outsider, db_session)
        assert role is None

    @pytest.mark.asyncio
    async def test_nonexistent_account_returns_none(self, db_session, owner):
        """Edge case: non-existent account_id returns None."""
        from app.auth.dependencies import get_account_role

        role = await get_account_role(99999, owner, db_session)
        assert role is None

    @pytest.mark.asyncio
    async def test_expired_membership_returns_none(
        self, db_session, shared_account, owner, member_user
    ):
        """Edge case: expired membership is treated as no access."""
        from app.auth.dependencies import get_account_role

        expired = AccountMembership(
            account_id=shared_account.id,
            user_id=member_user.id,
            role="manager",
            invited_by_user_id=owner.id,
            expires_at=utcnow() - timedelta(hours=1),
        )
        db_session.add(expired)
        await db_session.flush()

        role = await get_account_role(shared_account.id, member_user, db_session)
        assert role is None


# =============================================================================
# Access control integration
# =============================================================================


class TestAccessControl:
    """Integration tests: account list/get includes shared accounts."""

    @pytest.mark.asyncio
    async def test_list_pending_invitations_for_user(
        self, db_session, member_user, shared_account, pending_invitation
    ):
        """Happy path: user can see their inbound pending invitations."""
        from app.services.account_sharing_service import list_pending_invitations_for_user

        results = await list_pending_invitations_for_user(db_session, member_user.email)

        assert len(results) == 1
        assert results[0]["token"] == pending_invitation.token
        assert results[0]["role"] == "manager"

    @pytest.mark.asyncio
    async def test_list_pending_invitations_excludes_expired(
        self, db_session, member_user, shared_account, expired_invitation
    ):
        """Edge case: expired invitations don't appear as pending."""
        from app.services.account_sharing_service import list_pending_invitations_for_user

        results = await list_pending_invitations_for_user(db_session, member_user.email)
        assert results == []

    @pytest.mark.asyncio
    async def test_list_pending_invitations_for_account(
        self, db_session, shared_account, pending_invitation
    ):
        """Happy path: owner sees outbound pending invitations for account."""
        from app.services.account_sharing_service import list_pending_invitations_for_account

        results = await list_pending_invitations_for_account(db_session, shared_account.id)

        assert len(results) == 1
        assert results[0]["invited_email"] == "member@example.com"

    @pytest.mark.asyncio
    async def test_list_pending_invitations_for_account_excludes_accepted(
        self, db_session, shared_account, member_user, pending_invitation
    ):
        """Edge case: accepted invitations don't appear in pending list."""
        from app.services.account_sharing_service import (
            accept_invitation, list_pending_invitations_for_account,
        )

        await accept_invitation(db_session, pending_invitation.token, member_user)
        await db_session.flush()

        results = await list_pending_invitations_for_account(db_session, shared_account.id)
        assert results == []


# =============================================================================
# AccountInvitation.is_pending property
# =============================================================================


class TestAccountInvitationIsPending:
    """Unit tests for AccountInvitation.is_pending property."""

    def test_fresh_invitation_is_pending(self):
        inv = AccountInvitation(
            expires_at=utcnow() + timedelta(days=7),
        )
        assert inv.is_pending is True

    def test_accepted_invitation_not_pending(self):
        inv = AccountInvitation(
            expires_at=utcnow() + timedelta(days=7),
            accepted_at=utcnow(),
        )
        assert inv.is_pending is False

    def test_declined_invitation_not_pending(self):
        inv = AccountInvitation(
            expires_at=utcnow() + timedelta(days=7),
            declined_at=utcnow(),
        )
        assert inv.is_pending is False

    def test_revoked_invitation_not_pending(self):
        inv = AccountInvitation(
            expires_at=utcnow() + timedelta(days=7),
            revoked_at=utcnow(),
        )
        assert inv.is_pending is False

    def test_expired_invitation_not_pending(self):
        inv = AccountInvitation(
            expires_at=utcnow() - timedelta(seconds=1),
        )
        assert inv.is_pending is False


# =============================================================================
# AccountMembership.is_expired property
# =============================================================================


class TestAccountMembershipIsExpired:
    """Unit tests for AccountMembership.is_expired property."""

    def test_no_expiry_not_expired(self):
        m = AccountMembership(expires_at=None)
        assert m.is_expired is False

    def test_future_expiry_not_expired(self):
        m = AccountMembership(expires_at=utcnow() + timedelta(days=30))
        assert m.is_expired is False

    def test_past_expiry_is_expired(self):
        m = AccountMembership(expires_at=utcnow() - timedelta(seconds=1))
        assert m.is_expired is True


# =============================================================================
# M3: Invite rate limiting (max 10 per account per hour)
# =============================================================================


class TestInviteRateLimit:
    """Tests for the in-memory invite rate limits on POST /invite.

    Rate limits live in app.services.user_rate_limit — the per-account cap
    is 10/hr and the per-inviter global cap is 30/hr.
    """

    @pytest.fixture(autouse=True)
    def _clear_rate_state(self):
        from app.services import user_rate_limit
        user_rate_limit._buckets.clear()
        yield
        user_rate_limit._buckets.clear()

    @pytest.mark.asyncio
    async def test_invite_succeeds_when_under_limit(self, db_session, shared_account, owner, member_user):
        """Happy path: invite is created when under both rate limits."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.routers.account_sharing_router import invite_member, InviteRequest
        from app.services.user_rate_limit import check_user_rate_limit

        # Seed 9 prior per-account entries (one under the 10/hr cap)
        for _ in range(9):
            check_user_rate_limit(
                user_id=owner.id,
                bucket=f"invite_account:{shared_account.id}",
                max_requests=10,
                window_seconds=3600,
            )

        body = InviteRequest(email="newguest@example.com", role="shadow")

        mock_inv = AccountInvitation(
            account_id=shared_account.id,
            invited_email="newguest@example.com",
            invited_by_user_id=owner.id,
            role="shadow",
            token="freshtoken999",
            expires_at=utcnow() + timedelta(days=7),
        )
        mock_inv.id = 999

        registry = MagicMock()
        registry.broadcast = MagicMock()
        registry.broadcast.send_to_user = AsyncMock()

        with patch("app.routers.account_sharing_router.svc.create_invitation", new_callable=AsyncMock,
                   return_value=mock_inv), \
             patch("app.routers.account_sharing_router.send_invitation_email"):
            result = await invite_member(
                account_id=shared_account.id,
                body=body,
                account_role="owner",
                current_user=owner,
                db=db_session,
                registry=registry,
            )

        assert result["invitation_id"] == 999

    @pytest.mark.asyncio
    async def test_invite_returns_429_at_per_account_limit(self, db_session, shared_account, owner):
        """Failure: 429 raised after 10 invites for a single account in an hour."""
        from unittest.mock import MagicMock
        from fastapi import HTTPException
        from app.routers.account_sharing_router import invite_member, InviteRequest
        from app.services.user_rate_limit import check_user_rate_limit

        for _ in range(10):
            check_user_rate_limit(
                user_id=owner.id,
                bucket=f"invite_account:{shared_account.id}",
                max_requests=10,
                window_seconds=3600,
            )

        body = InviteRequest(email="blocked@example.com", role="shadow")
        registry = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await invite_member(
                account_id=shared_account.id,
                body=body,
                account_role="owner",
                current_user=owner,
                db=db_session,
                registry=registry,
            )

        assert exc_info.value.status_code == 429
        assert "account" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_invite_returns_429_at_global_inviter_limit(self, db_session, shared_account, owner):
        """Failure: 429 raised after 30 invites across any accounts in an hour."""
        from unittest.mock import MagicMock
        from fastapi import HTTPException
        from app.routers.account_sharing_router import invite_member, InviteRequest
        from app.services.user_rate_limit import check_user_rate_limit

        # Fill the global bucket but leave the per-account bucket empty so we
        # specifically exercise the inviter-wide cap.
        for _ in range(30):
            check_user_rate_limit(
                user_id=owner.id,
                bucket="invite_global",
                max_requests=30,
                window_seconds=3600,
            )

        body = InviteRequest(email="blocked@example.com", role="shadow")
        registry = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await invite_member(
                account_id=shared_account.id,
                body=body,
                account_role="owner",
                current_user=owner,
                db=db_session,
                registry=registry,
            )

        assert exc_info.value.status_code == 429
        assert "invitation" in exc_info.value.detail.lower()
