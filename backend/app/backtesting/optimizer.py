"""
Strategy Optimizer

Sweeps parameter permutations through the backtesting engine and ranks
results by fitness metrics to find the best strategy configuration.

Usage:
    result = await run_optimization(
        strategy_type="indicator_based",
        strategy_config={...base config...},
        parameter_ranges={
            "base_order_size": [10, 20, 50],
            "rebalance_threshold": [3.0, 5.0, 10.0],
        },
        candles=candles,
        product_id="BTC-USD",
        fitness_metric="total_return_pct",
        top_n=5,
    )
"""

import itertools
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.backtesting import run_backtest, BacktestResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class OptimizationResult:
    """Result of a single parameter combination run."""
    params: Dict[str, Any]
    metrics: BacktestResult
    score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "params": self.params,
            "score": round(self.score, 4),
            "metrics": self.metrics.to_dict(),
        }


@dataclass
class OptimizationReport:
    """Full optimization report with all parameter combinations ranked."""
    strategy_type: str
    fitness_metric: str
    total_combinations: int
    results: List[OptimizationResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_type": self.strategy_type,
            "fitness_metric": self.fitness_metric,
            "total_combinations": self.total_combinations,
            "top_results": [r.to_dict() for r in self.results[:10]],
            "all_results_count": len(self.results),
        }


# ---------------------------------------------------------------------------
# Fitness scoring
# ---------------------------------------------------------------------------

FITNESS_METRICS = {
    "total_return_pct": lambda r: r.total_return_pct,
    "sharpe_ratio": lambda r: r.sharpe_ratio,
    "profit_factor": lambda r: r.profit_factor if r.profit_factor != float("inf") else 999.0,
    "win_rate": lambda r: r.win_rate,
    "total_profit_quote": lambda r: r.total_profit_quote,
    "max_drawdown_inverse": lambda r: -r.max_drawdown_pct,  # Lower drawdown is better
}


def _compute_score(result: BacktestResult, metric: str) -> float:
    """Compute a fitness score from a backtest result using the given metric."""
    scorer = FITNESS_METRICS.get(metric)
    if scorer is None:
        logger.warning(f"Unknown fitness metric '{metric}', using total_return_pct")
        return result.total_return_pct
    return scorer(result)


# ---------------------------------------------------------------------------
# Parameter permutation
# ---------------------------------------------------------------------------

def _generate_permutations(
    base_config: Dict[str, Any],
    parameter_ranges: Dict[str, List[Any]],
) -> List[Dict[str, Any]]:
    """Generate all parameter combinations from the ranges.

    Each key in parameter_ranges maps to a list of values to try.
    The base_config provides fixed values for parameters not in the ranges.
    """
    if not parameter_ranges:
        return [base_config.copy()]

    keys = list(parameter_ranges.keys())
    value_lists = [parameter_ranges[k] for k in keys]

    configs = []
    for combination in itertools.product(*value_lists):
        config = base_config.copy()
        for key, value in zip(keys, combination):
            config[key] = value
        configs.append(config)

    return configs


# ---------------------------------------------------------------------------
# Main optimization runner
# ---------------------------------------------------------------------------

async def run_optimization(
    strategy_type: str,
    strategy_config: Dict[str, Any],
    parameter_ranges: Dict[str, List[Any]],
    candles: List[Dict[str, Any]],
    product_id: str,
    initial_capital: float = 1000.0,
    fee_pct: float = 0.0,
    fitness_metric: str = "total_return_pct",
    top_n: int = 5,
    user_id: Optional[int] = None,
    account_id: Optional[int] = None,
) -> OptimizationReport:
    """Run a parameter sweep optimization.

    Args:
        strategy_type: Strategy ID to optimize
        strategy_config: Base config (fixed parameters)
        parameter_ranges: {param_name: [value1, value2, ...]}
        candles: Historical candle data
        product_id: Trading pair
        initial_capital: Starting balance for each backtest
        fee_pct: Trading fee percentage
        fitness_metric: Metric to rank by (see FITNESS_METRICS)
        top_n: Number of top results to keep in detail
        user_id: For account scoping
        account_id: For account scoping

    Returns:
        OptimizationReport with all results ranked by fitness score
    """
    configs = _generate_permutations(strategy_config, parameter_ranges)
    total = len(configs)
    logger.info(f"Strategy optimizer: {total} combinations for {strategy_type}")

    results: List[OptimizationResult] = []

    for i, config in enumerate(configs):
        try:
            bt_result = await run_backtest(
                strategy_type=strategy_type,
                strategy_config=config,
                candles=candles,
                product_id=product_id,
                initial_capital=initial_capital,
                fee_pct=fee_pct,
                user_id=user_id,
                account_id=account_id,
            )

            score = _compute_score(bt_result, fitness_metric)
            results.append(OptimizationResult(
                params={k: config[k] for k in parameter_ranges},
                metrics=bt_result,
                score=score,
            ))

        except Exception as e:
            logger.warning(f"Optimization run {i+1}/{total} failed: {e}")
            continue

        if (i + 1) % 10 == 0:
            logger.info(f"Optimization progress: {i+1}/{total}")

    # Sort by score descending
    results.sort(key=lambda r: r.score, reverse=True)

    logger.info(
        f"Optimization complete: {len(results)}/{total} runs succeeded. "
        f"Best score: {results[0].score:.4f}" if results else "No results"
    )

    return OptimizationReport(
        strategy_type=strategy_type,
        fitness_metric=fitness_metric,
        total_combinations=total,
        results=results,
    )
