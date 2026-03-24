"""
Account sharing models: memberships, invitations, audit events.

All tables live in the auth schema (co-located with users/RBAC).
Ownership is always determined by account.user_id — these models
cover non-owner access only (role in: 'manager', 'observer').
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class AccountMembership(Base):
    """
    Maps a non-owner user to an account with a specific role.

    Roles:
      manager  — read + write: start/stop bots, add/edit/delete bots, cancel/close positions,
                 view all data including operational settings; cannot touch credentials or invites
      observer — read-only: balances, bots, positions, reports, logs, and operational settings
                 (auto-buy thresholds, rebalance configuration, dust sweep settings)

    The account owner is identified by account.user_id — no 'owner' row here.
    """
    __tablename__ = "account_memberships"
    __table_args__ = {'schema': 'auth'}

    id = Column(Integer, primary_key=True)
    account_id = Column(
        Integer, ForeignKey("trading.accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        Integer, ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role = Column(String(20), nullable=False)  # 'manager' | 'observer'
    invited_by_user_id = Column(
        Integer, ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True
    )
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)  # NULL = no expiry

    # Relationships
    account = relationship("Account", back_populates="memberships", lazy="select")
    user = relationship("User", foreign_keys=[user_id], lazy="select")
    invited_by = relationship("User", foreign_keys=[invited_by_user_id], lazy="select")

    @property
    def is_expired(self) -> bool:
        """True if this membership has a set expiry that has already passed."""
        return self.expires_at is not None and self.expires_at < datetime.utcnow()


class AccountInvitation(Base):
    """
    One-time, expiring invitation token sent to an email address.

    Security invariants:
    - Token is a UUID hex (32 chars), unique.
    - Only the user authenticated with invited_email can accept.
    - Token is single-use: once accepted/declined/revoked, is_pending returns False.
    - Default expiry: 7 days from creation.
    """
    __tablename__ = "account_invitations"
    __table_args__ = {'schema': 'auth'}

    id = Column(Integer, primary_key=True)
    account_id = Column(
        Integer, ForeignKey("trading.accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invited_email = Column(String(255), nullable=False, index=True)
    invited_by_user_id = Column(
        Integer, ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(20), nullable=False)  # 'manager' | 'observer'
    token = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    declined_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    account = relationship("Account", lazy="select")
    invited_by = relationship("User", foreign_keys=[invited_by_user_id], lazy="select")

    @property
    def is_pending(self) -> bool:
        """True if this invitation can still be acted upon."""
        return (
            self.accepted_at is None
            and self.declined_at is None
            and self.revoked_at is None
            and self.expires_at > datetime.utcnow()
        )


class AccountMembershipEvent(Base):
    """
    Immutable audit log of all membership lifecycle events.

    event_type values:
      invited, invite_revoked, accepted, declined,
      role_changed, removed, left, expired
    """
    __tablename__ = "account_membership_events"
    __table_args__ = {'schema': 'auth'}

    id = Column(Integer, primary_key=True)
    account_id = Column(
        Integer, ForeignKey("trading.accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id = Column(
        Integer, ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True
    )
    target_user_id = Column(
        Integer, ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True
    )
    event_type = Column(String(30), nullable=False)
    old_role = Column(String(20), nullable=True)
    new_role = Column(String(20), nullable=True)
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
