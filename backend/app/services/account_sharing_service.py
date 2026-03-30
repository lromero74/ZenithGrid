"""
Account Sharing Service

Business logic for account co-management:
  - Creating and validating invitations
  - Accepting / declining / revoking invitations
  - Managing memberships (add, change role, remove)
  - Audit event logging

Security invariants enforced here:
  - invited_email must match current_user.email on accept/decline
  - Tokens are single-use (is_pending checks all termination states)
  - Only 'manager' and 'shadow' roles can be granted (not 'owner')
  - Account owner (account.user_id) cannot be removed via membership delete
"""

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, User
from app.models.sharing import AccountInvitation, AccountMembership, AccountMembershipEvent

INVITATION_TTL_DAYS = 7
_VALID_ROLES = frozenset(("manager", "shadow"))

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Invitation management
# ---------------------------------------------------------------------------

async def create_invitation(
    db: AsyncSession,
    account_id: int,
    invited_email: str,
    role: str,
    inviter: User,
) -> AccountInvitation:
    """
    Create a pending invitation for invited_email to join account_id with role.

    Raises ValueError for: invalid role, self-invite, existing member,
    or duplicate pending invitation.
    """
    if role not in _VALID_ROLES:
        raise ValueError(f"Invalid role: {role!r}. Must be 'manager' or 'shadow'.")

    normalized_email = invited_email.lower().strip()

    if normalized_email == inviter.email.lower():
        raise ValueError("You cannot invite yourself.")

    # Check if the invitee is already a member (by looking up their user account)
    existing_user = await _get_user_by_email(db, normalized_email)
    if existing_user:
        existing_membership = await db.execute(
            select(AccountMembership).where(
                AccountMembership.account_id == account_id,
                AccountMembership.user_id == existing_user.id,
            )
        )
        if existing_membership.scalar_one_or_none():
            raise ValueError(f"{normalized_email} is already a member of this account.")

    # Check for a duplicate pending invitation
    dup = await db.execute(
        select(AccountInvitation).where(
            AccountInvitation.account_id == account_id,
            AccountInvitation.invited_email == normalized_email,
            AccountInvitation.accepted_at.is_(None),
            AccountInvitation.declined_at.is_(None),
            AccountInvitation.revoked_at.is_(None),
            AccountInvitation.expires_at > datetime.utcnow(),
        )
    )
    if dup.scalar_one_or_none():
        raise ValueError(
            f"A pending invitation for {normalized_email} already exists. "
            "Revoke the existing one first if you want to change the role."
        )

    token = uuid.uuid4().hex  # 32-char hex, unique
    invitation = AccountInvitation(
        account_id=account_id,
        invited_email=normalized_email,
        invited_by_user_id=inviter.id,
        role=role,
        token=token,
        expires_at=datetime.utcnow() + timedelta(days=INVITATION_TTL_DAYS),
    )
    db.add(invitation)
    await db.flush()

    await _log_event(
        db,
        account_id=account_id,
        actor_user_id=inviter.id,
        target_user_id=existing_user.id if existing_user else None,
        event_type="invited",
        new_role=role,
        notes=normalized_email,
    )

    return invitation


async def preview_invitation(
    db: AsyncSession,
    token: str,
    current_user: User,
) -> dict:
    """
    Return preview details for an invitation token.

    Validates:
    - Token exists and is pending
    - current_user.email matches invited_email

    Returns a dict with account_name, invited_by, role, expires_at.
    """
    invitation = await _get_pending_invitation(db, token)
    _assert_email_match(invitation, current_user)

    account = await db.get(Account, invitation.account_id)
    inviter = await db.get(User, invitation.invited_by_user_id)

    return {
        "invitation_id": invitation.id,
        "account_name": account.get_display_name() if account else "Unknown Account",
        "invited_by": (inviter.display_name or inviter.email) if inviter else "Unknown",
        "role": invitation.role,
        "expires_at": invitation.expires_at.isoformat(),
    }


