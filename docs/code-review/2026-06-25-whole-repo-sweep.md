# Whole-repo code review sweep — 2026-06-25

Comprehensive sweep for **bugs, inconsistencies, performance** across backend + frontend
(8 parallel Sonnet reviewers). Status legend: `[ ]` open · `[x]` fixed · `~` deferred.
"✓verified" = re-confirmed against the source during the sweep; others are reviewer
findings not individually re-confirmed (high-confidence, verify before fixing).

This doc is the tracking list. Tier-1 + short-position items are being fixed first
(branch `fix/sweep-tier1-and-shorts`).

## 🔴 Tier 1 — real-money correctness & security  (fixed on `fix/sweep-tier1-and-shorts`)

- [x] **Dust-close writes wrong fields** — now writes persisted `sell_price` + BTC→USD-converted `profit_usd`. +2 tests. `sell_executor.py`
- [x] **Shorts: DCA price check skipped** — `_evaluate_dca_price_condition` now runs for any open position (it's direction-aware). `indicator_based.py`
- [x] **Shorts: exit P&L uses long fields** — `should_sell` now computes direction-correct profit from `short_total_sold_*`, guards div-by-zero, and inverts trailing TSL/TP for shorts. +5 short tests. `indicator_based.py`
- [x] **Grace SOs disabled for shorts** — `_shared.py` grace block now uses `entry_trades_for_position` (sells for shorts). `_shared.py`
- [x] **Bull-flag exit always throws** — uses `create_market_order(side="SELL")` and only closes on confirmed success. `bull_flag_processor.py`
- [x] **Limit re-price never works on Coinbase** — parses the batch `{results:[{success}]}` shape. `limit_order_monitor.py`
- [~] **ORM cascade vs FK RESTRICT** — **DEFERRED (not a clean fix).** `delete_bot` (`bot_crud_router.py:572`) uses ORM `db.delete(bot)` and *relies* on the cascade (ORM deletes children bottom-up, satisfying RESTRICT). Removing the cascade would break bot deletion. The real question is a delete-semantics policy decision: should deleting a bot erase its closed-position financial history? Needs a deliberate call, not a mechanical change. `models/trading.py`
- [x] **`AIBotLog.position_id is None`** — now `.is_(None)` (SQL IS NULL). `position_query_router.py`
- [x] **IDOR: `force_end_session`** — verifies the session belongs to the path `user_id` before ending. `admin_router.py`
- [x] **Cross-account credentials in `get_bot_stats`** — uses the bot's account-scoped exchange client. `bot_crud_router.py`
- [x] **Portfolio cache key collision** — persistent cache now namespaced (`acct_<id>` vs `user_<id>`) + in-memory keys namespaced; also added the missing **age-check** (rejects >120s-old entries). `cache.py`, `portfolio_service.py`
- [x] **Read pool missing `search_path`** — read pool now sets the same `search_path` as the write pool. `database.py`

## 🟠 Notable bugs

- [ ] Persistent portfolio cache **never age-checks** → serves stale after restart; also **sync file I/O under lock in async** (blocks loop). `backend/app/cache.py`
- [ ] `all_positions_exhausted_safety_orders` **undercounts cascades** (`buy_count-1` vs summing `dca_levels`) → premature new same-pair deal. `backend/app/trading_engine/position_manager.py`
- [ ] **`fixed_usd` missing from budget type checks** → `max_quote_allowed` = full balance (no per-deal cap). `position_manager.py:74`, `safety_order_calculator.py:102`
- [ ] Frontend candle fetch **no AbortController** (wrong pair's data overwrites). `useChartsData.ts:79`, `DealChart.tsx:158`
- [ ] `PositionCard` `getQueryData(['bots'])` **wrong key** (missing `accountId`) → toggles stale value. `PositionCard.tsx:112`
- [ ] `take_profit_percent` **typo** (→ `take_profit_percentage`) → blank label. `PositionCard.tsx:226`; `PriceBar.tsx:38` uses only `min_profit_percentage`.
- [ ] `botRebalancerApi` **no `r.ok` check** → parses error body as data. `botRebalancerApi.ts:32,38`
- [ ] react-query keys **missing `account_id`** (PerpsPortfolioPanel, transfer summary, dashboard) → stale data across accounts.
- [ ] `_close_sell_position_as_dust` clamped path over-books proceeds (related to dust fix above).
- [ ] `order_reconciliation_monitor` `fetch_limit` can exceed Coinbase 1000 cap → missed fills. `order_reconciliation_monitor.py:263`
- [ ] limit_order_monitor catches+logs and swallows `_process_order_completion`'s deliberate re-raise → fills unrecorded until next cycle. `limit_order_monitor.py:144`
- [ ] batch_analyzer per-product `except` swallows trade-exec errors without rollback; `process_bot_batch` outer `except` no `db.rollback()`. `batch_analyzer.py:434,525`
- [ ] pair_processor candle cache key excludes `lookback_candles` → indicator strategy gets 100 candles when 200 requested. `pair_processor.py:107,170`
- [ ] `float(... )` without `or 0` on possibly-null fill fields → TypeError on null. `limit_order_monitor.py:151-152,559-561`

## 🟡 Performance

- [ ] **Missing indexes** (also absent from ORM → fresh installs lack them): `OrderHistory.bot_id`, `AIOpinionLog.account_id`, `PendingOrder.bot_id`, `SpeculativeWeightsProposal.account_id`; compound indexes (`ai_opinion_log`, `order_history`, rate-limit) only in migrations. `models/trading.py`, `models/auth.py`
- [ ] **Unbounded full-history loads**: `get_generic_cex_portfolio` and `get_daily_activity` hydrate all closed positions in Python — aggregate in SQL (Coinbase path already does). `portfolio_service.py:459`, `account_snapshot_service.py:463`
- [ ] **`get_account_balances` 2nd full Coinbase breakdown** for `untracked_usd` (v3.10.0) — fetch once. `portfolio_service.py:668`
- [ ] Charts **recreate instance every poll tick** — init once, then `setData`. `AccountValueChart.tsx:199`, `DealChart.tsx`
- [ ] `_previous_market_context` module dict **never pruned** (unbounded). `_shared.py:80`
- [ ] Sync engine lacks `pool_pre_ping`/`pool_recycle`. `database.py:96`
- [ ] `Positions.tsx` handlers not `useCallback` → defeats `memo`. Card double-fetches bot already in props (`DealChart.tsx:90`).
- [ ] Batch budget calls sequential (could `gather`); semaphore allocated inside retry loop. `batch_analyzer.py:53,252`
- [ ] Unbounded loops in `get_transfer_summary` and `copy_bot_to_account` name-collision. `transfers_router.py:234`, `bot_crud_router.py:736`
- [ ] `batch_price` query re-keyed by new array ref each render. `usePositionsData.ts:70`

## ⚪ Low / cleanup

- [ ] Migration number collisions: `077_*` ×2, `086_*` ×2. `backend/migrations/`
- [ ] ORM/migration FK `ondelete` divergence on fresh installs: `AIOpinionLog.user_id` (CASCADE in migration, none in model), `BotRebalancerGroup.account_id` (same); `Position.signals` cascade vs SET NULL. `models/trading.py`
- [ ] Dead query in `create_or_update_cex_account` (line 458). `exchange_service.py`
- [ ] `dca_target_reference` type `"string"` vs `"str"`. `indicator_params.py:89`
- [ ] Routine budget lines logged at `warning`. `batch_analyzer.py:95,103`
- [ ] Account enumeration via 403-vs-404. `blacklist_router.py:414`
- [ ] Webhook rate-limit per-token only (enumerable across IPs). `webhook_router.py:46`
- [ ] Misleading BTC-fee comment. `fill_reconciler.py:104`
- [ ] `manual_max_dca_orders` percentage-mode base-size back-calc overstates (volume-scaled). `indicator_based.py:1016`
- [ ] Broad react-query invalidations (`['positions']` prefix hits other accounts). `useBotMutations.ts`, etc.
- [ ] `VirtualizedPositionList` `scrollMargin` reads ref before mount → 0. `VirtualizedPositionList.tsx:37`
- [ ] `syncAllChartsToRange` 3-param interface vs 2-param impl (silent ignored arg). `useIndicators.ts` / `useChartManagement.ts`

## Likely false positive (not fixing)
- `is_paper` "used before assignment" in `_post_sell_operations`/close-short — Python doesn't block-scope and the assignment is the first statement in the `try`; defined before any await that could fail. Not a real bug.
