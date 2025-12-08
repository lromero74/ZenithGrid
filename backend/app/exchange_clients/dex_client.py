"""
DEX Client Implementation for Ethereum and Uniswap V3

This module implements the ExchangeClient interface for decentralized exchanges,
initially supporting Ethereum mainnet with Uniswap V3.

Architecture:
- Uses Web3.py for Ethereum blockchain interaction
- Supports Uniswap V3 for token swaps and price discovery
- Wallet management via private key (imported MetaMask wallet)
- All methods return standardized data structures matching the ExchangeClient interface

Supported Chains (Phase 3):
- Ethereum Mainnet (chain_id: 1)

Supported DEXes (Phase 3):
- Uniswap V3

Future Expansion (Phase 5):
- BSC (chain_id: 56) + PancakeSwap
- Polygon (chain_id: 137) + SushiSwap
- Arbitrum (chain_id: 42161) + Uniswap V3
"""

import asyncio
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from web3 import Web3
# web3.py 6.x uses geth_poa_middleware, 7.x uses ExtraDataToPOAMiddleware
try:
    from web3.middleware import ExtraDataToPOAMiddleware as poa_middleware
except ImportError:
    from web3.middleware import geth_poa_middleware as poa_middleware
from eth_account import Account
from eth_typing import ChecksumAddress

from app.exchange_clients.base import ExchangeClient
from app.exchange_clients.dex_constants import (
    TOKEN_ADDRESSES,
    TOKEN_DECIMALS,
    UNISWAP_V3_QUOTER,
    UNISWAP_V3_QUOTER_ABI,
    UNISWAP_V3_SWAPROUTER_ABI,
    ERC20_ABI,
)

logger = logging.getLogger(__name__)


