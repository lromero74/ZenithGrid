"""
Tests for backend/app/coinbase_api/account_balance_api.py

Covers account listing, balance queries (BTC/ETH/USD/USDC/USDT),
cache invalidation, and aggregate value calculations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.coinbase_api.account_balance_api import (
    calculate_aggregate_btc_value,
    calculate_aggregate_quote_value,
    calculate_aggregate_usd_value,
    get_account,
    get_accounts,
    get_btc_balance,
    get_currency_balance,
    get_eth_balance,
    get_portfolio_breakdown,
    get_portfolios,
    get_usd_balance,
    get_usdc_balance,
    get_usdt_balance,
    invalidate_balance_cache,
)


@pytest.fixture(autouse=True)
async def clear_cache():
    """Clear the API cache before each test to prevent cross-test contamination."""
    from app.cache import api_cache
    await api_cache.clear()
    yield
    await api_cache.clear()


# ---------------------------------------------------------------------------
# get_accounts
# ---------------------------------------------------------------------------


class TestGetAccounts:
    """Tests for get_accounts()"""

    @pytest.mark.asyncio
    async def test_fetches_all_accounts_single_page(self):
        """Happy path: fetches accounts from a single page."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "BTC", "available_balance": {"value": "1.5"}},
                {"currency": "USD", "available_balance": {"value": "1000"}},
            ],
            "cursor": "",
        })

        result = await get_accounts(mock_request)
        assert len(result) == 2
        assert result[0]["currency"] == "BTC"
        mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_paginates_through_multiple_pages(self):
        """Happy path: follows cursor to fetch all pages."""
        page1 = {
            "accounts": [{"currency": "BTC"}],
            "cursor": "page2-cursor",
        }
        page2 = {
            "accounts": [{"currency": "ETH"}],
            "cursor": "",
        }
        mock_request = AsyncMock(side_effect=[page1, page2])

        result = await get_accounts(mock_request, force_fresh=True)
        assert len(result) == 2
        assert result[0]["currency"] == "BTC"
        assert result[1]["currency"] == "ETH"
        assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_returns_cached_result(self):
        """Edge case: returns cached accounts without hitting API."""
        mock_request = AsyncMock(return_value={
            "accounts": [{"currency": "BTC"}],
            "cursor": "",
        })

        # First call populates cache
        await get_accounts(mock_request, account_id=99)
        # Second call should use cache
        result = await get_accounts(mock_request, account_id=99)

        assert len(result) == 1
        assert mock_request.call_count == 1  # Only called once

    @pytest.mark.asyncio
    async def test_force_fresh_bypasses_cache(self):
        """Edge case: force_fresh=True bypasses cache."""
        mock_request = AsyncMock(return_value={
            "accounts": [{"currency": "BTC"}],
            "cursor": "",
        })

        await get_accounts(mock_request, account_id=88)
        await get_accounts(mock_request, force_fresh=True, account_id=88)

        assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_stops_at_max_pages(self):
        """Edge case: stops pagination at max_pages safety limit."""
        # Always return a cursor so pagination never ends naturally
        mock_request = AsyncMock(return_value={
            "accounts": [{"currency": "BTC"}],
            "cursor": "always-more",
        })

        result = await get_accounts(mock_request, force_fresh=True, account_id=77)
        # Max pages is 10, so should get 10 accounts
        assert len(result) == 10
        assert mock_request.call_count == 10

    @pytest.mark.asyncio
    async def test_empty_accounts_page_stops_pagination(self):
        """Edge case: empty accounts list stops pagination even with cursor."""
        mock_request = AsyncMock(return_value={
            "accounts": [],
            "cursor": "should-not-follow",
        })

        result = await get_accounts(mock_request, force_fresh=True, account_id=66)
        assert len(result) == 0
        assert mock_request.call_count == 1


# ---------------------------------------------------------------------------
# get_account
# ---------------------------------------------------------------------------


