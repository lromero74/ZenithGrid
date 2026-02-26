"""
Tests for backend/app/services/bot_validation_service.py

Tests quote currency validation, AI market focus auto-correction,
and bidirectional budget configuration validation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.exceptions import ValidationError

from app.services.bot_validation_service import (
    validate_quote_currency,
    auto_correct_market_focus,
)


# ---------------------------------------------------------------------------
# validate_quote_currency
# ---------------------------------------------------------------------------


class TestValidateQuoteCurrency:
    """Tests for validate_quote_currency()."""

    def test_single_usd_pair(self):
        """Happy path: single USD-quoted pair returns 'USD'."""
        result = validate_quote_currency(["BTC-USD"])
        assert result == "USD"

    def test_multiple_same_quote(self):
        """Happy path: multiple pairs with same quote returns that quote."""
        result = validate_quote_currency(["ETH-BTC", "SOL-BTC", "ADA-BTC"])
        assert result == "BTC"

    def test_empty_pairs_returns_none(self):
        """Edge case: empty list returns None."""
        result = validate_quote_currency([])
        assert result is None

    def test_pair_without_dash_ignored(self):
        """Edge case: pairs without dash separator are ignored."""
        result = validate_quote_currency(["ETHBTC"])
        assert result is None

    def test_mixed_quote_currencies_raises(self):
        """Failure: mixed quote currencies raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_quote_currency(["ETH-BTC", "SOL-USD"])
        assert exc_info.value.status_code == 400
        assert "same quote currency" in exc_info.value.message

    def test_single_pair_no_dash(self):
        """Edge case: single pair without dash returns None (no quotes found)."""
        result = validate_quote_currency(["BTCUSD"])
        assert result is None

    def test_mixed_with_three_currencies_raises(self):
        """Failure: three different quote currencies also raises."""
        with pytest.raises(ValidationError) as exc_info:
            validate_quote_currency(["ETH-BTC", "SOL-USD", "ADA-USDC"])
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# auto_correct_market_focus
# ---------------------------------------------------------------------------


class TestAutoCorrectMarketFocus:
    """Tests for auto_correct_market_focus()."""

    def test_corrects_mismatch(self):
        """Happy path: corrects market_focus when it doesn't match quote."""
        config = {"market_focus": "BTC"}
        auto_correct_market_focus("ai_autonomous", config, "USD")
        assert config["market_focus"] == "USD"

    def test_no_correction_when_matching(self):
        """Happy path: no change when market_focus matches quote."""
        config = {"market_focus": "USD"}
        auto_correct_market_focus("ai_autonomous", config, "USD")
        assert config["market_focus"] == "USD"

    def test_skips_non_ai_strategy(self):
        """Edge case: non-AI strategy is not corrected."""
        config = {"market_focus": "BTC"}
        auto_correct_market_focus("macd_dca", config, "USD")
        assert config["market_focus"] == "BTC"  # unchanged

    def test_skips_when_no_quote_currency(self):
        """Edge case: no quote currency means no correction."""
        config = {"market_focus": "BTC"}
        auto_correct_market_focus("ai_autonomous", config, None)
        assert config["market_focus"] == "BTC"  # unchanged

    def test_skips_when_no_market_focus_key(self):
        """Edge case: config without market_focus key is left alone."""
        config = {"other_key": "value"}
        auto_correct_market_focus("ai_autonomous", config, "USD")
        assert "market_focus" not in config

    def test_correction_with_entity_name(self):
        """Happy path: entity_name parameter works (for logging)."""
        config = {"market_focus": "BTC"}
        auto_correct_market_focus("ai_autonomous", config, "USD", entity_name="TestBot")
        assert config["market_focus"] == "USD"


# ---------------------------------------------------------------------------
# validate_bidirectional_budget_config
# (requires extensive mocking of exchange and budget_calculator)
# ---------------------------------------------------------------------------


