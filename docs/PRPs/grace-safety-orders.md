# PRP: Grace Safety Orders

## Context & Goal

**Problem.** When a deal exhausts its configured safety orders (SOs) and price keeps
dropping, the user currently has to manually bump that deal's `max_safety_orders` to
let one or two more SOs fire. That manual bump *recomputes and raises* the deal's
budget (`max_quote_allowed` via `compute_resize_budget`), which the user does NOT
always want to do across the board.

**Goal.** A per-bot setting **`grace_safety_orders`** (int, default `0`; UI label
**"grace"**) that pre-authorizes *N* bonus SOs beyond the configured count. They fire
automatically once the configured (or manually-bumped) SOs are used up — sequentially,
sized and triggered exactly like a manual bump would produce — **without ever entering
any budget/sizing calculation**. Overallocation beyond the planned budget is the
knowingly-accepted cost (same as today's manual bump, just automatic).

**Who benefits.** The bot owner (and any multi-user tenant) — removes manual babysitting
while keeping budget math honest. User-facing, opt-in, default 0 = exact current behavior.

### Locked decisions
1. Config key `grace_safety_orders`; UI label "grace".
2. **Stack-on-top:** effective placement ceiling = `snapshot.max_safety_orders` (bot
   config, or higher if this deal was manually bumped) **+ `grace_safety_orders`**. A
   manual bump must still be free to raise the snapshot beyond grace.
3. **Budget-excluded:** `max_quote_allowed`, soft-ceiling, expected-cost, volume-scale
   totals all compute off `max_safety_orders` only. Grace never enters them.

## Key mechanics discovered (verified — don't re-derive)

- **Placement gate** (the limit): `indicator_based.py:902` `if safety_orders_count >= max_safety: return False`.
- **Cascade loop** (fires multiple SOs on a gap-down): `indicator_based.py:934`
  `for so_num in range(first_so, max_safety + 1)`. Also a LIMIT site.
- **SO sizing** `safety_order_calculator.calculate_safety_order_size(config, base, order_number)`
  and **trigger price** `calculate_safety_order_price(ref, so_number, direction)` are
  per-index — they already continue the volume-scale / step-deviation ladder for *any*
  index, so grace SOs (#4, #5…) size & trigger identically to a manual bump. **No math change.**
- **THE KEYSTONE — just-in-time budget expansion (Option B, matches the manual edit).**
  For an existing position, the DCA `balance` is set at `_shared.py:351`:
  `quote_balance = position.max_quote_allowed - position.total_quote_spent`. The cascade
  refuses any SO whose size exceeds the remaining balance. **Grace must therefore expand
  the deal's budget — exactly like editing "Max Safety Orders" does today.** The manual
  edit (`position_actions_router.py:241-253` → `compute_resize_budget`) raises
  `max_quote_allowed` to the deal cost for the new SO count. Grace mimics this **just in
  time**: once a deal has deployed its *configured* SOs and grace remains, its effective
  budget becomes the deal cost for `configured + grace` SOs, computed via the SAME
  service functions (`calculate_expected_position_budget` / `calculate_max_deal_cost`)
  with an effective-count config — and `max_quote_allowed` is **persisted** to that value
  so the Budget column grows just like after a manual bump.
- **Reconciliation of the two requirements.** "Ignored by budget calc as if they never
  existed" applies to the **up-front planning** (deal-creation budget, soft-ceiling,
  `max_concurrent_deals` division) — those keep using the *configured* count, so grace
  never pre-reserves capital or shrinks concurrent deals. The budget only expands **per
  deal, once that deal actually crosses into grace** — so across many deals, the ones
  that never need grace keep the lean planned budget. This is the just-in-time auto
  version of the user's manual "bump when it runs out" workflow.
- `compute_resize_budget` lives in the router layer (`position_routers/helpers.py`) but
  only wraps the two `position_manager` service functions — call THOSE directly from
  `_shared.py` with `{**config, "max_safety_orders": effective}` (no upward router import).

### Every `max_safety_orders` usage, classified

| File:line | Role | Action |
|---|---|---|
| `indicator_based.py:895,902` | LIMIT (gate) | → `effective_max = max_safety + grace` |
| `indicator_based.py:934` | LIMIT (cascade range) | → `range(first_so, effective_max + 1)` |
| `monitor/pair_processor.py:135` | LIMIT (display gate) | → effective_max |
| `monitor/pair_processor.py:409,412` | LIMIT (`dca_slots_available`) | → effective_max |
| `monitor/pair_processor.py:455` | LIMIT (`_execute_trades`) | → effective_max (verify use) |
| `_shared.py:351` | BALANCE gate (runtime) | **+ grace allowance** (keystone, see below) |
| `position_manager.py:71,94` (`calculate_expected_position_budget`) | BUDGET | **NO CHANGE** |
| `position_manager.py:134,159` (`calculate_max_deal_cost`) | BUDGET | **NO CHANGE** |
| `position_manager.py:211,218` (`all_positions_exhausted_safety_orders`) | LIMIT? | Keep on **configured** (decides new-deal eligibility off planned SOs) — verify caller, document choice |
| `safety_order_calculator.py:20-49` (`get_total_multiplier`) | BUDGET | **NO CHANGE** |
| `safety_order_calculator.py:64-87` (`calculate_base_order_size`) | BUDGET | **NO CHANGE** |
| `compute_resize_budget` (manual bump) | BUDGET | **NO CHANGE** — verify it never reads grace |
| `indicator_params.py:51` | param registry | ADD `grace_safety_orders` param |
| `risk_presets.py:64`, `templates.py:298/324/350` | defaults | optional: add `grace_safety_orders: 0` |
| `schemas/position.py:165`, `position_query_router.py:35` | per-deal edit/query | out of scope (grace is bot-level) unless we expose per-deal later |
| `report_ai_service.py:417` | AI report params | optional: surface grace |

## Implementation Blueprint

### Backend

**1. Single source of truth for the effective ceiling.** Add ONE helper (avoid
scattering `max_safety + grace`):
```python
# safety_order_calculator.py
def effective_max_safety_orders(config: dict) -> int:
    """Placement ceiling = configured (or manually-bumped) SOs + grace bonus.
    Grace is NEVER part of any budget/sizing calc — see get_total_multiplier."""
    base = int(config.get("max_safety_orders", 0) or 0)
    grace = int(config.get("grace_safety_orders", 0) or 0)
    return base + max(0, grace)
```
Use it at every LIMIT site in the table above. Budget functions keep reading
`max_safety_orders` directly — untouched.

**2. Just-in-time budget expansion (keystone) — `_shared.py` ~line 351.** After the
existing `quote_balance = position.max_quote_allowed - position.total_quote_spent`, expand
the deal's budget once it has crossed into grace — mirroring the manual edit:
```python
config = position.strategy_config_snapshot or {}
configured = int(config.get("max_safety_orders", 0) or 0)
grace = int(config.get("grace_safety_orders", 0) or 0)
if position and grace > 0 and configured > 0:
    deployed = count_deployed_safety_orders(entry_trades_for_position(position))
    if deployed >= configured:                     # configured SOs spent → grace is live
        eff_config = {**config, "max_safety_orders": configured + grace}
        # SAME service formula the manual edit uses, just with the effective count.
        eff_cost = calculate_expected_position_budget(eff_config, aggregate_value)
        if eff_cost <= 0:
            eff_cost = calculate_max_deal_cost(eff_config, _first_buy_quote(position))
        if eff_cost > (position.max_quote_allowed or 0):
            position.max_quote_allowed = eff_cost   # PERSIST — Budget column grows, like a manual bump
            quote_balance = position.max_quote_allowed - position.total_quote_spent
```
This keeps ONE budget formula (rule 13) — it's the same functions, called with the
effective count only after the deal needs grace. Planning sites still call them with the
configured count, so grace stays out of up-front allocation/soft-ceiling. Persisting is
safe/idempotent (recomputed each cycle; commits with the buy). Do NOT add grace to the
planning callers.

**3. Config field.** Add `grace_safety_orders` to `indicator_params.py` param registry
(int, default 0, min 0, help text). It rides in `strategy_config` JSON — **no DB migration**
(JSON column). It is copied into `strategy_config_snapshot` at position creation like every
other config key (verify the snapshot copy is a full dict copy — it is).

**4. Mark grace fills for the UI.** A deployed SO's index = its order in
`entry_trades_for_position`. Grace = index > `snapshot.max_safety_orders`. No new column
needed; the frontend derives it (see below). Optionally include grace level in the
`reason` string already built at `indicator_based.py:985`.

### Frontend

**5. Bot config form** — `pages/bots/components/StrategyConfigSection.tsx`: add a "Grace
safety orders" number input next to Max Safety Orders. Help text: *"Bonus safety orders
beyond your configured count. Only used after the configured ones are exhausted. NOT
counted in budget — these intentionally overallocate (accepted risk)."* Wire through
`pages/bots/helpers.ts` + `botUtils.ts` defaults (0) and `useValidation.ts` (int ≥ 0).

**6. Chart "pips" (distinct color)** — `components/positions/DealChart.tsx:635-689`:
- Read `const grace = Number(cfgSnapshot.grace_safety_orders || 0)`.
- `base_order` branch (line 654): loop `i < maxSafetyOrders + grace`; for the price line,
  if `i + 1 > maxSafetyOrders` use grace color `#f59e0b` (amber) and title `G${i+1-maxSafetyOrders}` (or `SO${i+1}*`).
- `average_price`/`last_buy` branch (line 676): change `soRemaining` to use
  `maxSafetyOrders + grace`; color the next line amber when `soTriggered + 1 > maxSafetyOrders`.
- DCA history markers (`DealChart.tsx:722-747`): color the marker amber when its SO index
  > `maxSafetyOrders`.
- Add a small legend note ("amber = grace SO").

Confirm `position.safety_orders_deployed` and `cfgSnapshot.grace_safety_orders` are present
in the position payload (`position_query_router.py` field list — add `grace_safety_orders`
if snapshot fields are whitelisted).

## Files to modify
- `backend/app/strategies/safety_order_calculator.py` (+`effective_max_safety_orders`)
- `backend/app/strategies/indicator_based.py` (gate 902, cascade 934)
- `backend/app/monitor/pair_processor.py` (135, 409/412, 455)
- `backend/app/trading_engine/signal_processor/_shared.py` (351 — grace allowance)
- `backend/app/strategies/indicator_params.py` (param)
- (optional) `risk_presets.py`, `routers/templates.py`, `report_ai_service.py`, `position_query_router.py`
- `frontend/src/pages/bots/components/StrategyConfigSection.tsx`, `pages/bots/helpers.ts`,
  `components/bots/botUtils.ts`, `pages/bots/hooks/useValidation.ts`
- `frontend/src/components/positions/DealChart.tsx`
- Tests (below)

## Test-Driven Development (write FIRST)
`backend/tests/strategies/test_safety_order_calculator.py`:
- `effective_max_safety_orders`: base 3 + grace 2 = 5; grace 0 = base; negative grace clamped.

`backend/tests/.../test_grace_budget_exclusion.py`:
- **Regression:** `calculate_expected_position_budget`, `calculate_max_deal_cost`,
  `get_total_multiplier` return **identical** values for `grace=0` vs `grace=2` (same base).
- `compute_resize_budget` unchanged by grace.

`backend/tests/strategies/test_indicator_based_grace.py` (mock position/trades):
- Gate allows up to `base+grace` SOs; blocks at `base+grace+1`.
- grace SO #4/#5 size == `calculate_safety_order_size(order_number=4/5)` (equals manual-bump-to-5).
- Cascade range extends into grace levels.
- **grace=0 byte-for-byte identical** to current behavior (snapshot the decisions).

`backend/tests/.../test_shared_grace_allowance.py`:
- With budget exhausted (`total_quote_spent == max_quote_allowed`) and `grace=2`,
  `quote_balance` includes the 2-level grace allowance; with `grace=0` it's `0`.
- `max_quote_allowed` is never mutated by the allowance path.

**Stacking:** snapshot bumped to 4 + grace 2 → effective ceiling 6.

**Multiuser/account-scoping:** `multiuser-security` agent after — grace reads only the
position's own snapshot; no cross-account/bot leakage (rule 12).

Frontend: extend `useValidation.test.ts` (grace int ≥ 0) and a DealChart unit/snapshot
test that grace price lines use the amber color and beyond-config markers are amber.

## Validation Gates
```bash
backend/venv/bin/python3 -m flake8 --max-line-length=120 \
  backend/app/strategies/safety_order_calculator.py \
  backend/app/strategies/indicator_based.py \
  backend/app/monitor/pair_processor.py \
  backend/app/trading_engine/signal_processor/_shared.py \
  backend/app/strategies/indicator_params.py
backend/venv/bin/python3 -m pytest backend/tests/strategies backend/tests/trading_engine -q -W error
cd frontend && npx tsc --noEmit && npx eslint src/components/positions/DealChart.tsx src/pages/bots/components/StrategyConfigSection.tsx
backend/venv/bin/python3 -c "from app.strategies.safety_order_calculator import effective_max_safety_orders; print(effective_max_safety_orders({'max_safety_orders':3,'grace_safety_orders':2}))"  # -> 5
```
Run `validation-gates`, `test-auditor`, `regression-check`, and `multiuser-security` agents
before shipit (per CLAUDE.md proactive workflow).

## Commercialization Check
- [x] Multi-user: grace is per-bot config in `strategy_config`, scoped to the owning
  account/bot via the position snapshot. No shared state.
- [x] Credentials: untouched.
- [x] Pay-for: yes — "auto-grace SOs without inflating budget" is a differentiated DCA
  control vs. fixed-SO platforms.

## Rollback Plan
- Pure feature-add behind `grace_safety_orders` default `0` → zero behavior change when unset.
- Revert the dev branch; no DB migration to undo (JSON config). No data backfill.
- If only the runtime-allowance misbehaves, set all bots' `grace_safety_orders` to 0
  (config edit) to instantly neutralize while keeping the rest.

## Risks / watch-items
- **Account-funds reality:** the grace allowance grants *deal-budget* headroom; actual
  fills are still subject to real wallet funds at execution. A grace SO that can't be
  funded will be rejected by the exchange and now handled cleanly by the v3.10.0
  unconfirmed-buy guard (no $0 trade / phantom position). Document this; do not add a
  second budget gate.
- **Every LIMIT site must move together** or a grace SO is half-enabled (gate allows but
  cascade/`dca_slots_available` blocks). The single `effective_max_safety_orders` helper
  + the enumerated table mitigate this; `regression-check` should confirm no missed site.
- **`all_positions_exhausted_safety_orders`**: confirm its caller intent before deciding
  configured-vs-effective; default to configured (planned SOs) and document.

## Quality Score
**9/10** — all layers traced to exact line numbers, the budget-vs-limit split is
enumerated, the non-obvious keystone (runtime grace allowance vs. the budget-raising
manual-bump path) is identified, and the test plan locks the budget-exclusion invariant.
The −1 is residual verification of `pair_processor.py:455` and
`all_positions_exhausted_safety_orders` caller intent, to be confirmed during execution.
