"""
Tests for backend/app/exchange_clients/dex_client.py

Tests the DEX Client that interacts with Ethereum and Uniswap V3.
All Web3/blockchain calls are mocked -- no real RPC or on-chain activity.

Covers:
- Exchange metadata (type, connection test)
- Account / balance methods (ETH, ERC-20, cache)
- Market data methods (products, ticker, price)
- Token address resolution
- Order execution (market orders / Uniswap swaps)
- Limit order / cancel / list (not implemented, raise NotImplementedError)
- Convenience trading methods
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from app.exchange_clients.dex_client import DEXClient
from app.exchange_clients.dex_constants import (
    TOKEN_ADDRESSES,
    UNISWAP_V3_ROUTER,
)


# =========================================================
# Fixtures
# =========================================================


@pytest.fixture
def mock_w3():
    """Create a mocked Web3 instance."""
    w3 = MagicMock()
    # Mock provider connection
    w3.is_connected.return_value = True
    # Mock eth namespace
    w3.eth = MagicMock()
    w3.eth.block_number = 19000000
    w3.eth.get_balance.return_value = 5 * 10**18  # 5 ETH in wei
    w3.eth.gas_price = 30 * 10**9  # 30 gwei
    w3.eth.get_transaction_count.return_value = 42
    # Mock from_wei for ETH balance conversion
    w3.from_wei.return_value = 5.0
    # Mock contract factory
    w3.eth.contract.return_value = MagicMock()
    # Mock to_checksum_address
    w3.to_checksum_address = MagicMock(side_effect=lambda x: x)
    return w3


@pytest.fixture
def mock_account():
    """Create a mocked eth_account Account."""
    account = MagicMock()
    account.address = "0x1234567890abcdef1234567890abcdef12345678"
    account.sign_transaction.return_value = MagicMock(
        raw_transaction=b"\x00" * 32
    )
    return account


@pytest.fixture
def dex_client(mock_w3, mock_account):
    """Create a DEXClient with mocked Web3 and Account."""
    with patch("app.exchange_clients.dex_client.Web3") as MockWeb3, \
         patch("app.exchange_clients.dex_client.Account") as MockAccount, \
         patch("app.exchange_clients.dex_client.poa_middleware"):

        MockWeb3.return_value = mock_w3
        MockWeb3.HTTPProvider = MagicMock()
        MockWeb3.to_checksum_address = MagicMock(side_effect=lambda x: x)
        MockAccount.from_key.return_value = mock_account

        client = DEXClient(
            chain_id=1,
            rpc_url="https://fake-rpc.example.com",
            wallet_private_key="0x" + "a" * 64,
            dex_router=UNISWAP_V3_ROUTER,
        )

    # Patch the w3 instance on the client so tests can control it
    client.w3 = mock_w3
    client.account = mock_account
    client.wallet_address = mock_account.address

    return client


# =========================================================
# Exchange metadata tests
# =========================================================


class TestDEXClientMetadata:
    """Tests for exchange type and connection testing."""

    def test_get_exchange_type_returns_dex(self, dex_client):
        """Happy path: DEX client identifies as 'dex'."""
        assert dex_client.get_exchange_type() == "dex"

    @pytest.mark.asyncio
    async def test_test_connection_success(self, dex_client, mock_w3):
        """Happy path: successful block number fetch returns True."""
        result = await dex_client.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, dex_client, mock_w3):
        """Failure: RPC error returns False."""
        type(mock_w3.eth).block_number = PropertyMock(
            side_effect=Exception("RPC error")
        )
        result = await dex_client.test_connection()
        assert result is False


# =========================================================
# Account / Balance tests
# =========================================================


class TestDEXClientBalances:
    """Tests for account and balance methods."""

    @pytest.mark.asyncio
    async def test_get_eth_balance_success(self, dex_client, mock_w3):
        """Happy path: returns ETH balance in ether."""
        mock_w3.eth.get_balance.return_value = 2 * 10**18
        mock_w3.from_wei.return_value = 2.0

        # Clear cache first
        dex_client._cache_valid = False
        balance = await dex_client.get_eth_balance()
        assert balance == 2.0

    @pytest.mark.asyncio
    async def test_get_eth_balance_uses_cache(self, dex_client):
        """Edge case: cached balance is returned without RPC call."""
        dex_client._cache_valid = True
        dex_client._balance_cache["ETH"] = 3.14
        balance = await dex_client.get_eth_balance()
        assert balance == 3.14

    @pytest.mark.asyncio
    async def test_get_btc_balance_calls_erc20(self, dex_client):
        """Happy path: get_btc_balance fetches WBTC ERC-20 balance."""
        dex_client._get_erc20_balance = AsyncMock(return_value=0.5)
        balance = await dex_client.get_btc_balance()
        assert balance == 0.5
        dex_client._get_erc20_balance.assert_called_once_with(
            TOKEN_ADDRESSES["WBTC"], "WBTC", 8,
        )

    @pytest.mark.asyncio
    async def test_get_usd_balance_calls_erc20(self, dex_client):
        """Happy path: get_usd_balance fetches USDC ERC-20 balance."""
        dex_client._get_erc20_balance = AsyncMock(return_value=1000.0)
        balance = await dex_client.get_usd_balance()
        assert balance == 1000.0
        dex_client._get_erc20_balance.assert_called_once_with(
            TOKEN_ADDRESSES["USDC"], "USDC", 6,
        )

    @pytest.mark.asyncio
    async def test_get_erc20_balance_fetches_and_caches(self, dex_client, mock_w3):
        """Happy path: ERC-20 balance is fetched from contract and cached."""
        dex_client._cache_valid = False
        # Mock the contract call returning raw balance
        mock_contract = MagicMock()
        mock_contract.functions.balanceOf.return_value.call.return_value = 1000 * 10**6  # 1000 USDC
        mock_w3.eth.contract.return_value = mock_contract

        balance = await dex_client._get_erc20_balance(
            TOKEN_ADDRESSES["USDC"], "USDC", 6,
        )
        assert balance == pytest.approx(1000.0)
        assert dex_client._balance_cache["USDC"] == pytest.approx(1000.0)

    @pytest.mark.asyncio
    async def test_get_erc20_balance_uses_cache(self, dex_client):
        """Edge case: cached ERC-20 balance returned without contract call."""
        dex_client._cache_valid = True
        dex_client._balance_cache["USDC"] = 500.0
        balance = await dex_client._get_erc20_balance(
            TOKEN_ADDRESSES["USDC"], "USDC", 6,
        )
        assert balance == 500.0

    @pytest.mark.asyncio
    async def test_get_balance_eth(self, dex_client, mock_w3):
        """get_balance('ETH') returns structured dict."""
        dex_client._cache_valid = False
        mock_w3.eth.get_balance.return_value = 10**18
        mock_w3.from_wei.return_value = 1.0

        result = await dex_client.get_balance("ETH")
        assert result["currency"] == "ETH"
        assert result["available"] == "1.0"
        assert result["hold"] == "0"

    @pytest.mark.asyncio
    async def test_get_balance_usdc(self, dex_client):
        """get_balance('USDC') calls ERC-20 balance."""
        dex_client._get_erc20_balance = AsyncMock(return_value=2500.0)
        result = await dex_client.get_balance("USDC")
        assert result["currency"] == "USDC"
        assert result["available"] == "2500.0"

    @pytest.mark.asyncio
    async def test_get_balance_btc_maps_to_wbtc(self, dex_client):
        """get_balance('BTC') maps to WBTC on DEX."""
        dex_client._get_erc20_balance = AsyncMock(return_value=0.25)
        result = await dex_client.get_balance("BTC")
        assert result["available"] == "0.25"

    @pytest.mark.asyncio
    async def test_get_balance_unknown_currency(self, dex_client):
        """Edge case: unknown currency returns 0 balance."""
        result = await dex_client.get_balance("DOGE")
        assert result["currency"] == "DOGE"
        assert result["available"] == "0.0"

    @pytest.mark.asyncio
    async def test_invalidate_balance_cache(self, dex_client):
        """invalidate_balance_cache clears the cache."""
        dex_client._cache_valid = True
        dex_client._balance_cache = {"ETH": 5.0, "USDC": 1000.0}
        await dex_client.invalidate_balance_cache()
        assert dex_client._cache_valid is False
        assert dex_client._balance_cache == {}

    @pytest.mark.asyncio
    async def test_get_accounts_returns_wallet_info(self, dex_client, mock_w3):
        """Happy path: returns single account with wallet info."""
        dex_client._cache_valid = False
        mock_w3.eth.get_balance.return_value = 3 * 10**18
        mock_w3.from_wei.return_value = 3.0

        accounts = await dex_client.get_accounts()
        assert len(accounts) == 1
        assert accounts[0]["uuid"] == dex_client.wallet_address
        assert accounts[0]["currency"] == "ETH"
        assert accounts[0]["type"] == "dex_wallet"
        assert accounts[0]["available_balance"]["value"] == "3.0"

    @pytest.mark.asyncio
    async def test_get_account_returns_first(self, dex_client, mock_w3):
        """get_account returns the single wallet account."""
        dex_client._cache_valid = True
        dex_client._balance_cache["ETH"] = 1.0
        account = await dex_client.get_account("any-id")
        assert account["uuid"] == dex_client.wallet_address


# =========================================================
# Aggregate value tests
# =========================================================


class TestDEXClientAggregateValues:
    """Tests for portfolio value calculations."""

    @pytest.mark.asyncio
    async def test_calculate_aggregate_btc_value(self, dex_client):
        """Returns WBTC balance only (simplified implementation)."""
        dex_client._get_erc20_balance = AsyncMock(return_value=0.75)
        result = await dex_client.calculate_aggregate_btc_value()
        assert result == 0.75

    @pytest.mark.asyncio
    async def test_calculate_aggregate_usd_value(self, dex_client):
        """Returns USDC balance only (simplified implementation)."""
        dex_client._get_erc20_balance = AsyncMock(return_value=5000.0)
        result = await dex_client.calculate_aggregate_usd_value()
        assert result == 5000.0


# =========================================================
# Market data tests
# =========================================================


class TestDEXClientMarketData:
    """Tests for market data methods."""

    @pytest.mark.asyncio
    async def test_list_products_returns_common_pairs(self, dex_client):
        """Happy path: returns WETH-USDC and WBTC-WETH."""
        products = await dex_client.list_products()
        assert len(products) >= 2
        ids = [p["product_id"] for p in products]
        assert "WETH-USDC" in ids
        assert "WBTC-WETH" in ids

    @pytest.mark.asyncio
    async def test_get_product_known(self, dex_client):
        """Happy path: known product returns full details."""
        product = await dex_client.get_product("WETH-USDC")
        assert product["product_id"] == "WETH-USDC"
        assert product["base_currency"] == "WETH"
        assert product["quote_currency"] == "USDC"

    @pytest.mark.asyncio
    async def test_get_product_unknown(self, dex_client):
        """Edge case: unknown product returns minimal info from parsing."""
        product = await dex_client.get_product("LINK-WETH")
        assert product["product_id"] == "LINK-WETH"
        assert product["base_currency"] == "LINK"
        assert product["quote_currency"] == "WETH"

    @pytest.mark.asyncio
    async def test_get_ticker_success(self, dex_client):
        """Happy path: get_ticker returns price from Uniswap."""
        dex_client.get_current_price = AsyncMock(return_value=3250.50)
        ticker = await dex_client.get_ticker("WETH-USDC")
        assert ticker["product_id"] == "WETH-USDC"
        assert ticker["price"] == "3250.5"

    @pytest.mark.asyncio
    async def test_get_product_stats_returns_placeholder(self, dex_client):
        """DEX doesn't have built-in stats, returns zeros."""
        stats = await dex_client.get_product_stats("WETH-USDC")
        assert stats["product_id"] == "WETH-USDC"
        assert stats["open"] == "0"

    @pytest.mark.asyncio
    async def test_get_candles_returns_empty(self, dex_client):
        """DEX candles not implemented, returns empty list."""
        candles = await dex_client.get_candles("WETH-USDC", 1700000000, 1700100000, "ONE_HOUR")
        assert candles == []

    @pytest.mark.asyncio
    async def test_get_btc_usd_price(self, dex_client):
        """Delegates to get_current_price('WBTC-USDC')."""
        dex_client.get_current_price = AsyncMock(return_value=65000.0)
        price = await dex_client.get_btc_usd_price()
        assert price == 65000.0
        dex_client.get_current_price.assert_called_once_with("WBTC-USDC")

    @pytest.mark.asyncio
    async def test_get_eth_usd_price(self, dex_client):
        """Delegates to get_current_price('WETH-USDC')."""
        dex_client.get_current_price = AsyncMock(return_value=3200.0)
        price = await dex_client.get_eth_usd_price()
        assert price == 3200.0
        dex_client.get_current_price.assert_called_once_with("WETH-USDC")


