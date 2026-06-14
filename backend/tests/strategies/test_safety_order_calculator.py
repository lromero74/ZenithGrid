"""
Tests for backend/app/strategies/safety_order_calculator.py

Characterization + parity tests for the DCA geometric-series math. These pin the
exact outputs of ``get_total_multiplier`` and ``calculate_base_order_size`` across
a grid of configs so that collapsing the duplicated series math into a single
source of truth (CLAUDE.md rule 13) is provably behavior-preserving.

The key invariant: wherever ``calculate_base_order_size`` auto-calculates a base
order from a budget, the divisor it uses MUST equal ``get_total_multiplier`` for
the same config. If a value here moves, the two were NOT equivalent — stop and
understand the divergence before refactoring.
"""

import itertools

import pytest

from app.strategies.safety_order_calculator import (
    calculate_base_order_size,
    get_total_multiplier,
)


def _cfg(**overrides):
    """A baseline config dict with sensible defaults, overridable per-test."""
    base = {
        "base_order_type": "percentage",
        "base_order_percentage": 10.0,
        "auto_calculate_order_sizes": True,
        "max_safety_orders": 2,
        "safety_order_type": "percentage_of_base",
        "safety_order_percentage": 50.0,
        "safety_order_volume_scale": 1.0,
    }
    base.update(overrides)
    return base


# The config grid from the PRP: every combination is a characterization point.
_SAFETY_TYPES = ["percentage_of_base", "fixed"]
_VOLUME_SCALES = [1.0, 1.62, 2.0]
_MAX_SOS = [0, 1, 2, 5]
_SO_PCTS = [50.0, 100.0]
_GRID = list(
    itertools.product(_SAFETY_TYPES, _VOLUME_SCALES, _MAX_SOS, _SO_PCTS)
)


class TestGetTotalMultiplier:
    """Direct characterization of get_total_multiplier."""

    def test_no_safety_orders_returns_one(self):
        """Edge: 0 safety orders means the base order is the whole cycle."""
        assert get_total_multiplier(_cfg(max_safety_orders=0)) == 1.0

    def test_percentage_of_base_flat_scale(self):
        """Happy path: 1 + so_pct * n with volume_scale == 1."""
        cfg = _cfg(max_safety_orders=2, safety_order_percentage=50.0, safety_order_volume_scale=1.0)
        assert get_total_multiplier(cfg) == pytest.approx(1.0 + 0.5 * 2)

    def test_percentage_of_base_geometric_scale(self):
        """Happy path: geometric sum when volume_scale != 1."""
        cfg = _cfg(max_safety_orders=3, safety_order_percentage=50.0, safety_order_volume_scale=2.0)
        # 1 + 0.5 * (2^3 - 1)/(2 - 1) = 1 + 0.5 * 7 = 4.5
        assert get_total_multiplier(cfg) == pytest.approx(4.5)

    def test_fixed_type_flat_scale(self):
        """Happy path: fixed SO type, base(1) + SO1(1) + (n-1) flat."""
        cfg = _cfg(safety_order_type="fixed", max_safety_orders=3, safety_order_volume_scale=1.0)
        # 2.0 + (3 - 1) = 4.0
        assert get_total_multiplier(cfg) == pytest.approx(4.0)

    def test_fixed_type_single_so(self):
        """Edge: fixed type with exactly 1 SO is just base + SO1 = 2.0."""
        cfg = _cfg(safety_order_type="fixed", max_safety_orders=1, safety_order_volume_scale=2.0)
        assert get_total_multiplier(cfg) == pytest.approx(2.0)

    def test_always_at_least_one_for_valid_configs(self):
        """Invariant: a valid config never yields a multiplier below 1.0."""
        for st, vs, n, pct in _GRID:
            cfg = _cfg(
                safety_order_type=st,
                safety_order_volume_scale=vs,
                max_safety_orders=n,
                safety_order_percentage=pct,
            )
            assert get_total_multiplier(cfg) >= 1.0


