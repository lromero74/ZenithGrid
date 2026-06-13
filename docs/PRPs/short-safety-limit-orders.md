# PRP: Limit Orders for Short Safety Orders (DCA adds)

**Branch:** `feature/short-safety-limit-orders`
**Status:** Ready for execution (via `/execute-prp short-safety-limit-orders`)
**Author:** research pass 2026-06-12

---

## Context & Goal

### Problem
When a **short** bot is configured with `dca_execution_type == "limit"`, its safety
orders (DCA adds) should be placed as **limit SELL** orders that **add to the short**
when they fill. Today they don't:

- `backend/app/trading_engine/sell_executor.py` (`execute_sell_short`, ~lines 600-605)
  has a `TODO` and **falls back to a market order** with a warning
  (`"Limit short safety orders not yet implemented - using market order"`).
- A prior naive attempt called `execute_limit_sell` — the **CLOSE** path — which sets
  `position.closing_via_limit = True` + `position.limit_close_order_id`. The close
  monitor (`limit_order_monitor.check_all_pending_limit_orders` →
  `_process_order_completion`) then **marks the position `closed` and books P&L on
  fill**. That is catastrophically wrong for an *add*: the short is growing, not
  exiting. (This is why the naive patch was rejected — see git history / session notes.)

### Who benefits
Internal correctness + users running **short / bidirectional** bots with limit DCA.
Long-only users are unaffected by the bug today, but see the **shared-reconciler**
finding below — fixing this also closes a latent gap on the long side.

### How leading platforms handle it
Limit DCA = "maker" safety orders: place a resting limit order at/through the desired
level, let the book come to you (lower fees, controlled entry), and only mutate the
position when the order actually fills (including partials). The position lifecycle
(open → add → … → close) is driven by **fills**, never by order *placement*.

---

## ⚠️ Critical Finding (shapes the whole design)

**There is no automated path that applies a filled *safety* limit order back to the
position as an add — on either side.**

Traced during research:
- The correct placement template is the long side: `buy_executor.py:478` →
  `execute_limit_buy` (`buy_executor.py:553`) places the order and records a
  **`PendingOrder`** (`side="BUY"`, `trade_type="safety_order_N"`, `status="pending"`)
  and **does NOT** touch `closing_via_limit`. The caller then `return None` — the
  position is **not** mutated at placement time. Good. ✅
- BUT the only monitors that run on a schedule (`backend/app/main.py`) are:
  - `check_all_pending_limit_orders` (`limit_order_monitor.py:33`) — queries **only**
    `Position.closing_via_limit.is_(True)`. It does **not** look at safety
    `PendingOrder` rows. (CLOSE path only.)
  - `OrderReconciliationMonitor.check_for_missing_orders` — **detects & alerts only**.
    It literally logs *"STUCK PENDING ORDERS: filled on exchange but stuck with
    status='pending' … no auto-fix available"* (`order_reconciliation_monitor.py:372`).
- `trading_engine_v2.py` only has thin `execute_limit_buy/sell` wrappers.
- `auto_buy_monitor.py` is a separate "auto-buy the dip" feature (in-memory
  `AutoBuyPendingOrder`), not DCA safety reconciliation.

**Conclusion:** long limit-DCA safety orders are placed but (apparently) never
auto-applied — they'd surface as "STUCK PENDING ORDERS". So this feature must
**build the safety-limit fill→add reconciler**, and it should handle **both**
`BUY` (long add) and `SELL` (short add). This is the core of the work, not a footnote.

