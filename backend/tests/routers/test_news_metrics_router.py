"""
Tests for backend/app/routers/news_metrics_router.py

Covers all 14 metric endpoints: fear_greed, btc_block_height, us_debt,
debt_ceiling_history, btc_dominance, altseason_index, stablecoin_mcap,
total_market_cap, btc_supply, mempool, hash_rate, lightning, ath, btc_rsi,
and metric_history.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.models import User


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def test_user(db_session):
    user = User(
        id=1, email="test@test.com",
        hashed_password="hashed", is_active=True, is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


# =============================================================================
# Fear & Greed Index
# =============================================================================


class TestFearGreed:
    """Tests for get_fear_greed endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_fear_greed_cache")
    async def test_fear_greed_from_cache(self, mock_cache, test_user):
        """Happy path: returns cached fear/greed data."""
        mock_cache.return_value = {
            "data": {
                "value": 72, "value_classification": "Greed",
                "timestamp": "2026-01-01T00:00:00Z",
            },
            "cached_at": "2026-01-01T00:00:00Z",
            "cache_expires_at": "2026-01-01T00:15:00Z",
        }
        from app.routers.news_metrics_router import get_fear_greed
        result = await get_fear_greed(current_user=test_user)
        assert result.data.value == 72
        assert result.data.value_classification == "Greed"

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_fear_greed_cache", return_value=None)
    @patch("app.routers.news_metrics_router.fetch_fear_greed_index", new_callable=AsyncMock)
    async def test_fear_greed_fresh_fetch(self, mock_fetch, mock_cache, test_user):
        """Edge case: cache miss triggers fresh fetch."""
        mock_fetch.return_value = {
            "data": {
                "value": 25, "value_classification": "Fear",
                "timestamp": "2026-01-01T00:00:00Z",
            },
            "cached_at": "2026-01-01T00:00:00Z",
            "cache_expires_at": "2026-01-01T00:15:00Z",
        }
        from app.routers.news_metrics_router import get_fear_greed
        result = await get_fear_greed(current_user=test_user)
        assert result.data.value == 25
        mock_fetch.assert_called_once()


# =============================================================================
# BTC Block Height
# =============================================================================


class TestBtcBlockHeight:
    """Tests for get_btc_block_height endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_block_height_cache")
    async def test_block_height_from_cache(self, mock_cache, test_user):
        """Happy path: returns cached block height."""
        mock_cache.return_value = {
            "height": 850000,
            "timestamp": "2026-01-01T00:00:00Z",
        }
        from app.routers.news_metrics_router import get_btc_block_height
        result = await get_btc_block_height(current_user=test_user)
        assert result.height == 850000

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_block_height_cache", return_value=None)
    @patch("app.routers.news_metrics_router.fetch_btc_block_height", new_callable=AsyncMock)
    async def test_block_height_fresh(self, mock_fetch, mock_cache, test_user):
        """Edge case: cache miss triggers fresh fetch."""
        mock_fetch.return_value = {
            "height": 850001,
            "timestamp": "2026-01-01T00:00:00Z",
        }
        from app.routers.news_metrics_router import get_btc_block_height
        result = await get_btc_block_height(current_user=test_user)
        assert result.height == 850001


# =============================================================================
# US Debt
# =============================================================================


class TestUSDebt:
    """Tests for get_us_debt endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_us_debt_cache")
    async def test_us_debt_from_cache(self, mock_cache, test_user):
        """Happy path: returns cached US debt data."""
        mock_cache.return_value = {
            "total_debt": 36000000000000,
            "debt_per_second": 36529.0,
            "gdp": 27000000000000,
            "debt_to_gdp_ratio": 133.3,
            "record_date": "2026-01-01",
            "cached_at": "2026-01-01T00:00:00Z",
            "cache_expires_at": "2026-01-02T00:00:00Z",
        }
        from app.routers.news_metrics_router import get_us_debt
        result = await get_us_debt(current_user=test_user)
        assert result.total_debt == 36000000000000

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_us_debt_cache", return_value=None)
    @patch("app.routers.news_metrics_router.fetch_us_debt", new_callable=AsyncMock)
    async def test_us_debt_fresh(self, mock_fetch, mock_cache, test_user):
        """Edge case: cache miss triggers fresh fetch."""
        mock_fetch.return_value = {
            "total_debt": 36000000000000,
            "debt_per_second": 36529.0,
            "gdp": 27000000000000,
            "debt_to_gdp_ratio": 133.3,
            "record_date": "2026-01-01",
            "cached_at": "2026-01-01T00:00:00Z",
            "cache_expires_at": "2026-01-02T00:00:00Z",
        }
        from app.routers.news_metrics_router import get_us_debt
        result = await get_us_debt(current_user=test_user)
        mock_fetch.assert_called_once()


