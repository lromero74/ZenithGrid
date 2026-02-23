"""
Tests for backend/app/services/portfolio_service.py

Covers:
- get_cex_portfolio: Coinbase portfolio breakdown, PnL, balance breakdown
- get_dex_portfolio: DEX wallet portfolio with fallback pricing
- get_generic_cex_portfolio: ByBit/MT5 portfolio from exchange balances
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# get_cex_portfolio
# ---------------------------------------------------------------------------


class TestGetCexPortfolio:
    """Tests for get_cex_portfolio()."""

    @pytest.mark.asyncio
    async def test_happy_path_with_spot_positions(self, db_session):
        """Happy path: builds portfolio from Coinbase breakdown with holdings."""
        from app.services.portfolio_service import get_cex_portfolio

        account = MagicMock()
        account.id = 1
        account.user_id = 10
        account.name = "Main CEX"

        coinbase = AsyncMock()
        coinbase.get_portfolio_breakdown.return_value = {
            "spot_positions": [
                {
                    "asset": "BTC",
                    "total_balance_crypto": "0.5",
                    "available_to_trade_crypto": "0.4",
                    "total_balance_fiat": "50000",
                },
                {
                    "asset": "USD",
                    "total_balance_crypto": "1000",
                    "available_to_trade_crypto": "1000",
                    "total_balance_fiat": "0",
                },
            ]
        }
        coinbase.get_btc_usd_price.return_value = 100000.0

        get_coinbase_func = AsyncMock(return_value=coinbase)

        # Patch both caches to avoid real cache usage
        with patch("app.services.portfolio_service.api_cache") as mock_api_cache, \
             patch("app.services.portfolio_service.portfolio_cache") as mock_portfolio_cache:
            mock_api_cache.get = AsyncMock(return_value=None)
            mock_api_cache.set = AsyncMock()
            mock_portfolio_cache.get = AsyncMock(return_value=None)
            mock_portfolio_cache.save = AsyncMock()

            result = await get_cex_portfolio(
                account=account,
                db=db_session,
                get_coinbase_for_account_func=get_coinbase_func,
                force_fresh=True,
            )

        assert result["account_id"] == 1
        assert result["account_name"] == "Main CEX"
        assert result["account_type"] == "cex"
        assert result["is_dex"] is False
        assert result["btc_usd_price"] == 100000.0
        assert result["total_usd_value"] > 0
        assert len(result["holdings"]) >= 1
        assert "balance_breakdown" in result
        assert "pnl" in result

    @pytest.mark.asyncio
    async def test_returns_cached_result_when_available(self, db_session):
        """Edge case: returns in-memory cached result without calling exchange."""
        from app.services.portfolio_service import get_cex_portfolio

        account = MagicMock()
        account.id = 2
        account.user_id = 20

        cached_data = {"total_usd_value": 5000, "cached": True}
        get_coinbase_func = AsyncMock()

        with patch("app.services.portfolio_service.api_cache") as mock_api_cache:
            mock_api_cache.get = AsyncMock(return_value=cached_data)

            result = await get_cex_portfolio(
                account=account,
                db=db_session,
                get_coinbase_for_account_func=get_coinbase_func,
                force_fresh=False,
            )

        assert result == cached_data
        get_coinbase_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_persistent_cache_when_api_cache_empty(self, db_session):
        """Edge case: falls back to persistent cache when in-memory is empty."""
        from app.services.portfolio_service import get_cex_portfolio

        account = MagicMock()
        account.id = 3
        account.user_id = 30

        persistent_data = {"total_usd_value": 8000, "persistent": True}
        get_coinbase_func = AsyncMock()

        with patch("app.services.portfolio_service.api_cache") as mock_api_cache, \
             patch("app.services.portfolio_service.portfolio_cache") as mock_portfolio_cache:
            mock_api_cache.get = AsyncMock(return_value=None)
            mock_api_cache.set = AsyncMock()
            mock_portfolio_cache.get = AsyncMock(return_value=persistent_data)

            result = await get_cex_portfolio(
                account=account,
                db=db_session,
                get_coinbase_for_account_func=get_coinbase_func,
                force_fresh=False,
            )

        assert result == persistent_data
        get_coinbase_func.assert_not_called()
        mock_api_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_dust_below_one_cent(self, db_session):
        """Edge case: holdings with < $0.01 usd_value are filtered out."""
        from app.services.portfolio_service import get_cex_portfolio

        account = MagicMock()
        account.id = 4
        account.user_id = 40
        account.name = "Dust Test"

        coinbase = AsyncMock()
        coinbase.get_portfolio_breakdown.return_value = {
            "spot_positions": [
                {
                    "asset": "SHIB",
                    "total_balance_crypto": "100",
                    "available_to_trade_crypto": "100",
                    "total_balance_fiat": "0.005",
                },
                {
                    "asset": "BTC",
                    "total_balance_crypto": "0.1",
                    "available_to_trade_crypto": "0.1",
                    "total_balance_fiat": "10000",
                },
            ]
        }
        coinbase.get_btc_usd_price.return_value = 100000.0
        get_coinbase_func = AsyncMock(return_value=coinbase)

        with patch("app.services.portfolio_service.api_cache") as mock_api_cache, \
             patch("app.services.portfolio_service.portfolio_cache") as mock_portfolio_cache:
            mock_api_cache.get = AsyncMock(return_value=None)
            mock_api_cache.set = AsyncMock()
            mock_portfolio_cache.get = AsyncMock(return_value=None)
            mock_portfolio_cache.save = AsyncMock()

            result = await get_cex_portfolio(
                account=account,
                db=db_session,
                get_coinbase_for_account_func=get_coinbase_func,
                force_fresh=True,
            )

        # SHIB should be filtered out as dust
        assets = [h["asset"] for h in result["holdings"]]
        assert "SHIB" not in assets
        assert "BTC" in assets

    @pytest.mark.asyncio
    async def test_zero_balance_positions_are_skipped(self, db_session):
        """Edge case: positions with total_balance == 0 are skipped."""
        from app.services.portfolio_service import get_cex_portfolio

        account = MagicMock()
        account.id = 5
        account.user_id = 50
        account.name = "Zero Test"

        coinbase = AsyncMock()
        coinbase.get_portfolio_breakdown.return_value = {
            "spot_positions": [
                {
                    "asset": "EMPTY",
                    "total_balance_crypto": "0",
                    "available_to_trade_crypto": "0",
                    "total_balance_fiat": "0",
                },
            ]
        }
        coinbase.get_btc_usd_price.return_value = 100000.0
        get_coinbase_func = AsyncMock(return_value=coinbase)

        with patch("app.services.portfolio_service.api_cache") as mock_api_cache, \
             patch("app.services.portfolio_service.portfolio_cache") as mock_portfolio_cache:
            mock_api_cache.get = AsyncMock(return_value=None)
            mock_api_cache.set = AsyncMock()
            mock_portfolio_cache.get = AsyncMock(return_value=None)
            mock_portfolio_cache.save = AsyncMock()

            result = await get_cex_portfolio(
                account=account,
                db=db_session,
                get_coinbase_for_account_func=get_coinbase_func,
                force_fresh=True,
            )

        assert result["holdings"] == []
        assert result["total_usd_value"] == 0.0

    @pytest.mark.asyncio
    async def test_usd_and_usdc_use_price_one(self, db_session):
        """USD and USDC positions derive price as 1.0."""
        from app.services.portfolio_service import get_cex_portfolio

        account = MagicMock()
        account.id = 6
        account.user_id = 60
        account.name = "Stablecoin Test"

        coinbase = AsyncMock()
        coinbase.get_portfolio_breakdown.return_value = {
            "spot_positions": [
                {
                    "asset": "USDC",
                    "total_balance_crypto": "500",
                    "available_to_trade_crypto": "500",
                    "total_balance_fiat": "0",
                },
            ]
        }
        coinbase.get_btc_usd_price.return_value = 100000.0
        get_coinbase_func = AsyncMock(return_value=coinbase)

        with patch("app.services.portfolio_service.api_cache") as mock_api_cache, \
             patch("app.services.portfolio_service.portfolio_cache") as mock_portfolio_cache:
            mock_api_cache.get = AsyncMock(return_value=None)
            mock_api_cache.set = AsyncMock()
            mock_portfolio_cache.get = AsyncMock(return_value=None)
            mock_portfolio_cache.save = AsyncMock()

            result = await get_cex_portfolio(
                account=account,
                db=db_session,
                get_coinbase_for_account_func=get_coinbase_func,
                force_fresh=True,
            )

        usdc_holding = next(h for h in result["holdings"] if h["asset"] == "USDC")
        assert usdc_holding["current_price_usd"] == pytest.approx(1.0)
        assert usdc_holding["usd_value"] == pytest.approx(500.0)


# ---------------------------------------------------------------------------
# get_dex_portfolio
# ---------------------------------------------------------------------------


class TestGetDexPortfolio:
    """Tests for get_dex_portfolio()."""

    @pytest.mark.asyncio
    async def test_happy_path_with_wallet_balance(self, db_session):
        """Happy path: fetches DEX wallet portfolio with ETH balance."""
        from app.services.portfolio_service import get_dex_portfolio
        from app.models import Account

        # Create a CEX account in db for price lookup
        cex_account = Account(
            id=100,
            user_id=10,
            name="CEX for prices",
            type="cex",
            is_active=True,
            is_default=True,
            api_key_name="key",
            api_private_key="secret",
        )
        db_session.add(cex_account)
        await db_session.flush()

        dex_account = MagicMock()
        dex_account.id = 200
        dex_account.user_id = 10
        dex_account.name = "DEX Wallet"
        dex_account.chain_id = 1
        dex_account.wallet_address = "0x1234567890abcdef"
        dex_account.rpc_url = None

        coinbase = AsyncMock()
        coinbase.get_current_price.return_value = 3500.0
        coinbase.get_btc_usd_price.return_value = 100000.0
        get_coinbase_func = AsyncMock(return_value=coinbase)

        mock_portfolio = MagicMock()
        mock_portfolio.native_balance = Decimal("1.5")
        mock_portfolio.error = None

        mock_formatted = {
            "total_usd_value": 5250.0,
            "total_btc_value": 0.0525,
            "holdings": [{"asset": "ETH", "usd_value": 5250.0}],
            "holdings_count": 1,
            "is_dex": True,
        }

        with patch("app.services.portfolio_service.dex_wallet_service") as mock_dex:
            mock_dex.get_wallet_portfolio = AsyncMock(return_value=mock_portfolio)
            mock_dex.format_portfolio_for_api = AsyncMock(return_value=mock_formatted)

            result = await get_dex_portfolio(
                account=dex_account,
                db=db_session,
                get_coinbase_for_account_func=get_coinbase_func,
            )

        assert result["account_id"] == 200
        assert result["account_name"] == "DEX Wallet"
        assert result["account_type"] == "dex"
        assert result["is_dex"] is True
        assert "pnl" in result
        assert "balance_breakdown" in result
        assert result["balance_breakdown"]["eth"]["total"] == float(Decimal("1.5"))

    @pytest.mark.asyncio
    async def test_fallback_prices_when_no_cex_account(self, db_session):
        """Edge case: uses fallback prices when no CEX account is available."""
        from app.services.portfolio_service import get_dex_portfolio

        dex_account = MagicMock()
        dex_account.id = 201
        dex_account.user_id = 999  # No CEX account for this user
        dex_account.name = "DEX No CEX"
        dex_account.chain_id = 1
        dex_account.wallet_address = "0xdeadbeef"
        dex_account.rpc_url = None

        get_coinbase_func = AsyncMock(side_effect=Exception("no cex"))

        mock_portfolio = MagicMock()
        mock_portfolio.native_balance = Decimal("2.0")
        mock_portfolio.error = None

        mock_formatted = {
            "total_usd_value": 7000.0,
            "total_btc_value": 0.07,
            "holdings": [],
            "holdings_count": 0,
            "is_dex": True,
        }

        with patch("app.services.portfolio_service.dex_wallet_service") as mock_dex:
            mock_dex.get_wallet_portfolio = AsyncMock(return_value=mock_portfolio)
            mock_dex.format_portfolio_for_api = AsyncMock(return_value=mock_formatted)

            result = await get_dex_portfolio(
                account=dex_account,
                db=db_session,
                get_coinbase_for_account_func=get_coinbase_func,
            )

        # Should still return a result using fallback prices
        assert result["account_type"] == "dex"
        # format_portfolio_for_api was called (with fallback prices)
        mock_dex.format_portfolio_for_api.assert_called_once()

    @pytest.mark.asyncio
    async def test_wallet_error_is_logged(self, db_session):
        """Failure: portfolio returns error but function still completes."""
        from app.services.portfolio_service import get_dex_portfolio

        dex_account = MagicMock()
        dex_account.id = 202
        dex_account.user_id = 888
        dex_account.name = "Error Wallet"
        dex_account.chain_id = 1
        dex_account.wallet_address = "0xfail"
        dex_account.rpc_url = None

        get_coinbase_func = AsyncMock(side_effect=Exception("no cex"))

        mock_portfolio = MagicMock()
        mock_portfolio.native_balance = Decimal("0")
        mock_portfolio.error = "RPC connection failed"

        mock_formatted = {
            "total_usd_value": 0.0,
            "total_btc_value": 0.0,
            "holdings": [],
            "holdings_count": 0,
            "is_dex": True,
        }

        with patch("app.services.portfolio_service.dex_wallet_service") as mock_dex:
            mock_dex.get_wallet_portfolio = AsyncMock(return_value=mock_portfolio)
            mock_dex.format_portfolio_for_api = AsyncMock(return_value=mock_formatted)

            result = await get_dex_portfolio(
                account=dex_account,
                db=db_session,
                get_coinbase_for_account_func=get_coinbase_func,
            )

        assert result["account_type"] == "dex"
        assert result["total_usd_value"] == 0.0


# ---------------------------------------------------------------------------
# get_generic_cex_portfolio
# ---------------------------------------------------------------------------


class TestGetGenericCexPortfolio:
    """Tests for get_generic_cex_portfolio() (ByBit, MT5)."""

    @pytest.mark.asyncio
    async def test_happy_path_with_balances(self, db_session):
        """Happy path: builds portfolio from exchange get_accounts()."""
        from app.services.portfolio_service import get_generic_cex_portfolio

        account = MagicMock()
        account.id = 300
        account.name = "ByBit Account"

        mock_exchange = AsyncMock()
        mock_exchange.get_accounts.return_value = [
            {
                "currency": "USDT",
                "available_balance": {"value": "5000"},
                "hold": {"value": "100"},
            },
            {
                "currency": "BTC",
                "available_balance": {"value": "0.1"},
                "hold": {"value": "0.0"},
            },
        ]
        mock_exchange.get_btc_usd_price.return_value = 100000.0
        mock_exchange.get_equity.side_effect = Exception("not supported")

        with patch(
            "app.services.exchange_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=mock_exchange,
        ):
            result = await get_generic_cex_portfolio(account=account, db=db_session)

        assert result["account_id"] == 300
        assert result["account_name"] == "ByBit Account"
        assert result["is_dex"] is False
        assert result["total_usd_value"] > 0
        assert len(result["holdings"]) == 2

        # USDT should be valued at $1 each
        usdt_holding = next(h for h in result["holdings"] if h["asset"] == "USDT")
        assert usdt_holding["usd_value"] == pytest.approx(5100.0)

        # BTC should be valued at btc_usd_price
        btc_holding = next(h for h in result["holdings"] if h["asset"] == "BTC")
        assert btc_holding["usd_value"] == pytest.approx(10000.0)

    @pytest.mark.asyncio
    async def test_no_exchange_client_raises_503(self, db_session):
        """Failure: raises HTTPException 503 when exchange client unavailable."""
        from app.services.portfolio_service import get_generic_cex_portfolio
        from fastapi import HTTPException

        account = MagicMock()
        account.id = 301

        with patch(
            "app.services.exchange_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_generic_cex_portfolio(account=account, db=db_session)

            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_exchange_balance_fetch_failure_raises_503(self, db_session):
        """Failure: raises HTTPException 503 when balance fetch fails."""
        from app.services.portfolio_service import get_generic_cex_portfolio
        from fastapi import HTTPException

        account = MagicMock()
        account.id = 302

        mock_exchange = AsyncMock()
        mock_exchange.get_accounts.side_effect = Exception("API error")

        with patch(
            "app.services.exchange_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=mock_exchange,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_generic_cex_portfolio(account=account, db=db_session)

            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_skips_micro_balance_coins(self, db_session):
        """Edge case: coins with balance < 0.000001 are skipped."""
        from app.services.portfolio_service import get_generic_cex_portfolio

        account = MagicMock()
        account.id = 303
        account.name = "Micro Test"

        mock_exchange = AsyncMock()
        mock_exchange.get_accounts.return_value = [
            {
                "currency": "DUST",
                "available_balance": {"value": "0.0000001"},
                "hold": {"value": "0"},
            },
        ]
        mock_exchange.get_btc_usd_price.return_value = 100000.0
        mock_exchange.get_equity.side_effect = Exception("not supported")

        with patch(
            "app.services.exchange_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=mock_exchange,
        ):
            result = await get_generic_cex_portfolio(account=account, db=db_session)

        assert result["holdings"] == []

    @pytest.mark.asyncio
    async def test_equity_adjusts_total_value(self, db_session):
        """Edge case: if exchange equity > sum of balances, total is adjusted."""
        from app.services.portfolio_service import get_generic_cex_portfolio

        account = MagicMock()
        account.id = 304
        account.name = "Equity Test"

        mock_exchange = AsyncMock()
        mock_exchange.get_accounts.return_value = [
            {
                "currency": "USDT",
                "available_balance": {"value": "1000"},
                "hold": {"value": "0"},
            },
        ]
        mock_exchange.get_btc_usd_price.return_value = 100000.0
        # Equity includes unrealized PnL
        mock_exchange.get_equity.return_value = 1500.0

        with patch(
            "app.services.exchange_service.get_exchange_client_for_account",
            new_callable=AsyncMock,
            return_value=mock_exchange,
        ):
            result = await get_generic_cex_portfolio(account=account, db=db_session)

        assert result["total_usd_value"] == pytest.approx(1500.0)
        # First holding should have the unrealized PnL
        assert result["holdings"][0]["unrealized_pnl_usd"] == pytest.approx(500.0)
