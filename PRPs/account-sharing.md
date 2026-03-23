# PRP: Account Sharing / Co-Management

**Version:** 1.0
**Feature Branch:** `feature/account-sharing`
**Confidence Score:** 9/10

---

## Overview

Allow a ZenithGrid user to invite other platform users to co-manage or observe their CEX/DEX exchange account, Google Docs-style. The inviter enumerates rights (Manager or Observer) in the invitation. The invitation is one-time, expiring (7 days), and requires the recipient to **authenticate on the platform as the invited email address** before accepting. This extends the existing RBAC system with account-scoped roles that map directly to existing `Perm.*` permission constants.

---

## User Stories

1. **As an account owner**, I can invite my wife (by her platform email) to be a Manager on my Coinbase account, so she can run bots and see my positions.
2. **As an invitee**, I receive a single-use email link, log in as myself, see what I'm being offered, and accept or decline.
3. **As a Manager**, I can create/stop bots, view positions, and run reports — but I cannot view raw API credentials, delete the account, or change member roles.
4. **As an Observer**, I can see balances, bots, positions, and reports in read-only mode — identical to how demo/paper accounts are observed today.
5. **As an account owner**, I can change a member's role, revoke access, or revoke a pending invitation at any time.
6. **As a member**, I can leave a shared account at any time without needing owner approval.
7. **As a user browsing my accounts**, shared accounts are visually distinct in the dropdown (owner name + role badge).

---

## Design Decisions

### Ownership stays in `account.user_id`
Membership roles are only `manager` and `observer`. There is no `owner` row in the memberships table. Ownership is always: `account.user_id == current_user.id`. This prevents privilege escalation via a rogue INSERT.

### RBAC Integration
New `ACCOUNT_ROLE_PERMISSIONS` dict maps string roles to existing `Perm.*` sets. New dependency `require_account_access(account_id, min_role)` checks ownership first, then falls back to membership role. This is a **scoped extension** of the existing RBAC pattern — roles and permissions remain the abstraction.

```python
ACCOUNT_ROLE_PERMISSIONS = {
    "manager": {
        Perm.ACCOUNTS_READ,
        Perm.BOTS_READ, Perm.BOTS_WRITE,
        Perm.POSITIONS_READ, Perm.POSITIONS_WRITE,
        Perm.ORDERS_READ, Perm.ORDERS_WRITE,
        Perm.REPORTS_READ,
        Perm.TEMPLATES_READ,
    },
    "observer": {
        Perm.ACCOUNTS_READ,
        Perm.BOTS_READ,
        Perm.POSITIONS_READ,
        Perm.ORDERS_READ,
        Perm.REPORTS_READ,
    },
}
```

### Invitation Security Model
- Token: UUID4, stored in DB, single-use
- Expiry: 7 days from creation
- **`invited_email` must match `current_user.email` on accept** — only the intended recipient can accept
- Accept/Decline are authenticated endpoints (require valid JWT)
- Preview endpoint returns enough info to show "Louis invited you to manage Coinbase Main as Manager" — no sensitive account data

### Bot Ownership on Shared Accounts
When a manager creates a bot on a shared account: `bot.user_id = manager.id`, `bot.account_id = shared_account.id`. The account owner sees all bots on their account. Managers see bots they created. This is consistent with current model — no schema change to `bots` needed.

### Membership Expiry (Optional)
`account_memberships.expires_at` is nullable. When set, the sharing service checks this on every access and treats expired memberships as non-existent. This enables time-boxed access grants.

---

## Database Schema

### New Tables (all in `auth` schema)

#### `auth.account_memberships`
```sql
CREATE TABLE auth.account_memberships (
    id          SERIAL PRIMARY KEY,
    account_id  INTEGER NOT NULL REFERENCES trading.accounts(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role        VARCHAR(20) NOT NULL CHECK (role IN ('manager', 'observer')),
    invited_by_user_id INTEGER REFERENCES auth.users(id) ON DELETE SET NULL,
    joined_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMP,          -- NULL = no expiry
    CONSTRAINT uq_account_membership UNIQUE (account_id, user_id)
);
CREATE INDEX idx_memberships_user ON auth.account_memberships(user_id);
CREATE INDEX idx_memberships_account ON auth.account_memberships(account_id);
```

#### `auth.account_invitations`
```sql
CREATE TABLE auth.account_invitations (
    id                  SERIAL PRIMARY KEY,
    account_id          INTEGER NOT NULL REFERENCES trading.accounts(id) ON DELETE CASCADE,
    invited_email       VARCHAR(255) NOT NULL,
    invited_by_user_id  INTEGER NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role                VARCHAR(20) NOT NULL CHECK (role IN ('manager', 'observer')),
    token               VARCHAR(64) UNIQUE NOT NULL,
    expires_at          TIMESTAMP NOT NULL,
    accepted_at         TIMESTAMP,
    declined_at         TIMESTAMP,
    revoked_at          TIMESTAMP,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_invitations_email ON auth.account_invitations(invited_email);
CREATE INDEX idx_invitations_account ON auth.account_invitations(account_id);
CREATE INDEX idx_invitations_token ON auth.account_invitations(token);
```

#### `auth.account_membership_events` (audit log)
```sql
CREATE TABLE auth.account_membership_events (
    id              SERIAL PRIMARY KEY,
    account_id      INTEGER NOT NULL REFERENCES trading.accounts(id) ON DELETE CASCADE,
    actor_user_id   INTEGER REFERENCES auth.users(id) ON DELETE SET NULL,
    target_user_id  INTEGER REFERENCES auth.users(id) ON DELETE SET NULL,
    event_type      VARCHAR(30) NOT NULL,
    -- event_type values: invited, invite_revoked, accepted, declined,
    --                    role_changed, removed, left, expired
    old_role        VARCHAR(20),
    new_role        VARCHAR(20),
    notes           VARCHAR(255),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_membership_events_account ON auth.account_membership_events(account_id);
```

