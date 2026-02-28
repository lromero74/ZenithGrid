"""
Tests for backend/app/services/market_metrics_service.py

Covers:
- record_metric_snapshot: write snapshot to DB
- prune_old_snapshots: delete old snapshots with guard
- calculate_btc_supply: pure supply calculation
- get_metric_history_data: fetch + downsample
- fetch_btc_block_height: external API fetch
- fetch_fear_greed_index: external API fetch
- fetch_btc_dominance: external API fetch
- fetch_mempool_stats: external API fetch
- fetch_lightning_stats: external API fetch
- fetch_btc_rsi: external API fetch + RSI calc
"""

import asyncio
import time
from contextlib import asynccontextmanager

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.exceptions import ExchangeUnavailableError
from app.services.market_metrics_service import (
    calculate_btc_supply,
    fetch_btc_block_height,
    fetch_btc_dominance,
    fetch_fear_greed_index,
    fetch_hash_rate,
    fetch_lightning_stats,
    fetch_mempool_stats,
    fetch_btc_rsi,
    get_metric_history_data,
    prune_old_snapshots,
    record_metric_snapshot,
)


# =============================================================================
# Helper: mock aiohttp session.get() context manager
# =============================================================================


class MockResponse:
    """Mimics an aiohttp response object usable as async context manager."""

    def __init__(self, status=200, json_data=None, text_data=None):
        self.status = status
        self._json_data = json_data
        self._text_data = text_data

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _make_session(*responses):
    """
    Build a MagicMock session where session.get() returns async context managers.

    Each response should be a MockResponse instance. For multiple calls, they
    are returned in order (side_effect).
    """
    session = MagicMock()
    if len(responses) == 1:
        session.get.return_value = responses[0]
    else:
        session.get.side_effect = list(responses)
    return session


# =============================================================================
# calculate_btc_supply (pure function)
# =============================================================================


class TestCalculateBtcSupply:
    """Tests for calculate_btc_supply()."""

    def test_genesis_block(self):
        """Edge case: block 0 yields 0 circulating."""
        result = calculate_btc_supply(0)
        assert result["circulating"] == 0
        assert result["max_supply"] == 21_000_000
        assert result["remaining"] == 21_000_000
        assert result["current_block"] == 0

    def test_first_halving_boundary(self):
        """Happy path: exactly at the first halving boundary (210,000 blocks)."""
        result = calculate_btc_supply(210_000)
        assert result["circulating"] == pytest.approx(10_500_000)
        assert result["remaining"] == pytest.approx(10_500_000)
        assert result["percent_mined"] == pytest.approx(50.0)

    def test_after_first_halving(self):
        """Happy path: 210,001 blocks -- first block of second era."""
        result = calculate_btc_supply(210_001)
        assert result["circulating"] == pytest.approx(10_500_025.0)

    def test_realistic_block_height(self):
        """Happy path: realistic block height ~870,000."""
        result = calculate_btc_supply(870_000)
        assert result["circulating"] > 0
        assert result["circulating"] < 21_000_000
        assert result["percent_mined"] > 90
        assert result["current_block"] == 870_000

    def test_very_large_height_approaches_max(self):
        """Edge case: very large height approaches but never exceeds max supply."""
        result = calculate_btc_supply(10_000_000)
        assert result["circulating"] <= 21_000_000
        assert result["remaining"] >= 0


# =============================================================================
# record_metric_snapshot
# =============================================================================


class TestRecordMetricSnapshot:
    """Tests for record_metric_snapshot()."""

    @pytest.mark.asyncio
    async def test_records_snapshot_successfully(self):
        """Happy path: snapshot is committed to DB."""
        mock_session = AsyncMock()
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.market_metrics_service.async_session_maker",
            return_value=mock_db,
        ):
            await record_metric_snapshot("fear_greed", 72.0)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_logs_warning_on_db_error(self):
        """Failure: DB error is caught and logged, does not raise."""
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(side_effect=Exception("DB connection failed"))
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.market_metrics_service.async_session_maker",
            return_value=mock_db,
        ):
            await record_metric_snapshot("fear_greed", 72.0)


