"""
Speculative preset weight auto-tuning algorithm.

Pure functions — no DB, no I/O. Given a user's current scorer weights and
outcome stats per component (from analyze_speculative_calibration), returns
a new weights dict that:

  - Nudges weights of over-performing components UP and under-performing ones
    DOWN, proportionally to how far their win rate deviates from the overall.
  - Respects a per-cycle change cap (no whiplash — user can eyeball each
    proposal comfortably).
  - Respects per-component [floor, ceiling] so no single component dominates
    or gets silenced entirely.
  - Preserves weights for components that never fired in the window — no
    data is not a signal either way.
  - Always sums to exactly 100 (integer rounding preserved).

Raises ValueError when the clamp constraints are impossible
(e.g. forcing a sum to N when all floors already sum to >N). The caller
treats this as "no proposal this cycle, keep current weights".

See PRPs/speculative-weights-auto-calibration.md §Recommended Design §2.
"""

from __future__ import annotations

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants — tuned conservatively for Phase 1. Phase 2 may expose these
# as per-user settings.
# ---------------------------------------------------------------------------

# Step-size coefficient on the proportional-alpha update. 0.3 means a
# component 10pp above the overall win rate gains 3% of its current weight
# before the per-cycle change cap binds.
LEARNING_RATE: float = 0.3

# No single weight can move more than this many points per proposal. Caps
# the algorithm's aggressiveness so weird data blips don't wreck the scorer.
MAX_WEIGHT_CHANGE_PER_CYCLE: int = 5

# [floor, ceiling] clamp. Prevents any component from either dominating
# the score (ceiling) or getting effectively silenced (floor).
WEIGHT_FLOOR: int = 5
WEIGHT_CEILING: int = 40

# Sample-size threshold for auto-generating a proposal. The alert itself
# still fires at a lower threshold — this gates only the auto-proposal.
PROPOSAL_MIN_SAMPLE_SIZE: int = 500

# Tag stored on each proposal row so future changes to the algorithm can
# be identified and backtested separately.
ALGORITHM_NAME: str = "proportional-alpha-v1"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def propose_weights(
    current_weights: Dict[str, int],
    component_stats: List[Dict],
    overall_win_rate_pct: float,
    *,
    learning_rate: float = LEARNING_RATE,
    max_change: float = MAX_WEIGHT_CHANGE_PER_CYCLE,
    floor: float = WEIGHT_FLOOR,
    ceiling: float = WEIGHT_CEILING,
) -> Dict[str, int]:
    """Compute a new weights dict from outcome statistics.

    Args:
        current_weights: The user's currently-effective WEIGHTS dict.
        component_stats: List of {name, fires, win_rate_pct} dicts — the
            `components` field from analyze_speculative_calibration().
        overall_win_rate_pct: User's overall win rate across the sample.
        learning_rate, max_change, floor, ceiling: Algorithm tuning knobs
            (exposed for tests; production code uses module defaults).

    Returns:
        New weights dict with same keys as `current_weights`. Integers,
        sum to 100, each in [floor, ceiling].

    Raises:
        ValueError: When the clamp constraints are impossible to satisfy
            (e.g. all components at ceiling summing to >100). The caller
            should treat this as "no proposal this cycle".
    """
    stats_by_name = {s["name"]: s for s in component_stats}

    # 1. Proportional-alpha update per component.
    raw: Dict[str, float] = {}
    for name, old in current_weights.items():
        stat = stats_by_name.get(name)
        if stat is None or (stat.get("fires") or 0) == 0:
            # No data on this component — preserve the current weight.
            raw[name] = float(old)
            continue
        alpha = (stat["win_rate_pct"] - overall_win_rate_pct) / 100.0
        new_w = float(old) * (1.0 + learning_rate * alpha)
        # 2. Cap per-cycle change at ±max_change from baseline.
        new_w = max(float(old) - max_change, min(float(old) + max_change, new_w))
        raw[name] = new_w

    # 3. Clamp to [floor, ceiling].
    clamped = {k: max(float(floor), min(float(ceiling), v)) for k, v in raw.items()}

    # 4. Normalize to sum 100, pinning binding-constraint components.
    normalized = _normalize_to_sum(
        clamped, target=100.0, floor=float(floor), ceiling=float(ceiling),
    )

    # 5. Integer-round while preserving exact sum=100.
    return _integer_round_preserving_sum(normalized, target=100)


# ---------------------------------------------------------------------------
# Internals (exposed only for focused unit tests)
# ---------------------------------------------------------------------------


