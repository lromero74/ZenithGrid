"""
News Metrics Router

Market sentiment and blockchain metric endpoints:
- Fear & Greed Index
- BTC Block Height / Halving Countdown
- US National Debt
- BTC Dominance / Altseason Index
- Stablecoin Market Cap / Total Market Cap
- Mempool / Hash Rate / Lightning Network
- ATH / RSI / Funding Rates
- Metric history for sparkline charts

Extracted from news_router.py for maintainability.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.database import async_session_maker
from app.indicator_calculator import IndicatorCalculator
from app.models import MetricSnapshot, User
from app.routers.auth_dependencies import get_current_user
from app.routers.news import (
    DEBT_CEILING_HISTORY,
    FEAR_GREED_CACHE_MINUTES,
    US_DEBT_CACHE_HOURS,
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
    load_funding_rates_cache,
    load_hash_rate_cache,
    load_lightning_cache,
    load_mempool_cache,
    load_stablecoin_mcap_cache,
    load_us_debt_cache,
    save_altseason_cache,
    save_ath_cache,
    save_block_height_cache,
    save_btc_dominance_cache,
    save_btc_rsi_cache,
    save_fear_greed_cache,
    save_funding_rates_cache,
    save_hash_rate_cache,
    save_lightning_cache,
    save_mempool_cache,
    save_stablecoin_mcap_cache,
    save_us_debt_cache,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["news-metrics"])

METRIC_SNAPSHOT_PRUNE_DAYS = 90


# =============================================================================
# Metric Snapshot Helpers
# =============================================================================


async def record_metric_snapshot(metric_name: str, value: float) -> None:
    """Record a metric value for sparkline history. Non-blocking, errors are logged."""
    try:
        async with async_session_maker() as db:
            db.add(MetricSnapshot(
                metric_name=metric_name,
                value=value,
                recorded_at=datetime.utcnow(),
            ))
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to record metric snapshot {metric_name}: {e}")


async def prune_old_snapshots() -> None:
    """Delete metric snapshots older than 90 days."""
    try:
        cutoff = datetime.utcnow() - timedelta(days=METRIC_SNAPSHOT_PRUNE_DAYS)
        async with async_session_maker() as db:
            from sqlalchemy import delete
            await db.execute(
                delete(MetricSnapshot).where(MetricSnapshot.recorded_at < cutoff)
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to prune old snapshots: {e}")


# =============================================================================
# External API Fetch Functions
# =============================================================================


async def fetch_btc_block_height() -> Dict[str, Any]:
    """Fetch current BTC block height from blockchain.info API"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}
            async with session.get(
                "https://blockchain.info/q/getblockcount",
                headers=headers,
                timeout=10
            ) as response:
                if response.status != 200:
                    logger.warning(f"Blockchain.info API returned {response.status}")
                    raise HTTPException(status_code=503, detail="Block height API unavailable")

                height_text = await response.text()
                height = int(height_text.strip())

                now = datetime.now()
                cache_data = {
                    "height": height,
                    "timestamp": now.isoformat(),
                    "cached_at": now.isoformat(),
                }

                save_block_height_cache(cache_data)
                return cache_data
    except asyncio.TimeoutError:
        logger.warning("Timeout fetching BTC block height")
        raise HTTPException(status_code=503, detail="Block height API timeout")
    except ValueError as e:
        logger.error(f"Invalid block height response: {e}")
        raise HTTPException(status_code=503, detail="Invalid block height response")
    except Exception as e:
        logger.error(f"Error fetching BTC block height: {e}")
        raise HTTPException(status_code=503, detail="Block height API error")