# =========================================================
# Token address resolution tests
# =========================================================


class TestDEXClientTokenAddresses:
    """Tests for _get_token_addresses()."""

    def test_weth_usdc_resolves(self, dex_client):
        """Happy path: WETH-USDC resolves to correct addresses."""
        addr_in, addr_out, dec_in, dec_out = dex_client._get_token_addresses("WETH-USDC")
        assert addr_in == TOKEN_ADDRESSES["WETH"]
        assert addr_out == TOKEN_ADDRESSES["USDC"]
        assert dec_in == 18
        assert dec_out == 6

    def test_wbtc_weth_resolves(self, dex_client):
        """Happy path: WBTC-WETH resolves correctly."""
        addr_in, addr_out, dec_in, dec_out = dex_client._get_token_addresses("WBTC-WETH")
        assert addr_in == TOKEN_ADDRESSES["WBTC"]
        assert addr_out == TOKEN_ADDRESSES["WETH"]
        assert dec_in == 8
        assert dec_out == 18

    def test_unsupported_base_token_raises(self, dex_client):
        """Failure: unsupported base token raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported token: DOGE"):
            dex_client._get_token_addresses("DOGE-USDC")

    def test_unsupported_quote_token_raises(self, dex_client):
        """Failure: unsupported quote token raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported token: DOGE"):
            dex_client._get_token_addresses("WETH-DOGE")