def _normalize_to_sum(
    weights: Dict[str, float], *, target: float, floor: float, ceiling: float,
) -> Dict[str, float]:
    """Scale a weights dict so its values sum to `target`, respecting
    [floor, ceiling] on each value.

    Iterative: scale free components proportionally. If the scale would
    push any component below floor or above ceiling, pin it to the
    boundary and redistribute the remainder across the rest. Terminates
    in at most len(weights)+1 passes (each pass pins at least one
    component OR converges with no change).

    Raises:
        ValueError: when pinned-sum already > target (all at ceiling
            summing over) or pinned-sum already < target with nowhere
            left to scale (all at floor summing under).
    """
    w = dict(weights)
    pinned: set[str] = set()
    max_iter = len(w) + 1
    for _ in range(max_iter):
        free = [k for k in w if k not in pinned]
        pinned_sum = sum(w[k] for k in pinned)
        remaining = target - pinned_sum
        if not free:
            # Nothing left to rescale — either exactly on target or impossible.
            if abs(remaining) > 1e-6:
                raise ValueError(
                    f"Cannot normalize to target={target}: "
                    f"all components pinned, pinned_sum={pinned_sum}"
                )
            return w
        free_sum = sum(w[k] for k in free)
        if free_sum <= 0 or remaining <= 0:
            raise ValueError(
                f"Cannot normalize to target={target}: "
                f"free_sum={free_sum}, remaining={remaining}"
            )
        scale = remaining / free_sum

        # Find the SINGLE worst-violating component at this scale. Pinning
        # one per pass (rather than all at once) avoids the failure case
        # where scaling drives every free component to a boundary in one
        # step, leaving no headroom to reach target. It also guarantees
        # convergence in at most N iterations since each one either pins
        # a component or settles.
        worst_k: str | None = None
        worst_violation = 0.0
        worst_boundary: float = 0.0
        for k in free:
            scaled = w[k] * scale
            if scaled < floor - 1e-9:
                violation = floor - scaled
                if violation > worst_violation:
                    worst_violation = violation
                    worst_k = k
                    worst_boundary = floor
            elif scaled > ceiling + 1e-9:
                violation = scaled - ceiling
                if violation > worst_violation:
                    worst_violation = violation
                    worst_k = k
                    worst_boundary = ceiling

        if worst_k is None:
            # No violations at this scale — apply it and converge.
            for k in free:
                w[k] = w[k] * scale
            return w

        # Pin the worst offender; the next iteration rescales what's left.
        w[worst_k] = worst_boundary
        pinned.add(worst_k)

    # Loop bound is len(w) + 1; each non-terminating pass pins exactly one
    # component, so this is unreachable unless the guard math above breaks.
    raise ValueError("Normalization failed to converge")


def _integer_round_preserving_sum(
    weights: Dict[str, float], *, target: int,
) -> Dict[str, int]:
    """Round float weights to ints while guaranteeing sum == target.

    Uses the largest-remainder (Hamilton) method: floor every value, then
    distribute the +1 bumps to the components with the largest fractional
    parts until sum == target. For positive weights this preserves the
    relative ordering of nearby components and never 'double-corrects'
    a value in the wrong direction (the naive round-then-adjust approach
    could bump a value UP that the algorithm had already decided to
    move DOWN).

    Weights are expected to be non-negative (they're scorer weights). For
    that reason we floor rather than round-to-nearest; each component ends
    up as either floor(v) or floor(v)+1.
    """
    floored = {k: int(v) for k, v in weights.items()}
    delta = target - sum(floored.values())
    if delta <= 0:
        # Either already on target, or the pre-clamp math gave us a sum
        # above target (shouldn't happen after _normalize_to_sum but
        # defense in depth). In the rare >target case, shave from the
        # largest fractions (they're the ones where our floor lost the
        # most precision, so bumping them down costs the least).
        if delta < 0:
            fracs = sorted(
                ((k, v - int(v)) for k, v in weights.items()),
                key=lambda kv: kv[1],
                reverse=True,
            )
            for k, _ in fracs[: -delta]:
                if floored[k] > 0:
                    floored[k] -= 1
        return floored
    # delta > 0: distribute +1 bumps to components with largest fractional parts.
    fracs = sorted(
        ((k, v - int(v)) for k, v in weights.items()),
        key=lambda kv: kv[1],
        reverse=True,
    )
    for k, _ in fracs[:delta]:
        floored[k] += 1
    return floored
