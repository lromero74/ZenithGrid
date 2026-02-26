"""
News Metrics Router

Market sentiment and blockchain metric endpoints.
All fetch logic lives in services/market_metrics_service.py.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.models import User
from app.auth.dependencies import get_current_user
from app.news_data import (
    DEBT_CEILING_HISTORY,
    BlockHeightResponse,
    DebtCeilingEvent,
    DebtCeilingHistoryResponse,
    FearGreedResponse,
    USDebtResponse,
    load_altseason_cache,
    load_ath_cache,
    load_block_height_cache,
    load_btc_dominance_cache,
    load_btc_rsi_cache,
    load_fear_greed_cache,
    load_hash_rate_cache,
    load_lightning_cache,
    load_mempool_cache,
    load_stablecoin_mcap_cache,
    load_us_debt_cache,
)
from app.services.market_metrics_service import (
    calculate_btc_supply,
    fetch_altseason_index,
    fetch_ath_data,
    fetch_btc_block_height,
    fetch_btc_dominance,
    fetch_btc_rsi,
    fetch_fear_greed_index,
    fetch_hash_rate,
    fetch_lightning_stats,
    fetch_mempool_stats,
    fetch_stablecoin_mcap,
    fetch_us_debt,
    get_metric_history_data,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["news-metrics"])

VALID_METRIC_NAMES = {
    "fear_greed", "btc_dominance", "altseason_index", "stablecoin_mcap",
    "total_market_cap", "hash_rate", "lightning_capacity", "mempool_tx_count",
    "btc_rsi",
}


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/fear-greed", response_model=FearGreedResponse)
async def get_fear_greed(current_user: User = Depends(get_current_user)):
    """
    Get the Crypto Fear & Greed Index.

    The index ranges from 0 (Extreme Fear) to 100 (Extreme Greed).
    Data is cached for 15 minutes.
    """
    cache = load_fear_greed_cache()
    if cache:
        logger.info("Serving Fear/Greed from cache")
        return FearGreedResponse(**cache)

    logger.info("Fetching fresh Fear/Greed index...")
    data = await fetch_fear_greed_index()
    return FearGreedResponse(**data)


@router.get("/btc-block-height", response_model=BlockHeightResponse)
async def get_btc_block_height(current_user: User = Depends(get_current_user)):
    """
    Get the current Bitcoin block height.

    Used for BTC halving countdown calculations.
    Data is cached for 10 minutes.
    """
    cache = load_block_height_cache()
    if cache:
        logger.info("Serving BTC block height from cache")
        return BlockHeightResponse(**cache)

    logger.info("Fetching fresh BTC block height...")
    data = await fetch_btc_block_height()
    return BlockHeightResponse(**data)


@router.get("/us-debt", response_model=USDebtResponse)
async def get_us_debt(current_user: User = Depends(get_current_user)):
    """
    Get the current US National Debt with rate of change.

    Returns total debt, debt per second (for animation), GDP, and debt-to-GDP ratio.
    Data is cached for 24 hours.
    """
    cache = load_us_debt_cache()
    if cache:
        logger.info("Serving US debt from cache")
        return USDebtResponse(**cache)

    logger.info("Fetching fresh US debt data...")
    data = await fetch_us_debt()
    return USDebtResponse(**data)


@router.get("/debt-ceiling-history", response_model=DebtCeilingHistoryResponse)
async def get_debt_ceiling_history(
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    """
    Get historical debt ceiling changes/suspensions.

    Returns debt ceiling legislation events from 1939 to present.
    """
    limit = max(1, min(limit, 100))
    events = DEBT_CEILING_HISTORY[:limit]

    return DebtCeilingHistoryResponse(
        events=[DebtCeilingEvent(**e) for e in events],
        total_events=len(DEBT_CEILING_HISTORY),
        last_updated="2025-11-29",
    )


@router.get("/btc-dominance")
async def get_btc_dominance(current_user: User = Depends(get_current_user)):
    """
    Get Bitcoin market dominance percentage.

    Rising dominance = risk-off, altcoins underperforming
    Falling dominance = alt season potential
    """
    cache = load_btc_dominance_cache()
    if cache:
        logger.info("Serving BTC dominance from cache")
        return cache

    logger.info("Fetching fresh BTC dominance data...")
    return await fetch_btc_dominance()


@router.get("/altseason-index")
async def get_altseason_index(current_user: User = Depends(get_current_user)):
    """
    Get Altcoin Season Index (0-100).

    Index >= 75: Altcoin Season (75%+ of top 50 altcoins outperformed BTC over 90 days)
    Index <= 25: Bitcoin Season
    25 < Index < 75: Neutral
    """
    cache = load_altseason_cache()
    if cache:
        logger.info("Serving altseason index from cache")
        return cache

    logger.info("Fetching fresh altseason index...")
    return await fetch_altseason_index()


@router.get("/stablecoin-mcap")
async def get_stablecoin_mcap(current_user: User = Depends(get_current_user)):
    """
    Get total stablecoin market cap.

    High/rising stablecoin mcap = "dry powder" waiting to be deployed = bullish
    Falling stablecoin mcap = capital leaving crypto = bearish
    """
    cache = load_stablecoin_mcap_cache()
    if cache:
        logger.info("Serving stablecoin mcap from cache")
        return cache

    logger.info("Fetching fresh stablecoin mcap...")
    return await fetch_stablecoin_mcap()


@router.get("/total-market-cap")
async def get_total_market_cap(current_user: User = Depends(get_current_user)):
    """
    Get total crypto market capitalization.
    Uses cached BTC dominance data which includes total market cap.
    """
    cache = load_btc_dominance_cache()
    if cache:
        return {
            "total_market_cap": cache.get("total_market_cap", 0),
            "cached_at": cache.get("cached_at"),
        }

    fresh_data = await fetch_btc_dominance()
    return {
        "total_market_cap": fresh_data.get("total_market_cap", 0),
        "cached_at": fresh_data.get("cached_at"),
    }


@router.get("/btc-supply")
async def get_btc_supply(current_user: User = Depends(get_current_user)):
    """
    Get Bitcoin supply progress - how much of the 21M has been mined.
    Calculated from current block height.
    """
    cache = load_block_height_cache()
    if not cache:
        try:
            cache = await fetch_btc_block_height()
        except Exception:
            pass

    if not cache:
        raise HTTPException(status_code=503, detail="Could not fetch block height")

    height = cache.get("height", 0)
    result = calculate_btc_supply(height)
    result["cached_at"] = cache.get("timestamp", datetime.now().isoformat())
    return result


@router.get("/mempool")
async def get_mempool_stats(current_user: User = Depends(get_current_user)):
    """
    Get Bitcoin mempool statistics.
    Shows pending transactions and fee estimates.
    """
    cache = load_mempool_cache()
    if cache:
        logger.info("Serving mempool stats from cache")
        return cache

    logger.info("Fetching fresh mempool stats...")
    return await fetch_mempool_stats()


@router.get("/hash-rate")
async def get_hash_rate(current_user: User = Depends(get_current_user)):
    """
    Get Bitcoin network hash rate.
    Higher = more secure network.
    """
    cache = load_hash_rate_cache()
    if cache:
        logger.info("Serving hash rate from cache")
        return cache

    logger.info("Fetching fresh hash rate...")
    return await fetch_hash_rate()


@router.get("/lightning")
async def get_lightning_stats(current_user: User = Depends(get_current_user)):
    """
    Get Lightning Network statistics.
    Shows nodes, channels, and total capacity.
    """
    cache = load_lightning_cache()
    if cache:
        logger.info("Serving lightning stats from cache")
        return cache

    logger.info("Fetching fresh lightning stats...")
    return await fetch_lightning_stats()


@router.get("/ath")
async def get_ath(current_user: User = Depends(get_current_user)):
    """
    Get Bitcoin ATH (All-Time High) data.
    Shows days since ATH and current drawdown.
    """
    cache = load_ath_cache()
    if cache:
        logger.info("Serving ATH data from cache")
        return cache

    logger.info("Fetching fresh ATH data...")
    return await fetch_ath_data()


@router.get("/btc-rsi")
async def get_btc_rsi(current_user: User = Depends(get_current_user)):
    """
    Get BTC RSI(14) based on daily candles.
    RSI < 30 = oversold, RSI > 70 = overbought.
    """
    cache = load_btc_rsi_cache()
    if cache:
        logger.info("Serving BTC RSI from cache")
        return cache

    logger.info("Fetching fresh BTC RSI data...")
    return await fetch_btc_rsi()


@router.get("/metric-history/{metric_name}")
async def get_metric_history(
    metric_name: str,
    days: int = Query(default=30, ge=1, le=90),
    max_points: int = Query(default=30, ge=5, le=500),
    current_user: User = Depends(get_current_user),
):
    """
    Get historical snapshots for a metric (for sparkline charts).
    Returns averaged/downsampled data (default: 30 points over 14 days).
    """
    if metric_name not in VALID_METRIC_NAMES:
        raise HTTPException(status_code=400, detail=f"Invalid metric: {metric_name}")

    return await get_metric_history_data(metric_name, days, max_points)