# =========================================================
# Price discovery tests
# =========================================================


class TestDEXClientPriceDiscovery:
    """Tests for get_current_price and _quote_exact_input_single."""

    @pytest.mark.asyncio
    async def test_get_current_price_success(self, dex_client):
        """Happy path: price calculated from Quoter response."""
        # Mock _quote_exact_input_single to return a known output
        # 1 WETH (10^18 wei) -> 3250.5 USDC (3250500000 in 6 decimals)
        dex_client._quote_exact_input_single = AsyncMock(
            return_value=3250500000
        )
        price = await dex_client.get_current_price("WETH-USDC")
        assert price == pytest.approx(3250.5)

    @pytest.mark.asyncio
    async def test_get_current_price_fallback_on_error(self, dex_client):
        """Failure: returns fallback 3000.0 when quoter fails."""
        dex_client._quote_exact_input_single = AsyncMock(
            side_effect=Exception("quoter failed")
        )
        price = await dex_client.get_current_price("WETH-USDC")
        assert price == 3000.0

    @pytest.mark.asyncio
    async def test_get_current_price_unsupported_token_fallback(self, dex_client):
        """Failure: unsupported token falls back to 3000.0."""
        price = await dex_client.get_current_price("DOGE-USDC")
        assert price == 3000.0

    @pytest.mark.asyncio
    async def test_quote_exact_input_single_success(self, dex_client):
        """Happy path: quoter contract returns expected output."""
        mock_quoter = MagicMock()
        mock_quoter.functions.quoteExactInputSingle.return_value.call.return_value = (
            3250500000, 0, 0, 0  # (amountOut, sqrtPriceX96After, ticks, gas)
        )
        dex_client.quoter = mock_quoter

        result = await dex_client._quote_exact_input_single(
            token_in=TOKEN_ADDRESSES["WETH"],
            token_out=TOKEN_ADDRESSES["USDC"],
            amount_in_wei=10**18,
        )
        assert result == 3250500000

    @pytest.mark.asyncio
    async def test_quote_exact_input_single_failure_raises(self, dex_client):
        """Failure: quoter contract error is re-raised."""
        mock_quoter = MagicMock()
        mock_quoter.functions.quoteExactInputSingle.return_value.call.side_effect = (
            Exception("No pool")
        )
        dex_client.quoter = mock_quoter

        with pytest.raises(Exception, match="No pool"):
            await dex_client._quote_exact_input_single(
                token_in=TOKEN_ADDRESSES["WETH"],
                token_out=TOKEN_ADDRESSES["USDC"],
                amount_in_wei=10**18,
            )


