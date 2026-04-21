"""
Tests for app/config.py — Pydantic settings validators.

Ensures the JWT secret key default cannot accidentally ship to production.
"""

import logging

import pytest
from pydantic import ValidationError

from app.config import Settings, DEFAULT_JWT_SECRET


class TestJwtSecretKeyValidator:
    """The default jwt_secret_key must not be accepted when environment=production."""

    def test_default_jwt_secret_rejected_in_production(self):
        """REGRESSION (sweep v2.160.4): a missing .env must not silently ship
        the publicly-known default JWT signing key."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(environment="production", jwt_secret_key=DEFAULT_JWT_SECRET)
        assert "jwt_secret_key" in str(exc_info.value).lower()

    def test_default_jwt_secret_allowed_in_development(self, caplog):
        """In non-production environments the default is allowed but warns."""
        with caplog.at_level(logging.WARNING, logger="app.config"):
            s = Settings(environment="development", jwt_secret_key=DEFAULT_JWT_SECRET)
        assert s.jwt_secret_key == DEFAULT_JWT_SECRET
        assert any("jwt_secret_key" in r.message.lower() for r in caplog.records)

    def test_override_jwt_secret_accepted_in_production(self):
        """A real override works in production with no warning and no error."""
        s = Settings(
            environment="production",
            jwt_secret_key="a-real-non-default-secret-that-is-plausibly-unique",
        )
        assert s.jwt_secret_key != DEFAULT_JWT_SECRET

    def test_override_jwt_secret_accepted_in_development(self):
        """A real override works in development too."""
        s = Settings(
            environment="development",
            jwt_secret_key="dev-only-secret-still-not-default",
        )
        assert s.jwt_secret_key != DEFAULT_JWT_SECRET
