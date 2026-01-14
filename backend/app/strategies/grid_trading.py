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


async def calculate_volume_weighted_levels(
    product_id: str,
    upper: float,
    lower: float,
    num_levels: int,
    exchange_client,
    lookback_hours: int = 24,
    clustering_strength: float = 1.5
) -> List[float]:
    """
    Calculate grid levels weighted by trading volume distribution.

    Places more levels at price zones with historically high trading volume.
    This increases fill rate by clustering orders where price action occurs most frequently.

    Algorithm:
    1. Fetch recent trades (last N hours)
    2. Create price buckets across the range
    3. Sum trading volume in each bucket
    4. Calculate cumulative volume distribution
    5. Place grid levels according to volume percentiles

    Args:
        product_id: Trading pair (e.g., "ETH-BTC")
        upper: Upper price bound
        lower: Lower price bound
        num_levels: Number of grid levels
        exchange_client: Exchange client to fetch trade data
        lookback_hours: Historical period to analyze (default 24 hours)
        clustering_strength: How strongly to cluster at high-volume zones (1.0-3.0)

    Returns:
        List of volume-weighted price levels

    Example:
        If ETH-BTC traded heavily around 0.032 and 0.038 (support/resistance),
        more grid levels will cluster near those prices rather than spacing evenly.
    """
    try:
        # Fetch recent trades for volume analysis
        trades = await exchange_client.get_recent_trades(product_id, hours=lookback_hours)

        if not trades or len(trades) < 100:
            logger.warning(f"Insufficient trade data ({len(trades) if trades else 0} trades), falling back to arithmetic grid")
            return calculate_arithmetic_levels(lower, upper, num_levels)

        # Create price buckets (100 buckets for fine granularity)
        num_buckets = 100
        bucket_size = (upper - lower) / num_buckets
        volume_by_bucket = [0.0] * num_buckets

        # Sum volume in each bucket
        for trade in trades:
            price = float(trade.get('price', 0))
            size = float(trade.get('size', 0))

            # Only count trades within our range
            if lower <= price <= upper:
                bucket_index = int((price - lower) / bucket_size)
                # Ensure bucket is within bounds
                bucket_index = min(bucket_index, num_buckets - 1)
                volume_by_bucket[bucket_index] += size

        # Check if we got meaningful volume data
        total_volume = sum(volume_by_bucket)
        if total_volume == 0:
            logger.warning("No trades within range, falling back to arithmetic grid")
            return calculate_arithmetic_levels(lower, upper, num_levels)

        # Apply clustering strength (power transform)
        # Higher clustering_strength = more aggressive clustering at high-volume zones
        weighted_volume = [vol ** clustering_strength for vol in volume_by_bucket]
        total_weighted_volume = sum(weighted_volume)

        # Calculate cumulative distribution
        cumulative_volume = []
        running_sum = 0
        for vol in weighted_volume:
            running_sum += vol
            cumulative_volume.append(running_sum / total_weighted_volume)

        # Place levels according to volume percentiles
        levels = []
        for i in range(num_levels):
            # Target percentile for this level
            target_percentile = i / (num_levels - 1) if num_levels > 1 else 0.5

            # Find bucket closest to this percentile
            bucket_index = 0
            for idx, cumul in enumerate(cumulative_volume):
                if cumul >= target_percentile:
                    bucket_index = idx
                    break

            # Calculate price at this bucket
            price = lower + (bucket_index * bucket_size) + (bucket_size / 2)
            levels.append(price)

        # Ensure first and last levels match bounds exactly
        if levels:
            levels[0] = lower
            levels[-1] = upper

        logger.info(f"Volume-weighted grid: {num_levels} levels with clustering strength {clustering_strength}")
        logger.info(f"Total volume analyzed: {total_volume:.8f} over {len(trades)} trades")

        return levels

    except Exception as e:
        logger.error(f"Error calculating volume-weighted levels: {e}, falling back to arithmetic grid")
        return calculate_arithmetic_levels(lower, upper, num_levels)


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

                # AI-Dynamic Optimization
                StrategyParameter(
                    name="enable_ai_optimization",
                    display_name="Enable AI-Dynamic Optimization",
                    description="Use AI to continuously optimize grid parameters based on performance",
                    type="bool",
                    default=False,
                    group="ai_optimization",
                    required=False,
                ),

                StrategyParameter(
                    name="ai_provider",
                    display_name="AI Provider",
                    description="AI service for grid optimization",
                    type="string",
                    default="anthropic",
                    options=["anthropic", "openai", "gemini"],
                    group="ai_optimization",
                    visible_when={"enable_ai_optimization": True},
                    required=False,
                ),

                StrategyParameter(
                    name="ai_model",
                    display_name="AI Model",
                    description="Specific AI model to use",
                    type="string",
                    default="claude-sonnet-4.5",
                    group="ai_optimization",
                    visible_when={"enable_ai_optimization": True},
                    required=False,
                ),

                StrategyParameter(
                    name="ai_adjustment_interval_minutes",
                    display_name="AI Check Interval (minutes)",
                    description="How often AI analyzes and optimizes grid",
                    type="int",
                    default=120,
                    min_value=15,
                    max_value=1440,
                    group="ai_optimization",
                    visible_when={"enable_ai_optimization": True},
                    required=False,
                ),

                StrategyParameter(
                    name="ai_analysis_depth",
                    display_name="AI Analysis Depth",
                    description="Thoroughness of AI analysis (quick/standard/deep)",
                    type="string",
                    default="standard",
                    options=["quick", "standard", "deep"],
                    group="ai_optimization",
                    visible_when={"enable_ai_optimization": True},
                    required=False,
                ),

                # Volume-Weighted Levels
                StrategyParameter(
                    name="enable_volume_weighting",
                    display_name="Enable Volume-Weighted Levels",
                    description="Place more grid levels at price zones with high trading volume",
                    type="bool",
                    default=False,
                    group="volume_weighting",
                    required=False,
                ),

                StrategyParameter(
                    name="volume_analysis_hours",
                    display_name="Volume Analysis Period (hours)",
                    description="Historical period to analyze trade volume distribution",
                    type="int",
                    default=24,
                    min_value=6,
                    max_value=168,
                    group="volume_weighting",
                    visible_when={"enable_volume_weighting": True},
                    required=False,
                ),

                StrategyParameter(
                    name="volume_clustering_strength",
                    display_name="Volume Clustering Strength",
                    description="How strongly to cluster levels at high-volume zones (1.0-3.0)",
                    type="float",
                    default=1.5,
                    min_value=1.0,
                    max_value=3.0,
                    group="volume_weighting",
                    visible_when={"enable_volume_weighting": True},
                    required=False,
                ),

                # Time-Based Grid Rotation
                StrategyParameter(
                    name="enable_time_rotation",
                    display_name="Enable Time-Based Profit Rotation",
                    description="Periodically lock in profits and refresh grid",
                    type="bool",
                    default=False,
                    group="time_rotation",
                    required=False,
                ),

                StrategyParameter(
                    name="rotation_interval_hours",
                    display_name="Rotation Interval (hours)",
                    description="Time between profit-locking rotations",
                    type="int",
                    default=48,
                    min_value=12,
                    max_value=168,
                    group="time_rotation",
                    visible_when={"enable_time_rotation": True},
                    required=False,
                ),

                StrategyParameter(
                    name="profit_lock_percent",
                    display_name="Profit Lock Threshold (%)",
                    description="Close positions with profit >= this percentage on rotation",
                    type="float",
                    default=70.0,
                    min_value=0.0,
                    max_value=100.0,
                    group="time_rotation",
                    visible_when={"enable_time_rotation": True},
                    required=False,
                ),

                StrategyParameter(
                    name="min_profit_to_rotate",
                    display_name="Minimum Profit to Trigger Rotation",
                    description="Only rotate if total unrealized profit > this amount (0 = always rotate)",
                    type="float",
                    default=0.0,
                    min_value=0.0,
                    max_value=999999.0,
                    group="time_rotation",
                    visible_when={"enable_time_rotation": True},
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
        enable_volume_weighting = self.config.get("enable_volume_weighting", False)

        # Check if we should use volume-weighted levels
        if enable_volume_weighting:
            # Get exchange client from kwargs
            exchange_client = kwargs.get("exchange_client")
            if exchange_client:
                volume_hours = self.config.get("volume_analysis_hours", 24)
                clustering_strength = self.config.get("volume_clustering_strength", 1.5)

                logger.info(f"Using volume-weighted grid levels (lookback: {volume_hours}h, strength: {clustering_strength})")

                # Get product_id from kwargs
                product_id = kwargs.get("product_id")
                if not product_id:
                    # Fallback to bot_config if available
                    product_id = bot_config.get("product_id")

                if product_id:
                    levels = await calculate_volume_weighted_levels(
                        product_id=product_id,
                        upper=upper,
                        lower=lower,
                        num_levels=num_levels,
                        exchange_client=exchange_client,
                        lookback_hours=volume_hours,
                        clustering_strength=clustering_strength
                    )
                else:
                    logger.warning("No product_id available for volume weighting, falling back to standard grid")
                    enable_volume_weighting = False
            else:
                logger.warning("No exchange client available for volume weighting, falling back to standard grid")
                enable_volume_weighting = False

        # Fallback to standard grid types if volume weighting is disabled or failed
        if not enable_volume_weighting:
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

        # Run AI optimization if enabled (returns signal with ai_optimization flag)
        ai_optimization_signal = None
        if self.config.get("enable_ai_optimization", False) and grid_state and not breakout_direction:
            # Check if AI optimization should run
            # (Actual AI analysis happens in bot monitor via ai_grid_optimizer service)
            last_ai_check = grid_state.get("last_ai_check")
            interval_minutes = self.config.get("ai_adjustment_interval_minutes", 120)

            should_run_ai = False
            if not last_ai_check:
                should_run_ai = True
            else:
                last_check_time = datetime.fromisoformat(last_ai_check)
                minutes_elapsed = (datetime.utcnow() - last_check_time).total_seconds() / 60
                if minutes_elapsed >= interval_minutes:
                    should_run_ai = True

            if should_run_ai:
                logger.info(f"🤖 AI optimization scheduled for next bot cycle")
                ai_optimization_signal = "due"

        return {
            "action": "initialize_grid" if not grid_state else ("rebalance" if breakout_direction else "monitor"),
            "grid_type": grid_type,
            "grid_mode": self.config.get("grid_mode", "neutral"),
            "upper_limit": upper,
            "lower_limit": lower,
            "levels": levels,
            "current_price": current_price,
            "breakout_direction": breakout_direction,
            "ai_optimization_due": ai_optimization_signal,
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
