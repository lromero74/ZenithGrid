"""
Tests for backend/app/routers/seasonality_router.py

Covers:
- GET /api/seasonality — get current seasonality status
- POST /api/seasonality — toggle seasonality on/off (superuser)
- GET /api/seasonality/check-bot — check if bot type is allowed
- auto_manage_bots() helper
- get_setting() / set_setting() helpers
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Bot, Settings, User


# ---------------------------------------------------------------------------
# Mock SeasonalityStatus fixtures
# ---------------------------------------------------------------------------


def _make_season_info(**overrides):
    """Create a mock SeasonInfo object."""
    defaults = dict(
        season="bull",
        name="Summer",
        subtitle="Bull Run",
        description="BTC price rising after halving",
        progress=50.0,
        confidence=80.0,
        signals=["Days since halving: ~500", "Price above 200-day MA"],
        halving_days=500,
        cycle_position="Mid-cycle",
    )
    defaults.update(overrides)
    info = MagicMock()
    for k, v in defaults.items():
        setattr(info, k, v)
    return info


def _make_seasonality_status(mode="risk_on", btc_allowed=True, usd_allowed=False,
                             threshold=False, **season_overrides):
    """Create a mock SeasonalityStatus object."""
    status = MagicMock()
    status.season_info = _make_season_info(**season_overrides)
    status.mode = mode
    status.btc_bots_allowed = btc_allowed
    status.usd_bots_allowed = usd_allowed
    status.threshold_crossed = threshold
    return status


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def seasonality_user(db_session):
    """Create a superuser for seasonality tests."""
    user = User(
        email="season_test@example.com",
        hashed_password="hashed",
        display_name="Admin",
        is_active=True,
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


# =============================================================================
# get_setting / set_setting helpers
# =============================================================================


class TestGetSetting:
    """Tests for get_setting() helper."""

    @pytest.mark.asyncio
    async def test_get_existing_setting(self, db_session):
        """Happy path: returns value for existing key."""
        from app.routers.seasonality_router import get_setting

        s = Settings(key="test_key", value="test_value", value_type="string")
        db_session.add(s)
        await db_session.flush()

        result = await get_setting(db_session, "test_key")
        assert result == "test_value"

    @pytest.mark.asyncio
    async def test_get_nonexistent_setting(self, db_session):
        """Edge case: returns None for missing key."""
        from app.routers.seasonality_router import get_setting

        result = await get_setting(db_session, "nonexistent_key")
        assert result is None


class TestSetSetting:
    """Tests for set_setting() helper."""

    @pytest.mark.asyncio
    async def test_set_creates_new_setting(self, db_session):
        """Happy path: creates a new setting if key doesn't exist."""
        from app.routers.seasonality_router import set_setting, get_setting

        await set_setting(db_session, "new_key", "new_value", "string", "A new setting")
        result = await get_setting(db_session, "new_key")
        assert result == "new_value"

    @pytest.mark.asyncio
    async def test_set_updates_existing_setting(self, db_session):
        """Edge case: updates value if key already exists."""
        from app.routers.seasonality_router import set_setting, get_setting

        await set_setting(db_session, "update_key", "old", "string")
        await set_setting(db_session, "update_key", "new", "string")
        result = await get_setting(db_session, "update_key")
        assert result == "new"


# =============================================================================
# GET /api/seasonality
# =============================================================================


class TestGetSeasonality:
    """Tests for GET /api/seasonality"""

    @pytest.mark.asyncio
    @patch("app.routers.seasonality_router.get_seasonality_status", new_callable=AsyncMock)
    async def test_returns_status_when_disabled(self, mock_status, db_session, seasonality_user):
        """Happy path: returns seasonality status with enabled=False."""
        from app.routers.seasonality_router import get_seasonality

        mock_status.return_value = _make_seasonality_status(
            mode="risk_on", btc_allowed=True, usd_allowed=False,
        )

        result = await get_seasonality(db=db_session, current_user=seasonality_user)
        assert result.enabled is False
        assert result.season == "bull"
        assert result.mode == "risk_on"
        # When disabled, both bot types should be allowed
        assert result.btc_bots_allowed is True
        assert result.usd_bots_allowed is True

    @pytest.mark.asyncio
    @patch("app.routers.seasonality_router.get_seasonality_status", new_callable=AsyncMock)
    async def test_returns_status_when_enabled(self, mock_status, db_session, seasonality_user):
        """Happy path: returns seasonality status with enabled=True."""
        from app.routers.seasonality_router import get_seasonality, set_setting

        mock_status.return_value = _make_seasonality_status(
            mode="risk_off", btc_allowed=False, usd_allowed=True,
        )

        await set_setting(db_session, "seasonality_enabled", "true")
        result = await get_seasonality(db=db_session, current_user=seasonality_user)
        assert result.enabled is True
        # When enabled, respects the status
        assert result.btc_bots_allowed is False
        assert result.usd_bots_allowed is True

    @pytest.mark.asyncio
    @patch("app.routers.seasonality_router.get_seasonality_status", new_callable=AsyncMock)
    async def test_includes_last_transition(self, mock_status, db_session, seasonality_user):
        """Edge case: last_transition from settings is included."""
        from app.routers.seasonality_router import get_seasonality, set_setting

        mock_status.return_value = _make_seasonality_status()
        ts = "2026-01-15T12:00:00"
        await set_setting(db_session, "seasonality_last_transition", ts)

        result = await get_seasonality(db=db_session, current_user=seasonality_user)
        assert result.last_transition == ts


