# PRP: Single source of truth for the DCA total-multiplier / base-order math

**Date:** 2026-06-13
**Origin:** Deferred from the v2.168.8 bug sweep (financial-calc agent Finding 4). Tech-debt refactor of *working* code, so it warrants a careful plan + regression test rather than an inline edit. (The frontend↔backend parity test added in v2.168.8 already guards the cross-language drift; this PRP addresses the *backend↔backend* duplication.)

## TL;DR

`backend/app/strategies/safety_order_calculator.py` computes the same geometric DCA series in **two** places: `get_total_multiplier()` (lines 14–49) returns the full-cycle multiplier (base + all safety orders), and `calculate_base_order_size()` (lines 52–124) re-derives the identical series inline to divide a budget into a base order. They currently agree, but they're two maintenance targets — exactly the CLAUDE.md rule-13 "two backend paths re-deriving the same split" anti-pattern. Collapse to one: `calculate_base_order_size` should derive the multiplier via `get_total_multiplier`, leaving the geometric math defined once.

## Context & Goal

### Problem
Two independent implementations of: `multiplier = base(1) + Σ safety-order ratios`:
- `get_total_multiplier(config)` — used by `calculate_soft_ceiling` and the soft-ceiling display.
- Inline loop inside `calculate_base_order_size(config, balance)` — `base_order_size ≈ balance / (that same series)`.

A future change to the SO sizing model (e.g. a new `safety_order_type`, a different volume-scale convention) must be made in both or they silently diverge — the precise failure mode behind the June-2026 "modal showed 20/$1 while engine used 1/$1.83" incident and the "auto-calculated base order didn't match actual deal sizes" changelog fix.

### Goal
One authoritative geometric-series implementation. `calculate_base_order_size` consumes `get_total_multiplier` (or a shared private helper) rather than re-deriving it. No behavioral change — byte-for-byte equal outputs across all configs.

### Non-Goals
- No change to the sizing *formula* or any external behavior. This is a pure refactor.
- Not touching the frontend mirror (`botUtils.ts::getDCAMultiplier`) — its parity is already covered by `botUtils.test.ts`.
- Not changing `calculate_safety_order_size` (per-order sizing; orthogonal).

## Constraints
- **Zero behavioral drift.** The refactor must be provably equivalent. Pin current outputs with a characterization test BEFORE refactoring.
- `calculate_base_order_size` may contain extra logic beyond the series (exchange minimums, `base_order_type` branches, rounding). Preserve all of it; only the geometric-series computation is shared.
- Both PostgreSQL and SQLite installs run this (pure Python; no DB), so no migration concern — but it's in the **hot trading path**, so correctness is paramount.

## Existing Patterns (Reference)
- `safety_order_calculator.py::get_total_multiplier` (14–49) — the canonical series; handles `percentage_of_base` and `fixed`/`fixed_btc`, `volume_scale == 1` vs `≠ 1`.
- `safety_order_calculator.py::calculate_base_order_size` (52–124) — the duplicate; the relationship is approximately `base_order_size = available_budget / get_total_multiplier(config)` (verify exactly, including any `base_order_type`/min-size handling).
- v2.168.3 added `count_deployed_safety_orders`/`entry_trades_for_position` to this same module — follow its docstring style and keep helpers pure/leaf.

## Recommended Design
1. **Characterize first.** Add a parametrized test asserting current `calculate_base_order_size` and `get_total_multiplier` outputs for a grid of configs: `safety_order_type ∈ {percentage_of_base, fixed}`, `volume_scale ∈ {1.0, 1.62, 2.0}`, `max_safety_orders ∈ {0, 1, 2, 5}`, `safety_order_percentage ∈ {50, 100}`. Capture exact numbers (these become the regression oracle).
2. **Extract or reuse.** Determine the exact relationship between the inline loop and `get_total_multiplier`. If `base_order_size == available_budget / get_total_multiplier(config)`, replace the inline loop with a call to `get_total_multiplier` (guarding divide-by-zero → return "not computable"/sensible floor, never `Infinity`). If there's a residual difference (e.g. fixed vs percentage base handling), factor the shared part into one private `_dca_series_sum(config) -> float` that both call.
3. **Re-run the characterization test** — every captured value must match to full precision.

## Implementation Tasks (in order)
1. Add the characterization/parity test in `tests/strategies/test_safety_order_calculator.py` (create if absent) — capture current outputs across the config grid. Run it green against today's code.
2. Refactor `calculate_base_order_size` to consume `get_total_multiplier` (or a shared `_dca_series_sum`). Guard div-by-zero.
3. Re-run the characterization test — must stay green unchanged.
4. Run the full strategy + monitor suites (the soft-ceiling/engine paths consume these). Ship (backend restart, no migration).

## Validation Gates (executable)
```bash
cd backend
./venv/bin/python3 -m pytest tests/strategies/ tests/monitor/ tests/trading_engine/ -q
./venv/bin/python3 -m pytest tests/ -q -k "multiplier or base_order or soft_ceiling or dca"
./venv/bin/python3 -m flake8 --max-line-length=120 app/strategies/safety_order_calculator.py
```
Also re-run the frontend parity guard to confirm the backend numbers it pins didn't move:
```bash
cd frontend && npx vitest run src/components/bots/botUtils.test.ts
```

## Gotchas & Pitfalls
- **Don't change behavior.** If the characterization test moves a single value, stop — the two were NOT equivalent and the "duplicate" was actually a divergence you must understand first.
- Divide-by-zero: `get_total_multiplier` can't be 0 for valid configs, but guard anyway (`max_safety_orders` weirdness, negative volume_scale) — return a floor, never `Infinity` (CLAUDE.md rule 13).
- This is hot-path code; keep it allocation-free and pure (no I/O).

## Test Coverage Summary
A config-grid characterization test (the regression oracle) + the existing soft-ceiling/engine tests that exercise both functions indirectly + the frontend parity test re-run.

## Rollout
Backend code-only; `sudo systemctl restart zenithgrid`. No migration. Lowest-urgency of the three deferred items — it's drift *prevention*, not a live bug.
