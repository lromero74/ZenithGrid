"""
Tests for news_cache module — file-based caching for news, videos, and market data.

Covers:
- load_cache / save_cache (news): fresh, expired, corrupt, for_merge mode
- prune_old_items: date filtering, missing dates, unparseable dates
- merge_news_items: deduplication, ordering, empty lists
- load_video_cache / save_video_cache
- load_fear_greed_cache / save_fear_greed_cache
- load_block_height_cache / save_block_height_cache
- load_us_debt_cache / save_us_debt_cache
- Generic market metrics caches (btc_dominance, altseason, mempool, etc.)
- Edge cases: missing files, JSON decode errors, write failures
"""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

from app.news_data.news_cache import (
    load_cache,
    save_cache,
    load_video_cache,
    save_video_cache,
    load_fear_greed_cache,
    save_fear_greed_cache,
    load_block_height_cache,
    save_block_height_cache,
    load_us_debt_cache,
    save_us_debt_cache,
    load_btc_dominance_cache,
    save_btc_dominance_cache,
    load_altseason_cache,
    save_altseason_cache,
    load_stablecoin_mcap_cache,
    save_stablecoin_mcap_cache,
    load_mempool_cache,
    save_mempool_cache,
    load_hash_rate_cache,
    save_hash_rate_cache,
    load_lightning_cache,
    save_lightning_cache,
    load_ath_cache,
    save_ath_cache,
    load_btc_rsi_cache,
    save_btc_rsi_cache,
    prune_old_items,
    merge_news_items,
    NEWS_CACHE_CHECK_MINUTES,
    NEWS_ITEM_MAX_AGE_DAYS,
    FEAR_GREED_CACHE_MINUTES,
    BLOCK_HEIGHT_CACHE_MINUTES,
    US_DEBT_CACHE_HOURS,
    MARKET_METRICS_CACHE_MINUTES,
)


# ---------------------------------------------------------------------------
# TestPruneOldItems
# ---------------------------------------------------------------------------

class TestPruneOldItems:
    """Tests for prune_old_items — date-based item removal."""

    def test_keeps_recent_items(self):
        now = datetime.now().isoformat()
        items = [{"url": "https://a.com", "published": now}]
        result = prune_old_items(items, max_age_days=14)
        assert len(result) == 1

    def test_removes_old_items(self):
        old_date = (datetime.now() - timedelta(days=30)).isoformat()
        items = [{"url": "https://old.com", "published": old_date}]
        result = prune_old_items(items, max_age_days=14)
        assert len(result) == 0

    def test_keeps_items_without_published_date(self):
        items = [{"url": "https://no-date.com"}]
        result = prune_old_items(items, max_age_days=14)
        assert len(result) == 1

    def test_keeps_items_with_none_published(self):
        items = [{"url": "https://none.com", "published": None}]
        result = prune_old_items(items, max_age_days=14)
        assert len(result) == 1

    def test_keeps_items_with_unparseable_date(self):
        items = [{"url": "https://bad.com", "published": "not-a-date"}]
        result = prune_old_items(items, max_age_days=14)
        assert len(result) == 1

    def test_handles_z_suffix_dates(self):
        now = datetime.now().isoformat() + "Z"
        items = [{"url": "https://z.com", "published": now}]
        result = prune_old_items(items, max_age_days=14)
        assert len(result) == 1

    def test_boundary_just_inside_cutoff_kept(self):
        # One second newer than the cutoff should be kept
        just_inside = (datetime.now() - timedelta(days=14) + timedelta(seconds=1)).isoformat()
        items = [{"url": "https://edge.com", "published": just_inside}]
        result = prune_old_items(items, max_age_days=14)
        assert len(result) == 1

    def test_boundary_just_outside_cutoff_pruned(self):
        # One second older than cutoff should be removed
        just_outside = (datetime.now() - timedelta(days=14) - timedelta(seconds=1)).isoformat()
        items = [{"url": "https://edge.com", "published": just_outside}]
        result = prune_old_items(items, max_age_days=14)
        assert len(result) == 0

    def test_empty_list_returns_empty(self):
        assert prune_old_items([], max_age_days=14) == []

    def test_mixed_old_and_new(self):
        now = datetime.now().isoformat()
        old = (datetime.now() - timedelta(days=30)).isoformat()
        items = [
            {"url": "https://new.com", "published": now},
            {"url": "https://old.com", "published": old},
            {"url": "https://no-date.com"},
        ]
        result = prune_old_items(items, max_age_days=14)
        assert len(result) == 2  # new + no-date kept
        urls = [i["url"] for i in result]
        assert "https://old.com" not in urls

    def test_custom_max_age(self):
        three_days_ago = (datetime.now() - timedelta(days=3)).isoformat()
        items = [{"url": "https://a.com", "published": three_days_ago}]
        # With 2-day max age, this should be pruned
        result = prune_old_items(items, max_age_days=2)
        assert len(result) == 0
        # With 5-day max age, this should be kept
        result = prune_old_items(items, max_age_days=5)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# TestMergeNewsItems
