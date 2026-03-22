# PRP: Order Type Per Phase + Take Profit Mode Redesign

**Feature**: Per-phase market/limit order type selection (base, DCA, take profit) always visible in the bot form, plus Take Profit mode redesign (fixed/trailing/minimum)
**Created**: 2026-02-25
**One-Pass Confidence Score**: 8/10

---

## Context & Goal

### Problem

1. **Order type invisible**: The `take_profit_order_type` parameter exists in `indicator_based.py` (line 222) but is **never rendered** in `DCABudgetConfigForm.tsx` — the form that indicator_based and conditional_dca strategies actually use. Users can't see or change it. Default is "limit", which surprises users who find limit close orders on their positions.

2. **No per-phase control**: Base orders are always market (hardcoded in `buy_executor.py` line 101). DCA orders check `safety_order_type` for "limit" (`buy_executor.py` line 73) but this field actually stores sizing type (`percentage_of_base`/`fixed_btc`/`fixed_usd`), so the limit path is dead code. Users have no way to choose market vs limit for any phase.

3. **Confusing TP/exit UI**: The "Take Profit / Exit" section shows:
   - "Take Profit %" — always active as minimum target
   - "Condition Exit Override %" — maps to `min_profit_for_conditions`, confusing name
   - "Enable Trailing Take Profit" checkbox + deviation
   - These are three separate controls for overlapping concepts

### Solution

**Part A — Per-phase order execution type**:
Add 3 always-visible dropdowns (market/limit, default: market) in the bot form:
- `base_execution_type` — controls base order execution
- `dca_execution_type` — controls DCA/safety order execution
- `take_profit_order_type` — controls close/exit order execution (already exists, change default to "market")

**Part B — Take Profit mode redesign**:
Replace the 3 overlapping controls with a single `take_profit_mode` selector:
- **Fixed** (default): Exit at `take_profit_percentage` above average entry. Simple hard target.
- **Trailing**: Activate trailing TP when price hits `take_profit_percentage`, then trail with `trailing_deviation`. Replaces `trailing_take_profit` bool.
- **Minimum**: `take_profit_percentage` becomes the minimum profit threshold. Actual exit is determined by take profit conditions. Requires at least one condition to be configured. Replaces `min_profit_for_conditions`.

### Who Benefits
All users configuring indicator_based or conditional_dca bots. Eliminates confusion around order types and exit strategies.

### Scope
- **In**: Strategy parameters, frontend form, buy executor, sell executor, signal processor, sample bots, migration
- **Out**: Perpetual futures (separate branch), stop loss changes, new endpoints

---

## Existing Code Patterns (Reference)

### Strategy Parameters (`backend/app/strategies/indicator_based.py`)

Current Take Profit group (lines 210-258):
```python
StrategyParameter(name="take_profit_percentage", type="float", default=3.0, group="Take Profit"),
StrategyParameter(name="take_profit_order_type", type="str", default="limit", options=["limit", "market"], group="Take Profit"),
StrategyParameter(name="min_profit_for_conditions", type="float", default=None, optional=True, group="Take Profit"),
StrategyParameter(name="trailing_take_profit", type="bool", default=False, group="Take Profit"),
StrategyParameter(name="trailing_deviation", type="float", default=1.0, group="Take Profit"),
```

Current Base Order group (lines 96-127): Only has sizing params, no execution type.

Current Safety Orders group (lines 128-208): `safety_order_type` controls sizing only.

### Frontend Form (`frontend/src/components/DCABudgetConfigForm.tsx`)

Take Profit section (lines 806-917): Renders `take_profit_percentage`, `min_profit_for_conditions` (labeled "Condition Exit Override %"), `stop_loss_enabled`/`stop_loss_percentage`, `trailing_take_profit`/`trailing_deviation`, and condition builder. Does NOT render `take_profit_order_type`.

Base Order section (lines ~470-530): Renders `base_order_type` (sizing) dropdown. No execution type.

Safety Order section (lines ~630-710): Renders `safety_order_type` (sizing) dropdown. No execution type.

