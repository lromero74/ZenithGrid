# PRP: High-Risk Doubling Preset — Speculative 2x Hunter

**Feature**: Add a bot preset that hunts for high-risk, high-reward "double in a day" opportunities, with an account-level speculative bucket that hard-caps total cost-basis exposure across all speculative-tagged bots.
**Feature Branch**: `feature/high-risk-doubling-preset`
**Created**: 2026-04-22
**One-Pass Confidence Score**: 7/10

> **Status (2026-04-23)**: All 6 phases (A–F) **shipped** across v2.165.0–v2.165.4. Phase A (bucket infrastructure), Phase B (preset + catalyst-mode signals), Phase C (bucket endpoint + preset auto-population), Phase D (frontend UX), Phase E (polish in subsequent patches), Phase F (calibration alert monitor) are all live in production. The signal-quality follow-up mentioned below ("v2 once enough signal logs accumulate") has its own separate PRP — `PRPs/done/speculative-weights-auto-calibration.md`, Phase 1 of which shipped in v2.166.0.

> **7/10** because the plumbing (preset defaults, AI prompt branch, bucket validator) is mechanical and well-scaffolded by existing patterns (`risk_presets.py`, `calculate_available_usd`, `AISpotOpinionEvaluator`), but the signal-quality work — tuning the doubling-probability scorer and prompt against real outcomes — will need iteration after first ship. Plan for a v2 once enough signal logs accumulate.

---

## TL;DR

A new bot preset (`"speculative"`) that tunes the AI indicator to detect likely 2x-in-a-day setups and enforces tight exit discipline (fast TP, tight SL, time-based cutoff, no safety orders by default). Speculative bots opt into an **account-level bucket** sized by `Account.speculative_allocation_pct`. The bucket enforces a **hard cap on total cost basis** deployed across all speculative-tagged bots on that account — winners at 2x do **not** expand headroom for new bets. The UI surfaces the bucket prominently with a warning banner and a confirmation checkbox on bot creation, then shows deployed-vs-bucket usage on the Dashboard so damage is isolated and visible.

---

## Context & Goal

### User Story

> "I want to dedicate a small portion of my portfolio to swinging for 2x-in-a-day trades without risking the main bucket. When I spin up a second speculative bot, I don't want to have to recompute the allocation myself — the platform should keep the total speculative exposure capped at the % I chose, even across multiple bots and pairs."

### Problem

The current AI indicator (`AISpotOpinionEvaluator` — see `backend/app/indicators/ai_spot_opinion.py`) is tuned for sober mean-reversion / momentum entries. Its default prefilter actively rejects setups that are already up today (`prefilter_max_drop_24h` is bidirectional — a coin up 15% with catalyst heat gets filtered out the same way a coin crashing 15% does). There's no way to express "I want to hunt for asymmetric upside, accept a low win rate, but contain the damage to a known % of my portfolio."

There's also no cross-bot budget coordination for tagged high-risk bots. A user who creates three "speculative" bots today would have three independent budgets; the "this is 5% of my portfolio" promise would silently break to 15%.

### Goal

Ship a preset that:
1. **Selects for catalyst/pump-setup opportunities** rather than mean-reversion.
2. **Enforces exit discipline** aligned with the signal type (fast TP, tight SL, time-based exit, no safety orders by default).
3. **Opts into a shared account bucket** so total speculative cost-basis exposure is hard-capped at the user's chosen % regardless of how many speculative bots they spin up or how many pairs they trade.
4. **Uses cost-basis accounting** (not mark-to-market) so winners don't fund new bets.
5. **Surfaces the risk prominently** — warning banner, confirmation checkbox, separate PnL card on Dashboard.

### Non-Goals

- Removing the existing AI preset. This is additive.
- Building a new exchange or data provider. All signals derive from Coinbase candles, existing news feed, and tool-use context already available to the AI indicator.
- Building leverage / margin support for this preset. Spot only in v1.
- Auto-sizing the user's bucket. User picks the % manually.

---

## Constraints

### Hard Cap Must Hold Across Bots

If a user sets `speculative_allocation_pct = 5` and spins up 3 speculative bots trading 30 pairs between them, the sum of `position.total_quote_spent` across all open positions on those 3 bots must stay ≤ `5% × account_value`. Every new entry attempt on a speculative-tagged bot must revalidate against this cap **before** placing an order.

### Cost-Basis Accounting

The bucket's "deployed" figure is `SUM(position.total_quote_spent)` for open positions on speculative-tagged bots, not mark-to-market value. Otherwise a few winners at 2x would silently let the user pile on at the worst time. Unrealized gains belong to the user but do not expand bucket headroom.

### Existing Risk-Preset Pattern

This must layer on top of, not replace, the existing `RISK_PRESETS` dict in `backend/app/indicators/risk_presets.py`. The current three presets (`aggressive`, `moderate`, `conservative`) tune `min_confluence_score` and `ai_confidence_threshold`; the speculative preset is a sibling entry plus additional preset-only config keys.

### AI Tool-Use Parity

The preset MUST reuse the existing tool-use loop (`_ARG_TOOL_NAMES` in `ai_spot_opinion.py`: `get_candle_window`, `get_recent_news`, `get_trade_history`, `get_prior_ai_signals`). No new provider plumbing. The catalyst-mode branch is a prompt + metrics change, not a transport change.

### Multi-User Isolation

All bucket queries MUST scope by `account_id`. A speculative bot on user A's account must never see user B's bucket or bot cost bases. Mirror the pattern in `backend/app/services/budget_calculator.py::calculate_available_usd` (which already enforces account-level isolation).

---

## Existing Patterns (Reference)

### Risk Preset Shape — `backend/app/indicators/risk_presets.py`
```python
RISK_PRESETS = {
    "aggressive":   {"min_confluence_score": 30, "ai_confidence_threshold": 60, "entry_timeframe": "FIVE_MINUTE",   ...},
    "moderate":     {"min_confluence_score": 40, "ai_confidence_threshold": 70, "entry_timeframe": "FIFTEEN_MINUTE", ...},
    "conservative": {"min_confluence_score": 50, "ai_confidence_threshold": 80, "entry_timeframe": "THIRTY_MINUTE",  ...},
}

def get_risk_preset_defaults(preset_name: str) -> dict:
    return RISK_PRESETS.get(preset_name, RISK_PRESETS["moderate"]).copy()
```
Add `"speculative"` here. See Recommended Design §2.

