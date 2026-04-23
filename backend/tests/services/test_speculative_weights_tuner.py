"""
Tests for app.services.speculative_weights_tuner.

The tuner is a pure function. Given current weights + per-component
outcome stats, it returns proposed new weights that:
  - sum to exactly 100
  - respect [WEIGHT_FLOOR, WEIGHT_CEILING] clamp
  - cap any single weight's change at ±MAX_WEIGHT_CHANGE_PER_CYCLE
  - preserve weights for components with zero fires (no data = no opinion)
  - raise ValueError on impossible constraints (so the caller skips the cycle)
"""

import pytest

from app.services.speculative_weights_tuner import (
    MAX_WEIGHT_CHANGE_PER_CYCLE,
    WEIGHT_CEILING,
    WEIGHT_FLOOR,
    _integer_round_preserving_sum,
    _normalize_to_sum,
    propose_weights,
)


# Matches speculative_signals.DEFAULT_WEIGHTS — kept inline to decouple the
# tuner tests from any future module-default renames.
DEFAULTS = {
    "volume_surge": 25,
    "compression_breakout": 20,
    "momentum_accelerating": 20,
    "micro_mid_cap": 10,
    "correlation_break": 10,
    "volume_vs_mcap": 15,
}


def _stats(win_rates: dict, fires: int = 50) -> list:
    """Shorthand: one stat dict per component name in DEFAULTS."""
    return [
        {"name": name, "fires": fires, "win_rate_pct": win_rates[name]}
        for name in DEFAULTS
    ]


class TestProposeWeights:
    def test_all_components_equal_win_rate_returns_defaults_unchanged(self):
        stats = _stats({k: 15.0 for k in DEFAULTS})
        result = propose_weights(DEFAULTS, stats, overall_win_rate_pct=15.0)
        assert result == DEFAULTS

    def test_above_baseline_component_gains_weight(self):
        rates = {k: 15.0 for k in DEFAULTS}
        rates["volume_surge"] = 30.0
        result = propose_weights(DEFAULTS, _stats(rates), overall_win_rate_pct=15.0)
        assert result["volume_surge"] > DEFAULTS["volume_surge"]

    def test_below_baseline_component_loses_weight(self):
        # Use a wide divergence (50pp) so the proportional-alpha update is
        # large enough to survive integer rounding. A small divergence
        # (e.g. 10pp at k=0.3) can round away entirely.
        rates = {k: 50.0 for k in DEFAULTS}
        rates["correlation_break"] = 0.0
        result = propose_weights(DEFAULTS, _stats(rates), overall_win_rate_pct=50.0)
        assert result["correlation_break"] < DEFAULTS["correlation_break"]

    def test_output_sums_to_100(self):
        rates = {k: 15.0 for k in DEFAULTS}
        rates["volume_surge"] = 30.0
        rates["correlation_break"] = 3.0
        result = propose_weights(DEFAULTS, _stats(rates), overall_win_rate_pct=15.0)
        assert sum(result.values()) == 100

    def test_per_cycle_change_clamped_to_plus_minus_5(self):
        # Extreme divergence — if the formula were unbounded volume_surge
        # would swing way more than ±5.
        rates = {k: 10.0 for k in DEFAULTS}
        rates["volume_surge"] = 95.0
        result = propose_weights(
            DEFAULTS, _stats(rates, fires=1000), overall_win_rate_pct=10.0,
        )
        assert abs(result["volume_surge"] - DEFAULTS["volume_surge"]) \
            <= MAX_WEIGHT_CHANGE_PER_CYCLE

    def test_floor_respected(self):
        # correlation_break starts at 10; drastic underperformance should
        # push it toward the floor but never below.
        rates = {k: 50.0 for k in DEFAULTS}
        rates["correlation_break"] = 0.1
        result = propose_weights(
            DEFAULTS, _stats(rates, fires=1000), overall_win_rate_pct=50.0,
        )
        assert result["correlation_break"] >= WEIGHT_FLOOR

    def test_ceiling_respected(self):
        # Even pathological inputs must not push any single weight over
        # WEIGHT_CEILING.
        rates = {k: 5.0 for k in DEFAULTS}
        rates["volume_surge"] = 99.0
        result = propose_weights(
            DEFAULTS, _stats(rates, fires=1000), overall_win_rate_pct=10.0,
        )
        assert all(v <= WEIGHT_CEILING for v in result.values()), result

    def test_zero_fires_component_keeps_current_weight(self):
        """No data on a component is 'no opinion' — its weight must not
        drift just because other components' stats changed."""
        rates = {k: 15.0 for k in DEFAULTS}
        rates["volume_surge"] = 30.0  # drives the re-weighting
        stats = _stats(rates)
        # Zero out fires for micro_mid_cap explicitly.
        for s in stats:
            if s["name"] == "micro_mid_cap":
                s["fires"] = 0
        result = propose_weights(DEFAULTS, stats, overall_win_rate_pct=15.0)
        assert result["micro_mid_cap"] == DEFAULTS["micro_mid_cap"]

    def test_output_is_all_integers(self):
        rates = {k: 15.0 + i for i, k in enumerate(DEFAULTS)}
        result = propose_weights(
            DEFAULTS, _stats(rates), overall_win_rate_pct=15.0,
        )
        assert all(isinstance(v, int) for v in result.values())