# =============================================================================
# prune_old_snapshots
# =============================================================================


class TestPruneOldSnapshots:
    """Tests for prune_old_snapshots()."""

    @pytest.mark.asyncio
    async def test_prunes_when_interval_elapsed(self):
        """Happy path: prunes when enough time has passed since last prune."""
        import app.services.market_metrics_service as mms
        mms._last_prune_time = 0.0

        mock_session = AsyncMock()
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.market_metrics_service.async_session_maker",
            return_value=mock_db,
        ):
            await prune_old_snapshots()

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_prune_when_recently_pruned(self):
        """Edge case: skips prune if called again within the interval."""
        import app.services.market_metrics_service as mms
        mms._last_prune_time = time.monotonic()

        mock_session = AsyncMock()
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.market_metrics_service.async_session_maker",
            return_value=mock_db,
        ):
            await prune_old_snapshots()

        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_warning_on_db_error(self):
        """Failure: DB error during prune is caught and logged."""
        import app.services.market_metrics_service as mms
        mms._last_prune_time = 0.0

        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("DB error")
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.market_metrics_service.async_session_maker",
            return_value=mock_db,
        ):
            await prune_old_snapshots()


# =============================================================================
# get_metric_history_data
# =============================================================================


class TestGetMetricHistoryData:
    """Tests for get_metric_history_data()."""

    @pytest.mark.asyncio
    async def test_returns_data_without_downsampling(self):
        """Happy path: fewer rows than max_points returns all."""
        row1 = MagicMock()
        row1.value = 50.0
        row1.recorded_at = MagicMock()
        row1.recorded_at.isoformat.return_value = "2025-01-01T00:00:00"

        row2 = MagicMock()
        row2.value = 60.0
        row2.recorded_at = MagicMock()
        row2.recorded_at.isoformat.return_value = "2025-01-02T00:00:00"

        mock_result = MagicMock()
        mock_result.all.return_value = [row1, row2]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.market_metrics_service.async_session_maker",
            return_value=mock_db,
        ), patch(
            "app.services.market_metrics_service.prune_old_snapshots",
            new_callable=AsyncMock,
        ):
            result = await get_metric_history_data("fear_greed", days=7, max_points=100)

        assert result["metric_name"] == "fear_greed"
        assert len(result["data"]) == 2
        assert result["data"][0]["value"] == 50.0

    @pytest.mark.asyncio
    async def test_downsamples_when_too_many_rows(self):
        """Edge case: more rows than max_points triggers downsampling."""
        rows = []
        for i in range(20):
            r = MagicMock()
            r.value = float(i * 5)
            r.recorded_at = MagicMock()
            r.recorded_at.isoformat.return_value = f"2025-01-{i+1:02d}T00:00:00"
            rows.append(r)

        mock_result = MagicMock()
        mock_result.all.return_value = rows

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.market_metrics_service.async_session_maker",
            return_value=mock_db,
        ), patch(
            "app.services.market_metrics_service.prune_old_snapshots",
            new_callable=AsyncMock,
        ):
            result = await get_metric_history_data("btc_dominance", days=30, max_points=5)

        assert len(result["data"]) == 5

    @pytest.mark.asyncio
    async def test_empty_data_returns_empty_list(self):
        """Edge case: no rows returns empty data list."""
        mock_result = MagicMock()
        mock_result.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.market_metrics_service.async_session_maker",
            return_value=mock_db,
        ):
            result = await get_metric_history_data("hash_rate", days=7, max_points=100)

        assert result["data"] == []
        assert result["metric_name"] == "hash_rate"


# =============================================================================
# fetch_btc_block_height
# =============================================================================


