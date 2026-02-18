"""
Spatial Arbitrage Strategy

Cross-exchange arbitrage that exploits price differences between venues.
Buy on the exchange with the lower price, sell on the exchange with higher price.

This strategy:
1. Monitors prices across CEX and DEX venues
2. Identifies when price discrepancy exceeds trading costs
3. Executes simultaneous buy/sell orders
4. Tracks profit and adjusts position sizing

Requirements:
- Funds available on BOTH exchanges
- Low-latency execution
- Careful fee and slippage calculation
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.strategies import StrategyDefinition, StrategyParameter, StrategyRegistry, TradingStrategy


@StrategyRegistry.register
class SpatialArbitrageStrategy(TradingStrategy):
    """
    Cross-exchange (spatial) arbitrage strategy.

    Exploits price differences between centralized and decentralized exchanges.
    """

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="spatial_arbitrage",
            name="Spatial Arbitrage (Cross-Exchange)",
            description=(
                "Profit from price differences between CEX and DEX"
                " by buying low and selling high across venues"
            ),
            parameters=[
                # Profit thresholds
                StrategyParameter(
                    name="min_profit_pct",
                    display_name="Minimum Profit %",
                    description="Minimum net profit percentage after all fees to trigger trade",
                    type="float",
                    default=0.3,
                    min_value=0.1,
                    max_value=5.0,
                    group="Profit Settings",
                ),
                StrategyParameter(
                    name="target_profit_pct",
                    display_name="Target Profit %",
                    description="Ideal profit percentage to aim for",
                    type="float",
                    default=0.5,
                    min_value=0.2,
                    max_value=10.0,
                    group="Profit Settings",
                ),
                # Position sizing
                StrategyParameter(
                    name="max_position_size_usd",
                    display_name="Max Position Size (USD)",
                    description="Maximum trade size in USD equivalent",
                    type="float",
                    default=1000,
                    min_value=100,
                    max_value=100000,
                    group="Position Sizing",
                ),
                StrategyParameter(
                    name="min_position_size_usd",
                    display_name="Min Position Size (USD)",
                    description="Minimum trade size (must exceed exchange minimums)",
                    type="float",
                    default=50,
                    min_value=10,
                    max_value=1000,
                    group="Position Sizing",
                ),
                StrategyParameter(
                    name="position_size_pct",
                    display_name="Position Size % of Opportunity",
                    description="What percentage of the available arbitrage to capture",
                    type="float",
                    default=80,
                    min_value=10,
                    max_value=100,
                    group="Position Sizing",
                ),
                # Exchange selection
                StrategyParameter(
                    name="buy_exchange",
                    display_name="Buy Exchange",
                    description="Exchange to buy from (or 'auto' to choose best)",
                    type="string",
                    default="auto",
                    options=["auto", "coinbase", "uniswap_v3", "pancakeswap"],
                    group="Exchange Settings",
                ),
                StrategyParameter(
                    name="sell_exchange",
                    display_name="Sell Exchange",
                    description="Exchange to sell on (or 'auto' to choose best)",
                    type="string",
                    default="auto",
                    options=["auto", "coinbase", "uniswap_v3", "pancakeswap"],
                    group="Exchange Settings",
                ),
                # Risk management
                StrategyParameter(
                    name="slippage_tolerance",
                    display_name="Slippage Tolerance %",
                    description="Maximum acceptable slippage before aborting trade",
                    type="float",
                    default=0.5,
                    min_value=0.1,
                    max_value=3.0,
                    group="Risk Management",
                ),
                StrategyParameter(
                    name="execution_timeout_seconds",
                    display_name="Execution Timeout (seconds)",
                    description="Maximum time to complete both sides of the trade",
                    type="int",
                    default=30,
                    min_value=5,
                    max_value=120,
                    group="Risk Management",
                ),
                StrategyParameter(
                    name="max_daily_trades",
                    display_name="Max Daily Trades",
                    description="Maximum number of arbitrage trades per day",
                    type="int",
                    default=50,
                    min_value=1,
                    max_value=500,
                    group="Risk Management",
                ),
                StrategyParameter(
                    name="include_gas_in_calc",
                    display_name="Include Gas Fees",
                    description="Account for gas fees when calculating DEX profitability",
                    type="bool",
                    default=True,
                    group="Fee Settings",
                ),
                # Monitoring
                StrategyParameter(
                    name="scan_interval_seconds",
                    display_name="Scan Interval (seconds)",
                    description="How often to scan for opportunities",
                    type="int",
                    default=5,
                    min_value=1,
                    max_value=60,
                    group="Monitoring",
                ),
            ],
            supported_products=["ETH-USDT", "ETH-USDC", "BTC-USDT", "BTC-USDC", "ETH-BTC"],
        )

    def validate_config(self):
        """Validate strategy configuration."""
        # Set defaults for missing values
        defaults = {
            "min_profit_pct": 0.3,
            "target_profit_pct": 0.5,
            "max_position_size_usd": 1000,
            "min_position_size_usd": 50,
            "position_size_pct": 80,
            "buy_exchange": "auto",
            "sell_exchange": "auto",
            "slippage_tolerance": 0.5,
            "execution_timeout_seconds": 30,
            "max_daily_trades": 50,
            "include_gas_in_calc": True,
            "scan_interval_seconds": 5,
        }

        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

        # Validate constraints
        if self.config["min_profit_pct"] > self.config["target_profit_pct"]:
            self.config["min_profit_pct"] = self.config["target_profit_pct"]

        if self.config["min_position_size_usd"] > self.config["max_position_size_usd"]:
            self.config["min_position_size_usd"] = self.config["max_position_size_usd"] / 2

    async def analyze_signal(
        self,
        candles: List[Dict[str, Any]],
        current_price: float,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze prices across exchanges for arbitrage opportunities.

        Args:
            candles: Not used for arbitrage (we need real-time prices)
            current_price: Reference price
            **kwargs: Must include:
                - price_aggregator: PriceAggregator instance
                - base: Base currency
                - quote: Quote currency

        Returns:
            Signal dict if profitable opportunity found
        """
        price_aggregator = kwargs.get("price_aggregator")
        base = kwargs.get("base", "ETH")
        quote = kwargs.get("quote", "USDT")

        if not price_aggregator:
            return None

        # Get aggregated prices
        prices = await price_aggregator.get_best_prices(base, quote)

        if not prices.best_buy or not prices.best_sell:
            return None

        # Check if exchanges match user preference
        buy_exchange = self.config.get("buy_exchange", "auto")
        sell_exchange = self.config.get("sell_exchange", "auto")

        if buy_exchange != "auto" and prices.best_buy.exchange != buy_exchange:
            return None
        if sell_exchange != "auto" and prices.best_sell.exchange != sell_exchange:
            return None

        # Calculate position size based on available liquidity and config
        max_size_usd = Decimal(str(self.config["max_position_size_usd"]))
        # Reserved for future validation
        _min_size_usd = Decimal(str(self.config["min_position_size_usd"]))  # noqa: F841

        # Use position_size_pct of max to be conservative
        target_size_usd = max_size_usd * Decimal(str(self.config["position_size_pct"])) / 100

        # Calculate profit
        profit_calc = prices.calculate_profit(
            quantity=target_size_usd / prices.best_buy.ask,
            include_fees=True,
            include_gas=self.config.get("include_gas_in_calc", True),
        )

        if not profit_calc or not profit_calc["is_profitable"]:
            return None

        # Check against minimum profit threshold
        min_profit_pct = Decimal(str(self.config["min_profit_pct"]))
        if profit_calc["net_profit_pct"] < min_profit_pct:
            return None

        # Found a profitable opportunity!
        return {
            "signal": "spatial_arbitrage",
            "action": "execute",
            "base": base,
            "quote": quote,
            "buy_exchange": prices.best_buy.exchange,
            "buy_exchange_type": prices.best_buy.exchange_type,
            "buy_price": float(prices.best_buy.ask),
            "sell_exchange": prices.best_sell.exchange,
            "sell_exchange_type": prices.best_sell.exchange_type,
            "sell_price": float(prices.best_sell.bid),
            "spread": float(prices.spread or 0),
            "spread_pct": float(prices.spread_pct or 0),
            "quantity": float(profit_calc["quantity"]),
            "quantity_usd": float(target_size_usd),
            "estimated_profit": float(profit_calc["net_profit"]),
            "estimated_profit_pct": float(profit_calc["net_profit_pct"]),
            "buy_cost": float(profit_calc["buy_cost"]),
            "sell_revenue": float(profit_calc["sell_revenue"]),
            "timestamp": str(prices.timestamp),
        }

    async def should_buy(
        self,
        signal_data: Dict[str, Any],
        position: Optional[Any],
        btc_balance: float
    ) -> Tuple[bool, float, str]:
        """
        Determine if we should execute the buy side of arbitrage.

        For spatial arbitrage, both buy and sell happen simultaneously,
        so this is always True if we have a valid signal.

        Args:
            signal_data: Signal from analyze_signal
            position: Current position (usually None for arb)
            btc_balance: Available balance

        Returns:
            (should_buy, amount, reason)
        """
        if signal_data.get("signal") != "spatial_arbitrage":
            return False, 0.0, "Not an arbitrage signal"

        # Check if we have enough balance
        buy_cost = signal_data.get("buy_cost", 0)
        available = btc_balance  # This should be in quote currency

        if buy_cost > available:
            return False, 0.0, f"Insufficient balance: need {buy_cost}, have {available}"

        quantity = signal_data.get("quantity", 0)
        profit_pct = signal_data.get("estimated_profit_pct", 0)

        return True, quantity, f"Arbitrage opportunity: {profit_pct:.2f}% profit"

    async def should_sell(
        self,
        signal_data: Dict[str, Any],
        position: Any,
        current_price: float
    ) -> Tuple[bool, str]:
        """
        Determine if we should execute the sell side of arbitrage.

        For spatial arbitrage, sell always happens with buy (simultaneous).

        Args:
            signal_data: Signal from analyze_signal
            position: Current position
            current_price: Current price

        Returns:
            (should_sell, reason)
        """
        if signal_data.get("signal") != "spatial_arbitrage":
            return False, "Not an arbitrage signal"

        # Arbitrage sells are always executed with the buy
        return True, "Simultaneous arbitrage execution"

    def calculate_optimal_size(
        self,
        buy_liquidity: Decimal,
        sell_liquidity: Decimal,
        spread_pct: Decimal,
    ) -> Decimal:
        """
        Calculate optimal position size based on liquidity and spread.

        Args:
            buy_liquidity: Available liquidity on buy side
            sell_liquidity: Available liquidity on sell side
            spread_pct: Current spread percentage

        Returns:
            Optimal trade size in quote currency
        """
        # Use minimum of available liquidity
        max_by_liquidity = min(buy_liquidity, sell_liquidity)

        # Scale down based on spread (larger spread = more confident, can do more)
        confidence_multiplier = min(Decimal("1"), spread_pct / Decimal("1"))

        # Apply position size limits
        max_size = Decimal(str(self.config["max_position_size_usd"]))
        min_size = Decimal(str(self.config["min_position_size_usd"]))

        optimal = min(max_by_liquidity * confidence_multiplier, max_size)
        return max(optimal, min_size)