class TestValidateBidirectionalBudgetConfig:
    """Tests for validate_bidirectional_budget_config()."""

    @pytest.mark.asyncio
    @patch("app.services.budget_calculator.validate_bidirectional_budget")
    @patch("app.services.exchange_service.get_exchange_client_for_account")
    async def test_happy_path_usd_bot(self, mock_get_exchange, mock_validate, db_session):
        """Happy path: valid bidirectional config returns required amounts."""
        mock_exchange = AsyncMock()
        mock_exchange.get_account = AsyncMock(return_value={
            "USD": 5000.0, "USDC": 0.0, "USDT": 0.0, "BTC": 0.5
        })
        mock_exchange.calculate_aggregate_usd_value = AsyncMock(return_value=10000.0)
        mock_exchange.get_btc_usd_price = AsyncMock(return_value=50000.0)
        mock_get_exchange.return_value = mock_exchange
        mock_validate.return_value = (True, "")

        bot = MagicMock()
        bot.strategy_config = {
            "long_budget_percentage": 60.0,
            "short_budget_percentage": 40.0,
        }
        bot.budget_percentage = 50.0
        bot.account_id = 1
        bot.id = 1

        from app.services.bot_validation_service import validate_bidirectional_budget_config
        required_usd, required_btc = await validate_bidirectional_budget_config(
            db_session, bot, quote_currency="USD", is_update=False
        )

        # bot_budget_usd = 10000 * 0.5 = 5000
        # required_usd = 5000 * 0.6 = 3000
        assert required_usd == pytest.approx(3000.0)
        # bot_budget_btc = 0.5 * 0.5 = 0.25
        # required_btc = 0.25 * 0.4 = 0.1
        assert required_btc == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_budget_percentages_not_summing_to_100_raises(self, db_session):
        """Failure: long + short percentages not summing to 100 raises."""
        bot = MagicMock()
        bot.strategy_config = {
            "long_budget_percentage": 60.0,
            "short_budget_percentage": 30.0,  # 60 + 30 = 90, not 100
        }

        from app.services.bot_validation_service import validate_bidirectional_budget_config
        with pytest.raises(ValidationError) as exc_info:
            await validate_bidirectional_budget_config(
                db_session, bot, quote_currency="USD"
            )
        assert exc_info.value.status_code == 400
        assert "sum to 100%" in exc_info.value.message

    @pytest.mark.asyncio
    @patch("app.services.exchange_service.get_exchange_client_for_account")
    async def test_no_exchange_client_raises(self, mock_get_exchange, db_session):
        """Failure: missing exchange client raises ValidationError."""
        mock_get_exchange.return_value = None

        bot = MagicMock()
        bot.strategy_config = {
            "long_budget_percentage": 50.0,
            "short_budget_percentage": 50.0,
        }
        bot.account_id = 1

        from app.services.bot_validation_service import validate_bidirectional_budget_config
        with pytest.raises(ValidationError) as exc_info:
            await validate_bidirectional_budget_config(
                db_session, bot, quote_currency="USD"
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("app.services.exchange_service.get_exchange_client_for_account")
    async def test_zero_budget_percentage_raises(self, mock_get_exchange, db_session):
        """Failure: zero budget_percentage raises ValidationError."""
        mock_exchange = AsyncMock()
        mock_exchange.get_account = AsyncMock(return_value={
            "USD": 5000.0, "USDC": 0.0, "USDT": 0.0, "BTC": 0.5
        })
        mock_exchange.calculate_aggregate_usd_value = AsyncMock(return_value=10000.0)
        mock_exchange.get_btc_usd_price = AsyncMock(return_value=50000.0)
        mock_get_exchange.return_value = mock_exchange

        bot = MagicMock()
        bot.strategy_config = {
            "long_budget_percentage": 50.0,
            "short_budget_percentage": 50.0,
        }
        bot.budget_percentage = 0.0
        bot.account_id = 1

        from app.services.bot_validation_service import validate_bidirectional_budget_config
        with pytest.raises(ValidationError) as exc_info:
            await validate_bidirectional_budget_config(
                db_session, bot, quote_currency="USD"
            )
        assert exc_info.value.status_code == 400
        assert "Budget percentage must be > 0" in exc_info.value.message

    @pytest.mark.asyncio
    @patch("app.services.budget_calculator.validate_bidirectional_budget")
    @patch("app.services.exchange_service.get_exchange_client_for_account")
    async def test_insufficient_funds_raises(self, mock_get_exchange, mock_validate, db_session):
        """Failure: validate_bidirectional_budget returning invalid raises."""
        mock_exchange = AsyncMock()
        mock_exchange.get_account = AsyncMock(return_value={
            "USD": 100.0, "USDC": 0.0, "USDT": 0.0, "BTC": 0.001
        })
        mock_exchange.calculate_aggregate_usd_value = AsyncMock(return_value=1000.0)
        mock_exchange.get_btc_usd_price = AsyncMock(return_value=50000.0)
        mock_get_exchange.return_value = mock_exchange
        mock_validate.return_value = (False, "Insufficient USD for long side.")

        bot = MagicMock()
        bot.strategy_config = {
            "long_budget_percentage": 50.0,
            "short_budget_percentage": 50.0,
        }
        bot.budget_percentage = 100.0
        bot.account_id = 1
        bot.id = 1

        from app.services.bot_validation_service import validate_bidirectional_budget_config
        with pytest.raises(ValidationError) as exc_info:
            await validate_bidirectional_budget_config(
                db_session, bot, quote_currency="USD"
            )
        assert exc_info.value.status_code == 400
        assert "Insufficient USD" in exc_info.value.message