class TestGetAccount:
    """Tests for get_account()"""

    @pytest.mark.asyncio
    async def test_returns_account_details(self):
        """Happy path: returns nested account data."""
        mock_request = AsyncMock(return_value={
            "account": {"uuid": "abc-123", "currency": "BTC"},
        })

        result = await get_account(mock_request, "abc-123")
        assert result["uuid"] == "abc-123"

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_account_key(self):
        """Edge case: missing 'account' key returns empty dict."""
        mock_request = AsyncMock(return_value={"error": "not found"})

        result = await get_account(mock_request, "nonexistent")
        assert result == {}


# ---------------------------------------------------------------------------
# get_portfolios
# ---------------------------------------------------------------------------


class TestGetPortfolios:
    """Tests for get_portfolios()"""

    @pytest.mark.asyncio
    async def test_returns_portfolio_list(self):
        """Happy path: returns list of portfolios."""
        mock_request = AsyncMock(return_value={
            "portfolios": [{"uuid": "port-1", "name": "Default"}],
        })

        result = await get_portfolios(mock_request)
        assert len(result) == 1
        assert result[0]["uuid"] == "port-1"


# ---------------------------------------------------------------------------
# get_portfolio_breakdown
# ---------------------------------------------------------------------------


class TestGetPortfolioBreakdown:
    """Tests for get_portfolio_breakdown()"""

    @pytest.mark.asyncio
    async def test_with_explicit_uuid(self):
        """Happy path: fetches breakdown for given portfolio UUID."""
        mock_request = AsyncMock(return_value={
            "breakdown": {"spot_positions": [{"asset": "BTC"}]},
        })

        result = await get_portfolio_breakdown(mock_request, portfolio_uuid="port-1")
        assert "spot_positions" in result

    @pytest.mark.asyncio
    async def test_auto_fetches_first_portfolio(self):
        """Edge case: fetches first portfolio UUID when none provided."""
        # First call to get_portfolios, second to get breakdown
        mock_request = AsyncMock(side_effect=[
            {"portfolios": [{"uuid": "auto-port", "name": "Default"}]},
            {"breakdown": {"spot_positions": []}},
        ])

        result = await get_portfolio_breakdown(mock_request)
        assert result == {"spot_positions": []}
        assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_when_no_portfolios(self):
        """Failure: raises exception when no portfolios exist."""
        mock_request = AsyncMock(return_value={"portfolios": []})

        with pytest.raises(Exception, match="No portfolios found"):
            await get_portfolio_breakdown(mock_request)


# ---------------------------------------------------------------------------
# get_btc_balance
# ---------------------------------------------------------------------------


class TestGetBtcBalance:
    """Tests for get_btc_balance()"""

    @pytest.mark.asyncio
    async def test_cdp_uses_portfolio_breakdown(self):
        """Happy path: CDP auth uses portfolio breakdown to get BTC balance."""
        mock_request = AsyncMock(side_effect=[
            # get_portfolios response
            {"portfolios": [{"uuid": "port-1", "name": "Default"}]},
            # get_portfolio_breakdown response
            {"breakdown": {"spot_positions": [
                {"asset": "BTC", "available_to_trade_crypto": "1.25"},
                {"asset": "ETH", "available_to_trade_crypto": "10.0"},
            ]}},
        ])

        result = await get_btc_balance(mock_request, "cdp")
        assert result == 1.25

    @pytest.mark.asyncio
    async def test_cdp_falls_back_to_accounts_on_portfolio_failure(self):
        """Edge case: CDP falls back to get_accounts when portfolio endpoint fails."""
        call_count = 0

        async def mock_request(method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "portfolios" in url and call_count == 1:
                raise Exception("Portfolio endpoint failed")
            return {
                "accounts": [
                    {"currency": "BTC", "available_balance": {"value": "0.5"}},
                ],
                "cursor": "",
            }

        result = await get_btc_balance(mock_request, "cdp", account_id=10)
        assert result == 0.5

    @pytest.mark.asyncio
    async def test_hmac_uses_accounts(self):
        """Happy path: HMAC auth uses get_accounts to find BTC balance."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "USD", "available_balance": {"value": "500"}},
                {"currency": "BTC", "available_balance": {"value": "2.0"}},
            ],
            "cursor": "",
        })

        result = await get_btc_balance(mock_request, "hmac", account_id=20)
        assert result == 2.0

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_btc_account(self):
        """Edge case: returns 0.0 when no BTC account exists (HMAC)."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "USD", "available_balance": {"value": "500"}},
            ],
            "cursor": "",
        })

        result = await get_btc_balance(mock_request, "hmac", account_id=21)
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_cdp_returns_zero_when_all_methods_fail(self):
        """Failure: CDP returns 0.0 when both portfolio and accounts fail."""
        mock_request = AsyncMock(side_effect=Exception("API down"))

        result = await get_btc_balance(mock_request, "cdp", account_id=30)
        assert result == 0.0


