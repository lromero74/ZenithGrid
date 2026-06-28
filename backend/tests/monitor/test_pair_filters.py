"""Tests for app/monitor/pair_filters.py — coin-category pair filtering."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.monitor.pair_filters import filter_pairs_by_allowed_categories


# ===========================================================================
# Class: TestFilterPairsByCategoriesAdvanced
# ===========================================================================


class TestFilterPairsByCategoriesAdvanced:
    """Additional category filter tests covering user override precedence."""

    @pytest.mark.asyncio
    async def test_user_override_takes_precedence(self, db_session):
        """User override's category wins over the global entry's category."""
        pairs = ["DOGE-BTC"]

        # Global entry: MEME (should be filtered out under APPROVED-only allow)
        # User override: APPROVED (should be allowed)
        mock_global = MagicMock()
        mock_global.symbol = "DOGE"
        mock_global.reason = "[MEME] meme coin"
        mock_global.user_id = None

        mock_override = MagicMock()
        mock_override.symbol = "DOGE"
        mock_override.reason = "[APPROVED] I like it"
        mock_override.user_id = 42

        # First call returns global entries, second call returns overrides
        call_count = {"n": 0}

        def execute_side_effect(query):
            call_count["n"] += 1
            mock_result = MagicMock()
            if call_count["n"] == 1:
                mock_result.scalars.return_value.all.return_value = [mock_global]
            else:
                mock_result.scalars.return_value.all.return_value = [mock_override]
            return mock_result

        db_session.execute = AsyncMock(side_effect=execute_side_effect)

        result = await filter_pairs_by_allowed_categories(
            db_session, pairs, ["APPROVED"], user_id=42,
        )
        assert "DOGE-BTC" in result


# ===========================================================================
# Class: TestFilterPairsByAllowedCategories
# ===========================================================================


class TestFilterPairsByAllowedCategories:
    """Tests for filter_pairs_by_allowed_categories()."""

    @pytest.mark.asyncio
    async def test_no_categories_returns_all(self, db_session):
        pairs = ["ETH-BTC", "SOL-BTC"]
        result = await filter_pairs_by_allowed_categories(db_session, pairs, None)
        assert result == pairs

    @pytest.mark.asyncio
    async def test_empty_categories_returns_all(self, db_session):
        pairs = ["ETH-BTC", "SOL-BTC"]
        result = await filter_pairs_by_allowed_categories(db_session, pairs, [])
        assert result == pairs

    @pytest.mark.asyncio
    async def test_filters_by_category(self, db_session):
        """Pairs not in allowed categories are filtered out."""
        pairs = ["ETH-BTC", "DOGE-BTC"]

        # Create mock blacklist entries
        mock_eth = MagicMock()
        mock_eth.symbol = "ETH"
        mock_eth.reason = "[APPROVED] Solid project"
        mock_eth.user_id = None

        mock_doge = MagicMock()
        mock_doge.symbol = "DOGE"
        mock_doge.reason = "[MEME] Meme coin"
        mock_doge.user_id = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_eth, mock_doge]
        db_session.execute = AsyncMock(return_value=mock_result)

        result = await filter_pairs_by_allowed_categories(db_session, pairs, ["APPROVED"])
        assert "ETH-BTC" in result
        assert "DOGE-BTC" not in result