async def accept_invitation(
    db: AsyncSession,
    token: str,
    current_user: User,
) -> AccountMembership:
    """
    Accept an invitation. Creates an AccountMembership record.

    Security: only the user authenticated as invited_email may accept.
    """
    invitation = await _get_pending_invitation(db, token)
    _assert_email_match(invitation, current_user)

    membership = AccountMembership(
        account_id=invitation.account_id,
        user_id=current_user.id,
        role=invitation.role,
        invited_by_user_id=invitation.invited_by_user_id,
    )
    db.add(membership)

    invitation.accepted_at = datetime.utcnow()
    await db.flush()

    await _log_event(
        db,
        account_id=invitation.account_id,
        actor_user_id=current_user.id,
        event_type="accepted",
        new_role=invitation.role,
    )

    return membership


async def decline_invitation(
    db: AsyncSession,
    token: str,
    current_user: User,
) -> None:
    """
    Decline an invitation. Marks it declined; no membership is created.

    Security: only the user authenticated as invited_email may decline.
    """
    invitation = await _get_pending_invitation(db, token)
    _assert_email_match(invitation, current_user)

    invitation.declined_at = datetime.utcnow()
    await db.flush()

    await _log_event(
        db,
        account_id=invitation.account_id,
        actor_user_id=current_user.id,
        event_type="declined",
        new_role=invitation.role,
    )


async def revoke_invitation(
    db: AsyncSession,
    invitation_id: int,
    account_id: int,
    actor: User,
) -> None:
    """
    Revoke a pending outbound invitation. Only the account owner should call this.

    Raises ValueError if invitation not found or no longer pending.
    """
    result = await db.execute(
        select(AccountInvitation).where(
            AccountInvitation.id == invitation_id,
            AccountInvitation.account_id == account_id,
        )
    )
    invitation = result.scalar_one_or_none()
    if not invitation:
        raise ValueError("Invitation not found.")
    if not invitation.is_pending:
        raise ValueError("Invitation is no longer pending and cannot be revoked.")

    invitation.revoked_at = datetime.utcnow()
    await db.flush()

    await _log_event(
        db,
        account_id=account_id,
        actor_user_id=actor.id,
        event_type="invite_revoked",
        new_role=invitation.role,
        notes=invitation.invited_email,
    )


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------

async def list_members(
    db: AsyncSession,
    account_id: int,
) -> list[dict]:
    """Return all active (non-expired) members for an account."""
    result = await db.execute(
        select(AccountMembership).where(
            AccountMembership.account_id == account_id,
        )
    )
    memberships = result.scalars().all()

    members = []
    for m in memberships:
        if m.is_expired:
            continue
        user = await db.get(User, m.user_id)
        inviter = await db.get(User, m.invited_by_user_id) if m.invited_by_user_id else None
        members.append({
            "user_id": m.user_id,
            "email": user.email if user else "unknown",
            "display_name": user.display_name if user else None,
            "role": m.role,
            "joined_at": m.joined_at.isoformat(),
            "expires_at": m.expires_at.isoformat() if m.expires_at else None,
            "invited_by": (inviter.display_name or inviter.email) if inviter else None,
        })
    return members


