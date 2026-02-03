"""
Market Season Detection Service (Enhanced with Halving Cycle Awareness)

Determines the current crypto market season based on multiple indicators:
- Halving cycle position (primary anchor - prevents retrograde)
- Fear & Greed Index
- Days since ATH / Drawdown percentage
- Recovery percentage
- BTC Dominance

Historical Halving Cycle Data:
- 2012 Halving: ~400 days to top, ~400 days top to bottom
- 2016 Halving: ~525 days to top, ~365 days top to bottom
- 2020 Halving: ~550 days to top, ~365 days top to bottom
- 2024 Halving: Apr 20, 2024 (expected ~500-550 days to top)

Seasons (in cycle order - NEVER retrograde):
- Spring (Accumulation): ~6-12 months before halving, bottom formation
- Summer (Bull): ~0-18 months after halving, prices rising
- Fall (Distribution): ~15-20 months after halving, peak euphoria
- Winter (Bear): ~18-30 months after halving, prices falling

Anti-Retrograde: Once confirmed in a season, only forward progression allowed.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

import aiohttp

logger = logging.getLogger(__name__)

SeasonType = Literal["accumulation", "bull", "distribution", "bear"]
SeasonName = Literal["Spring", "Summer", "Fall", "Winter"]
SeasonalityMode = Literal["risk_on", "risk_off"]

# Bitcoin halving dates (UTC)
HALVING_DATES = [
    datetime(2012, 11, 28, tzinfo=timezone.utc),  # Block 210,000
    datetime(2016, 7, 9, tzinfo=timezone.utc),    # Block 420,000
    datetime(2020, 5, 11, tzinfo=timezone.utc),   # Block 630,000
    datetime(2024, 4, 20, tzinfo=timezone.utc),   # Block 840,000
    datetime(2028, 4, 17, tzinfo=timezone.utc),   # Block 1,050,000 (estimated)
]

# Historical cycle timing (in days from halving)
# Based on 2016 and 2020 cycles
CYCLE_TIMING = {
    # Days from halving to cycle top (historically 500-550)
    "avg_days_to_top": 525,
    "min_days_to_top": 450,
    "max_days_to_top": 600,

    # Days from top to bottom (historically 350-400)
    "avg_days_top_to_bottom": 375,

    # Season boundaries (days from halving)
    # Spring: -180 to 0 (6 months before halving)
    # Summer: 0 to 400 (0-13 months after)
    # Fall: 400 to 550 (13-18 months after)
    # Winter: 550 to 900 (18-30 months after, then next Spring)
    "spring_start": -180,  # 6 months before halving
    "summer_start": 0,     # Halving day
    "fall_start": 400,     # ~13 months after halving
    "winter_start": 550,   # ~18 months after halving
    "cycle_length": 1260,  # ~4 years (to next halving)
}


@dataclass
class SeasonInfo:
    """Current market season information."""
    season: SeasonType  # Internal identifier
    name: SeasonName  # Display name (Winter, Spring, Summer, Fall)
    subtitle: str  # Technical term (Bear Market, Accumulation Phase, etc.)
    description: str
    progress: float  # 0-100, how far into this season
    confidence: float  # 0-100, confidence in classification
    signals: list[str]  # Key signals that influenced classification
    halving_days: int  # Days since last halving (or negative if before)
    cycle_position: str  # Human-readable cycle position


@dataclass
class SeasonalityStatus:
    """Full seasonality status for API response."""
    season_info: SeasonInfo
    mode: SeasonalityMode  # Current mode based on thresholds
    btc_bots_allowed: bool
    usd_bots_allowed: bool
    threshold_crossed: bool  # True if at/past 80% threshold


def get_halving_info() -> tuple[datetime, int, int]:
    """
    Get information about the current halving cycle.

    Returns: (last_halving_date, days_since_halving, cycle_number)
    """
    now = datetime.now(timezone.utc)

    # Find the most recent halving
    last_halving = HALVING_DATES[0]
    cycle_number = 1

    for i, halving_date in enumerate(HALVING_DATES):
        if halving_date <= now:
            last_halving = halving_date
            cycle_number = i + 1
        else:
            break

    days_since_halving = (now - last_halving).days

    return last_halving, days_since_halving, cycle_number


def get_cycle_season_from_halving(days_since_halving: int) -> tuple[SeasonType, float, str]:
    """
    Determine season primarily from halving cycle position.

    This is the PRIMARY determinant and prevents retrograde.

    Returns: (season, progress_in_season, cycle_position_description)
    """
    timing = CYCLE_TIMING

    # Normalize to handle pre-halving (negative days)
    if days_since_halving < timing["spring_start"]:
        # Very early - previous cycle's winter
        return "bear", 50.0, "Late previous cycle"

    elif days_since_halving < timing["summer_start"]:
        # Spring: 6 months before halving to halving day
        season_length = timing["summer_start"] - timing["spring_start"]
        days_into_season = days_since_halving - timing["spring_start"]
        progress = (days_into_season / season_length) * 100
        return "accumulation", progress, f"{-days_since_halving} days to halving"

    elif days_since_halving < timing["fall_start"]:
        # Summer: Halving to ~13 months after
        season_length = timing["fall_start"] - timing["summer_start"]
        days_into_season = days_since_halving - timing["summer_start"]
        progress = (days_into_season / season_length) * 100
        return "bull", progress, f"{days_since_halving} days post-halving"

    elif days_since_halving < timing["winter_start"]:
        # Fall: ~13-18 months after halving
        season_length = timing["winter_start"] - timing["fall_start"]
        days_into_season = days_since_halving - timing["fall_start"]
        progress = (days_into_season / season_length) * 100
        return "distribution", progress, f"{days_since_halving} days post-halving (distribution)"

    else:
        # Winter: ~18-30 months after halving
        # Winter ends at next Spring (~6 months before next halving)
        winter_end = timing["cycle_length"] + timing["spring_start"]  # ~1080 days
        season_length = winter_end - timing["winter_start"]
        days_into_season = days_since_halving - timing["winter_start"]
        progress = min((days_into_season / season_length) * 100, 100)
        return "bear", progress, f"{days_since_halving} days post-halving (bear market)"


async def fetch_fear_greed() -> Optional[int]:
    """Fetch current Fear & Greed Index value."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.alternative.me/fng/?limit=1",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return int(data["data"][0]["value"])
    except Exception as e:
        logger.warning(f"Failed to fetch Fear & Greed: {e}")
    return None


