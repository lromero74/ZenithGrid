"""
Tests for backend/app/services/dex_wallet_service.py

Covers:
- DexWalletService._get_native_symbol: chain ID to native token mapping
- DexWalletService._get_web3: Web3 instance creation/caching
- DexWalletService.get_native_balance: fetch native token balance
- DexWalletService.get_token_balance: fetch ERC20 token balance
- DexWalletService.get_wallet_portfolio: full portfolio fetching
- DexWalletService.fetch_token_prices: CoinGecko price fetching
- DexWalletService.format_portfolio_for_api: API response formatting
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.dex_wallet_service import (
    DEFAULT_RPC_URLS,
    DexWalletService,
    TokenBalance,
    WalletPortfolio,
)


# ---------------------------------------------------------------------------
# _get_native_symbol
# ---------------------------------------------------------------------------


class TestGetNativeSymbol:
    """Tests for DexWalletService._get_native_symbol()."""

    def test_ethereum_returns_eth(self):
        """Happy path: Ethereum mainnet returns ETH."""
        service = DexWalletService()
        assert service._get_native_symbol(1) == "ETH"

    def test_polygon_returns_matic(self):
        """Happy path: Polygon returns MATIC."""
        service = DexWalletService()
        assert service._get_native_symbol(137) == "MATIC"

    def test_arbitrum_returns_eth(self):
        """Edge case: Arbitrum uses ETH as native token."""
        service = DexWalletService()
        assert service._get_native_symbol(42161) == "ETH"

    def test_base_returns_eth(self):
        """Edge case: Base uses ETH as native token."""
        service = DexWalletService()
        assert service._get_native_symbol(8453) == "ETH"

    def test_unknown_chain_defaults_to_eth(self):
        """Edge case: unknown chain ID defaults to ETH."""
        service = DexWalletService()
        assert service._get_native_symbol(99999) == "ETH"

    def test_bsc_returns_bnb(self):
        """Happy path: BSC (chain 56) returns BNB."""
        service = DexWalletService()
        assert service._get_native_symbol(56) == "BNB"


# ---------------------------------------------------------------------------
# _get_web3
# ---------------------------------------------------------------------------


class TestGetWeb3:
    """Tests for DexWalletService._get_web3()."""

    def test_creates_web3_with_custom_rpc(self):
        """Happy path: creates Web3 instance with custom RPC URL."""
        service = DexWalletService()

        with patch("app.services.dex_wallet_service.Web3") as MockWeb3:
            MockWeb3.HTTPProvider.return_value = MagicMock()
            MockWeb3.return_value = MagicMock()

            service._get_web3(1, "https://custom-rpc.com")

        MockWeb3.HTTPProvider.assert_called_once_with("https://custom-rpc.com")

    def test_caches_web3_instances(self):
        """Edge case: subsequent calls return cached instance."""
        service = DexWalletService()

        with patch("app.services.dex_wallet_service.Web3") as MockWeb3:
            MockWeb3.HTTPProvider.return_value = MagicMock()
            mock_w3 = MagicMock()
            MockWeb3.return_value = mock_w3

            w3_first = service._get_web3(1, "https://custom-rpc.com")
            w3_second = service._get_web3(1, "https://custom-rpc.com")

        assert w3_first is w3_second
        # Web3 constructor called only once
        assert MockWeb3.call_count == 1

    def test_uses_default_rpc_when_none_provided(self):
        """Happy path: uses DEFAULT_RPC_URLS when no custom RPC given."""
        service = DexWalletService()

        with patch("app.services.dex_wallet_service.Web3") as MockWeb3:
            MockWeb3.HTTPProvider.return_value = MagicMock()
            MockWeb3.return_value = MagicMock()

            service._get_web3(1)

        MockWeb3.HTTPProvider.assert_called_once_with(DEFAULT_RPC_URLS[1])

    def test_raises_for_unknown_chain_without_rpc(self):
        """Failure: unknown chain with no default RPC raises ValueError."""
        service = DexWalletService()

        with pytest.raises(ValueError, match="No RPC URL"):
            service._get_web3(99999)


# ---------------------------------------------------------------------------
# get_native_balance
# ---------------------------------------------------------------------------


class TestGetNativeBalance:
    """Tests for DexWalletService.get_native_balance()."""

    @pytest.mark.asyncio
    async def test_returns_balance_as_decimal(self):
        """Happy path: returns native balance in ether units."""
        service = DexWalletService()

        mock_w3 = MagicMock()
        mock_w3.eth.get_balance.return_value = 1_500_000_000_000_000_000  # 1.5 ETH in wei
        mock_w3.from_wei.return_value = Decimal("1.5")

        with patch.object(service, "_get_web3", return_value=mock_w3), \
             patch("app.services.dex_wallet_service.Web3") as MockWeb3:
            MockWeb3.to_checksum_address.return_value = "0xChecksum"

            result = await service.get_native_balance(
                chain_id=1, wallet_address="0xabc123"
            )

        assert result == Decimal("1.5")

    @pytest.mark.asyncio
    async def test_returns_zero_on_error(self):
        """Failure: returns Decimal(0) when RPC call fails."""
        service = DexWalletService()

        with patch.object(service, "_get_web3", side_effect=Exception("RPC down")):
            result = await service.get_native_balance(
                chain_id=1, wallet_address="0xfail"
            )

        assert result == Decimal("0")


# ---------------------------------------------------------------------------
# get_token_balance
# ---------------------------------------------------------------------------


class TestGetTokenBalance:
    """Tests for DexWalletService.get_token_balance()."""

    @pytest.mark.asyncio
    async def test_returns_token_balance(self):
        """Happy path: returns TokenBalance for non-zero balance."""
        service = DexWalletService()

        mock_contract = MagicMock()
        mock_contract.functions.balanceOf.return_value.call.return_value = 1000000  # 1 USDC (6 decimals)
        mock_contract.functions.decimals.return_value.call.return_value = 6
        mock_contract.functions.symbol.return_value.call.return_value = "USDC"

        mock_w3 = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract

        with patch.object(service, "_get_web3", return_value=mock_w3), \
             patch("app.services.dex_wallet_service.Web3") as MockWeb3:
            MockWeb3.to_checksum_address.side_effect = lambda x: x

            result = await service.get_token_balance(
                chain_id=1,
                wallet_address="0xwallet",
                token_address="0xUSDC",
            )

        assert result is not None
        assert result.symbol == "USDC"
        assert result.balance == Decimal("1")
        assert result.decimals == 6
        assert result.raw_balance == 1000000

    @pytest.mark.asyncio
    async def test_returns_none_for_zero_balance(self):
        """Edge case: returns None when token balance is 0."""
        service = DexWalletService()

        mock_contract = MagicMock()
        mock_contract.functions.balanceOf.return_value.call.return_value = 0
        mock_contract.functions.decimals.return_value.call.return_value = 18
        mock_contract.functions.symbol.return_value.call.return_value = "DEAD"

        mock_w3 = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract

        with patch.object(service, "_get_web3", return_value=mock_w3), \
             patch("app.services.dex_wallet_service.Web3") as MockWeb3:
            MockWeb3.to_checksum_address.side_effect = lambda x: x

            result = await service.get_token_balance(
                chain_id=1,
                wallet_address="0xwallet",
                token_address="0xDEAD",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_contract_error(self):
        """Failure: returns None when contract call fails."""
        service = DexWalletService()

        with patch.object(service, "_get_web3", side_effect=Exception("bad contract")):
            result = await service.get_token_balance(
                chain_id=1,
                wallet_address="0xwallet",
                token_address="0xBAD",
            )

        assert result is None


# ---------------------------------------------------------------------------
# get_wallet_portfolio
# ---------------------------------------------------------------------------


class TestGetWalletPortfolio:
    """Tests for DexWalletService.get_wallet_portfolio()."""

    @pytest.mark.asyncio
    async def test_returns_portfolio_with_native_and_tokens(self):
        """Happy path: returns WalletPortfolio with native + token balances."""
        service = DexWalletService()

        token = TokenBalance(
            symbol="USDC",
            address="0xUSDC",
            balance=Decimal("500"),
            decimals=6,
            raw_balance=500000000,
        )

        with patch.object(service, "get_native_balance", new_callable=AsyncMock, return_value=Decimal("2.5")), \
             patch.object(service, "get_token_balance", new_callable=AsyncMock, return_value=token), \
             patch("app.services.dex_wallet_service.asyncio") as mock_asyncio:
            mock_asyncio.sleep = AsyncMock()

            result = await service.get_wallet_portfolio(
                chain_id=1,
                wallet_address="0xwallet",
                include_tokens=True,
            )

        assert isinstance(result, WalletPortfolio)
        assert result.chain_id == 1
        assert result.wallet_address == "0xwallet"
        assert result.native_balance == Decimal("2.5")
        assert result.native_symbol == "ETH"
        assert result.error is None
        assert len(result.token_balances) > 0

    @pytest.mark.asyncio
    async def test_returns_portfolio_without_tokens(self):
        """Edge case: include_tokens=False skips token fetching."""
        service = DexWalletService()

        with patch.object(service, "get_native_balance", new_callable=AsyncMock, return_value=Decimal("1.0")):
            result = await service.get_wallet_portfolio(
                chain_id=1,
                wallet_address="0xwallet",
                include_tokens=False,
            )

        assert result.token_balances == []
        assert result.native_balance == Decimal("1.0")

    @pytest.mark.asyncio
    async def test_returns_error_portfolio_on_failure(self):
        """Failure: returns portfolio with error message on exception."""
        service = DexWalletService()

        with patch.object(
            service, "get_native_balance", new_callable=AsyncMock,
            side_effect=Exception("RPC timeout")
        ):
            result = await service.get_wallet_portfolio(
                chain_id=1,
                wallet_address="0xfail",
            )

        assert result.error is not None
        assert "RPC timeout" in result.error
        assert result.native_balance == Decimal("0")
        assert result.token_balances == []


# ---------------------------------------------------------------------------
# fetch_token_prices
# ---------------------------------------------------------------------------


class TestFetchTokenPrices:
    """Tests for DexWalletService.fetch_token_prices()."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_addresses(self):
        """Edge case: empty address list returns empty dict."""
        service = DexWalletService()
        result = await service.fetch_token_prices(1, [])
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_for_unknown_chain(self):
        """Edge case: unknown chain ID (no CoinGecko mapping) returns empty."""
        service = DexWalletService()
        result = await service.fetch_token_prices(99999, ["0xabc"])
        assert result == {}

    @pytest.mark.asyncio
    async def test_fetches_prices_from_coingecko(self):
        """Happy path: fetches and returns token prices."""
        service = DexWalletService()

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "0xusdc_address": {"usd": 1.0}
        })

        # session.get() returns an async context manager
        mock_get_cm = MagicMock()
        mock_get_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_cm.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_get_cm

        # ClientSession() is itself an async context manager
        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        # Clear cache to force fetch
        import app.services.dex_wallet_service as dws
        dws._price_cache.clear()

        with patch("app.services.dex_wallet_service.aiohttp.ClientSession", return_value=mock_session_cm), \
             patch("app.services.dex_wallet_service.asyncio") as mock_asyncio:
            mock_asyncio.sleep = AsyncMock()

            result = await service.fetch_token_prices(1, ["0xUSDC_Address"])

        assert "0xusdc_address" in result
        assert result["0xusdc_address"] == 1.0

    @pytest.mark.asyncio
    async def test_uses_cache_when_fresh(self):
        """Edge case: returns cached prices without making API call."""
        import time
        import app.services.dex_wallet_service as dws

        service = DexWalletService()

        # Set fresh cache
        dws._price_cache["0xcached"] = (42.0, time.time())

        result = await service.fetch_token_prices(1, ["0xCached"])

        assert result["0xcached"] == 42.0

        # Clean up
        dws._price_cache.clear()

    @pytest.mark.asyncio
    async def test_stops_on_rate_limit(self):
        """Edge case: stops fetching when CoinGecko returns 429."""
        service = DexWalletService()

        mock_response = MagicMock()
        mock_response.status = 429

        mock_get_cm = MagicMock()
        mock_get_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_cm.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_get_cm

        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        import app.services.dex_wallet_service as dws
        dws._price_cache.clear()

        with patch("app.services.dex_wallet_service.aiohttp.ClientSession", return_value=mock_session_cm), \
             patch("app.services.dex_wallet_service.asyncio") as mock_asyncio:
            mock_asyncio.sleep = AsyncMock()

            await service.fetch_token_prices(
                1, ["0xToken1", "0xToken2"]
            )

        # Only 1 API call before rate limit stop
        assert mock_session.get.call_count == 1


