"""Auth & RBAC models: users, groups, roles, permissions, sessions, tokens."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Table,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# RBAC junction tables (must be defined before ORM classes that reference them)
# ---------------------------------------------------------------------------

user_groups = Table(
    "user_groups",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
)

group_roles = Table(
    "group_roles",
    Base.metadata,
    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    """
    User model for authentication and multi-tenancy.

    Each user has their own:
    - Exchange accounts (CEX/DEX)
    - Bots and trading configurations
    - Positions and trade history
    - Templates and blacklisted coins
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)  # Admin privileges

    # Profile info
    display_name = Column(String, nullable=True)  # Optional display name

    # UI preferences
    last_seen_history_count = Column(Integer, default=0)  # For "new items" badge in History tab (closed positions)
    last_seen_failed_count = Column(Integer, default=0)  # For "new items" badge in Failed tab

    # Terms and conditions acceptance
    terms_accepted_at = Column(DateTime, nullable=True)  # NULL = not accepted, timestamp = when accepted

    # Email verification
    email_verified = Column(Boolean, default=False)  # Whether email has been verified
    email_verified_at = Column(DateTime, nullable=True)  # When email was verified

    # MFA (Two-Factor Authentication)
    totp_secret = Column(String, nullable=True)  # Fernet-encrypted TOTP secret key
    mfa_enabled = Column(Boolean, default=False)  # Whether TOTP MFA is active
    mfa_email_enabled = Column(Boolean, default=False)  # Whether email MFA is active

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    # Token revocation: tokens issued before this timestamp are invalid
    # Set on password change / reset to force re-login on all sessions
    tokens_valid_after = Column(DateTime, nullable=True)

    # Relationships
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    bots = relationship("Bot", back_populates="user", cascade="all, delete-orphan")
    bot_templates = relationship("BotTemplate", back_populates="user", cascade="all, delete-orphan")
    blacklisted_coins = relationship("BlacklistedCoin", back_populates="user", cascade="all, delete-orphan")
    ai_provider_credentials = relationship("AIProviderCredential", back_populates="user", cascade="all, delete-orphan")
    source_subscriptions = relationship("UserSourceSubscription", back_populates="user", cascade="all, delete-orphan")
    trusted_devices = relationship("TrustedDevice", back_populates="user", cascade="all, delete-orphan")
    email_verification_tokens = relationship(
        "EmailVerificationToken", back_populates="user", cascade="all, delete-orphan"
    )
    report_goals = relationship("ReportGoal", back_populates="user", cascade="all, delete-orphan")
    report_schedules = relationship("ReportSchedule", back_populates="user", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="user", cascade="all, delete-orphan")
    account_transfers = relationship("AccountTransfer", back_populates="user", cascade="all, delete-orphan")

    # Session policy override (per-user, masks group policy)
    session_policy_override = Column(JSON, nullable=True)

    # RBAC
    groups = relationship("Group", secondary=user_groups, back_populates="users", lazy="selectin")


class Group(Base):
    """Organizational group. Users belong to groups; groups are assigned roles."""
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255), nullable=True)
    is_system = Column(Boolean, default=False)
    session_policy = Column(JSON, nullable=True)  # Session limit policy for this group
    created_at = Column(DateTime, default=datetime.utcnow)

    roles = relationship("Role", secondary=group_roles, back_populates="groups", lazy="selectin")
    users = relationship("User", secondary=user_groups, back_populates="groups", lazy="selectin")


class Role(Base):
    """Functional capability set with associated permissions."""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(255), nullable=True)
    is_system = Column(Boolean, default=False)
    requires_mfa = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles", lazy="selectin")
    groups = relationship("Group", secondary=group_roles, back_populates="roles", lazy="selectin")


class Permission(Base):
    """Granular permission using resource:action naming (e.g. bots:read, admin:users)."""
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255), nullable=True)

    roles = relationship("Role", secondary=role_permissions, back_populates="permissions")


class TrustedDevice(Base):
    """
    Trusted device for MFA bypass (30-day remember device).

    When a user checks "Remember this device", a record is created here.
    The device_id is embedded in a JWT token stored on the client.
    Users can view and revoke trusted devices from Settings.
    """
    __tablename__ = "trusted_devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    device_id = Column(String, unique=True, nullable=False, index=True)  # UUID in the JWT
    device_name = Column(String, nullable=True)  # Parsed from User-Agent
    ip_address = Column(String, nullable=True)
    location = Column(String, nullable=True)  # City, State, Country from IP geolocation
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    # Relationships
    user = relationship("User", back_populates="trusted_devices")


class EmailVerificationToken(Base):
    """
    Tokens for email verification and password reset.

    token_type distinguishes purpose:
    - "email_verify": Email verification (24h expiry)
    - "password_reset": Password reset (1h expiry)

    Supports both link-based (token) and code-based (verification_code) verification.
    """
    __tablename__ = "email_verification_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    verification_code = Column(String, nullable=True)  # 6-digit code for manual entry
    token_type = Column(String, nullable=False, default="email_verify")
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="email_verification_tokens")


class RevokedToken(Base):
    """
    Revoked JWT tokens for server-side token invalidation.

    When a user logs out or changes their password, the token's JTI (JWT ID)
    is recorded here. On every authenticated request, decode_token() checks
    this table and rejects revoked tokens.

    Expired entries (past their JWT expiry) are cleaned up by a periodic task.
    """
    __tablename__ = "revoked_tokens"

    id = Column(Integer, primary_key=True, index=True)
    jti = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    revoked_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)  # JWT's original expiry — for cleanup

    user = relationship("User")


class ActiveSession(Base):
    """Tracks active user sessions for enforcement of session limits."""
    __tablename__ = "active_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(36), unique=True, nullable=False, index=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, index=True)

    user = relationship("User", backref="active_sessions")
