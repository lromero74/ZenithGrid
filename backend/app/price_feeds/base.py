"""
Base Price Feed Interface

Defines the abstract interface that all price feed implementations must follow.
This enables uniform access to pricing data across CEX and DEX sources.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import List, Optional


@dataclass
class OrderBookLevel:
    """Single level in an order book (price + quantity)"""
    price: Decimal
    quantity: Decimal

    @property
    def value(self) -> Decimal:
        """Total value at this level"""
        return self.price * self.quantity


@dataclass
class OrderBook:
    """Order book snapshot with bids and asks"""
    exchange: str
    exchange_type: str  # "cex" or "dex"
    base: str
    quote: str
    timestamp: datetime
    bids: List[OrderBookLevel] = field(default_factory=list)  # Sorted highest to lowest
    asks: List[OrderBookLevel] = field(default_factory=list)  # Sorted lowest to highest

    @property
    def product_id(self) -> str:
        return f"{self.base}-{self.quote}"

    @property
    def best_bid(self) -> Optional[Decimal]:
        """Best (highest) bid price"""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[Decimal]:
        """Best (lowest) ask price"""
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> Optional[Decimal]:
        """Absolute spread between best bid and ask"""
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None

    @property
    def spread_pct(self) -> Optional[Decimal]:
        """Spread as a percentage of mid price"""
        if self.best_bid and self.best_ask:
            mid = (self.best_bid + self.best_ask) / 2
            if mid > 0:
                return (self.spread / mid) * 100
        return None

    def get_execution_price(self, side: str, quantity: Decimal) -> Optional[Decimal]:
        """
        Calculate average execution price for a given quantity.

        Args:
            side: "buy" or "sell"
            quantity: Amount of base currency to trade

        Returns:
            Average execution price, or None if insufficient liquidity
        """
        levels = self.asks if side == "buy" else self.bids

        remaining = quantity
        total_cost = Decimal("0")

        for level in levels:
            fill_qty = min(remaining, level.quantity)
            total_cost += fill_qty * level.price
            remaining -= fill_qty

            if remaining <= 0:
                break

        if remaining > 0:
            return None  # Insufficient liquidity

        return total_cost / quantity


@dataclass
class PriceQuote:
    """Price quote from an exchange"""
    exchange: str
    exchange_type: str  # "cex" or "dex"
    base: str
    quote: str
    bid: Decimal  # Best bid (what you can sell at)
    ask: Decimal  # Best ask (what you can buy at)
    timestamp: datetime
    bid_size: Optional[Decimal] = None  # Quantity available at bid
    ask_size: Optional[Decimal] = None  # Quantity available at ask

    # Fee information
    taker_fee_pct: Decimal = Decimal("0.3")  # Default 0.3%
    maker_fee_pct: Decimal = Decimal("0.1")  # Default 0.1%

    # DEX-specific
    gas_estimate_usd: Optional[Decimal] = None  # Estimated gas cost in USD
    chain_id: Optional[int] = None

    @property
    def product_id(self) -> str:
        return f"{self.base}-{self.quote}"

    @property
    def mid(self) -> Decimal:
        """Mid-market price"""
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> Decimal:
        """Absolute spread"""
        return self.ask - self.bid

    @property
    def spread_pct(self) -> Decimal:
        """Spread as percentage of mid price"""
        if self.mid > 0:
            return (self.spread / self.mid) * 100
        return Decimal("0")

    def net_buy_price(self, include_gas: bool = True) -> Decimal:
        """
        Effective price to buy including fees.

        Returns ask price adjusted for taker fee.
        For DEX, optionally includes gas cost (requires knowing quantity).
        """
        fee_multiplier = 1 + (self.taker_fee_pct / 100)
        return self.ask * fee_multiplier

    def net_sell_price(self, include_gas: bool = True) -> Decimal:
        """
        Effective price to sell including fees.

        Returns bid price adjusted for taker fee.
        For DEX, optionally includes gas cost (requires knowing quantity).
        """
        fee_multiplier = 1 - (self.taker_fee_pct / 100)
        return self.bid * fee_multiplier


class PriceFeed(ABC):
    """
    Abstract base class for price feed implementations.

    Each price feed represents a single exchange or DEX and provides
    methods to retrieve current prices and order book data.
    """

    def __init__(self, name: str, exchange_type: str):
        """
        Initialize price feed.

        Args:
            name: Exchange name (e.g., "coinbase", "uniswap_v3")
            exchange_type: "cex" or "dex"
        """
        self.name = name
        self.exchange_type = exchange_type

    @abstractmethod
    async def get_price(self, base: str, quote: str) -> Optional[PriceQuote]:
        """
        Get current price quote for a trading pair.

        Args:
            base: Base currency (e.g., "ETH")
            quote: Quote currency (e.g., "USDT")

        Returns:
            PriceQuote with bid/ask prices, or None if pair not available
        """
        pass

    @abstractmethod
    async def get_orderbook(
        self, base: str, quote: str, depth: int = 10
    ) -> Optional[OrderBook]:
        """
        Get order book snapshot for a trading pair.

        Args:
            base: Base currency
            quote: Quote currency
            depth: Number of levels to retrieve (default 10)

        Returns:
            OrderBook with bids and asks, or None if pair not available
        """
        pass

    @abstractmethod
    async def get_supported_pairs(self) -> List[str]:
        """
        Get list of supported trading pairs.

        Returns:
            List of product IDs in "BASE-QUOTE" format
        """
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if the price feed is available and responsive.

        Returns:
            True if feed is working, False otherwise
        """
        pass

    def get_fee_estimate(self, side: str, is_maker: bool = False) -> Decimal:
        """
        Get estimated trading fee percentage.

        Args:
            side: "buy" or "sell"
            is_maker: True for maker orders, False for taker

        Returns:
            Fee as percentage (e.g., 0.3 for 0.3%)
        """
        # Override in subclasses for exchange-specific fees
        return Decimal("0.1") if is_maker else Decimal("0.3")