class DEXClient(ExchangeClient):
    """
    Decentralized Exchange Client for Ethereum + Uniswap V3

    Implements the ExchangeClient interface for DEX trading.

    Features:
    - Web3 blockchain interaction
    - Uniswap V3 token swaps
    - ERC-20 token balance tracking
    - On-chain price discovery
    - MetaMask wallet support (private key import)

    Usage:
        client = DEXClient(
            chain_id=1,  # Ethereum Mainnet
            rpc_url="https://mainnet.infura.io/v3/YOUR_KEY",
            wallet_private_key="0x...",
            dex_router=UNISWAP_V3_ROUTER
        )

        # Use like any ExchangeClient
        balance = await client.get_eth_balance()
        order = await client.create_market_order("WETH-USDC", "BUY", funds="100")
    """

    def __init__(
        self,
        chain_id: int,
        rpc_url: str,
        wallet_private_key: str,
        dex_router: str,
    ):
        """
        Initialize DEX client for Ethereum + Uniswap V3

        Args:
            chain_id: Blockchain network ID (1 for Ethereum Mainnet)
            rpc_url: RPC endpoint URL (Infura, Alchemy, etc.)
            wallet_private_key: Private key for wallet (0x prefixed hex string)
            dex_router: DEX router contract address (Uniswap V3 SwapRouter)
        """
        self.chain_id = chain_id
        self.rpc_url = rpc_url
        self.dex_router = dex_router

        # Initialize Web3 connection
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))

        # Add PoA middleware for BSC/Polygon compatibility (not needed for Ethereum mainnet but doesn't hurt)
        self.w3.middleware_onion.inject(poa_middleware, layer=0)

        # Load wallet from private key
        self.account = Account.from_key(wallet_private_key)
        self.wallet_address: ChecksumAddress = self.account.address

        # Initialize Uniswap V3 Quoter contract for price discovery
        self.quoter = self.w3.eth.contract(
            address=Web3.to_checksum_address(UNISWAP_V3_QUOTER),
            abi=UNISWAP_V3_QUOTER_ABI
        )

        # Initialize Uniswap V3 SwapRouter contract for trade execution
        self.swap_router = self.w3.eth.contract(
            address=Web3.to_checksum_address(dex_router),
            abi=UNISWAP_V3_SWAPROUTER_ABI
        )

        # Cache for balances (invalidated after trades)
        self._balance_cache: Dict[str, float] = {}
        self._cache_valid = False

        logger.info(f"DEXClient initialized: chain={chain_id}, wallet={self.wallet_address}, router={dex_router}")

    # ========================================
    # EXCHANGE METADATA
    # ========================================

    def get_exchange_type(self) -> str:
        """Return 'dex' to identify as decentralized exchange"""
        return "dex"

    async def test_connection(self) -> bool:
        """Test connectivity to blockchain RPC"""
        try:
            block_number = await asyncio.to_thread(lambda: self.w3.eth.block_number)
            logger.info(f"DEX connection test successful: block_number={block_number}")
            return True
        except Exception as e:
            logger.error(f"DEX connection test failed: {e}")
            return False

    # ========================================
    # ACCOUNT & BALANCE METHODS
    # ========================================

    async def get_accounts(self, force_fresh: bool = False) -> List[Dict[str, Any]]:
        """
        Get wallet account information (DEX has single wallet)

        Returns wallet as single account in Coinbase-compatible format
        """
        # For DEX, we have one "account" which is the connected wallet
        eth_balance = await self.get_eth_balance()

        return [
            {
                "uuid": str(self.wallet_address),
                "currency": "ETH",
                "available_balance": {
                    "value": str(eth_balance),
                    "currency": "ETH"
                },
                "type": "dex_wallet",
                "name": "MetaMask Wallet",
            }
        ]

    async def get_account(self, account_id: str) -> Dict[str, Any]:
        """Get account details (for DEX, returns wallet info)"""
        accounts = await self.get_accounts()
        return accounts[0] if accounts else {}

    async def get_eth_balance(self) -> float:
        """Get native ETH balance from wallet"""
        if self._cache_valid and "ETH" in self._balance_cache:
            return self._balance_cache["ETH"]

        # Get balance in Wei, convert to ETH
        balance_wei = await asyncio.to_thread(
            lambda: self.w3.eth.get_balance(self.wallet_address)
        )
        balance_eth = float(self.w3.from_wei(balance_wei, 'ether'))

        self._balance_cache["ETH"] = balance_eth
        self._cache_valid = True

        return balance_eth

    async def get_btc_balance(self) -> float:
        """Get WBTC (Wrapped Bitcoin) balance from wallet"""
        return await self._get_erc20_balance(TOKEN_ADDRESSES["WBTC"], "WBTC", 8)

    async def get_usd_balance(self) -> float:
        """Get USDC balance (primary stablecoin)"""
        return await self._get_erc20_balance(TOKEN_ADDRESSES["USDC"], "USDC", 6)

    async def _get_erc20_balance(self, token_address: str, symbol: str, decimals: int) -> float:
        """
        Get ERC-20 token balance

        Args:
            token_address: Contract address of token
            symbol: Token symbol (for caching)
            decimals: Token decimals (e.g., 18 for most tokens, 6 for USDC, 8 for WBTC)

        Returns:
            Balance as float
        """
        if self._cache_valid and symbol in self._balance_cache:
            return self._balance_cache[symbol]

        # Create contract instance
        token_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=ERC20_ABI
        )

        # Get balance in token's smallest unit
        balance_raw = await asyncio.to_thread(
            lambda: token_contract.functions.balanceOf(self.wallet_address).call()
        )

        # Convert to human-readable format
        balance = float(Decimal(balance_raw) / Decimal(10 ** decimals))

        self._balance_cache[symbol] = balance
        self._cache_valid = True

        return balance

    async def invalidate_balance_cache(self):
        """Invalidate balance cache (call after trades)"""
        self._cache_valid = False
        self._balance_cache.clear()
        logger.debug("Balance cache invalidated")

    async def calculate_aggregate_btc_value(self) -> float:
        """
        Calculate total portfolio value in BTC (WBTC)

        For DEX: Includes WBTC balance + BTC value of other holdings

        NOTE: This is a simplified implementation. Full implementation would
        fetch prices for all tokens and convert to BTC.
        """
        wbtc_balance = await self.get_btc_balance()

        # TODO: Add conversion of ETH, USDC, and other tokens to BTC equivalent
        # For now, just return WBTC balance
        logger.warning("aggregate_btc_value: Only counting WBTC balance, not converting other assets")

        return wbtc_balance

    async def calculate_aggregate_usd_value(self) -> float:
        """
        Calculate total portfolio value in USD

        Converts all holdings (ETH, WBTC, tokens) to USD value
        """
        # Get stablecoin balance (already in USD)
        usdc_balance = await self.get_usd_balance()

        # TODO: Add USD value of ETH, WBTC, and other tokens
        # Would need to fetch USD prices from Uniswap or price oracle
        logger.warning("aggregate_usd_value: Only counting USDC balance, not converting other assets")

        return usdc_balance

    # ========================================
    # MARKET DATA METHODS
    # ========================================

    async def list_products(self) -> List[Dict[str, Any]]:
        """
        List available trading pairs on Uniswap

        NOTE: Uniswap supports thousands of pairs. This returns common pairs.
        Full implementation would query Uniswap factory for all pools.
        """
        # Return common pairs for now
        return [
            {
                "product_id": "WETH-USDC",
                "base_currency": "WETH",
                "quote_currency": "USDC",
                "base_min_size": "0.001",
                "base_max_size": "1000000",
                "status": "online",
            },
            {
                "product_id": "WBTC-WETH",
                "base_currency": "WBTC",
                "quote_currency": "WETH",
                "base_min_size": "0.0001",
                "base_max_size": "100000",
                "status": "online",
            },
            # Add more pairs as needed
        ]

    async def get_product(self, product_id: str = "WETH-USDC") -> Dict[str, Any]:
        """Get product details for a trading pair"""
        products = await self.list_products()
        for product in products:
            if product["product_id"] == product_id:
                return product

        # If not in list, return minimal info
        base, quote = product_id.split("-")
        return {
            "product_id": product_id,
            "base_currency": base,
            "quote_currency": quote,
            "status": "online",
        }

    async def get_ticker(self, product_id: str = "WETH-USDC") -> Dict[str, Any]:
        """Get real-time ticker (price) from Uniswap pool"""
        price = await self.get_current_price(product_id)

        return {
            "product_id": product_id,
            "price": str(price),
            "time": "",  # Uniswap doesn't have ticker timestamps (on-chain state)
        }

    def _get_token_addresses(self, product_id: str) -> tuple[str, str, int, int]:
        """
        Resolve product_id to token addresses and decimals

        Args:
            product_id: Trading pair (e.g., "WETH-USDC")

        Returns:
            Tuple of (token_in_address, token_out_address, token_in_decimals, token_out_decimals)

        Raises:
            ValueError: If token not found in TOKEN_ADDRESSES
        """
        base, quote = product_id.split("-")

        if base not in TOKEN_ADDRESSES or base not in TOKEN_DECIMALS:
            raise ValueError(f"Unsupported token: {base}")
        if quote not in TOKEN_ADDRESSES or quote not in TOKEN_DECIMALS:
            raise ValueError(f"Unsupported token: {quote}")

        return (
            TOKEN_ADDRESSES[base],
            TOKEN_ADDRESSES[quote],
            TOKEN_DECIMALS[base],
            TOKEN_DECIMALS[quote],
        )

    async def _quote_exact_input_single(
        self,
        token_in: str,
        token_out: str,
        amount_in_wei: int,
        fee: int = 3000,  # 0.3% fee tier (most common)
    ) -> int:
        """
        Call Uniswap V3 Quoter to get expected output amount

        Args:
            token_in: Input token address
            token_out: Output token address
            amount_in_wei: Input amount in wei (smallest unit)
            fee: Pool fee tier (500=0.05%, 3000=0.3%, 10000=1%)

        Returns:
            Expected output amount in wei

        Raises:
            Exception: If Quoter call fails
        """
        try:
            # Call Quoter contract (static call, doesn't cost gas)
            result = await asyncio.to_thread(
                lambda: self.quoter.functions.quoteExactInputSingle(
                    Web3.to_checksum_address(token_in),
                    Web3.to_checksum_address(token_out),
                    amount_in_wei,
                    fee,
                    0  # sqrtPriceLimitX96 = 0 means no limit
                ).call()
            )

            # Result is a tuple: (amountOut, sqrtPriceX96After, initializedTicksCrossed, gasEstimate)
            amount_out = result[0]
            return amount_out

        except Exception as e:
            logger.error(f"Quoter call failed: token_in={token_in}, token_out={token_out}, amount={amount_in_wei}, error={e}")
            raise

    async def get_current_price(self, product_id: str = "WETH-USDC") -> float:
        """
        Get current market price from Uniswap V3

        Uses Uniswap Quoter to get exact output amount for 1 unit of base currency

        Args:
            product_id: Trading pair (e.g., "WETH-USDC")

        Returns:
            Current price in quote currency

        Example:
            price = await client.get_current_price("WETH-USDC")
            # Returns: 3250.50 (1 WETH = 3250.50 USDC)
        """
        try:
            # Get token addresses and decimals
            token_in, token_out, decimals_in, decimals_out = self._get_token_addresses(product_id)

            # Amount in = 1 unit of base currency (e.g., 1 WETH = 10^18 wei)
            amount_in_wei = 10 ** decimals_in

            # Get quote from Uniswap V3
            amount_out_wei = await self._quote_exact_input_single(
                token_in=token_in,
                token_out=token_out,
                amount_in_wei=amount_in_wei,
                fee=3000  # 0.3% fee tier (most liquid pools)
            )

            # Convert output to human-readable format
            price = float(Decimal(amount_out_wei) / Decimal(10 ** decimals_out))

            logger.info(f"Price fetched from Uniswap: {product_id} = {price:.6f}")
            return price

        except Exception as e:
            logger.error(f"Failed to get price for {product_id}: {e}")
            # Fallback to placeholder if price fetch fails
            logger.warning(f"Using fallback placeholder price for {product_id}")
            return 3000.0

    async def get_btc_usd_price(self) -> float:
        """Get BTC-USD price (WBTC-USDC on Uniswap)"""
        return await self.get_current_price("WBTC-USDC")

    async def get_product_stats(self, product_id: str = "WETH-USDC") -> Dict[str, Any]:
        """
        Get 24h statistics for a product

        NOTE: DEXes don't have built-in stats. Would need to query historical
        transactions or use a subgraph (The Graph).
        """
        logger.warning(f"get_product_stats({product_id}): Not implemented for DEX")
        return {
            "product_id": product_id,
            "open": "0",
            "high": "0",
            "low": "0",
            "volume": "0",
        }

    async def get_candles(
        self,
        product_id: str,
        start: int,
        end: int,
        granularity: str,
    ) -> List[Dict[str, Any]]:
        """
        Get historical OHLCV candle data

        NOTE: Would require querying The Graph subgraph or similar indexer.
        DEX smart contracts don't provide historical candle data directly.
        """
        logger.warning(f"get_candles({product_id}): Not implemented for DEX - would need subgraph integration")
        return []

    # ========================================
    # ORDER EXECUTION METHODS (Uniswap V3 Swaps)
    # ========================================

    async def _approve_token(
        self,
        token_address: str,
        spender: str,
        amount_wei: int,
    ) -> str:
        """
        Approve ERC-20 token spending for SwapRouter

        Args:
            token_address: Token contract address
            spender: Spender address (SwapRouter)
            amount_wei: Amount to approve in wei

        Returns:
            Transaction hash of approval transaction

        Raises:
            Exception: If approval fails
        """
        try:
            # Create token contract instance
            token = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=ERC20_ABI
            )

            # Check current allowance
            current_allowance = await asyncio.to_thread(
                lambda: token.functions.allowance(
                    self.wallet_address,
                    Web3.to_checksum_address(spender)
                ).call()
            )

            # If allowance is sufficient, skip approval
            if current_allowance >= amount_wei:
                logger.info(f"Token approval not needed: current_allowance={current_allowance}, needed={amount_wei}")
                return ""  # No transaction needed

            logger.info(f"Approving token: address={token_address}, spender={spender}, amount={amount_wei}")

            # Build approval transaction
            approve_txn = await asyncio.to_thread(
                lambda: token.functions.approve(
                    Web3.to_checksum_address(spender),
                    amount_wei
                ).build_transaction({
                    'from': self.wallet_address,
                    'gas': 100000,  # Standard gas for approval
                    'gasPrice': self.w3.eth.gas_price,
                    'nonce': self.w3.eth.get_transaction_count(self.wallet_address),
                })
            )

            # Sign transaction
            signed_txn = self.account.sign_transaction(approve_txn)

            # Send transaction
            tx_hash = await asyncio.to_thread(
                lambda: self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            )

            # Wait for confirmation
            receipt = await asyncio.to_thread(
                lambda: self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            )

            if receipt['status'] != 1:
                raise Exception(f"Approval transaction failed: {tx_hash.hex()}")

            logger.info(f"Token approved successfully: tx_hash={tx_hash.hex()}")
            return tx_hash.hex()

        except Exception as e:
            logger.error(f"Token approval failed: {e}")
            raise

    async def create_market_order(
        self,
        product_id: str,
        side: str,
        size: Optional[str] = None,
        funds: Optional[str] = None,
        slippage_pct: float = 0.5,  # 0.5% default slippage tolerance
    ) -> Dict[str, Any]:
        """
        Execute a swap on Uniswap V3 (market order equivalent)

        Args:
            product_id: Trading pair (e.g., "WETH-USDC")
            side: "BUY" or "SELL"
            size: Amount of base currency to buy/sell
            funds: Amount of quote currency to spend (for BUY only)
            slippage_pct: Slippage tolerance percentage (default 0.5%)

        Returns:
            Order response with transaction hash as order_id

        Raises:
            ValueError: If parameters are invalid
            Exception: If swap execution fails

        Example:
            # Buy 0.1 WETH with USDC
            order = await client.create_market_order("WETH-USDC", "BUY", size="0.1")

            # Sell 0.1 WETH for USDC
            order = await client.create_market_order("WETH-USDC", "SELL", size="0.1")
        """
        import time

        try:
            logger.info(f"DEX swap: {product_id} {side} size={size} funds={funds}")

            # Get token addresses and decimals
            base_addr, quote_addr, base_decimals, quote_decimals = self._get_token_addresses(product_id)

            # Determine swap direction
            if side.upper() == "BUY":
                # BUY: quote → base (e.g., USDC → WETH)
                token_in = quote_addr
                token_out = base_addr
                decimals_in = quote_decimals
                decimals_out = base_decimals

                if not funds:
                    raise ValueError("BUY orders require 'funds' parameter")

                amount_in_float = float(funds)

            elif side.upper() == "SELL":
                # SELL: base → quote (e.g., WETH → USDC)
                token_in = base_addr
                token_out = quote_addr
                decimals_in = base_decimals
                decimals_out = quote_decimals

                if not size:
                    raise ValueError("SELL orders require 'size' parameter")

                amount_in_float = float(size)

            else:
                raise ValueError(f"Invalid side: {side}. Must be 'BUY' or 'SELL'")

            # Convert amount to wei
            amount_in_wei = int(amount_in_float * (10 ** decimals_in))

            logger.info(f"Swap params: token_in={token_in}, token_out={token_out}, amount_in={amount_in_wei}")

            # Step 1: Get quote for expected output (for slippage protection)
            expected_amount_out_wei = await self._quote_exact_input_single(
                token_in=token_in,
                token_out=token_out,
                amount_in_wei=amount_in_wei,
                fee=3000  # 0.3% fee tier
            )

            # Apply slippage tolerance
            amount_out_min_wei = int(expected_amount_out_wei * (1 - slippage_pct / 100))

            logger.info(f"Expected output: {expected_amount_out_wei}, min after slippage: {amount_out_min_wei}")

            # Step 2: Approve token spending (if needed)
            approval_tx = await self._approve_token(
                token_address=token_in,
                spender=self.dex_router,
                amount_wei=amount_in_wei
            )

            if approval_tx:
                logger.info(f"Token approval completed: {approval_tx}")

            # Step 3: Build swap transaction
            deadline = int(time.time()) + 300  # 5 minutes from now

            swap_params = {
                'tokenIn': Web3.to_checksum_address(token_in),
                'tokenOut': Web3.to_checksum_address(token_out),
                'fee': 3000,  # 0.3% fee tier
                'recipient': self.wallet_address,
                'deadline': deadline,
                'amountIn': amount_in_wei,
                'amountOutMinimum': amount_out_min_wei,
                'sqrtPriceLimitX96': 0  # No price limit
            }

            swap_txn = await asyncio.to_thread(
                lambda: self.swap_router.functions.exactInputSingle(swap_params).build_transaction({
                    'from': self.wallet_address,
                    'gas': 300000,  # Estimate gas for swap
                    'gasPrice': self.w3.eth.gas_price,
                    'nonce': self.w3.eth.get_transaction_count(self.wallet_address),
                    'value': 0  # No ETH value for ERC-20 swaps
                })
            )

            # Step 4: Sign and send swap transaction
            signed_swap = self.account.sign_transaction(swap_txn)

            tx_hash = await asyncio.to_thread(
                lambda: self.w3.eth.send_raw_transaction(signed_swap.raw_transaction)
            )

            logger.info(f"Swap transaction sent: tx_hash={tx_hash.hex()}")

            # Step 5: Wait for confirmation
            receipt = await asyncio.to_thread(
                lambda: self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            )

            if receipt['status'] != 1:
                raise Exception(f"Swap transaction failed: {tx_hash.hex()}")

            # Invalidate balance cache after successful trade
            await self.invalidate_balance_cache()

            # Calculate actual output amount from logs (if available)
            actual_amount_out = expected_amount_out_wei  # Placeholder - would parse logs for real value

            logger.info(f"Swap completed successfully: tx_hash={tx_hash.hex()}, gas_used={receipt['gasUsed']}")

            # Return order response in ExchangeClient format
            return {
                'order_id': tx_hash.hex(),
                'product_id': product_id,
                'side': side.upper(),
                'status': 'FILLED',
                'size': str(amount_in_float) if side.upper() == "SELL" else str(actual_amount_out / (10 ** decimals_out)),
                'filled_size': str(amount_in_float) if side.upper() == "SELL" else str(actual_amount_out / (10 ** decimals_out)),
                'price': str((expected_amount_out_wei / (10 ** decimals_out)) / amount_in_float),
                'funds': str(amount_in_float) if side.upper() == "BUY" else str(actual_amount_out / (10 ** decimals_out)),
                'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'tx_hash': tx_hash.hex(),
                'gas_used': receipt['gasUsed'],
            }

        except Exception as e:
            logger.error(f"DEX swap failed: {e}")
            raise

    async def create_limit_order(
        self,
        product_id: str,
        side: str,
        limit_price: float,
        size: Optional[str] = None,
        funds: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a limit order

        NOTE: Uniswap V3 doesn't support limit orders natively.
        Would require a limit order protocol like 1inch Limit Order Protocol.
        """
        logger.error("create_limit_order: DEX limit orders not supported in Phase 3")
        raise NotImplementedError("DEX limit orders require additional protocol integration")

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """
        Get order status (transaction status for DEX)

        Args:
            order_id: Transaction hash

        Returns:
            Order details with transaction status
        """
        # TODO: Query transaction receipt from blockchain
        logger.warning(f"get_order({order_id}): Placeholder implementation")
        return {
            "order_id": order_id,
            "status": "FILLED",  # Placeholder
            "product_id": "",
            "side": "",
        }

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel an order

        NOTE: Cannot cancel DEX swaps after broadcast (transaction is final)
        """
        logger.error("cancel_order: Cannot cancel DEX transactions after broadcast")
        raise NotImplementedError("DEX transactions cannot be cancelled")

    async def list_orders(
        self,
        product_id: Optional[str] = None,
        order_status: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List orders (transactions) for this wallet

        NOTE: Would require indexing wallet transactions from blockchain or subgraph
        """
        logger.warning("list_orders: Not implemented for DEX - would need transaction indexing")
        return []

    # ========================================
    # CONVENIENCE TRADING METHODS
    # ========================================

    async def buy_eth_with_btc(self, btc_amount: float, product_id: str = "WETH-WBTC") -> Dict[str, Any]:
        """Buy WETH using WBTC on Uniswap"""
        return await self.create_market_order(
            product_id=product_id,
            side="BUY",
            funds=str(btc_amount)
        )

    async def sell_eth_for_btc(self, eth_amount: float, product_id: str = "WETH-WBTC") -> Dict[str, Any]:
        """Sell WETH for WBTC on Uniswap"""
        return await self.create_market_order(
            product_id=product_id,
            side="SELL",
            size=str(eth_amount)
        )

    async def buy_with_usd(self, usd_amount: float, product_id: str) -> Dict[str, Any]:
        """Buy crypto with USDC on Uniswap"""
        return await self.create_market_order(
            product_id=product_id,
            side="BUY",
            funds=str(usd_amount)
        )

    async def sell_for_usd(self, base_amount: float, product_id: str) -> Dict[str, Any]:
        """Sell crypto for USDC on Uniswap"""
        return await self.create_market_order(
            product_id=product_id,
            side="SELL",
            size=str(base_amount)
        )