class TestBaseOrderConsumesMultiplier:
    """
    The parity oracle: for every auto-calculate path that derives a base order
    from a budget, base_order_size * total_multiplier == budget. This is what
    lets calculate_base_order_size delegate to get_total_multiplier.
    """

    BALANCE = 1000.0

    @pytest.mark.parametrize("safety_type,volume_scale,max_sos,so_pct", _GRID)
    def test_percentage_base_order_parity(self, safety_type, volume_scale, max_sos, so_pct):
        """
        base_order_type == 'percentage', auto-calc on.

        Only the percentage_of_base safety type takes the multiplier path; the
        fixed safety type falls through to the flat base_order_percentage. Both
        behaviors are pinned here.
        """
        cfg = _cfg(
            base_order_type="percentage",
            base_order_percentage=10.0,
            auto_calculate_order_sizes=True,
            safety_order_type=safety_type,
            safety_order_volume_scale=volume_scale,
            max_safety_orders=max_sos,
            safety_order_percentage=so_pct,
        )
        result = calculate_base_order_size(cfg, self.BALANCE)

        if safety_type == "percentage_of_base" and max_sos > 0:
            # Auto-calculated: result * multiplier reconstructs the budget.
            assert result == pytest.approx(self.BALANCE / get_total_multiplier(cfg))
        else:
            # Flat percentage path (no auto-calc divisor applied).
            assert result == pytest.approx(self.BALANCE * 0.10)

    @pytest.mark.parametrize("safety_type,volume_scale,max_sos,so_pct", _GRID)
    def test_fixed_base_order_parity(self, safety_type, volume_scale, max_sos, so_pct):
        """
        base_order_type == 'fixed', auto-calc on, balance > 0.

        Both safety types take the multiplier path here; the divisor must equal
        get_total_multiplier for the same config.
        """
        cfg = _cfg(
            base_order_type="fixed",
            auto_calculate_order_sizes=True,
            safety_order_type=safety_type,
            safety_order_volume_scale=volume_scale,
            max_safety_orders=max_sos,
            safety_order_percentage=so_pct,
        )
        result = calculate_base_order_size(cfg, self.BALANCE)

        if max_sos > 0:
            assert result == pytest.approx(self.BALANCE / get_total_multiplier(cfg))
        else:
            # No safety orders -> falls through to the fixed-size literal path.
            assert result == pytest.approx(cfg.get("base_order_fixed", 0.001))


class TestBaseOrderNonAutoPaths:
    """Failure / fallback cases that must NOT route through the multiplier."""

    def test_percentage_without_auto_calculate(self):
        """No auto-calc: plain percentage of balance."""
        cfg = _cfg(auto_calculate_order_sizes=False, base_order_percentage=25.0, max_safety_orders=3)
        assert calculate_base_order_size(cfg, 800.0) == pytest.approx(200.0)

    def test_fixed_without_auto_calculate_uses_literal(self):
        """No auto-calc on a fixed base order returns the configured fixed size."""
        cfg = _cfg(base_order_type="fixed", auto_calculate_order_sizes=False, base_order_fixed=0.05)
        assert calculate_base_order_size(cfg, 1000.0) == pytest.approx(0.05)

    def test_fixed_auto_calculate_zero_balance_uses_literal(self):
        """Edge: balance == 0 disables auto-calc for fixed and uses the literal."""
        cfg = _cfg(base_order_type="fixed", auto_calculate_order_sizes=True, base_order_fixed=0.02, max_safety_orders=3)
        assert calculate_base_order_size(cfg, 0.0) == pytest.approx(0.02)

    def test_divide_by_zero_guard_never_infinite(self):
        """
        Failure: a degenerate config that makes the multiplier non-positive must
        never produce Infinity or raise (CLAUDE.md rule 13).

        With so_pct=100% (1.0), volume_scale=-2, max_safety_orders=2 the geometric
        sum is ((-2)^2 - 1)/((-2) - 1) = 3/-3 = -1, so the multiplier collapses to
        1 + 1.0*(-1) = 0. The pre-refactor inline code divided by this and raised
        ZeroDivisionError; the refactor must guard and return a finite floor.
        """
        cfg = _cfg(
            base_order_type="fixed",
            auto_calculate_order_sizes=True,
            safety_order_type="percentage_of_base",
            safety_order_volume_scale=-2.0,
            max_safety_orders=2,
            safety_order_percentage=100.0,
        )
        assert get_total_multiplier(cfg) == pytest.approx(0.0)
        result = calculate_base_order_size(cfg, 1000.0)
        assert result != float("inf")
        assert result == result  # not NaN