class TestFetchBtcBlockHeight:
    """Tests for fetch_btc_block_height()."""

    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        """Happy path: returns parsed block height."""
        session = _make_session(MockResponse(status=200, text_data="870123"))

        with patch(
            "app.services.market_metrics_service.get_shared_session",
            new_callable=AsyncMock,
            return_value=session,
        ), patch("app.services.market_metrics_service.save_block_height_cache"):
            result = await fetch_btc_block_height()

        assert result["height"] == 870123

    @pytest.mark.asyncio
    async def test_non_200_raises(self):
        """Failure: non-200 status raises ExchangeUnavailableError."""
        session = _make_session(MockResponse(status=500))

        with patch(
            "app.services.market_metrics_service.get_shared_session",
            new_callable=AsyncMock,
            return_value=session,
        ):
            with pytest.raises(ExchangeUnavailableError):
                await fetch_btc_block_height()

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        """Failure: timeout raises ExchangeUnavailableError."""
        session = MagicMock()
        session.get.side_effect = asyncio.TimeoutError()

        with patch(
            "app.services.market_metrics_service.get_shared_session",
            new_callable=AsyncMock,
            return_value=session,
        ):
            with pytest.raises(ExchangeUnavailableError, match="timeout"):
                await fetch_btc_block_height()

    @pytest.mark.asyncio
    async def test_invalid_response_raises(self):
        """Failure: non-integer response raises ExchangeUnavailableError."""
        session = _make_session(MockResponse(status=200, text_data="not a number"))

        with patch(
            "app.services.market_metrics_service.get_shared_session",
            new_callable=AsyncMock,
            return_value=session,
        ):
            with pytest.raises(ExchangeUnavailableError):
                await fetch_btc_block_height()


# =============================================================================
# fetch_fear_greed_index
# =============================================================================


class TestFetchFearGreedIndex:
    """Tests for fetch_fear_greed_index()."""

    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        """Happy path: returns parsed fear & greed data."""
        session = _make_session(MockResponse(status=200, json_data={
            "data": [{"value": "75", "value_classification": "Greed", "timestamp": "1700000000"}]
        }))

        with patch(
            "app.services.market_metrics_service.get_shared_session",
            new_callable=AsyncMock,
            return_value=session,
        ), patch(
            "app.services.market_metrics_service.save_fear_greed_cache",
        ), patch(
            "app.services.market_metrics_service.record_metric_snapshot",
            new_callable=AsyncMock,
        ):
            result = await fetch_fear_greed_index()

        assert result["data"]["value"] == 75
        assert result["data"]["value_classification"] == "Greed"

    @pytest.mark.asyncio
    async def test_api_error_raises(self):
        """Failure: non-200 status raises ExchangeUnavailableError."""
        session = _make_session(MockResponse(status=429))

        with patch(
            "app.services.market_metrics_service.get_shared_session",
            new_callable=AsyncMock,
            return_value=session,
        ):
            with pytest.raises(ExchangeUnavailableError):
                await fetch_fear_greed_index()


# =============================================================================
# fetch_btc_dominance
# =============================================================================


class TestFetchBtcDominance:
    """Tests for fetch_btc_dominance()."""

    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        """Happy path: returns BTC dominance data."""
        session = _make_session(MockResponse(status=200, json_data={
            "data": {
                "market_cap_percentage": {"btc": 54.5, "eth": 17.2},
                "total_market_cap": {"usd": 2500000000000},
            }
        }))

        with patch(
            "app.services.market_metrics_service.get_shared_session",
            new_callable=AsyncMock,
            return_value=session,
        ), patch(
            "app.services.market_metrics_service.save_btc_dominance_cache",
        ), patch(
            "app.services.market_metrics_service.record_metric_snapshot",
            new_callable=AsyncMock,
        ):
            result = await fetch_btc_dominance()

        assert result["btc_dominance"] == 54.5
        assert result["eth_dominance"] == 17.2
        assert result["others_dominance"] == pytest.approx(28.3)

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        """Failure: timeout raises ExchangeUnavailableError."""
        session = MagicMock()
        session.get.side_effect = asyncio.TimeoutError()

        with patch(
            "app.services.market_metrics_service.get_shared_session",
            new_callable=AsyncMock,
            return_value=session,
        ):
            with pytest.raises(ExchangeUnavailableError, match="timeout"):
                await fetch_btc_dominance()