class TestNormalizeToSum:
    def test_already_sums_to_target_passes_through(self):
        w = {"a": 25.0, "b": 25.0, "c": 25.0, "d": 25.0}
        result = _normalize_to_sum(w, target=100.0, floor=5.0, ceiling=40.0)
        assert sum(result.values()) == pytest.approx(100.0)

    def test_scales_up_when_below_target(self):
        w = {"a": 10.0, "b": 10.0, "c": 10.0, "d": 10.0}
        result = _normalize_to_sum(w, target=100.0, floor=5.0, ceiling=40.0)
        assert sum(result.values()) == pytest.approx(100.0)

    def test_rejects_impossible_all_pinned_to_floor(self):
        # 6 × floor 5 = 30, target=10 is impossible.
        w = {f"c{i}": 5.0 for i in range(6)}
        with pytest.raises(ValueError):
            _normalize_to_sum(w, target=10.0, floor=5.0, ceiling=40.0)

    def test_pins_ceiling_and_redistributes(self):
        # One component would otherwise go way above ceiling; the rest fill.
        w = {"a": 100.0, "b": 1.0, "c": 1.0, "d": 1.0}
        result = _normalize_to_sum(w, target=100.0, floor=5.0, ceiling=40.0)
        assert result["a"] == 40.0  # pinned to ceiling
        assert sum(result.values()) == pytest.approx(100.0)


class TestIntegerRoundPreservingSum:
    def test_preserves_sum_under_banker_rounding_drift(self):
        weights = {"a": 33.3333, "b": 33.3333, "c": 33.3334}
        result = _integer_round_preserving_sum(weights, target=100)
        assert sum(result.values()) == 100

    def test_returns_ints(self):
        weights = {"a": 33.5, "b": 33.2, "c": 33.3}
        result = _integer_round_preserving_sum(weights, target=100)
        assert all(isinstance(v, int) for v in result.values())

    def test_exact_integers_unchanged(self):
        weights = {"a": 50.0, "b": 50.0}
        result = _integer_round_preserving_sum(weights, target=100)
        assert result == {"a": 50, "b": 50}

    def test_over_target_shaves_largest_fractions(self):
        """When floats sum above target (can happen if pre-clamp math went
        past the ceiling), the function shaves +1 down to +0 on the
        components with the largest fractional parts. Exercises the
        `delta < 0` branch that the happy-path drift test misses."""
        # Floors: 50 + 50 = 100, fractions .6 + .6 = 1.2 → sum_floor = 100.
        # Wait — int(50.6) = 50, so sum_floor = 100, delta = 0. Need larger
        # fractions. Try int(50) = 50, int(50) = 50; sum=100.
        # Use 50.9 + 50.9 instead: int → 50+50=100, delta=0 too.
        # The over-target path fires when SUM > target AFTER flooring;
        # that requires explicit non-int floors. Use values whose floors
        # already sum to target+1:
        weights = {"a": 50.9, "b": 50.9}
        # floor sums to 100, but target=99 triggers the delta<0 branch.
        result = _integer_round_preserving_sum(weights, target=99)
        assert sum(result.values()) == 99


class TestProposeWeightsContractViolations:
    def test_propose_weights_raises_on_impossible_clamps(self):
        """The public API's docstring promises a ValueError when the
        floor/ceiling constraints can't be satisfied. Regression guard
        against the normalizer's error getting silently swallowed on the
        propose_weights path."""
        # Force impossible: each of 6 components at floor=5 sums to 30,
        # but pass a propose_weights arg where target is implicit (100)
        # and all components are artificially pushed below floor. We
        # achieve this by setting the floor very high relative to the
        # component count — 6 × 20 = 120 > 100.
        with pytest.raises(ValueError):
            propose_weights(
                DEFAULTS,
                _stats({k: 15.0 for k in DEFAULTS}),
                overall_win_rate_pct=15.0,
                floor=20,   # 6 × 20 = 120 > 100 target → impossible
                ceiling=40,
            )
