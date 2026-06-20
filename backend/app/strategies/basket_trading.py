"""
Crypto Basket / Index Trading Strategy

Maintains a weighted basket of cryptocurrencies and auto-rebalances
when allocations drift beyond a configurable threshold.

The strategy:
1. Computes current portfolio weights from balances + prices
2. Compares to target weights
3. If any asset drifts beyond the threshold, generates rebalance signals
4. Signals include which assets to buy (underweight) and sell (overweight)

Config:
    basket_composition: [{"symbol": "BTC-USD", "target_weight": 40.0}, ...]
    rebalance_threshold: 5.0  # percent drift that triggers rebalance
    rebalance_interval_minutes: 60  # minimum time between rebalances
    quote_currency: "USD"  # base currency for valuation
"""

import logging
from typing import Any, Dict, List, Optional

from app.strategies import (
    StrategyDefinition,
    StrategyParameter,
    StrategyRegistry,
    TradingStrategy,
)

logger = logging.getLogger(__name__)


@StrategyRegistry.register
class BasketTradingStrategy(TradingStrategy):
    """
    Crypto basket / index trading strategy.

    Maintains a target allocation across multiple cryptocurrencies and
    generates rebalance signals when weights drift beyond a threshold.
    """

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="basket_trading",
            name="Crypto Basket / Index",
            description=(
                "Maintain a weighted basket of cryptocurrencies with"
                " automatic rebalancing when allocations drift"
            ),
            parameters=[
                StrategyParameter(
                    name="basket_composition",
                    display_name="Basket Composition",
                    description='List of {"symbol": "BTC-USD", "target_weight": 40.0}',
                    type="string",
                    default='[]',
                    required=True,
                ),
                StrategyParameter(
                    name="rebalance_threshold",
                    display_name="Rebalance Threshold %",
                    description="Percent drift from target that triggers rebalance",
                    type="float",
                    default=5.0,
                    min_value=1.0,
                    max_value=50.0,
                ),
                StrategyParameter(
                    name="rebalance_interval_minutes",
                    display_name="Min Rebalance Interval (min)",
                    description="Minimum minutes between rebalances",
                    type="float",
                    default=60.0,
                    min_value=1.0,
                    max_value=10080.0,
                ),
                StrategyParameter(
                    name="quote_currency",
                    display_name="Quote Currency",
                    description="Currency for valuation (USD or BTC)",
                    type="string",
                    default="USD",
                    options=["USD", "BTC"],
                ),
                StrategyParameter(
                    name="base_order_size",
                    display_name="Base Order Size",
                    description="Order size per rebalance trade (in quote currency)",
                    type="float",
                    default=50.0,
                    min_value=1.0,
                ),
                StrategyParameter(
                    name="max_concurrent_deals",
                    display_name="Max Concurrent Deals",
                    description="Maximum simultaneous positions",
                    type="int",
                    default=10,
                    min_value=1,
                    max_value=100,
                ),
            ],
        )

    def validate_config(self):
        """Validate strategy configuration."""
        composition = self._parse_composition()
        if not composition:
            return

        total_weight = sum(item["target_weight"] for item in composition)
        if total_weight <= 0:
            return  # Will be caught at runtime, not validation

        # Warn if weights don't sum to 100 (but don't fail — user may be building incrementally)
        if abs(total_weight - 100.0) > 0.01:
            logger.info(
                f"Basket weights sum to {total_weight:.1f}%, not 100%. "
                f"Weights will be normalized at runtime."
            )

    def _parse_composition(self) -> List[Dict[str, Any]]:
        """Parse basket_composition from config (may be a JSON string or list)."""
        import json
        raw = self.config.get("basket_composition", [])
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return []
        if isinstance(raw, list):
            return raw
        return []

    def get_target_weights(self) -> Dict[str, float]:
        """Return normalized target weights: {symbol: weight_pct}."""
        composition = self._parse_composition()
        if not composition:
            return {}

        total = sum(item["target_weight"] for item in composition)
        if total <= 0:
            return {}

        return {
            item["symbol"]: (item["target_weight"] / total) * 100.0
            for item in composition
        }

    def compute_current_weights(
        self,
        balances: Dict[str, float],
        prices: Dict[str, float],
    ) -> Dict[str, float]:
        """Compute current portfolio weights from balances and prices.

        Args:
            balances: {currency: amount} e.g. {"BTC": 0.5, "ETH": 3.0, "USD": 5000.0}
            prices: {product_id: price} e.g. {"BTC-USD": 100000.0, "ETH-USD": 3000.0}

        Returns:
            {currency: weight_pct} e.g. {"BTC": 40.0, "ETH": 30.0, "USD": 30.0}
        """
        quote = self.config.get("quote_currency", "USD")
        values: Dict[str, float] = {}

        for currency, amount in balances.items():
            if amount <= 0:
                continue
            if currency == quote:
                values[currency] = amount
            else:
                price_key = f"{currency}-{quote}"
                price = prices.get(price_key, 0.0)
                if price > 0:
                    values[currency] = amount * price
                else:
                    # Can't value this asset — skip it
                    logger.debug(f"Basket: no price for {price_key}, skipping {currency}")

        total_value = sum(values.values())
        if total_value <= 0:
            return {}

        return {ccy: (val / total_value) * 100.0 for ccy, val in values.items()}

    def compute_drift(
        self,
        current: Dict[str, float],
        target: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        """Compute drift between current and target weights.

        Returns a list of {currency, current_pct, target_pct, drift_pct, action}
        sorted by absolute drift (largest first).
        """
        all_currencies = set(list(current.keys()) + list(target.keys()))
        drifts: List[Dict[str, Any]] = []

        for ccy in all_currencies:
            curr_pct = current.get(ccy, 0.0)
            targ_pct = target.get(ccy, 0.0)
            drift = curr_pct - targ_pct
            action = "sell" if drift > 0 else "buy" if drift < 0 else "hold"
            drifts.append({
                "currency": ccy,
                "current_pct": round(curr_pct, 4),
                "target_pct": round(targ_pct, 4),
                "drift_pct": round(drift, 4),
                "abs_drift": abs(drift),
                "action": action,
            })

        drifts.sort(key=lambda d: d["abs_drift"], reverse=True)
        return drifts

    def needs_rebalance(self, drifts: List[Dict[str, Any]]) -> bool:
        """Check if any asset's drift exceeds the rebalance threshold."""
        threshold = float(self.config.get("rebalance_threshold", 5.0))
        return any(d["abs_drift"] >= threshold for d in drifts)

    async def analyze_signal(
        self,
        candles: List[Dict[str, Any]],
        current_price: float,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Analyze whether the basket needs rebalancing.

        Expects kwargs to include:
            - balances: {currency: amount}
            - prices: {product_id: price}

        Returns a signal dict with rebalance instructions if needed.
        """
        balances = kwargs.get("balances", {})
        prices = kwargs.get("prices", {})

        if not balances:
            return None

        target = self.get_target_weights()
        if not target:
            return None

        current = self.compute_current_weights(balances, prices)
        if not current:
            return None

        drifts = self.compute_drift(current, target)

        if not self.needs_rebalance(drifts):
            return {
                "signal_type": "hold",
                "confidence": 100,
                "reasoning": "Basket within rebalance threshold",
                "indicators": {
                    "current_weights": current,
                    "target_weights": target,
                    "max_drift": max(d["abs_drift"] for d in drifts) if drifts else 0.0,
                },
            }

        # Build rebalance instructions
        threshold = float(self.config.get("rebalance_threshold", 5.0))
        order_size = float(self.config.get("base_order_size", 50.0))

        trades_needed = []
        for d in drifts:
            if d["abs_drift"] < threshold:
                continue
            trades_needed.append({
                "currency": d["currency"],
                "action": d["action"],
                "drift_pct": d["drift_pct"],
                "current_pct": d["current_pct"],
                "target_pct": d["target_pct"],
                "order_size": order_size,
            })

        # Determine primary signal: if the largest drift is overweight, we sell first
        primary = trades_needed[0] if trades_needed else None
        signal_type = "hold"
        if primary:
            signal_type = "sell" if primary["action"] == "sell" else "buy"

        return {
            "signal_type": signal_type,
            "confidence": 100,
            "reasoning": f"Basket rebalance needed: {len(trades_needed)} trades",
            "indicators": {
                "current_weights": current,
                "target_weights": target,
                "max_drift": max(d["abs_drift"] for d in drifts) if drifts else 0.0,
                "drifts": drifts,
            },
            "rebalance_trades": trades_needed,
        }

    async def should_buy(
        self,
        signal_data: Dict[str, Any],
        position: Optional[Any],
        btc_balance: float,
    ) -> tuple:
        """Determine if a buy is needed for rebalancing."""
        trades = signal_data.get("rebalance_trades", [])
        buy_trades = [t for t in trades if t["action"] == "buy"]
        if not buy_trades:
            return False, 0.0, "No buy trades needed"

        order_size = float(self.config.get("base_order_size", 50.0))
        return True, order_size, f"Buy underweight assets: {[t['currency'] for t in buy_trades]}"

    async def should_sell(
        self,
        signal_data: Dict[str, Any],
        position: Any,
        current_price: float,
    ) -> tuple:
        """Determine if a sell is needed for rebalancing."""
        trades = signal_data.get("rebalance_trades", [])
        sell_trades = [t for t in trades if t["action"] == "sell"]
        if not sell_trades:
            return False, "No sell trades needed"

        return True, f"Sell overweight assets: {[t['currency'] for t in sell_trades]}"
