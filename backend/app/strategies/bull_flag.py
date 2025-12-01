"""
Bull Flag Strategy

USD-based trading strategy that:
1. Scans coins in allowed categories for volume spikes (5x 50-day average)
2. Detects bull flag patterns (pole + pullback + confirmation)
3. Enters with trailing stop loss at pullback low
4. Sets trailing take profit target at 2x risk distance
5. Manages positions with TSL/TTP logic

No DCA - single entry, win/loss based on stops.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.strategies import (
    StrategyDefinition,
    StrategyParameter,
    StrategyRegistry,
    TradingStrategy,
)
from app.strategies.bull_flag_scanner import detect_bull_flag_pattern

logger = logging.getLogger(__name__)


@StrategyRegistry.register
class BullFlagStrategy(TradingStrategy):
    """
    Bull Flag Pattern Trading Strategy

    Scans USD pairs for volume spikes and bull flag patterns,
    enters with TSL at pullback low and TTP at 2x risk.
    """

    def get_definition(self) -> StrategyDefinition:
        """Return strategy metadata and parameter definitions."""
        return StrategyDefinition(
            id="bull_flag",
            name="Bull Flag Pattern",
            description=(
                "USD-based pattern trading. Scans coins for volume spikes (5x average) "
                "and bull flag patterns. Enters with trailing stop loss and trailing "
                "take profit. No DCA - single entry with win/loss based on stops."
            ),
            parameters=[
                # Pattern Detection Group
                StrategyParameter(
                    name="timeframe",
                    display_name="Analysis Timeframe",
                    description="Candle timeframe for pattern detection",
                    type="string",
                    default="FIFTEEN_MINUTE",
                    options=["FIVE_MINUTE", "FIFTEEN_MINUTE", "THIRTY_MINUTE", "ONE_HOUR", "TWO_HOUR"],
                    group="Pattern Detection",
                ),
                StrategyParameter(
                    name="volume_multiplier",
                    display_name="Volume Spike Threshold",
                    description="Multiple of 50-day average volume to trigger scan (e.g., 5 = 5x average)",
                    type="float",
                    default=5.0,
                    min_value=2.0,
                    max_value=20.0,
                    group="Pattern Detection",
                ),
                StrategyParameter(
                    name="min_pole_candles",
                    display_name="Min Pole Candles",
                    description="Minimum candles in the pole (uptrend)",
                    type="int",
                    default=3,
                    min_value=2,
                    max_value=10,
                    group="Pattern Detection",
                ),
                StrategyParameter(
                    name="min_pole_gain_pct",
                    display_name="Min Pole Gain %",
                    description="Minimum percentage gain required in the pole",
                    type="float",
                    default=3.0,
                    min_value=1.0,
                    max_value=20.0,
                    group="Pattern Detection",
                ),
                StrategyParameter(
                    name="min_pullback_candles",
                    display_name="Min Pullback Candles",
                    description="Minimum red candles in pullback (flag)",
                    type="int",
                    default=2,
                    min_value=1,
                    max_value=5,
                    group="Pattern Detection",
                ),
                StrategyParameter(
                    name="max_pullback_candles",
                    display_name="Max Pullback Candles",
                    description="Maximum candles allowed in pullback",
                    type="int",
                    default=8,
                    min_value=3,
                    max_value=15,
                    group="Pattern Detection",
                ),
                StrategyParameter(
                    name="pullback_retracement_max",
                    display_name="Max Retracement %",
                    description="Maximum percentage of pole that can be retraced",
                    type="float",
                    default=50.0,
                    min_value=20.0,
                    max_value=80.0,
                    group="Pattern Detection",
                ),
                # Risk Management Group
                StrategyParameter(
                    name="reward_risk_ratio",
                    display_name="Reward/Risk Ratio",
                    description="Take profit target as multiple of risk (e.g., 2 = 2x risk)",
                    type="float",
                    default=2.0,
                    min_value=1.0,
                    max_value=5.0,
                    group="Risk Management",
                ),
                # Budget Group
                StrategyParameter(
                    name="budget_mode",
                    display_name="Budget Mode",
                    description="How to calculate position size",
                    type="string",
                    default="percentage",
                    options=["fixed_usd", "percentage"],
                    group="Budget",
                ),
                StrategyParameter(
                    name="fixed_usd_amount",
                    display_name="Fixed USD Amount",
                    description="Fixed USD amount per position (when budget_mode=fixed_usd)",
                    type="float",
                    default=100.0,
                    min_value=10.0,
                    max_value=10000.0,
                    group="Budget",
                    visible_when={"budget_mode": "fixed_usd"},
                ),
                StrategyParameter(
                    name="budget_percentage",
                    display_name="Budget Percentage",
                    description="Percentage of aggregate USD value per position",
                    type="float",
                    default=5.0,
                    min_value=1.0,
                    max_value=50.0,
                    group="Budget",
                    visible_when={"budget_mode": "percentage"},
                ),
                StrategyParameter(
                    name="max_concurrent_positions",
                    display_name="Max Concurrent Positions",
                    description="Maximum number of open positions at once",
                    type="int",
                    default=5,
                    min_value=1,
                    max_value=20,
                    group="Budget",
                ),
            ],
            supported_products=["*-USD"],  # USD pairs only
        )

    def validate_config(self):
        """Validate configuration parameters."""
        # Set defaults if not provided
        if not self.config:
            self.config = {}

        # Apply defaults from definition
        definition = self.get_definition()
        for param in definition.parameters:
            if param.name not in self.config:
                self.config[param.name] = param.default

    async def analyze_signal(
        self,
        candles: List[Dict[str, Any]],
        current_price: float,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze market data and detect bull flag pattern.

        Args:
            candles: List of recent candle data
            current_price: Current market price
            **kwargs: Additional parameters (action_context, position, etc.)

        Returns:
            Signal data dict with pattern info, or None if no signal
        """
        if not candles or len(candles) < 10:
            return None

        # Build config for pattern detection
        pattern_config = {
            "min_pole_candles": self.config.get("min_pole_candles", 3),
            "min_pole_gain_pct": self.config.get("min_pole_gain_pct", 3.0),
            "min_pullback_candles": self.config.get("min_pullback_candles", 2),
            "max_pullback_candles": self.config.get("max_pullback_candles", 8),
            "pullback_retracement_max": self.config.get("pullback_retracement_max", 50.0),
            "reward_risk_ratio": self.config.get("reward_risk_ratio", 2.0),
        }

        # Detect pattern - returns (pattern, rejection_reason) tuple
        pattern, rejection_reason = detect_bull_flag_pattern(candles, pattern_config)

        if not pattern:
            logger.debug(f"Pattern detection failed: {rejection_reason}")
            return None

        return {
            "signal_type": "bull_flag_entry",
            "pattern": pattern,
            "entry_price": pattern["entry_price"],
            "stop_loss": pattern["stop_loss"],
            "take_profit_target": pattern["take_profit_target"],
            "current_price": current_price,
            "risk": pattern["risk"],
            "reward": pattern["reward"],
        }

    async def should_buy(
        self,
        signal_data: Dict[str, Any],
        position: Optional[Any],
        usd_balance: float,
        aggregate_value: Optional[float] = None
    ) -> Tuple[bool, float, str]:
        """
        Determine if we should buy and how much.

        Args:
            signal_data: Signal information from analyze_signal
            position: Current position (should be None for new entries)
            usd_balance: Available USD balance
            aggregate_value: Optional aggregate portfolio value (not used for USD strategy)

        Returns:
            Tuple of (should_buy: bool, usd_amount: float, reason: str)
        """
        # Only enter if no existing position
        if position is not None:
            return (False, 0.0, "Already have position, bull flag strategy doesn't DCA")

        if not signal_data or signal_data.get("signal_type") != "bull_flag_entry":
            return (False, 0.0, "No valid bull flag signal")

        pattern = signal_data.get("pattern")
        if not pattern or not pattern.get("pattern_valid"):
            return (False, 0.0, "Invalid pattern data")

        # Calculate position size based on budget mode
        budget_mode = self.config.get("budget_mode", "percentage")

        if budget_mode == "fixed_usd":
            usd_amount = self.config.get("fixed_usd_amount", 100.0)
        else:
            # Percentage mode
            budget_pct = self.config.get("budget_percentage", 5.0)
            usd_amount = usd_balance * (budget_pct / 100.0)

        # Minimum order check (Coinbase minimum is typically $1-10)
        min_order = 10.0  # USD minimum
        if usd_amount < min_order:
            return (False, 0.0, f"Position size ${usd_amount:.2f} below minimum ${min_order}")

        # Don't exceed available balance
        if usd_amount > usd_balance:
            usd_amount = usd_balance
            if usd_amount < min_order:
                return (False, 0.0, f"Insufficient balance: ${usd_balance:.2f}")

        reason = (
            f"Bull flag pattern detected. Entry: ${pattern['entry_price']:.4f}, "
            f"SL: ${pattern['stop_loss']:.4f}, TP: ${pattern['take_profit_target']:.4f}, "
            f"R:R={pattern['risk_reward_ratio']:.1f}x"
        )

        return (True, usd_amount, reason)

    async def should_sell(
        self,
        signal_data: Dict[str, Any],
        position: Any,
        current_price: float,
        market_context: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str]:
        """
        Determine if we should sell based on TSL/TTP.

        Note: The actual TSL/TTP logic is handled in the trading_engine/trailing_stops.py
        module. This method is for strategy-specific sell conditions.

        Args:
            signal_data: Signal information from analyze_signal
            position: Current position
            current_price: Current market price
            market_context: Optional market context data (not used for TSL/TTP)

        Returns:
            Tuple of (should_sell: bool, reason: str)
        """
        if not position:
            return (False, "No position to sell")

        # Get position's stop/target levels
        stop_loss = getattr(position, "trailing_stop_loss_price", None) or \
                    getattr(position, "entry_stop_loss", None)
        take_profit = getattr(position, "entry_take_profit_target", None)
        trailing_tp_active = getattr(position, "trailing_tp_active", False)

        # Check trailing stop loss (if not in TTP mode)
        if not trailing_tp_active and stop_loss and current_price <= stop_loss:
            return (True, f"Trailing stop loss triggered at ${current_price:.4f} (<= ${stop_loss:.4f})")

        # Check trailing take profit
        if trailing_tp_active:
            # When TTP is active, we trail from the peak
            highest_since_tp = getattr(position, "highest_price_since_tp", None)
            if highest_since_tp:
                # Calculate TTP trigger price (risk distance below peak)
                risk = getattr(position, "entry_stop_loss", 0)
                entry_price = position.average_buy_price
                if risk and entry_price:
                    risk_distance = entry_price - risk
                    ttp_trigger = highest_since_tp - risk_distance

                    if current_price <= ttp_trigger:
                        return (
                            True,
                            f"Trailing take profit triggered at ${current_price:.4f} "
                            f"(peak ${highest_since_tp:.4f}, trigger ${ttp_trigger:.4f})"
                        )

        return (False, "No sell condition met")

    def get_pattern_data_for_position(self, pattern: Dict[str, Any]) -> str:
        """Serialize pattern data for storage in position.pattern_data."""
        return json.dumps(pattern)

    def parse_pattern_data(self, pattern_data_str: str) -> Optional[Dict[str, Any]]:
        """Parse pattern data from position.pattern_data."""
        if not pattern_data_str:
            return None
        try:
            return json.loads(pattern_data_str)
        except json.JSONDecodeError:
            return None
