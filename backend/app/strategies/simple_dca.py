"""
Simple DCA Strategy

Time-based Dollar Cost Averaging strategy.
Buys a fixed amount at regular intervals regardless of price.
Sells when profit target is reached.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.strategies import (
    StrategyDefinition,
    StrategyParameter,
    StrategyRegistry,
    TradingStrategy,
)


@StrategyRegistry.register
class SimpleDCAStrategy(TradingStrategy):
    """Simple time-based DCA strategy"""

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="simple_dca",
            name="Simple DCA Strategy",
            description="Time-based Dollar Cost Averaging. Buys fixed amount at regular intervals, "
                       "sells when profit target is reached.",
            parameters=[
                StrategyParameter(
                    name="timeframe",
                    display_name="Timeframe / Candle Interval",
                    description="Timeframe for price monitoring (e.g., 5min, 1hour, 1day)",
                    type="str",
                    default="FIVE_MINUTE",
                    options=["ONE_MINUTE", "FIVE_MINUTE", "FIFTEEN_MINUTE", "THIRTY_MINUTE", "ONE_HOUR", "TWO_HOUR", "SIX_HOUR", "ONE_DAY"]
                ),
                StrategyParameter(
                    name="buy_amount_btc",
                    display_name="Buy Amount (BTC)",
                    description="Fixed BTC amount to buy each interval",
                    type="float",
                    default=0.01,
                    min_value=0.0001,
                    max_value=1.0
                ),
                StrategyParameter(
                    name="buy_interval_hours",
                    display_name="Buy Interval (hours)",
                    description="Hours between each buy",
                    type="int",
                    default=24,
                    min_value=1,
                    max_value=168  # 1 week
                ),
                StrategyParameter(
                    name="max_position_size_btc",
                    display_name="Max Position Size (BTC)",
                    description="Maximum total BTC to accumulate in a position",
                    type="float",
                    default=0.1,
                    min_value=0.001,
                    max_value=10.0
                ),
                StrategyParameter(
                    name="take_profit_percentage",
                    display_name="Take Profit %",
                    description="Profit percentage at which to sell entire position",
                    type="float",
                    default=5.0,
                    min_value=0.5,
                    max_value=50.0
                ),
                StrategyParameter(
                    name="stop_loss_percentage",
                    display_name="Stop Loss %",
                    description="Loss percentage at which to sell entire position (0 = disabled)",
                    type="float",
                    default=0.0,
                    min_value=0.0,
                    max_value=50.0
                ),
            ],
            supported_products=["ETH-BTC", "BTC-USD", "ETH-USD", "SOL-USD", "LINK-USD"]
        )

    def validate_config(self):
        """Validate configuration parameters"""
        definition = self.get_definition()

        # Set defaults for missing parameters
        for param in definition.parameters:
            if param.name not in self.config:
                self.config[param.name] = param.default

        # Validate ranges
        for param in definition.parameters:
            value = self.config[param.name]
            if param.min_value is not None and value < param.min_value:
                raise ValueError(f"{param.display_name} must be >= {param.min_value}")
            if param.max_value is not None and value > param.max_value:
                raise ValueError(f"{param.display_name} must be <= {param.max_value}")

        # Track last buy time (will be managed externally in bot state)
        self.last_buy_time = None

    async def analyze_signal(
        self,
        candles: List[Dict[str, Any]],
        current_price: float
    ) -> Optional[Dict[str, Any]]:
        """
        Time-based signal - always returns a signal for evaluation

        The buy decision is made in should_buy() based on time elapsed
        """
        # Always return a signal - decision is time-based
        return {
            "signal_type": "time_check",
            "price": current_price,
            "timestamp": datetime.utcnow()
        }

    async def should_buy(
        self,
        signal_data: Dict[str, Any],
        position: Optional[Any],
        btc_balance: float
    ) -> Tuple[bool, float, str]:
        """
        Buy fixed amount if enough time has elapsed since last buy

        Logic:
        - Buy if buy_interval_hours has elapsed since last trade
        - Don't exceed max_position_size_btc
        - Ensure we have enough BTC balance
        """
        buy_amount = self.config["buy_amount_btc"]
        interval_hours = self.config["buy_interval_hours"]
        max_position = self.config["max_position_size_btc"]

        # Check if we have sufficient balance
        if btc_balance < buy_amount:
            return False, 0.0, f"Insufficient BTC balance (need {buy_amount:.8f})"

        # Check position size limit
        if position is not None:
            if position.total_btc_spent + buy_amount > max_position:
                return False, 0.0, f"Would exceed max position size ({max_position} BTC)"

        # Check time interval (this should be tracked in bot state/position)
        # For now, we'll rely on the trading engine to track this
        # If position exists, check last trade time
        if position is not None and hasattr(position, 'trades') and len(position.trades) > 0:
            last_trade = max(position.trades, key=lambda t: t.timestamp)
            time_since_last = datetime.utcnow() - last_trade.timestamp
            required_interval = timedelta(hours=interval_hours)

            if time_since_last < required_interval:
                hours_remaining = (required_interval - time_since_last).total_seconds() / 3600
                return False, 0.0, f"Next buy in {hours_remaining:.1f} hours"

        return True, buy_amount, f"DCA buy of {buy_amount:.8f} BTC"

    async def should_sell(
        self,
        signal_data: Dict[str, Any],
        position: Any,
        current_price: float
    ) -> Tuple[bool, str]:
        """
        Sell when take_profit or stop_loss is hit

        Logic:
        - Sell if profit >= take_profit_percentage
        - Sell if stop_loss_percentage > 0 and loss >= stop_loss_percentage
        """
        # Calculate current profit
        eth_value = position.total_eth_acquired * current_price
        current_profit_btc = eth_value - position.total_btc_spent
        current_profit_pct = (current_profit_btc / position.total_btc_spent) * 100

        take_profit = self.config["take_profit_percentage"]
        stop_loss = self.config["stop_loss_percentage"]

        # Check take profit
        if current_profit_pct >= take_profit:
            return True, f"Take profit hit: {current_profit_pct:.2f}% >= {take_profit}%"

        # Check stop loss (if enabled)
        if stop_loss > 0 and current_profit_pct <= -stop_loss:
            return True, f"Stop loss hit: {current_profit_pct:.2f}% <= -{stop_loss}%"

        return False, f"Holding (P&L: {current_profit_pct:.2f}%, Target: {take_profit}%)"
