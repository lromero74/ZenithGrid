"""
Triangular Arbitrage Strategy

Exploits pricing inefficiencies within a single exchange by trading
through a 3-currency cycle. Example: ETH → BTC → USDT → ETH

If you end up with more ETH than you started with (after fees),
there's an arbitrage profit.

This strategy:
1. Builds a graph of all trading pairs
2. Finds 3-hop cycles returning to starting currency
3. Calculates net exchange rate around cycle
4. Executes if rate > 1 (profit exists)
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.strategies import StrategyDefinition, StrategyParameter, StrategyRegistry, TradingStrategy


@StrategyRegistry.register
class TriangularArbitrageStrategy(TradingStrategy):
    """
    Triangular arbitrage within a single exchange.

    Finds and exploits 3-way currency cycles where the product
    of exchange rates exceeds 1.
    """

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="triangular_arbitrage",
            name="Triangular Arbitrage",
            description="Profit from pricing inefficiencies through 3-way currency cycles on a single exchange",
            parameters=[
                # Base settings
                StrategyParameter(
                    name="base_currency",
                    display_name="Base Currency",
                    description="Currency to start and end with",
                    type="string",
                    default="ETH",
                    options=["ETH", "BTC", "USDT", "USDC"],
                    group="Base Settings",
                ),
                StrategyParameter(
                    name="trade_amount",
                    display_name="Trade Amount",
                    description="Amount to trade in base currency",
                    type="float",
                    default=0.5,
                    min_value=0.01,
                    max_value=100,
                    group="Base Settings",
                ),
                # Profit thresholds
                StrategyParameter(
                    name="min_profit_pct",
                    display_name="Minimum Profit %",
                    description="Minimum profit percentage to execute (after all fees)",
                    type="float",
                    default=0.1,
                    min_value=0.01,
                    max_value=2.0,
                    group="Profit Settings",
                ),
                StrategyParameter(
                    name="target_profit_pct",
                    display_name="Target Profit %",
                    description="Ideal profit percentage to aim for",
                    type="float",
                    default=0.3,
                    min_value=0.05,
                    max_value=5.0,
                    group="Profit Settings",
                ),
                # Scanning
                StrategyParameter(
                    name="scan_interval_ms",
                    display_name="Scan Interval (ms)",
                    description="How often to scan for opportunities",
                    type="int",
                    default=1000,
                    min_value=100,
                    max_value=10000,
                    group="Scanning",
                ),
                StrategyParameter(
                    name="max_paths_to_check",
                    display_name="Max Paths to Check",
                    description="Maximum triangular paths to evaluate per scan",
                    type="int",
                    default=20,
                    min_value=5,
                    max_value=100,
                    group="Scanning",
                ),
                StrategyParameter(
                    name="currencies_to_scan",
                    display_name="Currencies to Scan",
                    description="Which base currencies to check for triangular paths",
                    type="string",
                    default="ETH,BTC,USDT",
                    group="Scanning",
                ),
                # Risk management
                StrategyParameter(
                    name="max_trades_per_hour",
                    display_name="Max Trades Per Hour",
                    description="Maximum triangular trades per hour",
                    type="int",
                    default=20,
                    min_value=1,
                    max_value=100,
                    group="Risk Management",
                ),
                StrategyParameter(
                    name="execution_timeout_ms",
                    display_name="Execution Timeout (ms)",
                    description="Maximum time for all 3 legs to complete",
                    type="int",
                    default=5000,
                    min_value=1000,
                    max_value=30000,
                    group="Risk Management",
                ),
                StrategyParameter(
                    name="abort_on_partial_fill",
                    display_name="Abort on Partial Fill",
                    description="Cancel remaining orders if any leg partially fills",
                    type="bool",
                    default=True,
                    group="Risk Management",
                ),
                # Fees
                StrategyParameter(
                    name="fee_pct",
                    display_name="Trading Fee %",
                    description="Exchange trading fee percentage",
                    type="float",
                    default=0.1,
                    min_value=0.0,
                    max_value=1.0,
                    group="Fees",
                ),
            ],
            supported_products=["ETH-BTC", "BTC-USDT", "ETH-USDT", "ETH-USDC", "BTC-USDC"],
        )

    def validate_config(self):
        """Validate strategy configuration."""
        defaults = {
            "base_currency": "ETH",
            "trade_amount": 0.5,
            "min_profit_pct": 0.1,
            "target_profit_pct": 0.3,
            "scan_interval_ms": 1000,
            "max_paths_to_check": 20,
            "currencies_to_scan": "ETH,BTC,USDT",
            "max_trades_per_hour": 20,
            "execution_timeout_ms": 5000,
            "abort_on_partial_fill": True,
            "fee_pct": 0.1,
        }

        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

        # Parse currencies to scan
        if isinstance(self.config["currencies_to_scan"], str):
            self.config["currencies_list"] = [
                c.strip() for c in self.config["currencies_to_scan"].split(",")
            ]
        else:
            self.config["currencies_list"] = ["ETH", "BTC", "USDT"]

    async def analyze_signal(
        self,
        candles: List[Dict[str, Any]],
        current_price: float,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze exchange for triangular arbitrage opportunities.

        Args:
            candles: Not used (we need real-time prices)
            current_price: Reference price
            **kwargs: Must include:
                - triangular_detector: TriangularDetector instance

        Returns:
            Signal dict if profitable opportunity found
        """
        detector = kwargs.get("triangular_detector")

        if not detector:
            return None

        # Get currencies to scan
        currencies = self.config.get("currencies_list", ["ETH", "BTC", "USDT"])
        min_profit_pct = Decimal(str(self.config.get("min_profit_pct", 0.1)))
        trade_amount = Decimal(str(self.config.get("trade_amount", 1.0)))
        max_paths = self.config.get("max_paths_to_check", 20)

        # Find profitable paths
        profitable_paths = await detector.find_profitable_paths(
            start_currencies=currencies,
            min_profit_pct=min_profit_pct,
            start_amount=trade_amount,
            max_paths_per_currency=max_paths,
        )

        if not profitable_paths:
            return None

        # Get the best opportunity
        best = profitable_paths[0]

        return {
            "signal": "triangular_arbitrage",
            "action": "execute",
            "path": str(best.path),
            "currencies": best.path.currencies,
            "pairs": best.path.pairs,
            "directions": best.path.directions,
            "start_amount": float(best.start_amount),
            "end_amount": float(best.end_amount),
            "profit": float(best.profit),
            "profit_pct": float(best.profit_pct),
            "rates": [float(r) for r in best.rates],
            "fees": [float(f) for f in best.fees],
            "timestamp": str(best.timestamp),
        }

    async def should_buy(
        self,
        signal_data: Dict[str, Any],
        position: Optional[Any],
        btc_balance: float
    ) -> Tuple[bool, float, str]:
        """
        Determine if we should execute the triangular arbitrage.

        For triangular arb, all 3 legs execute together.

        Args:
            signal_data: Signal from analyze_signal
            position: Current position
            btc_balance: Available balance

        Returns:
            (should_execute, amount, reason)
        """
        if signal_data.get("signal") != "triangular_arbitrage":
            return False, 0.0, "Not a triangular arbitrage signal"

        start_amount = signal_data.get("start_amount", 0)
        profit_pct = signal_data.get("profit_pct", 0)
        path = signal_data.get("path", "Unknown")

        return True, start_amount, f"Triangular opportunity: {path} -> {profit_pct:.3f}% profit"

    async def should_sell(
        self,
        signal_data: Dict[str, Any],
        position: Any,
        current_price: float
    ) -> Tuple[bool, str]:
        """
        For triangular arb, the "sell" is part of the cycle.

        Args:
            signal_data: Signal from analyze_signal
            position: Current position
            current_price: Current price

        Returns:
            (should_sell, reason)
        """
        # Triangular arb is self-closing - no separate sell decision
        return False, "Triangular arbitrage is self-closing"

    def get_execution_plan(
        self,
        signal_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Generate execution plan for the 3 legs.

        Args:
            signal_data: Signal from analyze_signal

        Returns:
            List of 3 order specifications
        """
        pairs = signal_data.get("pairs", [])
        directions = signal_data.get("directions", [])
        rates = signal_data.get("rates", [])

        if len(pairs) != 3 or len(directions) != 3:
            return []

        start_amount = signal_data.get("start_amount", 0)
        current_amount = start_amount

        orders = []
        for i, (pair, direction, rate) in enumerate(zip(pairs, directions, rates)):
            if direction == "sell":
                # Selling base for quote
                base_amount = current_amount
                quote_amount = current_amount * rate
                next_amount = quote_amount
            else:
                # Buying base with quote
                quote_amount = current_amount
                base_amount = current_amount / rate
                next_amount = base_amount

            orders.append({
                "leg": i + 1,
                "pair": pair,
                "side": "SELL" if direction == "sell" else "BUY",
                "base_amount": base_amount,
                "quote_amount": quote_amount,
                "expected_rate": rate,
            })

            current_amount = next_amount

        return orders