### Cross-Bot Account-Scoped Budget — `backend/app/services/budget_calculator.py`
The `calculate_available_usd` / `calculate_available_btc` functions already enforce account-level reservation math for bidirectional bots:
- Query all matching bots on the same account: `Bot.account_id == account_id`, exclude self via `exclude_bot_id`.
- Sum reservations across bots.
- Return `max(0.0, raw_balance - total_reserved)`.

Mirror this shape exactly for `speculative_bucket_service.py`. Replace "bidirectional" filter with "speculative" filter (`strategy_config['is_speculative'] == true`) and replace "reserved" with "cost basis of open positions."

### AI Evaluator Prompt + Prefilter — `backend/app/indicators/ai_spot_opinion.py`

The `_build_prompt()` method is already a pure function of metrics + context. Extend (don't fork) it with a `catalyst_mode` branch that swaps the question ("Should I BUY this position right now?" → "Is this likely to double in the next 24 hours?") and appends additional metrics (volume surge, compression, already-up-today).

The `_check_buy_prefilter()` method currently blocks entries where `abs(price_change_24h) > prefilter_max_drop_24h`. For speculative bots, the prefilter should:
- **Allow** coins up +10% to +40% today (that's the entry zone for catalyst hunts).
- **Block** coins already up >50% today (too late, likely distribution).
- **Block** coins down more than 10% (crashing, not setup).

Add a `speculative_mode: bool` param to `AISpotOpinionParams` and branch inside the existing function rather than adding a new one.

### Position Preflight Hook — `backend/app/trading_engine/signal_processor/buy_decision.py`

`_run_new_position_preflight()` is the canonical place to insert per-entry validation. It already handles stable-pair guard, soft ceiling, deal cooldown, and returns `(blocked, reason, open_positions_count)`. Add the speculative-bucket check as one more guard in that function. Early-return pattern mirrors perfectly.

### Account Model — `backend/app/models/trading.py`

`Account` already carries per-account trading knobs (`rebalance_*`, `min_balance_*`, `auto_buy_*`, `is_paper_trading`). Add `speculative_allocation_pct: Float default=0.0` next to the rebalance block (lines ~77-93 of `trading.py`). Zero means "no bucket; speculative bots are blocked from opening positions" — an explicit opt-in.

### Migration Pattern — `backend/migrations/076_bot_budget_rebalancer.py`

Perfect template for "add column to `trading.accounts` + create supporting table if needed, idempotent, both PG and SQLite paths, with `GRANT` for the `zenithgrid_app` role on PG." See §6 of the Recommended Design for why we don't actually need a new table.

### Bot Form + Preset UX — `frontend/src/pages/bots/components/BotFormModal.tsx` + `frontend/src/components/trading/AdvancedConditionBuilder.tsx`

The `RiskPreset` type in `AdvancedConditionBuilder.tsx:60-70` already renders a preset dropdown. Extend the union to include `'speculative'` and extend `RISK_PRESETS` with a label + helper text. See Frontend Implementation §11.

---

## Recommended Design

### 1. Account-Level Speculative Bucket

**New column**: `trading.accounts.speculative_allocation_pct: FLOAT NOT NULL DEFAULT 0.0`
- Range: 0.0 to 100.0.
- Default 0 = no bucket, speculative bots are soft-blocked from opening new positions.
- Interpreted as "% of current `aggregate_usd_value` of the account" (same aggregate used by existing budget math).

**New service**: `backend/app/services/speculative_bucket_service.py`

```python
async def get_speculative_bucket_info(
    db: AsyncSession, account_id: int, aggregate_usd_value: float,
) -> dict:
    """Return the user's full speculative bucket snapshot.

    Shape:
    {
      "bucket_pct": 5.0,                 # From Account.speculative_allocation_pct
      "bucket_usd": 500.0,               # bucket_pct × aggregate_usd_value
      "deployed_cost_basis_usd": 200.0,  # Σ position.total_quote_spent for open positions
                                         # on speculative-tagged bots in this account
      "available_usd": 300.0,            # max(0, bucket_usd - deployed_cost_basis_usd)
      "active_bot_count": 2,
      "open_position_count": 3,
      "max_concurrent_slots": 10,        # Σ max_concurrent_deals across tagged bots
      "per_slot_budget_usd": 30.0,       # available_usd / remaining_slots
    }
    """

async def validate_speculative_entry(
    db: AsyncSession, bot: Bot, intended_cost_basis_usd: float,
    aggregate_usd_value: float,
) -> tuple[bool, str]:
    """Gate a speculative-tagged bot's new-position attempt against the bucket.
    Returns (allowed, reason). Called from _run_new_position_preflight."""
```

Both functions MUST scope by `account_id` exactly like `calculate_available_usd` does (copy the query pattern). Positions on non-speculative bots are not counted; positions on speculative bots across other accounts are not counted.

**Speculative-tagged** is defined as: `bot.strategy_config.get("is_speculative") is True` (a flag added automatically when the user selects the preset). This mirrors the `enable_bidirectional` flag already used by `budget_calculator.py`. No new column on `Bot`.

### 2. Speculative Preset Definition

Extend `backend/app/indicators/risk_presets.py`:

```python
RISK_PRESETS["speculative"] = {
    # AI evaluation
    "min_confluence_score": 35,        # Low-ish bar but not as low as "aggressive"
    "ai_confidence_threshold": 70,     # Need genuine AI conviction; false positives are costly
    "entry_timeframe": "FIFTEEN_MINUTE",
    "trend_timeframe": "ONE_HOUR",     # Shorter than moderate; catalysts move fast
    "require_trend_alignment": False,  # Catalysts often break trend
    "max_volatility": None,            # Don't filter on volatility; volatility IS the opportunity
    # Preset-only keys (consumed by indicator_based.py + ai_spot_opinion.py)
    "is_speculative": True,            # Opt-in tag — speculative_bucket_service looks for this
    "speculative_mode": True,          # ai_spot_opinion uses catalyst prompt branch
    "target_multiple": 2.0,            # Used by the prompt ("likely to 2x in N hours")
    "target_horizon_hours": 24,
    # Exit discipline defaults (consumed by indicator_based.py)
    "take_profit_percentage": 25.0,    # Fast partial exit — 25% is meaningful for a 2x hunt
    "trailing_take_profit": True,
    "trailing_tp_deviation": 5.0,      # Give it room to run once triggered
    "stop_loss_enabled": True,
    "stop_loss_percentage": -12.0,     # Tight — these set up fast or fail fast
    "max_safety_orders": 0,            # NO doubling down on microcap pumps
    "speculative_max_hold_hours": 24,  # Time-based exit if neither TP nor SL trips
    # Prefilter overrides (consumed by ai_spot_opinion.py)
    "prefilter_max_drop_24h": 10.0,    # Block crashers
    "prefilter_max_gain_24h": 50.0,    # Block too-late setups (NEW key)
    "prefilter_min_gain_24h": -10.0,   # Allow already-up setups (NEW — negates the "drop" one-sidedness)
    "prefilter_volume_min_ratio": 1.5, # Require volume confirmation
    "prefilter_rsi_max": 85.0,         # Looser than default 70 — catalyst pumps run hot
}
```

### 3. AI Catalyst Mode

**Extend `AISpotOpinionParams`** (`backend/app/indicators/ai_spot_opinion.py`):

```python
@dataclass
class AISpotOpinionParams:
    # ... existing fields ...
    speculative_mode: bool = False
    target_multiple: float = 2.0
    target_horizon_hours: int = 24
    prefilter_max_gain_24h: Optional[float] = None  # None = no upper check (existing behavior)
    prefilter_min_gain_24h: Optional[float] = None  # None = use prefilter_max_drop_24h as -X (existing)
```

**Extend `_calculate_metrics`** to include:

- `volume_30d_ratio`: current 24h volume / average of last 30 24h-rollups (instead of 20-candle moving avg).
- `compression_ratio`: (max close − min close over last 24 candles) / median(|close_i − close_{i-1}|). High value = coiled spring broke out.
- `momentum_1h`: 1-hour price change %.
- `momentum_acceleration`: (momentum_1h − momentum_6h/6). Positive = accelerating.

These are cheap to compute from the existing candle array.

**Extend `_check_buy_prefilter`** to honor the new keys when `speculative_mode`:
```python
if params.speculative_mode:
    if params.prefilter_max_gain_24h is not None and price_change_24h > params.prefilter_max_gain_24h:
        return False, f"Too late — already up {price_change_24h:.1f}% > {params.prefilter_max_gain_24h}%"
    if params.prefilter_min_gain_24h is not None and price_change_24h < params.prefilter_min_gain_24h:
        return False, f"Crashing — down {price_change_24h:.1f}% < {params.prefilter_min_gain_24h}%"
else:
    # existing behavior (symmetric drop filter)
    if price_change_24h < -params.prefilter_max_drop_24h:
        return False, ...
```

**Extend `_build_prompt`** with a catalyst branch when `speculative_mode=True`:

```python
if speculative_mode:
    question = (
        f"Question: Is {product_id} likely to reach a {target_multiple}x price move "
        f"within the next {target_horizon_hours} hours? "
        f"Answer 'buy' only if yes with high conviction — otherwise 'hold'."
    )
    context_hint = (
        "\nYou are hunting asymmetric upside. You should prefer passing (hold) most of "
        "the time; only commit (buy) when a concrete catalyst, volume surge, or "
        "compression breakout meaningfully raises the odds. Use get_recent_news "
        "proactively here — this question is mostly answered by catalysts, not "
        "technicals alone."
    )
```

The speculative branch also asks the LLM to include a `doubling_probability_score: int (0-100)` field in its JSON response, logged to `ai_opinion_log` for calibration over time.

### 4. Speculative Signal-Weighting Module

**New module**: `backend/app/indicators/speculative_signals.py`

A pre-AI quantitative scorer that runs before the LLM call and is injected into the prompt as pre-computed context. This lets the AI reason over a summarized score while still doing its own narrative-catalyst analysis via tools.

```python
WEIGHTS = {
    "volume_surge":         25,  # volume_30d_ratio ≥ 3.0
    "compression_breakout": 20,  # compression_ratio ≥ 3.0 with positive momentum_1h
    "momentum_accelerating":20,  # momentum_acceleration > 0 with momentum_1h ≥ +2%
    "micro_mid_cap":        10,  # heuristic: product listed < 90 days ago OR not in top-20 popularity
    "correlation_break":    10,  # |momentum_1h − btc_momentum_1h| > 3%
    "volume_vs_mcap":       15,  # high turnover ratio suggests "in play"
}
# Sum of weights = 100

def score_speculative_setup(metrics: dict, btc_metrics: dict, product_id: str) -> dict:
    """Returns {score: int 0-100, components: {name: (fired, weight_contribution)}}
    for logging and prompt injection."""
```

**Why a pre-score if the AI can read the same data?**
- Calibratable over time — after enough `ai_opinion_log` rows, we can adjust weights using win-rate data.
- Deterministic, testable.
- Gives the LLM a human-audited scaffold rather than freelancing the full analysis.
- Score is included in the prompt as one number the AI can use or override.

### 5. Exit Discipline

Most of the exit discipline is already present in `indicator_based.py` (take_profit_percentage, trailing_take_profit, trailing_tp_deviation, stop_loss_enabled, stop_loss_percentage). The preset wires defaults (see §2) and no code change is needed for those.

**New: time-based max-hold exit**

The speculative preset introduces `speculative_max_hold_hours`. If a position on a speculative bot is older than this cutoff and neither TP nor SL has tripped, force-close it. Rationale: 2x-in-24h setups that haven't moved in 24h are not going to; get out and free the bucket slot.

**Implementation**:

Add to `backend/app/strategies/indicator_based.py::should_sell()` (or the equivalent exit-decision path). Before the SL/TP checks:

```python
max_hold_hours = self.config.get("speculative_max_hold_hours")
if max_hold_hours and position and position.opened_at:
    age_hours = (datetime.utcnow() - position.opened_at).total_seconds() / 3600
    if age_hours >= max_hold_hours:
        return True, f"Speculative max hold ({max_hold_hours}h) reached — exiting"
```

This stays out of other presets because `speculative_max_hold_hours` is only set by the speculative preset.

### 6. Preflight Hook

In `backend/app/trading_engine/signal_processor/buy_decision.py::_run_new_position_preflight`, after the deal-cooldown check:

```python
if bot.strategy_config and bot.strategy_config.get("is_speculative"):
    from app.services.speculative_bucket_service import validate_speculative_entry
    # Use the first buy's typical cost basis: base_order_size in quote currency
    intended_cost_basis = strategy.config.get("base_order_size", 0.0)
    aggregate_usd = aggregate_value or 0.0
    allowed, reason = await validate_speculative_entry(
        db, bot, intended_cost_basis, aggregate_usd
    )
    if not allowed:
        return True, reason, open_positions_count
```

This is the single choke point — no other code path opens new positions.

### 7. UX Guardrails

**Bot creation**:
- Preset dropdown shows "Speculative (High-Risk 2x Hunter)" with a red/amber treatment.
- Selecting it auto-populates `strategy_config` with preset defaults, pops a warning banner:
  > "Speculative bots hunt for asymmetric upside. **Historical win rate is typically under 20%.** Typical losses are -12% per failed bet. Only allocate capital you can lose entirely. This bot will respect your account's Speculative Allocation cap — open positions across all speculative bots cannot exceed that % of your portfolio."
- Requires a "I understand the risk" confirmation checkbox before save.
- Shows the account's current bucket setting and available headroom. If `speculative_allocation_pct == 0`, the save button is disabled with copy directing the user to Account Settings first.

**Account settings**:
- New field: "Speculative Allocation %" (0-100, default 0), next to rebalance targets. Tooltip explains cost-basis semantics.

**Dashboard card**:
- New card: "Speculative Bucket" showing `deployed / bucket` with a progress bar and a link to the speculative bots.
- Shows separate realized/unrealized PnL for speculative-tagged positions so damage is isolated from the main portfolio view.

**AI opinion log**:
- When the opinion came from a speculative bot, render the `doubling_probability_score` and the component breakdown (from `speculative_signals.py`).

---

## Implementation Blueprint

### TDD Requirement

Write failing tests first. Each task below lists the tests to write before the implementation code.

---

### Phase A — Backend Infrastructure

**Task A1 — Account column migration** (`backend/migrations/082_speculative_bucket.py`)

Test (new file `backend/tests/migrations/test_082_speculative_bucket.py`):
- Running migration adds column; re-running is a no-op.
- Column defaults to 0.0.

Implementation:
- Mirror `076_bot_budget_rebalancer.py` exactly. Add one column; no new table needed (bucket state is derived from `position.total_quote_spent` at query time).
- Both PG and SQLite branches.

**Task A2 — Account model field**

Test: import Account model, assert `speculative_allocation_pct` attribute exists and defaults to `0.0`.

Implementation: add column to `backend/app/models/trading.py::Account` (~line 93, next to rebalance fields).

**Task A3 — speculative_bucket_service.py**

Tests (`backend/tests/services/test_speculative_bucket_service.py`):
- Happy path: one speculative bot with one open position, `total_quote_spent=50`, bucket=500 → `deployed=50`, `available=450`.
- Multi-bot aggregation: two speculative bots, one with 2 open positions, sum cost bases correctly.
- **Cost-basis semantics**: position.total_quote_spent=100, current market value=200 (2x winner) → deployed=100 (not 200). Winners do not expand headroom.
- Account isolation: bots on other account_ids do not contribute to this bucket.
- Non-speculative bot exclusion: bots without `is_speculative=true` do not contribute.
- `validate_speculative_entry` returns `(False, reason)` when intended cost basis exceeds available; `(True, "")` when it fits.
- Zero bucket (`speculative_allocation_pct=0`): validator always returns `(False, "Speculative bucket not configured for this account")`.

Implementation: mirror `backend/app/services/budget_calculator.py::calculate_available_usd` structure exactly. Replace the bidirectional filter with `Bot.strategy_config.op('->>')('is_speculative') == 'true'`. Replace the reservation sum with a joined query over `trading.positions` filtered to `status='open'` and the bot list.

**Task A4 — Preflight hook**

Tests (add to `backend/tests/trading_engine/test_buy_decision.py` or create `test_speculative_preflight.py`):
- Speculative bot with bucket room → `_run_new_position_preflight` does not block.
- Speculative bot without bucket room → blocks with reason containing "Speculative".
- Non-speculative bot → unchanged behavior (bucket check not invoked).
- Zero bucket → blocks immediately with actionable reason.

Implementation: add the speculative-check block shown in Recommended Design §6.

---

### Phase B — Preset + Signals

**Task B1 — risk_presets.py entry**

Tests (`backend/tests/indicators/test_risk_presets.py`):
- `get_risk_preset_defaults("speculative")` returns the dict from §2.
- Required keys present: `is_speculative`, `speculative_mode`, `target_multiple`, `speculative_max_hold_hours`, all exit discipline defaults.

Implementation: append to `RISK_PRESETS` dict.

**Task B2 — Speculative signal scorer**

Tests (`backend/tests/indicators/test_speculative_signals.py`):
- Each weight component: pass metrics that fire only that component, assert its weight contributes exactly.
- Boundary conditions: volume_30d_ratio=3.0 exactly triggers, 2.99 does not.
- Total score bounded [0, 100].
- `components` dict is returned with {name: (fired: bool, contribution: int)} for logging.
- Happy path: all components fire → score=100.
- Failure case: no metrics → score=0, no crash.

Implementation: new file as specified in Recommended Design §4.

**Task B3 — AI catalyst mode**

Tests (`backend/tests/indicators/test_ai_spot_opinion_catalyst.py`):
- `AISpotOpinionParams.from_config` reads `speculative_mode`, `target_multiple`, `target_horizon_hours`, `prefilter_max_gain_24h`, `prefilter_min_gain_24h`.
- `_check_buy_prefilter` with `speculative_mode=True`, `price_change_24h=+20`, `prefilter_max_gain_24h=50` → allowed (current behavior would block).
- `_check_buy_prefilter` with `speculative_mode=True`, `price_change_24h=+60`, `prefilter_max_gain_24h=50` → blocked with "too late" reason.
- `_check_buy_prefilter` with `speculative_mode=True`, `price_change_24h=-15`, `prefilter_min_gain_24h=-10` → blocked with "crashing" reason.
- `_build_prompt` with `speculative_mode=True` contains "likely to reach a 2x" and the catalyst hint paragraph.
- `_build_prompt` with `speculative_mode=False` is byte-identical to today (regression guard).
- `_calculate_metrics` returns new keys: `volume_30d_ratio`, `compression_ratio`, `momentum_1h`, `momentum_acceleration`.
- `_parse_llm_response` tolerates the optional `doubling_probability_score` field.

Implementation: extend the params dataclass, the metrics function, the prefilter, and the prompt builder per Recommended Design §3.

**Task B4 — Exit discipline: time-based max hold**

Tests (add to `backend/tests/strategies/test_indicator_based.py`):
- Position opened 23h ago with `speculative_max_hold_hours=24` → `should_sell` returns `(False, ...)` on other grounds.
- Position opened 25h ago with `speculative_max_hold_hours=24` → `should_sell` returns `(True, "Speculative max hold ...")`.
- `speculative_max_hold_hours` absent from config → age-based exit never triggers (preserves all other preset behavior).

Implementation: add the check to the existing `should_sell` before SL/TP checks per Recommended Design §5.

---

### Phase C — Endpoint + Strategy Wiring

**Task C1 — Bucket info endpoint**

Tests (`backend/tests/routers/test_speculative_bucket_router.py`):
- `GET /api/accounts/{id}/speculative-bucket` returns the shape from `get_speculative_bucket_info`.
- 403 for cross-user access (mirror `accounts_query_router` patterns).
- Stale-while-revalidate friendly: no mutation on read.

Implementation: add endpoint to `backend/app/routers/accounts_query_router.py`. Use `accessible_accounts_filter(current_user.id)` as existing endpoints do.

**Task C2 — Strategy config auto-population**

Tests (`backend/tests/bot_routers/test_bot_crud_speculative.py`):
- Creating a bot with `strategy_config={"ai_risk_preset": "speculative"}` server-side merges in all preset defaults, including `is_speculative=true` and exit discipline.
- Explicit user overrides win over preset defaults (e.g., user passes `stop_loss_percentage=-8`, that survives the merge).

Implementation: in `bot_crud_router.py` create/update paths, after validation, call `get_risk_preset_defaults` and merge preset defaults into `strategy_config` with user values taking precedence.

---

### Phase D — Frontend

**Task D1 — Account settings**

Tests (`frontend/src/components/settings/__tests__/AccountSettings.test.tsx`):
- Renders speculative allocation input with current value.
- Clamps input to [0, 100].
- Submits new value via existing account update endpoint.

Implementation: add field to `frontend/src/components/settings/AccountSettings.tsx` (or wherever rebalance fields currently live — locate via `grep -l rebalance_target_usd_pct`). Wire through to existing PATCH account endpoint.

**Task D2 — Bot form preset selector**

Tests (`frontend/src/pages/bots/components/BotFormModal.test.tsx`):
- Selecting "speculative" preset populates `strategy_config` with preset defaults.
- Warning banner renders when preset is selected.
- Save button is disabled until confirmation checkbox is checked.
- Save button is disabled with actionable copy when account's `speculative_allocation_pct == 0`.

Implementation: extend `RISK_PRESETS` frontend constant in `frontend/src/components/trading/AdvancedConditionBuilder.tsx` (and/or `PhaseConditionSelector.tsx` — remember the dual-builder lesson in memory `feedback_new_condition_wiring.md`). Extend `BotFormModal.tsx` with the warning + confirmation UX.

**Task D3 — Dashboard bucket card**

Tests (`frontend/src/pages/__tests__/DashboardSpeculativeBucket.test.tsx`):
- Card hidden when `speculative_allocation_pct == 0`.
- Card shows deployed/bucket progress bar when configured.
- Card shows separate speculative PnL.

Implementation: new component that consumes the bucket endpoint. Add to Dashboard render tree, behind the 2-second deferred query block used for non-critical widgets.

**Task D4 — AI log display**

Tests: existing `AIOpinionLog` display component renders `doubling_probability_score` and component breakdown when present.

Implementation: locate the AI log component (`frontend/src/components/...` — grep for `AIOpinionLogResponse`), add conditional rendering for the new field.

---

### Phase E — Polish

**Task E1 — CHANGELOG**: user-facing entry in Keep a Changelog format.

**Task E2 — Architecture docs**: run `architecture-sync` agent to update `docs/architecture/{backend,frontend,index}.json` with the new service, endpoint, migration, and UI surfaces.

**Task E3 — DOMAIN_KNOWLEDGE.md**: add a section on the speculative bucket semantics and cost-basis accounting rationale.

---

### Phase F — Calibration Alert Monitor

**Motivation**: The signal weights in `speculative_signals.py` are educated guesses until we have real outcomes to calibrate against. Rather than relying on the user to remember to check, a background monitor watches for "enough data accumulated + meaningful component divergence" and alerts the account owner by email + in-app toast. **The email must contain a self-sufficient re-engagement prompt** because by the time it fires (likely weeks or months later), the Claude session that originally shipped the preset will have long-since lost context.

**Task F1 — Account model: alert cooldown timestamp**

Add to `trading.accounts`:
```
speculative_calibration_last_alerted_at  TIMESTAMP NULL
```
Combine into migration `082_speculative_bucket.py` (single migration for all Phase A + F account columns). Idempotent add-column.

**Task F2 — Calibration analysis helper**

New function in `backend/app/services/speculative_bucket_service.py` (co-located — same domain):
```python
async def analyze_speculative_calibration(
    db: AsyncSession, user_id: int,
) -> dict | None:
    """Return an analysis dict if the user has enough data AND there is
    component-level divergence worth alerting on. Returns None otherwise.

    Shape:
    {
        "total_closed": 67,
        "wins": 9,
        "losses": 58,
        "overall_win_rate_pct": 13.4,
        "overall_realized_pnl_usd": -127.40,
        "components": [
            {"name": "volume_surge",          "fires": 52, "win_rate_pct": 19.2},
            {"name": "compression_breakout",  "fires": 41, "win_rate_pct": 17.1},
            ...
        ],
        "top_component": "volume_surge",
        "bottom_component": "correlation_break",
        "divergence_pp": 15.2,
    }
    """
```

Thresholds (all must hold to return a non-None analysis):
- ≥50 closed positions from speculative-tagged bots with non-null `doubling_probability_score` in `ai_opinion_log`
- At least one component with ≥30 fires
- `top_component.win_rate - bottom_component.win_rate >= 20.0` percentage points

Tests (`backend/tests/services/test_speculative_calibration.py`):
- Happy path: enough data + divergence → returns analysis dict with correct shape.
- Not enough data (40 positions) → returns None.
- Enough data but flat components (all within 5pp) → returns None.
- Ignores non-speculative bot positions.
- Multi-user isolation: user A's data never contaminates user B's analysis.

**Task F3 — Monitor background task**

New file: `backend/app/services/speculative_calibration_monitor.py`

Pattern: mirror `backend/app/services/prop_guard_monitor.py` (periodic async loop, one check per interval, per-user processing, started from `main.py` startup hook).

```python
CHECK_INTERVAL_SECONDS = 24 * 3600   # once per day
COOLDOWN_DAYS = 30                    # don't re-alert more often than this

async def run_speculative_calibration_monitor():
    """Periodic background task — loops forever."""
    while True:
        try:
            await _run_one_pass()
        except Exception:
            logger.exception("speculative_calibration_monitor pass failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)

async def _run_one_pass():
    """One pass: iterate users with speculative-tagged bots, check each."""
    # Find users who have at least one speculative-tagged bot
    # For each user:
    #   - Check cooldown via Account.speculative_calibration_last_alerted_at
    #   - Call analyze_speculative_calibration(db, user_id)
    #   - If analysis is non-None: send email + toast, update timestamp
```

Tests (`backend/tests/services/test_speculative_calibration_monitor.py`):
- Cooldown respected: user alerted 10 days ago is skipped; user alerted 40 days ago is re-checked.
- Users without speculative bots are skipped (no cost).
- Email send failure does not set the cooldown timestamp (so next pass retries).
- Toast broadcast failure does not set the cooldown timestamp.
- On success, both email + toast are sent and timestamp is updated.

Wire up in `backend/app/main.py` startup hook alongside the other monitors.

**Task F4 — Email template with self-sufficient re-engagement prompt**

New template: `backend/app/email_templates/speculative_calibration.html` (or wherever current templates live — locate via `grep -rln "speculative_preset\|TemplateResponse" backend/app/services/email_service.py`).

The email MUST include a copy-pasteable prompt block that a fresh Claude Code session can act on without any prior context. Use a fenced verbatim block the user can copy whole.

Email body (render with the analysis dict):

```
Subject: ZenithGrid — Time to review speculative preset weights

Hi {user_first_name},

Your speculative bot preset has accumulated enough closed positions that
it's worth revisiting the signal weights. The signal weights in
speculative_signals.py were educated guesses at ship time; this alert
fires once we have enough data to calibrate them against real outcomes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Total closed speculative positions:   {total_closed}
Overall win rate:                     {overall_win_rate_pct}%  ({wins}W / {losses}L)
Overall realized PnL:                 ${overall_realized_pnl_usd:+.2f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMPONENT PERFORMANCE (fires / win rate)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{for c in components (sorted by win_rate_pct desc):}
  {c.name:<24} {c.fires:>4} fires    {c.win_rate_pct:>5.1f}%
{endfor}

Gap between top ({top_component}) and bottom ({bottom_component}):
  {divergence_pp:.1f} percentage points

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TO ACT ON THIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Open a new Claude Code session at /home/ec2-user/ZenithGrid and
paste the block below. It is self-contained — Claude will have
no memory of the original preset design, but this prompt has
everything needed to recalibrate.

━━━━━ COPY EVERYTHING BELOW THIS LINE ━━━━━

I received a speculative preset calibration alert from ZenithGrid.
I want to review and adjust the signal weights in
`backend/app/indicators/speculative_signals.py` based on accumulated
outcome data in `ai_opinion_log`.

Reference: `PRPs/high-risk-doubling-preset.md` (Phase F — Calibration
Alert Monitor). The monitor fires when ≥50 closed speculative positions
have accumulated and component win rates diverge by ≥20 percentage
points.

Current snapshot from the alert:
- Total closed speculative positions: {total_closed}
- Overall win rate: {overall_win_rate_pct}%
- Top component: {top_component} ({top_win_rate_pct}% win rate)
- Bottom component: {bottom_component} ({bottom_win_rate_pct}% win rate)
- Divergence: {divergence_pp:.1f} percentage points

Please do this, in order:

1. Re-verify the numbers in the alert by querying `ai_opinion_log`
   joined to `trading.positions` for my user_id
   (user_id={user_id}), filtered to:
     - speculative-tagged bots (bot.strategy_config->>'is_speculative' = 'true')
     - closed positions (positions.status = 'closed')
     - non-null doubling_probability_score
   For each weight component in `speculative_signals.py::WEIGHTS`, compute
   fire_count (how often it contributed to the score) and win_rate
   (wins = position.profit_percentage > 0).

2. Propose weight adjustments to the `WEIGHTS` dict in
   `backend/app/indicators/speculative_signals.py`:
     - Lower weights of components whose win rate is materially below
       the overall win rate (>5pp below).
     - Raise weights of top performers (>5pp above overall win rate).
     - Preserve the invariant that weights sum to 100.
     - Do NOT change the scorer logic, the prefilter, or the LLM prompt
       — only the weights dict.

3. Show me a before/after weights diff and a one-line reason per change.

4. Add or update a test in
   `backend/tests/indicators/test_speculative_signals.py` that asserts
   the new weights sum to 100 and that at least one weight changed.

5. Write a CHANGELOG entry under the next patch version.

6. Stop after the weights change and tests pass — do not ship (no
   tag, no push, no deploy). I want to review before `/shipit`.

If the query shows the alert was noisy (no real divergence, or
sample size was lower than I claimed), say so and recommend
dismissing the alert instead of adjusting weights.

━━━━━ COPY EVERYTHING ABOVE THIS LINE ━━━━━

If you want to silence this alert without acting on it, reply to
this email with "dismiss" (or click: {dismiss_url}) — the cooldown
will reset to 30 days.

— ZenithGrid
```

Tests (`backend/tests/services/test_speculative_calibration_email.py`):
- Render with a full analysis dict produces a message containing "COPY EVERYTHING BELOW THIS LINE" and "COPY EVERYTHING ABOVE THIS LINE" (sanity: the copy-paste markers exist).
- Rendered email references the correct filename (`speculative_signals.py`) and the correct PRP path.
- Rendered email contains the specific numbers from the analysis dict (no template holes).
- Rendered email includes a valid `dismiss_url` signed with a short-lived token.

**Task F5 — Toast notification**

Broadcast via `WebSocketManager.broadcast(user_id, event)`. New event type:
```typescript
{ type: 'speculative_calibration_alert', payload: { total_closed, overall_win_rate_pct, divergence_pp, dismiss_url } }
```

Frontend (Phase D or deferred): `NotificationContext` adds a toast handler that renders a persistent (non-auto-dismiss) toast with a "Review in email" CTA. Reason for non-auto-dismiss: this is an action item, not a status update.

Tests: see the existing `NotificationContext` toast handler tests as a pattern.

**Task F6 — Dismiss endpoint**

`POST /api/accounts/{id}/speculative-calibration/dismiss` — authenticated; verifies the `dismiss_token` query param matches; sets `speculative_calibration_last_alerted_at = now` (extending the cooldown by another 30 days without actually sending an alert).

Tests: happy path dismisses; invalid/expired token 403; cross-user access 403.

**Phase F deliverables checklist**:
- [ ] Combined migration (082) includes both `speculative_allocation_pct` and `speculative_calibration_last_alerted_at`
- [ ] `analyze_speculative_calibration()` in `speculative_bucket_service.py`
- [ ] `speculative_calibration_monitor.py` periodic task
- [ ] Monitor wired into `main.py` startup
- [ ] Email template (HTML + plain-text) with copy-paste re-engagement prompt
- [ ] Toast broadcast on alert send
- [ ] Dismiss endpoint + token signing
- [ ] Tests for each unit

**Phase F depends on Phase B** (component breakdown must be stored in `ai_opinion_log` for the analysis to work). The monitor code can be written any time, but its `analyze_speculative_calibration()` query must match the Phase B log shape exactly.

---

## File-Level Plan

### Backend (new)
- `backend/migrations/082_speculative_bucket.py` (covers Phase A `speculative_allocation_pct` and Phase F `speculative_calibration_last_alerted_at`)
- `backend/app/services/speculative_bucket_service.py` (bucket math + `analyze_speculative_calibration()`)
- `backend/app/services/speculative_calibration_monitor.py` (Phase F periodic task)
- `backend/app/indicators/speculative_signals.py`
- `backend/app/email_templates/speculative_calibration.html` (+ plain-text if required by `email_service.py`)
- `backend/tests/services/test_speculative_bucket_service.py`
- `backend/tests/services/test_speculative_calibration.py` (analysis helper)
- `backend/tests/services/test_speculative_calibration_monitor.py` (Phase F monitor)
- `backend/tests/services/test_speculative_calibration_email.py` (Phase F email template)
- `backend/tests/indicators/test_speculative_signals.py`
- `backend/tests/indicators/test_ai_spot_opinion_catalyst.py`
- `backend/tests/indicators/test_risk_presets.py`
- `backend/tests/routers/test_speculative_bucket_router.py`
- `backend/tests/routers/test_speculative_calibration_dismiss.py`
- `backend/tests/migrations/test_082_speculative_bucket.py`
- `backend/tests/bot_routers/test_bot_crud_speculative.py`

### Backend (modified)
- `backend/app/models/trading.py` — add `speculative_allocation_pct` AND `speculative_calibration_last_alerted_at` to `Account`
- `backend/app/indicators/risk_presets.py` — add "speculative" entry
- `backend/app/indicators/ai_spot_opinion.py` — extend params, metrics, prefilter, prompt; persist component breakdown into `ai_opinion_log` (needed by Phase F analysis)
- `backend/app/strategies/indicator_based.py` — time-based max-hold exit in `should_sell`
- `backend/app/trading_engine/signal_processor/buy_decision.py` — preflight bucket check
- `backend/app/routers/accounts_query_router.py` — new bucket endpoint, calibration dismiss endpoint
- `backend/app/bot_routers/bot_crud_router.py` — merge preset defaults on create/update
- `backend/app/main.py` — start Phase F monitor in the startup hook
- `backend/app/services/email_service.py` — new send method for calibration alerts (or reuse existing with new template)
- `backend/tests/strategies/test_indicator_based.py` — add time-based exit tests
- `backend/tests/trading_engine/test_buy_decision.py` — add preflight tests (or new file)

### Frontend (new)
- `frontend/src/components/dashboard/SpeculativeBucketCard.tsx`
- `frontend/src/pages/__tests__/DashboardSpeculativeBucket.test.tsx`

### Frontend (modified)
- `frontend/src/components/settings/AccountSettings.tsx` (locate actual filename via grep)
- `frontend/src/pages/bots/components/BotFormModal.tsx`
- `frontend/src/components/trading/AdvancedConditionBuilder.tsx` — add `'speculative'` to `RiskPreset` union and `RISK_PRESETS` table
- `frontend/src/components/trading/PhaseConditionSelector.tsx` — same (dual-builder lesson)
- `frontend/src/types/index.ts` — add fields to `AIOpinionLogResponse` equivalents
- `frontend/src/services/api.ts` — add `getSpeculativeBucket(accountId)` helper
- Tests for each above

### Docs
- `CHANGELOG.md`
- `docs/architecture/{index,backend,frontend}.json` (via architecture-sync agent)
- `docs/DOMAIN_KNOWLEDGE.md`

---

## Validation Gates

All must pass before merge. Run as part of `/shipit`.

```bash
# Backend lint
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m flake8 --max-line-length=120 app/ tests/

# Backend tests — focused (per testing strategy in memory)
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m pytest -v \
    tests/services/test_speculative_bucket_service.py \
    tests/indicators/test_speculative_signals.py \
    tests/indicators/test_ai_spot_opinion_catalyst.py \
    tests/indicators/test_risk_presets.py \
    tests/routers/test_speculative_bucket_router.py \
    tests/migrations/test_082_speculative_bucket.py \
    tests/bot_routers/test_bot_crud_speculative.py \
    tests/strategies/test_indicator_based.py \
    tests/trading_engine/

# Migration smoke test (in a disposable DB)
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 update.py --yes

# Frontend type check
cd /home/ec2-user/ZenithGrid/frontend && npx tsc --noEmit

# Frontend tests — focused
cd /home/ec2-user/ZenithGrid/frontend && npx vitest run \
    src/components/settings \
    src/pages/bots/components/BotFormModal.test.tsx \
    src/pages/__tests__/DashboardSpeculativeBucket.test.tsx \
    src/components/trading
```

---

## Acceptance Criteria

### Functional
- User can set `speculative_allocation_pct` in Account Settings.
- User can create a speculative bot; preset defaults auto-populate; warning banner and confirmation required.
- Opening a new position on a speculative bot succeeds when the bucket has room; blocks with a clear reason when it does not.
- A 2x winner in the bucket does NOT increase headroom for new entries (cost-basis semantics).
- Multi-bot aggregation: 3 speculative bots on one account respect a single cap.
- Time-based max-hold exit fires at the configured horizon.
- Non-speculative bots are unaffected by all changes (regression guard).

### Performance
- Bucket info endpoint p95 under 100ms. Query pattern is a single join + aggregate over typically <20 open positions.
- Preflight bucket check adds <20ms to the entry path.
- No new polling intervals on the frontend — bucket card uses React Query with a 30-second stale time and pauses in hidden tabs.

### Safety
- Speculative bots on account A cannot affect bucket state of account B.
- No new auth surfaces required beyond existing `accessible_accounts_filter`.
- Cost-basis queries scope by `account_id` and `status='open'`.
- Zero bucket (default on existing accounts) explicitly blocks speculative bot entries; no silent zero-cap behavior.

### UX
- Dashboard card hidden when bucket is zero.
- Warning banner + confirmation checkbox present on bot creation with speculative preset.
- Copy honestly states historical low win rate.
- Separate speculative PnL visible on Dashboard so damage is isolated.

---

## Risks & Mitigations

### Risk 1 — AI signal quality too noisy to be useful
The LLM may generate mostly false positives even with the catalyst prompt, burning through the bucket on losers. Historical base rate for "2x in a day on a liquid coin" is single digits.

**Mitigation**:
- Ship with conservative defaults: `ai_confidence_threshold=70`, require `prefilter_volume_min_ratio=1.5`.
- Log every speculative call to `ai_opinion_log` with the new `doubling_probability_score` and component breakdown so we can recalibrate weights after enough outcomes accumulate.
- Default `base_order_size` small (1-2% of bucket) so a single failed bet costs ~0.2% of bucket.
- Expose the score breakdown in the UI so users can gut-check the AI.

### Risk 2 — Bucket cap circumvention via position sizing math error
If the preflight check uses `base_order_size` but the actual order ends up larger (fees, slippage, safety orders), the bucket could be exceeded.

**Mitigation**:
- Preset forces `max_safety_orders=0` — no dynamic position growth.
- `base_order_size` already accounts for fee buffer in `order_validation.py`.
- Add a post-fill audit: after each fill, re-check that `sum(position.total_quote_spent)` ≤ `bucket_usd`. Log a loud warning if violated (shouldn't happen, but catch it).
- Unit test: simulate maximum slippage and confirm the bucket cap holds.

### Risk 3 — Time-based exit triggers during off-hours with bad liquidity
A 24h max-hold exit could dump into thin book at 3am.

**Mitigation**:
- Time-based exit uses the bot's standard order type (market by default, but preset could force limit-at-mid).
- Add a param `speculative_max_hold_fallback_to_limit: bool` (default `True`) — first try a limit at mid, fall back to market after a short wait.
- Flag this in Open Questions for v2 tuning.

### Risk 4 — Dual-builder frontend drift (historical lesson)
Memory `feedback_new_condition_wiring.md` notes that condition types must be updated in BOTH `PhaseConditionSelector.tsx` AND `AdvancedConditionBuilder.tsx`.

**Mitigation**:
- Task D2 explicitly touches both files.
- Frontend review checklist item: grep for `RiskPreset` and ensure every consumer handles `'speculative'`.

### Risk 5 — Preset defaults conflict with existing bot
A user might edit an existing speculative bot and unknowingly flip off `is_speculative` by changing an unrelated config field.

**Mitigation**:
- `is_speculative` is stored as a flag in `strategy_config`. Make the UI render it read-only once set, only changeable by deleting and recreating the bot.
- Server-side: `bot_crud_router.py` update path preserves `is_speculative` unless the user explicitly changes the preset.

---

## Rollout Order

### Phase A — Infrastructure (backend, no UI)
Ship first: migration, Account model field, `speculative_bucket_service.py`, preflight hook. At this point the bucket exists but nothing consumes it yet — backend is safe.

### Phase B — Signals (backend, no UI)
Ship second: risk preset entry, signal scorer, AI catalyst mode, time-based exit. Now bots tagged as speculative get the right behavior, but users can only create them via API.

### Phase C — Strategy Wiring
Bot CRUD merges preset defaults; bucket endpoint is live. API-level complete.

### Phase D — UI
Account settings, bot form preset + warning + confirmation, Dashboard card, AI log display. Users can now use the feature end-to-end.

### Phase E — Docs + Polish
CHANGELOG, architecture-sync, DOMAIN_KNOWLEDGE. Ship as final commit before tag.

---

## Open Questions

1. **Should speculative bots participate in the Bot Budget Rebalancer?**
   Recommended answer: **no** for v1. The speculative bucket is its own allocation envelope; mixing with the broader rebalancer doubles the math complexity for marginal benefit. Exclude speculative-tagged bots from the rebalancer; note in rebalancer docs.

2. **Should Phase B order validation also block if the bucket is nearly full but not empty?**
   Recommended answer: warn in the UI at >80% bucket usage ("Almost full — new entries may be blocked"), but don't block. The preflight check already blocks when truly out of room.

3. **Should `doubling_probability_score` be tracked separately from `confidence` in `ai_opinion_log`?**
   Recommended answer: **yes**. Add a nullable column `doubling_probability_score INTEGER` in a follow-up migration. For v1, store it in the existing JSON context field to avoid a second migration; promote to a column once we have calibration data.

4. **What timeframe should the "time-based max hold" use — position open time or signal detection time?**
   Recommended answer: position open time (`position.opened_at`). Signal-to-open latency is small (seconds); using open time is simpler and aligns with how age is presented in the UI.

5. **Should the speculative preset default to market orders or limit orders for entries?**
   Recommended answer: **limit orders at current mid** with a 30-second timeout fallback to market. Catalysts move fast but chasing with market orders on thin books is the classic bag-holder mistake. Flag for v2 tuning after first outcomes.

6. **Should paper accounts enforce the bucket cap or allow unlimited for testing?**
   Recommended answer: **enforce** — the bucket math should behave identically in paper and live so users can calibrate. Users can set a high paper bucket % (e.g., 50%) if they want to stress-test.

---

## PRP Score

**7/10**

**Strengths**:
- Leverages three strong existing patterns: `risk_presets.py` (preset shape), `budget_calculator.py` (cross-bot account-scoped math), `AISpotOpinionEvaluator` (prompt + tool loop). Most of the code is mechanical extension, not greenfield.
- The bucket's cost-basis accounting is simple to reason about and testable.
- Design decisions (account-level bucket, cost basis, preset shape) are already user-confirmed.
- Exit discipline is mostly reuse of existing config keys, minimizing new code surface.
- Risks are localized: signal quality is the main uncertainty, and the damage from poor signal quality is bounded by the bucket.

**Weaknesses dragging the score**:
- Signal-quality tuning is inherently empirical. The weights in `speculative_signals.py` are educated guesses; real calibration needs real outcomes. Expect a v2 after 30-60 days of logs.
- "Micro/mid cap" heuristic is soft — we don't have on-chain market cap data, so the proxy (listing age + popularity rank) is approximate.
- The doubling probability score from the LLM is unvalidated until we have enough labeled data to compare against realized 2x outcomes.
- Frontend touches both condition-builder components; history shows this is easy to half-wire (per `feedback_new_condition_wiring.md`).

**What would raise the score to 9**:
- A labeled dataset of past 2x-in-24h moves to validate signal weights against before ship.
- An actual market-cap data source (not just listing age proxy).
- Backtesting harness for the speculative preset on historical candles.

Neither is a blocker for v1; the preset ships with conservative defaults and the bucket cap limits downside regardless of signal quality.