# ---------------------------------------------------------------------------
# get_eth_balance
# ---------------------------------------------------------------------------


class TestGetEthBalance:
    """Tests for get_eth_balance()"""

    @pytest.mark.asyncio
    async def test_cdp_returns_eth_from_portfolio(self):
        """Happy path: CDP auth returns ETH from portfolio breakdown."""
        mock_request = AsyncMock(side_effect=[
            {"portfolios": [{"uuid": "port-1", "name": "Default"}]},
            {"breakdown": {"spot_positions": [
                {"asset": "ETH", "available_to_trade_crypto": "5.5"},
            ]}},
        ])

        result = await get_eth_balance(mock_request, "cdp", account_id=40)
        assert result == 5.5

    @pytest.mark.asyncio
    async def test_hmac_returns_eth_from_accounts(self):
        """Happy path: HMAC auth returns ETH from accounts list."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "ETH", "available_balance": {"value": "3.0"}},
            ],
            "cursor": "",
        })

        result = await get_eth_balance(mock_request, "hmac", account_id=41)
        assert result == 3.0

    @pytest.mark.asyncio
    async def test_cdp_returns_zero_on_failure(self):
        """Failure: CDP returns 0.0 when portfolio endpoint fails with no ETH."""
        mock_request = AsyncMock(side_effect=Exception("API error"))

        result = await get_eth_balance(mock_request, "cdp", account_id=42)
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_uses_cache_on_second_call(self):
        """Edge case: second call uses cached value."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "ETH", "available_balance": {"value": "7.0"}},
            ],
            "cursor": "",
        })

        result1 = await get_eth_balance(mock_request, "hmac", account_id=43)
        result2 = await get_eth_balance(mock_request, "hmac", account_id=43)

        assert result1 == 7.0
        assert result2 == 7.0
        # get_accounts called once (first call), second from cache
        # But get_accounts itself is also cached, so the mock may be called once total
        assert mock_request.call_count == 1


# ---------------------------------------------------------------------------
# get_usd_balance / get_usdc_balance / get_usdt_balance
# ---------------------------------------------------------------------------