### SQLite (in tests)
These tables also need SQLite-compatible `CREATE TABLE IF NOT EXISTS` versions (no named schema — use `schema_translate_map` in tests). The migration uses `is_postgres()` to branch.

---

## ORM Models

**File to create:** `backend/app/models/sharing.py`
Register in `backend/app/models/__init__.py`.

```python
"""
ORM models for account sharing: memberships, invitations, audit events.
All tables live in the auth schema.
"""
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base


class AccountMembership(Base):
    __tablename__ = "account_memberships"
    __table_args__ = {'schema': 'auth'}

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("trading.accounts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)  # 'manager' | 'observer'
    invited_by_user_id = Column(Integer, ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)

    # Relationships
    account = relationship("Account", back_populates="memberships", lazy="select")
    user = relationship("User", foreign_keys=[user_id], lazy="select")
    invited_by = relationship("User", foreign_keys=[invited_by_user_id], lazy="select")

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at < datetime.utcnow()


class AccountInvitation(Base):
    __tablename__ = "account_invitations"
    __table_args__ = {'schema': 'auth'}

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("trading.accounts.id", ondelete="CASCADE"), nullable=False)
    invited_email = Column(String(255), nullable=False)
    invited_by_user_id = Column(Integer, ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)  # 'manager' | 'observer'
    token = Column(String(64), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    declined_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    account = relationship("Account", lazy="select")
    invited_by = relationship("User", foreign_keys=[invited_by_user_id], lazy="select")

    @property
    def is_pending(self) -> bool:
        return (
            self.accepted_at is None
            and self.declined_at is None
            and self.revoked_at is None
            and self.expires_at > datetime.utcnow()
        )


class AccountMembershipEvent(Base):
    __tablename__ = "account_membership_events"
    __table_args__ = {'schema': 'auth'}

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("trading.accounts.id", ondelete="CASCADE"), nullable=False)
    actor_user_id = Column(Integer, ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    target_user_id = Column(Integer, ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(30), nullable=False)
    old_role = Column(String(20), nullable=True)
    new_role = Column(String(20), nullable=True)
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
```

**Also add to `Account` model** (`backend/app/models/trading.py`):
```python
# Add to Account class relationships:
memberships = relationship("AccountMembership", back_populates="account",
                           cascade="all, delete-orphan", lazy="select")
```

---

## Migration

**File to create:** `backend/migrations/069_account_sharing.py`

```python
"""
Migration 069: Account sharing tables.

Creates three new tables in the auth schema:
  auth.account_memberships        — Maps users to accounts with a role
  auth.account_invitations        — One-time, expiring invitation tokens
  auth.account_membership_events  — Audit log for membership changes

SQLite: uses plain table names (no schema prefix) via schema_translate_map.
Idempotent: CREATE TABLE IF NOT EXISTS on all tables.
"""

from migrations.db_utils import get_migration_connection, is_postgres


def run():
    conn = get_migration_connection()
    cur = conn.cursor()

    try:
        if is_postgres():
            _run_postgres(cur)
        else:
            _run_sqlite(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def _run_postgres(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS auth.account_memberships (
            id                  SERIAL PRIMARY KEY,
            account_id          INTEGER NOT NULL
                REFERENCES trading.accounts(id) ON DELETE CASCADE,
            user_id             INTEGER NOT NULL
                REFERENCES auth.users(id) ON DELETE CASCADE,
            role                VARCHAR(20) NOT NULL
                CHECK (role IN ('manager', 'observer')),
            invited_by_user_id  INTEGER
                REFERENCES auth.users(id) ON DELETE SET NULL,
            joined_at           TIMESTAMP NOT NULL DEFAULT NOW(),
            expires_at          TIMESTAMP,
            CONSTRAINT uq_account_membership UNIQUE (account_id, user_id)
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_memberships_user "
        "ON auth.account_memberships(user_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_memberships_account "
        "ON auth.account_memberships(account_id)"
    )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS auth.account_invitations (
            id                  SERIAL PRIMARY KEY,
            account_id          INTEGER NOT NULL
                REFERENCES trading.accounts(id) ON DELETE CASCADE,
            invited_email       VARCHAR(255) NOT NULL,
            invited_by_user_id  INTEGER NOT NULL
                REFERENCES auth.users(id) ON DELETE CASCADE,
            role                VARCHAR(20) NOT NULL
                CHECK (role IN ('manager', 'observer')),
            token               VARCHAR(64) UNIQUE NOT NULL,
            expires_at          TIMESTAMP NOT NULL,
            accepted_at         TIMESTAMP,
            declined_at         TIMESTAMP,
            revoked_at          TIMESTAMP,
            created_at          TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_invitations_email "
        "ON auth.account_invitations(invited_email)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_invitations_token "
        "ON auth.account_invitations(token)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_invitations_account "
        "ON auth.account_invitations(account_id)"
    )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS auth.account_membership_events (
            id              SERIAL PRIMARY KEY,
            account_id      INTEGER NOT NULL
                REFERENCES trading.accounts(id) ON DELETE CASCADE,
            actor_user_id   INTEGER
                REFERENCES auth.users(id) ON DELETE SET NULL,
            target_user_id  INTEGER
                REFERENCES auth.users(id) ON DELETE SET NULL,
            event_type      VARCHAR(30) NOT NULL,
            old_role        VARCHAR(20),
            new_role        VARCHAR(20),
            notes           VARCHAR(255),
            created_at      TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_membership_events_account "
        "ON auth.account_membership_events(account_id)"
    )

    # Grant privileges to app role
    app_role = "zenithgrid_app"
    for table in ["account_memberships", "account_invitations", "account_membership_events"]:
        cur.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE "
            f"ON auth.{table} TO {app_role}"
        )
        cur.execute(
            f"GRANT USAGE, SELECT ON SEQUENCE auth.{table}_id_seq TO {app_role}"
        )


def _run_sqlite(cur):
    """SQLite versions — no schema prefix, no sequences, no CHECK constraints."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS account_memberships (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id          INTEGER NOT NULL,
            user_id             INTEGER NOT NULL,
            role                VARCHAR(20) NOT NULL,
            invited_by_user_id  INTEGER,
            joined_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at          TIMESTAMP,
            UNIQUE (account_id, user_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS account_invitations (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id          INTEGER NOT NULL,
            invited_email       VARCHAR(255) NOT NULL,
            invited_by_user_id  INTEGER NOT NULL,
            role                VARCHAR(20) NOT NULL,
            token               VARCHAR(64) UNIQUE NOT NULL,
            expires_at          TIMESTAMP NOT NULL,
            accepted_at         TIMESTAMP,
            declined_at         TIMESTAMP,
            revoked_at          TIMESTAMP,
            created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS account_membership_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id      INTEGER NOT NULL,
            actor_user_id   INTEGER,
            target_user_id  INTEGER,
            event_type      VARCHAR(30) NOT NULL,
            old_role        VARCHAR(20),
            new_role        VARCHAR(20),
            notes           VARCHAR(255),
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
```

