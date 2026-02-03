"""
Market Season Detection Service

Determines the current crypto market season based on multiple indicators:
- Fear & Greed Index
- Days since ATH / Drawdown percentage
- Recovery percentage
- Altseason index
- BTC Dominance

Seasons:
- Winter (Bear): Prices falling, fear spreading
- Spring (Accumulation): Smart money buying at lows
- Summer (Bull): Prices rising, optimism growing
- Fall (Distribution): Peak euphoria, profit taking
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

import aiohttp

logger = logging.getLogger(__name__)

SeasonType = Literal["accumulation", "bull", "distribution", "bear"]
SeasonName = Literal["Spring", "Summer", "Fall", "Winter"]
SeasonalityMode = Literal["risk_on", "risk_off"]


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


@dataclass
class SeasonalityStatus:
    """Full seasonality status for API response."""
    season_info: SeasonInfo
    mode: SeasonalityMode  # Current mode based on thresholds
    btc_bots_allowed: bool
    usd_bots_allowed: bool
    threshold_crossed: bool  # True if at/past 80% threshold


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
                                ath_date = datetime.fromisoformat(ath_date_str.replace("Z", "+00:00"))
                                days_since_ath = (datetime.now(ath_date.tzinfo) - ath_date).days
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
                    return data.get("data", {}).get("market_cap_percentage", {}).get("btc", 50)
    except Exception as e:
        logger.warning(f"Failed to fetch BTC dominance: {e}")
    return None


async def fetch_altseason_index() -> Optional[int]:
    """Calculate altseason index from top coins performance."""
    # Simplified: return None to use default, full implementation would
    # compare altcoin vs BTC performance over 30/90 days
    return None


def determine_season(
    fear_greed: Optional[int],
    ath_data: Optional[dict],
    altseason_idx: Optional[int],
    btc_dominance: Optional[float]
) -> SeasonInfo:
    """
    Determine current market season based on indicators.

    KEY DISTINCTION: Bear vs Accumulation
    - Bear: Recent drawdown (<180 days since ATH), still falling
    - Accumulation: Extended time at lows (365+ days), stabilizing
    """
    signals: list[str] = []

    # Default values if data not available
    fg = fear_greed if fear_greed is not None else 50
    drawdown = ath_data["drawdown_pct"] if ath_data else 0
    days_since_ath = ath_data["days_since_ath"] if ath_data else 0
    recovery = ath_data["recovery_pct"] if ath_data else 100
    alt_idx = altseason_idx if altseason_idx is not None else 50
    btc_dom = btc_dominance if btc_dominance is not None else 50

    # Score each season
    accumulation_score = 0
    bull_score = 0
    distribution_score = 0
    bear_score = 0

    # Time-based bear vs accumulation distinction
    is_recent_drop = days_since_ath < 180 and drawdown > 15
    is_extended_bear = days_since_ath >= 365 and drawdown > 30

    # Fear & Greed signals
    if fg <= 20:
        if is_recent_drop:
            bear_score += 35
            signals.append("Extreme fear (capitulation)")
        elif is_extended_bear:
            accumulation_score += 25
            bear_score += 10
            signals.append("Extreme fear (potential bottom)")
        else:
            bear_score += 20
            accumulation_score += 15
            signals.append("Extreme fear")
    elif fg <= 35:
        if is_recent_drop:
            bear_score += 25
            signals.append("Fear amid recent decline")
        else:
            bear_score += 15
            accumulation_score += 10
            signals.append("Fear in market")
    elif fg >= 80:
        distribution_score += 35
        signals.append("Extreme greed (caution)")
    elif fg >= 65:
        distribution_score += 20
        bull_score += 15
        signals.append("Greed rising")
    elif fg >= 50:
        bull_score += 20
        signals.append("Optimism building")
    else:
        bear_score += 10
        bull_score += 5

    # Drawdown signals
    if drawdown <= 5:
        distribution_score += 30
        signals.append("At/near all-time high")
    elif drawdown <= 10:
        bull_score += 20
        distribution_score += 15
        signals.append("Close to ATH")
    elif drawdown <= 20:
        bull_score += 15
        signals.append("Healthy pullback")
    elif drawdown <= 35:
        if days_since_ath < 90:
            bear_score += 30
            signals.append("Recent correction")
        elif days_since_ath < 180:
            bear_score += 20
            signals.append("Correction deepening")
        else:
            bear_score += 10
            accumulation_score += 10
    elif drawdown <= 50:
        if days_since_ath < 180:
            bear_score += 35
            signals.append("Bear market decline")
        elif days_since_ath < 365:
            bear_score += 25
            accumulation_score += 10
            signals.append("Extended bear market")
        else:
            accumulation_score += 25
            bear_score += 10
            signals.append("Prolonged drawdown (accumulation zone)")
    else:
        if days_since_ath < 365:
            bear_score += 30
            signals.append("Deep bear market")
        else:
            accumulation_score += 35
            signals.append("Deep drawdown (accumulation zone)")

    # Days since ATH signals
    if days_since_ath <= 30:
        if drawdown <= 10:
            distribution_score += 20
            signals.append("Recent ATH")
        else:
            bear_score += 15
            signals.append("Fresh decline from ATH")
    elif days_since_ath <= 90 and drawdown > 20:
        bear_score += 20
        signals.append("Early bear market")
    elif days_since_ath >= 500 and drawdown > 40:
        accumulation_score += 25
        signals.append("Extended cycle low")

    # Recovery signals
    if recovery >= 95:
        distribution_score += 15
        bull_score += 10
    elif recovery >= 80:
        bull_score += 25
        signals.append("Strong recovery")
    elif recovery >= 60:
        bull_score += 15
        signals.append("Recovery underway")
    elif recovery <= 40:
        bear_score += 15

    # Altseason signals
    if alt_idx >= 75:
        distribution_score += 15
        bull_score += 10
        signals.append("Altcoin season (late cycle)")
    elif alt_idx <= 25:
        if recovery > 50:
            bull_score += 10
            signals.append("BTC leading (early bull)")
        else:
            bear_score += 10
            signals.append("Flight to BTC (risk-off)")

    # BTC Dominance signals
    if btc_dom >= 60:
        if fg < 40:
            bear_score += 10
        else:
            accumulation_score += 5
            bull_score += 5
    elif btc_dom <= 40:
        distribution_score += 15
        signals.append("Low BTC dominance (risk-on)")

    # Final adjustments
    if is_recent_drop and fg < 40:
        bear_score += 15
        accumulation_score = max(0, accumulation_score - 10)

    # Determine winning season
    scores = {
        "accumulation": accumulation_score,
        "bull": bull_score,
        "distribution": distribution_score,
        "bear": bear_score
    }

    max_score = max(scores.values())
    total_score = sum(scores.values())

    # Default to bear if uncertain
    season: SeasonType = "bear"
    if max_score == scores["distribution"]:
        season = "distribution"
    elif max_score == scores["bull"]:
        season = "bull"
    elif max_score == scores["accumulation"]:
        season = "accumulation"

    confidence = round((max_score / total_score) * 100) if total_score > 0 else 50

    # Calculate progress within season
    progress = 50.0
    if season == "accumulation":
        progress = max(0, min(100, (fg - 10) * 2))
    elif season == "bull":
        progress = max(0, min(100, recovery))
    elif season == "distribution":
        progress = max(0, min(100, (fg - 50) * 2))
    elif season == "bear":
        drawdown_progress = min(drawdown * 2, 70)
        time_progress = min(days_since_ath / 5, 30)
        progress = max(0, min(100, drawdown_progress + time_progress))

    # Season metadata
    season_meta = {
        "accumulation": ("Spring", "Accumulation Phase", "Smart money quietly buying. Fear dominates headlines."),
        "bull": ("Summer", "Bull Market", "Prices rising, optimism growing. Momentum building."),
        "distribution": ("Fall", "Distribution Phase", "Peak euphoria. Smart money taking profits."),
        "bear": ("Winter", "Bear Market", "Prices falling, fear spreading. Patience required.")
    }

    name, subtitle, description = season_meta[season]

    return SeasonInfo(
        season=season,
        name=name,
        subtitle=subtitle,
        description=description,
        progress=progress,
        confidence=confidence,
        signals=signals[:3]  # Top 3 signals
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
    # Fetch all data in parallel would be more efficient, but sequential is simpler
    fear_greed = await fetch_fear_greed()
    ath_data = await fetch_ath_data()
    btc_dominance = await fetch_btc_dominance()
    altseason_idx = await fetch_altseason_index()

    return determine_season(fear_greed, ath_data, altseason_idx, btc_dominance)


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
