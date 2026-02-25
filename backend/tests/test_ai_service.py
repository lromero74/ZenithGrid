"""
Tests for backend/app/ai_service.py

Covers get_ai_client() credential resolution, provider instantiation,
GeminiClientWrapper, and get_ai_analysis() dispatch.
All AI provider libraries are mocked -- no real API calls.

Note: AsyncAnthropic, AsyncOpenAI, and genai are imported LOCALLY inside
functions in ai_service.py, so we patch them at their source packages.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import google.generativeai  # noqa: F401 -- imported so patch("google.generativeai") works

from app.ai_service import get_ai_client, get_ai_analysis, GeminiClientWrapper


# ---------------------------------------------------------------------------
# get_ai_client -- credential resolution
# ---------------------------------------------------------------------------


class TestGetAiClientCredentials:
    """Tests for get_ai_client() credential resolution logic."""

    @pytest.mark.asyncio
    async def test_user_credential_used_when_available(self):
        """User-specific API key takes priority over system settings."""
        mock_db = AsyncMock()

        with patch("app.services.ai_credential_service.get_user_api_key", new_callable=AsyncMock) as mock_get_key, \
             patch("anthropic.AsyncAnthropic") as MockAnthropic:
            mock_get_key.return_value = "user-anthropic-key"
            MockAnthropic.return_value = MagicMock()

            await get_ai_client("anthropic", user_id=1, db=mock_db)

        MockAnthropic.assert_called_once_with(api_key="user-anthropic-key")
        mock_get_key.assert_called_once_with(mock_db, 1, "claude")

    @pytest.mark.asyncio
    async def test_system_fallback_when_no_user_credential(self):
        """Falls back to system settings when user has no credential."""
        mock_db = AsyncMock()

        with patch("app.services.ai_credential_service.get_user_api_key", new_callable=AsyncMock) as mock_get_key, \
             patch("app.config.settings") as mock_settings, \
             patch("anthropic.AsyncAnthropic") as MockAnthropic:
            mock_get_key.return_value = None
            mock_settings.anthropic_api_key = "system-anthropic-key"
            MockAnthropic.return_value = MagicMock()

            await get_ai_client("anthropic", user_id=1, db=mock_db)

        MockAnthropic.assert_called_once_with(api_key="system-anthropic-key")

    @pytest.mark.asyncio
    async def test_system_fallback_when_no_user_id(self):
        """Uses system settings when user_id is not provided."""
        with patch("app.config.settings") as mock_settings, \
             patch("anthropic.AsyncAnthropic") as MockAnthropic:
            mock_settings.anthropic_api_key = "system-key"
            MockAnthropic.return_value = MagicMock()

            await get_ai_client("anthropic")

        MockAnthropic.assert_called_once_with(api_key="system-key")

    @pytest.mark.asyncio
    async def test_no_api_key_raises_value_error(self):
        """Raises ValueError when no API key is found."""
        with patch("app.config.settings") as mock_settings:
            mock_settings.anthropic_api_key = ""

            with pytest.raises(ValueError, match="No API key configured"):
                await get_ai_client("anthropic")

    @pytest.mark.asyncio
    async def test_user_credential_exception_falls_back_gracefully(self):
        """Exception fetching user credentials falls back to system."""
        mock_db = AsyncMock()

        with patch("app.services.ai_credential_service.get_user_api_key", new_callable=AsyncMock) as mock_get_key, \
             patch("app.config.settings") as mock_settings, \
             patch("anthropic.AsyncAnthropic") as MockAnthropic:
            mock_get_key.side_effect = Exception("DB error")
            mock_settings.anthropic_api_key = "fallback-key"
            MockAnthropic.return_value = MagicMock()

            await get_ai_client("anthropic", user_id=1, db=mock_db)

        MockAnthropic.assert_called_once_with(api_key="fallback-key")

    @pytest.mark.asyncio
    async def test_openai_user_credential_maps_to_openai(self):
        """OpenAI provider maps to 'openai' in credential lookup."""
        mock_db = AsyncMock()

        with patch("app.services.ai_credential_service.get_user_api_key", new_callable=AsyncMock) as mock_get_key, \
             patch("openai.AsyncOpenAI") as MockOpenAI:
            mock_get_key.return_value = "user-oai-key"
            MockOpenAI.return_value = MagicMock()

            await get_ai_client("openai", user_id=2, db=mock_db)

        mock_get_key.assert_called_once_with(mock_db, 2, "openai")
        MockOpenAI.assert_called_once_with(api_key="user-oai-key")

    @pytest.mark.asyncio
    async def test_gemini_user_credential_maps_to_gemini(self):
        """Gemini provider maps to 'gemini' in credential lookup."""
        mock_db = AsyncMock()

        with patch("app.services.ai_credential_service.get_user_api_key", new_callable=AsyncMock) as mock_get_key, \
             patch("google.generativeai"):
            mock_get_key.return_value = "user-gem-key"

            client = await get_ai_client("gemini", user_id=3, db=mock_db)

        mock_get_key.assert_called_once_with(mock_db, 3, "gemini")
        assert isinstance(client, GeminiClientWrapper)
        assert client.api_key == "user-gem-key"

    @pytest.mark.asyncio
    async def test_no_api_key_for_openai_raises(self):
        """Raises ValueError when no OpenAI key configured."""
        with patch("app.config.settings") as mock_settings:
            mock_settings.openai_api_key = ""

            with pytest.raises(ValueError, match="No API key configured"):
                await get_ai_client("openai")

    @pytest.mark.asyncio
    async def test_no_api_key_for_gemini_raises(self):
        """Raises ValueError when no Gemini key configured."""
        with patch("app.config.settings") as mock_settings:
            mock_settings.gemini_api_key = ""

            with pytest.raises(ValueError, match="No API key configured"):
                await get_ai_client("gemini")

    @pytest.mark.asyncio
    async def test_system_fallback_openai(self):
        """Uses system OpenAI key when no user credential."""
        with patch("app.config.settings") as mock_settings, \
             patch("openai.AsyncOpenAI") as MockOpenAI:
            mock_settings.openai_api_key = "sys-oai-key"
            MockOpenAI.return_value = MagicMock()

            await get_ai_client("openai")

        MockOpenAI.assert_called_once_with(api_key="sys-oai-key")

    @pytest.mark.asyncio
    async def test_system_fallback_gemini(self):
        """Uses system Gemini key when no user credential."""
        with patch("app.config.settings") as mock_settings, \
             patch("google.generativeai"):
            mock_settings.gemini_api_key = "sys-gem-key"

            client = await get_ai_client("gemini")

        assert isinstance(client, GeminiClientWrapper)
        assert client.api_key == "sys-gem-key"


# ---------------------------------------------------------------------------
# get_ai_client -- provider instantiation
# ---------------------------------------------------------------------------


class TestGetAiClientProviders:
    """Tests for get_ai_client() provider-specific client creation."""

    @pytest.mark.asyncio
    async def test_anthropic_client_created(self):
        """Anthropic provider creates AsyncAnthropic client."""
        with patch("app.config.settings") as mock_settings, \
             patch("anthropic.AsyncAnthropic") as MockAnthropic:
            mock_settings.anthropic_api_key = "ant-key"
            MockAnthropic.return_value = MagicMock()

            await get_ai_client("anthropic")

        MockAnthropic.assert_called_once_with(api_key="ant-key")

    @pytest.mark.asyncio
    async def test_openai_client_created(self):
        """OpenAI provider creates AsyncOpenAI client."""
        with patch("app.config.settings") as mock_settings, \
             patch("openai.AsyncOpenAI") as MockOpenAI:
            mock_settings.openai_api_key = "oai-key"
            MockOpenAI.return_value = MagicMock()

            await get_ai_client("openai")

        MockOpenAI.assert_called_once_with(api_key="oai-key")

    @pytest.mark.asyncio
    async def test_gemini_returns_wrapper(self):
        """Gemini provider returns GeminiClientWrapper."""
        with patch("app.config.settings") as mock_settings, \
             patch("google.generativeai"):
            mock_settings.gemini_api_key = "gem-key"

            client = await get_ai_client("gemini")

        assert isinstance(client, GeminiClientWrapper)
        assert client.api_key == "gem-key"

    @pytest.mark.asyncio
    async def test_unsupported_provider_raises(self):
        """Unsupported provider raises ValueError."""
        with pytest.raises(ValueError, match="No API key configured|Unsupported"):
            await get_ai_client("fakeprovider")

    @pytest.mark.asyncio
    async def test_unsupported_provider_with_user_key_raises(self):
        """Unsupported provider with a user credential still raises ValueError.

        This covers the else branch at the end of get_ai_client() (line 77).
        If a user has a stored credential for a provider name that passes
        the API-key check but is not in the if/elif dispatch chain, the
        'Unsupported AI provider' error is raised.
        """
        mock_db = AsyncMock()

        with patch(
            "app.services.ai_credential_service.get_user_api_key", new_callable=AsyncMock
        ) as mock_get_key:
            # User has a credential for a bogus provider name
            mock_get_key.return_value = "user-key-for-bogus"

            with pytest.raises(ValueError, match="Unsupported AI provider: bogusprovider"):
                await get_ai_client("bogusprovider", user_id=99, db=mock_db)

    @pytest.mark.asyncio
    async def test_provider_name_case_insensitive(self):
        """Provider names are case-insensitive."""
        with patch("app.config.settings") as mock_settings, \
             patch("anthropic.AsyncAnthropic") as MockAnthropic:
            mock_settings.anthropic_api_key = "key"
            MockAnthropic.return_value = MagicMock()

            await get_ai_client("ANTHROPIC")

        MockAnthropic.assert_called_once()

    @pytest.mark.asyncio
    async def test_claude_alias_maps_to_anthropic(self):
        """'claude' provider name maps to Anthropic credentials."""
        mock_db = AsyncMock()

        with patch("app.services.ai_credential_service.get_user_api_key", new_callable=AsyncMock) as mock_get_key, \
             patch("app.config.settings") as mock_settings:
            mock_get_key.return_value = None
            mock_settings.anthropic_api_key = ""

            # Provider "claude" -> credential "claude" but system fallback
            # checks provider == "anthropic" which won't match "claude"
            with pytest.raises(ValueError, match="No API key configured"):
                await get_ai_client("claude", user_id=1, db=mock_db)

        mock_get_key.assert_called_once_with(mock_db, 1, "claude")

    @pytest.mark.asyncio
    async def test_mixed_case_openai(self):
        """Mixed-case 'OpenAI' is correctly normalized."""
        with patch("app.config.settings") as mock_settings, \
             patch("openai.AsyncOpenAI") as MockOpenAI:
            mock_settings.openai_api_key = "key"
            MockOpenAI.return_value = MagicMock()

            await get_ai_client("OpenAI")

        MockOpenAI.assert_called_once()

    @pytest.mark.asyncio
    async def test_mixed_case_gemini(self):
        """Mixed-case 'Gemini' is correctly normalized."""
        with patch("app.config.settings") as mock_settings, \
             patch("google.generativeai"):
            mock_settings.gemini_api_key = "key"

            client = await get_ai_client("GEMINI")

        assert isinstance(client, GeminiClientWrapper)


# ---------------------------------------------------------------------------
# GeminiClientWrapper
# ---------------------------------------------------------------------------


class TestGeminiClientWrapper:
    """Tests for GeminiClientWrapper."""

    def test_stores_api_key(self):
        """Wrapper stores the API key."""
        wrapper = GeminiClientWrapper(api_key="test-gem-key")
        assert wrapper.api_key == "test-gem-key"

    @patch("google.generativeai")
    def test_generative_model_configures_and_creates(self, mock_genai):
        """GenerativeModel() configures genai and creates model."""
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        wrapper = GeminiClientWrapper(api_key="gem-key")
        result = wrapper.GenerativeModel("gemini-2.0-flash")

        mock_genai.configure.assert_called_once_with(api_key="gem-key")
        mock_genai.GenerativeModel.assert_called_once_with("gemini-2.0-flash")
        assert result == mock_model

    @patch("google.generativeai")
    def test_generative_model_passes_kwargs(self, mock_genai):
        """Extra kwargs are forwarded to genai.GenerativeModel."""
        wrapper = GeminiClientWrapper(api_key="key")
        wrapper.GenerativeModel("gemini-pro", generation_config={"temp": 0.5})

        mock_genai.GenerativeModel.assert_called_once_with(
            "gemini-pro", generation_config={"temp": 0.5}
        )

    @patch("google.generativeai")
    def test_generative_model_default_model_name(self, mock_genai):
        """Default model name is gemini-2.0-flash."""
        wrapper = GeminiClientWrapper(api_key="key")
        wrapper.GenerativeModel()

        mock_genai.GenerativeModel.assert_called_once_with("gemini-2.0-flash")

    @patch("google.generativeai")
    def test_multiple_model_instances_reconfigure(self, mock_genai):
        """Creating multiple models calls configure each time."""
        wrapper = GeminiClientWrapper(api_key="key-1")
        wrapper.GenerativeModel("model-a")
        wrapper.GenerativeModel("model-b")

        assert mock_genai.configure.call_count == 2
        assert mock_genai.GenerativeModel.call_count == 2


# ---------------------------------------------------------------------------
# get_ai_analysis -- dispatch per provider
# ---------------------------------------------------------------------------


class TestGetAiAnalysis:
    """Tests for get_ai_analysis() multi-provider dispatch."""

    @pytest.mark.asyncio
    async def test_anthropic_analysis(self):
        """Anthropic analysis calls client.messages.create correctly."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="AI says buy")]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        result = await get_ai_analysis(mock_client, "anthropic", "Analyze BTC")

        assert result == "AI says buy"
        mock_client.messages.create.assert_called_once_with(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            messages=[{"role": "user", "content": "Analyze BTC"}],
        )

    @pytest.mark.asyncio
    async def test_anthropic_custom_model(self):
        """Anthropic analysis uses custom model when provided."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="response")]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        await get_ai_analysis(mock_client, "anthropic", "prompt", model="claude-3-haiku-20240307")

        call_args = mock_client.messages.create.call_args
        assert call_args.kwargs["model"] == "claude-3-haiku-20240307"

    @pytest.mark.asyncio
    async def test_openai_analysis(self):
        """OpenAI analysis calls client.chat.completions.create correctly."""
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "GPT says sell"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await get_ai_analysis(mock_client, "openai", "Analyze ETH")

        assert result == "GPT says sell"
        mock_client.chat.completions.create.assert_called_once_with(
            model="gpt-4-turbo-preview",
            messages=[{"role": "user", "content": "Analyze ETH"}],
            max_tokens=2000,
        )

    @pytest.mark.asyncio
    async def test_openai_custom_model(self):
        """OpenAI analysis uses custom model when provided."""
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "response"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        await get_ai_analysis(mock_client, "openai", "prompt", model="gpt-4o")

        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_gemini_analysis(self):
        """Gemini analysis uses GenerativeModel and generate_content_async."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Gemini says hold"
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)

        mock_client = MagicMock()
        mock_client.GenerativeModel.return_value = mock_model

        result = await get_ai_analysis(mock_client, "gemini", "Analyze SOL")

        assert result == "Gemini says hold"
        mock_client.GenerativeModel.assert_called_once_with("gemini-2.0-flash")
        mock_model.generate_content_async.assert_called_once_with("Analyze SOL")

    @pytest.mark.asyncio
    async def test_gemini_custom_model(self):
        """Gemini analysis uses custom model when provided."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "response"
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)

        mock_client = MagicMock()
        mock_client.GenerativeModel.return_value = mock_model

        await get_ai_analysis(mock_client, "gemini", "prompt", model="gemini-pro")

        mock_client.GenerativeModel.assert_called_once_with("gemini-pro")

    @pytest.mark.asyncio
    async def test_unsupported_provider_raises(self):
        """Unsupported provider raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported AI provider"):
            await get_ai_analysis(MagicMock(), "fakeprovider", "prompt")

    @pytest.mark.asyncio
    async def test_provider_case_insensitive(self):
        """Provider name is lowercased before dispatch."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="ok")]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        result = await get_ai_analysis(mock_client, "ANTHROPIC", "test")
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_anthropic_default_model_name(self):
        """Anthropic uses default model when model param is None."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="response")]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        await get_ai_analysis(mock_client, "anthropic", "test", model=None)

        call_args = mock_client.messages.create.call_args
        assert call_args.kwargs["model"] == "claude-sonnet-4-5-20250929"

    @pytest.mark.asyncio
    async def test_openai_default_model_name(self):
        """OpenAI uses default model when model param is None."""
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "response"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        await get_ai_analysis(mock_client, "openai", "test", model=None)

        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs["model"] == "gpt-4-turbo-preview"

    @pytest.mark.asyncio
    async def test_gemini_default_model_name(self):
        """Gemini uses default model when model param is None."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "response"
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)

        mock_client = MagicMock()
        mock_client.GenerativeModel.return_value = mock_model

        await get_ai_analysis(mock_client, "gemini", "test", model=None)

        mock_client.GenerativeModel.assert_called_once_with("gemini-2.0-flash")
