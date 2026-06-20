"""
Market Making Trading Strategy

Provides liquidity by placing simultaneous buy and sell limit orders
around a reference price (mid-price from order book, falling back to
current price), profiting from the bid-ask spread.

The strategy:
1. Computes a reference price (mid-price or current price fallback)
2. Places a buy order at reference - spread/2 and a sell order at reference + spread/2
3. Cancels and re-quotes when price moves beyond the recenter threshold
4. Skews order sizes toward the underweight side when inventory is unbalanced

Config:
    spread_bps: spread width in basis points (e.g. 20 = 0.20%)
    order_size: quote-currency amount per side (e.g. 100 = $100 each side)
    max_inventory: maximum base-asset units before skewing/pausing the buy side
    recenter_threshold_pct: price-move % that triggers a re-quote
    order_refresh_interval: minimum seconds between re-quotes
    quote_currency: "USD" or "BTC"
"""

import logging
import time
from typing import Any, Dict, List, Optional

from app.strategies import (
    StrategyDefinition,
    StrategyParameter,
    StrategyRegistry,
    TradingStrategy,
)

logger = logging.getLogger(__name__)

# Basis-point divisor (1 bps = 0.01%)
_BPS_DIVISOR = 10_000.0


@StrategyRegistry.register
class MarketMakingStrategy(TradingStrategy):
    """
    Market making strategy — places simultaneous bid and ask orders around
    the mid-price and re-quotes when the market moves beyond a threshold.

    Account-scoped: each instance holds only the state for the bot/account
    it was created for; no class-level cross-account data.
    """

    # Instance-level state (not shared across accounts — each bot gets its own instance)
    _last_quote_time: float = 0.0
    _last_reference_price: float = 0.0

    def __init__(self, config: Dict[str, Any]):
        # Reset per-instance state before validate_config() runs
        self._last_quote_time = 0.0
        self._last_reference_price = 0.0
        super().__init__(config)

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="market_making",
            name="Market Making",
            description=(
                "Provide liquidity by placing simultaneous buy and sell limit orders"
                " around the mid-price, profiting from the bid-ask spread"
            ),
            parameters=[
                StrategyParameter(
                    name="spread_bps",
                    display_name="Spread (bps)",
                    description="Total spread width in basis points (e.g. 20 = 0.20%)",
                    type="float",
                    default=20.0,
                    min_value=1.0,
                    max_value=500.0,
                ),
                StrategyParameter(
                    name="order_size",
                    display_name="Order Size (quote)",
                    description="Quote-currency amount to place on each side (buy and sell)",
                    type="float",
                    default=100.0,
                    min_value=1.0,
                ),
                StrategyParameter(
                    name="max_inventory",
                    display_name="Max Inventory (base)",
                    description=(
                        "Maximum base-asset units to hold before skewing "
                        "order sizes to reduce inventory"
                    ),
                    type="float",
                    default=0.1,
                    min_value=0.0,
                ),
                StrategyParameter(
                    name="recenter_threshold_pct",
                    display_name="Recenter Threshold %",
                    description="Price-move % from last reference that triggers a re-quote",
                    type="float",
                    default=0.5,
                    min_value=0.01,
                    max_value=10.0,
                ),
                StrategyParameter(
                    name="order_refresh_interval",
                    display_name="Order Refresh Interval (s)",
                    description="Minimum seconds between re-quotes",
                    type="float",
                    default=30.0,
                    min_value=1.0,
                    max_value=3600.0,
                ),
                StrategyParameter(
                    name="quote_currency",
                    display_name="Quote Currency",
                    description="Currency used as the quote (USD or BTC)",
                    type="string",
                    default="USD",
                    options=["USD", "BTC"],
                ),
            ],
        )

    def validate_config(self):
        """Validate strategy configuration."""
        spread_bps = float(self.config.get("spread_bps", 20.0))
        if spread_bps <= 0:
            logger.warning("market_making: spread_bps must be positive; got %s", spread_bps)

        order_size = float(self.config.get("order_size", 100.0))
        if order_size <= 0:
            logger.warning("market_making: order_size must be positive; got %s", order_size)

        max_inventory = float(self.config.get("max_inventory", 0.1))
        if max_inventory < 0:
            logger.warning("market_making: max_inventory cannot be negative; got %s", max_inventory)

    # ------------------------------------------------------------------
    # Public helpers (all pure / account-isolated)
    # ------------------------------------------------------------------

    def compute_reference_price(
        self,
        current_price: float,
        order_book: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Compute the reference (mid) price.

        Uses the order-book mid-price when available; falls back to current price.

        Args:
            current_price: Last traded / current market price.
            order_book: Optional dict with keys ``best_bid`` and ``best_ask``.

        Returns:
            Reference price to quote around.
        """
        if order_book:
            best_bid = order_book.get("best_bid")
            best_ask = order_book.get("best_ask")
            if best_bid and best_ask and best_bid > 0 and best_ask > 0 and best_ask > best_bid:
                return (best_bid + best_ask) / 2.0
        return current_price

    def compute_quote_prices(self, reference_price: float) -> Dict[str, float]:
        """Compute bid and ask prices for the given reference.

        Args:
            reference_price: Mid-price to quote around.

        Returns:
            Dict with keys ``bid_price`` and ``ask_price``.
        """
        spread_bps = float(self.config.get("spread_bps", 20.0))
        half_spread = reference_price * (spread_bps / 2.0) / _BPS_DIVISOR
        return {
            "bid_price": reference_price - half_spread,
            "ask_price": reference_price + half_spread,
        }

    def compute_inventory_skew(
        self,
        current_inventory: float,
    ) -> Dict[str, float]:
        """Compute order-size multipliers to mean-revert inventory.

        When inventory exceeds max_inventory, the buy-side size shrinks and
        the sell-side size grows proportionally, and vice versa.

        Args:
            current_inventory: Current base-asset holding (units, not quote).

        Returns:
            Dict with ``buy_multiplier`` and ``sell_multiplier`` (both in [0, 2]).
        """
        max_inventory = float(self.config.get("max_inventory", 0.1))
        if max_inventory <= 0:
            return {"buy_multiplier": 1.0, "sell_multiplier": 1.0}

        # Skew ratio: +1 = fully long (max buy), -1 = fully short (max sell)
        ratio = max(-1.0, min(1.0, current_inventory / max_inventory))

        # Positive inventory (long-heavy) → shrink buys, grow sells
        buy_multiplier = max(0.0, 1.0 - ratio)
        sell_multiplier = max(0.0, 1.0 + ratio)

        return {"buy_multiplier": buy_multiplier, "sell_multiplier": sell_multiplier}

    def needs_requote(
        self,
        current_price: float,
        now: Optional[float] = None,
    ) -> bool:
        """Determine whether the strategy should cancel and re-place its orders.

        Returns True when:
        - The refresh interval has elapsed since the last quote, OR
        - The price has moved beyond recenter_threshold_pct from the last reference.

        Args:
            current_price: Current market price.
            now: Current Unix timestamp (defaults to time.time()).
        """
        if now is None:
            now = time.time()

        refresh_interval = float(self.config.get("order_refresh_interval", 30.0))
        if now - self._last_quote_time >= refresh_interval:
            return True

        if self._last_reference_price <= 0:
            return True

        threshold = float(self.config.get("recenter_threshold_pct", 0.5))
        price_move_pct = abs(current_price - self._last_reference_price) / self._last_reference_price * 100.0
        return price_move_pct >= threshold

    def record_quote(self, reference_price: float, now: Optional[float] = None) -> None:
        """Update internal state after placing quotes.

        Args:
            reference_price: The reference price used for this quote cycle.
            now: Current Unix timestamp (defaults to time.time()).
        """
        if now is None:
            now = time.time()
        self._last_quote_time = now
        self._last_reference_price = reference_price

    # ------------------------------------------------------------------
    # TradingStrategy abstract interface
    # ------------------------------------------------------------------

    async def analyze_signal(
        self,
        candles: List[Dict[str, Any]],
        current_price: float,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """Compute market-making signal.

        Kwargs:
            order_book: optional dict with ``best_bid`` / ``best_ask``
            current_inventory: current base-asset units held (default 0.0)
            now: current Unix timestamp (injectable for testing)

        Returns:
            Signal dict with quoting instructions, or None if no requote needed.
        """
        order_book = kwargs.get("order_book")
        current_inventory = float(kwargs.get("current_inventory", 0.0))
        now = kwargs.get("now")

        if current_price <= 0:
            return None

        reference_price = self.compute_reference_price(current_price, order_book)
        requote = self.needs_requote(reference_price, now=now)

        if not requote:
            return {
                "signal_type": "hold",
                "confidence": 100,
                "reasoning": "Within refresh interval and recenter threshold — no requote needed",
                "indicators": {
                    "reference_price": reference_price,
                    "last_reference_price": self._last_reference_price,
                    "requote": False,
                },
            }

        quotes = self.compute_quote_prices(reference_price)
        skew = self.compute_inventory_skew(current_inventory)
        order_size = float(self.config.get("order_size", 100.0))

        buy_size = order_size * skew["buy_multiplier"]
        sell_size = order_size * skew["sell_multiplier"]

        self.record_quote(reference_price, now=now)

        return {
            "signal_type": "requote",
            "confidence": 100,
            "reasoning": "Placing market-making quotes around reference price",
            "indicators": {
                "reference_price": reference_price,
                "bid_price": quotes["bid_price"],
                "ask_price": quotes["ask_price"],
                "buy_size": buy_size,
                "sell_size": sell_size,
                "buy_multiplier": skew["buy_multiplier"],
                "sell_multiplier": skew["sell_multiplier"],
                "current_inventory": current_inventory,
                "requote": True,
            },
            "bid_price": quotes["bid_price"],
            "ask_price": quotes["ask_price"],
            "buy_size": buy_size,
            "sell_size": sell_size,
        }

    async def should_buy(
        self,
        signal_data: Dict[str, Any],
        position: Optional[Any],
        btc_balance: float,
    ) -> tuple:
        """Return buy decision from the market-making signal."""
        if signal_data.get("signal_type") != "requote":
            return False, 0.0, "No requote signal — skipping buy"

        buy_size = float(signal_data.get("buy_size", 0.0))
        bid_price = float(signal_data.get("bid_price", 0.0))

        if buy_size <= 0:
            return False, 0.0, "Buy size skewed to zero due to inventory limit"

        return (
            True,
            buy_size,
            f"Place bid at {bid_price:.8g} (size={buy_size:.4f} {self.config.get('quote_currency', 'USD')})",
        )

    async def should_sell(
        self,
        signal_data: Dict[str, Any],
        position: Any,
        current_price: float,
    ) -> tuple:
        """Return sell decision from the market-making signal."""
        if signal_data.get("signal_type") != "requote":
            return False, "No requote signal — skipping sell"

        sell_size = float(signal_data.get("sell_size", 0.0))
        ask_price = float(signal_data.get("ask_price", 0.0))

        if sell_size <= 0:
            return False, "Sell size skewed to zero due to inventory limit"

        return (
            True,
            f"Place ask at {ask_price:.8g} (size={sell_size:.4f} {self.config.get('quote_currency', 'USD')})",
        )
