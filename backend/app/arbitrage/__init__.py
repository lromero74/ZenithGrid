"""
Arbitrage Detection and Analysis Module

Provides algorithms for detecting arbitrage opportunities:
- TriangularDetector: Find profitable 3-way currency cycles
- StatArbAnalyzer: Correlation-based statistical arbitrage
"""

from app.arbitrage.triangular_detector import TriangularDetector, TriangularPath, PathProfit
from app.arbitrage.stat_arb_analyzer import StatArbAnalyzer, PairCorrelation, ZScoreSignal

__all__ = [
    "TriangularDetector",
    "TriangularPath",
    "PathProfit",
    "StatArbAnalyzer",
    "PairCorrelation",
    "ZScoreSignal",
]