# =============================================================================
# Debt Ceiling History
# =============================================================================


class TestDebtCeilingHistory:
    """Tests for get_debt_ceiling_history endpoint."""

    @pytest.mark.asyncio
    async def test_debt_ceiling_returns_events(self, test_user):
        """Happy path: returns historical debt ceiling events."""
        from app.routers.news_metrics_router import get_debt_ceiling_history
        result = await get_debt_ceiling_history(
            limit=5, current_user=test_user,
        )
        assert len(result.events) <= 5
        assert result.total_events > 0

    @pytest.mark.asyncio
    async def test_debt_ceiling_limit_clamped(self, test_user):
        """Edge case: limit is clamped to max 100."""
        from app.routers.news_metrics_router import get_debt_ceiling_history
        result = await get_debt_ceiling_history(
            limit=500, current_user=test_user,
        )
        assert len(result.events) <= 100


# =============================================================================
# BTC Dominance
# =============================================================================


class TestBtcDominance:
    """Tests for get_btc_dominance endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_btc_dominance_cache")
    async def test_btc_dominance_from_cache(self, mock_cache, test_user):
        """Happy path: returns cached BTC dominance."""
        mock_cache.return_value = {"dominance": 54.3, "cached_at": "2026-01-01T00:00:00Z"}
        from app.routers.news_metrics_router import get_btc_dominance
        result = await get_btc_dominance(current_user=test_user)
        assert result["dominance"] == 54.3

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_btc_dominance_cache", return_value=None)
    @patch("app.routers.news_metrics_router.fetch_btc_dominance", new_callable=AsyncMock)
    async def test_btc_dominance_fresh(self, mock_fetch, mock_cache, test_user):
        """Edge case: cache miss triggers fresh fetch."""
        mock_fetch.return_value = {"dominance": 55.0}
        from app.routers.news_metrics_router import get_btc_dominance
        result = await get_btc_dominance(current_user=test_user)
        assert result["dominance"] == 55.0


# =============================================================================
# Altseason Index
# =============================================================================


class TestAltseasonIndex:
    """Tests for get_altseason_index endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_altseason_cache")
    async def test_altseason_from_cache(self, mock_cache, test_user):
        """Happy path: returns cached altseason index."""
        mock_cache.return_value = {"index": 38}
        from app.routers.news_metrics_router import get_altseason_index
        result = await get_altseason_index(current_user=test_user)
        assert result["index"] == 38

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_altseason_cache", return_value=None)
    @patch("app.routers.news_metrics_router.fetch_altseason_index", new_callable=AsyncMock)
    async def test_altseason_fresh(self, mock_fetch, mock_cache, test_user):
        """Edge case: cache miss triggers fresh fetch."""
        mock_fetch.return_value = {"index": 42}
        from app.routers.news_metrics_router import get_altseason_index
        result = await get_altseason_index(current_user=test_user)
        mock_fetch.assert_called_once()


# =============================================================================
# Stablecoin Mcap
# =============================================================================


class TestStablecoinMcap:
    """Tests for get_stablecoin_mcap endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_stablecoin_mcap_cache")
    async def test_stablecoin_mcap_from_cache(self, mock_cache, test_user):
        """Happy path: returns cached stablecoin market cap."""
        mock_cache.return_value = {"total_mcap": 180000000000}
        from app.routers.news_metrics_router import get_stablecoin_mcap
        result = await get_stablecoin_mcap(current_user=test_user)
        assert result["total_mcap"] == 180000000000


# =============================================================================
# Total Market Cap
# =============================================================================


class TestTotalMarketCap:
    """Tests for get_total_market_cap endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_btc_dominance_cache")
    async def test_total_market_cap_from_cache(self, mock_cache, test_user):
        """Happy path: uses BTC dominance cache for total market cap."""
        mock_cache.return_value = {
            "total_market_cap": 3000000000000,
            "cached_at": "2026-01-01T00:00:00Z",
        }
        from app.routers.news_metrics_router import get_total_market_cap
        result = await get_total_market_cap(current_user=test_user)
        assert result["total_market_cap"] == 3000000000000

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_btc_dominance_cache", return_value=None)
    @patch("app.routers.news_metrics_router.fetch_btc_dominance", new_callable=AsyncMock)
    async def test_total_market_cap_fresh(self, mock_fetch, mock_cache, test_user):
        """Edge case: fetches fresh dominance data when cache empty."""
        mock_fetch.return_value = {
            "total_market_cap": 3100000000000,
            "cached_at": "2026-01-01T00:00:00Z",
        }
        from app.routers.news_metrics_router import get_total_market_cap
        result = await get_total_market_cap(current_user=test_user)
        assert result["total_market_cap"] == 3100000000000


# =============================================================================
# BTC Supply
# =============================================================================


