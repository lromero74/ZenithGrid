"""
DEX Wallet Service

Fetches wallet balances and token holdings from blockchain networks.
Supports Ethereum mainnet and common L2s (Arbitrum, Polygon, Base).
"""

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional

from web3 import Web3
from web3.exceptions import Web3Exception

logger = logging.getLogger(__name__)

# Common ERC20 ABI for balanceOf
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    },
]

# Common token addresses by chain
TOKEN_ADDRESSES = {
    1: {  # Ethereum Mainnet
        "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
        "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
        "LINK": "0x514910771AF9Ca656af840dff83E8264EcF986CA",
        "UNI": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",
        "AAVE": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9",
    },
    42161: {  # Arbitrum One
        "WETH": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "USDT": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
        "WBTC": "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
    },
    137: {  # Polygon
        "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
        "USDC": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "WBTC": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
    },
    8453: {  # Base
        "WETH": "0x4200000000000000000000000000000000000006",
        "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    },
}

# Default RPC URLs (can be overridden)
DEFAULT_RPC_URLS = {
    1: "https://eth.llamarpc.com",
    42161: "https://arb1.arbitrum.io/rpc",
    137: "https://polygon-rpc.com",
    8453: "https://mainnet.base.org",
}


@dataclass
class TokenBalance:
    """Token balance information"""
    symbol: str
    address: str
    balance: Decimal
    decimals: int
    raw_balance: int


@dataclass
class WalletPortfolio:
    """Complete wallet portfolio"""
    chain_id: int
    wallet_address: str
    native_balance: Decimal  # ETH/MATIC/etc
    native_symbol: str
    token_balances: List[TokenBalance]
    total_usd_value: Optional[Decimal] = None
    error: Optional[str] = None


class DexWalletService:
    """
    Service for fetching DEX wallet balances.

    Usage:
        service = DexWalletService()
        portfolio = await service.get_wallet_portfolio(
            chain_id=1,
            wallet_address="0x...",
            rpc_url="https://..."  # optional
        )
    """

    def __init__(self):
        self._web3_cache: Dict[int, Web3] = {}

    def _get_web3(self, chain_id: int, rpc_url: Optional[str] = None) -> Web3:
        """Get or create Web3 instance for chain"""
        cache_key = f"{chain_id}:{rpc_url or 'default'}"

        if cache_key not in self._web3_cache:
            url = rpc_url or DEFAULT_RPC_URLS.get(chain_id)
            if not url:
                raise ValueError(f"No RPC URL for chain {chain_id}")

            self._web3_cache[cache_key] = Web3(Web3.HTTPProvider(url))

        return self._web3_cache[cache_key]

    def _get_native_symbol(self, chain_id: int) -> str:
        """Get native token symbol for chain"""
        return {
            1: "ETH",
            42161: "ETH",
            137: "MATIC",
            8453: "ETH",
            56: "BNB",
            43114: "AVAX",
        }.get(chain_id, "ETH")

    async def get_native_balance(
        self,
        chain_id: int,
        wallet_address: str,
        rpc_url: Optional[str] = None,
    ) -> Decimal:
        """Get native token balance (ETH, MATIC, etc)"""
        try:
            w3 = self._get_web3(chain_id, rpc_url)

            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            balance_wei = await loop.run_in_executor(
                None,
                lambda: w3.eth.get_balance(Web3.to_checksum_address(wallet_address))
            )

            return Decimal(str(w3.from_wei(balance_wei, 'ether')))
        except Exception as e:
            logger.error(f"Error fetching native balance: {e}")
            return Decimal("0")

    async def get_token_balance(
        self,
        chain_id: int,
        wallet_address: str,
        token_address: str,
        rpc_url: Optional[str] = None,
    ) -> Optional[TokenBalance]:
        """Get ERC20 token balance"""
        try:
            w3 = self._get_web3(chain_id, rpc_url)
            wallet = Web3.to_checksum_address(wallet_address)
            token = Web3.to_checksum_address(token_address)

            contract = w3.eth.contract(address=token, abi=ERC20_ABI)

            loop = asyncio.get_event_loop()

            # Fetch balance, decimals, and symbol concurrently
            balance_task = loop.run_in_executor(
                None, lambda: contract.functions.balanceOf(wallet).call()
            )
            decimals_task = loop.run_in_executor(
                None, lambda: contract.functions.decimals().call()
            )
            symbol_task = loop.run_in_executor(
                None, lambda: contract.functions.symbol().call()
            )

            raw_balance, decimals, symbol = await asyncio.gather(
                balance_task, decimals_task, symbol_task
            )

            if raw_balance == 0:
                return None

            balance = Decimal(str(raw_balance)) / Decimal(10 ** decimals)

            return TokenBalance(
                symbol=symbol,
                address=token_address,
                balance=balance,
                decimals=decimals,
                raw_balance=raw_balance,
            )
        except Exception as e:
            logger.warning(f"Error fetching token {token_address}: {e}")
            return None

    async def get_wallet_portfolio(
        self,
        chain_id: int,
        wallet_address: str,
        rpc_url: Optional[str] = None,
        include_tokens: bool = True,
    ) -> WalletPortfolio:
        """
        Get complete wallet portfolio.

        Args:
            chain_id: Blockchain chain ID
            wallet_address: Wallet address to query
            rpc_url: Optional custom RPC URL
            include_tokens: Whether to fetch ERC20 token balances

        Returns:
            WalletPortfolio with native and token balances
        """
        try:
            # Get native balance
            native_balance = await self.get_native_balance(
                chain_id, wallet_address, rpc_url
            )

            token_balances = []

            if include_tokens:
                # Get known token balances for this chain
                tokens = TOKEN_ADDRESSES.get(chain_id, {})

                # Fetch all token balances concurrently
                tasks = [
                    self.get_token_balance(chain_id, wallet_address, addr, rpc_url)
                    for addr in tokens.values()
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, TokenBalance) and result is not None:
                        token_balances.append(result)

            return WalletPortfolio(
                chain_id=chain_id,
                wallet_address=wallet_address,
                native_balance=native_balance,
                native_symbol=self._get_native_symbol(chain_id),
                token_balances=token_balances,
            )
        except Exception as e:
            logger.error(f"Error fetching wallet portfolio: {e}")
            return WalletPortfolio(
                chain_id=chain_id,
                wallet_address=wallet_address,
                native_balance=Decimal("0"),
                native_symbol=self._get_native_symbol(chain_id),
                token_balances=[],
                error=str(e),
            )

    def format_portfolio_for_api(
        self,
        portfolio: WalletPortfolio,
        eth_usd_price: float = 0,
        btc_usd_price: float = 0,
    ) -> dict:
        """
        Format portfolio for API response (matching CEX portfolio format).

        Args:
            portfolio: WalletPortfolio from get_wallet_portfolio
            eth_usd_price: Current ETH/USD price for valuation
            btc_usd_price: Current BTC/USD price for valuation

        Returns:
            Dict matching the CEX portfolio API response format
        """
        holdings = []
        total_usd = Decimal("0")

        # Add native token
        if portfolio.native_balance > 0:
            native_usd = portfolio.native_balance * Decimal(str(eth_usd_price))
            native_btc = native_usd / Decimal(str(btc_usd_price)) if btc_usd_price > 0 else Decimal("0")
            total_usd += native_usd

            holdings.append({
                "asset": portfolio.native_symbol,
                "total_balance": float(portfolio.native_balance),
                "available": float(portfolio.native_balance),
                "hold": 0,
                "current_price_usd": eth_usd_price,
                "usd_value": float(native_usd),
                "btc_value": float(native_btc),
                "percentage": 0,  # Will be calculated later
            })

        # Add token balances
        for token in portfolio.token_balances:
            # For now, only value stablecoins accurately
            if token.symbol in ["USDC", "USDT", "DAI"]:
                token_usd = token.balance  # 1:1 for stablecoins
            elif token.symbol == "WETH":
                token_usd = token.balance * Decimal(str(eth_usd_price))
            elif token.symbol == "WBTC":
                token_usd = token.balance * Decimal(str(btc_usd_price))
            else:
                # Skip tokens we can't price yet
                token_usd = Decimal("0")

            if token_usd > 0:
                token_btc = token_usd / Decimal(str(btc_usd_price)) if btc_usd_price > 0 else Decimal("0")
                total_usd += token_usd

                holdings.append({
                    "asset": token.symbol,
                    "total_balance": float(token.balance),
                    "available": float(token.balance),
                    "hold": 0,
                    "current_price_usd": float(token_usd / token.balance) if token.balance > 0 else 0,
                    "usd_value": float(token_usd),
                    "btc_value": float(token_btc),
                    "percentage": 0,
                })

        # Calculate percentages
        for holding in holdings:
            if total_usd > 0:
                holding["percentage"] = (holding["usd_value"] / float(total_usd)) * 100

        # Sort by USD value
        holdings.sort(key=lambda x: x["usd_value"], reverse=True)

        total_btc = total_usd / Decimal(str(btc_usd_price)) if btc_usd_price > 0 else Decimal("0")

        return {
            "total_usd_value": float(total_usd),
            "total_btc_value": float(total_btc),
            "btc_usd_price": btc_usd_price,
            "holdings": holdings,
            "holdings_count": len(holdings),
            "chain_id": portfolio.chain_id,
            "wallet_address": portfolio.wallet_address,
            "is_dex": True,
        }


# Singleton instance
dex_wallet_service = DexWalletService()