# =========================================================
# Token approval tests
# =========================================================


class TestDEXClientTokenApproval:
    """Tests for _approve_token()."""

    @pytest.mark.asyncio
    async def test_approve_skips_when_allowance_sufficient(self, dex_client, mock_w3):
        """Edge case: skip approval when current allowance >= needed."""
        mock_contract = MagicMock()
        mock_contract.functions.allowance.return_value.call.return_value = 10**20
        mock_w3.eth.contract.return_value = mock_contract

        result = await dex_client._approve_token(
            token_address=TOKEN_ADDRESSES["USDC"],
            spender=UNISWAP_V3_ROUTER,
            amount_wei=10**18,
        )
        assert result == ""  # No transaction needed

    @pytest.mark.asyncio
    async def test_approve_sends_transaction_when_needed(self, dex_client, mock_w3, mock_account):
        """Happy path: sends approval transaction when allowance insufficient."""
        mock_contract = MagicMock()
        mock_contract.functions.allowance.return_value.call.return_value = 0  # no allowance
        mock_contract.functions.approve.return_value.build_transaction.return_value = {
            "to": TOKEN_ADDRESSES["USDC"],
            "data": "0x...",
            "gas": 100000,
        }
        mock_w3.eth.contract.return_value = mock_contract
        mock_w3.eth.send_raw_transaction.return_value = b"\xab" * 32
        mock_w3.eth.wait_for_transaction_receipt.return_value = {"status": 1}

        # Mock the tx_hash hex
        mock_tx_hash = MagicMock()
        mock_tx_hash.hex.return_value = "ab" * 32
        mock_w3.eth.send_raw_transaction.return_value = mock_tx_hash

        result = await dex_client._approve_token(
            token_address=TOKEN_ADDRESSES["USDC"],
            spender=UNISWAP_V3_ROUTER,
            amount_wei=10**18,
        )
        assert result == "ab" * 32

    @pytest.mark.asyncio
    async def test_approve_failed_transaction_raises(self, dex_client, mock_w3, mock_account):
        """Failure: approval transaction with status != 1 raises."""
        mock_contract = MagicMock()
        mock_contract.functions.allowance.return_value.call.return_value = 0
        mock_contract.functions.approve.return_value.build_transaction.return_value = {}
        mock_w3.eth.contract.return_value = mock_contract

        mock_tx_hash = MagicMock()
        mock_tx_hash.hex.return_value = "dead" * 16
        mock_w3.eth.send_raw_transaction.return_value = mock_tx_hash
        mock_w3.eth.wait_for_transaction_receipt.return_value = {"status": 0}

        with pytest.raises(Exception, match="Approval transaction failed"):
            await dex_client._approve_token(
                token_address=TOKEN_ADDRESSES["USDC"],
                spender=UNISWAP_V3_ROUTER,
                amount_wei=10**18,
            )


