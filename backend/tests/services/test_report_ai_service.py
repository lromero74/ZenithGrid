"""
Tests for report_ai_service — AI summary generation with provider fallback.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.report_ai_service import (
    generate_report_summary,
    _build_summary_prompt,
    _parse_tiered_summary,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def sample_report_data():
    return {
        "account_value_usd": 10000.0,
        "account_value_btc": 0.1,
        "period_start_value_usd": 9500.0,
        "period_profit_usd": 500.0,
        "period_profit_btc": 0.005,
        "total_trades": 42,
        "winning_trades": 30,
        "losing_trades": 12,
        "win_rate": 71.4,
        "net_deposits_usd": 0,
        "total_deposits_usd": 0,
        "total_withdrawals_usd": 0,
        "adjusted_account_growth_usd": 500.0,
    }


FAKE_TIERED_RESPONSE = (
    "---BEGINNER---\nGreat job!\n"
    "---COMFORTABLE---\nSolid performance.\n"
    "---EXPERIENCED---\nAlpha positive."
)


# ---------------------------------------------------------------------------
# GeminiClientWrapper — kwargs forwarding
# ---------------------------------------------------------------------------

class TestGeminiClientWrapperKwargs:
    """Ensure GeminiClientWrapper forwards kwargs like system_instruction."""

    def test_forward_system_instruction(self):
        """GeminiClientWrapper.GenerativeModel must pass **kwargs to genai."""
        from app.ai_service import GeminiClientWrapper

        wrapper = GeminiClientWrapper(api_key="fake-key")
        mock_genai = MagicMock()

        with patch.dict("sys.modules", {"google.generativeai": mock_genai}):
            wrapper.GenerativeModel(
                "gemini-2.0-flash",
                system_instruction="You are a helpful assistant.",
            )
            mock_genai.configure.assert_called_once_with(api_key="fake-key")
            mock_genai.GenerativeModel.assert_called_once_with(
                "gemini-2.0-flash",
                system_instruction="You are a helpful assistant.",
            )

    def test_forward_no_extra_kwargs(self):
        """Works fine without extra kwargs too."""
        from app.ai_service import GeminiClientWrapper

        wrapper = GeminiClientWrapper(api_key="fake-key")
        mock_genai = MagicMock()

        with patch.dict("sys.modules", {"google.generativeai": mock_genai}):
            wrapper.GenerativeModel("gemini-2.0-flash")
            mock_genai.GenerativeModel.assert_called_once_with("gemini-2.0-flash")


# ---------------------------------------------------------------------------
# Provider fallback — preferred provider fails, falls back to others
# ---------------------------------------------------------------------------

class TestProviderFallback:
    """generate_report_summary should try preferred provider then fall back."""

    @pytest.mark.asyncio
    async def test_preferred_provider_succeeds(self, mock_db, sample_report_data):
        """When the preferred provider works, use it directly."""
        mock_client = MagicMock()
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(
            return_value=MagicMock(text=FAKE_TIERED_RESPONSE)
        )
        mock_client.GenerativeModel.return_value = mock_model

        with patch("app.ai_service.get_ai_client", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_client

            result, provider_used = await generate_report_summary(
                db=mock_db,
                user_id=1,
                report_data=sample_report_data,
                period_label="Jan 1 - Jan 7, 2026",
                provider="gemini",
            )

        assert provider_used == "gemini"
        assert result is not None
        assert "comfortable" in result

    @pytest.mark.asyncio
    async def test_fallback_when_preferred_fails(self, mock_db, sample_report_data):
        """When preferred provider raises ValueError, fall back to next."""
        call_count = 0

        async def mock_get_client(provider, user_id, db):
            nonlocal call_count
            call_count += 1
            if provider == "gemini":
                raise ValueError("No API key configured for provider: gemini")
            # Return a mock Anthropic client
            mock_client = MagicMock()
            mock_client.messages = MagicMock()
            mock_client.messages.create = AsyncMock(
                return_value=MagicMock(
                    content=[MagicMock(text=FAKE_TIERED_RESPONSE)]
                )
            )
            return mock_client

        with patch(
            "app.ai_service.get_ai_client",
            side_effect=mock_get_client,
        ):
            result, provider_used = await generate_report_summary(
                db=mock_db,
                user_id=1,
                report_data=sample_report_data,
                period_label="Jan 1 - Jan 7, 2026",
                provider="gemini",
            )

        # Should have tried gemini first (failed), then claude (succeeded)
        assert call_count >= 2
        assert provider_used == "claude"
        assert result is not None

    @pytest.mark.asyncio
    async def test_all_providers_fail_returns_none(self, mock_db, sample_report_data):
        """When all providers fail, returns (None, None)."""
        with patch(
            "app.ai_service.get_ai_client",
            new_callable=AsyncMock,
            side_effect=ValueError("No API key"),
        ):
            result, provider_used = await generate_report_summary(
                db=mock_db,
                user_id=1,
                report_data=sample_report_data,
                period_label="Jan 1 - Jan 7, 2026",
                provider="gemini",
            )

        assert result is None
        assert provider_used is None

    @pytest.mark.asyncio
    async def test_no_preferred_tries_all_three(self, mock_db, sample_report_data):
        """When no preferred provider, tries claude, openai, gemini in order."""
        providers_tried = []

        async def mock_get_client(provider, user_id, db):
            providers_tried.append(provider)
            raise ValueError("No key")

        with patch(
            "app.ai_service.get_ai_client",
            side_effect=mock_get_client,
        ):
            await generate_report_summary(
                db=mock_db,
                user_id=1,
                report_data=sample_report_data,
                period_label="Jan 1 - Jan 7, 2026",
                provider=None,
            )

        # Should try all three: claude→anthropic, openai, gemini
        assert len(providers_tried) == 3

    @pytest.mark.asyncio
    async def test_preferred_gemini_fallback_order(self, mock_db, sample_report_data):
        """preferred=gemini → tries gemini, claude, openai in that order."""
        providers_tried = []

        async def mock_get_client(provider, user_id, db):
            providers_tried.append(provider)
            raise ValueError("No key")

        with patch(
            "app.ai_service.get_ai_client",
            side_effect=mock_get_client,
        ):
            await generate_report_summary(
                db=mock_db,
                user_id=1,
                report_data=sample_report_data,
                period_label="Jan 1 - Jan 7, 2026",
                provider="gemini",
            )

        # gemini first, then the claude→openai fallback
        assert providers_tried[0] == "gemini"
        assert len(providers_tried) == 3


# ---------------------------------------------------------------------------
# _parse_tiered_summary
# ---------------------------------------------------------------------------

class TestParseTieredSummary:
    def test_parse_with_delimiters(self):
        result = _parse_tiered_summary(FAKE_TIERED_RESPONSE)
        assert result["beginner"] == "Great job!"
        assert result["comfortable"] == "Solid performance."
        assert result["experienced"] == "Alpha positive."

    def test_parse_without_delimiters_falls_back(self):
        result = _parse_tiered_summary("Just a plain summary.")
        assert result["beginner"] is None
        assert result["comfortable"] == "Just a plain summary."
        assert result["experienced"] is None

    def test_parse_empty_tiers(self):
        text = "---BEGINNER---\n\n---COMFORTABLE---\nContent\n---EXPERIENCED---\n"
        result = _parse_tiered_summary(text)
        assert result["beginner"] is None  # empty → None
        assert result["comfortable"] == "Content"
        assert result["experienced"] is None  # empty → None


# ---------------------------------------------------------------------------
# _build_summary_prompt — capital movement data always included
# ---------------------------------------------------------------------------

class TestBuildSummaryPrompt:
    """Prompt must always include capital movement reconciliation data."""

    def test_capital_section_always_present_zero_deposits(self, sample_report_data):
        """Capital movement section appears even when net deposits are zero."""
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "Capital Movements & Account Reconciliation" in prompt
        assert "Account value change in period" in prompt
        assert "Trading profit in period" in prompt
        assert "Net deposits/withdrawals" in prompt
        assert "Adjusted growth" in prompt

    def test_capital_section_with_deposits(self, sample_report_data):
        """Capital section shows correct deposit/withdrawal breakdown."""
        sample_report_data["net_deposits_usd"] = 5000.0
        sample_report_data["total_deposits_usd"] = 6000.0
        sample_report_data["total_withdrawals_usd"] = 1000.0
        sample_report_data["adjusted_account_growth_usd"] = -4500.0
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "$5,000.00" in prompt  # net deposits
        assert "$6,000.00" in prompt  # total deposits
        assert "$1,000.00" in prompt  # total withdrawals
        assert "$-4,500.00" in prompt  # adjusted growth

    def test_prompt_includes_never_conflate_instruction(self, sample_report_data):
        """Prompt includes critical instruction to never conflate value change with profit."""
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "NEVER imply that account value change equals trading profit" in prompt

    def test_prompt_always_include_capital_movements_header(self, sample_report_data):
        """Prompt instructs AI to ALWAYS include ### Capital Movements section."""
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "ALWAYS include ### Capital Movements" in prompt

    def test_prior_period_comparison_included(self, sample_report_data):
        """Prior period data is included when present."""
        sample_report_data["prior_period"] = {
            "period_profit_usd": 300.0,
            "account_value_usd": 9200.0,
        }
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "Prior Period Comparison" in prompt
        assert "$300.00" in prompt
        assert "$200.00" in prompt  # change: 500 - 300

    def test_no_prior_period_when_absent(self, sample_report_data):
        """Prior period section omitted when no data."""
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "Prior Period Comparison" not in prompt
