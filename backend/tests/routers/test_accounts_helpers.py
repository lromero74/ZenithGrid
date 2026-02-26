"""Tests for accounts_router helper functions (_mask_key_name, validate_prop_firm_config)"""

import pytest

from app.exceptions import ValidationError
from app.routers.accounts_router import _mask_key_name
from app.services.account_service import validate_prop_firm_config


class TestMaskKeyName:
    def test_masks_long_key(self):
        result = _mask_key_name("organizations/abc123/apiKeys/xyz789")
        assert result.startswith("orga")
        assert result.endswith("z789")
        assert "****" in result

    def test_short_key_returns_asterisks(self):
        result = _mask_key_name("short")
        assert result == "****"

    def test_none_returns_none(self):
        assert _mask_key_name(None) is None

    def test_empty_string_returns_none(self):
        assert _mask_key_name("") is None

    def test_exactly_8_chars(self):
        assert _mask_key_name("12345678") == "****"

    def test_9_chars_shows_partial(self):
        result = _mask_key_name("123456789")
        assert result == "1234****6789"

    def test_handles_encrypted_value(self):
        """Encrypted values (starting with FERNET:) should be decrypted before masking."""
        # Just verify it doesn't crash on encrypted values
        # Actual behavior depends on encryption key availability
        from app.encryption import encrypt_value
        encrypted = encrypt_value("test_api_key_1234")
        result = _mask_key_name(encrypted)
        assert result is not None
        # Should contain mask pattern
        assert "****" in result


class TestValidatePropFirmConfig:
    def test_valid_config(self):
        """Should not raise for valid config."""
        config = {"bridge_url": "https://api.example.com", "testnet": False}
        validate_prop_firm_config(config, "mt5_bridge")  # Should not raise

    def test_non_dict_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_prop_firm_config("not a dict", "mt5_bridge")
        assert exc_info.value.status_code == 400

    def test_rejects_non_http_scheme(self):
        config = {"bridge_url": "ftp://evil.com/api"}
        with pytest.raises(ValidationError) as exc_info:
            validate_prop_firm_config(config, "mt5_bridge")
        assert "http" in exc_info.value.message.lower()

    def test_rejects_localhost(self):
        config = {"bridge_url": "http://localhost:8080/api"}
        with pytest.raises(ValidationError) as exc_info:
            validate_prop_firm_config(config, "mt5_bridge")
        assert "private" in exc_info.value.message.lower()

    def test_rejects_127_0_0_1(self):
        config = {"bridge_url": "http://127.0.0.1:8080/api"}
        with pytest.raises(ValidationError):
            validate_prop_firm_config(config, "mt5_bridge")

    def test_rejects_private_10_network(self):
        config = {"bridge_url": "http://10.0.0.5:8080/api"}
        with pytest.raises(ValidationError):
            validate_prop_firm_config(config, "mt5_bridge")

    def test_rejects_private_192_168_network(self):
        config = {"bridge_url": "http://192.168.1.1/api"}
        with pytest.raises(ValidationError):
            validate_prop_firm_config(config, "mt5_bridge")

    def test_rejects_private_172_network(self):
        config = {"bridge_url": "http://172.16.0.1/api"}
        with pytest.raises(ValidationError):
            validate_prop_firm_config(config, "mt5_bridge")

    def test_non_bool_testnet_raises(self):
        config = {"testnet": "yes"}
        with pytest.raises(ValidationError) as exc_info:
            validate_prop_firm_config(config, "mt5_bridge")
        assert "boolean" in exc_info.value.message.lower()

    def test_unknown_keys_raises(self):
        config = {"bridge_url": "https://api.example.com", "malicious_key": "value"}
        with pytest.raises(ValidationError) as exc_info:
            validate_prop_firm_config(config, "mt5_bridge")
        assert "Unknown keys" in exc_info.value.message

    def test_all_allowed_keys_accepted(self):
        config = {
            "bridge_url": "https://api.example.com",
            "testnet": True,
            "api_key": "key123",
            "api_secret": "secret",
            "broker": "my_broker",
            "server": "demo.server.com",
        }
        validate_prop_firm_config(config, "mt5_bridge")  # Should not raise
