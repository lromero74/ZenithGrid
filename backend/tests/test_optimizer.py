"""
Tests for backend/app/backtesting/optimizer.py

Covers:
- Parameter permutation generation
- Fitness scoring with different metrics
- run_optimization: full sweep, ranking, error handling
- OptimizationReport serialization
"""

from unittest.mock import AsyncMock, MagicMock, patch

from app.backtesting.optimizer import (
    run_optimization, _generate_permutations, _compute_score,
    OptimizationResult, OptimizationReport, FITNESS_METRICS,
)
from app.backtesting import BacktestResult


# =============================================================================
# Parameter permutation tests
# =============================================================================


def test_generate_permutations_single_param():
    """Single parameter with 3 values generates 3 configs."""
    base = {"a": 1, "b": 2}
    ranges = {"a": [10, 20, 30]}
    configs = _generate_permutations(base, ranges)
    assert len(configs) == 3
    assert {"a": 10, "b": 2} in configs
    assert {"a": 20, "b": 2} in configs
    assert {"a": 30, "b": 2} in configs


def test_generate_permutations_multi_param():
    """Two parameters with 2 and 3 values generates 6 configs."""
    base = {"x": 0}
    ranges = {"a": [1, 2], "b": [10, 20, 30]}
    configs = _generate_permutations(base, ranges)
    assert len(configs) == 6


def test_generate_permutations_no_ranges():
    """No parameter ranges returns just the base config."""
    base = {"a": 1}
    configs = _generate_permutations(base, {})
    assert len(configs) == 1
    assert configs[0] == {"a": 1}


def test_generate_permutations_preserves_base():
    """Base config values are preserved for non-ranged parameters."""
    base = {"fixed": "keep", "sweep": 0}
    ranges = {"sweep": [1, 2]}
    configs = _generate_permutations(base, ranges)
    for c in configs:
        assert c["fixed"] == "keep"


# =============================================================================
# Fitness scoring tests
# =============================================================================


def test_compute_score_total_return():
    """Score by total_return_pct."""
    result = BacktestResult(total_return_pct=15.5)
    assert _compute_score(result, "total_return_pct") == 15.5


def test_compute_score_sharpe():
    """Score by sharpe_ratio."""
    result = BacktestResult(sharpe_ratio=2.3)
    assert _compute_score(result, "sharpe_ratio") == 2.3


def test_compute_score_profit_factor_inf():
    """Infinite profit factor is capped to 999."""
    result = BacktestResult(profit_factor=float("inf"))
    assert _compute_score(result, "profit_factor") == 999.0


def test_compute_score_win_rate():
    """Score by win_rate."""
    result = BacktestResult(win_rate=65.0)
    assert _compute_score(result, "win_rate") == 65.0


def test_compute_score_max_drawdown_inverse():
    """Score by max_drawdown_inverse (lower drawdown = higher score)."""
    result = BacktestResult(max_drawdown_pct=10.0)
    assert _compute_score(result, "max_drawdown_inverse") == -10.0


def test_compute_score_unknown_metric():
    """Unknown metric falls back to total_return_pct."""
    result = BacktestResult(total_return_pct=12.0)
    assert _compute_score(result, "unknown_metric") == 12.0


# =============================================================================
# run_optimization tests
# =============================================================================


def _make_candles(n: int, start_price: float = 50000.0) -> list:
    """Generate n synthetic candles."""
    candles = []
    for i in range(n):
        price = start_price + (i % 10) * 100
        candles.append({
            "start": str(i * 300), "open": str(price),
            "high": str(price + 50), "low": str(price - 50),
            "close": str(price + 30), "volume": "1000",
        })
    return candles


async def test_run_optimization_3x3_grid():
    """3x3 parameter grid produces 9 results ranked by score."""
    candles = _make_candles(30)

    mock_strategy = MagicMock()
    mock_strategy.analyze_signal = AsyncMock(return_value=None)

    with patch("app.strategies.StrategyRegistry.get_strategy", return_value=mock_strategy):
        report = await run_optimization(
            strategy_type="indicator_based",
            strategy_config={"base_order_percentage": 5.0},
            parameter_ranges={
                "base_order_size": [10, 50, 100],
                "rebalance_threshold": [3.0, 5.0, 10.0],
            },
            candles=candles,
            product_id="BTC-USD",
            fitness_metric="total_return_pct",
        )

    assert report.total_combinations == 9
    assert len(report.results) == 9
    # Results should be sorted by score descending
    scores = [r.score for r in report.results]
    assert scores == sorted(scores, reverse=True)