async def fetch_ath_data() -> Optional[dict]:
    """Fetch ATH data from CoinGecko."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.coingecko.com/api/v3/coins/bitcoin",
                params={"localization": "false", "tickers": "false",
                        "community_data": "false", "developer_data": "false"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    market_data = data.get("market_data", {})
                    current_price = market_data.get("current_price", {}).get("usd", 0)
                    ath = market_data.get("ath", {}).get("usd", 0)
                    ath_date_str = market_data.get("ath_date", {}).get("usd", "")

                    if ath > 0 and current_price > 0:
                        drawdown_pct = ((ath - current_price) / ath) * 100
                        recovery_pct = (current_price / ath) * 100

                        # Calculate days since ATH
                        days_since_ath = 0
                        if ath_date_str:
                            try:
                                ath_date = datetime.fromisoformat(
                                    ath_date_str.replace("Z", "+00:00")
                                )
                                days_since_ath = (
                                    datetime.now(timezone.utc) - ath_date
                                ).days
                            except Exception:
                                pass

                        return {
                            "current_price": current_price,
                            "ath": ath,
                            "drawdown_pct": drawdown_pct,
                            "recovery_pct": recovery_pct,
                            "days_since_ath": days_since_ath
                        }
    except Exception as e:
        logger.warning(f"Failed to fetch ATH data: {e}")
    return None


async def fetch_btc_dominance() -> Optional[float]:
    """Fetch BTC dominance from CoinGecko."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.coingecko.com/api/v3/global",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", {}).get(
                        "market_cap_percentage", {}
                    ).get("btc", 50)
    except Exception as e:
        logger.warning(f"Failed to fetch BTC dominance: {e}")
    return None


