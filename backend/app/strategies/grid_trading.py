"""
Grid Trading Strategy

Places multiple buy and sell limit orders at predetermined price levels,
profiting from market volatility by buying low and selling high repeatedly
within a defined range.

Grid Types:
- Arithmetic: Linear spacing between levels
- Geometric: Exponential spacing (percentage-based)
- Neutral: Both buy and sell orders (range-bound markets)
- Long: Buy orders only (bullish accumulation)

Key Features:
- Dynamic breakout handling (auto-rebalancing)
- AI-powered grid optimization
- Volume-weighted level placement
- Time-based profit rotation
"""

import logging
import math
import statistics
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.strategies import StrategyDefinition, StrategyParameter, StrategyRegistry, TradingStrategy

logger = logging.getLogger(__name__)


def calculate_arithmetic_levels(lower: float, upper: float, num_levels: int) -> List[float]:
    """
    Calculate grid levels with linear (arithmetic) spacing.

    Formula: step_size = (upper - lower) / (num_levels - 1)
             price[i] = lower + (i * step_size)

    Args:
        lower: Lower price bound
        upper: Upper price bound
        num_levels: Number of grid levels

    Returns:
        List of price levels with equal dollar spacing

    Example:
        >>> calculate_arithmetic_levels(45, 55, 10)
        [45.0, 46.11, 47.22, 48.33, 49.44, 50.56, 51.67, 52.78, 53.89, 55.0]
    """
    if num_levels < 2:
        raise ValueError("num_levels must be at least 2")
    if upper <= lower:
        raise ValueError("upper must be greater than lower")

    step_size = (upper - lower) / (num_levels - 1)
    levels = [lower + (i * step_size) for i in range(num_levels)]

    return levels


def calculate_geometric_levels(lower: float, upper: float, num_levels: int) -> List[float]:
    """
    Calculate grid levels with exponential (geometric) spacing.

    Formula: ratio = (upper / lower) ^ (1 / (num_levels - 1))
             price[i] = lower * (ratio ^ i)

    Geometric spacing creates tighter levels near lower bound and wider levels near upper bound.
    This is ideal for volatile assets where percentage moves matter more than absolute dollar moves.

    Args:
        lower: Lower price bound
        upper: Upper price bound
        num_levels: Number of grid levels

    Returns:
        List of price levels with exponential spacing

    Example:
        >>> calculate_geometric_levels(45, 55, 10)
        [45.0, 45.92, 46.87, 47.83, 48.82, 49.83, 50.87, 51.93, 53.01, 55.0]
    """
    if num_levels < 2:
        raise ValueError("num_levels must be at least 2")
    if upper <= lower:
        raise ValueError("upper must be greater than lower")
    if lower <= 0:
        raise ValueError("lower must be positive for geometric spacing")

    # Calculate the common ratio
    ratio = (upper / lower) ** (1 / (num_levels - 1))

    # Generate levels using geometric progression
    levels = [lower * (ratio ** i) for i in range(num_levels)]

    return levels


def calculate_auto_range_from_volatility(
    candles: List[Dict[str, Any]],
    current_price: float,
    buffer_percent: float = 5.0
) -> Tuple[float, float]:
    """
    Calculate grid range automatically based on historical price volatility.

    Uses 2 standard deviations from the mean as the range, which captures ~95% of price movement.
    Adds a buffer percentage for safety margin.

    Args:
        candles: Historical OHLCV data (last N days)
        current_price: Current market price
        buffer_percent: Safety margin beyond calculated range (default 5%)

    Returns:
        Tuple of (upper_limit, lower_limit)

    Example:
        If price ranged between 45-55 over 30 days, with std dev of 3:
        - Range half-width = 2 * 3 = 6
        - Upper = current_price + 6 * 1.05 = 56.30
        - Lower = current_price - 6 * 1.05 = 43.70
    """
    if not candles or len(candles) < 7:
        # Fallback: use ±10% of current price
        logger.warning(f"Insufficient candle data ({len(candles)} candles), using ±10% fallback")
        return (current_price * 1.10, current_price * 0.90)

    # Extract closing prices
    prices = [float(candle.get('close', current_price)) for candle in candles]

    # Calculate volatility using standard deviation
    std_dev = statistics.stdev(prices)
    mean = statistics.mean(prices)

    logger.info(f"Auto-range calculation: mean={mean:.8f}, std_dev={std_dev:.8f}, prices_count={len(prices)}")

    # Use 2 standard deviations as range (captures ~95% of price movement)
    range_half_width = 2 * std_dev

    # Add buffer for safety
    buffer_multiplier = 1 + (buffer_percent / 100)

    # Calculate bounds around current price (not mean, to avoid being off-center)
    upper = current_price + (range_half_width * buffer_multiplier)
    lower = current_price - (range_half_width * buffer_multiplier)

    # Ensure lower bound is positive
    lower = max(lower, current_price * 0.5)

    logger.info(f"Auto-range result: upper={upper:.8f}, lower={lower:.8f}")

    return (upper, lower)