# =========================================================
# Market order (swap) tests
# =========================================================


class TestDEXClientMarketOrder:
    """Tests for create_market_order() — Uniswap V3 swaps."""

    @pytest.mark.asyncio
    async def test_sell_order_success(self, dex_client, mock_w3, mock_account):
        """Happy path: SELL swap executes and returns order details."""
        # Mock quote
        dex_client._quote_exact_input_single = AsyncMock(return_value=3250 * 10**6)
        # Mock approval (skip)
        dex_client._approve_token = AsyncMock(return_value="")

        # Mock swap router
        mock_router = MagicMock()
        mock_router.functions.exactInputSingle.return_value.build_transaction.return_value = {
            "to": UNISWAP_V3_ROUTER,
            "data": "0x...",
        }
        dex_client.swap_router = mock_router

        # Mock transaction send/receipt
        mock_tx_hash = MagicMock()
        mock_tx_hash.hex.return_value = "abc123" * 10 + "ab"
        mock_w3.eth.send_raw_transaction.return_value = mock_tx_hash
        mock_w3.eth.wait_for_transaction_receipt.return_value = {
            "status": 1, "gasUsed": 150000,
        }

        result = await dex_client.create_market_order(
            product_id="WETH-USDC",
            side="SELL",
            size="1.0",
        )
        assert result["side"] == "SELL"
        assert result["status"] == "FILLED"
        assert result["tx_hash"] == mock_tx_hash.hex()
        assert result["gas_used"] == 150000

    @pytest.mark.asyncio
    async def test_buy_order_requires_funds(self, dex_client):
        """Failure: BUY without funds raises ValueError."""
        dex_client._quote_exact_input_single = AsyncMock(return_value=10**18)
        with pytest.raises(ValueError, match="BUY orders require 'funds'"):
            await dex_client.create_market_order(
                product_id="WETH-USDC",
                side="BUY",
                size="1.0",  # size alone not enough for BUY
            )

    @pytest.mark.asyncio
    async def test_sell_order_requires_size(self, dex_client):
        """Failure: SELL without size raises ValueError."""
        dex_client._quote_exact_input_single = AsyncMock(return_value=10**18)
        with pytest.raises(ValueError, match="SELL orders require 'size'"):
            await dex_client.create_market_order(
                product_id="WETH-USDC",
                side="SELL",
                funds="3000",  # funds alone not enough for SELL
            )

    @pytest.mark.asyncio
    async def test_invalid_side_raises(self, dex_client):
        """Failure: invalid side raises ValueError."""
        dex_client._quote_exact_input_single = AsyncMock(return_value=10**18)
        with pytest.raises(ValueError, match="Invalid side"):
            await dex_client.create_market_order(
                product_id="WETH-USDC",
                side="HOLD",
                size="1.0",
            )

    @pytest.mark.asyncio
    async def test_buy_order_success(self, dex_client, mock_w3, mock_account):
        """Happy path: BUY swap (USDC -> WETH)."""
        # Mock quote: spending 3250 USDC -> get ~1 WETH
        dex_client._quote_exact_input_single = AsyncMock(return_value=10**18)
        dex_client._approve_token = AsyncMock(return_value="")

        mock_router = MagicMock()
        mock_router.functions.exactInputSingle.return_value.build_transaction.return_value = {}
        dex_client.swap_router = mock_router

        mock_tx_hash = MagicMock()
        mock_tx_hash.hex.return_value = "def456" * 10 + "de"
        mock_w3.eth.send_raw_transaction.return_value = mock_tx_hash
        mock_w3.eth.wait_for_transaction_receipt.return_value = {
            "status": 1, "gasUsed": 200000,
        }

        result = await dex_client.create_market_order(
            product_id="WETH-USDC",
            side="BUY",
            funds="3250",
        )
        assert result["side"] == "BUY"
        assert result["status"] == "FILLED"

    @pytest.mark.asyncio
    async def test_swap_failed_transaction_raises(self, dex_client, mock_w3, mock_account):
        """Failure: swap tx with status 0 raises."""
        dex_client._quote_exact_input_single = AsyncMock(return_value=10**6)
        dex_client._approve_token = AsyncMock(return_value="")

        mock_router = MagicMock()
        mock_router.functions.exactInputSingle.return_value.build_transaction.return_value = {}
        dex_client.swap_router = mock_router

        mock_tx_hash = MagicMock()
        mock_tx_hash.hex.return_value = "bad0" * 16
        mock_w3.eth.send_raw_transaction.return_value = mock_tx_hash
        mock_w3.eth.wait_for_transaction_receipt.return_value = {
            "status": 0, "gasUsed": 21000,
        }

        with pytest.raises(Exception, match="Swap transaction failed"):
            await dex_client.create_market_order(
                product_id="WETH-USDC",
                side="SELL",
                size="0.1",
            )

    @pytest.mark.asyncio
    async def test_swap_unsupported_token_raises(self, dex_client):
        """Failure: unsupported token pair raises."""
        with pytest.raises(Exception):
            await dex_client.create_market_order(
                product_id="DOGE-USDC",
                side="BUY",
                funds="100",
            )