async def fetch_us_debt() -> Dict[str, Any]:
    """Fetch US National Debt from Treasury Fiscal Data API and GDP from FRED"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}

            # Get last 8 records to calculate 7-day weighted average rate
            debt_url = (
                "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
                "v2/accounting/od/debt_to_penny"
                "?sort=-record_date&page[size]=8"
            )

            # Fetch debt data
            async with session.get(debt_url, headers=headers, timeout=15) as response:
                if response.status != 200:
                    logger.warning(f"Treasury API returned {response.status}")
                    raise HTTPException(status_code=503, detail="Treasury API unavailable")

                data = await response.json()
                records = data.get("data", [])

                if len(records) < 1:
                    raise HTTPException(status_code=503, detail="No debt data available")

                # Get current debt
                latest = records[0]
                total_debt = float(latest.get("tot_pub_debt_out_amt", 0))
                record_date = latest.get("record_date", "")

                # Calculate rate of change per second using 7-day weighted average
                default_rate = 31710.0
                debt_per_second = default_rate

                if len(records) >= 2:
                    daily_rates = []
                    for i in range(len(records) - 1):
                        curr = records[i]
                        prev = records[i + 1]
                        curr_debt = float(curr.get("tot_pub_debt_out_amt", 0))
                        prev_debt = float(prev.get("tot_pub_debt_out_amt", 0))
                        curr_date = curr.get("record_date", "")
                        prev_date = prev.get("record_date", "")

                        if prev_date and curr_date:
                            date1 = datetime.strptime(curr_date, "%Y-%m-%d")
                            date2 = datetime.strptime(prev_date, "%Y-%m-%d")
                            days_diff = (date1 - date2).days

                            if days_diff > 0:
                                debt_change = curr_debt - prev_debt
                                seconds_diff = days_diff * 24 * 60 * 60
                                rate = debt_change / seconds_diff
                                if rate > 0:
                                    daily_rates.append(rate)

                    if daily_rates:
                        num_rates = len(daily_rates)
                        weights = []
                        for i in range(num_rates):
                            if i < 1:
                                weights.append(3)
                            elif i < 3:
                                weights.append(2)
                            else:
                                weights.append(1)

                        weighted_sum = sum(r * w for r, w in zip(daily_rates, weights))
                        total_weight = sum(weights)
                        debt_per_second = weighted_sum / total_weight
                        logger.info(f"Calculated debt rate from {num_rates} days: ${debt_per_second:.2f}/sec (weighted avg)")
                    else:
                        logger.info("No positive debt rates found, using default rate")
                        debt_per_second = default_rate

            # Fetch GDP from FRED
            gdp = 28_000_000_000_000.0
            try:
                gdp_url = (
                    "https://api.stlouisfed.org/fred/series/observations"
                    "?series_id=GDP&api_key=DEMO_KEY&file_type=json"
                    "&sort_order=desc&limit=1"
                )
                async with session.get(gdp_url, headers=headers, timeout=10) as gdp_response:
                    if gdp_response.status == 200:
                        gdp_data = await gdp_response.json()
                        observations = gdp_data.get("observations", [])
                        if observations:
                            gdp_billions = float(observations[0].get("value", 28000))
                            gdp = gdp_billions * 1_000_000_000
                    else:
                        logger.warning(f"FRED GDP API returned {gdp_response.status}, using fallback")
            except Exception as e:
                logger.warning(f"Failed to fetch GDP: {e}, using fallback")

            debt_to_gdp_ratio = (total_debt / gdp * 100) if gdp > 0 else 0

            # Get current debt ceiling from history
            debt_ceiling = None
            debt_ceiling_suspended = False
            debt_ceiling_note = None
            headroom = None

            if DEBT_CEILING_HISTORY:
                latest_ceiling = DEBT_CEILING_HISTORY[0]
                debt_ceiling_suspended = latest_ceiling.get("suspended", False)
                debt_ceiling_note = latest_ceiling.get("note", "")

                if debt_ceiling_suspended:
                    suspension_end = latest_ceiling.get("suspension_end")
                    if suspension_end:
                        debt_ceiling_note = f"Suspended until {suspension_end}"
                else:
                    amount_trillion = latest_ceiling.get("amount_trillion")
                    if amount_trillion:
                        debt_ceiling = amount_trillion * 1_000_000_000_000
                        headroom = debt_ceiling - total_debt

            now = datetime.now()
            cache_data = {
                "total_debt": total_debt,
                "debt_per_second": debt_per_second,
                "gdp": gdp,
                "debt_to_gdp_ratio": round(debt_to_gdp_ratio, 2),
                "record_date": record_date,
                "cached_at": now.isoformat(),
                "cache_expires_at": (now + timedelta(hours=US_DEBT_CACHE_HOURS)).isoformat(),
                "debt_ceiling": debt_ceiling,
                "debt_ceiling_suspended": debt_ceiling_suspended,
                "debt_ceiling_note": debt_ceiling_note,
                "headroom": headroom,
            }

            save_us_debt_cache(cache_data)
            return cache_data
    except asyncio.TimeoutError:
        logger.warning("Timeout fetching US debt")
        raise HTTPException(status_code=503, detail="Treasury API timeout")
    except Exception as e:
        logger.error(f"Error fetching US debt: {e}")
        raise HTTPException(status_code=503, detail="Treasury API error")


async def fetch_fear_greed_index() -> Dict[str, Any]:
    """Fetch Fear & Greed Index from Alternative.me API"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}
            async with session.get(
                "https://api.alternative.me/fng/",
                headers=headers,
                timeout=10
            ) as response:
                if response.status != 200:
                    logger.warning(f"Fear/Greed API returned {response.status}")
                    raise HTTPException(status_code=503, detail="Fear/Greed API unavailable")

                data = await response.json()
                fng_data = data.get("data", [{}])[0]

                now = datetime.now()
                cache_data = {
                    "data": {
                        "value": int(fng_data.get("value", 50)),
                        "value_classification": fng_data.get("value_classification", "Neutral"),
                        "timestamp": datetime.fromtimestamp(int(fng_data.get("timestamp", 0))).isoformat(),
                        "time_until_update": fng_data.get("time_until_update"),
                    },
                    "cached_at": now.isoformat(),
                    "cache_expires_at": (now + timedelta(minutes=FEAR_GREED_CACHE_MINUTES)).isoformat(),
                }

                save_fear_greed_cache(cache_data)
                asyncio.create_task(record_metric_snapshot("fear_greed", cache_data["data"]["value"]))
                return cache_data
    except asyncio.TimeoutError:
        logger.warning("Timeout fetching Fear/Greed index")
        raise HTTPException(status_code=503, detail="Fear/Greed API timeout")
    except Exception as e:
        logger.error(f"Error fetching Fear/Greed index: {e}")
        raise HTTPException(status_code=503, detail="Fear/Greed API error")


