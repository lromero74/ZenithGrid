"""Tests for the single-source AI provider → credential-name mapping."""
import pytest

from app.utils.ai_credentials import credential_name_for


class TestCredentialNameFor:
    def test_known_providers_map(self):
        assert credential_name_for("claude") == "claude"
        assert credential_name_for("gpt") == "openai"
        assert credential_name_for("openai") == "openai"
        assert credential_name_for("gemini") == "gemini"

    def test_case_insensitive(self):
        assert credential_name_for("Claude") == "claude"
        assert credential_name_for("GPT") == "openai"

    def test_unknown_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown AI model"):
            credential_name_for("mistral")

    def test_none_or_empty_raises(self):
        with pytest.raises(ValueError):
            credential_name_for("")
        with pytest.raises(ValueError):
            credential_name_for(None)