async def test_run_optimization_no_ranges():
    """No parameter ranges produces a single result."""
    candles = _make_candles(30)

    mock_strategy = MagicMock()
    mock_strategy.analyze_signal = AsyncMock(return_value=None)

    with patch("app.strategies.StrategyRegistry.get_strategy", return_value=mock_strategy):
        report = await run_optimization(
            strategy_type="indicator_based",
            strategy_config={"base_order_percentage": 5.0},
            parameter_ranges={},
            candles=candles,
            product_id="BTC-USD",
        )

    assert report.total_combinations == 1
    assert len(report.results) == 1


async def test_run_optimization_results_sorted_descending():
    """Results are sorted by score in descending order."""
    candles = _make_candles(30)

    mock_strategy = MagicMock()
    mock_strategy.analyze_signal = AsyncMock(return_value=None)

    with patch("app.strategies.StrategyRegistry.get_strategy", return_value=mock_strategy):
        report = await run_optimization(
            strategy_type="indicator_based",
            strategy_config={},
            parameter_ranges={"x": [1, 2, 3, 4, 5]},
            candles=candles,
            product_id="BTC-USD",
            fitness_metric="total_return_pct",
        )

    # All scores should be 0 (no trades), but still sorted
    scores = [r.score for r in report.results]
    assert scores == sorted(scores, reverse=True)


async def test_run_optimization_params_in_results():
    """Each result includes only the swept parameters, not the full config."""
    candles = _make_candles(30)

    mock_strategy = MagicMock()
    mock_strategy.analyze_signal = AsyncMock(return_value=None)

    with patch("app.strategies.StrategyRegistry.get_strategy", return_value=mock_strategy):
        report = await run_optimization(
            strategy_type="indicator_based",
            strategy_config={"fixed_param": 42, "swept_param": 0},
            parameter_ranges={"swept_param": [1, 2, 3]},
            candles=candles,
            product_id="BTC-USD",
        )

    for result in report.results:
        assert "swept_param" in result.params
        assert "fixed_param" not in result.params


# =============================================================================
# OptimizationReport serialization tests
# =============================================================================


def test_optimization_report_to_dict():
    """to_dict produces a valid dict with top results."""
    report = OptimizationReport(
        strategy_type="indicator_based",
        fitness_metric="total_return_pct",
        total_combinations=3,
        results=[
            OptimizationResult(
                params={"x": 1},
                metrics=BacktestResult(total_return_pct=10.0),
                score=10.0,
            ),
            OptimizationResult(
                params={"x": 2},
                metrics=BacktestResult(total_return_pct=5.0),
                score=5.0,
            ),
        ],
    )
    d = report.to_dict()
    assert d["strategy_type"] == "indicator_based"
    assert d["total_combinations"] == 3
    assert d["all_results_count"] == 2
    assert len(d["top_results"]) == 2
    assert d["top_results"][0]["score"] == 10.0


def test_optimization_result_to_dict():
    """OptimizationResult.to_dict includes params, score, and metrics."""
    result = OptimizationResult(
        params={"threshold": 5.0},
        metrics=BacktestResult(total_return_pct=15.0, num_trades=3),
        score=15.0,
    )
    d = result.to_dict()
    assert d["params"] == {"threshold": 5.0}
    assert d["score"] == 15.0
    assert "metrics" in d
    assert d["metrics"]["total_return_pct"] == 15.0


# =============================================================================
# FITNESS_METRICS tests
# =============================================================================


def test_fitness_metrics_has_expected_keys():
    """All expected fitness metrics are defined."""
    expected = {"total_return_pct", "sharpe_ratio", "profit_factor",
                "win_rate", "total_profit_quote", "max_drawdown_inverse"}
    assert expected.issubset(set(FITNESS_METRICS.keys()))
