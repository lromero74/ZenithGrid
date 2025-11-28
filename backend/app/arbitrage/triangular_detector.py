"""
Triangular Arbitrage Detector

Finds profitable 3-way currency cycles within a single exchange.
Example: ETH → BTC → USDT → ETH

If the product of exchange rates around the cycle is > 1,
there's a profit opportunity.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class TriangularPath:
    """Represents a triangular arbitrage path through 3 currencies."""
    currencies: List[str]  # e.g., ["ETH", "BTC", "USDT", "ETH"]
    pairs: List[str]       # e.g., ["ETH-BTC", "BTC-USDT", "USDT-ETH"]
    directions: List[str]  # e.g., ["sell", "sell", "buy"] - direction for each leg

    @property
    def start_currency(self) -> str:
        return self.currencies[0]

    @property
    def is_valid(self) -> bool:
        """Check if path forms a valid cycle"""
        return (
            len(self.currencies) == 4 and
            len(self.pairs) == 3 and
            self.currencies[0] == self.currencies[-1]
        )

    def __str__(self) -> str:
        return " → ".join(self.currencies)


@dataclass
class PathProfit:
    """Profit calculation result for a triangular path."""
    path: TriangularPath
    start_amount: Decimal
    end_amount: Decimal
    profit: Decimal
    profit_pct: Decimal
    rates: List[Decimal]  # Exchange rate at each step
    fees: List[Decimal]   # Fee at each step
    is_profitable: bool
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def net_multiplier(self) -> Decimal:
        """Net multiplication factor around the cycle"""
        return self.end_amount / self.start_amount if self.start_amount > 0 else Decimal("0")


class TriangularDetector:
    """
    Detects profitable triangular arbitrage paths.

    Usage:
        detector = TriangularDetector(exchange_client)
        await detector.build_currency_graph()
        paths = detector.find_triangular_paths("ETH")
        for path in paths:
            profit = await detector.calculate_path_profit(path, Decimal("1.0"))
            if profit.is_profitable:
                print(f"Opportunity: {path} -> {profit.profit_pct}%")
    """

    def __init__(self, exchange_client, fee_pct: Decimal = Decimal("0.1")):
        """
        Initialize detector.

        Args:
            exchange_client: Exchange client for fetching prices
            fee_pct: Trading fee percentage (default 0.1%)
        """
        self.client = exchange_client
        self.fee_pct = fee_pct
        self.graph: Dict[str, Dict[str, str]] = {}  # currency -> {currency -> pair}
        self.pairs: Set[str] = set()
        self.last_build: Optional[datetime] = None

    async def build_currency_graph(self) -> int:
        """
        Build graph of all tradable currency pairs.

        Returns:
            Number of pairs in the graph
        """
        try:
            products = await self.client.get_products()

            self.graph = {}
            self.pairs = set()

            for product in products:
                # Skip disabled products
                if product.get("trading_disabled"):
                    continue

                product_id = product.get("product_id", "")
                if "-" not in product_id:
                    continue

                base, quote = product_id.split("-")

                # Add both directions to graph
                if base not in self.graph:
                    self.graph[base] = {}
                if quote not in self.graph:
                    self.graph[quote] = {}

                # Store the pair for both directions
                self.graph[base][quote] = product_id
                self.graph[quote][base] = product_id

                self.pairs.add(product_id)

            self.last_build = datetime.utcnow()
            logger.info(f"Built currency graph with {len(self.pairs)} pairs")
            return len(self.pairs)

        except Exception as e:
            logger.error(f"Error building currency graph: {e}")
            return 0

    def find_triangular_paths(
        self,
        start_currency: str,
        max_paths: int = 100
    ) -> List[TriangularPath]:
        """
        Find all 3-hop paths that return to the starting currency.

        Args:
            start_currency: Currency to start and end with (e.g., "ETH")
            max_paths: Maximum number of paths to return

        Returns:
            List of TriangularPath objects
        """
        if start_currency not in self.graph:
            logger.warning(f"Currency {start_currency} not in graph")
            return []

        paths = []

        # First hop: start_currency -> mid1
        for mid1 in self.graph.get(start_currency, {}):
            if mid1 == start_currency:
                continue

            pair1 = self.graph[start_currency][mid1]
            dir1 = self._get_direction(pair1, start_currency, mid1)

            # Second hop: mid1 -> mid2
            for mid2 in self.graph.get(mid1, {}):
                if mid2 == start_currency or mid2 == mid1:
                    continue

                pair2 = self.graph[mid1][mid2]
                dir2 = self._get_direction(pair2, mid1, mid2)

                # Third hop: mid2 -> start_currency (close the loop)
                if start_currency in self.graph.get(mid2, {}):
                    pair3 = self.graph[mid2][start_currency]
                    dir3 = self._get_direction(pair3, mid2, start_currency)

                    paths.append(TriangularPath(
                        currencies=[start_currency, mid1, mid2, start_currency],
                        pairs=[pair1, pair2, pair3],
                        directions=[dir1, dir2, dir3],
                    ))

                    if len(paths) >= max_paths:
                        return paths

        logger.debug(f"Found {len(paths)} triangular paths from {start_currency}")
        return paths

    def _get_direction(self, pair: str, from_currency: str, to_currency: str) -> str:
        """
        Determine trade direction for a hop.

        Args:
            pair: Trading pair (e.g., "ETH-BTC")
            from_currency: Currency we have
            to_currency: Currency we want

        Returns:
            "buy" or "sell"
        """
        base, quote = pair.split("-")

        if from_currency == base and to_currency == quote:
            # We have base, want quote -> sell base
            return "sell"
        elif from_currency == quote and to_currency == base:
            # We have quote, want base -> buy base
            return "buy"
        else:
            logger.warning(f"Invalid hop: {from_currency} -> {to_currency} via {pair}")
            return "unknown"

    async def calculate_path_profit(
        self,
        path: TriangularPath,
        start_amount: Decimal,
        include_fees: bool = True
    ) -> PathProfit:
        """
        Calculate expected profit for a triangular path.

        Args:
            path: Triangular path to evaluate
            start_amount: Amount of starting currency
            include_fees: Whether to include trading fees

        Returns:
            PathProfit with detailed calculation
        """
        current_amount = start_amount
        rates = []
        fees = []

        for i, (pair, direction) in enumerate(zip(path.pairs, path.directions)):
            try:
                # Get current price
                price = await self._get_execution_price(pair, direction, current_amount)

                if price is None or price <= 0:
                    return PathProfit(
                        path=path,
                        start_amount=start_amount,
                        end_amount=Decimal("0"),
                        profit=Decimal("0"),
                        profit_pct=Decimal("0"),
                        rates=[],
                        fees=[],
                        is_profitable=False,
                    )

                rates.append(price)

                # Calculate output amount
                if direction == "sell":
                    # Selling base for quote: amount * price
                    output = current_amount * price
                else:
                    # Buying base with quote: amount / price
                    output = current_amount / price

                # Apply fees
                fee = Decimal("0")
                if include_fees:
                    fee = output * (self.fee_pct / 100)
                    output = output - fee
                fees.append(fee)

                current_amount = output

            except Exception as e:
                logger.error(f"Error calculating profit for {pair}: {e}")
                return PathProfit(
                    path=path,
                    start_amount=start_amount,
                    end_amount=Decimal("0"),
                    profit=Decimal("0"),
                    profit_pct=Decimal("0"),
                    rates=[],
                    fees=[],
                    is_profitable=False,
                )

        profit = current_amount - start_amount
        profit_pct = (profit / start_amount * 100) if start_amount > 0 else Decimal("0")

        return PathProfit(
            path=path,
            start_amount=start_amount,
            end_amount=current_amount,
            profit=profit,
            profit_pct=profit_pct,
            rates=rates,
            fees=fees,
            is_profitable=profit > 0,
        )

    async def _get_execution_price(
        self,
        pair: str,
        direction: str,
        amount: Decimal
    ) -> Optional[Decimal]:
        """
        Get execution price for a trade.

        Args:
            pair: Trading pair
            direction: "buy" or "sell"
            amount: Trade amount

        Returns:
            Execution price
        """
        try:
            ticker = await self.client.get_ticker(pair)

            if not ticker:
                return None

            if direction == "buy":
                # Use ask price for buys
                return Decimal(str(ticker.get("ask", 0)))
            else:
                # Use bid price for sells
                return Decimal(str(ticker.get("bid", 0)))

        except Exception as e:
            logger.error(f"Error getting price for {pair}: {e}")
            return None

    async def find_profitable_paths(
        self,
        start_currencies: List[str],
        min_profit_pct: Decimal = Decimal("0.1"),
        start_amount: Decimal = Decimal("1000"),
        max_paths_per_currency: int = 50,
    ) -> List[PathProfit]:
        """
        Find all profitable triangular paths.

        Args:
            start_currencies: Currencies to check (e.g., ["ETH", "BTC", "USDT"])
            min_profit_pct: Minimum profit percentage to include
            start_amount: Amount to simulate trading
            max_paths_per_currency: Max paths to check per currency

        Returns:
            List of profitable PathProfit objects, sorted by profit
        """
        profitable = []

        for currency in start_currencies:
            paths = self.find_triangular_paths(currency, max_paths_per_currency)

            # Check paths concurrently (with some rate limiting)
            async def check_path(path: TriangularPath) -> Optional[PathProfit]:
                profit = await self.calculate_path_profit(path, start_amount)
                if profit.is_profitable and profit.profit_pct >= min_profit_pct:
                    return profit
                return None

            # Check in batches to avoid rate limits
            batch_size = 10
            for i in range(0, len(paths), batch_size):
                batch = paths[i:i + batch_size]
                results = await asyncio.gather(
                    *[check_path(p) for p in batch],
                    return_exceptions=True
                )

                for result in results:
                    if isinstance(result, PathProfit):
                        profitable.append(result)

                # Small delay between batches
                await asyncio.sleep(0.1)

        # Sort by profit percentage (highest first)
        profitable.sort(key=lambda p: p.profit_pct, reverse=True)

        return profitable

    def get_all_currencies(self) -> List[str]:
        """Get list of all currencies in the graph."""
        return list(self.graph.keys())

    def get_pair_count(self) -> int:
        """Get number of trading pairs."""
        return len(self.pairs)