### Buy Executor (`backend/app/trading_engine/buy_executor.py`)

Lines 70-99: Checks `safety_order_type == "limit"` for DCA limit orders. Dead code path for indicator_based since `safety_order_type` holds sizing values. Base orders always go to market (line 101+).

### Sell Executor (`backend/app/trading_engine/sell_executor.py`)

Lines 433-507: Reads `take_profit_order_type` from config (default "limit"). Limit path places order at mark price (bid/ask midpoint). Falls back to market if limit fails, with profit safety check.

### Signal Processor (`backend/app/trading_engine/signal_processor.py`)

Lines 856-912: Reads `take_profit_order_type` and `min_profit_for_conditions` from position's config snapshot. For limit orders, validates profit at mark price before proceeding.

### Strategy should_sell (`backend/app/strategies/indicator_based.py`)

Lines 1388-1427: Three exit paths checked in order:
1. Hard TP target (line 1390): `profit_pct >= take_profit_percentage` → if trailing enabled, trail; else sell
2. Condition exit (line 1413): `take_profit_signal and take_profit_conditions` → check `min_profit_for_conditions` (or fall back to `take_profit_percentage`)
3. Hold (line 1426): Neither condition met

### StrategyParameter Type (`frontend/src/types/index.ts` line 198)

```typescript
export interface StrategyParameter {
  name: string;
  display_name?: string;
  description: string;
  default: number | string | boolean | null;
  min_value?: number;
  max_value?: number;
  type: 'float' | 'int' | 'string' | 'bool' | 'text';
  options?: string[];
  required?: boolean;
  group?: string;
  visible_when?: Record<string, any>;
}
```

### Sample Bots (`frontend/src/pages/bots/data/sampleBots.ts`)

Most sample bots set `take_profit_order_type: 'limit'`, `trailing_take_profit: false`, no `min_profit_for_conditions`. These all need updating.

---

## Implementation Plan

### Task 1: Add new strategy parameters (backend)

**File**: `backend/app/strategies/indicator_based.py`

Add to Base Order group (after line 127):
```python
StrategyParameter(
    name="base_execution_type",
    display_name="Base Order Execution",
    description="Market (instant fill) or Limit (at current price)",
    type="str",
    default="market",
    options=["market", "limit"],
    group="Base Order",
),
```

Add to Safety Orders group (after line 207):
```python
StrategyParameter(
    name="dca_execution_type",
    display_name="DCA Order Execution",
    description="Market (instant fill) or Limit (at current price)",
    type="str",
    default="market",
    options=["market", "limit"],
    group="Safety Orders",
),
```

Replace the Take Profit parameters (lines 212-258) with:
```python
StrategyParameter(
    name="take_profit_percentage",
    display_name="Take Profit %",
    description="Profit target % from average buy price",
    type="float",
    default=3.0,
    min_value=0.1,
    max_value=50.0,
    group="Take Profit",
),
StrategyParameter(
    name="take_profit_mode",
    display_name="Take Profit Mode",
    description="Fixed (hard target), Trailing (trail from peak), or Minimum (condition-based exit)",
    type="str",
    default="fixed",
    options=["fixed", "trailing", "minimum"],
    group="Take Profit",
),
StrategyParameter(
    name="trailing_deviation",
    display_name="Trailing Deviation %",
    description="How far price can drop from peak before selling",
    type="float",
    default=1.0,
    min_value=0.1,
    max_value=10.0,
    group="Take Profit",
    visible_when={"take_profit_mode": "trailing"},
),
StrategyParameter(
    name="take_profit_order_type",
    display_name="Exit Order Execution",
    description="Market (instant fill) or Limit (at mark price)",
    type="str",
    default="market",
    options=["market", "limit"],
    group="Take Profit",
),
```

Note: `min_profit_for_conditions` is removed as a parameter. `trailing_take_profit` (bool) is removed. Both are replaced by `take_profit_mode`.

### Task 2: Update buy executor for base execution type (backend)

**File**: `backend/app/trading_engine/buy_executor.py`