---

## Backend: Auth Dependencies Extension

**File to modify:** `backend/app/auth/dependencies.py`

Add after the existing `require_permission` factory:

```python
from app.models.sharing import AccountMembership

# Maps account-scoped membership roles → the Perm constants they unlock.
# Ownership (account.user_id == user.id) grants full access regardless of this map.
ACCOUNT_ROLE_PERMISSIONS: dict[str, set[Perm]] = {
    "manager": {
        Perm.ACCOUNTS_READ,
        Perm.BOTS_READ, Perm.BOTS_WRITE,
        Perm.POSITIONS_READ, Perm.POSITIONS_WRITE,
        Perm.ORDERS_READ, Perm.ORDERS_WRITE,
        Perm.REPORTS_READ,
        Perm.TEMPLATES_READ,
    },
    "observer": {
        Perm.ACCOUNTS_READ,
        Perm.BOTS_READ,
        Perm.POSITIONS_READ,
        Perm.ORDERS_READ,
        Perm.REPORTS_READ,
    },
}


async def get_account_role(
    account_id: int,
    current_user: User,
    db: AsyncSession,
) -> str | None:
    """
    Return the effective role string for current_user on account_id.

    Returns:
        'owner'    — account.user_id == current_user.id
        'manager'  — active membership with role='manager'
        'observer' — active membership with role='observer'
        None       — no access

    Expired memberships are treated as None.
    """
    from app.models import Account
    from datetime import datetime

    # Check ownership first (fast path)
    result = await db.execute(
        select(Account.user_id).where(Account.id == account_id)
    )
    owner_id = result.scalar_one_or_none()
    if owner_id is None:
        return None  # Account doesn't exist
    if owner_id == current_user.id:
        return "owner"

    # Check membership
    result = await db.execute(
        select(AccountMembership).where(
            AccountMembership.account_id == account_id,
            AccountMembership.user_id == current_user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        return None
    if membership.is_expired:
        return None
    return membership.role


def require_account_access(min_role: str = "observer"):
    """
    Dependency factory: require at least `min_role` on the target account.

    Role hierarchy: owner > manager > observer

    Usage:
        @router.get("/{account_id}/members")
        async def list_members(
            account_id: int,
            role: str = Depends(require_account_access("manager")),
            ...
        ):

    The injected `role` is the user's actual role string ('owner', 'manager', or 'observer').
    Raises 404 if account does not exist, 403 if insufficient access.
    """
    _ROLE_ORDER = {"observer": 0, "manager": 1, "owner": 2}

    async def _check(
        account_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> str:
        role = await get_account_role(account_id, current_user, db)
        if role is None:
            raise HTTPException(status_code=404, detail="Account not found")
        if _ROLE_ORDER.get(role, -1) < _ROLE_ORDER.get(min_role, 0):
            raise HTTPException(status_code=403, detail="Insufficient account access")
        return role

    return _check
```

---

## Backend: Account Sharing Service

**File to create:** `backend/app/services/account_sharing_service.py`