# =============================================================================
# POST /api/seasonality (toggle)
# =============================================================================


class TestToggleSeasonality:
    """Tests for POST /api/seasonality"""

    @pytest.mark.asyncio
    @patch("app.routers.seasonality_router.get_seasonality_status", new_callable=AsyncMock)
    async def test_enable_seasonality(self, mock_status, db_session, seasonality_user):
        """Happy path: enabling sets mode and auto-manages bots."""
        from app.routers.seasonality_router import (
            toggle_seasonality, SeasonalityToggleRequest, get_setting,
        )

        mock_status.return_value = _make_seasonality_status(
            mode="risk_on", btc_allowed=True, usd_allowed=False,
        )

        request = SeasonalityToggleRequest(enabled=True)
        result = await toggle_seasonality(
            request=request, db=db_session, current_user=seasonality_user,
        )
        assert result.enabled is True

        # Check that settings were persisted
        enabled = await get_setting(db_session, "seasonality_enabled")
        assert enabled == "true"
        mode = await get_setting(db_session, "seasonality_mode")
        assert mode == "risk_on"

    @pytest.mark.asyncio
    @patch("app.routers.seasonality_router.get_seasonality_status", new_callable=AsyncMock)
    async def test_disable_seasonality(self, mock_status, db_session, seasonality_user):
        """Happy path: disabling clears restrictions."""
        from app.routers.seasonality_router import (
            toggle_seasonality, SeasonalityToggleRequest, set_setting,
        )

        mock_status.return_value = _make_seasonality_status()

        # First enable
        await set_setting(db_session, "seasonality_enabled", "true")

        # Now disable
        request = SeasonalityToggleRequest(enabled=False)
        result = await toggle_seasonality(
            request=request, db=db_session, current_user=seasonality_user,
        )
        assert result.enabled is False
        assert result.btc_bots_allowed is True
        assert result.usd_bots_allowed is True


# =============================================================================
# auto_manage_bots
# =============================================================================


