"""
DEX Price Feed

Implements PriceFeed interface for decentralized exchanges (Uniswap V3, etc.).
Uses the DEXClient to fetch on-chain prices via quoter contracts.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from app.price_feeds.base import PriceFeed, PriceQuote, OrderBook, OrderBookLevel

logger = logging.getLogger(__name__)


class DEXPriceFeed(PriceFeed):
    """
    Price feed implementation for decentralized exchanges.

    Uses Uniswap V3 Quoter contract to get accurate swap quotes
    that account for liquidity depth and slippage.
    """

    # DEX fee tiers (Uniswap V3)
    FEE_TIERS = {
        100: Decimal("0.01"),    # 0.01% - stablecoins
        500: Decimal("0.05"),    # 0.05% - stable pairs
        3000: Decimal("0.30"),   # 0.30% - most pairs
        10000: Decimal("1.00"),  # 1.00% - exotic pairs
    }

    # Default fee tier for unknown pairs
    DEFAULT_FEE_PCT = Decimal("0.30")

    # Estimated gas costs in USD (varies by network congestion)
    GAS_ESTIMATES_USD = {
        1: Decimal("15.00"),      # Ethereum mainnet
        56: Decimal("0.30"),      # BSC
        137: Decimal("0.05"),     # Polygon
        42161: Decimal("0.50"),   # Arbitrum
    }

    def __init__(self, dex_client, chain_id: int = 1, dex_name: str = "uniswap_v3"):
        """
        Initialize DEX price feed.

        Args:
            dex_client: DEXClient instance
            chain_id: Blockchain chain ID (1=Ethereum, etc.)
            dex_name: DEX identifier (e.g., "uniswap_v3", "pancakeswap")
        """
        super().__init__(name=dex_name, exchange_type="dex")
        self.client = dex_client
        self.chain_id = chain_id

    async def get_price(self, base: str, quote: str) -> Optional[PriceQuote]:
        """
        Get current price quote from DEX.

        Uses the Quoter contract to get accurate swap prices that
        account for liquidity depth.

        Args:
            base: Base token symbol (e.g., "ETH", "WETH")
            quote: Quote token symbol (e.g., "USDT", "USDC")

        Returns:
            PriceQuote with bid/ask prices
        """
        try:
            # For DEX, we need to simulate swaps in both directions
            # to get accurate bid (sell) and ask (buy) prices

            # Get quote for buying base (selling quote)
            # This gives us the "ask" - price to buy
            ask_quote = await self.client.get_quote(
                token_in=quote,
                token_out=base,
                amount_in=Decimal("1000"),  # Use $1000 worth for better accuracy
            )

            # Get quote for selling base (buying quote)
            # This gives us the "bid" - price to sell
            bid_quote = await self.client.get_quote(
                token_in=base,
                token_out=quote,
                amount_in=Decimal("1"),  # 1 unit of base
            )

            if not ask_quote or not bid_quote:
                logger.warning(f"Could not get DEX quote for {base}-{quote}")
                return None

            # Calculate prices
            # ask_quote: 1000 USDT -> X ETH, so ask = 1000/X USDT per ETH
            ask_price = Decimal("1000") / ask_quote["amount_out"] if ask_quote["amount_out"] > 0 else Decimal("0")

            # bid_quote: 1 ETH -> Y USDT, so bid = Y USDT per ETH
            bid_price = bid_quote["amount_out"]

            # Get fee tier from quote
            fee_pct = self.FEE_TIERS.get(
                ask_quote.get("fee_tier", 3000),
                self.DEFAULT_FEE_PCT
            )

            # Estimate gas cost
            gas_estimate = self.GAS_ESTIMATES_USD.get(self.chain_id, Decimal("10.00"))

            return PriceQuote(
                exchange=self.name,
                exchange_type="dex",
                base=base,
                quote=quote,
                bid=bid_price,
                ask=ask_price,
                timestamp=datetime.utcnow(),
                taker_fee_pct=fee_pct,
                maker_fee_pct=fee_pct,  # No maker/taker distinction on DEX
                gas_estimate_usd=gas_estimate,
                chain_id=self.chain_id,
            )

        except Exception as e:
            logger.error(f"Error fetching DEX price for {base}-{quote}: {e}")
            return None

    async def get_orderbook(
        self, base: str, quote: str, depth: int = 10
    ) -> Optional[OrderBook]:
        """
        Simulate order book from DEX liquidity.

        DEXes don't have traditional order books, but we can simulate
        one by getting quotes at different size levels.

        Args:
            base: Base token symbol
            quote: Quote token symbol
            depth: Number of simulated levels

        Returns:
            Simulated OrderBook based on AMM liquidity curve
        """
        try:
            bids = []
            asks = []

            # Simulate order book by getting quotes at increasing sizes
            # This shows how price changes with size (slippage)
            sizes = [
                Decimal("100"),
                Decimal("500"),
                Decimal("1000"),
                Decimal("5000"),
                Decimal("10000"),
                Decimal("25000"),
                Decimal("50000"),
                Decimal("100000"),
                Decimal("250000"),
                Decimal("500000"),
            ][:depth]

            for size in sizes:
                # Get ask (buy) quote
                ask_quote = await self.client.get_quote(
                    token_in=quote,
                    token_out=base,
                    amount_in=size,
                )

                if ask_quote and ask_quote["amount_out"] > 0:
                    price = size / ask_quote["amount_out"]
                    asks.append(OrderBookLevel(
                        price=price,
                        quantity=ask_quote["amount_out"]
                    ))

                # Get bid (sell) quote
                # Convert size in quote to approximate base amount
                base_amount = size / (asks[-1].price if asks else Decimal("1000"))
                bid_quote = await self.client.get_quote(
                    token_in=base,
                    token_out=quote,
                    amount_in=base_amount,
                )

                if bid_quote and bid_quote["amount_out"] > 0:
                    price = bid_quote["amount_out"] / base_amount
                    bids.append(OrderBookLevel(
                        price=price,
                        quantity=base_amount
                    ))

            return OrderBook(
                exchange=self.name,
                exchange_type="dex",
                base=base,
                quote=quote,
                timestamp=datetime.utcnow(),
                bids=bids,
                asks=asks,
            )

        except Exception as e:
            logger.error(f"Error simulating DEX orderbook for {base}-{quote}: {e}")
            return None

    async def get_supported_pairs(self) -> List[str]:
        """
        Get list of commonly traded pairs on DEX.

        Note: DEXes support arbitrary pairs, but we return
        the most liquid/common ones.

        Returns:
            List of common trading pairs
        """
        # Common pairs vary by chain
        common_pairs = {
            1: [  # Ethereum
                "ETH-USDT", "ETH-USDC", "ETH-DAI",
                "WBTC-ETH", "WBTC-USDT", "WBTC-USDC",
                "LINK-ETH", "UNI-ETH", "AAVE-ETH",
            ],
            56: [  # BSC
                "BNB-USDT", "BNB-BUSD",
                "ETH-BNB", "BTCB-BNB",
                "CAKE-BNB", "CAKE-USDT",
            ],
            137: [  # Polygon
                "MATIC-USDT", "MATIC-USDC",
                "WETH-MATIC", "WBTC-WETH",
                "AAVE-MATIC", "LINK-MATIC",
            ],
            42161: [  # Arbitrum
                "ETH-USDT", "ETH-USDC",
                "WBTC-ETH", "ARB-ETH",
                "GMX-ETH", "LINK-ETH",
            ],
        }

        return common_pairs.get(self.chain_id, [])

    async def is_available(self) -> bool:
        """
        Check if DEX is available (RPC responsive).

        Returns:
            True if RPC endpoint is working
        """
        try:
            return await self.client.check_connection()
        except Exception:
            return False

    def get_fee_estimate(self, side: str, is_maker: bool = False) -> Decimal:
        """
        Get DEX swap fee (same for all swaps in a pool).

        Args:
            side: "buy" or "sell" (same fee either way)
            is_maker: Ignored for DEX

        Returns:
            Fee percentage
        """
        return self.DEFAULT_FEE_PCT

    def get_gas_estimate_usd(self) -> Decimal:
        """
        Get estimated gas cost in USD for this chain.

        Returns:
            Estimated gas cost in USD
        """
        return self.GAS_ESTIMATES_USD.get(self.chain_id, Decimal("10.00"))