In `execute_buy()` (line 70-99), add base order limit check BEFORE the safety order check:

```python
# Check if this is a base order that should use limit orders
is_base_order = trade_type == "initial"
config: Dict = position.strategy_config_snapshot or {}

if is_base_order and config.get("base_execution_type") == "limit":
    limit_price = current_price
    logger.info(f"  Placing limit base buy: {quote_amount:.8f} {quote_currency} @ {limit_price:.8f}")
    await execute_limit_buy(...)
    return None

# Check if this is a safety order that should use limit orders
is_safety_order = trade_type.startswith("safety_order")
dca_execution_type = config.get("dca_execution_type", "market")

if is_safety_order and dca_execution_type == "limit":
    # (existing limit buy logic, line 76-99)
```

**Key change**: Replace `safety_order_type == "limit"` check with `dca_execution_type == "limit"`. The old field `safety_order_type` continues to control sizing only.

Also update `execute_sell_short()` in `sell_executor.py` (lines 63-90) with the same pattern for short DCA orders.

### Task 3: Update sell executor for TP order type default (backend)

**File**: `backend/app/trading_engine/sell_executor.py`

Line 435: Change default from "limit" to "market":
```python
take_profit_order_type = config.get("take_profit_order_type", "market")
```

### Task 4: Update should_sell for take_profit_mode (backend)

**File**: `backend/app/strategies/indicator_based.py`

Replace lines 1388-1424 with mode-aware logic:

```python
tp_pct = self.config.get("take_profit_percentage")
tp_mode = self.config.get("take_profit_mode", "fixed")

if tp_pct is not None and profit_pct >= tp_pct:
    if tp_mode == "trailing":
        # Existing trailing logic (lines 1391-1406)
        trailing_dev = self.config.get("trailing_deviation", 1.0)
        # ... track peak, check deviation ...
        return True/False, reason
    elif tp_mode == "fixed":
        return True, f"Take profit target reached: {profit_pct:.2f}%"
    # tp_mode == "minimum" falls through to condition check below

# Check take profit conditions (only active in "minimum" mode)
if tp_mode == "minimum" and take_profit_signal and self.take_profit_conditions:
    if profit_pct >= (tp_pct or 3.0):
        return True, f"Take profit conditions met (profit: {profit_pct:.2f}%)"
    return False, f"Conditions met but profit too low ({profit_pct:.2f}% < {tp_pct}%)"
```

**Key behavioral change**: In "minimum" mode, hitting the TP% alone does NOT trigger a sell — conditions must also fire. In "fixed" mode, conditions are ignored (TP% is the hard target). In "trailing" mode, TP% activates the trail, conditions are ignored.

### Task 5: Update signal processor (backend)

**File**: `backend/app/trading_engine/signal_processor.py`

Lines 857-860: Replace `min_profit_for_conditions` logic with `take_profit_mode` check:
```python
take_profit_order_type = config.get("take_profit_order_type", "market")
take_profit_mode = config.get("take_profit_mode", "fixed")

# For limit orders in "minimum" mode, verify profit at mark price
if take_profit_order_type == "limit" and take_profit_mode == "minimum":
    tp_pct = config.get("take_profit_percentage", 3.0)
    # ... existing mark price validation using tp_pct as threshold ...
```

### Task 6: Update frontend form (frontend)

**File**: `frontend/src/components/DCABudgetConfigForm.tsx`

**A. Base Order section** (~line 490): After the base_order_type sizing dropdown, add:
```tsx
<div>
  <label className="block text-sm font-medium text-slate-300 mb-1">
    Base Order Execution
  </label>
  <select
    value={config.base_execution_type || 'market'}
    onChange={(e) => updateConfig('base_execution_type', e.target.value)}
    className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
  >
    <option value="market">Market (instant fill)</option>
    <option value="limit">Limit (at current price)</option>
  </select>
</div>
```

**B. Safety Order section** (~line 650): After the safety_order_type sizing dropdown, add the same pattern for `dca_execution_type`.