class TestAutoManageBots:
    """Tests for auto_manage_bots() helper."""

    @pytest.mark.asyncio
    async def test_risk_off_disables_btc_bots(self, db_session, seasonality_user):
        """Happy path: risk_off disables BTC bots."""
        from app.routers.seasonality_router import auto_manage_bots

        # Create a BTC bot
        bot = Bot(
            user_id=seasonality_user.id,
            name="BTC DCA",
            strategy_type="macd_dca",
            product_id="ETH-BTC",
            is_active=True,
        )
        db_session.add(bot)
        await db_session.flush()

        status = _make_seasonality_status(mode="risk_off")

        # Mock get_quote_currency to return "BTC"
        with patch.object(Bot, "get_quote_currency", return_value="BTC"):
            counts = await auto_manage_bots(db_session, status)

        assert counts["disabled_btc"] == 1
        assert counts["disabled_usd"] == 0

    @pytest.mark.asyncio
    async def test_risk_on_disables_usd_bots(self, db_session, seasonality_user):
        """Happy path: risk_on disables USD bots."""
        from app.routers.seasonality_router import auto_manage_bots

        bot = Bot(
            user_id=seasonality_user.id,
            name="USD DCA",
            strategy_type="macd_dca",
            product_id="ETH-USD",
            is_active=True,
        )
        db_session.add(bot)
        await db_session.flush()

        status = _make_seasonality_status(mode="risk_on")

        with patch.object(Bot, "get_quote_currency", return_value="USD"):
            counts = await auto_manage_bots(db_session, status)

        assert counts["disabled_usd"] == 1
        assert counts["disabled_btc"] == 0

    @pytest.mark.asyncio
    async def test_grid_bots_exempt(self, db_session, seasonality_user):
        """Edge case: grid trading bots are exempt from seasonality."""
        from app.routers.seasonality_router import auto_manage_bots

        bot = Bot(
            user_id=seasonality_user.id,
            name="Grid Bot",
            strategy_type="grid_trading",
            product_id="ETH-BTC",
            is_active=True,
        )
        db_session.add(bot)
        await db_session.flush()

        status = _make_seasonality_status(mode="risk_off")
        counts = await auto_manage_bots(db_session, status)
        assert counts["disabled_btc"] == 0
        assert counts["disabled_usd"] == 0

    @pytest.mark.asyncio
    async def test_no_active_bots(self, db_session, seasonality_user):
        """Edge case: no active bots, nothing to disable."""
        from app.routers.seasonality_router import auto_manage_bots

        status = _make_seasonality_status(mode="risk_off")
        counts = await auto_manage_bots(db_session, status)
        assert counts["disabled_btc"] == 0
        assert counts["disabled_usd"] == 0

    @pytest.mark.asyncio
    async def test_scoped_to_user(self, db_session, seasonality_user):
        """Edge case: user_id scoping limits which bots are managed."""
        from app.routers.seasonality_router import auto_manage_bots

        # Create bots for two users
        other_user = User(
            email="other_season@example.com",
            hashed_password="hashed",
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.flush()

        bot1 = Bot(
            user_id=seasonality_user.id,
            name="My BTC",
            strategy_type="macd_dca",
            product_id="ETH-BTC",
            is_active=True,
        )
        bot2 = Bot(
            user_id=other_user.id,
            name="Other BTC",
            strategy_type="macd_dca",
            product_id="ETH-BTC",
            is_active=True,
        )
        db_session.add_all([bot1, bot2])
        await db_session.flush()

        status = _make_seasonality_status(mode="risk_off")

        with patch.object(Bot, "get_quote_currency", return_value="BTC"):
            counts = await auto_manage_bots(db_session, status, user_id=seasonality_user.id)

        assert counts["disabled_btc"] == 1  # Only our user's bot


# =============================================================================
# GET /api/seasonality/check-bot
# =============================================================================


class TestCheckBotAllowed:
    """Tests for GET /api/seasonality/check-bot"""

    @pytest.mark.asyncio
    async def test_check_allowed_when_disabled(self, db_session, seasonality_user):
        """Happy path: all bots allowed when seasonality is disabled."""
        from app.routers.seasonality_router import check_bot_allowed

        result = await check_bot_allowed(
            bot_type="btc", db=db_session, current_user=seasonality_user,
        )
        assert result["allowed"] is True
        assert result["reason"] is None

    @pytest.mark.asyncio
    @patch("app.routers.seasonality_router.get_seasonality_status", new_callable=AsyncMock)
    async def test_btc_blocked_in_risk_off(self, mock_status, db_session, seasonality_user):
        """Failure: BTC bots blocked during risk-off mode."""
        from app.routers.seasonality_router import check_bot_allowed, set_setting

        mock_status.return_value = _make_seasonality_status(
            mode="risk_off", btc_allowed=False, usd_allowed=True,
        )

        await set_setting(db_session, "seasonality_enabled", "true")
        result = await check_bot_allowed(
            bot_type="btc", db=db_session, current_user=seasonality_user,
        )
        assert result["allowed"] is False
        assert "BTC bots are blocked" in result["reason"]

    @pytest.mark.asyncio
    @patch("app.routers.seasonality_router.get_seasonality_status", new_callable=AsyncMock)
    async def test_usd_blocked_in_risk_on(self, mock_status, db_session, seasonality_user):
        """Failure: USD bots blocked during risk-on mode."""
        from app.routers.seasonality_router import check_bot_allowed, set_setting

        mock_status.return_value = _make_seasonality_status(
            mode="risk_on", btc_allowed=True, usd_allowed=False,
        )

        await set_setting(db_session, "seasonality_enabled", "true")
        result = await check_bot_allowed(
            bot_type="usd", db=db_session, current_user=seasonality_user,
        )
        assert result["allowed"] is False
        assert "USD bots are blocked" in result["reason"]

    @pytest.mark.asyncio
    @patch("app.routers.seasonality_router.get_seasonality_status", new_callable=AsyncMock)
    async def test_btc_allowed_in_risk_on(self, mock_status, db_session, seasonality_user):
        """Happy path: BTC bots allowed during risk-on mode."""
        from app.routers.seasonality_router import check_bot_allowed, set_setting

        mock_status.return_value = _make_seasonality_status(
            mode="risk_on", btc_allowed=True, usd_allowed=False,
        )

        await set_setting(db_session, "seasonality_enabled", "true")
        result = await check_bot_allowed(
            bot_type="btc", db=db_session, current_user=seasonality_user,
        )
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_unknown_bot_type_allowed(self, db_session, seasonality_user):
        """Edge case: unknown bot type is allowed by default."""
        from app.routers.seasonality_router import check_bot_allowed, set_setting

        await set_setting(db_session, "seasonality_enabled", "true")

        with patch("app.routers.seasonality_router.get_seasonality_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = _make_seasonality_status()
            result = await check_bot_allowed(
                bot_type="eth", db=db_session, current_user=seasonality_user,
            )
        assert result["allowed"] is True
