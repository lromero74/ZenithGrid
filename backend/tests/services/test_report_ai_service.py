"""
Tests for report_ai_service — AI summary generation with provider fallback.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.report_ai_service import (
    generate_report_summary,
    _build_summary_prompt,
    _parse_tiered_summary,
    _summarize_conditions,
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
    "---SUMMARY---\nGreat job!\n"
    "---DETAILED---\nAlpha positive."
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
        assert "simple" in result

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
    async def test_all_providers_no_credentials_returns_none(self, mock_db, sample_report_data):
        """When no provider has credentials, returns (None, None)."""
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
    async def test_all_providers_fail_at_call_returns_error(self, mock_db, sample_report_data):
        """When credentials found but all AI calls fail, returns error dict."""
        mock_client = MagicMock()
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(
            side_effect=Exception("429 Rate limited")
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

        assert isinstance(result, dict)
        assert "_error" in result
        assert result["_error"] == "all_providers_failed"
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
        assert result["simple"] == "Great job!"
        assert result["detailed"] == "Alpha positive."

    def test_parse_without_delimiters_falls_back(self):
        result = _parse_tiered_summary("Just a plain summary.")
        assert result["simple"] == "Just a plain summary."
        assert result["detailed"] is None

    def test_parse_empty_tiers(self):
        text = "---SUMMARY---\n\n---DETAILED---\nContent"
        result = _parse_tiered_summary(text)
        assert result["simple"] is None  # empty → None
        assert result["detailed"] == "Content"

    def test_parse_strips_stray_delimiters(self):
        """Stray delimiter artifacts like ---DELIMITER--- are stripped."""
        text = (
            "---SUMMARY---\nGreat job!\n---DELIMITER---\n"
            "---DETAILED---\nAlpha positive.\n---END---"
        )
        result = _parse_tiered_summary(text)
        assert "DELIMITER" not in result["simple"]
        assert result["simple"] == "Great job!"
        assert "END" not in result["detailed"]
        assert result["detailed"] == "Alpha positive."


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

    def test_prompt_includes_capital_movements_in_required_sections(self, sample_report_data):
        """Prompt lists ### Capital Movements as a required section."""
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "### Capital Movements" in prompt

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

    def test_implied_deposits_source_adds_note(self, sample_report_data):
        """When deposits_source is 'implied', prompt warns AI not to say no deposits."""
        sample_report_data["deposits_source"] = "implied"
        sample_report_data["net_deposits_usd"] = 309.16
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "Do NOT say 'no deposits were made'" in prompt
        assert "native-currency accounting" in prompt

    def test_transfers_source_no_implied_note(self, sample_report_data):
        """When deposits_source is 'transfers', no implied note is added."""
        sample_report_data["deposits_source"] = "transfers"
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "Do NOT say 'no deposits were made'" not in prompt

    def test_individual_transfers_in_prompt(self, sample_report_data):
        """Non-staking transfer records are listed individually in the prompt."""
        sample_report_data["transfer_records"] = [
            {"date": "2026-02-23", "type": "deposit", "amount_usd": 150.0},
            {"date": "2026-02-20", "type": "withdrawal", "amount_usd": 50.0},
        ]
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "Individual transfers" in prompt
        assert "2026-02-23: Deposit +$150.00" in prompt
        assert "2026-02-20: Withdrawal -$50.00" in prompt

    def test_staking_rewards_aggregated(self, sample_report_data):
        """Staking rewards (original_type=send, type=deposit) are aggregated."""
        sample_report_data["transfer_records"] = [
            {"date": "2026-02-23", "type": "deposit", "original_type": "send",
             "amount_usd": 0.12},
            {"date": "2026-02-22", "type": "deposit", "original_type": "send",
             "amount_usd": 0.05},
            {"date": "2026-02-20", "type": "withdrawal", "amount_usd": 50.0},
        ]
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "Staking rewards: 2 deposits, total +$0.17" in prompt
        # Non-staking transfer still listed individually
        assert "2026-02-20: Withdrawal -$50.00" in prompt
        # Staking rewards NOT listed individually
        assert "2026-02-23" not in prompt

    def test_only_staking_no_individual_section(self, sample_report_data):
        """When only staking rewards exist, no 'Individual transfers' header."""
        sample_report_data["transfer_records"] = [
            {"date": "2026-02-23", "type": "deposit", "original_type": "send",
             "amount_usd": 0.10},
        ]
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "Staking rewards: 1 deposits" in prompt
        assert "Individual transfers" not in prompt

    def test_no_transfers_no_individual_section(self, sample_report_data):
        """When no transfer records, individual transfers section is omitted."""
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "Individual transfers" not in prompt

    def test_empty_transfers_no_individual_section(self, sample_report_data):
        """Empty transfer_records list should not produce individual section."""
        sample_report_data["transfer_records"] = []
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "Individual transfers" not in prompt

    def test_trade_summary_included_when_present(self, sample_report_data):
        """Trading activity line appears in prompt when trade_summary exists."""
        sample_report_data["trade_summary"] = {
            "total_trades": 15,
            "winning_trades": 10,
            "losing_trades": 5,
            "net_profit_usd": 250.50,
        }
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "Trading activity: 15 trades" in prompt
        assert "10W/5L" in prompt
        assert "+$250.50" in prompt

    def test_trade_summary_negative_pnl(self, sample_report_data):
        """Negative P&L shows without plus sign."""
        sample_report_data["trade_summary"] = {
            "total_trades": 3,
            "winning_trades": 0,
            "losing_trades": 3,
            "net_profit_usd": -100.00,
        }
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "Trading activity: 3 trades" in prompt
        assert "0W/3L" in prompt

    def test_trade_summary_absent_no_line(self, sample_report_data):
        """No trading activity line when trade_summary is absent."""
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "Trading activity:" not in prompt

    def test_trade_summary_zero_trades_no_line(self, sample_report_data):
        """No trading activity line when total_trades is 0."""
        sample_report_data["trade_summary"] = {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "net_profit_usd": 0,
        }
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "Trading activity:" not in prompt

    def test_bot_strategies_included(self, sample_report_data):
        """Bot strategy context appears in prompt when present."""
        sample_report_data["bot_strategies"] = [{
            "name": "DCA Bot",
            "strategy_type": "dca_grid",
            "pairs": ["ETH-BTC", "SOL-USD"],
            "config": {
                "take_profit_percentage": 2,
                "max_safety_orders": 8,
                "safety_order_percentage": 100,
                "price_deviation": 2,
                "max_concurrent_deals": 2,
                "safety_order_step_scale": 2,
                "safety_order_volume_scale": 2,
                "base_order_conditions": {
                    "groups": [{
                        "conditions": [{
                            "type": "bb_percent",
                            "operator": "crossing_above",
                            "value": 10,
                            "timeframe": "FIFTEEN_MINUTE",
                        }],
                        "logic": "and",
                    }],
                    "groupLogic": "and",
                },
            },
            "trades_in_period": 15,
            "wins_in_period": 12,
        }]
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "Trading Strategy Context" in prompt
        assert "DCA Bot" in prompt
        assert "dca_grid" in prompt
        assert "take_profit=2%" in prompt
        assert "max_safety_orders=8" in prompt
        assert "safety_order_step_scale=2" in prompt
        assert "safety_order_volume_scale=2" in prompt
        assert "Entry signals:" in prompt
        assert "bb_percent crossing_above 10" in prompt
        assert "DCA Mechanics" in prompt
        assert "minimum price drop from entry" in prompt
        # ETH-BTC pair should trigger BTC accumulation note
        assert "BTC Accumulation Strategy" in prompt
        assert "Do NOT frame BTC-pair positions" in prompt

    def test_strategy_multiple_conditions_and_logic(self, sample_report_data):
        """Multiple conditions joined by AND appear in prompt."""
        sample_report_data["bot_strategies"] = [{
            "name": "Multi Signal Bot",
            "strategy_type": "indicator_based",
            "pairs": ["BTC-USD"],
            "config": {
                "take_profit_percentage": 1.5,
                "max_safety_orders": 2,
                "base_order_conditions": {
                    "groups": [{
                        "conditions": [
                            {"type": "rsi", "operator": "greater_than",
                             "value": 50, "timeframe": "FIFTEEN_MINUTE"},
                            {"type": "volume_rsi", "operator": "increasing",
                             "value": 2, "timeframe": "THREE_MINUTE"},
                        ],
                        "logic": "and",
                    }],
                    "groupLogic": "and",
                },
            },
            "trades_in_period": 5,
            "wins_in_period": 4,
        }]
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "rsi greater_than 50" in prompt
        assert "volume_rsi increasing 2" in prompt
        assert " AND " in prompt

    def test_strategy_trailing_tp_and_stop_loss(self, sample_report_data):
        """Trailing take profit and stop loss flags appear when enabled."""
        sample_report_data["bot_strategies"] = [{
            "name": "Trailing Bot",
            "strategy_type": "dca_grid",
            "pairs": ["SOL-USD"],
            "config": {
                "trailing_take_profit": True,
                "trailing_deviation": 0.5,
                "stop_loss_enabled": True,
            },
            "trades_in_period": 3,
            "wins_in_period": 2,
        }]
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "trailing_tp=0.5%" in prompt
        assert "stop_loss=enabled" in prompt

    def test_usd_only_bots_no_btc_accumulation_note(self, sample_report_data):
        """USD-pair-only bots should NOT get BTC accumulation context."""
        sample_report_data["bot_strategies"] = [{
            "name": "USD Bot",
            "strategy_type": "dca_grid",
            "pairs": ["SOL-USD", "ETH-USD"],
            "config": {"take_profit_percentage": 2},
            "trades_in_period": 5,
            "wins_in_period": 4,
        }]
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "DCA Mechanics" in prompt
        assert "BTC Accumulation Strategy" not in prompt

    def test_no_bot_strategies_no_section(self, sample_report_data):
        """No strategy section when bot_strategies is empty."""
        prompt = _build_summary_prompt(sample_report_data, "Jan 1 - Jan 7, 2026")
        assert "Trading Strategy Context" not in prompt


