"""
Statistical Arbitrage Strategy

Mean-reversion strategy based on price correlations between trading pairs.
When two correlated assets diverge beyond historical norms, bet on convergence.

This strategy:
1. Tracks price correlations between pairs
2. Calculates z-scores of the spread
3. Enters when z-score exceeds threshold (divergence)
4. Exits when z-score returns to normal (convergence)

Key concepts:
- Pairs trading: Long one, short the other
- Hedge ratio: Position sizing to maintain market neutrality
- Z-score: Standard deviations from mean spread
"""

from typing import Any, Dict, List, Optional, Tuple

from app.strategies import StrategyDefinition, StrategyParameter, StrategyRegistry, TradingStrategy


@StrategyRegistry.register
class StatisticalArbitrageStrategy(TradingStrategy):
    """
    Statistical arbitrage (pairs trading) strategy.

    Trades mean-reversion between correlated pairs using z-score signals.
    """

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="statistical_arbitrage",
            name="Statistical Arbitrage (Pairs Trading)",
            description="Trade mean-reversion between correlated pairs using z-score analysis",
            parameters=[
                # Pair selection
                StrategyParameter(
                    name="pair_1",
                    display_name="Pair 1",
                    description="First trading pair (e.g., ETH-USD)",
                    type="string",
                    default="ETH-USD",
                    group="Pair Selection",
                ),
                StrategyParameter(
                    name="pair_2",
                    display_name="Pair 2",
                    description="Second trading pair (should be correlated with pair 1)",
                    type="string",
                    default="ETH-BTC",
                    group="Pair Selection",
                ),
                # Analysis parameters
                StrategyParameter(
                    name="lookback_period",
                    display_name="Lookback Period (days)",
                    description="Historical data window for correlation analysis",
                    type="int",
                    default=30,
                    min_value=7,
                    max_value=90,
                    group="Analysis",
                ),
                StrategyParameter(
                    name="min_correlation",
                    display_name="Minimum Correlation",
                    description="Minimum required correlation coefficient to trade",
                    type="float",
                    default=0.7,
                    min_value=0.5,
                    max_value=0.95,
                    group="Analysis",
                ),
                # Entry/exit thresholds
                StrategyParameter(
                    name="z_score_entry",
                    display_name="Z-Score Entry Threshold",
                    description="Enter position when z-score exceeds this (typically 2.0)",
                    type="float",
                    default=2.0,
                    min_value=1.0,
                    max_value=4.0,
                    group="Thresholds",
                ),
                StrategyParameter(
                    name="z_score_exit",
                    display_name="Z-Score Exit Threshold",
                    description="Exit position when z-score falls below this (typically 0.5)",
                    type="float",
                    default=0.5,
                    min_value=0.0,
                    max_value=1.5,
                    group="Thresholds",
                ),
                StrategyParameter(
                    name="z_score_stop_loss",
                    display_name="Z-Score Stop Loss",
                    description="Exit if z-score goes further against us (e.g., 4.0)",
                    type="float",
                    default=4.0,
                    min_value=2.5,
                    max_value=6.0,
                    group="Thresholds",
                ),
                # Position sizing
                StrategyParameter(
                    name="position_size_usd",
                    display_name="Position Size (USD)",
                    description="Size of each leg in USD equivalent",
                    type="float",
                    default=500,
                    min_value=100,
                    max_value=50000,
                    group="Position Sizing",
                ),
                StrategyParameter(
                    name="use_hedge_ratio",
                    display_name="Use Hedge Ratio",
                    description="Size positions using calculated hedge ratio for market neutrality",
                    type="bool",
                    default=True,
                    group="Position Sizing",
                ),
                # Risk management
                StrategyParameter(
                    name="max_holding_period",
                    display_name="Max Holding Period (days)",
                    description="Maximum days to hold position before forced exit",
                    type="int",
                    default=14,
                    min_value=1,
                    max_value=60,
                    group="Risk Management",
                ),
                StrategyParameter(
                    name="max_open_positions",
                    display_name="Max Open Stat-Arb Positions",
                    description="Maximum concurrent statistical arbitrage positions",
                    type="int",
                    default=3,
                    min_value=1,
                    max_value=10,
                    group="Risk Management",
                ),
                StrategyParameter(
                    name="stop_loss_pct",
                    display_name="Stop Loss %",
                    description="Exit if combined position loses this percentage",
                    type="float",
                    default=5.0,
                    min_value=1.0,
                    max_value=20.0,
                    group="Risk Management",
                ),
            ],
            supported_products=["ETH-USD", "ETH-BTC", "BTC-USD", "ETH-USDT", "BTC-USDT"],
        )

    def validate_config(self):
        """Validate strategy configuration."""
        defaults = {
            "pair_1": "ETH-USD",
            "pair_2": "ETH-BTC",
            "lookback_period": 30,
            "min_correlation": 0.7,
            "z_score_entry": 2.0,
            "z_score_exit": 0.5,
            "z_score_stop_loss": 4.0,
            "position_size_usd": 500,
            "use_hedge_ratio": True,
            "max_holding_period": 14,
            "max_open_positions": 3,
            "stop_loss_pct": 5.0,
        }

        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

        # Validate thresholds
        if self.config["z_score_exit"] >= self.config["z_score_entry"]:
            self.config["z_score_exit"] = self.config["z_score_entry"] / 4

        if self.config["z_score_stop_loss"] <= self.config["z_score_entry"]:
            self.config["z_score_stop_loss"] = self.config["z_score_entry"] * 2

    async def analyze_signal(
        self,
        candles: List[Dict[str, Any]],
        current_price: float,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze pair correlation for statistical arbitrage signals.

        Args:
            candles: Not used directly (we need paired price history)
            current_price: Reference price
            **kwargs: Must include:
                - stat_analyzer: StatArbAnalyzer instance
                - has_position: Whether we have an existing position

        Returns:
            Signal dict if entry/exit opportunity found
        """
        analyzer = kwargs.get("stat_analyzer")
        has_position = kwargs.get("has_position", False)
        current_direction = kwargs.get("current_direction")  # "long_spread" or "short_spread"

        if not analyzer:
            return None

        pair_1 = self.config.get("pair_1", "ETH-USD")
        pair_2 = self.config.get("pair_2", "ETH-BTC")

        # Check correlation is sufficient
        correlation = analyzer.calculate_correlation(pair_1, pair_2)
        if not correlation:
            return None

        min_corr = self.config.get("min_correlation", 0.7)
        if abs(correlation.correlation) < min_corr:
            return None

        # Get z-score signal
        z_entry = self.config.get("z_score_entry", 2.0)
        z_exit = self.config.get("z_score_exit", 0.5)

        signal = analyzer.get_signal(
            pair_1=pair_1,
            pair_2=pair_2,
            entry_threshold=z_entry,
            exit_threshold=z_exit,
            current_position=current_direction,
        )

        if not signal:
            return None

        # Check for stop loss
        z_stop = self.config.get("z_score_stop_loss", 4.0)
        if has_position and abs(signal.z_score) >= z_stop:
            return {
                "signal": "stat_arb_stop_loss",
                "action": "exit",
                "pair_1": pair_1,
                "pair_2": pair_2,
                "z_score": signal.z_score,
                "reason": f"Z-score {signal.z_score:.2f} exceeded stop loss {z_stop}",
                "correlation": correlation.correlation,
                "hedge_ratio": correlation.hedge_ratio,
                "timestamp": str(signal.timestamp),
            }

        # Exit signal
        if signal.direction == "exit" and has_position:
            return {
                "signal": "stat_arb_exit",
                "action": "exit",
                "pair_1": pair_1,
                "pair_2": pair_2,
                "z_score": signal.z_score,
                "reason": f"Z-score converged to {signal.z_score:.2f}",
                "correlation": correlation.correlation,
                "hedge_ratio": correlation.hedge_ratio,
                "timestamp": str(signal.timestamp),
            }

        # Entry signal (only if no existing position)
        if signal.direction in ["long_spread", "short_spread"] and not has_position:
            position_size = self.config.get("position_size_usd", 500)
            hedge_ratio = correlation.hedge_ratio if self.config.get("use_hedge_ratio", True) else 1.0

            return {
                "signal": "stat_arb_entry",
                "action": "enter",
                "pair_1": pair_1,
                "pair_2": pair_2,
                "direction": signal.direction,
                "pair_1_action": signal.pair_1_action,
                "pair_2_action": signal.pair_2_action,
                "z_score": signal.z_score,
                "confidence": signal.confidence,
                "correlation": correlation.correlation,
                "hedge_ratio": hedge_ratio,
                "position_size_usd": position_size,
                "pair_1_size_usd": position_size,
                "pair_2_size_usd": position_size * hedge_ratio,
                "timestamp": str(signal.timestamp),
            }

        return None

    async def should_buy(
        self,
        signal_data: Dict[str, Any],
        position: Optional[Any],
        btc_balance: float
    ) -> Tuple[bool, float, str]:
        """
        Determine if we should enter a stat-arb position.

        For stat-arb, we buy one leg and sell the other.

        Args:
            signal_data: Signal from analyze_signal
            position: Current position (if any)
            btc_balance: Available balance

        Returns:
            (should_enter, amount, reason)
        """
        signal_type = signal_data.get("signal", "")

        if signal_type == "stat_arb_entry":
            direction = signal_data.get("direction", "")
            z_score = signal_data.get("z_score", 0)
            confidence = signal_data.get("confidence", 0)
            pair_1 = signal_data.get("pair_1", "")
            pair_2 = signal_data.get("pair_2", "")
            size = signal_data.get("position_size_usd", 0)

            return (
                True,
                size,
                f"Stat-arb: {direction} ({pair_1}/{pair_2}) z={z_score:.2f} conf={confidence:.0%}"
            )

        return False, 0.0, "Not a stat-arb entry signal"

    async def should_sell(
        self,
        signal_data: Dict[str, Any],
        position: Any,
        current_price: float
    ) -> Tuple[bool, str]:
        """
        Determine if we should exit a stat-arb position.

        Args:
            signal_data: Signal from analyze_signal
            position: Current position
            current_price: Current price

        Returns:
            (should_exit, reason)
        """
        signal_type = signal_data.get("signal", "")

        if signal_type == "stat_arb_exit":
            z_score = signal_data.get("z_score", 0)
            return True, f"Z-score converged to {z_score:.2f}"

        if signal_type == "stat_arb_stop_loss":
            z_score = signal_data.get("z_score", 0)
            return True, f"Stop loss triggered at z-score {z_score:.2f}"

        return False, "No exit signal"

    def get_position_sizes(
        self,
        signal_data: Dict[str, Any]
    ) -> Dict[str, Dict]:
        """
        Calculate position sizes for both legs.

        Args:
            signal_data: Signal from analyze_signal

        Returns:
            Dict with sizing for each pair
        """
        return {
            signal_data["pair_1"]: {
                "action": signal_data["pair_1_action"],
                "size_usd": signal_data["pair_1_size_usd"],
            },
            signal_data["pair_2"]: {
                "action": signal_data["pair_2_action"],
                "size_usd": signal_data["pair_2_size_usd"],
            },
        }