class TestStablecoinBalances:
    """Tests for get_usd_balance(), get_usdc_balance(), get_usdt_balance()"""

    @pytest.mark.asyncio
    async def test_usd_balance_happy_path(self):
        """Happy path: returns USD balance from accounts."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "USD", "available_balance": {"value": "5000.50"}},
            ],
            "cursor": "",
        })

        result = await get_usd_balance(mock_request, account_id=50)
        assert result == 5000.50

    @pytest.mark.asyncio
    async def test_usdc_balance_happy_path(self):
        """Happy path: returns USDC balance from accounts."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "USDC", "available_balance": {"value": "2500.00"}},
            ],
            "cursor": "",
        })

        result = await get_usdc_balance(mock_request, account_id=51)
        assert result == 2500.0

    @pytest.mark.asyncio
    async def test_usdt_balance_happy_path(self):
        """Happy path: returns USDT balance from accounts."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "USDT", "available_balance": {"value": "800.00"}},
            ],
            "cursor": "",
        })

        result = await get_usdt_balance(mock_request, account_id=52)
        assert result == 800.0

    @pytest.mark.asyncio
    async def test_returns_zero_when_currency_not_found(self):
        """Edge case: returns 0.0 when requested currency not in accounts."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "BTC", "available_balance": {"value": "1.0"}},
            ],
            "cursor": "",
        })

        result = await get_usd_balance(mock_request, account_id=53)
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_usd_balance_cached(self):
        """Edge case: second call returns cached value."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "USD", "available_balance": {"value": "100"}},
            ],
            "cursor": "",
        })

        await get_usd_balance(mock_request, account_id=54)
        result = await get_usd_balance(mock_request, account_id=54)
        assert result == 100.0
        assert mock_request.call_count == 1


# ---------------------------------------------------------------------------
# invalidate_balance_cache
# ---------------------------------------------------------------------------


class TestInvalidateBalanceCache:
    """Tests for invalidate_balance_cache()"""

    @pytest.mark.asyncio
    async def test_invalidates_specific_account(self):
        """Happy path: clears cache for specific account_id."""
        from app.cache import api_cache

        # Seed cache
        await api_cache.set("balance_btc_5", 1.0, 60)
        await api_cache.set("balance_usd_5", 500.0, 60)
        await api_cache.set("accounts_list_5", [], 60)

        await invalidate_balance_cache(account_id=5)

        assert await api_cache.get("balance_btc_5") is None
        assert await api_cache.get("balance_usd_5") is None
        assert await api_cache.get("accounts_list_5") is None

    @pytest.mark.asyncio
    async def test_global_invalidation_clears_all(self):
        """Edge case: account_id=None clears all balance-related keys."""
        from app.cache import api_cache

        await api_cache.set("balance_btc_1", 1.0, 60)
        await api_cache.set("balance_btc_2", 2.0, 60)
        await api_cache.set("accounts_list_1", [], 60)
        await api_cache.set("aggregate_btc_1", 5.0, 60)

        await invalidate_balance_cache(account_id=None)

        assert await api_cache.get("balance_btc_1") is None
        assert await api_cache.get("balance_btc_2") is None
        assert await api_cache.get("accounts_list_1") is None
        assert await api_cache.get("aggregate_btc_1") is None

    @pytest.mark.asyncio
    async def test_invalidation_also_clears_portfolio_cache(self):
        """Edge case: portfolio response cache is also invalidated."""
        from app.cache import api_cache

        await api_cache.set("portfolio_response", {"data": "old"}, 60)
        await api_cache.set("portfolio_response_5", {"data": "old_5"}, 60)

        await invalidate_balance_cache(account_id=5)

        assert await api_cache.get("portfolio_response") is None
        assert await api_cache.get("portfolio_response_5") is None


# ---------------------------------------------------------------------------
# calculate_aggregate_btc_value
# ---------------------------------------------------------------------------


class TestCalculateAggregateBtcValue:
    """Tests for calculate_aggregate_btc_value()"""

    @pytest.mark.asyncio
    async def test_returns_available_btc_when_no_db(self):
        """Happy path: returns available BTC balance when DB lookup has no positions."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "BTC", "available_balance": {"value": "1.5"}},
            ],
            "cursor": "",
        })

        # sqlite3 is imported locally inside the function, so patch at stdlib level
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            result = await calculate_aggregate_btc_value(
                mock_request, "hmac", account_id=60, bypass_cache=True
            )

        assert result == 1.5

    @pytest.mark.asyncio
    async def test_includes_positions_with_current_prices(self):
        """Happy path: adds BTC value of open positions using current prices."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "BTC", "available_balance": {"value": "1.0"}},
            ],
            "cursor": "",
        })
        mock_price_func = AsyncMock(return_value=0.05)  # 0.05 BTC per unit

        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor_obj = MagicMock()
            # product_id, total_base_acquired, average_buy_price
            mock_cursor_obj.fetchall.return_value = [
                ("ETH-BTC", "10.0", "0.04"),
            ]
            mock_conn.cursor.return_value = mock_cursor_obj
            mock_connect.return_value = mock_conn

            result = await calculate_aggregate_btc_value(
                mock_request, "hmac",
                get_current_price_func=mock_price_func,
                account_id=61, bypass_cache=True,
            )

        # 1.0 (available) + 10.0 * 0.05 (position value) = 1.5
        assert result == pytest.approx(1.5)

    @pytest.mark.asyncio
    async def test_uses_avg_price_when_price_func_unavailable(self):
        """Edge case: falls back to average buy price when no price function."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "BTC", "available_balance": {"value": "0.5"}},
            ],
            "cursor": "",
        })

        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor_obj = MagicMock()
            mock_cursor_obj.fetchall.return_value = [
                ("ETH-BTC", "5.0", "0.03"),
            ]
            mock_conn.cursor.return_value = mock_cursor_obj
            mock_connect.return_value = mock_conn

            result = await calculate_aggregate_btc_value(
                mock_request, "hmac",
                get_current_price_func=None,
                account_id=62, bypass_cache=True,
            )

        # 0.5 + 5.0 * 0.03 = 0.65
        assert result == pytest.approx(0.65)

    @pytest.mark.asyncio
    async def test_returns_cached_value(self):
        """Edge case: returns cached aggregate value when bypass_cache=False."""
        from app.cache import api_cache
        await api_cache.set("aggregate_btc_63", 3.14, 300)

        mock_request = AsyncMock()
        result = await calculate_aggregate_btc_value(
            mock_request, "hmac", account_id=63, bypass_cache=False
        )

        assert result == 3.14
        mock_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_db_error_gracefully(self):
        """Failure: returns available BTC only when DB fails."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "BTC", "available_balance": {"value": "2.0"}},
            ],
            "cursor": "",
        })

        with patch("sqlite3.connect") as mock_connect:
            mock_connect.side_effect = Exception("DB file not found")

            result = await calculate_aggregate_btc_value(
                mock_request, "hmac", account_id=64, bypass_cache=True
            )

        assert result == 2.0


# ---------------------------------------------------------------------------
# calculate_aggregate_usd_value
# ---------------------------------------------------------------------------


class TestCalculateAggregateUsdValue:
    """Tests for calculate_aggregate_usd_value()"""

    @pytest.mark.asyncio
    async def test_sums_usd_and_btc_values(self):
        """Happy path: sums USD + BTC holdings converted to USD."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "USD", "available_balance": {"value": "1000"}},
                {"currency": "BTC", "available_balance": {"value": "0.1"}},
                {"currency": "USDC", "available_balance": {"value": "500"}},
            ],
            "cursor": "",
        })
        mock_btc_price = AsyncMock(return_value=50000.0)
        mock_price_func = AsyncMock(return_value=100.0)

        result = await calculate_aggregate_usd_value(
            mock_request, mock_btc_price, mock_price_func, account_id=70
        )

        # 1000 (USD) + 500 (USDC) + 0.1 * 50000 (BTC) = 6500
        assert result == pytest.approx(6500.0)

    @pytest.mark.asyncio
    async def test_skips_dust_btc_balances(self):
        """Edge case: skips BTC with USD value below MIN_USD_BALANCE_FOR_AGGREGATE."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "USD", "available_balance": {"value": "100"}},
                # 0.000001 BTC * 50000 = $0.05 -- below $1 threshold
                {"currency": "BTC", "available_balance": {"value": "0.000001"}},
            ],
            "cursor": "",
        })
        mock_btc_price = AsyncMock(return_value=50000.0)
        mock_price_func = AsyncMock(return_value=100.0)

        result = await calculate_aggregate_usd_value(
            mock_request, mock_btc_price, mock_price_func, account_id=71
        )

        # Only USD counts; BTC dust is skipped
        assert result == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_skips_zero_balance_accounts(self):
        """Edge case: skips accounts with zero balance."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "USD", "available_balance": {"value": "200"}},
                {"currency": "ETH", "available_balance": {"value": "0"}},
            ],
            "cursor": "",
        })
        mock_btc_price = AsyncMock(return_value=50000.0)
        mock_price_func = AsyncMock(return_value=3000.0)

        result = await calculate_aggregate_usd_value(
            mock_request, mock_btc_price, mock_price_func, account_id=72
        )

        assert result == pytest.approx(200.0)
        mock_price_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetches_usd_price_for_altcoins(self):
        """Happy path: fetches USD price for non-USD/BTC currencies."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "SOL", "available_balance": {"value": "10.0"}},
            ],
            "cursor": "",
        })
        mock_btc_price = AsyncMock(return_value=50000.0)
        mock_price_func = AsyncMock(return_value=150.0)  # SOL at $150

        result = await calculate_aggregate_usd_value(
            mock_request, mock_btc_price, mock_price_func, account_id=73
        )

        # 10 SOL * $150 = $1500
        assert result == pytest.approx(1500.0)
        mock_price_func.assert_called_with("SOL-USD")

    @pytest.mark.asyncio
    async def test_raises_on_api_failure(self):
        """Failure: raises exception when accounts API fails."""
        mock_request = AsyncMock(side_effect=Exception("API down"))
        mock_btc_price = AsyncMock(return_value=50000.0)
        mock_price_func = AsyncMock(return_value=100.0)

        with pytest.raises(Exception, match="Failed to calculate aggregate USD value"):
            await calculate_aggregate_usd_value(
                mock_request, mock_btc_price, mock_price_func, account_id=74
            )

    @pytest.mark.asyncio
    async def test_returns_cached_value(self):
        """Edge case: returns cached aggregate USD value."""
        from app.cache import api_cache
        await api_cache.set("aggregate_usd_75", 9999.99, 300)

        mock_request = AsyncMock()
        mock_btc_price = AsyncMock()
        mock_price_func = AsyncMock()

        result = await calculate_aggregate_usd_value(
            mock_request, mock_btc_price, mock_price_func, account_id=75
        )

        assert result == 9999.99
        mock_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_tiny_altcoin_dust(self):
        """Edge case: skips altcoin quantities below 0.00001 as dust."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "USD", "available_balance": {"value": "100"}},
                {"currency": "SHIB", "available_balance": {"value": "0.000001"}},  # dust
            ],
            "cursor": "",
        })
        mock_btc_price = AsyncMock(return_value=50000.0)
        mock_price_func = AsyncMock(return_value=0.00001)

        result = await calculate_aggregate_usd_value(
            mock_request, mock_btc_price, mock_price_func, account_id=76
        )

        assert result == pytest.approx(100.0)
        mock_price_func.assert_not_called()


