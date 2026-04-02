"""Tests for seasonality_service — business logic extracted from seasonality_router."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.seasonality_service import auto_manage_bots, build_seasonality_response


class TestAutoManageBots:
    """Tests for auto_manage_bots business logic."""

    def _make_bot(self, quote="USD", strategy="dca", is_active=True, bot_id=1, name="TestBot"):
        bot = MagicMock()
        bot.id = bot_id
        bot.name = name
        bot.is_active = is_active
        bot.strategy_type = strategy
        bot.get_quote_currency.return_value = quote
        bot.updated_at = None
        return bot

    def _make_status(self, mode="risk_off"):
        status = MagicMock()
        status.mode = mode
        status.btc_bots_allowed = mode == "risk_on"
        status.usd_bots_allowed = mode == "risk_off"
        return status

    @pytest.mark.asyncio
    async def test_risk_off_disables_btc_bots(self, db_session):
        """Risk-off mode should disable BTC bots but not USD bots."""
        btc_bot = self._make_bot(quote="BTC", bot_id=1, name="BTC Bot")
        usd_bot = self._make_bot(quote="USD", bot_id=2, name="USD Bot")
        status = self._make_status(mode="risk_off")

        result = await auto_manage_bots(
            bots=[btc_bot, usd_bot],
            status=status,
        )

        assert result["disabled_btc"] == 1
        assert result["disabled_usd"] == 0
        assert btc_bot.is_active is False
        assert usd_bot.is_active is True

    @pytest.mark.asyncio
    async def test_risk_on_disables_usd_bots(self):
        """Risk-on mode should disable USD bots but not BTC bots."""
        btc_bot = self._make_bot(quote="BTC", bot_id=1)
        usd_bot = self._make_bot(quote="USD", bot_id=2)
        status = self._make_status(mode="risk_on")

        result = await auto_manage_bots(
            bots=[btc_bot, usd_bot],
            status=status,
        )

        assert result["disabled_btc"] == 0
        assert result["disabled_usd"] == 1
        assert btc_bot.is_active is True
        assert usd_bot.is_active is False

    @pytest.mark.asyncio
    async def test_grid_bots_exempt_from_seasonality(self):
        """Grid trading bots should never be disabled by seasonality."""
        grid_bot = self._make_bot(quote="BTC", strategy="grid_trading", bot_id=1)
        status = self._make_status(mode="risk_off")

        result = await auto_manage_bots(bots=[grid_bot], status=status)

        assert result["disabled_btc"] == 0
        assert grid_bot.is_active is True

    @pytest.mark.asyncio
    async def test_empty_bot_list_returns_zeros(self):
        """No bots = no changes."""
        status = self._make_status(mode="risk_off")

        result = await auto_manage_bots(bots=[], status=status)

        assert result["disabled_btc"] == 0
        assert result["disabled_usd"] == 0


class TestBuildSeasonalityResponse:
    """Tests for building the seasonality response dict."""

    def _make_season_info(self):
        info = MagicMock()
        info.season = "accumulation"
        info.name = "Spring"
        info.subtitle = "Accumulation Phase"
        info.description = "Market is accumulating"
        info.progress = 0.45
        info.confidence = 0.8
        info.signals = ["signal1", "signal2"]
        info.halving_days = 200
        info.cycle_position = "Early cycle"
        return info

    def _make_status(self, mode="risk_on"):
        status = MagicMock()
        status.season_info = self._make_season_info()
        status.mode = mode
        status.btc_bots_allowed = True
        status.usd_bots_allowed = False
        status.threshold_crossed = False
        return status

    def test_disabled_seasonality_allows_all_bots(self):
        """When seasonality is disabled, both bot types should be allowed."""
        status = self._make_status(mode="risk_off")
        status.btc_bots_allowed = False

        result = build_seasonality_response(
            status=status,
            enabled=False,
            last_transition=None,
        )

        assert result["btc_bots_allowed"] is True
        assert result["usd_bots_allowed"] is True
        assert result["enabled"] is False

    def test_enabled_seasonality_respects_mode(self):
        """When enabled, bot allowed flags come from status."""
        status = self._make_status(mode="risk_on")
        status.btc_bots_allowed = True
        status.usd_bots_allowed = False

        result = build_seasonality_response(
            status=status,
            enabled=True,
            last_transition="2026-01-15T00:00:00",
        )

        assert result["btc_bots_allowed"] is True
        assert result["usd_bots_allowed"] is False
        assert result["enabled"] is True
        assert result["last_transition"] == "2026-01-15T00:00:00"

    def test_response_includes_season_fields(self):
        """Response includes all season info fields."""
        status = self._make_status()

        result = build_seasonality_response(
            status=status, enabled=True, last_transition=None,
        )

        assert result["season"] == "accumulation"
        assert result["season_name"] == "Spring"
        assert result["progress"] == 0.45
        assert result["confidence"] == 0.8
        assert result["halving_days"] == 200