async def fetch_btc_dominance() -> Dict[str, Any]:
    """Fetch Bitcoin dominance from CoinGecko"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}
            url = "https://api.coingecko.com/api/v3/global"

            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status != 200:
                    logger.warning(f"CoinGecko global API returned {response.status}")
                    raise HTTPException(status_code=503, detail="CoinGecko API unavailable")

                data = await response.json()
                global_data = data.get("data", {})

                btc_dominance = global_data.get("market_cap_percentage", {}).get("btc", 0)
                eth_dominance = global_data.get("market_cap_percentage", {}).get("eth", 0)
                total_mcap = global_data.get("total_market_cap", {}).get("usd", 0)

                now = datetime.now()
                cache_data = {
                    "btc_dominance": round(btc_dominance, 2),
                    "eth_dominance": round(eth_dominance, 2),
                    "others_dominance": round(100 - btc_dominance - eth_dominance, 2),
                    "total_market_cap": total_mcap,
                    "cached_at": now.isoformat(),
                }

                save_btc_dominance_cache(cache_data)
                asyncio.create_task(record_metric_snapshot("btc_dominance", cache_data["btc_dominance"]))
                asyncio.create_task(record_metric_snapshot("total_market_cap", cache_data["total_market_cap"]))
                return cache_data

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching BTC dominance")
        raise HTTPException(status_code=503, detail="CoinGecko API timeout")
    except Exception as e:
        logger.error(f"Error fetching BTC dominance: {e}")
        raise HTTPException(status_code=503, detail="CoinGecko API error")


async def fetch_altseason_index() -> Dict[str, Any]:
    """
    Calculate Altcoin Season Index based on top coins performance vs BTC.
    Altcoin season = 75%+ of top 50 altcoins outperformed BTC over 30 days.
    """
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}
            url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=51&sparkline=false&price_change_percentage=30d"

            async with session.get(url, headers=headers, timeout=20) as response:
                if response.status != 200:
                    logger.warning(f"CoinGecko markets API returned {response.status}")
                    raise HTTPException(status_code=503, detail="CoinGecko API unavailable")

                coins = await response.json()

                btc_change = 0
                altcoins = []
                for coin in coins:
                    if coin.get("id") == "bitcoin":
                        btc_change = coin.get("price_change_percentage_30d_in_currency", 0) or 0
                    elif coin.get("id") not in ["tether", "usd-coin", "dai", "binance-usd"]:
                        altcoins.append(coin)

                outperformers = 0
                for coin in altcoins[:50]:
                    coin_change = coin.get("price_change_percentage_30d_in_currency", 0) or 0
                    if coin_change > btc_change:
                        outperformers += 1

                total_altcoins = min(len(altcoins), 50)
                altseason_index = round((outperformers / total_altcoins) * 100) if total_altcoins > 0 else 50

                if altseason_index >= 75:
                    season = "Altcoin Season"
                elif altseason_index <= 25:
                    season = "Bitcoin Season"
                else:
                    season = "Neutral"

                now = datetime.now()
                cache_data = {
                    "altseason_index": altseason_index,
                    "season": season,
                    "outperformers": outperformers,
                    "total_altcoins": total_altcoins,
                    "btc_30d_change": round(btc_change, 2),
                    "cached_at": now.isoformat(),
                }

                save_altseason_cache(cache_data)
                asyncio.create_task(record_metric_snapshot("altseason_index", cache_data["altseason_index"]))
                return cache_data

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching altseason index")
        raise HTTPException(status_code=503, detail="CoinGecko API timeout")
    except Exception as e:
        logger.error(f"Error fetching altseason index: {e}")
        raise HTTPException(status_code=503, detail="CoinGecko API error")


async def fetch_funding_rates() -> Dict[str, Any]:
    """
    Fetch BTC and ETH perpetual funding rates from CoinGlass public API.
    Positive = longs pay shorts (bullish overcrowded)
    Negative = shorts pay longs (bearish overcrowded)
    """
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}
            url = "https://open-api.coinglass.com/public/v2/funding"

            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    funding_data = data.get("data", [])

                    btc_funding = None
                    eth_funding = None

                    for item in funding_data:
                        symbol = item.get("symbol", "").upper()
                        if symbol == "BTC":
                            btc_funding = item.get("uMarginList", [{}])[0].get("rate", 0)
                        elif symbol == "ETH":
                            eth_funding = item.get("uMarginList", [{}])[0].get("rate", 0)

                    if btc_funding is not None:
                        now = datetime.now()
                        cache_data = {
                            "btc_funding_rate": round(btc_funding * 100, 4),
                            "eth_funding_rate": round((eth_funding or 0) * 100, 4),
                            "sentiment": "Overleveraged Longs" if (btc_funding or 0) > 0.01 else (
                                "Overleveraged Shorts" if (btc_funding or 0) < -0.01 else "Neutral"
                            ),
                            "cached_at": now.isoformat(),
                        }
                        save_funding_rates_cache(cache_data)
                        return cache_data

                logger.warning("CoinGlass funding API unavailable, using fallback")
                now = datetime.now()
                return {
                    "btc_funding_rate": 0.01,
                    "eth_funding_rate": 0.01,
                    "sentiment": "Data Unavailable",
                    "cached_at": now.isoformat(),
                }

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching funding rates")
        return {"btc_funding_rate": 0, "eth_funding_rate": 0, "sentiment": "Data Unavailable", "cached_at": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching funding rates: {e}")
        return {"btc_funding_rate": 0, "eth_funding_rate": 0, "sentiment": "Data Unavailable", "cached_at": datetime.now().isoformat()}


async def fetch_stablecoin_mcap() -> Dict[str, Any]:
    """Fetch total stablecoin market cap from CoinGecko"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}
            url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&category=stablecoins&order=market_cap_desc&per_page=20&sparkline=false"

            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status != 200:
                    logger.warning(f"CoinGecko stablecoins API returned {response.status}")
                    raise HTTPException(status_code=503, detail="CoinGecko API unavailable")

                coins = await response.json()
                total_mcap = sum(coin.get("market_cap", 0) or 0 for coin in coins)

                usdt_mcap = 0
                usdc_mcap = 0
                dai_mcap = 0
                others_mcap = 0

                for coin in coins:
                    coin_id = coin.get("id", "")
                    mcap = coin.get("market_cap", 0) or 0
                    if coin_id == "tether":
                        usdt_mcap = mcap
                    elif coin_id == "usd-coin":
                        usdc_mcap = mcap
                    elif coin_id == "dai":
                        dai_mcap = mcap
                    else:
                        others_mcap += mcap

                now = datetime.now()
                cache_data = {
                    "total_stablecoin_mcap": total_mcap,
                    "usdt_mcap": usdt_mcap,
                    "usdc_mcap": usdc_mcap,
                    "dai_mcap": dai_mcap,
                    "others_mcap": others_mcap,
                    "cached_at": now.isoformat(),
                }

                save_stablecoin_mcap_cache(cache_data)
                asyncio.create_task(record_metric_snapshot("stablecoin_mcap", cache_data["total_stablecoin_mcap"]))
                return cache_data

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching stablecoin mcap")
        raise HTTPException(status_code=503, detail="CoinGecko API timeout")
    except Exception as e:
        logger.error(f"Error fetching stablecoin mcap: {e}")
        raise HTTPException(status_code=503, detail="CoinGecko API error")