```python
"""
Account Sharing Service

Business logic for:
- Creating and validating invitations
- Accepting / declining / revoking invitations
- Managing memberships (add, change role, remove)
- Logging audit events
"""
import uuid
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, User
from app.models.sharing import AccountInvitation, AccountMembership, AccountMembershipEvent

INVITATION_TTL_DAYS = 7
ROLE_ORDER = {"observer": 0, "manager": 1, "owner": 2}

logger = logging.getLogger(__name__)


async def create_invitation(
    db: AsyncSession,
    account_id: int,
    invited_email: str,
    role: str,
    inviter: User,
) -> AccountInvitation:
    """
    Create a pending invitation for invited_email to join account_id with role.

    Rules:
    - Role must be 'manager' or 'observer'
    - invited_email must not already be a member
    - invited_email must not already have a pending invitation for this account
    - inviter must be owner (checked in router via require_account_access)
    """
    if role not in ("manager", "observer"):
        raise ValueError(f"Invalid role: {role}")

    if invited_email.lower() == inviter.email.lower():
        raise ValueError("You cannot invite yourself.")

    # Check for existing membership (by email lookup)
    existing_user = await _get_user_by_email(db, invited_email)
    if existing_user:
        existing_membership = await db.execute(
            select(AccountMembership).where(
                AccountMembership.account_id == account_id,
                AccountMembership.user_id == existing_user.id,
            )
        )
        if existing_membership.scalar_one_or_none():
            raise ValueError(f"{invited_email} is already a member of this account.")

    # Check for existing pending invitation
    existing_invite = await db.execute(
        select(AccountInvitation).where(
            AccountInvitation.account_id == account_id,
            AccountInvitation.invited_email == invited_email.lower(),
            AccountInvitation.accepted_at.is_(None),
            AccountInvitation.declined_at.is_(None),
            AccountInvitation.revoked_at.is_(None),
            AccountInvitation.expires_at > datetime.utcnow(),
        )
    )
    if existing_invite.scalar_one_or_none():
        raise ValueError(f"A pending invitation for {invited_email} already exists.")

    token = uuid.uuid4().hex  # 32-char hex token
    invitation = AccountInvitation(
        account_id=account_id,
        invited_email=invited_email.lower(),
        invited_by_user_id=inviter.id,
        role=role,
        token=token,
        expires_at=datetime.utcnow() + timedelta(days=INVITATION_TTL_DAYS),
    )
    db.add(invitation)
    await db.flush()

    await _log_event(db, account_id, actor=inviter, target_email=invited_email,
                     event_type="invited", new_role=role)

    return invitation


async def preview_invitation(db: AsyncSession, token: str, current_user: User) -> dict:
    """
    Return preview info for an invitation token.
    Validates:
    - Token exists, is pending
    - current_user.email matches invited_email
    Returns dict with account name, owner name, role.
    """
    invitation = await _get_pending_invitation(db, token)
    _assert_email_match(invitation, current_user)

    account = await db.get(Account, invitation.account_id)
    inviter = await db.get(User, invitation.invited_by_user_id)

    return {
        "account_name": account.get_display_name() if account else "Unknown",
        "invited_by": inviter.display_name or inviter.email if inviter else "Unknown",
        "role": invitation.role,
        "expires_at": invitation.expires_at.isoformat(),
    }


async def accept_invitation(db: AsyncSession, token: str, current_user: User) -> AccountMembership:
    """
    Accept an invitation. Creates a membership record.
    Validates email match and token validity.
    """
    invitation = await _get_pending_invitation(db, token)
    _assert_email_match(invitation, current_user)

    # Create membership
    membership = AccountMembership(
        account_id=invitation.account_id,
        user_id=current_user.id,
        role=invitation.role,
        invited_by_user_id=invitation.invited_by_user_id,
    )
    db.add(membership)

    # Mark invitation used
    invitation.accepted_at = datetime.utcnow()

    await db.flush()
    await _log_event(db, invitation.account_id, actor=current_user,
                     event_type="accepted", new_role=invitation.role)
    return membership


async def decline_invitation(db: AsyncSession, token: str, current_user: User) -> None:
    """Decline an invitation. Marks it declined so it won't appear as pending."""
    invitation = await _get_pending_invitation(db, token)
    _assert_email_match(invitation, current_user)

    invitation.declined_at = datetime.utcnow()
    await db.flush()
    await _log_event(db, invitation.account_id, actor=current_user,
                     event_type="declined", new_role=invitation.role)


async def revoke_invitation(
    db: AsyncSession, invitation_id: int, account_id: int, actor: User
) -> None:
    """Revoke a pending outbound invitation. Only account owner can revoke."""
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
        raise ValueError("Invitation is no longer pending.")

    invitation.revoked_at = datetime.utcnow()
    await db.flush()
    await _log_event(db, account_id, actor=actor,
                     event_type="invite_revoked", new_role=invitation.role,
                     notes=invitation.invited_email)


async def update_member_role(
    db: AsyncSession, account_id: int, target_user_id: int, new_role: str, actor: User
) -> AccountMembership:
    """
    Change a member's role. Only the account owner can do this.
    Cannot demote/remove the owner (target_user_id == account.user_id → reject).
    """
    if new_role not in ("manager", "observer"):
        raise ValueError(f"Invalid role: {new_role}")

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
    await _log_event(db, account_id, actor=actor,
                     event_type="role_changed", old_role=old_role, new_role=new_role)
    return membership


async def remove_member(
    db: AsyncSession, account_id: int, target_user_id: int, actor: User
) -> None:
    """
    Remove a member or allow self-leave.
    Rules:
    - Anyone can remove themselves (leave)
    - Only the owner can remove others
    - The owner cannot be removed (target_user_id == account.user_id → reject)
    """
    # Check target is not the owner
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
    await _log_event(db, account_id, actor=actor,
                     event_type=event_type, old_role=old_role)


async def list_members(db: AsyncSession, account_id: int) -> list[dict]:
    """Return all active members for an account (not including the owner)."""
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
            "invited_by": inviter.display_name or inviter.email if inviter else None,
        })
    return members


async def list_pending_invitations_for_account(db: AsyncSession, account_id: int) -> list[dict]:
    """Return outbound pending invitations for an account (for owner's view)."""
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


async def list_pending_invitations_for_user(db: AsyncSession, user_email: str) -> list[dict]:
    """Return inbound pending invitations for the given email address."""
    result = await db.execute(
        select(AccountInvitation).where(
            AccountInvitation.invited_email == user_email.lower(),
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
            "account_name": account.get_display_name() if account else "Unknown",
            "invited_by": inviter.display_name or inviter.email if inviter else "Unknown",
            "role": inv.role,
            "expires_at": inv.expires_at.isoformat(),
        })
    return output


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

async def _get_pending_invitation(db: AsyncSession, token: str) -> AccountInvitation:
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
            raise ValueError("This invitation has been revoked.")
        raise ValueError("This invitation has expired.")
    return invitation


def _assert_email_match(invitation: AccountInvitation, current_user: User) -> None:
    """Ensure only the intended recipient can act on this invitation."""
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
    actor: User,
    event_type: str,
    target_email: str | None = None,
    old_role: str | None = None,
    new_role: str | None = None,
    notes: str | None = None,
) -> None:
    target_user = None
    if target_email:
        target_user = await _get_user_by_email(db, target_email)

    event = AccountMembershipEvent(
        account_id=account_id,
        actor_user_id=actor.id,
        target_user_id=target_user.id if target_user else None,
        event_type=event_type,
        old_role=old_role,
        new_role=new_role,
        notes=notes or target_email,
    )
    db.add(event)
```

