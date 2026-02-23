"""
Tests for backend/app/services/season_detector.py

Covers:
- get_halving_info: halving cycle lookup
- get_cycle_season_from_halving: season determination from days-since-halving
- calculate_confidence: confidence scoring from multiple indicators
- determine_season: full season determination with metadata
- get_seasonality_mode: risk_on/risk_off mode from season + progress
- fetch_fear_greed / fetch_ath_data / fetch_btc_dominance: external API fetches
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.season_detector import (
    CYCLE_TIMING,
    HALVING_DATES,
    SeasonInfo,
    calculate_confidence,
    determine_season,
    fetch_ath_data,
    fetch_btc_dominance,
    fetch_fear_greed,
    get_cycle_season_from_halving,
    get_halving_info,
    get_seasonality_mode,
    get_seasonality_status,
)


# ---------------------------------------------------------------------------
# get_halving_info
# ---------------------------------------------------------------------------


class TestGetHalvingInfo:
    """Tests for get_halving_info()."""

    def test_returns_most_recent_halving(self):
        """Happy path: returns the most recent halving date."""
        with patch(
            "app.services.season_detector.datetime",
        ) as mock_dt:
            # Set "now" to after the 2024 halving
            mock_dt.now.return_value = datetime(2025, 6, 1, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            last_halving, days_since, cycle_num = get_halving_info()

        assert last_halving == HALVING_DATES[3]  # 2024 halving
        assert cycle_num == 4
        assert days_since > 0

    def test_before_any_halving_uses_first(self):
        """Edge case: date before first known halving should use the first."""
        with patch(
            "app.services.season_detector.datetime",
        ) as mock_dt:
            mock_dt.now.return_value = datetime(2010, 1, 1, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            last_halving, days_since, cycle_num = get_halving_info()

        # First halving is 2012-11-28; we're before it
        assert last_halving == HALVING_DATES[0]
        assert cycle_num == 1
        # days_since should be negative (we haven't reached the first halving)
        # But the implementation always uses HALVING_DATES[0] as default
        # so days_since will be negative
        assert days_since < 0


# ---------------------------------------------------------------------------
# get_cycle_season_from_halving
# ---------------------------------------------------------------------------


class TestGetCycleSeasonFromHalving:
    """Tests for get_cycle_season_from_halving()."""

    def test_spring_phase_before_halving(self):
        """Spring/accumulation: -180 to 0 days from halving."""
        season, progress, desc = get_cycle_season_from_halving(-90)

        assert season == "accumulation"
        assert 0 <= progress <= 100
        assert "days to halving" in desc

    def test_summer_phase_after_halving(self):
        """Summer/bull: 0 to 400 days after halving."""
        season, progress, desc = get_cycle_season_from_halving(200)

        assert season == "bull"
        assert 0 <= progress <= 100
        assert "days post-halving" in desc

    def test_fall_phase_distribution(self):
        """Fall/distribution: 400 to 550 days after halving."""
        season, progress, desc = get_cycle_season_from_halving(475)

        assert season == "distribution"
        assert 0 <= progress <= 100
        assert "distribution" in desc

    def test_winter_phase_bear(self):
        """Winter/bear: 550+ days after halving."""
        season, progress, desc = get_cycle_season_from_halving(700)

        assert season == "bear"
        assert 0 <= progress <= 100
        assert "bear market" in desc

    def test_very_early_previous_cycle(self):
        """Edge case: days < spring_start (-180) is late previous cycle."""
        season, progress, desc = get_cycle_season_from_halving(-300)

        assert season == "bear"
        assert progress == 50.0
        assert "Late previous cycle" in desc

    def test_progress_at_season_boundary(self):
        """Edge case: exactly at fall_start boundary."""
        season, progress, desc = get_cycle_season_from_halving(
            CYCLE_TIMING["fall_start"]
        )

        assert season == "distribution"
        assert progress == pytest.approx(0.0)

    def test_progress_maxes_at_100(self):
        """Edge case: very late winter progress caps at 100."""
        season, progress, desc = get_cycle_season_from_halving(2000)

        assert season == "bear"
        assert progress <= 100


# ---------------------------------------------------------------------------
# calculate_confidence
# ---------------------------------------------------------------------------


class TestCalculateConfidence:
    """Tests for calculate_confidence()."""

    def test_all_signals_agree_with_bull(self):
        """Happy path: all indicators confirm bull season -> high confidence."""
        confidence, signals = calculate_confidence(
            halving_season="bull",
            fear_greed=65,
            ath_data={"drawdown_pct": 10, "recovery_pct": 90, "days_since_ath": 30},
            btc_dominance=50.0,
        )

        # Base 40% + up to 60% from signals
        assert confidence >= 70
        assert len(signals) > 0

    def test_no_signals_agree_gives_base_confidence(self):
        """Edge case: no indicators match -> minimum confidence (40%)."""
        confidence, signals = calculate_confidence(
            halving_season="accumulation",
            fear_greed=80,  # Not fearful (disagrees)
            ath_data={"drawdown_pct": 5, "recovery_pct": 95, "days_since_ath": 10},
            btc_dominance=30.0,  # Not high dominance (disagrees)
        )

        assert confidence == pytest.approx(40.0)
        assert signals == []

    def test_none_values_use_defaults(self):
        """Edge case: None values for indicators use defaults (50)."""
        confidence, signals = calculate_confidence(
            halving_season="bear",
            fear_greed=None,
            ath_data=None,
            btc_dominance=None,
        )

        # Should not crash and should return base confidence
        assert confidence >= 40.0

    def test_distribution_all_agree(self):
        """Happy path: distribution season with all confirming signals."""
        confidence, signals = calculate_confidence(
            halving_season="distribution",
            fear_greed=80,  # Extreme greed
            ath_data={"drawdown_pct": 5, "recovery_pct": 95, "days_since_ath": 10},
            btc_dominance=40.0,  # Low dominance
        )

        assert confidence >= 85
        assert len(signals) >= 3

    def test_bear_all_agree(self):
        """Happy path: bear season with all confirming signals."""
        confidence, signals = calculate_confidence(
            halving_season="bear",
            fear_greed=15,  # Extreme fear
            ath_data={"drawdown_pct": 60, "recovery_pct": 40, "days_since_ath": 200},
            btc_dominance=60.0,  # Rising dominance
        )

        assert confidence == pytest.approx(100.0)
        assert len(signals) == 4


# ---------------------------------------------------------------------------
# determine_season
# ---------------------------------------------------------------------------


class TestDetermineSeason:
    """Tests for determine_season()."""

    def test_returns_season_info_dataclass(self):
        """Happy path: returns properly populated SeasonInfo."""
        result = determine_season(
            fear_greed=50,
            ath_data={"drawdown_pct": 10, "recovery_pct": 90, "days_since_ath": 30},
            btc_dominance=50.0,
        )

        assert isinstance(result, SeasonInfo)
        assert result.season in ("accumulation", "bull", "distribution", "bear")
        assert result.name in ("Spring", "Summer", "Fall", "Winter")
        assert 0 <= result.confidence <= 100
        assert len(result.signals) <= 4

    def test_with_all_none_indicators(self):
        """Edge case: all None indicators still returns valid result."""
        result = determine_season(
            fear_greed=None,
            ath_data=None,
            btc_dominance=None,
        )

        assert isinstance(result, SeasonInfo)
        assert result.confidence >= 40

    def test_cycle_position_is_first_signal(self):
        """The cycle position description is always the first signal."""
        result = determine_season(
            fear_greed=50,
            ath_data=None,
            btc_dominance=None,
        )

        assert len(result.signals) >= 1
        # First signal is cycle position (e.g., "123 days post-halving")
        assert "days" in result.signals[0] or "cycle" in result.signals[0].lower()


# ---------------------------------------------------------------------------
# get_seasonality_mode
# ---------------------------------------------------------------------------


class TestGetSeasonalityMode:
    """Tests for get_seasonality_mode()."""

    def test_bull_below_80_is_risk_on(self):
        """Summer below 80% progress -> risk_on."""
        info = SeasonInfo(
            season="bull", name="Summer", subtitle="Bull Market",
            description="", progress=50.0, confidence=80.0,
            signals=[], halving_days=200, cycle_position="",
        )

        mode, threshold = get_seasonality_mode(info)

        assert mode == "risk_on"
        assert threshold is False

    def test_bull_at_80_is_risk_off(self):
        """Summer at 80% progress -> transition to risk_off."""
        info = SeasonInfo(
            season="bull", name="Summer", subtitle="Bull Market",
            description="", progress=80.0, confidence=80.0,
            signals=[], halving_days=350, cycle_position="",
        )

        mode, threshold = get_seasonality_mode(info)

        assert mode == "risk_off"
        assert threshold is True

    def test_distribution_always_risk_off(self):
        """Fall/distribution is always risk_off."""
        info = SeasonInfo(
            season="distribution", name="Fall", subtitle="Distribution Phase",
            description="", progress=30.0, confidence=70.0,
            signals=[], halving_days=430, cycle_position="",
        )

        mode, threshold = get_seasonality_mode(info)

        assert mode == "risk_off"
        assert threshold is True

    def test_bear_below_80_is_risk_off(self):
        """Winter below 80% progress -> risk_off."""
        info = SeasonInfo(
            season="bear", name="Winter", subtitle="Bear Market",
            description="", progress=40.0, confidence=70.0,
            signals=[], halving_days=700, cycle_position="",
        )

        mode, threshold = get_seasonality_mode(info)

        assert mode == "risk_off"
        assert threshold is False

    def test_bear_at_80_transitions_to_risk_on(self):
        """Winter at 80% progress -> transition to risk_on."""
        info = SeasonInfo(
            season="bear", name="Winter", subtitle="Bear Market",
            description="", progress=85.0, confidence=70.0,
            signals=[], halving_days=900, cycle_position="",
        )

        mode, threshold = get_seasonality_mode(info)

        assert mode == "risk_on"
        assert threshold is True

    def test_accumulation_always_risk_on(self):
        """Spring/accumulation is always risk_on."""
        info = SeasonInfo(
            season="accumulation", name="Spring", subtitle="Accumulation Phase",
            description="", progress=50.0, confidence=80.0,
            signals=[], halving_days=-90, cycle_position="",
        )

        mode, threshold = get_seasonality_mode(info)

        assert mode == "risk_on"
        assert threshold is True


# ---------------------------------------------------------------------------
# fetch_fear_greed (external API)
# ---------------------------------------------------------------------------


def _make_aiohttp_response(status, json_data):
    """Helper to build a mock aiohttp response as an async context manager."""
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.json = AsyncMock(return_value=json_data)
    mock_response.text = AsyncMock(return_value="")
    return mock_response


def _make_aiohttp_session(response_or_error):
    """Helper to build a mock aiohttp.ClientSession that returns response from .get()."""
    mock_session = MagicMock()

    if isinstance(response_or_error, Exception):
        mock_session.get.side_effect = response_or_error
    else:
        # Make .get() return an async context manager
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=response_or_error)
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_session.get.return_value = cm

    # Make ClientSession itself an async context manager
    outer_cm = MagicMock()
    outer_cm.__aenter__ = AsyncMock(return_value=mock_session)
    outer_cm.__aexit__ = AsyncMock(return_value=False)
    return outer_cm


class TestFetchFearGreed:
    """Tests for fetch_fear_greed()."""

    @pytest.mark.asyncio
    async def test_returns_value_on_success(self):
        """Happy path: returns Fear & Greed index value."""
        response = _make_aiohttp_response(200, {"data": [{"value": "72"}]})
        session = _make_aiohttp_session(response)

        with patch("app.services.season_detector.aiohttp.ClientSession", return_value=session):
            result = await fetch_fear_greed()

        assert result == 72

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self):
        """Failure: returns None when API request fails."""
        session = _make_aiohttp_session(Exception("Connection timeout"))

        with patch("app.services.season_detector.aiohttp.ClientSession", return_value=session):
            result = await fetch_fear_greed()

        assert result is None


# ---------------------------------------------------------------------------
# fetch_ath_data (external API)
# ---------------------------------------------------------------------------


class TestFetchAthData:
    """Tests for fetch_ath_data()."""

    @pytest.mark.asyncio
    async def test_returns_dict_on_success(self):
        """Happy path: returns ATH data dict."""
        response = _make_aiohttp_response(200, {
            "market_data": {
                "current_price": {"usd": 95000},
                "ath": {"usd": 100000},
                "ath_date": {"usd": "2025-01-01T00:00:00Z"},
            }
        })
        session = _make_aiohttp_session(response)

        with patch("app.services.season_detector.aiohttp.ClientSession", return_value=session):
            result = await fetch_ath_data()

        assert result is not None
        assert result["current_price"] == 95000
        assert result["ath"] == 100000
        assert result["drawdown_pct"] == pytest.approx(5.0)
        assert result["recovery_pct"] == pytest.approx(95.0)

    @pytest.mark.asyncio
    async def test_returns_none_on_api_error(self):
        """Failure: returns None on API error."""
        session = _make_aiohttp_session(Exception("API down"))

        with patch("app.services.season_detector.aiohttp.ClientSession", return_value=session):
            result = await fetch_ath_data()

        assert result is None


# ---------------------------------------------------------------------------
# fetch_btc_dominance (external API)
# ---------------------------------------------------------------------------


class TestFetchBtcDominance:
    """Tests for fetch_btc_dominance()."""

    @pytest.mark.asyncio
    async def test_returns_float_on_success(self):
        """Happy path: returns BTC dominance as float."""
        response = _make_aiohttp_response(200, {
            "data": {"market_cap_percentage": {"btc": 58.5}}
        })
        session = _make_aiohttp_session(response)

        with patch("app.services.season_detector.aiohttp.ClientSession", return_value=session):
            result = await fetch_btc_dominance()

        assert result == pytest.approx(58.5)

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self):
        """Failure: returns None on API failure."""
        session = _make_aiohttp_session(Exception("timeout"))

        with patch("app.services.season_detector.aiohttp.ClientSession", return_value=session):
            result = await fetch_btc_dominance()

        assert result is None


# ---------------------------------------------------------------------------
# get_seasonality_status (integration)
# ---------------------------------------------------------------------------


class TestGetSeasonalityStatus:
    """Tests for get_seasonality_status()."""

    @pytest.mark.asyncio
    async def test_returns_full_status(self):
        """Happy path: returns full SeasonalityStatus with all fields."""
        with patch("app.services.season_detector.fetch_fear_greed", new_callable=AsyncMock, return_value=50), \
             patch("app.services.season_detector.fetch_ath_data", new_callable=AsyncMock, return_value=None), \
             patch("app.services.season_detector.fetch_btc_dominance", new_callable=AsyncMock, return_value=50.0):

            result = await get_seasonality_status()

        assert hasattr(result, "season_info")
        assert hasattr(result, "mode")
        assert result.mode in ("risk_on", "risk_off")
        assert isinstance(result.btc_bots_allowed, bool)
        assert isinstance(result.usd_bots_allowed, bool)
        # risk_on allows BTC bots, risk_off allows USD bots
        assert result.btc_bots_allowed != result.usd_bots_allowed