async def update_member_role(
    db: AsyncSession,
    account_id: int,
    target_user_id: int,
    new_role: str,
    actor: User,
) -> AccountMembership:
    """
    Change a member's role. Only the account owner should call this
    (enforced at the router level via require_account_access("owner")).

    Raises ValueError for invalid role or membership not found.
    """
    if new_role not in _VALID_ROLES:
        raise ValueError(f"Invalid role: {new_role!r}. Must be 'manager' or 'shadow'.")

    result = await db.execute(
        select(AccountMembership).where(
            AccountMembership.account_id == account_id,
            AccountMembership.user_id == target_user_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise ValueError("Membership not found.")

    old_role = membership.role
    membership.role = new_role
    await db.flush()

    await _log_event(
        db,
        account_id=account_id,
        actor_user_id=actor.id,
        target_user_id=target_user_id,
        event_type="role_changed",
        old_role=old_role,
        new_role=new_role,
    )

    return membership


async def remove_member(
    db: AsyncSession,
    account_id: int,
    target_user_id: int,
    actor: User,
) -> None:
    """
    Remove a member from an account, or allow self-leave.

    Rules enforced here:
    - The account owner (account.user_id) cannot be removed.
    - Any member can remove themselves (leave).
    - Only the owner can remove others (enforced at router level).

    Raises ValueError if target is the account owner or membership not found.
    """
    account = await db.get(Account, account_id)
    if account and account.user_id == target_user_id:
        raise ValueError("The account owner cannot be removed.")

    result = await db.execute(
        select(AccountMembership).where(
            AccountMembership.account_id == account_id,
            AccountMembership.user_id == target_user_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise ValueError("Membership not found.")

    old_role = membership.role
    await db.delete(membership)
    await db.flush()

    event_type = "left" if actor.id == target_user_id else "removed"
    await _log_event(
        db,
        account_id=account_id,
        actor_user_id=actor.id,
        target_user_id=target_user_id,
        event_type=event_type,
        old_role=old_role,
    )


# ---------------------------------------------------------------------------
# Listing helpers
# ---------------------------------------------------------------------------

async def list_pending_invitations_for_account(
    db: AsyncSession,
    account_id: int,
) -> list[dict]:
    """Return outbound pending invitations for an account (owner's view)."""
    result = await db.execute(
        select(AccountInvitation).where(
            AccountInvitation.account_id == account_id,
            AccountInvitation.accepted_at.is_(None),
            AccountInvitation.declined_at.is_(None),
            AccountInvitation.revoked_at.is_(None),
            AccountInvitation.expires_at > datetime.utcnow(),
        )
    )
    return [
        {
            "id": inv.id,
            "invited_email": inv.invited_email,
            "role": inv.role,
            "expires_at": inv.expires_at.isoformat(),
            "created_at": inv.created_at.isoformat(),
        }
        for inv in result.scalars().all()
    ]


async def list_pending_invitations_for_user(
    db: AsyncSession,
    user_email: str,
) -> list[dict]:
    """Return inbound pending invitations for the given email address."""
    normalized = user_email.lower().strip()
    result = await db.execute(
        select(AccountInvitation).where(
            AccountInvitation.invited_email == normalized,
            AccountInvitation.accepted_at.is_(None),
            AccountInvitation.declined_at.is_(None),
            AccountInvitation.revoked_at.is_(None),
            AccountInvitation.expires_at > datetime.utcnow(),
        )
    )
    invitations = result.scalars().all()

    output = []
    for inv in invitations:
        account = await db.get(Account, inv.account_id)
        inviter = await db.get(User, inv.invited_by_user_id)
        output.append({
            "token": inv.token,
            "account_name": account.get_display_name() if account else "Unknown Account",
            "invited_by": (inviter.display_name or inviter.email) if inviter else "Unknown",
            "role": inv.role,
            "expires_at": inv.expires_at.isoformat(),
        })
    return output


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

async def _get_pending_invitation(db: AsyncSession, token: str) -> AccountInvitation:
    """Fetch an invitation by token and assert it is still pending."""
    result = await db.execute(
        select(AccountInvitation).where(AccountInvitation.token == token)
    )
    invitation = result.scalar_one_or_none()
    if not invitation:
        raise ValueError("Invalid or expired invitation token.")

    if not invitation.is_pending:
        if invitation.accepted_at:
            raise ValueError("This invitation has already been accepted.")
        if invitation.declined_at:
            raise ValueError("This invitation has already been declined.")
        if invitation.revoked_at:
            raise ValueError("This invitation has been revoked by the account owner.")
        raise ValueError("This invitation has expired.")

    return invitation


def _assert_email_match(invitation: AccountInvitation, current_user: User) -> None:
    """Raise PermissionError if the current user's email does not match the invitation."""
    if invitation.invited_email.lower() != current_user.email.lower():
        raise PermissionError(
            "This invitation was sent to a different email address. "
            "Please log in with the account that received the invitation."
        )


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User).where(User.email == email.lower())
    )
    return result.scalar_one_or_none()


async def _log_event(
    db: AsyncSession,
    account_id: int,
    actor_user_id: int | None,
    event_type: str,
    target_user_id: int | None = None,
    old_role: str | None = None,
    new_role: str | None = None,
    notes: str | None = None,
) -> None:
    """Append an immutable audit record to account_membership_events."""
    event = AccountMembershipEvent(
        account_id=account_id,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        event_type=event_type,
        old_role=old_role,
        new_role=new_role,
        notes=notes,
    )
    db.add(event)