# ---------------------------------------------------------------------------

class TestMergeNewsItems:
    """Tests for merge_news_items — deduplication and ordering."""

    def test_new_items_added(self):
        existing = [{"url": "https://old.com", "published": "2025-01-01T00:00:00"}]
        new_items = [{"url": "https://new.com", "published": "2025-01-02T00:00:00"}]
        result = merge_news_items(existing, new_items)
        assert len(result) == 2

    def test_duplicate_urls_not_added(self):
        existing = [{"url": "https://same.com", "published": "2025-01-01T00:00:00"}]
        new_items = [{"url": "https://same.com", "published": "2025-01-01T00:00:00"}]
        result = merge_news_items(existing, new_items)
        assert len(result) == 1

    def test_sorted_by_published_date_descending(self):
        existing = [{"url": "https://old.com", "published": "2025-01-01T00:00:00"}]
        new_items = [{"url": "https://new.com", "published": "2025-01-03T00:00:00"}]
        result = merge_news_items(existing, new_items)
        assert result[0]["url"] == "https://new.com"
        assert result[1]["url"] == "https://old.com"

    def test_empty_existing_list(self):
        new_items = [{"url": "https://a.com", "published": "2025-01-01T00:00:00"}]
        result = merge_news_items([], new_items)
        assert len(result) == 1

    def test_empty_new_items_list(self):
        existing = [{"url": "https://a.com", "published": "2025-01-01T00:00:00"}]
        result = merge_news_items(existing, [])
        assert len(result) == 1

    def test_both_empty(self):
        result = merge_news_items([], [])
        assert result == []

    def test_items_without_url_not_deduped(self):
        """Items without a URL should not match for dedup."""
        existing = [{"title": "A", "published": "2025-01-01T00:00:00"}]
        new_items = [{"title": "B", "published": "2025-01-02T00:00:00"}]
        result = merge_news_items(existing, new_items)
        assert len(result) == 2

    def test_items_without_published_sorted_last(self):
        """Items without published date should sort after dated items."""
        existing = [{"url": "https://dated.com", "published": "2025-01-01T00:00:00"}]
        new_items = [{"url": "https://no-date.com"}]
        result = merge_news_items(existing, new_items)
        # no-date uses "1970-01-01" fallback, should be last
        assert result[-1]["url"] == "https://no-date.com"

    def test_partial_overlap(self):
        existing = [
            {"url": "https://a.com", "published": "2025-01-01T00:00:00"},
            {"url": "https://b.com", "published": "2025-01-02T00:00:00"},
        ]
        new_items = [
            {"url": "https://b.com", "published": "2025-01-02T00:00:00"},  # dupe
            {"url": "https://c.com", "published": "2025-01-03T00:00:00"},  # new
        ]
        result = merge_news_items(existing, new_items)
        assert len(result) == 3
        urls = [i["url"] for i in result]
        assert urls.count("https://b.com") == 1