# ---------------------------------------------------------------------------
# format_portfolio_for_api
# ---------------------------------------------------------------------------


class TestFormatPortfolioForApi:
    """Tests for DexWalletService.format_portfolio_for_api()."""

    @pytest.mark.asyncio
    async def test_formats_native_and_tokens(self):
        """Happy path: formats portfolio with native ETH and tokens."""
        service = DexWalletService()

        usdc_token = TokenBalance(
            symbol="USDC",
            address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            balance=Decimal("1000"),
            decimals=6,
            raw_balance=1000000000,
        )

        portfolio = WalletPortfolio(
            chain_id=1,
            wallet_address="0xWallet",
            native_balance=Decimal("2.0"),
            native_symbol="ETH",
            token_balances=[usdc_token],
        )

        with patch.object(
            service, "fetch_token_prices",
            new_callable=AsyncMock,
            return_value={
                "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": 1.0
            },
        ):
            result = await service.format_portfolio_for_api(
                portfolio, eth_usd_price=3500.0, btc_usd_price=100000.0
            )

        assert result["is_dex"] is True
        assert result["chain_id"] == 1
        assert result["holdings_count"] == 2  # ETH + USDC

        # Native ETH holding
        eth_holding = next(h for h in result["holdings"] if h["asset"] == "ETH")
        assert eth_holding["usd_value"] == pytest.approx(7000.0)
        assert eth_holding["total_balance"] == pytest.approx(2.0)

        # USDC holding
        usdc_holding = next(h for h in result["holdings"] if h["asset"] == "USDC")
        assert usdc_holding["usd_value"] == pytest.approx(1000.0)

        # Totals
        assert result["total_usd_value"] == pytest.approx(8000.0)

    @pytest.mark.asyncio
    async def test_empty_portfolio(self):
        """Edge case: empty wallet returns zero values."""
        service = DexWalletService()

        portfolio = WalletPortfolio(
            chain_id=1,
            wallet_address="0xEmpty",
            native_balance=Decimal("0"),
            native_symbol="ETH",
            token_balances=[],
        )

        with patch.object(
            service, "fetch_token_prices",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await service.format_portfolio_for_api(
                portfolio, eth_usd_price=3500.0, btc_usd_price=100000.0
            )

        assert result["total_usd_value"] == 0.0
        assert result["holdings"] == []

    @pytest.mark.asyncio
    async def test_stablecoin_fallback_pricing(self):
        """Edge case: stablecoins use $1 fallback when CoinGecko has no price."""
        service = DexWalletService()

        usdt_token = TokenBalance(
            symbol="USDT",
            address="0xdAC17F958D2ee523a2206206994597C13D831ec7",
            balance=Decimal("500"),
            decimals=6,
            raw_balance=500000000,
        )

        portfolio = WalletPortfolio(
            chain_id=1,
            wallet_address="0xWallet",
            native_balance=Decimal("0"),
            native_symbol="ETH",
            token_balances=[usdt_token],
        )

        with patch.object(
            service, "fetch_token_prices",
            new_callable=AsyncMock,
            return_value={},  # No CoinGecko prices
        ):
            result = await service.format_portfolio_for_api(
                portfolio, eth_usd_price=3500.0, btc_usd_price=100000.0
            )

        usdt_holding = result["holdings"][0]
        assert usdt_holding["current_price_usd"] == 1.0
        assert usdt_holding["usd_value"] == pytest.approx(500.0)

    @pytest.mark.asyncio
    async def test_weth_fallback_uses_eth_price(self):
        """Edge case: WETH uses ETH price as fallback."""
        service = DexWalletService()

        weth_token = TokenBalance(
            symbol="WETH",
            address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            balance=Decimal("1.0"),
            decimals=18,
            raw_balance=1000000000000000000,
        )

        portfolio = WalletPortfolio(
            chain_id=1,
            wallet_address="0xWallet",
            native_balance=Decimal("0"),
            native_symbol="ETH",
            token_balances=[weth_token],
        )

        with patch.object(
            service, "fetch_token_prices",
            new_callable=AsyncMock,
            return_value={},  # No CoinGecko prices
        ):
            result = await service.format_portfolio_for_api(
                portfolio, eth_usd_price=3500.0, btc_usd_price=100000.0
            )

        weth_holding = result["holdings"][0]
        assert weth_holding["current_price_usd"] == 3500.0
        assert weth_holding["usd_value"] == pytest.approx(3500.0)

    @pytest.mark.asyncio
    async def test_deprecated_token_gets_migration_flag(self):
        """Edge case: deprecated tokens get requires_migration flag."""
        service = DexWalletService()

        # Old GALA v1 token (in DEPRECATED_TOKENS)
        gala_addr = "0x15D4c048F83bd7e37d49eA4C83a07267Ec4203dA"
        gala_token = TokenBalance(
            symbol="GALA",
            address=gala_addr,
            balance=Decimal("10000"),
            decimals=18,
            raw_balance=10000000000000000000000,
        )

        portfolio = WalletPortfolio(
            chain_id=1,
            wallet_address="0xWallet",
            native_balance=Decimal("0"),
            native_symbol="ETH",
            token_balances=[gala_token],
        )

        with patch.object(
            service, "fetch_token_prices",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await service.format_portfolio_for_api(
                portfolio, eth_usd_price=3500.0, btc_usd_price=100000.0
            )

        gala_holding = result["holdings"][0]
        assert gala_holding["requires_migration"] is True
        assert "migration_url" in gala_holding

    @pytest.mark.asyncio
    async def test_percentages_calculated_correctly(self):
        """Percentages should sum to ~100%."""
        service = DexWalletService()

        portfolio = WalletPortfolio(
            chain_id=1,
            wallet_address="0xWallet",
            native_balance=Decimal("1.0"),
            native_symbol="ETH",
            token_balances=[],
        )

        with patch.object(
            service, "fetch_token_prices",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await service.format_portfolio_for_api(
                portfolio, eth_usd_price=3500.0, btc_usd_price=100000.0
            )

        total_pct = sum(h["percentage"] for h in result["holdings"])
        assert total_pct == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_btc_usd_zero_handles_gracefully(self):
        """Edge case: btc_usd_price = 0 does not cause division by zero."""
        service = DexWalletService()

        portfolio = WalletPortfolio(
            chain_id=1,
            wallet_address="0xWallet",
            native_balance=Decimal("1.0"),
            native_symbol="ETH",
            token_balances=[],
        )

        with patch.object(
            service, "fetch_token_prices",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await service.format_portfolio_for_api(
                portfolio, eth_usd_price=3500.0, btc_usd_price=0
            )

        eth_holding = result["holdings"][0]
        assert eth_holding["btc_value"] == 0.0
        assert result["total_btc_value"] == 0.0