async def fetch_mempool_stats() -> Dict[str, Any]:
    """
    Fetch Bitcoin mempool statistics from mempool.space API.
    Shows network congestion and fee estimates.
    """
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}

            async with session.get(
                "https://mempool.space/api/mempool",
                headers=headers,
                timeout=15
            ) as response:
                if response.status != 200:
                    raise HTTPException(status_code=503, detail="Mempool API unavailable")
                mempool_data = await response.json()

            async with session.get(
                "https://mempool.space/api/v1/fees/recommended",
                headers=headers,
                timeout=15
            ) as response:
                if response.status != 200:
                    fee_data = {"fastestFee": 0, "halfHourFee": 0, "hourFee": 0, "economyFee": 0}
                else:
                    fee_data = await response.json()

            now = datetime.now()
            cache_data = {
                "tx_count": mempool_data.get("count", 0),
                "vsize": mempool_data.get("vsize", 0),
                "total_fee": mempool_data.get("total_fee", 0),
                "fee_fastest": fee_data.get("fastestFee", 0),
                "fee_half_hour": fee_data.get("halfHourFee", 0),
                "fee_hour": fee_data.get("hourFee", 0),
                "fee_economy": fee_data.get("economyFee", 0),
                "congestion": "High" if mempool_data.get("count", 0) > 50000 else (
                    "Medium" if mempool_data.get("count", 0) > 20000 else "Low"
                ),
                "cached_at": now.isoformat(),
            }

            save_mempool_cache(cache_data)
            asyncio.create_task(record_metric_snapshot("mempool_tx_count", cache_data["tx_count"]))
            return cache_data

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching mempool stats")
        raise HTTPException(status_code=503, detail="Mempool API timeout")
    except Exception as e:
        logger.error(f"Error fetching mempool stats: {e}")
        raise HTTPException(status_code=503, detail="Mempool API error")