# ---------------------------------------------------------------------------
# TestLoadCache (news)
# ---------------------------------------------------------------------------

class TestLoadCache:
    """Tests for load_cache — news cache loading."""

    @patch("app.news_data.news_cache.CACHE_FILE")
    def test_file_not_exists_returns_none(self, mock_path):
        mock_path.exists.return_value = False
        result = load_cache()
        assert result is None

    @patch("app.news_data.news_cache.CACHE_FILE")
    def test_fresh_cache_returned(self, mock_path):
        mock_path.exists.return_value = True
        cache_data = {"cached_at": datetime.now().isoformat(), "items": []}
        with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
            result = load_cache()
        assert result is not None
        assert "items" in result

    @patch("app.news_data.news_cache.CACHE_FILE")
    def test_expired_cache_returns_none(self, mock_path):
        mock_path.exists.return_value = True
        old_time = (datetime.now() - timedelta(minutes=NEWS_CACHE_CHECK_MINUTES + 5)).isoformat()
        cache_data = {"cached_at": old_time, "items": []}
        with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
            result = load_cache()
        assert result is None

    @patch("app.news_data.news_cache.CACHE_FILE")
    def test_for_merge_returns_expired_cache(self, mock_path):
        mock_path.exists.return_value = True
        old_time = (datetime.now() - timedelta(hours=2)).isoformat()
        cache_data = {"cached_at": old_time, "items": ["old_item"]}
        with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
            result = load_cache(for_merge=True)
        assert result is not None
        assert result["items"] == ["old_item"]

    @patch("app.news_data.news_cache.CACHE_FILE")
    def test_corrupt_json_returns_none(self, mock_path):
        mock_path.exists.return_value = True
        with patch("builtins.open", mock_open(read_data="not valid json{")):
            result = load_cache()
        assert result is None

    @patch("app.news_data.news_cache.CACHE_FILE")
    def test_missing_cached_at_treated_as_expired(self, mock_path):
        mock_path.exists.return_value = True
        cache_data = {"items": []}  # No cached_at field
        with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
            result = load_cache()
        # Falls back to "2000-01-01" which is expired
        assert result is None


# ---------------------------------------------------------------------------
# TestSaveCache (news)
# ---------------------------------------------------------------------------

class TestSaveCache:
    """Tests for save_cache — news cache writing."""

    @patch("app.news_data.news_cache.CACHE_FILE", new_callable=lambda: MagicMock(spec=Path))
    def test_save_writes_json(self, mock_path):
        data = {"cached_at": datetime.now().isoformat(), "items": []}
        m = mock_open()
        with patch("builtins.open", m):
            save_cache(data)
        m.assert_called_once()
        # Verify json.dump was called (content written)
        handle = m()
        assert handle.write.called

    @patch("builtins.open", side_effect=PermissionError("No write access"))
    def test_save_handles_write_error(self, mock_file):
        """Should log error, not raise."""
        save_cache({"cached_at": datetime.now().isoformat()})
        # No exception raised


# ---------------------------------------------------------------------------
# TestLoadVideoCache
# ---------------------------------------------------------------------------

class TestLoadVideoCache:
    """Tests for load_video_cache."""

    @patch("app.news_data.news_cache.VIDEO_CACHE_FILE")
    def test_file_not_exists_returns_none(self, mock_path):
        mock_path.exists.return_value = False
        assert load_video_cache() is None

    @patch("app.news_data.news_cache.VIDEO_CACHE_FILE")
    def test_fresh_cache_returned(self, mock_path):
        mock_path.exists.return_value = True
        cache_data = {"cached_at": datetime.now().isoformat(), "videos": []}
        with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
            result = load_video_cache()
        assert result is not None

    @patch("app.news_data.news_cache.VIDEO_CACHE_FILE")
    def test_expired_returns_none(self, mock_path):
        mock_path.exists.return_value = True
        old = (datetime.now() - timedelta(minutes=NEWS_CACHE_CHECK_MINUTES + 5)).isoformat()
        cache_data = {"cached_at": old}
        with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
            result = load_video_cache()
        assert result is None

    @patch("app.news_data.news_cache.VIDEO_CACHE_FILE")
    def test_for_merge_returns_expired(self, mock_path):
        mock_path.exists.return_value = True
        old = (datetime.now() - timedelta(hours=3)).isoformat()
        cache_data = {"cached_at": old, "videos": ["v1"]}
        with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
            result = load_video_cache(for_merge=True)
        assert result is not None

    @patch("app.news_data.news_cache.VIDEO_CACHE_FILE")
    def test_corrupt_json_returns_none(self, mock_path):
        mock_path.exists.return_value = True
        with patch("builtins.open", mock_open(read_data="{")):
            result = load_video_cache()
        assert result is None