**FIRST STEP OF EXECUTION — confirm the gap (don't trust this doc blindly):**
```bash
# On prod (fedora) — are there pending safety PendingOrders that filled but never applied?
ssh fedora.local "distrobox enter postgres-box -- /usr/pgsql-15/bin/psql -h /tmp -U louis -d zenithgrid -c \
  \"SELECT side, trade_type, status, COUNT(*) FROM trading.pending_orders \
    WHERE trade_type LIKE 'safety_order%' GROUP BY side, trade_type, status ORDER BY 1,2,3;\""
```
Also `grep -rn "trade_type" backend/app/services/grid_trading_service.py` and re-scan
for any reconciler that increments `total_base_acquired` from a `PendingOrder`. If a
reconciler *does* exist that this research missed, mirror it for SELL instead of
building new. **If none exists, build the shared reconciler as specified below.**

---

## Domain notes (see `docs/DOMAIN_KNOWLEDGE.md`)

- **Short position lifecycle:** OPEN = SELL high; ADD (safety) = SELL more (at a worse
  price, raising the average short entry); CLOSE / take-profit = **BUY back** lower.
  So for a short: safety orders are **SELL**s, the close is a **BUY**.
- A fill that ADDs to a short must increase `total_base_acquired` and
  `total_quote_received`/cost-basis fields **for the short's accounting** and recompute
  the average entry — and must **never** set `status="closed"` or compute realized P&L.
- `closing_via_limit` / `limit_close_order_id` are **CLOSE-only** state. The add path
  must use the `PendingOrder` table exclusively (like `execute_limit_buy`).

---

## Implementation Blueprint

### Layer 1 — Placement: `execute_limit_sell_safety` (sell_executor.py)
Mirror `execute_limit_buy` exactly, but for the SELL/short-add side. Do **NOT** reuse
`execute_limit_sell` (close path).

Replace the TODO block in `execute_sell_short` (~600-605):
```python
if is_safety_order and dca_execution_type == "limit":
    limit_price = current_price
    await execute_limit_sell_safety(            # NEW — mirrors execute_limit_buy
        db=db, exchange=exchange, trading_client=trading_client, bot=bot,
        product_id=product_id, position=position,
        base_amount=base_amount, limit_price=limit_price,
        trade_type=trade_type, signal_data=signal_data,
    )
    return None      # position mutated later, on fill, by the reconciler
```

`execute_limit_sell_safety(...)` (new fn in `sell_executor.py`):
- Place a limit SELL via `trading_client.sell_limit(product_id, limit_price, base_amount)`
  (verify the client method name — long side uses `buy_limit`; confirm the sell analog).
- Create a `PendingOrder(side="SELL", order_type="LIMIT", trade_type="safety_order_N",
  status="pending", position_id, bot_id, order_id, product_id, limit_price,
  base_amount, quote_amount, created_at)`. **Do not** touch `closing_via_limit`.
- Return the `PendingOrder`. Handle PropGuard block + missing order_id like
  `execute_limit_buy`.

### Layer 2 — Reconciler: apply filled safety limit orders as ADDs (shared BUY+SELL)
This is the missing piece. Add a scheduled reconciliation that:
1. Selects `PendingOrder` where `status IN ("pending","partially_filled")` and
   `trade_type LIKE "safety_order%"` (these are *adds*, not closes), joined to an
   **open** position.
2. Fetches order status from the exchange (`exchange.get_order(order_id)`), grouped per
   account (reuse the per-account client grouping pattern from
   `check_all_pending_limit_orders`).
3. On **partial/full fill** (new fill since `filled_base_amount`):
   - Create a `Trade(side=<"buy"|"sell" per PendingOrder.side>,
     trade_type=pending.trade_type, order_id, base/quote/price, timestamp)`.
   - Apply the add to the position via the **same** accounting helper the market
     safety path uses (study `buy_executor.py:165-168`:
     `position.total_base_acquired += base; average_buy_price = total_quote_spent /
     total_base_acquired`). For SELL/short adds, increment the short's
     base/quote-received + recompute average **short** entry (mirror how
     `execute_sell_short`'s *market* safety path updates the position — find and reuse
     it; do NOT invent new math).
   - Update `PendingOrder.filled_base_amount/filled_quote_amount/filled_price/fills/
     remaining_base_amount`; set `status="partially_filled"` or `"filled"` + `filled_at`.
   - **Never** set `position.status="closed"` and never compute realized P&L here.
4. On CANCELLED/EXPIRED/FAILED: mark `PendingOrder.status` accordingly, release any
   reserved amounts, leave the position open and unmodified.
5. **Idempotency:** key off `filled_base_amount` deltas (like
   `_process_partial_fills`) and the unique `order_id` so re-runs never double-apply.
   A `Trade` must not be created twice for the same fill delta.

**Design decision (call out in PR):** implement the reconciler as a **shared** routine
that dispatches on `PendingOrder.side` so it fixes long (BUY add) and short (SELL add)
with one code path. Wire it into the `main.py` monitor loop next to
`check_all_pending_limit_orders` (same cadence, same per-account client resolution).

### Layer 3 — interactions / edge cases
- **Short take-profit:** TP for a short is a BUY-back via the close path. Ensure an
  *open* safety SELL limit doesn't block TP evaluation, and that TP/close logic ignores
  `safety_order%` PendingOrders (only `closing_via_limit` drives closes). Verify
  `sell_decision.py` / `_shared.py:239` close-skip guards still behave.
- **Partial fills:** support cumulative partials (mirror `_process_partial_fills`).
- **Cancel/replace/bid-fallback:** decide whether short safety limits get the same
  stale-order reprice/fallback as closes (`_check_bid_fallback`,
  `_cancel_and_replace_order`). MVP: no auto-reprice for safety adds (leave resting);
  document the choice. If added, reuse the close path's helpers generalized by side.
- **Paper trading:** `paper_trading_client` must support `sell_limit` + order status
  polling so the reconciler works in paper mode (the close monitor already special-cases
  `paper-` order ids at `limit_order_monitor.py:101` — mirror that).
- **Min-order validation:** run the same min-size validation the market short safety
  path uses before placing.

### Files to create / modify
| File | Change |
|---|---|
| `backend/app/trading_engine/sell_executor.py` | add `execute_limit_sell_safety`; replace the TODO market fallback in `execute_sell_short` |
| `backend/app/services/limit_order_monitor.py` (or new `safety_order_monitor.py`) | add the shared safety-limit fill→add reconciler (BUY+SELL) |
| `backend/app/main.py` | wire the reconciler into the scheduled monitor loop |
| `backend/app/trading_engine/buy_executor.py` | (if reconciler is shared) ensure long limit safety adds now route through it; remove/realign any dead assumptions |
| `backend/tests/trading_engine/test_sell_executor.py` | placement tests |
| `backend/tests/services/test_*safety*_monitor*.py` (new) | reconciler tests (BUY add, SELL add, partial, cancel, idempotency, never-close) |
| `CHANGELOG.md`, `docs/architecture/backend.json`, `docs/architecture/index.json` | release docs |

No DB schema change expected (reuses `PendingOrder`). **If** a new column proves
necessary (e.g. an explicit `intent="add"` discriminator instead of `trade_type LIKE
'safety_order%'`), add a migration + update `setup.py` and `database.py`, back up the
DB first, and keep it idempotent.

---

## TDD Test Plan (write FIRST, watch fail)

**Placement (`test_sell_executor.py`):**
1. Happy: short bot, `dca_execution_type="limit"`, safety order → calls
   `execute_limit_sell_safety`, creates a `PendingOrder(side="SELL",
   trade_type="safety_order_*", status="pending")`, and **does NOT** set
   `position.closing_via_limit` / `limit_close_order_id`; position not mutated.
2. Edge: `dca_execution_type="market"` (or unset) → still uses the market path (no regression).
3. Failure: exchange returns no order_id / PropGuard block → raises, no PendingOrder leaks.

**Reconciler (new test file):**
4. Happy SELL add: pending SELL safety order reports FILLED → position
   `total_base_acquired` grows, average **short** entry recomputed, a `sell` Trade
   recorded, `PendingOrder.status="filled"`, **`position.status` stays `"open"`**, no P&L booked.
5. Happy BUY add (long regression-fix): pending BUY safety order FILLED → long add applied.
6. Edge partial: partial fill then full → exactly one Trade per new delta; cumulative fields correct.
7. Failure/cancel: CANCELLED/EXPIRED → PendingOrder marked, position untouched, reserves released.
8. Idempotency: running the reconciler twice over the same fill does **not** double-apply.
9. Guard: a `closing_via_limit` close order is **not** processed by the safety reconciler (and vice-versa).

Mock the exchange/trading client (no real API). Use `pytest.approx` for floats,
`asyncio.run` patterns per existing tests, UTC timestamps via `app.utils.timeutil`.

---

## Validation Gates
```bash
cd backend
./venv/bin/python3 -m flake8 --max-line-length=120 \
  app/trading_engine/sell_executor.py app/services/limit_order_monitor.py app/main.py \
  app/trading_engine/buy_executor.py tests/trading_engine/test_sell_executor.py
./venv/bin/python3 -c "from app.trading_engine.sell_executor import execute_limit_sell_safety"
./venv/bin/python3 -m pytest tests/trading_engine/test_sell_executor.py tests/services/ -q
# Full suite must be green, zero warnings:
./venv/bin/python3 -m pytest tests/ -p no:cacheprovider -q
```
Then `multiuser-security` agent (touches order/position/account paths) and
`regression-check` before `/shipit`.

---

## Commercialization Check
- [x] Works for multiple users — reconciler is per-account-scoped (reuse the
      `get_exchange_client_for_account` grouping; respect Critical Rule #12).
- [x] Credentials secure — uses existing account-scoped exchange clients.
- [x] Would users pay — limit DCA (maker fees, controlled adds) is a premium DCA feature
      and correct short support is table-stakes vs. 3Commas et al.

## Rollback Plan
- Pure code (no schema): `git revert` the merge / reset the branch. The TODO + market
  fallback is the safe pre-state — short safety orders simply execute as market again.
- If a migration was added: `cp backend/trading.db backend/trading.db.bak.$(date +%s)`
  before migrating; rollback = restore the backup + revert code. (Prod is Postgres —
  back up via `pg_dump` first.)
- Deploy is backend → `systemctl --user restart zenithgrid` on fedora; revert = redeploy
  prior tag.

## Risks
- **Biggest:** building the reconciler means touching the live fill→position path for
  BOTH directions. A bug here mis-sizes real positions. Mitigate with the exhaustive
  TDD matrix above (esp. idempotency + never-close) and `multiuser-security` +
  `regression-check` before shipping. Consider shipping behind the existing
  `dca_execution_type` config (only limit-mode bots exercise it) and validating on a
  paper account first.
- Confirm `trading_client.sell_limit` exists and matches `buy_limit` semantics.
- Confirm short-add position accounting helper exists (reuse, don't reinvent).

## Quality Score
**7/10** for one-pass success. Placement layer is well-templated (8-9). The reconciler
is the unknown: this research shows it likely must be **built** (not just mirrored), and
the exact short-add accounting helper + `sell_limit` client semantics need confirmation
at the top of execution (first 30 min). The "FIRST STEP" prod check + targeted reuse of
the market short-safety accounting will close the gap; once confirmed, the path is clear.
