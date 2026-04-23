"""
Tests for app.services.speculative_calibration_apply_token.
"""

from datetime import datetime, timedelta

from jose import jwt

from app.config import settings
from app.services.speculative_calibration_apply_token import (
    build_apply_proposal_url,
    create_apply_proposal_token,
    decode_apply_proposal_token,
)


class TestTokenRoundTrip:
    def test_roundtrip_preserves_fields(self):
        tok = create_apply_proposal_token(user_id=7, account_id=13, proposal_id=42)
        payload = decode_apply_proposal_token(tok)
        assert payload is not None
        assert payload["sub"] == "7"
        assert payload["account_id"] == 13
        assert payload["proposal_id"] == 42
        assert payload["type"] == "speculative_calibration_apply_proposal"

    def test_expired_token_returns_none(self):
        expired = jwt.encode(
            {
                "sub": "7", "account_id": 13, "proposal_id": 42,
                "type": "speculative_calibration_apply_proposal",
                "exp": datetime.utcnow() - timedelta(days=1),
            },
            settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
        )
        assert decode_apply_proposal_token(expired) is None

    def test_wrong_type_returns_none(self):
        """A dismiss token (or any other type) MUST NOT be accepted as an
        apply token — that'd let a dismiss link mutate scorer weights."""
        wrong = jwt.encode(
            {
                "sub": "7", "account_id": 13, "proposal_id": 42,
                "type": "speculative_calibration_dismiss",  # wrong type
                "exp": datetime.utcnow() + timedelta(hours=1),
            },
            settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
        )
        assert decode_apply_proposal_token(wrong) is None

    def test_malformed_token_returns_none(self):
        assert decode_apply_proposal_token("not.a.jwt") is None


class TestBuildApplyProposalUrl:
    def test_includes_all_query_params_on_settings_route(self):
        url = build_apply_proposal_url(
            user_id=7, account_id=13, proposal_id=42,
            base_url="https://bot.example.com",
        )
        assert url.startswith("https://bot.example.com/settings?")
        assert "apply_token=" in url
        assert "account_id=13" in url
        assert "proposal_id=42" in url

    def test_strips_trailing_slash(self):
        url = build_apply_proposal_url(
            user_id=7, account_id=13, proposal_id=42,
            base_url="https://bot.example.com/",
        )
        assert "//settings" not in url.replace("https://", "")