# ---------------------------------------------------------------------------
# TestSaveVideoCache
# ---------------------------------------------------------------------------

class TestSaveVideoCache:
    """Tests for save_video_cache."""

    def test_save_writes_data(self):
        m = mock_open()
        with patch("builtins.open", m):
            save_video_cache({"cached_at": datetime.now().isoformat(), "videos": []})
        m.assert_called_once()

    @patch("builtins.open", side_effect=OSError("Disk full"))
    def test_save_handles_error(self, mock_file):
        save_video_cache({"data": "test"})  # Should not raise


# ---------------------------------------------------------------------------
# TestLoadFearGreedCache
# ---------------------------------------------------------------------------

class TestLoadFearGreedCache:
    """Tests for load_fear_greed_cache."""

    @patch("app.news_data.news_cache.FEAR_GREED_CACHE_FILE")
    def test_file_not_exists(self, mock_path):
        mock_path.exists.return_value = False
        assert load_fear_greed_cache() is None

    @patch("app.news_data.news_cache.FEAR_GREED_CACHE_FILE")
    def test_fresh_cache(self, mock_path):
        mock_path.exists.return_value = True
        cache_data = {"cached_at": datetime.now().isoformat(), "value": 42}
        with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
            result = load_fear_greed_cache()
        assert result is not None
        assert result["value"] == 42

    @patch("app.news_data.news_cache.FEAR_GREED_CACHE_FILE")
    def test_expired_cache(self, mock_path):
        mock_path.exists.return_value = True
        old = (datetime.now() - timedelta(minutes=FEAR_GREED_CACHE_MINUTES + 5)).isoformat()
        cache_data = {"cached_at": old}
        with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
            result = load_fear_greed_cache()
        assert result is None


# ---------------------------------------------------------------------------
# TestLoadBlockHeightCache
# ---------------------------------------------------------------------------

class TestLoadBlockHeightCache:
    """Tests for load_block_height_cache."""

    @patch("app.news_data.news_cache.BLOCK_HEIGHT_CACHE_FILE")
    def test_file_not_exists(self, mock_path):
        mock_path.exists.return_value = False
        assert load_block_height_cache() is None

    @patch("app.news_data.news_cache.BLOCK_HEIGHT_CACHE_FILE")
    def test_fresh_cache(self, mock_path):
        mock_path.exists.return_value = True
        cache_data = {"cached_at": datetime.now().isoformat(), "height": 880000}
        with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
            result = load_block_height_cache()
        assert result is not None
        assert result["height"] == 880000

    @patch("app.news_data.news_cache.BLOCK_HEIGHT_CACHE_FILE")
    def test_expired_cache(self, mock_path):
        mock_path.exists.return_value = True
        old = (datetime.now() - timedelta(minutes=BLOCK_HEIGHT_CACHE_MINUTES + 5)).isoformat()
        cache_data = {"cached_at": old}
        with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
            result = load_block_height_cache()
        assert result is None


# ---------------------------------------------------------------------------
# TestLoadUsDebtCache
# ---------------------------------------------------------------------------