---

## Backend: Account Sharing Router

**File to create:** `backend/app/routers/account_sharing_router.py`

```python
"""
Account Sharing Router

Endpoints for inviting members to co-manage or observe exchange accounts.

Prefixes:
  /api/accounts/{account_id}/sharing/*   — account-scoped operations
  /api/invitations/*                     — user-scoped invitation operations
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
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
    role: str = Field(..., pattern="^(manager|observer)$")
    expires_at: Optional[str] = None  # ISO date string for membership expiry (optional)


class RoleUpdateRequest(BaseModel):
    role: str = Field(..., pattern="^(manager|observer)$")


# =============================================================================
# Account-scoped endpoints (require account access)
# =============================================================================

@router.post("/api/accounts/{account_id}/sharing/invite", status_code=201)
async def invite_member(
    account_id: int,
    body: InviteRequest,
    role: str = Depends(require_account_access("owner")),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send an invitation email. Owner-only."""
    try:
        invitation = await svc.create_invitation(
            db, account_id, str(body.email), body.role, current_user
        )
        await db.commit()
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Send invitation email (non-blocking — failure doesn't abort the request)
    accept_url = f"{settings.frontend_url}/accept-invite?token={invitation.token}"
    try:
        send_invitation_email(
            to=str(body.email),
            accept_url=accept_url,
            inviter_name=current_user.display_name or current_user.email,
            role=body.role,
            account_name=invitation.account.get_display_name() if invitation.account else "an account",
        )
    except Exception:
        logger.warning("Failed to send invitation email to %s", body.email)

    return {"message": f"Invitation sent to {body.email}", "invitation_id": invitation.id}


@router.get("/api/accounts/{account_id}/sharing/members")
async def list_members(
    account_id: int,
    role: str = Depends(require_account_access("observer")),  # All roles can see members
    db: AsyncSession = Depends(get_db),
):
    """List all members of this account."""
    return await svc.list_members(db, account_id)


@router.get("/api/accounts/{account_id}/sharing/invitations")
async def list_outbound_invitations(
    account_id: int,
    role: str = Depends(require_account_access("owner")),
    db: AsyncSession = Depends(get_db),
):
    """List pending outbound invitations for this account. Owner-only."""
    return await svc.list_pending_invitations_for_account(db, account_id)


@router.put("/api/accounts/{account_id}/sharing/members/{target_user_id}")
async def update_member_role(
    account_id: int,
    target_user_id: int,
    body: RoleUpdateRequest,
    role: str = Depends(require_account_access("owner")),
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
        raise HTTPException(status_code=400, detail=str(e))
    return {"user_id": membership.user_id, "role": membership.role}


@router.delete("/api/accounts/{account_id}/sharing/members/{target_user_id}")
async def remove_member(
    account_id: int,
    target_user_id: int,
    role: str = Depends(require_account_access("observer")),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Remove a member (owner) or leave the account (self).
    A member can always remove themselves. Only owner can remove others.
    """
    # Non-owners can only remove themselves
    if role != "owner" and current_user.id != target_user_id:
        raise HTTPException(status_code=403, detail="You can only remove yourself.")
    try:
        await svc.remove_member(db, account_id, target_user_id, current_user)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "Member removed"}


@router.delete("/api/accounts/{account_id}/sharing/invitations/{invitation_id}")
async def revoke_invitation(
    account_id: int,
    invitation_id: int,
    role: str = Depends(require_account_access("owner")),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a pending outbound invitation. Owner-only."""
    try:
        await svc.revoke_invitation(db, invitation_id, account_id, current_user)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "Invitation revoked"}


# =============================================================================
# User-scoped invitation endpoints (inbound — no account_id in path)
# =============================================================================

@router.get("/api/invitations/pending")
async def list_pending_invitations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all pending inbound invitations for the current user."""
    return await svc.list_pending_invitations_for_user(db, current_user.email)


@router.get("/api/invitations/preview/{token}")
async def preview_invitation(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Preview an invitation before accepting/declining.
    Returns account name, inviter name, and role.
    Validates that current_user.email matches the invitation's invited_email.
    """
    try:
        return await svc.preview_invitation(db, token, current_user)
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/invitations/{token}/accept")
async def accept_invitation(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Accept an invitation. Requires authentication as the invited email.
    Creates an AccountMembership record.
    """
    try:
        membership = await svc.accept_invitation(db, token, current_user)
        await db.commit()
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "Invitation accepted", "role": membership.role}


@router.post("/api/invitations/{token}/decline")
async def decline_invitation(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Decline an invitation."""
    try:
        await svc.decline_invitation(db, token, current_user)
        await db.commit()
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "Invitation declined"}
```

---

## Backend: Email Service Addition

**File to modify:** `backend/app/services/email_service.py`

Add this new function following the existing patterns:

```python
def send_invitation_email(
    to: str,
    accept_url: str,
    inviter_name: str,
    role: str,
    account_name: str,
) -> bool:
    """
    Send an account sharing invitation email.

    The invitation link is one-time and expires in 7 days.
    Recipient must authenticate before accepting.
    """
    if not settings.ses_enabled:
        logger.warning("SES disabled, skipping invitation email to %s", to)
        return False

    b = get_brand()
    role_label = "Manager" if role == "manager" else "Observer"
    role_description = (
        "manage bots, view positions, and run reports"
        if role == "manager"
        else "view account activity in read-only mode"
    )

    subject = f"{inviter_name} invited you to {role_label.lower()} {account_name} on {b['shortName']}"

    html_body = (
        '<div style="font-family: -apple-system, BlinkMacSystemFont, '
        "'Segoe UI', Roboto, sans-serif; max-width: 600px; "
        'margin: 0 auto; padding: 20px; background-color: #0f172a; color: #e2e8f0;">'
        f'{_email_header()}'
        '<div style="padding: 30px 0;">'
        f'<h2 style="color: #f1f5f9; margin: 0 0 15px 0;">'
        f"You've been invited as {role_label}</h2>"
        '<p style="color: #cbd5e1; line-height: 1.6;">'
        f'<strong style="color: #f1f5f9;">{inviter_name}</strong> has invited you to '
        f'{role_description} on their account '
        f'<strong style="color: #f1f5f9;">{account_name}</strong>.</p>'
        '<div style="text-align: center; padding: 25px 0;">'
        f'<a href="{accept_url}" style="display: inline-block; '
        'background-color: #3b82f6; color: #ffffff; text-decoration: none; '
        'padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 16px;">'
        'View Invitation</a></div>'
        '<p style="color: #94a3b8; font-size: 13px; line-height: 1.5;">'
        'You must be logged in as the account that received this invitation to accept it. '
        'This link expires in 7 days. If you were not expecting this invitation, '
        'you can safely ignore it.</p>'
        '</div>'
        f'{_email_footer()}'
        '</div>'
    )

    text_body = (
        f"{inviter_name} has invited you to {role_description} on {account_name}.\n\n"
        f"Accept the invitation: {accept_url}\n\n"
        "You must log in as the invited email address to accept. This link expires in 7 days."
    )

    return _send_email(to, subject, html_body, text_body)
```

---

## Backend: Extend `accounts_router.py`

The existing router has 18 places that filter `Account.user_id == current_user.id`. Most list/read endpoints need to be extended to also include shared accounts. A helper function keeps this DRY.

**Add this helper near the top of `accounts_router.py`:**

```python
from sqlalchemy import or_
from app.models.sharing import AccountMembership
from datetime import datetime

def _accessible_accounts_filter(current_user_id: int):
    """
    Returns a SQLAlchemy filter clause that matches accounts the user can access:
    1. Accounts they own (user_id == current_user_id)
    2. Accounts they are an active member of (non-expired membership)
    """
    return or_(
        Account.user_id == current_user_id,
        Account.id.in_(
            select(AccountMembership.account_id).where(
                AccountMembership.user_id == current_user_id,
                or_(
                    AccountMembership.expires_at.is_(None),
                    AccountMembership.expires_at > datetime.utcnow(),
                ),
            )
        ),
    )
```

**Key changes to existing endpoints:**

1. `GET /api/accounts` (list all) — replace `Account.user_id == current_user.id` with `_accessible_accounts_filter(current_user.id)`. Add `membership_role` and `shared_by` fields to `AccountResponse`.

2. `GET /api/accounts/{id}` — use `_accessible_accounts_filter` + add membership info to response.

3. `DELETE /api/accounts/{id}` — keep owner-only check (`Account.user_id == current_user.id`).

4. `PUT /api/accounts/{id}` — keep owner-only check for credential fields; managers can update name only.

5. Bot-related sub-queries — extend to include shared accounts where user is manager.

**`AccountResponse` additions:**

```python
class AccountResponse(BaseModel):
    # ... existing fields ...
    membership_role: Optional[str] = None  # None = owner, 'manager', 'observer'
    shared_by: Optional[str] = None        # Display name of account owner (non-owners only)
    member_count: int = 0                  # Number of non-owner members
```

---

## Backend: Register New Router

**File to modify:** `backend/app/main.py`

```python
from app.routers import account_sharing_router
# ... after accounts_router registration:
app.include_router(account_sharing_router.router)
```

---

## Frontend: Type Extensions

**File to modify:** `frontend/src/contexts/AccountContext.tsx`

Add to the `Account` interface:

```typescript
// Sharing fields
membership_role?: 'manager' | 'observer' | null  // null/undefined = owner
shared_by?: string | null                         // owner's display name (non-owners only)
member_count?: number
```

Add new context values:

```typescript
interface AccountContextType {
  // ... existing ...
  pendingInvitations: PendingInvitation[]
  pendingInvitationCount: number
  refreshInvitations: () => Promise<void>
  acceptInvitation: (token: string) => Promise<void>
  declineInvitation: (token: string) => Promise<void>
}

interface PendingInvitation {
  token: string
  account_name: string
  invited_by: string
  role: 'manager' | 'observer'
  expires_at: string
}
```

Add a `useQuery` for `/api/invitations/pending` in the provider. Invalidate on accept/decline. Use `refetchInterval: 60000` (poll every minute for new invitations).

Helper in context:
```typescript
const isOwner = (account: Account) => !account.membership_role
const getMyAccounts = () => accounts.filter(a => isOwner(a))
const getSharedAccounts = () => accounts.filter(a => !!a.membership_role)
```

---

## Frontend: AccountSwitcher Changes

**File to modify:** `frontend/src/components/AccountSwitcher.tsx`

Split the dropdown into two sections:

```typescript
// Section 1: "Your Accounts" — accounts where isOwner(a)
// Section 2: "Shared With You" — accounts where membership_role is set

// For shared accounts, show:
<div className="flex items-center gap-1">
  <Users size={12} className="text-slate-400" />
  <span className="text-xs text-slate-400">
    {account.membership_role === 'manager' ? 'Manager' : 'Observer'}
    {account.shared_by ? ` · ${account.shared_by}` : ''}
  </span>
</div>
```