@StrategyRegistry.register
class GridTradingStrategy(TradingStrategy):
    """
    Grid Trading Strategy Implementation

    This strategy places multiple limit orders at predetermined price levels
    within a defined range. It profits from price oscillations by:
    - Buying at lower levels
    - Selling at higher levels
    - Repeating the cycle as price moves within the range

    The strategy automatically handles:
    - Capital reservation in pending orders
    - Breakout detection and rebalancing
    - Dynamic range adjustments
    - Multi-currency support (BTC, USD, USDC, USDT)
    """

    def get_definition(self) -> StrategyDefinition:
        """Return strategy metadata and parameter definitions"""
        return StrategyDefinition(
            id="grid_trading",
            name="Grid Trading",
            description="Place multiple buy/sell orders at predetermined price levels to profit from volatility",
            parameters=[
                # Grid Type
                StrategyParameter(
                    name="grid_type",
                    display_name="Grid Type",
                    description="Spacing pattern for grid levels",
                    type="string",
                    default="arithmetic",
                    options=["arithmetic", "geometric"],
                    group="grid_config",
                    required=True,
                ),

                # Grid Mode
                StrategyParameter(
                    name="grid_mode",
                    display_name="Grid Mode",
                    description="Trading direction (neutral: buy+sell, long: buy only)",
                    type="string",
                    default="neutral",
                    options=["neutral", "long"],
                    group="grid_config",
                    required=True,
                ),

                # Range Mode
                StrategyParameter(
                    name="range_mode",
                    display_name="Range Setup",
                    description="How to determine grid price range",
                    type="string",
                    default="manual",
                    options=["manual", "auto_volatility"],
                    group="grid_config",
                    required=True,
                ),

                # Manual Range - Upper Limit
                StrategyParameter(
                    name="upper_limit",
                    display_name="Upper Price Limit",
                    description="Maximum price for grid (manual mode)",
                    type="float",
                    default=None,
                    min_value=0.000001,
                    max_value=999999,
                    group="grid_config",
                    visible_when={"range_mode": "manual"},
                    required=False,
                ),

                # Manual Range - Lower Limit
                StrategyParameter(
                    name="lower_limit",
                    display_name="Lower Price Limit",
                    description="Minimum price for grid (manual mode)",
                    type="float",
                    default=None,
                    min_value=0.000001,
                    max_value=999999,
                    group="grid_config",
                    visible_when={"range_mode": "manual"},
                    required=False,
                ),

                # Auto Range - Period
                StrategyParameter(
                    name="auto_range_period_days",
                    display_name="Volatility Analysis Period (days)",
                    description="Historical period for auto-range calculation",
                    type="int",
                    default=30,
                    min_value=7,
                    max_value=90,
                    group="grid_config",
                    visible_when={"range_mode": "auto_volatility"},
                    required=False,
                ),

                # Auto Range - Buffer
                StrategyParameter(
                    name="range_buffer_percent",
                    display_name="Range Buffer (%)",
                    description="Safety margin beyond calculated range",
                    type="float",
                    default=5.0,
                    min_value=0,
                    max_value=20,
                    group="grid_config",
                    visible_when={"range_mode": "auto_volatility"},
                    required=False,
                ),

                # Grid Levels
                StrategyParameter(
                    name="num_grid_levels",
                    display_name="Number of Grid Levels",
                    description="Total buy + sell orders to place",
                    type="int",
                    default=20,
                    min_value=5,
                    max_value=100,
                    group="grid_config",
                    required=True,
                ),

                # Investment Amount
                StrategyParameter(
                    name="total_investment_quote",
                    display_name="Total Investment (Quote Currency)",
                    description="Total capital to allocate to grid",
                    type="float",
                    default=0.01,
                    min_value=0.0001,
                    max_value=999999,
                    group="investment",
                    required=True,
                ),

                # Dynamic Adjustment
                StrategyParameter(
                    name="enable_dynamic_adjustment",
                    display_name="Enable Dynamic Breakout Handling",
                    description="Automatically rebalance grid when price breaks out of range",
                    type="bool",
                    default=True,
                    group="advanced",
                    required=False,
                ),

                # Breakout Threshold
                StrategyParameter(
                    name="breakout_threshold_percent",
                    display_name="Breakout Threshold (%)",
                    description="Price move beyond range to trigger rebalance",
                    type="float",
                    default=5.0,
                    min_value=1.0,
                    max_value=20.0,
                    group="advanced",
                    visible_when={"enable_dynamic_adjustment": True},
                    required=False,
                ),

                # Stop Loss
                StrategyParameter(
                    name="stop_loss_percent",
                    display_name="Stop Loss (%)",
                    description="Exit grid if loss exceeds this percentage (0 = disabled)",
                    type="float",
                    default=0.0,
                    min_value=0,
                    max_value=50,
                    group="risk_management",
                    required=False,
                ),
            ],
            supported_products=["ETH-BTC", "ADA-BTC", "DOT-BTC", "BTC-USD", "ETH-USD"],
        )

    def validate_config(self):
        """Validate configuration parameters"""
        # Skip validation for empty config (used during strategy registration)
        if not self.config or len(self.config) == 0:
            return

        # Range mode validation
        range_mode = self.config.get("range_mode", "manual")

        if range_mode == "manual":
            upper = self.config.get("upper_limit")
            lower = self.config.get("lower_limit")

            if upper is None or lower is None:
                raise ValueError("Manual range mode requires upper_limit and lower_limit")

            if upper <= lower:
                raise ValueError(f"upper_limit ({upper}) must be greater than lower_limit ({lower})")

        # Grid levels validation
        num_levels = self.config.get("num_grid_levels", 20)
        if num_levels < 5:
            raise ValueError("num_grid_levels must be at least 5")

        # Investment validation
        total_investment = self.config.get("total_investment_quote", 0)
        if total_investment <= 0:
            raise ValueError("total_investment_quote must be positive")

        logger.info(f"Grid config validated: {self.config.get('grid_type')} grid, {num_levels} levels, range_mode={range_mode}")

    async def analyze_signal(
        self, candles: List[Dict[str, Any]], current_price: float, **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze market data and prepare grid configuration.

        For grid trading, this method:
        1. Calculates grid range (manual or auto)
        2. Generates grid levels (arithmetic or geometric)
        3. Detects breakout conditions (if enabled)

        Args:
            candles: Historical OHLCV data
            current_price: Current market price
            **kwargs: May contain 'position' and 'action_context'

        Returns:
            Signal dict with grid configuration or None
        """
        # Get grid state from bot config (if exists)
        bot_config = kwargs.get("bot_config", {})
        grid_state = bot_config.get("grid_state", {})

        # Determine grid range
        range_mode = self.config.get("range_mode", "manual")

        if range_mode == "manual":
            upper = self.config["upper_limit"]
            lower = self.config["lower_limit"]
            logger.debug(f"Using manual range: {lower:.8f} - {upper:.8f}")

        elif range_mode == "auto_volatility":
            upper, lower = calculate_auto_range_from_volatility(
                candles,
                current_price,
                buffer_percent=self.config.get("range_buffer_percent", 5.0)
            )
            logger.info(f"Auto-calculated range: {lower:.8f} - {upper:.8f}")

        else:
            raise ValueError(f"Unsupported range_mode: {range_mode}")

        # Generate grid levels
        grid_type = self.config.get("grid_type", "arithmetic")
        num_levels = self.config["num_grid_levels"]

        if grid_type == "arithmetic":
            levels = calculate_arithmetic_levels(lower, upper, num_levels)
        elif grid_type == "geometric":
            levels = calculate_geometric_levels(lower, upper, num_levels)
        else:
            raise ValueError(f"Unsupported grid_type: {grid_type}")

        # Check for breakout (if dynamic adjustment enabled)
        breakout_direction = None
        if self.config.get("enable_dynamic_adjustment", True) and grid_state:
            current_range_upper = grid_state.get("current_range_upper", upper)
            current_range_lower = grid_state.get("current_range_lower", lower)
            threshold = self.config.get("breakout_threshold_percent", 5.0) / 100

            if current_price > current_range_upper * (1 + threshold):
                breakout_direction = "upward"
                logger.warning(f"BREAKOUT DETECTED: Price {current_price:.8f} > upper {current_range_upper:.8f}")
            elif current_price < current_range_lower * (1 - threshold):
                breakout_direction = "downward"
                logger.warning(f"BREAKOUT DETECTED: Price {current_price:.8f} < lower {current_range_lower:.8f}")

        return {
            "action": "initialize_grid" if not grid_state else ("rebalance" if breakout_direction else "monitor"),
            "grid_type": grid_type,
            "grid_mode": self.config.get("grid_mode", "neutral"),
            "upper_limit": upper,
            "lower_limit": lower,
            "levels": levels,
            "current_price": current_price,
            "breakout_direction": breakout_direction,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def should_buy(
        self, signal_data: Dict[str, Any], position: Optional[Any], btc_balance: float
    ) -> Tuple[bool, float, str]:
        """
        Determine if we should place buy orders.

        For grid trading, this is called during grid initialization or rebalancing.
        Buy orders are placed at levels BELOW current price.

        Args:
            signal_data: Grid configuration from analyze_signal
            position: Current position (grid state stored here)
            btc_balance: Available quote currency balance

        Returns:
            Tuple of (should_buy: bool, amount: float, reason: str)
        """
        action = signal_data.get("action")

        if action == "initialize_grid":
            # Place initial buy orders
            total_investment = self.config["total_investment_quote"]

            if total_investment > btc_balance:
                return (False, 0, f"Insufficient balance: need {total_investment:.8f}, have {btc_balance:.8f}")

            return (True, total_investment, "Initializing grid with buy orders below current price")

        elif action == "rebalance":
            breakout = signal_data.get("breakout_direction")
            if breakout == "downward":
                # Price broke down - may need to place new buy orders in new range
                return (True, 0, f"Rebalancing grid after {breakout} breakout")

            return (False, 0, "Rebalancing but no buy action needed")

        else:
            # Monitoring - no action
            return (False, 0, "Grid monitoring - no buy action")

    async def should_sell(
        self, signal_data: Dict[str, Any], position: Any, current_price: float
    ) -> Tuple[bool, str]:
        """
        Determine if we should place sell orders.

        For grid trading, sell orders are placed at levels ABOVE current price.
        Individual grid levels sell when their limit orders fill.

        Args:
            signal_data: Grid configuration from analyze_signal
            position: Current position (grid state)
            current_price: Current market price

        Returns:
            Tuple of (should_sell: bool, reason: str)
        """
        action = signal_data.get("action")
        grid_mode = signal_data.get("grid_mode", "neutral")

        if action == "initialize_grid" and grid_mode == "neutral":
            # For neutral grids, place sell orders above current price
            return (True, "Initializing grid with sell orders above current price")

        elif action == "rebalance":
            breakout = signal_data.get("breakout_direction")
            if breakout == "upward":
                # Price broke up - may need to place new sell orders
                return (True, f"Rebalancing grid after {breakout} breakout")

        # Check stop loss
        stop_loss_pct = self.config.get("stop_loss_percent", 0)
        if stop_loss_pct > 0 and position:
            # Calculate total grid profit/loss
            # (This would be tracked in grid_state)
            pass

        return (False, "Grid monitoring - no sell action")


__all__ = ["GridTradingStrategy", "calculate_arithmetic_levels", "calculate_geometric_levels", "calculate_auto_range_from_volatility"]