# =============================================================================
# fetch_btc_rsi
# =============================================================================


class TestFetchBtcRsi:
    """Tests for fetch_btc_rsi()."""

    @pytest.mark.asyncio
    async def test_successful_fetch_neutral_zone(self):
        """Happy path: returns RSI in neutral zone."""
        candles = [{"start": str(i), "close": str(50000 + i * 100)} for i in range(20)]
        session = _make_session(MockResponse(status=200, json_data={"candles": candles}))
        mock_calc = MagicMock()
        mock_calc.calculate_rsi.return_value = 55.0

        with patch(
            "app.services.market_metrics_service.get_shared_session",
            new_callable=AsyncMock,
            return_value=session,
        ), patch(
            "app.services.market_metrics_service.IndicatorCalculator",
            return_value=mock_calc,
        ), patch(
            "app.services.market_metrics_service.save_btc_rsi_cache",
        ), patch(
            "app.services.market_metrics_service.record_metric_snapshot",
            new_callable=AsyncMock,
        ):
            result = await fetch_btc_rsi()

        assert result["rsi"] == 55.0
        assert result["zone"] == "neutral"

    @pytest.mark.asyncio
    async def test_insufficient_candles_raises(self):
        """Failure: fewer than 15 candles raises ExchangeUnavailableError."""
        candles = [{"start": str(i), "close": str(50000)} for i in range(5)]
        session = _make_session(MockResponse(status=200, json_data={"candles": candles}))

        with patch(
            "app.services.market_metrics_service.get_shared_session",
            new_callable=AsyncMock,
            return_value=session,
        ):
            with pytest.raises(ExchangeUnavailableError, match="Not enough candle"):
                await fetch_btc_rsi()

    @pytest.mark.asyncio
    async def test_rsi_none_raises(self):
        """Failure: RSI calculation returning None raises ExchangeUnavailableError."""
        candles = [{"start": str(i), "close": str(50000)} for i in range(20)]
        session = _make_session(MockResponse(status=200, json_data={"candles": candles}))
        mock_calc = MagicMock()
        mock_calc.calculate_rsi.return_value = None

        with patch(
            "app.services.market_metrics_service.get_shared_session",
            new_callable=AsyncMock,
            return_value=session,
        ), patch(
            "app.services.market_metrics_service.IndicatorCalculator",
            return_value=mock_calc,
        ):
            with pytest.raises(ExchangeUnavailableError, match="RSI calculation failed"):
                await fetch_btc_rsi()

    @pytest.mark.asyncio
    async def test_oversold_zone(self):
        """Edge case: RSI < 30 returns 'oversold' zone."""
        candles = [{"start": str(i), "close": str(50000 - i * 200)} for i in range(20)]
        session = _make_session(MockResponse(status=200, json_data={"candles": candles}))
        mock_calc = MagicMock()
        mock_calc.calculate_rsi.return_value = 22.5

        with patch(
            "app.services.market_metrics_service.get_shared_session",
            new_callable=AsyncMock,
            return_value=session,
        ), patch(
            "app.services.market_metrics_service.IndicatorCalculator",
            return_value=mock_calc,
        ), patch(
            "app.services.market_metrics_service.save_btc_rsi_cache",
        ), patch(
            "app.services.market_metrics_service.record_metric_snapshot",
            new_callable=AsyncMock,
        ):
            result = await fetch_btc_rsi()

        assert result["rsi"] == 22.5
        assert result["zone"] == "oversold"

    @pytest.mark.asyncio
    async def test_overbought_zone(self):
        """Edge case: RSI > 70 returns 'overbought' zone."""
        candles = [{"start": str(i), "close": str(50000 + i * 200)} for i in range(20)]
        session = _make_session(MockResponse(status=200, json_data={"candles": candles}))
        mock_calc = MagicMock()
        mock_calc.calculate_rsi.return_value = 85.3

        with patch(
            "app.services.market_metrics_service.get_shared_session",
            new_callable=AsyncMock,
            return_value=session,
        ), patch(
            "app.services.market_metrics_service.IndicatorCalculator",
            return_value=mock_calc,
        ), patch(
            "app.services.market_metrics_service.save_btc_rsi_cache",
        ), patch(
            "app.services.market_metrics_service.record_metric_snapshot",
            new_callable=AsyncMock,
        ):
            result = await fetch_btc_rsi()

        assert result["rsi"] == 85.3
        assert result["zone"] == "overbought"


