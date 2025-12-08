"""
Statistical Arbitrage Analyzer

Analyzes price correlations between trading pairs to identify
mean-reversion opportunities. When two normally-correlated assets
diverge beyond historical norms, bet on convergence.

Example: ETH-USD and ETH-BTC usually move together.
If ETH-BTC drops while ETH-USD stays flat, ETH-BTC is "undervalued"
relative to historical correlation. Buy ETH-BTC, short ETH-USD.
When they converge back, close both for profit.
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class PricePoint:
    """Single price observation."""
    timestamp: datetime
    price: float


@dataclass
class PairCorrelation:
    """Correlation analysis between two pairs."""
    pair_1: str
    pair_2: str
    correlation: float          # Pearson correlation coefficient
    cointegration_pvalue: float  # p-value from cointegration test
    hedge_ratio: float          # Optimal hedge ratio
    lookback_days: int
    sample_size: int
    is_cointegrated: bool       # p-value < 0.05

    @property
    def is_suitable_for_stat_arb(self) -> bool:
        """Check if pair is suitable for statistical arbitrage."""
        return (
            abs(self.correlation) > 0.7 and
            self.is_cointegrated and
            self.sample_size >= 100
        )


@dataclass
class ZScoreSignal:
    """Z-score based trading signal."""
    pair_1: str
    pair_2: str
    z_score: float
    direction: str  # "long_spread" or "short_spread"
    confidence: float
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def pair_1_action(self) -> str:
        """Action for pair 1."""
        return "buy" if self.direction == "long_spread" else "sell"

    @property
    def pair_2_action(self) -> str:
        """Action for pair 2 (opposite of pair 1)."""
        return "sell" if self.direction == "long_spread" else "buy"


class StatArbAnalyzer:
    """
    Statistical arbitrage analyzer.

    Tracks price history for multiple pairs and identifies
    mean-reversion opportunities based on z-scores.

    Usage:
        analyzer = StatArbAnalyzer(lookback_days=30)
        await analyzer.update_price("ETH-USD", 3500.0)
        await analyzer.update_price("ETH-BTC", 0.05)

        signal = analyzer.get_signal("ETH-USD", "ETH-BTC", entry_threshold=2.0)
        if signal:
            print(f"Trade: {signal.direction} with z-score {signal.z_score}")
    """

    def __init__(
        self,
        lookback_days: int = 30,
        max_history_points: int = 10000,
    ):
        """
        Initialize analyzer.

        Args:
            lookback_days: Days of price history to use for analysis
            max_history_points: Maximum price points to store per pair
        """
        self.lookback_days = lookback_days
        self.max_history_points = max_history_points
        self.price_history: Dict[str, Deque[PricePoint]] = {}
        self._correlation_cache: Dict[Tuple[str, str], PairCorrelation] = {}
        self._cache_expiry: Dict[Tuple[str, str], datetime] = {}

    async def update_price(self, pair: str, price: float, timestamp: Optional[datetime] = None):
        """
        Add a new price observation.

        Args:
            pair: Trading pair (e.g., "ETH-USD")
            price: Current price
            timestamp: Price timestamp (default: now)
        """
        if pair not in self.price_history:
            self.price_history[pair] = deque(maxlen=self.max_history_points)

        ts = timestamp or datetime.utcnow()
        self.price_history[pair].append(PricePoint(timestamp=ts, price=price))

        # Trim old data
        cutoff = datetime.utcnow() - timedelta(days=self.lookback_days + 1)
        while self.price_history[pair] and self.price_history[pair][0].timestamp < cutoff:
            self.price_history[pair].popleft()

    def get_prices(self, pair: str) -> List[float]:
        """Get price history for a pair."""
        if pair not in self.price_history:
            return []
        return [p.price for p in self.price_history[pair]]

    def calculate_correlation(
        self,
        pair_1: str,
        pair_2: str,
        use_cache: bool = True,
        cache_minutes: int = 5,
    ) -> Optional[PairCorrelation]:
        """
        Calculate correlation between two pairs.

        Args:
            pair_1: First trading pair
            pair_2: Second trading pair
            use_cache: Use cached correlation if available
            cache_minutes: Cache validity in minutes

        Returns:
            PairCorrelation object or None if insufficient data
        """
        cache_key = (pair_1, pair_2)

        # Check cache
        if use_cache and cache_key in self._correlation_cache:
            if datetime.utcnow() < self._cache_expiry.get(cache_key, datetime.min):
                return self._correlation_cache[cache_key]

        prices_1 = self.get_prices(pair_1)
        prices_2 = self.get_prices(pair_2)

        if len(prices_1) < 100 or len(prices_2) < 100:
            logger.warning(f"Insufficient data for correlation: {pair_1}={len(prices_1)}, {pair_2}={len(prices_2)}")
            return None

        # Align price series (use minimum length)
        min_len = min(len(prices_1), len(prices_2))
        prices_1 = prices_1[-min_len:]
        prices_2 = prices_2[-min_len:]

        arr_1 = np.array(prices_1)
        arr_2 = np.array(prices_2)

        # Calculate Pearson correlation
        correlation, _ = stats.pearsonr(arr_1, arr_2)

        # Calculate hedge ratio using linear regression
        slope, intercept, r_value, p_value, std_err = stats.linregress(arr_2, arr_1)
        hedge_ratio = slope

        # Test for cointegration (simplified: use ADF on spread)
        spread = arr_1 - hedge_ratio * arr_2
        # Simplified cointegration test using spread stationarity
        # A more robust implementation would use statsmodels.tsa.stattools.coint
        cointegration_pvalue = self._test_stationarity(spread)

        result = PairCorrelation(
            pair_1=pair_1,
            pair_2=pair_2,
            correlation=correlation,
            cointegration_pvalue=cointegration_pvalue,
            hedge_ratio=hedge_ratio,
            lookback_days=self.lookback_days,
            sample_size=min_len,
            is_cointegrated=cointegration_pvalue < 0.05,
        )

        # Cache result
        self._correlation_cache[cache_key] = result
        self._cache_expiry[cache_key] = datetime.utcnow() + timedelta(minutes=cache_minutes)

        return result

    def _test_stationarity(self, series: np.ndarray) -> float:
        """
        Simplified stationarity test.

        Returns a p-value approximation. Lower = more stationary.
        """
        # Simple heuristic: check if series reverts to mean
        mean = np.mean(series)
        std = np.std(series)

        if std == 0:
            return 1.0

        # Count mean crossings
        above_mean = series > mean
        crossings = np.sum(np.diff(above_mean.astype(int)) != 0)

        # More crossings = more mean-reverting = lower "p-value"
        expected_crossings = len(series) / 2
        crossing_ratio = crossings / expected_crossings

        # Heuristic p-value
        if crossing_ratio > 0.8:
            return 0.01  # Strong mean reversion
        elif crossing_ratio > 0.6:
            return 0.05  # Moderate mean reversion
        elif crossing_ratio > 0.4:
            return 0.10  # Weak mean reversion
        else:
            return 0.50  # Not mean reverting

    def calculate_z_score(self, pair_1: str, pair_2: str) -> Optional[float]:
        """
        Calculate current z-score of the spread.

        Z-score > 2: Pair 1 overvalued relative to pair 2
        Z-score < -2: Pair 1 undervalued relative to pair 2

        Args:
            pair_1: First trading pair
            pair_2: Second trading pair

        Returns:
            Z-score or None if insufficient data
        """
        correlation = self.calculate_correlation(pair_1, pair_2)
        if not correlation:
            return None

        prices_1 = np.array(self.get_prices(pair_1))
        prices_2 = np.array(self.get_prices(pair_2))

        if len(prices_1) < 2 or len(prices_2) < 2:
            return None

        # Align series
        min_len = min(len(prices_1), len(prices_2))
        prices_1 = prices_1[-min_len:]
        prices_2 = prices_2[-min_len:]

        # Calculate spread using hedge ratio
        spread = prices_1 - correlation.hedge_ratio * prices_2

        # Z-score of current spread
        current_spread = spread[-1]
        mean_spread = np.mean(spread)
        std_spread = np.std(spread)

        if std_spread == 0:
            return 0.0

        z_score = (current_spread - mean_spread) / std_spread
        return float(z_score)

    def get_signal(
        self,
        pair_1: str,
        pair_2: str,
        entry_threshold: float = 2.0,
        exit_threshold: float = 0.5,
        current_position: Optional[str] = None,
    ) -> Optional[ZScoreSignal]:
        """
        Generate trading signal based on z-score.

        Args:
            pair_1: First trading pair
            pair_2: Second trading pair
            entry_threshold: Z-score threshold to enter (default 2.0)
            exit_threshold: Z-score threshold to exit (default 0.5)
            current_position: Current position direction if any

        Returns:
            ZScoreSignal or None if no signal
        """
        z_score = self.calculate_z_score(pair_1, pair_2)
        if z_score is None:
            return None

        abs_z = abs(z_score)

        # Check for exit signal
        if current_position and abs_z <= exit_threshold:
            return ZScoreSignal(
                pair_1=pair_1,
                pair_2=pair_2,
                z_score=z_score,
                direction="exit",
                confidence=1.0 - abs_z / entry_threshold,
            )

        # Check for entry signal
        if abs_z >= entry_threshold:
            if z_score > 0:
                # Pair 1 overvalued: short pair 1, long pair 2
                direction = "short_spread"
            else:
                # Pair 1 undervalued: long pair 1, short pair 2
                direction = "long_spread"

            # Confidence increases with z-score magnitude
            confidence = min(1.0, abs_z / (entry_threshold * 2))

            return ZScoreSignal(
                pair_1=pair_1,
                pair_2=pair_2,
                z_score=z_score,
                direction=direction,
                confidence=confidence,
            )

        return None

    def get_suitable_pairs(
        self,
        min_correlation: float = 0.7,
    ) -> List[Tuple[str, str, PairCorrelation]]:
        """
        Find all pair combinations suitable for stat arb.

        Args:
            min_correlation: Minimum correlation coefficient

        Returns:
            List of (pair_1, pair_2, correlation) tuples
        """
        all_pairs = list(self.price_history.keys())
        suitable = []

        for i, pair_1 in enumerate(all_pairs):
            for pair_2 in all_pairs[i + 1:]:
                corr = self.calculate_correlation(pair_1, pair_2)
                if corr and corr.is_suitable_for_stat_arb:
                    if abs(corr.correlation) >= min_correlation:
                        suitable.append((pair_1, pair_2, corr))

        # Sort by correlation strength
        suitable.sort(key=lambda x: abs(x[2].correlation), reverse=True)
        return suitable

    def get_spread_statistics(
        self,
        pair_1: str,
        pair_2: str,
    ) -> Optional[Dict]:
        """
        Get detailed spread statistics.

        Args:
            pair_1: First trading pair
            pair_2: Second trading pair

        Returns:
            Dict with spread statistics
        """
        correlation = self.calculate_correlation(pair_1, pair_2)
        if not correlation:
            return None

        prices_1 = np.array(self.get_prices(pair_1))
        prices_2 = np.array(self.get_prices(pair_2))

        min_len = min(len(prices_1), len(prices_2))
        prices_1 = prices_1[-min_len:]
        prices_2 = prices_2[-min_len:]

        spread = prices_1 - correlation.hedge_ratio * prices_2

        return {
            "pair_1": pair_1,
            "pair_2": pair_2,
            "correlation": correlation.correlation,
            "hedge_ratio": correlation.hedge_ratio,
            "is_cointegrated": correlation.is_cointegrated,
            "current_spread": float(spread[-1]),
            "mean_spread": float(np.mean(spread)),
            "std_spread": float(np.std(spread)),
            "z_score": float((spread[-1] - np.mean(spread)) / np.std(spread)) if np.std(spread) > 0 else 0,
            "min_spread": float(np.min(spread)),
            "max_spread": float(np.max(spread)),
            "sample_size": min_len,
        }