Add a pending invitations badge to the switcher trigger (or header):
```typescript
{pendingInvitationCount > 0 && (
  <span className="absolute -top-1 -right-1 bg-blue-500 text-white text-xs font-bold
                   rounded-full w-4 h-4 flex items-center justify-center">
    {pendingInvitationCount > 9 ? '9+' : pendingInvitationCount}
  </span>
)}
```

---

## Frontend: New Components

### `AccountSharingPanel.tsx`
Renders within `AccountsManagement` (Settings page). Shows:
- **Owner's view**: Member list (role badge, joined date, change-role dropdown, remove button) + Pending outbound invitations (invited email, role, expiry, revoke button) + "Invite Someone" button that opens `InviteMemberModal`.
- **Member's view**: Own role badge, "Leave this account" button.

```typescript
// Props
interface AccountSharingPanelProps {
  accountId: number
  membershipRole: 'owner' | 'manager' | 'observer'
}
```

### `InviteMemberModal.tsx`
Simple modal with:
- Email input (validates format)
- Role picker: "Manager" (can trade + manage bots) | "Observer" (read-only)
- Optional "Expires" date picker
- Submit → `POST /api/accounts/{id}/sharing/invite`
- Success: show confirmation toast

### `PendingInvitationsPopover.tsx`
Header popover (triggered by bell/badge icon, or inline in AccountSwitcher):
- Lists pending invitations with "from whom", account name, role
- "Review" button → navigates to `/accept-invite?token=...`

---

## Frontend: Accept Invite Page

**File to create:** `frontend/src/pages/AcceptInvite.tsx`

```typescript
/**
 * Accept Invite Page
 *
 * Route: /accept-invite?token={token}
 *
 * Flow:
 * 1. Read token from query string
 * 2. If not logged in → redirect to /login?next=/accept-invite?token={token}
 * 3. If logged in → call GET /api/invitations/preview/{token}
 *    - On 400 "wrong email": show error with current email + guidance
 *    - On success: show preview card with Accept / Decline buttons
 * 4. On Accept → POST /api/invitations/{token}/accept → success screen
 * 5. On Decline → POST /api/invitations/{token}/decline → success screen
 */
```

This page must be accessible before authentication. Route added to `App.tsx` in the pre-auth token-based route block (same pattern as `/verify-email` and `/reset-password`).

---

## Frontend: App.tsx Route Addition

**File to modify:** `frontend/src/App.tsx`

Following the existing pattern:

```typescript
if (location.pathname === '/accept-invite') {
  return <AcceptInviteRoute />
}
```

Where `AcceptInviteRoute` checks authentication and either shows the `AcceptInvite` page (if logged in) or redirects to login with `?next=` query param.

---

## Implementation Tasks (in order)

1. **[ ] Migration** — Create `backend/migrations/069_account_sharing.py` with the three new tables (SQLite + PostgreSQL, idempotent).

2. **[ ] ORM Models** — Create `backend/app/models/sharing.py`. Register in `backend/app/models/__init__.py`. Add `memberships` relationship to `Account` in `trading.py`.

3. **[ ] Auth dependency extension** — Add `ACCOUNT_ROLE_PERMISSIONS`, `get_account_role()`, and `require_account_access()` to `backend/app/auth/dependencies.py`.

4. **[ ] Sharing service** — Create `backend/app/services/account_sharing_service.py`.

5. **[ ] Email function** — Add `send_invitation_email()` to `backend/app/services/email_service.py`.

6. **[ ] Sharing router** — Create `backend/app/routers/account_sharing_router.py`. Register in `main.py`.

7. **[ ] Extend accounts_router** — Add `_accessible_accounts_filter()` helper. Update `AccountResponse` with membership fields. Update list/get endpoints to use the filter. Preserve owner-only guards on delete/credentials.

8. **[ ] Backend tests** — Write `backend/tests/routers/test_account_sharing_router.py` (TDD: write tests first, then confirm they pass).

9. **[ ] Frontend: AccountContext** — Add `PendingInvitation` type, new context values, `useQuery` for pending invitations, `acceptInvitation`/`declineInvitation` actions, `isOwner`/`getSharedAccounts` helpers.

10. **[ ] Frontend: AccountSwitcher** — Add "Shared With You" section, role badges, pending invitations badge.

11. **[ ] Frontend: AccountSharingPanel** — New component for Settings page.

12. **[ ] Frontend: InviteMemberModal** — Email + role picker modal.

13. **[ ] Frontend: PendingInvitationsPopover** — Header notification for inbound invites.

14. **[ ] Frontend: AcceptInvite page** — `/accept-invite` route with auth-gate, preview, accept/decline.

15. **[ ] Frontend: App.tsx** — Add `/accept-invite` route.

16. **[ ] Run validation gates** — Lint, typecheck, tests.

17. **[ ] Run multiuser-security agent** — Verify tenant isolation, no IDOR on invitation tokens.

---

## Security Invariants

| Invariant | Enforced where |
|-----------|---------------|
| Only intended recipient can accept | `_assert_email_match()` in service layer |
| Token is single-use | `is_pending` property checks accepted/declined/revoked |
| Token expires in 7 days | `is_pending` checks `expires_at > now` |
| Owner cannot be removed via membership delete | `account.user_id == target_user_id` guard in service |
| Credentials (api_private_key) only for owner | Keep existing `account.user_id == current_user.id` guard on credential fields in `accounts_router.py` |
| Manager cannot grant 'owner' role | `role IN ('manager', 'observer')` constraint + service validation |
| Members cannot remove others | `role != 'owner' and actor.id != target_user_id` guard in router |
| Membership expiry honored | `is_expired` property checked in `get_account_role()` |
| No IDOR on invitations | `account_id` verified against authenticated user's ownership before revoke |