class TestLoadUsDebtCache:
    """Tests for load_us_debt_cache."""

    @patch("app.news_data.news_cache.US_DEBT_CACHE_FILE")
    def test_file_not_exists(self, mock_path):
        mock_path.exists.return_value = False
        assert load_us_debt_cache() is None

    @patch("app.news_data.news_cache.US_DEBT_CACHE_FILE")
    def test_fresh_cache(self, mock_path):
        mock_path.exists.return_value = True
        cache_data = {"cached_at": datetime.now().isoformat(), "debt": 36000000000000}
        with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
            result = load_us_debt_cache()
        assert result is not None

    @patch("app.news_data.news_cache.US_DEBT_CACHE_FILE")
    def test_expired_cache(self, mock_path):
        mock_path.exists.return_value = True
        old = (datetime.now() - timedelta(hours=US_DEBT_CACHE_HOURS + 1)).isoformat()
        cache_data = {"cached_at": old}
        with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
            result = load_us_debt_cache()
        assert result is None


# ---------------------------------------------------------------------------
# TestGenericMarketMetricsCaches
# ---------------------------------------------------------------------------

class TestGenericMarketMetricsCaches:
    """Tests for all generic market metrics load/save pairs."""

    @pytest.mark.parametrize("load_fn,save_fn,cache_file_attr", [
        (load_btc_dominance_cache, save_btc_dominance_cache, "BTC_DOMINANCE_CACHE_FILE"),
        (load_altseason_cache, save_altseason_cache, "ALTSEASON_CACHE_FILE"),
        (load_stablecoin_mcap_cache, save_stablecoin_mcap_cache, "STABLECOIN_MCAP_CACHE_FILE"),
        (load_mempool_cache, save_mempool_cache, "MEMPOOL_CACHE_FILE"),
        (load_hash_rate_cache, save_hash_rate_cache, "HASH_RATE_CACHE_FILE"),
        (load_lightning_cache, save_lightning_cache, "LIGHTNING_CACHE_FILE"),
        (load_ath_cache, save_ath_cache, "ATH_CACHE_FILE"),
        (load_btc_rsi_cache, save_btc_rsi_cache, "BTC_RSI_CACHE_FILE"),
    ])
    def test_load_file_not_exists_returns_none(self, load_fn, save_fn, cache_file_attr):
        with patch(f"app.news_data.news_cache.{cache_file_attr}") as mock_path:
            mock_path.exists.return_value = False
            assert load_fn() is None

    @pytest.mark.parametrize("load_fn,save_fn,cache_file_attr", [
        (load_btc_dominance_cache, save_btc_dominance_cache, "BTC_DOMINANCE_CACHE_FILE"),
        (load_altseason_cache, save_altseason_cache, "ALTSEASON_CACHE_FILE"),
        (load_stablecoin_mcap_cache, save_stablecoin_mcap_cache, "STABLECOIN_MCAP_CACHE_FILE"),
        (load_mempool_cache, save_mempool_cache, "MEMPOOL_CACHE_FILE"),
        (load_hash_rate_cache, save_hash_rate_cache, "HASH_RATE_CACHE_FILE"),
        (load_lightning_cache, save_lightning_cache, "LIGHTNING_CACHE_FILE"),
        (load_ath_cache, save_ath_cache, "ATH_CACHE_FILE"),
        (load_btc_rsi_cache, save_btc_rsi_cache, "BTC_RSI_CACHE_FILE"),
    ])
    def test_load_fresh_cache_returned(self, load_fn, save_fn, cache_file_attr):
        with patch(f"app.news_data.news_cache.{cache_file_attr}") as mock_path:
            mock_path.exists.return_value = True
            cache_data = {"cached_at": datetime.now().isoformat(), "value": 42}
            with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
                result = load_fn()
            assert result is not None
            assert result["value"] == 42

    @pytest.mark.parametrize("load_fn,save_fn,cache_file_attr", [
        (load_btc_dominance_cache, save_btc_dominance_cache, "BTC_DOMINANCE_CACHE_FILE"),
        (load_altseason_cache, save_altseason_cache, "ALTSEASON_CACHE_FILE"),
        (load_stablecoin_mcap_cache, save_stablecoin_mcap_cache, "STABLECOIN_MCAP_CACHE_FILE"),
        (load_mempool_cache, save_mempool_cache, "MEMPOOL_CACHE_FILE"),
        (load_hash_rate_cache, save_hash_rate_cache, "HASH_RATE_CACHE_FILE"),
        (load_lightning_cache, save_lightning_cache, "LIGHTNING_CACHE_FILE"),
        (load_ath_cache, save_ath_cache, "ATH_CACHE_FILE"),
        (load_btc_rsi_cache, save_btc_rsi_cache, "BTC_RSI_CACHE_FILE"),
    ])
    def test_load_expired_returns_none(self, load_fn, save_fn, cache_file_attr):
        with patch(f"app.news_data.news_cache.{cache_file_attr}") as mock_path:
            mock_path.exists.return_value = True
            old = (datetime.now() - timedelta(minutes=MARKET_METRICS_CACHE_MINUTES + 5)).isoformat()
            cache_data = {"cached_at": old}
            with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
                result = load_fn()
            assert result is None

    @pytest.mark.parametrize("save_fn", [
        save_btc_dominance_cache,
        save_altseason_cache,
        save_stablecoin_mcap_cache,
        save_mempool_cache,
        save_hash_rate_cache,
        save_lightning_cache,
        save_ath_cache,
        save_btc_rsi_cache,
    ])
    def test_save_writes_data(self, save_fn):
        m = mock_open()
        with patch("builtins.open", m):
            save_fn({"cached_at": datetime.now().isoformat(), "value": 99})
        m.assert_called_once()

    @pytest.mark.parametrize("save_fn", [
        save_btc_dominance_cache,
        save_altseason_cache,
    ])
    def test_save_handles_write_error(self, save_fn):
        with patch("builtins.open", side_effect=PermissionError("No access")):
            save_fn({"data": "test"})  # Should not raise


