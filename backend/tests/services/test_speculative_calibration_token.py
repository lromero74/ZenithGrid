"""
Tests for the dismiss-token signing helpers.
"""

from datetime import datetime, timedelta

import pytest
from jose import jwt

from app.config import settings
from app.services.speculative_calibration_token import (
    build_dismiss_url,
    create_dismiss_token,
    decode_dismiss_token,
)


class TestCreateDecodeDismissToken:
    def test_roundtrip_preserves_fields(self):
        token = create_dismiss_token(user_id=7, account_id=13)
        payload = decode_dismiss_token(token)
        assert payload is not None
        assert payload["sub"] == "7"
        assert payload["account_id"] == 13
        assert payload["type"] == "speculative_calibration_dismiss"

    def test_expired_token_decodes_as_none(self):
        expired = jwt.encode(
            {
                "sub": "7", "account_id": 13,
                "type": "speculative_calibration_dismiss",
                "exp": datetime.utcnow() - timedelta(days=1),
            },
            settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
        )
        assert decode_dismiss_token(expired) is None

    def test_wrong_type_decodes_as_none(self):
        wrong = jwt.encode(
            {
                "sub": "7", "account_id": 13, "type": "access",
                "exp": datetime.utcnow() + timedelta(hours=1),
            },
            settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
        )
        assert decode_dismiss_token(wrong) is None

    def test_invalid_token_decodes_as_none(self):
        assert decode_dismiss_token("not.a.valid.jwt") is None


class TestBuildDismissUrl:
    def test_includes_token_and_account_id_on_settings_route(self):
        """Dismiss link must land on /settings so the page's mount-time
        handler can catch and POST the token."""
        url = build_dismiss_url(
            user_id=7, account_id=13,
            base_url="https://tradebot.example.com",
        )
        assert url.startswith("https://tradebot.example.com/settings?")
        assert "dismiss_token=" in url
        assert "account_id=13" in url

    def test_strips_trailing_slash_on_base_url(self):
        url = build_dismiss_url(
            user_id=7, account_id=13,
            base_url="https://tradebot.example.com/",
        )
        # No double slash between host and /settings.
        assert "//settings" not in url.replace("https://", "")

    @pytest.mark.parametrize("base_url", ["", None])
    def test_tolerates_empty_base_url(self, base_url):
        """With frontend_url unset (dev mode), the URL still includes the
        token — the user clicks from the email but the origin is wrong.
        We don't want the URL builder to crash in this case."""
        url = build_dismiss_url(
            user_id=7, account_id=13, base_url=base_url or "",
        )
        assert "dismiss_token=" in url
        assert "account_id=13" in url