class TestBtcSupply:
    """Tests for get_btc_supply endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_block_height_cache")
    @patch("app.routers.news_metrics_router.calculate_btc_supply")
    async def test_btc_supply_success(self, mock_calc, mock_cache, test_user):
        """Happy path: calculates BTC supply from block height."""
        mock_cache.return_value = {
            "height": 850000,
            "timestamp": "2026-01-01T00:00:00Z",
        }
        mock_calc.return_value = {
            "mined": 19700000, "total": 21000000,
            "percentage": 93.8,
        }
        from app.routers.news_metrics_router import get_btc_supply
        result = await get_btc_supply(current_user=test_user)
        assert result["mined"] == 19700000

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_block_height_cache", return_value=None)
    @patch("app.routers.news_metrics_router.fetch_btc_block_height", new_callable=AsyncMock)
    async def test_btc_supply_no_data_raises_503(
        self, mock_fetch, mock_cache, test_user,
    ):
        """Failure case: no block height data raises 503."""
        mock_fetch.side_effect = Exception("API down")
        from app.routers.news_metrics_router import get_btc_supply
        with pytest.raises(HTTPException) as exc_info:
            await get_btc_supply(current_user=test_user)
        assert exc_info.value.status_code == 503


# =============================================================================
# Mempool Stats
# =============================================================================


class TestMempoolStats:
    """Tests for get_mempool_stats endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_mempool_cache")
    async def test_mempool_from_cache(self, mock_cache, test_user):
        """Happy path: returns cached mempool stats."""
        mock_cache.return_value = {"tx_count": 50000, "total_fee": 2.5}
        from app.routers.news_metrics_router import get_mempool_stats
        result = await get_mempool_stats(current_user=test_user)
        assert result["tx_count"] == 50000


# =============================================================================
# Hash Rate
# =============================================================================


class TestHashRate:
    """Tests for get_hash_rate endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_hash_rate_cache")
    async def test_hash_rate_from_cache(self, mock_cache, test_user):
        """Happy path: returns cached hash rate."""
        mock_cache.return_value = {"hash_rate": 650000000}
        from app.routers.news_metrics_router import get_hash_rate
        result = await get_hash_rate(current_user=test_user)
        assert result["hash_rate"] == 650000000


# =============================================================================
# Lightning
# =============================================================================


class TestLightningStats:
    """Tests for get_lightning_stats endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_lightning_cache")
    async def test_lightning_from_cache(self, mock_cache, test_user):
        """Happy path: returns cached lightning stats."""
        mock_cache.return_value = {"capacity_btc": 5600, "node_count": 16000}
        from app.routers.news_metrics_router import get_lightning_stats
        result = await get_lightning_stats(current_user=test_user)
        assert result["capacity_btc"] == 5600


# =============================================================================
# ATH (All-Time High)
# =============================================================================


class TestATH:
    """Tests for get_ath endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_ath_cache")
    async def test_ath_from_cache(self, mock_cache, test_user):
        """Happy path: returns cached ATH data."""
        mock_cache.return_value = {"ath_price": 108000, "days_since": 5}
        from app.routers.news_metrics_router import get_ath
        result = await get_ath(current_user=test_user)
        assert result["ath_price"] == 108000


# =============================================================================
# BTC RSI
# =============================================================================


class TestBtcRSI:
    """Tests for get_btc_rsi endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.load_btc_rsi_cache")
    async def test_btc_rsi_from_cache(self, mock_cache, test_user):
        """Happy path: returns cached RSI value."""
        mock_cache.return_value = {"rsi": 62.5}
        from app.routers.news_metrics_router import get_btc_rsi
        result = await get_btc_rsi(current_user=test_user)
        assert result["rsi"] == 62.5


# =============================================================================
# Metric History
# =============================================================================


class TestMetricHistory:
    """Tests for get_metric_history endpoint."""

    @pytest.mark.asyncio
    @patch("app.routers.news_metrics_router.get_metric_history_data", new_callable=AsyncMock)
    async def test_metric_history_valid_name(self, mock_data, test_user):
        """Happy path: returns metric history data."""
        mock_data.return_value = {"data": [{"x": 1, "y": 50}]}
        from app.routers.news_metrics_router import get_metric_history
        result = await get_metric_history(
            metric_name="fear_greed", days=30, max_points=30,
            current_user=test_user,
        )
        assert "data" in result

    @pytest.mark.asyncio
    async def test_metric_history_invalid_name(self, test_user):
        """Failure case: invalid metric name raises 400."""
        from app.routers.news_metrics_router import get_metric_history
        with pytest.raises(HTTPException) as exc_info:
            await get_metric_history(
                metric_name="invalid_metric", days=30, max_points=30,
                current_user=test_user,
            )
        assert exc_info.value.status_code == 400