# ---------------------------------------------------------------------------
# TestSaveFearGreedCache
# ---------------------------------------------------------------------------

class TestSaveFearGreedCache:
    """Tests for save_fear_greed_cache."""

    def test_save_writes(self):
        m = mock_open()
        with patch("builtins.open", m):
            save_fear_greed_cache({"cached_at": datetime.now().isoformat(), "value": 50})
        m.assert_called_once()


# ---------------------------------------------------------------------------
# TestSaveBlockHeightCache
# ---------------------------------------------------------------------------

class TestSaveBlockHeightCache:
    """Tests for save_block_height_cache."""

    def test_save_writes(self):
        m = mock_open()
        with patch("builtins.open", m):
            save_block_height_cache({"cached_at": datetime.now().isoformat(), "height": 880000})
        m.assert_called_once()


# ---------------------------------------------------------------------------
# TestSaveUsDebtCache
# ---------------------------------------------------------------------------

class TestSaveUsDebtCache:
    """Tests for save_us_debt_cache."""

    def test_save_writes(self):
        m = mock_open()
        with patch("builtins.open", m):
            save_us_debt_cache({"cached_at": datetime.now().isoformat(), "debt": 36000000000000})
        m.assert_called_once()


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    """Tests for cache timing constants."""

    def test_news_cache_check_minutes(self):
        assert NEWS_CACHE_CHECK_MINUTES == 30

    def test_news_item_max_age_days(self):
        assert NEWS_ITEM_MAX_AGE_DAYS == 14

    def test_fear_greed_cache_minutes(self):
        assert FEAR_GREED_CACHE_MINUTES == 60

    def test_block_height_cache_minutes(self):
        assert BLOCK_HEIGHT_CACHE_MINUTES == 10

    def test_us_debt_cache_hours(self):
        assert US_DEBT_CACHE_HOURS == 24

    def test_market_metrics_cache_minutes(self):
        assert MARKET_METRICS_CACHE_MINUTES == 15