async def fetch_hash_rate() -> Dict[str, Any]:
    """
    Fetch Bitcoin network hash rate from mempool.space API.
    Higher hash rate = more secure network.
    """
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}

            async with session.get(
                "https://mempool.space/api/v1/mining/hashrate/3d",
                headers=headers,
                timeout=15
            ) as response:
                if response.status != 200:
                    raise HTTPException(status_code=503, detail="Mempool API unavailable")
                data = await response.json()
                hashrates = data.get("hashrates", [])
                if hashrates:
                    latest = hashrates[-1].get("avgHashrate", 0)
                    hash_rate_eh = latest / 1e18
                else:
                    hash_rate_eh = 0

            async with session.get(
                "https://mempool.space/api/v1/difficulty-adjustment",
                headers=headers,
                timeout=15
            ) as response:
                if response.status != 200:
                    difficulty = 0
                else:
                    diff_data = await response.json()
                    difficulty = diff_data.get("difficultyChange", 0)

            now = datetime.now()
            cache_data = {
                "hash_rate_eh": round(hash_rate_eh, 2),
                "difficulty": difficulty,
                "difficulty_t": round(difficulty, 2),
                "cached_at": now.isoformat(),
            }

            save_hash_rate_cache(cache_data)
            asyncio.create_task(record_metric_snapshot("hash_rate", cache_data["hash_rate_eh"]))
            return cache_data

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching hash rate")
        raise HTTPException(status_code=503, detail="Mempool API timeout")
    except Exception as e:
        logger.error(f"Error fetching hash rate: {e}")
        raise HTTPException(status_code=503, detail="Mempool API error")