# ---------------------------------------------------------------------------
# get_currency_balance
# ---------------------------------------------------------------------------


class TestGetCurrencyBalance:
    """Tests for get_currency_balance() — generic balance getter for any currency."""

    @pytest.mark.asyncio
    async def test_returns_usd_balance(self):
        """Happy path: returns USD balance only."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "USD", "available_balance": {"value": "5000"}},
                {"currency": "USDC", "available_balance": {"value": "3000"}},
                {"currency": "BTC", "available_balance": {"value": "1.5"}},
            ],
            "cursor": "",
        })
        result = await get_currency_balance(mock_request, "USD", account_id=100)
        assert result == pytest.approx(5000.0)

    @pytest.mark.asyncio
    async def test_returns_usdc_balance_not_usd(self):
        """Critical: USDC is separate from USD — must not return USD balance."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "USD", "available_balance": {"value": "5000"}},
                {"currency": "USDC", "available_balance": {"value": "3000"}},
            ],
            "cursor": "",
        })
        result = await get_currency_balance(mock_request, "USDC", account_id=101)
        assert result == pytest.approx(3000.0)

    @pytest.mark.asyncio
    async def test_returns_btc_balance(self):
        """Happy path: returns BTC balance."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "BTC", "available_balance": {"value": "1.5"}},
                {"currency": "USD", "available_balance": {"value": "5000"}},
            ],
            "cursor": "",
        })
        result = await get_currency_balance(mock_request, "BTC", account_id=102)
        assert result == pytest.approx(1.5)

    @pytest.mark.asyncio
    async def test_returns_zero_when_currency_not_found(self):
        """Edge case: currency not in accounts returns 0."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "USD", "available_balance": {"value": "5000"}},
            ],
            "cursor": "",
        })
        result = await get_currency_balance(mock_request, "USDT", account_id=103)
        assert result == 0.0