# =========================================================
# Limit order / cancel / list (not implemented)
# =========================================================


class TestDEXClientNotImplemented:
    """Tests for methods that raise NotImplementedError."""

    @pytest.mark.asyncio
    async def test_create_limit_order_raises(self, dex_client):
        """Limit orders not supported on Uniswap V3."""
        with pytest.raises(NotImplementedError, match="limit orders"):
            await dex_client.create_limit_order(
                product_id="WETH-USDC",
                side="BUY",
                limit_price=3000.0,
                size="1.0",
            )

    @pytest.mark.asyncio
    async def test_cancel_order_raises(self, dex_client):
        """Cannot cancel DEX transactions."""
        with pytest.raises(NotImplementedError, match="cannot be cancelled"):
            await dex_client.cancel_order("0x123")


# =========================================================
# Placeholder methods tests
# =========================================================


class TestDEXClientPlaceholders:
    """Tests for placeholder / stub methods."""

    @pytest.mark.asyncio
    async def test_get_order_returns_filled(self, dex_client):
        """get_order returns placeholder FILLED status."""
        result = await dex_client.get_order("0xabc")
        assert result["order_id"] == "0xabc"
        assert result["status"] == "FILLED"

    @pytest.mark.asyncio
    async def test_list_orders_returns_empty(self, dex_client):
        """list_orders returns empty (not implemented)."""
        orders = await dex_client.list_orders()
        assert orders == []


