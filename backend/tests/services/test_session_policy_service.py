"""
Tests for session policy resolution service.

Covers:
- Single group passthrough
- Multi-group most-restrictive merging (min-wins, max-wins, true-wins)
- User override masking
- Empty / None / invalid policy handling
"""
from unittest.mock import MagicMock

from app.services.session_policy_service import (
    resolve_session_policy,
    has_any_limits,
    ALL_POLICY_FIELDS,
)


def _make_group(session_policy=None):
    """Create a mock Group with a session_policy."""
    g = MagicMock()
    g.session_policy = session_policy
    return g


def _make_user(groups=None, override=None):
    """Create a mock User with groups and optional override."""
    u = MagicMock()
    u.groups = groups or []
    u.session_policy_override = override
    return u


# ---------------------------------------------------------------------------
# Single group passthrough
# ---------------------------------------------------------------------------


class TestSingleGroupPassthrough:
    def test_single_group_policy_returned_as_is(self):
        policy = {
            "session_timeout_minutes": 30,
            "max_simultaneous_sessions": 5,
            "max_sessions_per_ip": 2,
            "relogin_cooldown_minutes": 5,
            "auto_logout": True,
        }
        user = _make_user(groups=[_make_group(policy)])
        result = resolve_session_policy(user)
        assert result == policy

    def test_single_group_partial_policy(self):
        policy = {"session_timeout_minutes": 60}
        user = _make_user(groups=[_make_group(policy)])
        result = resolve_session_policy(user)
        assert result == {"session_timeout_minutes": 60}

    def test_single_group_none_values_ignored(self):
        policy = {"session_timeout_minutes": 30, "max_simultaneous_sessions": None}
        user = _make_user(groups=[_make_group(policy)])
        result = resolve_session_policy(user)
        assert result == {"session_timeout_minutes": 30}


# ---------------------------------------------------------------------------
# Multi-group most-restrictive merging
# ---------------------------------------------------------------------------


class TestMultiGroupMerging:
    def test_min_wins_for_timeout(self):
        """Smallest timeout wins (most restrictive)."""
        g1 = _make_group({"session_timeout_minutes": 60})
        g2 = _make_group({"session_timeout_minutes": 30})
        user = _make_user(groups=[g1, g2])
        result = resolve_session_policy(user)
        assert result["session_timeout_minutes"] == 30

    def test_min_wins_for_max_simultaneous_sessions(self):
        g1 = _make_group({"max_simultaneous_sessions": 10})
        g2 = _make_group({"max_simultaneous_sessions": 3})
        user = _make_user(groups=[g1, g2])
        result = resolve_session_policy(user)
        assert result["max_simultaneous_sessions"] == 3

    def test_min_wins_for_max_sessions_per_ip(self):
        g1 = _make_group({"max_sessions_per_ip": 5})
        g2 = _make_group({"max_sessions_per_ip": 2})
        user = _make_user(groups=[g1, g2])
        result = resolve_session_policy(user)
        assert result["max_sessions_per_ip"] == 2

    def test_max_wins_for_relogin_cooldown(self):
        """Largest cooldown wins (most restrictive)."""
        g1 = _make_group({"relogin_cooldown_minutes": 5})
        g2 = _make_group({"relogin_cooldown_minutes": 15})
        user = _make_user(groups=[g1, g2])
        result = resolve_session_policy(user)
        assert result["relogin_cooldown_minutes"] == 15

    def test_true_wins_for_auto_logout(self):
        """True wins (more restrictive)."""
        g1 = _make_group({"auto_logout": False})
        g2 = _make_group({"auto_logout": True})
        user = _make_user(groups=[g1, g2])
        result = resolve_session_policy(user)
        assert result["auto_logout"] is True

    def test_true_wins_both_false(self):
        g1 = _make_group({"auto_logout": False})
        g2 = _make_group({"auto_logout": False})
        user = _make_user(groups=[g1, g2])
        result = resolve_session_policy(user)
        assert result["auto_logout"] is False

    def test_mixed_fields_across_groups(self):
        g1 = _make_group({"session_timeout_minutes": 60, "relogin_cooldown_minutes": 5})
        g2 = _make_group({"session_timeout_minutes": 30, "max_simultaneous_sessions": 3})
        user = _make_user(groups=[g1, g2])
        result = resolve_session_policy(user)
        assert result["session_timeout_minutes"] == 30
        assert result["relogin_cooldown_minutes"] == 5
        assert result["max_simultaneous_sessions"] == 3


# ---------------------------------------------------------------------------
# User override
# ---------------------------------------------------------------------------


class TestUserOverride:
    def test_override_replaces_group_field(self):
        g = _make_group({"session_timeout_minutes": 30, "max_simultaneous_sessions": 3})
        user = _make_user(
            groups=[g],
            override={"session_timeout_minutes": 120},
        )
        result = resolve_session_policy(user)
        assert result["session_timeout_minutes"] == 120
        assert result["max_simultaneous_sessions"] == 3

    def test_override_can_set_none(self):
        """User override with None removes the limit."""
        g = _make_group({"session_timeout_minutes": 30})
        user = _make_user(
            groups=[g],
            override={"session_timeout_minutes": None},
        )
        result = resolve_session_policy(user)
        assert result["session_timeout_minutes"] is None

    def test_override_adds_field_not_in_groups(self):
        g = _make_group({"session_timeout_minutes": 30})
        user = _make_user(
            groups=[g],
            override={"max_sessions_per_ip": 1},
        )
        result = resolve_session_policy(user)
        assert result["session_timeout_minutes"] == 30
        assert result["max_sessions_per_ip"] == 1

    def test_override_ignores_unknown_fields(self):
        user = _make_user(
            groups=[],
            override={"unknown_field": 42, "session_timeout_minutes": 60},
        )
        result = resolve_session_policy(user)
        assert "unknown_field" not in result
        assert result["session_timeout_minutes"] == 60


# ---------------------------------------------------------------------------
# Empty / invalid policy
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_no_groups_returns_empty(self):
        user = _make_user(groups=[])
        result = resolve_session_policy(user)
        assert result == {}

    def test_groups_with_none_policy(self):
        user = _make_user(groups=[_make_group(None)])
        result = resolve_session_policy(user)
        assert result == {}

    def test_groups_with_non_dict_policy(self):
        user = _make_user(groups=[_make_group("invalid")])
        result = resolve_session_policy(user)
        assert result == {}

    def test_groups_none_attribute(self):
        user = _make_user(groups=None)
        result = resolve_session_policy(user)
        assert result == {}

    def test_override_none(self):
        user = _make_user(groups=[], override=None)
        result = resolve_session_policy(user)
        assert result == {}

    def test_override_non_dict(self):
        user = _make_user(groups=[], override="bad")
        result = resolve_session_policy(user)
        assert result == {}


# ---------------------------------------------------------------------------
# has_any_limits
# ---------------------------------------------------------------------------


class TestHasAnyLimits:
    def test_empty_dict(self):
        assert has_any_limits({}) is False

    def test_none(self):
        assert has_any_limits(None) is False

    def test_all_none_values(self):
        policy = {f: None for f in ALL_POLICY_FIELDS}
        assert has_any_limits(policy) is False

    def test_one_non_null(self):
        assert has_any_limits({"session_timeout_minutes": 30}) is True

    def test_full_policy(self):
        policy = {
            "session_timeout_minutes": 30,
            "max_simultaneous_sessions": 5,
            "max_sessions_per_ip": 2,
            "relogin_cooldown_minutes": 5,
            "auto_logout": True,
        }
        assert has_any_limits(policy) is True