**C. Take Profit section** (lines 806-917): Redesign to:
1. Keep "Take Profit %" input
2. Replace "Condition Exit Override %" + "Enable Trailing Take Profit" checkbox with a single `take_profit_mode` dropdown: Fixed / Trailing / Minimum
3. When mode == "trailing": show `trailing_deviation` input
4. When mode == "minimum": show info text explaining conditions are required, and visually warn if no take profit conditions are configured
5. Add "Exit Order Execution" dropdown (market/limit) — always visible
6. Remove the old `min_profit_for_conditions` input entirely
7. Remove the `trailing_take_profit` checkbox entirely

### Task 7: Update sample bots (frontend)

**File**: `frontend/src/pages/bots/data/sampleBots.ts`

For all sample bots:
- Replace `take_profit_order_type: 'limit'` → `take_profit_order_type: 'market'`
- Replace `trailing_take_profit: false` → `take_profit_mode: 'fixed'`
- Replace `trailing_take_profit: true` → `take_profit_mode: 'trailing'`
- Where `min_profit_for_conditions` was set → `take_profit_mode: 'minimum'`
- Remove `min_profit_for_conditions` entries
- Add `base_execution_type: 'market'` and `dca_execution_type: 'market'`

### Task 8: Backwards compatibility for existing bots (backend)

Existing bots have configs without the new fields. Handle gracefully with defaults:

In `indicator_based.py` `should_sell()`: Derive `take_profit_mode` from legacy fields:
```python
tp_mode = self.config.get("take_profit_mode")
if tp_mode is None:
    # Legacy migration: infer mode from old fields
    if self.config.get("trailing_take_profit", False):
        tp_mode = "trailing"
    elif self.config.get("min_profit_for_conditions") is not None:
        tp_mode = "minimum"
    else:
        tp_mode = "fixed"
```

In `buy_executor.py`: `config.get("base_execution_type", "market")` — old bots without this field get market (current behavior).

In `buy_executor.py`: `config.get("dca_execution_type", "market")` — old bots get market (matches current behavior since the old limit path was dead code).