# =========================================================
# Convenience trading methods tests
# =========================================================


class TestDEXClientConvenienceMethods:
    """Tests for convenience trading methods."""

    @pytest.mark.asyncio
    async def test_buy_eth_with_btc(self, dex_client):
        """buy_eth_with_btc delegates to create_market_order."""
        dex_client.create_market_order = AsyncMock(return_value={"success": True})
        await dex_client.buy_eth_with_btc(0.5)
        dex_client.create_market_order.assert_called_once_with(
            product_id="WETH-WBTC", side="BUY", funds="0.5",
        )

    @pytest.mark.asyncio
    async def test_sell_eth_for_btc(self, dex_client):
        """sell_eth_for_btc delegates to create_market_order."""
        dex_client.create_market_order = AsyncMock(return_value={"success": True})
        await dex_client.sell_eth_for_btc(2.0)
        dex_client.create_market_order.assert_called_once_with(
            product_id="WETH-WBTC", side="SELL", size="2.0",
        )

    @pytest.mark.asyncio
    async def test_buy_with_usd(self, dex_client):
        """buy_with_usd delegates to create_market_order."""
        dex_client.create_market_order = AsyncMock(return_value={"success": True})
        await dex_client.buy_with_usd(1000.0, "WETH-USDC")
        dex_client.create_market_order.assert_called_once_with(
            product_id="WETH-USDC", side="BUY", funds="1000.0",
        )

    @pytest.mark.asyncio
    async def test_sell_for_usd(self, dex_client):
        """sell_for_usd delegates to create_market_order."""
        dex_client.create_market_order = AsyncMock(return_value={"success": True})
        await dex_client.sell_for_usd(0.5, "WETH-USDC")
        dex_client.create_market_order.assert_called_once_with(
            product_id="WETH-USDC", side="SELL", size="0.5",
        )
