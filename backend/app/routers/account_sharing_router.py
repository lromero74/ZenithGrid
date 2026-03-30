"""
Account Sharing Router

Endpoints for inviting members to co-manage or observe exchange accounts.

Route groups:
  /api/accounts/{account_id}/sharing/*   — account-scoped operations
  /api/invitations/*                     — user-scoped inbound invitation operations
"""

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import get_current_user, require_account_access
from app.models import User
from app.services import account_sharing_service as svc
from app.services.email_service import send_invitation_email
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["account-sharing"])


# =============================================================================
# Pydantic schemas
# =============================================================================

class InviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(..., pattern="^(manager|shadow)$")


class RoleUpdateRequest(BaseModel):
    role: str = Field(..., pattern="^(manager|shadow)$")


# =============================================================================
# Account-scoped endpoints
# =============================================================================

@router.post("/api/accounts/{account_id}/sharing/invite", status_code=201)
async def invite_member(
    account_id: int,
    body: InviteRequest,
    account_role: str = Depends(require_account_access("owner")),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send an account sharing invitation. Owner-only.

    Creates a one-time, 7-day expiring invitation token and emails it
    to the specified address. The recipient must authenticate as that
    email address before they can accept.

    Rate-limited to 10 invitations per account per hour.
    """
    # M3: Prevent invite spam — cap at 10 invitations per account per hour
    from datetime import timedelta
    from app.models.sharing import AccountInvitation
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    recent_count_result = await db.execute(
        select(func.count(AccountInvitation.id)).where(
            AccountInvitation.account_id == account_id,
            AccountInvitation.created_at >= one_hour_ago,
        )
    )
    recent_count = recent_count_result.scalar_one()
    if recent_count >= 10:
        raise HTTPException(
            status_code=429,
            detail="Too many invitations sent in the last hour. Please wait before sending more.",
        )

    try:
        invitation = await svc.create_invitation(
            db, account_id, str(body.email), body.role, current_user
        )
        await db.commit()
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Reload account name after commit (relationship may be detached)
    from app.models import Account as AccountModel
    account_result = await db.execute(
        select(AccountModel).where(AccountModel.id == account_id)
    )
    account_obj = account_result.scalar_one_or_none()
    account_name = account_obj.get_display_name() if account_obj else "your account"

    # Send invitation email — failure is non-fatal
    accept_url = f"{settings.frontend_url}/accept-invite?token={invitation.token}"
    try:
        send_invitation_email(
            to=str(body.email),
            accept_url=accept_url,
            inviter_name=current_user.display_name or current_user.email,
            role=body.role,
            account_name=account_name,
        )
    except Exception:
        logger.warning("Failed to send invitation email to %s", body.email)

    # Real-time push: if the invitee is currently connected via WebSocket, notify them
    try:
        from app.services.websocket_manager import ws_manager
        from app.models import User as UserModel
        from sqlalchemy import select as sa_select
        invitee_result = await db.execute(
            sa_select(UserModel).where(UserModel.email == str(body.email).lower())
        )
        invitee = invitee_result.scalar_one_or_none()
        if invitee:
            await ws_manager.send_to_user(invitee.id, {
                "type": "account:invitation",
                "invited_by": current_user.display_name or current_user.email,
                "account_name": account_name,
                "role": body.role,
                "token": invitation.token,
            })
    except Exception:
        pass  # Non-fatal — email is the primary channel

    return {
        "message": f"Invitation sent to {body.email}",
        "invitation_id": invitation.id,
    }


@router.get("/api/accounts/{account_id}/sharing/members")
async def list_members(
    account_id: int,
    account_role: str = Depends(require_account_access("shadow")),
    db: AsyncSession = Depends(get_db),
):
    """List all active members of this account. Any role can view."""
    return await svc.list_members(db, account_id)


@router.get("/api/accounts/{account_id}/sharing/invitations")
async def list_outbound_invitations(
    account_id: int,
    account_role: str = Depends(require_account_access("owner")),
    db: AsyncSession = Depends(get_db),
):
    """List pending outbound invitations for this account. Owner-only."""
    return await svc.list_pending_invitations_for_account(db, account_id)


@router.put("/api/accounts/{account_id}/sharing/members/{target_user_id}")
async def update_member_role(
    account_id: int,
    target_user_id: int,
    body: RoleUpdateRequest,
    account_role: str = Depends(require_account_access("owner")),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change a member's role. Owner-only."""
    try:
        membership = await svc.update_member_role(
            db, account_id, target_user_id, body.role, current_user
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {"user_id": membership.user_id, "role": membership.role}


@router.delete("/api/accounts/{account_id}/sharing/members/{target_user_id}")
async def remove_member(
    account_id: int,
    target_user_id: int,
    account_role: str = Depends(require_account_access("shadow")),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Remove a member (owner) or leave the account (self).

    Any role can remove themselves. Only the owner can remove others.
    """
    if account_role != "owner" and current_user.id != target_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only remove yourself from a shared account.",
        )
    try:
        await svc.remove_member(db, account_id, target_user_id, current_user)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {"message": "Member removed successfully"}


@router.delete("/api/accounts/{account_id}/sharing/invitations/{invitation_id}")
async def revoke_invitation(
    account_id: int,
    invitation_id: int,
    account_role: str = Depends(require_account_access("owner")),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a pending outbound invitation. Owner-only."""
    try:
        await svc.revoke_invitation(db, invitation_id, account_id, current_user)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {"message": "Invitation revoked"}


# =============================================================================
# User-scoped inbound invitation endpoints
# =============================================================================

@router.get("/api/invitations/pending")
async def list_pending_invitations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all pending inbound invitations for the current authenticated user."""
    return await svc.list_pending_invitations_for_user(db, current_user.email)


@router.get("/api/invitations/preview/{token}")
async def preview_invitation(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Preview an invitation before acting on it.

    Returns account name, inviter, and role. Validates that the authenticated
    user's email matches the invited_email — raises 400 if not.
    """
    try:
        return await svc.preview_invitation(db, token, current_user)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/api/invitations/{token}/accept")
async def accept_invitation(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Accept an invitation. Requires authentication as the invited email address.

    Creates an AccountMembership record. The token is marked used and
    cannot be reused.
    """
    try:
        membership = await svc.accept_invitation(db, token, current_user)
        await db.commit()
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {
        "message": "Invitation accepted. Welcome to the account!",
        "role": membership.role,
    }


@router.post("/api/invitations/{token}/decline")
async def decline_invitation(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Decline an invitation. The token is marked declined and cannot be reused."""
    try:
        await svc.decline_invitation(db, token, current_user)
        await db.commit()
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {"message": "Invitation declined"}