# =============================================================================
# fetch_mempool_stats
# =============================================================================


class TestFetchMempoolStats:
    """Tests for fetch_mempool_stats()."""

    @pytest.mark.asyncio
    async def test_successful_fetch_low_congestion(self):
        """Happy path: low congestion mempool."""
        mempool_resp = MockResponse(status=200, json_data={
            "count": 5000, "vsize": 100000, "total_fee": 50000
        })
        fee_resp = MockResponse(status=200, json_data={
            "fastestFee": 20, "halfHourFee": 15, "hourFee": 10, "economyFee": 5
        })
        session = _make_session(mempool_resp, fee_resp)

        with patch(
            "app.services.market_metrics_service.get_shared_session",
            new_callable=AsyncMock,
            return_value=session,
        ), patch(
            "app.services.market_metrics_service.save_mempool_cache",
        ), patch(
            "app.services.market_metrics_service.record_metric_snapshot",
            new_callable=AsyncMock,
        ):
            result = await fetch_mempool_stats()

        assert result["tx_count"] == 5000
        assert result["congestion"] == "Low"
        assert result["fee_fastest"] == 20

    @pytest.mark.asyncio
    async def test_high_congestion(self):
        """Edge case: high tx count results in 'High' congestion."""
        mempool_resp = MockResponse(status=200, json_data={
            "count": 60000, "vsize": 500000, "total_fee": 200000
        })
        fee_resp = MockResponse(status=200, json_data={
            "fastestFee": 100, "halfHourFee": 80, "hourFee": 50, "economyFee": 20
        })
        session = _make_session(mempool_resp, fee_resp)

        with patch(
            "app.services.market_metrics_service.get_shared_session",
            new_callable=AsyncMock,
            return_value=session,
        ), patch(
            "app.services.market_metrics_service.save_mempool_cache",
        ), patch(
            "app.services.market_metrics_service.record_metric_snapshot",
            new_callable=AsyncMock,
        ):
            result = await fetch_mempool_stats()

        assert result["congestion"] == "High"

    @pytest.mark.asyncio
    async def test_mempool_api_unavailable_raises(self):
        """Failure: mempool API returning non-200 raises ExchangeUnavailableError."""
        session = _make_session(MockResponse(status=503))

        with patch(
            "app.services.market_metrics_service.get_shared_session",
            new_callable=AsyncMock,
            return_value=session,
        ):
            with pytest.raises(ExchangeUnavailableError):
                await fetch_mempool_stats()


# =============================================================================
# fetch_lightning_stats
# =============================================================================


class TestFetchLightningStats:
    """Tests for fetch_lightning_stats()."""

    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        """Happy path: returns lightning network stats."""
        session = _make_session(MockResponse(status=200, json_data={
            "latest": {
                "channel_count": 55000,
                "node_count": 16000,
                "total_capacity": 500000000000,
                "avg_capacity": 9000000,
                "avg_fee_rate": 500,
            }
        }))

        with patch(
            "app.services.market_metrics_service.get_shared_session",
            new_callable=AsyncMock,
            return_value=session,
        ), patch(
            "app.services.market_metrics_service.save_lightning_cache",
        ), patch(
            "app.services.market_metrics_service.record_metric_snapshot",
            new_callable=AsyncMock,
        ):
            result = await fetch_lightning_stats()

        assert result["channel_count"] == 55000
        assert result["node_count"] == 16000
        assert result["total_capacity_btc"] == 5000.0