async def fetch_lightning_stats() -> Dict[str, Any]:
    """
    Fetch Lightning Network statistics from mempool.space API.
    Shows LN adoption and capacity.
    """
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}

            async with session.get(
                "https://mempool.space/api/v1/lightning/statistics/latest",
                headers=headers,
                timeout=15
            ) as response:
                if response.status != 200:
                    raise HTTPException(status_code=503, detail="Lightning API unavailable")
                response_data = await response.json()
                data = response_data.get("latest", response_data)

            now = datetime.now()
            cache_data = {
                "channel_count": data.get("channel_count", 0),
                "node_count": data.get("node_count", 0),
                "total_capacity_btc": round(data.get("total_capacity", 0) / 100_000_000, 2),
                "avg_capacity_sats": data.get("avg_capacity", 0),
                "avg_fee_rate": data.get("avg_fee_rate", 0),
                "cached_at": now.isoformat(),
            }

            save_lightning_cache(cache_data)
            asyncio.create_task(record_metric_snapshot("lightning_capacity", cache_data["total_capacity_btc"]))
            return cache_data

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching lightning stats")
        raise HTTPException(status_code=503, detail="Lightning API timeout")
    except Exception as e:
        logger.error(f"Error fetching lightning stats: {e}")
        raise HTTPException(status_code=503, detail="Lightning API error")


async def fetch_ath_data() -> Dict[str, Any]:
    """
    Fetch Bitcoin ATH (All-Time High) data from CoinGecko.
    Shows days since ATH and drawdown percentage.
    """
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}

            async with session.get(
                "https://api.coingecko.com/api/v3/coins/bitcoin?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false",
                headers=headers,
                timeout=15
            ) as response:
                if response.status != 200:
                    raise HTTPException(status_code=503, detail="CoinGecko API unavailable")
                data = await response.json()

            market_data = data.get("market_data", {})
            current_price = market_data.get("current_price", {}).get("usd", 0)
            ath = market_data.get("ath", {}).get("usd", 0)
            ath_date_str = market_data.get("ath_date", {}).get("usd", "")
            ath_change_pct = market_data.get("ath_change_percentage", {}).get("usd", 0)

            days_since_ath = 0
            if ath_date_str:
                try:
                    ath_date = datetime.fromisoformat(ath_date_str.replace("Z", "+00:00"))
                    days_since_ath = (datetime.now(ath_date.tzinfo) - ath_date).days
                except Exception:
                    pass

            now = datetime.now()
            cache_data = {
                "current_price": round(current_price, 2),
                "ath": round(ath, 2),
                "ath_date": ath_date_str[:10] if ath_date_str else "",
                "days_since_ath": days_since_ath,
                "drawdown_pct": round(ath_change_pct, 2),
                "recovery_pct": round(100 + ath_change_pct, 2) if ath_change_pct < 0 else 100,
                "cached_at": now.isoformat(),
            }

            save_ath_cache(cache_data)
            return cache_data

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching ATH data")
        raise HTTPException(status_code=503, detail="CoinGecko API timeout")
    except Exception as e:
        logger.error(f"Error fetching ATH data: {e}")
        raise HTTPException(status_code=503, detail="CoinGecko API error")