# ---------------------------------------------------------------------------
# calculate_aggregate_quote_value
# ---------------------------------------------------------------------------


class TestCalculateAggregateQuoteValue:
    """Tests for calculate_aggregate_quote_value() — per-quote budget allocation."""

    @pytest.mark.asyncio
    async def test_usd_only_returns_usd_balance(self):
        """Happy path: USD aggregate returns only USD, not USDC or BTC."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "USD", "available_balance": {"value": "5000"}},
                {"currency": "USDC", "available_balance": {"value": "3000"}},
                {"currency": "BTC", "available_balance": {"value": "1.5"}},
            ],
            "cursor": "",
        })
        mock_price = AsyncMock(return_value=50000.0)

        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []  # No open positions
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            result = await calculate_aggregate_quote_value(
                mock_request, "USD", mock_price,
                bypass_cache=True, account_id=200
            )

        # Only USD balance — not USDC (3000) or BTC (1.5 * 50000)
        assert result == pytest.approx(5000.0)

    @pytest.mark.asyncio
    async def test_usdc_separate_from_usd(self):
        """Critical: USDC aggregate must not include USD balance."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "USD", "available_balance": {"value": "5000"}},
                {"currency": "USDC", "available_balance": {"value": "3000"}},
            ],
            "cursor": "",
        })
        mock_price = AsyncMock(return_value=50000.0)

        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            result = await calculate_aggregate_quote_value(
                mock_request, "USDC", mock_price,
                bypass_cache=True, account_id=201
            )

        assert result == pytest.approx(3000.0)

    @pytest.mark.asyncio
    async def test_btc_includes_position_values(self):
        """Happy path: BTC aggregate includes balance + open BTC-pair positions."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "BTC", "available_balance": {"value": "1.0"}},
            ],
            "cursor": "",
        })
        # ETH-BTC price = 0.05
        mock_price = AsyncMock(return_value=0.05)

        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            # One open position: 10 ETH in ETH-BTC pair
            mock_cursor.fetchall.return_value = [
                ("ETH-BTC", 10.0, 0.04),
            ]
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            result = await calculate_aggregate_quote_value(
                mock_request, "BTC", mock_price,
                bypass_cache=True, account_id=202
            )

        # 1.0 BTC + (10 ETH * 0.05 BTC/ETH) = 1.5 BTC
        assert result == pytest.approx(1.5)

    @pytest.mark.asyncio
    async def test_uses_cache_when_available(self):
        """Edge case: returns cached value when not bypassing."""
        from app.cache import api_cache
        await api_cache.set("aggregate_quote_usd_203", 9999.0, ttl_seconds=60)

        mock_request = AsyncMock()  # Should not be called

        result = await calculate_aggregate_quote_value(
            mock_request, "USD", None,
            bypass_cache=False, account_id=203
        )

        assert result == pytest.approx(9999.0)
        mock_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_bypasses_cache_when_requested(self):
        """Edge case: bypass_cache=True fetches fresh data."""
        from app.cache import api_cache
        await api_cache.set("aggregate_quote_usd_204", 9999.0, ttl_seconds=60)

        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "USD", "available_balance": {"value": "1000"}},
            ],
            "cursor": "",
        })

        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            result = await calculate_aggregate_quote_value(
                mock_request, "USD", None,
                bypass_cache=True, account_id=204
            )

        assert result == pytest.approx(1000.0)

    @pytest.mark.asyncio
    async def test_fallback_to_avg_price_when_no_price_func(self):
        """Edge case: uses average_buy_price when no price function provided."""
        mock_request = AsyncMock(return_value={
            "accounts": [
                {"currency": "BTC", "available_balance": {"value": "0.5"}},
            ],
            "cursor": "",
        })

        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            # Position: 5 ETH at avg price 0.04 BTC
            mock_cursor.fetchall.return_value = [
                ("ETH-BTC", 5.0, 0.04),
            ]
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            result = await calculate_aggregate_quote_value(
                mock_request, "BTC", None,  # No price func
                bypass_cache=True, account_id=205
            )

        # 0.5 BTC + (5 * 0.04) = 0.7 BTC
        assert result == pytest.approx(0.7)
