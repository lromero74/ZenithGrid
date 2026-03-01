"""
Session policy resolution service.

Resolves effective session policy by merging group policies (most-restrictive)
and applying per-user overrides.
"""
import logging

logger = logging.getLogger(__name__)

# Session policy fields and their "most restrictive" merge strategy
# For min-wins fields: smallest non-null value is most restrictive
# For max-wins fields: largest non-null value is most restrictive
# For bool fields: True wins (more restrictive)
_MIN_WINS = {"session_timeout_minutes", "max_simultaneous_sessions", "max_sessions_per_ip"}
_MAX_WINS = {"relogin_cooldown_minutes"}
_TRUE_WINS = {"auto_logout"}

ALL_POLICY_FIELDS = _MIN_WINS | _MAX_WINS | _TRUE_WINS


def resolve_session_policy(user) -> dict:
    """
    Resolve effective session policy for a user.

    1. Merge all group policies (most-restrictive per field)
    2. Apply user-level override on top
    """
    merged = {}

    # Phase 1: merge group policies
    for group in (user.groups or []):
        policy = group.session_policy
        if not policy or not isinstance(policy, dict):
            continue
        for field in ALL_POLICY_FIELDS:
            value = policy.get(field)
            if value is None:
                continue
            existing = merged.get(field)
            if existing is None:
                merged[field] = value
            elif field in _MIN_WINS:
                merged[field] = min(existing, value)
            elif field in _MAX_WINS:
                merged[field] = max(existing, value)
            elif field in _TRUE_WINS:
                merged[field] = existing or value

    # Phase 2: apply user override (field-by-field mask)
    override = user.session_policy_override
    if override and isinstance(override, dict):
        for field in ALL_POLICY_FIELDS:
            if field in override:
                merged[field] = override[field]

    return merged


def has_any_limits(policy: dict) -> bool:
    """Check if a policy has any non-null limits."""
    if not policy:
        return False
    return any(policy.get(f) is not None for f in ALL_POLICY_FIELDS)
