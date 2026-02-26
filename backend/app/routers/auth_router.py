"""
Authentication API routes - aggregator

Combines all auth sub-routers into the /api/auth prefix.
"""

from fastapi import APIRouter

from app.auth_routers.auth_core_router import router as core_router
from app.auth_routers.email_verify_router import router as email_router
from app.auth_routers.password_router import router as password_router
from app.auth_routers.mfa_totp_router import router as mfa_totp_router
from app.auth_routers.mfa_email_router import router as mfa_email_router
from app.auth_routers.device_trust_router import router as device_router
from app.auth_routers.preferences_router import router as preferences_router

# Re-export helpers that other modules may depend on
from app.auth_routers.helpers import (  # noqa: F401
    _build_user_response,
    _parse_device_name,
    create_access_token,
    create_device_trust_token,
    create_mfa_token,
    create_refresh_token,
    decode_device_trust_token,
    get_user_by_email,
    hash_password,
    verify_password,
)

# Re-export rate limiter functions and state (used by tests)
from app.auth_routers.rate_limiters import (  # noqa: F401
    _check_forgot_pw_rate_limit,
    _check_mfa_rate_limit,
    _check_rate_limit,
    _check_resend_rate_limit,
    _check_signup_rate_limit,
    _forgot_pw_attempts,
    _forgot_pw_by_email,
    _is_forgot_pw_email_rate_limited,
    _login_attempts,
    _login_attempts_by_username,
    _mfa_attempts,
    _record_attempt,
    _record_forgot_pw_attempt,
    _record_forgot_pw_email_attempt,
    _record_mfa_attempt,
    _record_resend_attempt,
    _record_signup_attempt,
    _resend_attempts,
    _signup_attempts,
)

# Re-export schemas (used by tests and endpoint function imports)
from app.auth_routers.schemas import (  # noqa: F401
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    MFAEmailDisableRequest,
    MFAEmailEnableRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
    LastSeenHistoryRequest,
    VerifyEmailRequest,
    _validate_password_strength,
)

# Re-export endpoint functions (used by tests that import them directly)
from app.auth_routers.auth_core_router import (  # noqa: F401
    change_password,
    get_current_user_info,
    login,
    logout,
    refresh_token,
    register,
    signup,
)
from app.auth_routers.email_verify_router import verify_email  # noqa: F401
from app.auth_routers.password_router import (  # noqa: F401
    forgot_password,
    reset_password,
)
from app.auth_routers.preferences_router import (  # noqa: F401
    accept_terms,
    get_last_seen_history,
    update_last_seen_history,
)
from app.auth_routers.device_trust_router import (  # noqa: F401
    list_trusted_devices,
    revoke_all_trusted_devices,
    revoke_trusted_device,
)
from app.auth_routers.mfa_email_router import (  # noqa: F401
    mfa_email_disable,
    mfa_email_enable,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
router.include_router(core_router)
router.include_router(email_router)
router.include_router(password_router)
router.include_router(mfa_totp_router)
router.include_router(mfa_email_router)
router.include_router(device_router)
router.include_router(preferences_router)