# ---------------------------------------------------------------------------
# _summarize_conditions
# ---------------------------------------------------------------------------

class TestSummarizeConditions:
    def test_single_condition(self):
        conds = {
            "groups": [{
                "conditions": [
                    {"type": "bb_percent", "operator": "crossing_above",
                     "value": 10, "timeframe": "FIFTEEN_MINUTE"}
                ],
                "logic": "and",
            }],
            "groupLogic": "and",
        }
        result = _summarize_conditions(conds)
        assert "bb_percent crossing_above 10 (FIFTEEN_MINUTE)" in result

    def test_multiple_conditions_and(self):
        conds = {
            "groups": [{
                "conditions": [
                    {"type": "rsi", "operator": "greater_than",
                     "value": 50, "timeframe": "FIVE_MINUTE"},
                    {"type": "volume_rsi", "operator": "increasing",
                     "value": 2, "timeframe": "THREE_MINUTE"},
                ],
                "logic": "and",
            }],
            "groupLogic": "and",
        }
        result = _summarize_conditions(conds)
        assert "rsi greater_than 50 (FIVE_MINUTE)" in result
        assert " AND " in result
        assert "volume_rsi increasing 2 (THREE_MINUTE)" in result

    def test_empty_conditions(self):
        assert _summarize_conditions(None) == ""
        assert _summarize_conditions({}) == ""
        assert _summarize_conditions({"groups": []}) == ""

    def test_no_conditions_key(self):
        assert _summarize_conditions({"groups": [{"conditions": []}]}) == ""