async def fetch_btc_rsi() -> Dict[str, Any]:
    """Fetch BTC-USD daily candles from Coinbase and calculate RSI(14)."""
    try:
        now = int(datetime.now().timestamp())
        start = now - (25 * 24 * 60 * 60)

        async with aiohttp.ClientSession() as session:
            url = (
                f"https://api.coinbase.com/api/v3/brokerage/market/products/BTC-USD/candles"
                f"?start={start}&end={now}&granularity=ONE_DAY"
            )
            headers = {"User-Agent": "ZenithGrid/1.0"}

            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status != 200:
                    logger.warning(f"Coinbase candles API returned {response.status}")
                    raise HTTPException(status_code=503, detail="Coinbase API unavailable")

                data = await response.json()
                candles = data.get("candles", [])

                if len(candles) < 15:
                    raise HTTPException(status_code=503, detail="Not enough candle data for RSI")

                candles.sort(key=lambda c: int(c["start"]))
                closes = [float(c["close"]) for c in candles]

                calc = IndicatorCalculator()
                rsi = calc.calculate_rsi(closes, 14)

                if rsi is None:
                    raise HTTPException(status_code=503, detail="RSI calculation failed")

                rsi = round(rsi, 2)

                if rsi < 30:
                    zone = "oversold"
                elif rsi > 70:
                    zone = "overbought"
                else:
                    zone = "neutral"

                now_dt = datetime.now()
                cache_data = {
                    "rsi": rsi,
                    "zone": zone,
                    "cached_at": now_dt.isoformat(),
                    "cache_expires_at": (now_dt + timedelta(minutes=15)).isoformat(),
                }

                save_btc_rsi_cache(cache_data)
                asyncio.create_task(record_metric_snapshot("btc_rsi", rsi))
                return cache_data

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching BTC RSI candles")
        raise HTTPException(status_code=503, detail="Coinbase API timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching BTC RSI: {e}")
        raise HTTPException(status_code=503, detail="BTC RSI error")


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


@router.get("/funding-rates")
async def get_funding_rates(current_user: User = Depends(get_current_user)):
    """
    Get BTC and ETH perpetual futures funding rates.

    Positive rates = longs pay shorts (market overleveraged long, correction risk)
    Negative rates = shorts pay longs (market overleveraged short, squeeze potential)
    """
    cache = load_funding_rates_cache()
    if cache:
        logger.info("Serving funding rates from cache")
        return cache

    logger.info("Fetching fresh funding rates...")
    return await fetch_funding_rates()


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
            async with aiohttp.ClientSession() as session:
                headers = {"User-Agent": "ZenithGrid/1.0"}
                async with session.get(
                    "https://blockchain.info/q/getblockcount",
                    headers=headers,
                    timeout=10
                ) as response:
                    if response.status == 200:
                        height = int(await response.text())
                        cache = {"height": height}
        except Exception:
            pass

    if not cache:
        raise HTTPException(status_code=503, detail="Could not fetch block height")

    height = cache.get("height", 0)

    circulating = 0
    remaining_blocks = height
    reward = 50
    blocks_per_halving = 210_000

    while remaining_blocks > 0:
        blocks_in_era = min(remaining_blocks, blocks_per_halving)
        circulating += blocks_in_era * reward
        remaining_blocks -= blocks_in_era
        reward /= 2
        blocks_per_halving = 210_000

    max_supply = 21_000_000
    percent_mined = (circulating / max_supply) * 100
    remaining = max_supply - circulating

    return {
        "circulating": round(circulating, 2),
        "max_supply": max_supply,
        "remaining": round(remaining, 2),
        "percent_mined": round(percent_mined, 4),
        "current_block": height,
        "cached_at": cache.get("timestamp", datetime.now().isoformat()),
    }


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


VALID_METRIC_NAMES = {
    "fear_greed", "btc_dominance", "altseason_index", "stablecoin_mcap",
    "total_market_cap", "hash_rate", "lightning_capacity", "mempool_tx_count",
    "btc_rsi",
}


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

    cutoff = datetime.utcnow() - timedelta(days=days)
    async with async_session_maker() as db:
        result = await db.execute(
            select(MetricSnapshot.value, MetricSnapshot.recorded_at)
            .where(MetricSnapshot.metric_name == metric_name)
            .where(MetricSnapshot.recorded_at >= cutoff)
            .order_by(MetricSnapshot.recorded_at)
        )
        rows = result.all()

    # Downsample by averaging into buckets for smooth sparklines
    if len(rows) > max_points:
        bucket_size = len(rows) / max_points
        sampled = []
        for i in range(max_points):
            start = int(i * bucket_size)
            end = int((i + 1) * bucket_size)
            bucket = rows[start:end]
            avg_value = sum(r.value for r in bucket) / len(bucket)
            sampled.append(type('Row', (), {'value': avg_value, 'recorded_at': bucket[-1].recorded_at})())
    else:
        sampled = rows

    # Prune old data periodically (piggyback on reads)
    if len(rows) > 0:
        asyncio.create_task(prune_old_snapshots())

    return {
        "metric_name": metric_name,
        "data": [{"value": r.value, "recorded_at": r.recorded_at.isoformat()} for r in sampled],
    }