---

## Test Coverage Requirements

**File:** `backend/tests/routers/test_account_sharing_router.py`

Minimum test cases:

### Invitation creation
- `test_invite_member_as_owner_succeeds`
- `test_invite_member_as_manager_fails_403`
- `test_invite_self_fails_400`
- `test_invite_existing_member_fails_400`
- `test_invite_duplicate_pending_fails_400`
- `test_invite_sends_email` (mock email service)

### Invitation acceptance
- `test_accept_invitation_correct_email_succeeds`
- `test_accept_invitation_wrong_email_fails_400`
- `test_accept_expired_invitation_fails_400`
- `test_accept_already_accepted_invitation_fails_400`
- `test_accept_revoked_invitation_fails_400`
- `test_accept_creates_membership_record`
- `test_accept_requires_authentication` (no token → 401)

### Invitation decline
- `test_decline_invitation_correct_email_succeeds`
- `test_decline_invitation_wrong_email_fails_400`

### Member management
- `test_list_members_as_owner`
- `test_list_members_as_member`
- `test_update_member_role_as_owner_succeeds`
- `test_update_member_role_as_manager_fails_403`
- `test_remove_member_as_owner_succeeds`
- `test_member_can_leave_themselves`
- `test_member_cannot_remove_other_member_403`
- `test_cannot_remove_owner_400`

### Access control for shared accounts
- `test_manager_can_see_shared_account_in_list`
- `test_observer_can_see_shared_account_in_list`
- `test_unrelated_user_cannot_see_account_404`
- `test_manager_cannot_access_credentials`
- `test_manager_cannot_delete_account_403`

### Expired memberships
- `test_expired_membership_denies_access`

---

## Validation Gates

```bash
# 1. Run the migration
cd /home/ec2-user/ZenithGrid
backend/venv/bin/python3 update.py --yes

# 2. Python lint
cd backend
./venv/bin/python3 -m flake8 \
  app/models/sharing.py \
  app/services/account_sharing_service.py \
  app/routers/account_sharing_router.py \
  app/auth/dependencies.py \
  migrations/069_account_sharing.py \
  --max-line-length=120

# 3. TypeScript typecheck
cd /home/ec2-user/ZenithGrid/frontend
npx tsc --noEmit

# 4. Run targeted tests
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -m pytest \
  tests/routers/test_account_sharing_router.py \
  tests/routers/test_accounts_router.py \
  -v

# 5. Multiuser security audit
# (Call multiuser-security agent — it scans for IDOR, tenant isolation, auth gaps)
```

---

## Reference Patterns in Codebase

| What | Where |
|------|-------|
| Token-based one-time link flow | `backend/app/auth_routers/email_verify_router.py` |
| Email sending (SES) | `backend/app/services/email_service.py` — `send_verification_email()` |
| `require_permission` dependency factory | `backend/app/auth/dependencies.py` — lines ~80-100 |
| Migration with PostgreSQL + SQLite branches | `backend/migrations/067_add_dust_sweep_fields.py` |
| Schema-qualified FK pattern | `backend/app/models/sharing.py` (new) — use `"auth.users.id"`, `"trading.accounts.id"` |
| `_accessible_filter` subquery pattern | `backend/app/routers/accounts_router.py` — extend `line 251` |
| `schema_translate_map` in tests | `backend/tests/conftest.py` — add `"auth": None` (already there) |
| Frontend token-route pattern | `frontend/src/App.tsx` — verify-email and reset-password route blocks |
| Notification badge pattern | `frontend/src/App.tsx` — `newHistoryItemsCount` badge |
| `useQuery` + `useMutation` in context | `frontend/src/contexts/AccountContext.tsx` |
| Account model `get_display_name()` | `backend/app/models/trading.py` |
| `_SCHEMA_MAP` in conftest already has `"auth": None` | All new `auth.*` models will work in test SQLite automatically |

---

## Gotchas & Notes

1. **FK qualification**: Since `AccountMembership` is in `auth` schema and references `trading.accounts`, use `"trading.accounts.id"` in the `ForeignKey()` string. Using unqualified `"accounts.id"` will cause `NoReferencedTableError` at mapper configuration time.

2. **`configure_mappers()` won't be called in tests** until an ORM class is imported — the new models must be imported in `backend/app/models/__init__.py`.

3. **`schema_translate_map`** in `conftest.py` already flattens all 6 schemas. The new `auth.*` tables will work in in-memory SQLite tests automatically.

4. **`send_invitation_email` must not raise** — wrap in try/except in the router. A failed email delivery should not abort the invitation creation.

5. **Email comparison must be case-insensitive** — always `.lower()` both sides before comparing.

6. **`AccountMembership.is_expired` property** — used in both service layer and the dependency. Keep them consistent.

7. **`accounts_router.py` surgery**: The 18 `user_id == current_user.id` occurrences must be audited one by one. Not all should change — delete, credential access, and `set-default` should remain owner-only.

8. **Frontend `/accept-invite` route**: Must work before the user is authenticated (they might click the link from a fresh browser). Handle the not-logged-in case with a redirect to `/login?next=<current URL>`. After login, `App.tsx` should honor the `?next=` param and redirect back.

9. **Pending invitations polling**: Use `refetchInterval: 60_000` in React Query — not WebSocket push. Invitations are low-frequency events.

10. **Bot visibility on shared accounts**: No schema change needed. Managers see bots they own (`bot.user_id == manager.id`). The account owner sees all bots on their account. The existing `bots_router` already filters by `bot.user_id == current_user.id` — this is intentional and correct for managers. The owner's view of "all bots on my account" is handled by the existing account-level bot count and the ability to query by `account_id`.
