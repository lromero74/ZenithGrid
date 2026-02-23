"""
Tests for backend/app/exchange_clients/dex_constants.py

Tests that DEX constants are correctly defined and consistent.
These are static data validation tests, not logic tests.
"""

from app.exchange_clients.dex_constants import (
    CHAIN_ID_ETHEREUM,
    ERC20_ABI,
    TOKEN_ADDRESSES,
    TOKEN_DECIMALS,
    UNISWAP_V3_FACTORY,
    UNISWAP_V3_QUOTER,
    UNISWAP_V3_QUOTER_ABI,
    UNISWAP_V3_ROUTER,
    UNISWAP_V3_SWAPROUTER_ABI,
)


class TestTokenAddresses:
    """Tests for TOKEN_ADDRESSES constants."""

    def test_weth_address_format(self):
        """Happy path: WETH address is valid Ethereum address."""
        assert TOKEN_ADDRESSES["WETH"].startswith("0x")
        assert len(TOKEN_ADDRESSES["WETH"]) == 42

    def test_usdc_address_format(self):
        """Happy path: USDC address is valid."""
        assert TOKEN_ADDRESSES["USDC"].startswith("0x")
        assert len(TOKEN_ADDRESSES["USDC"]) == 42

    def test_all_addresses_are_checksummed(self):
        """Edge case: all addresses are 42 chars (0x + 40 hex chars)."""
        for token, addr in TOKEN_ADDRESSES.items():
            assert addr.startswith("0x"), f"{token} address missing 0x prefix"
            assert len(addr) == 42, f"{token} address wrong length: {len(addr)}"

    def test_expected_tokens_present(self):
        """Happy path: all expected tokens are defined."""
        expected = {"WETH", "USDC", "USDT", "DAI", "WBTC"}
        assert expected.issubset(set(TOKEN_ADDRESSES.keys()))


class TestTokenDecimals:
    """Tests for TOKEN_DECIMALS constants."""

    def test_usdc_has_6_decimals(self):
        """Happy path: USDC uses 6 decimals."""
        assert TOKEN_DECIMALS["USDC"] == 6

    def test_usdt_has_6_decimals(self):
        """Happy path: USDT uses 6 decimals."""
        assert TOKEN_DECIMALS["USDT"] == 6

    def test_weth_has_18_decimals(self):
        """Happy path: WETH uses 18 decimals."""
        assert TOKEN_DECIMALS["WETH"] == 18

    def test_wbtc_has_8_decimals(self):
        """Happy path: WBTC uses 8 decimals."""
        assert TOKEN_DECIMALS["WBTC"] == 8

    def test_decimals_match_addresses(self):
        """Edge case: every token with an address has a decimals entry."""
        for token in TOKEN_ADDRESSES:
            assert token in TOKEN_DECIMALS, f"{token} missing from TOKEN_DECIMALS"


class TestUniswapConstants:
    """Tests for Uniswap V3 contract addresses."""

    def test_router_address_format(self):
        """Happy path: router address is valid."""
        assert UNISWAP_V3_ROUTER.startswith("0x")
        assert len(UNISWAP_V3_ROUTER) == 42

    def test_quoter_address_format(self):
        """Happy path: quoter address is valid."""
        assert UNISWAP_V3_QUOTER.startswith("0x")

    def test_factory_address_format(self):
        """Happy path: factory address is valid."""
        assert UNISWAP_V3_FACTORY.startswith("0x")

    def test_chain_id_ethereum(self):
        """Happy path: Ethereum mainnet chain ID is 1."""
        assert CHAIN_ID_ETHEREUM == 1


class TestABIDefinitions:
    """Tests for ABI definition integrity."""

    def test_erc20_abi_has_balance_of(self):
        """Happy path: ERC20 ABI includes balanceOf function."""
        names = [item["name"] for item in ERC20_ABI]
        assert "balanceOf" in names

    def test_erc20_abi_has_approve(self):
        """Happy path: ERC20 ABI includes approve function."""
        names = [item["name"] for item in ERC20_ABI]
        assert "approve" in names

    def test_erc20_abi_has_decimals(self):
        """Happy path: ERC20 ABI includes decimals function."""
        names = [item["name"] for item in ERC20_ABI]
        assert "decimals" in names

    def test_quoter_abi_has_quote_function(self):
        """Happy path: Quoter ABI includes quoteExactInputSingle."""
        names = [item["name"] for item in UNISWAP_V3_QUOTER_ABI]
        assert "quoteExactInputSingle" in names

    def test_swaprouter_abi_has_swap_function(self):
        """Happy path: SwapRouter ABI includes exactInputSingle."""
        names = [item["name"] for item in UNISWAP_V3_SWAPROUTER_ABI]
        assert "exactInputSingle" in names

    def test_abi_entries_have_type_field(self):
        """Edge case: all ABI entries have a 'type' field."""
        for entry in ERC20_ABI:
            assert "type" in entry

    def test_abi_entries_have_name_field(self):
        """Edge case: all ABI entries have a 'name' field."""
        for entry in ERC20_ABI:
            assert "name" in entry
