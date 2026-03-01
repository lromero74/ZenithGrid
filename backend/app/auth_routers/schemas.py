"""
Pydantic models (schemas) for authentication endpoints.
"""

import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    """Login request with email and password"""
    email: EmailStr
    password: str = Field(..., min_length=1)
    device_trust_token: Optional[str] = None  # Skip MFA if valid trusted device


class TokenResponse(BaseModel):
    """Response containing JWT tokens"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires
    user: "UserResponse"


class RefreshRequest(BaseModel):
    """Request to refresh access token"""
    refresh_token: str


def _validate_password_strength(password: str) -> str:
    """Validate password has uppercase, lowercase, and digit."""
    if not re.search(r'[A-Z]', password):
        raise ValueError('Password must contain at least one uppercase letter')
    if not re.search(r'[a-z]', password):
        raise ValueError('Password must contain at least one lowercase letter')
    if not re.search(r'[0-9]', password):
        raise ValueError('Password must contain at least one digit')
    return password


class ChangePasswordRequest(BaseModel):
    """Request to change password"""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, description="New password (min 8 chars, 1 upper, 1 lower, 1 digit)")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_password_strength(v)


class RegisterRequest(BaseModel):
    """Request to register a new user"""
    email: EmailStr
    password: str = Field(..., min_length=8)
    display_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_strength(v)


class GroupResponse(BaseModel):
    """Group summary for user responses."""
    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleResponse(BaseModel):
    """Role summary for admin responses."""
    id: int
    name: str
    description: Optional[str] = None
    requires_mfa: bool = False

    class Config:
        from_attributes = True


class UserResponse(BaseModel):
    """User information (without sensitive data)"""
    id: int
    email: str
    display_name: Optional[str]
    is_active: bool
    is_superuser: bool
    mfa_enabled: bool = False
    mfa_email_enabled: bool = False
    email_verified: bool = False
    email_verified_at: Optional[datetime] = None
    created_at: datetime
    last_login_at: Optional[datetime]
    terms_accepted_at: Optional[datetime] = None  # NULL = must accept terms
    groups: List[GroupResponse] = []
    permissions: List[str] = []

    class Config:
        from_attributes = True


class MFAChallengeResponse(BaseModel):
    """Response when MFA is required during login"""
    mfa_required: bool = True
    mfa_token: str  # Short-lived JWT for MFA verification


class LoginResponse(BaseModel):
    """Union response for login: either full tokens or MFA challenge"""
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: Optional[int] = None
    user: Optional[UserResponse] = None
    mfa_required: bool = False
    mfa_token: Optional[str] = None
    mfa_methods: Optional[List[str]] = None  # e.g. ["totp", "email_code", "email_link"]
    device_trust_token: Optional[str] = None  # 30-day device trust token


class MFASetupResponse(BaseModel):
    """Response with QR code and secret for MFA setup"""
    qr_code_base64: str  # Base64 PNG of QR code
    secret_key: str  # Base32 secret for manual entry
    provisioning_uri: str  # otpauth:// URI


class MFAVerifyRequest(BaseModel):
    """Request to verify a TOTP code"""
    totp_code: str = Field(..., min_length=6, max_length=6, pattern=r'^\d{6}$')


class MFAVerifyLoginRequest(BaseModel):
    """Request to verify MFA during login"""
    mfa_token: str
    totp_code: str = Field(..., min_length=6, max_length=6, pattern=r'^\d{6}$')
    remember_device: bool = False  # If true, returns a 30-day device trust token


class MFADisableRequest(BaseModel):
    """Request to disable MFA (requires password + TOTP code)"""
    password: str = Field(..., min_length=1)
    totp_code: str = Field(..., min_length=6, max_length=6, pattern=r'^\d{6}$')


class VerifyEmailRequest(BaseModel):
    """Request to verify email with token"""
    token: str = Field(..., min_length=1)


class ForgotPasswordRequest(BaseModel):
    """Request to send password reset email"""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Request to reset password with token"""
    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_password_strength(v)


class VerifyEmailCodeRequest(BaseModel):
    """Request to verify email with 6-digit code (authenticated user)"""
    code: str = Field(..., min_length=6, max_length=6, pattern=r'^\d{6}$')


class MFAConfirmSetupRequest(BaseModel):
    """Request to confirm MFA setup with secret and first TOTP code"""
    secret_key: str = Field(..., min_length=16, max_length=64)
    totp_code: str = Field(..., min_length=6, max_length=6, pattern=r'^\d{6}$')


class MFAEmailCodeRequest(BaseModel):
    """Request to verify MFA with email code"""
    mfa_token: str
    email_code: str = Field(..., min_length=6, max_length=6, pattern=r'^\d{6}$')
    remember_device: bool = False


class MFAEmailLinkRequest(BaseModel):
    """Request to verify MFA with email link token"""
    token: str
    remember_device: bool = False


class MFAEmailEnableRequest(BaseModel):
    """Request to enable email MFA"""
    password: str = Field(..., min_length=1)


class MFAEmailDisableRequest(BaseModel):
    """Request to disable email MFA"""
    password: str = Field(..., min_length=1)


class LastSeenHistoryRequest(BaseModel):
    """Request to update last seen history count"""
    count: Optional[int] = Field(None, ge=0)  # Closed positions count
    failed_count: Optional[int] = Field(None, ge=0)  # Failed orders count


class LastSeenHistoryResponse(BaseModel):
    """Response with last seen history count"""
    last_seen_history_count: int
    last_seen_failed_count: int = 0


class TrustedDeviceResponse(BaseModel):
    """Response for a single trusted device"""
    id: int
    device_name: Optional[str]
    ip_address: Optional[str]
    location: Optional[str]
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


# Allow forward references
TokenResponse.model_rebuild()
LoginResponse.model_rebuild()