def calculate_confidence(
    halving_season: SeasonType,
    fear_greed: Optional[int],
    ath_data: Optional[dict],
    btc_dominance: Optional[float]
) -> tuple[float, list[str]]:
    """
    Calculate confidence score based on how many indicators agree with halving-based season.

    Returns: (confidence_percentage, list_of_confirming_signals)
    """
    signals: list[str] = []
    agreements = 0
    total_checks = 0

    fg = fear_greed if fear_greed is not None else 50
    drawdown = ath_data["drawdown_pct"] if ath_data else 0
    recovery = ath_data["recovery_pct"] if ath_data else 100
    days_since_ath = ath_data["days_since_ath"] if ath_data else 0
    btc_dom = btc_dominance if btc_dominance is not None else 50

    if halving_season == "accumulation":  # Spring
        # Expect: fear/neutral sentiment, significant drawdown, high BTC dominance
        total_checks = 4

        if fg <= 40:
            agreements += 1
            signals.append(f"Fear & Greed at {fg} (fear zone)")
        if drawdown >= 30:
            agreements += 1
            signals.append(f"Drawdown {drawdown:.0f}% from ATH")
        if btc_dom >= 50:
            agreements += 1
            signals.append(f"BTC dominance {btc_dom:.0f}%")
        if days_since_ath >= 300:
            agreements += 1
            signals.append(f"{days_since_ath} days since ATH")

    elif halving_season == "bull":  # Summer
        # Expect: neutral/greed sentiment, recovery underway, moderate dominance
        total_checks = 4

        if fg >= 40:
            agreements += 1
            signals.append(f"Fear & Greed at {fg} (optimism)")
        if recovery >= 50:
            agreements += 1
            signals.append(f"Recovery {recovery:.0f}% of ATH")
        if 40 <= btc_dom <= 60:
            agreements += 1
            signals.append(f"BTC dominance {btc_dom:.0f}% (balanced)")
        if drawdown <= 40:
            agreements += 1
            signals.append(f"Drawdown only {drawdown:.0f}%")

    elif halving_season == "distribution":  # Fall
        # Expect: greed/extreme greed, near ATH, low BTC dominance
        total_checks = 4

        if fg >= 60:
            agreements += 1
            signals.append(f"Fear & Greed at {fg} (greed)")
        if recovery >= 85:
            agreements += 1
            signals.append(f"Near ATH ({recovery:.0f}%)")
        if btc_dom <= 50:
            agreements += 1
            signals.append(f"Low BTC dominance {btc_dom:.0f}%")
        if days_since_ath <= 60:
            agreements += 1
            signals.append(f"Recent ATH ({days_since_ath} days ago)")

    elif halving_season == "bear":  # Winter
        # Expect: fear/extreme fear, significant drawdown, rising BTC dominance
        total_checks = 4

        if fg <= 35:
            agreements += 1
            signals.append(f"Fear & Greed at {fg} (fear)")
        if drawdown >= 40:
            agreements += 1
            signals.append(f"Drawdown {drawdown:.0f}% from ATH")
        if btc_dom >= 55:
            agreements += 1
            signals.append(f"Rising BTC dominance {btc_dom:.0f}%")
        if days_since_ath >= 60:
            agreements += 1
            signals.append(f"{days_since_ath} days since ATH")

    # Calculate confidence (minimum 40% from halving alone, up to 100% with all signals)
    base_confidence = 40  # Halving cycle gives us 40% confidence minimum
    signal_confidence = (agreements / total_checks) * 60 if total_checks > 0 else 0
    confidence = base_confidence + signal_confidence

    return confidence, signals