In `sell_executor.py`: Default changed to "market" matches what most users expect. Old bots with explicit `take_profit_order_type: "limit"` keep their setting (it's in their config).

### Task 9: Update limit_order_monitor (backend)

**File**: `backend/app/services/limit_order_monitor.py`

Line 196: Replace `min_profit_for_conditions` reference with `take_profit_mode` awareness:
```python
take_profit_mode = position_config.get("take_profit_mode", "fixed")
if take_profit_mode == "minimum":
    min_profit_threshold_pct = position_config.get("take_profit_percentage", 3.0)
else:
    min_profit_threshold_pct = position_config.get("take_profit_percentage", 3.0)
```

### Task 10: Migration for existing bot configs (backend)

**File**: `backend/migrations/migrate_take_profit_mode.py` (new file)

Idempotent migration that reads all bots' `strategy_config` JSON and:
1. If `trailing_take_profit: true` → set `take_profit_mode: "trailing"`, remove `trailing_take_profit`
2. If `min_profit_for_conditions` is not None → set `take_profit_mode: "minimum"`, copy value to `take_profit_percentage` if different, remove `min_profit_for_conditions`
3. Otherwise → set `take_profit_mode: "fixed"`
4. Change `take_profit_order_type` default from "limit" to "market" for bots that have no explicit value
5. Add `base_execution_type: "market"` and `dca_execution_type: "market"` if not present

Also update open positions' `strategy_config_snapshot` with same logic.

Also update templates in `backend/app/routers/templates.py` (lines 275, 301, 327).

### Task 11: Tests

Write tests for:

**`backend/tests/strategies/test_indicator_based.py`**:
- `test_should_sell_fixed_mode_hits_target_sells` — mode=fixed, profit >= TP% → sell
- `test_should_sell_fixed_mode_below_target_holds` — mode=fixed, profit < TP% → hold
- `test_should_sell_fixed_mode_ignores_conditions` — mode=fixed with conditions met but profit < TP% → hold
- `test_should_sell_trailing_mode_activates_on_target` — mode=trailing, profit >= TP% → starts trailing
- `test_should_sell_trailing_mode_triggers_on_deviation` — mode=trailing, price drops by trailing_deviation from peak → sell
- `test_should_sell_minimum_mode_conditions_met_above_min` — mode=minimum, conditions met + profit >= TP% → sell
- `test_should_sell_minimum_mode_conditions_met_below_min` — mode=minimum, conditions met + profit < TP% → hold
- `test_should_sell_minimum_mode_no_conditions_holds` — mode=minimum, no conditions configured → hold (never sells)
- `test_should_sell_legacy_trailing_inferred` — old config with `trailing_take_profit: true`, no `take_profit_mode` → trailing behavior
- `test_should_sell_legacy_min_profit_inferred` — old config with `min_profit_for_conditions`, no `take_profit_mode` → minimum behavior

**`backend/tests/trading_engine/test_buy_executor.py`**:
- `test_base_order_market_execution` — base_execution_type=market → market order
- `test_base_order_limit_execution` — base_execution_type=limit → limit order via execute_limit_buy
- `test_dca_order_market_execution` — dca_execution_type=market → market order
- `test_dca_order_limit_execution` — dca_execution_type=limit → limit order via execute_limit_buy
- `test_legacy_no_execution_type_defaults_market` — no field → market (backwards compat)

**`backend/tests/trading_engine/test_sell_executor.py`**:
- `test_close_market_by_default` — no explicit order type → market order
- `test_close_limit_when_configured` — take_profit_order_type=limit → limit close

---

## Validation Gates

```bash
# Lint Python
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m flake8 --max-line-length=120 \
  app/strategies/indicator_based.py \
  app/trading_engine/buy_executor.py \
  app/trading_engine/sell_executor.py \
  app/trading_engine/signal_processor.py \
  app/services/limit_order_monitor.py

# TypeScript type check
cd /home/ec2-user/ZenithGrid/frontend && npx tsc --noEmit

# Run all tests
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m pytest tests/ -v

# Run specific test files
./venv/bin/python3 -m pytest tests/strategies/test_indicator_based.py -v
./venv/bin/python3 -m pytest tests/trading_engine/test_buy_executor.py -v
./venv/bin/python3 -m pytest tests/trading_engine/test_sell_executor.py -v
```

---

## Gotchas & Edge Cases

1. **Position config snapshots**: Open positions have frozen `strategy_config_snapshot`. The migration must update these too, or the backwards-compat inference in Task 8 handles them at runtime. Runtime inference is safer (no risk of corrupting snapshots).

2. **`safety_order_type` dual meaning**: Currently holds sizing values AND is checked for "limit" in executors. The new `dca_execution_type` cleanly separates these. The old `safety_order_type == "limit"` check becomes dead code once we switch to `dca_execution_type`.

3. **Minimum mode with no conditions**: If user selects "minimum" but doesn't configure any take profit conditions, the bot would never sell (except via stop loss). The frontend should show a warning, and the backend should log a warning but not crash.

4. **Trailing TP state on position**: `trailing_tp_active`, `highest_price_since_tp` are position-level fields, not config fields. These are unaffected by the config redesign.

5. **Short positions**: `buy_executor.py` `execute_buy_close_short()` line 587 reads `take_profit_order_type` but always falls back to market (limit close for shorts not implemented). This stays unchanged — just update the default.

6. **DCA BudgetConfigForm vs generic param rendering**: The indicator_based strategy renders through `DCABudgetConfigForm`, NOT the generic `renderParameterInput` loop. All new UI must go in `DCABudgetConfigForm.tsx`. The strategy parameter definitions still need updating for other strategies that use the generic renderer.

---

## Migration Risk

Low. All changes are backwards-compatible via runtime inference of `take_profit_mode` from legacy fields. The migration script is optional (makes configs cleaner) but the system works without it.

The default change from limit→market for `take_profit_order_type` only affects **newly created** bots. Existing bots with explicit `"limit"` in their config keep it. Existing bots without the field get the new default "market" which is actually what most users expected.