def determine_season(
    fear_greed: Optional[int],
    ath_data: Optional[dict],
    btc_dominance: Optional[float]
) -> SeasonInfo:
    """
    Determine current market season based on halving cycle (primary) and indicators (secondary).

    The halving cycle position is the PRIMARY determinant and PREVENTS RETROGRADE.
    Other indicators adjust confidence but cannot change the season.
    """
    # Get halving cycle position (PRIMARY - determines season)
    _last_halving, days_since_halving, _cycle_number = get_halving_info()
    halving_season, halving_progress, cycle_position = get_cycle_season_from_halving(
        days_since_halving
    )

    # Calculate confidence based on how many indicators agree
    confidence, signals = calculate_confidence(
        halving_season, fear_greed, ath_data, btc_dominance
    )

    # Add cycle position as first signal
    signals.insert(0, cycle_position)

    # Season metadata
    season_meta = {
        "accumulation": (
            "Spring",
            "Accumulation Phase",
            "Smart money quietly buying. Fear dominates headlines."
        ),
        "bull": (
            "Summer",
            "Bull Market",
            "Prices rising, optimism growing. Momentum building."
        ),
        "distribution": (
            "Fall",
            "Distribution Phase",
            "Peak euphoria. Smart money taking profits."
        ),
        "bear": (
            "Winter",
            "Bear Market",
            "Prices falling, fear spreading. Patience required."
        )
    }

    name, subtitle, description = season_meta[halving_season]

    return SeasonInfo(
        season=halving_season,
        name=name,
        subtitle=subtitle,
        description=description,
        progress=halving_progress,
        confidence=confidence,
        signals=signals[:4],  # Top 4 signals
        halving_days=days_since_halving,
        cycle_position=cycle_position
    )


def get_seasonality_mode(season_info: SeasonInfo) -> tuple[SeasonalityMode, bool]:
    """
    Determine seasonality mode based on season and progress.

    Returns: (mode, threshold_crossed)

    Risk-Off: Summer 80%+ through Winter <80% (late bull/distribution/early bear)
    Risk-On: Winter 80%+ through Summer <80% (late bear/accumulation/early bull)
    """
    season = season_info.season
    progress = season_info.progress

    # Check if we're past the 80% threshold
    threshold_crossed = progress >= 80

    if season == "bull":  # Summer
        # Before 80%: Risk-On, After 80%: transition to Risk-Off
        if progress >= 80:
            return "risk_off", True
        return "risk_on", False

    elif season == "distribution":  # Fall
        # All of Fall is Risk-Off (we're past Summer 80%)
        return "risk_off", True

    elif season == "bear":  # Winter
        # Before 80%: Risk-Off, After 80%: transition to Risk-On
        if progress >= 80:
            return "risk_on", True
        return "risk_off", False

    elif season == "accumulation":  # Spring
        # All of Spring is Risk-On (we're past Winter 80%)
        return "risk_on", True

    return "risk_on", False


async def get_current_season() -> SeasonInfo:
    """Fetch all indicators and determine current season."""
    fear_greed = await fetch_fear_greed()
    ath_data = await fetch_ath_data()
    btc_dominance = await fetch_btc_dominance()

    return determine_season(fear_greed, ath_data, btc_dominance)


async def get_seasonality_status() -> SeasonalityStatus:
    """Get full seasonality status including mode and bot permissions."""
    season_info = await get_current_season()
    mode, threshold_crossed = get_seasonality_mode(season_info)

    # Determine what's allowed based on mode
    btc_bots_allowed = mode == "risk_on"
    usd_bots_allowed = mode == "risk_off"

    return SeasonalityStatus(
        season_info=season_info,
        mode=mode,
        btc_bots_allowed=btc_bots_allowed,
        usd_bots_allowed=usd_bots_allowed,
        threshold_crossed=threshold_crossed
    )
