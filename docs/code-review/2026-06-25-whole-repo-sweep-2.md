# Whole-repo code review sweep #2 — 2026-06-25

Second comprehensive sweep (6 parallel Sonnet reviewers: security, hygiene, trading
engine, services/monitors, perf/async/DB, frontend) after v3.11.6. Every item below
was **re-verified against current source** by the orchestrator before listing.
Status: `[ ]` open · `[x]` fixed · `~` deferred.

## 🔴 Tier 1 — real-money correctness & security

- [x] **Close-short fill has no terminal-status gate** — `_reconcile_close_short_fill` now gates on `_TERMINAL_ORDER_STATUSES` (shared with the v3.11.6 buy/sell reconciler), waits through partials, and still raises on exhaustion. +4 tests. `buy_executor.py`
- [x] **Clamped dust-close over-books proceeds** — `_close_sell_position_as_dust` now takes `available_base`; the clamped caller passes the clamped wallet balance so proceeds are booked on what's actually held, not the recorded total. Round-to-zero caller unchanged. +2 tests. `sell_executor.py`
- [x] **Backtesting builds exchange client from an unverified account_id** — a caller-supplied `account_id` is now verified to belong to `current_user` (404 if not) before any exchange client is built. +2 tests. `backtesting_router.py`

## 🟠 Tier 2 — bugs (correctness / stats)

- [x] **Candle cache pruned every cycle (cache defeated)** — prune now extracts the product with `k.split(":",1)[0]` (was `rsplit`, which left `product:granularity` and matched nothing → full eviction every cycle → a fresh Coinbase fetch per pair per tick). `multi_bot_monitor.py`
- [x] **Limit-close `profit_usd` only set for BTC pairs** — USD/USDC limit-closes now set `profit_usd = profit_quote`, so they count toward win-rate. +1 test. `limit_order_monitor.py`
- [x] **Portfolio unrealized P&L wrong for shorts + excludes USDC** — `_compute_position_pnl` now uses the direction-aware `calculate_profit` (shorts use their own cost basis) and treats USDC like USD. +3 tests. (Also retires the dead `calculate_profit` duplication for this caller.) `portfolio_calculations.py`
- [x] **`_validate_market_fallback` / sell_decision divide-by-zero** — both now guard `total_quote_spent > 0`. `sell_executor.py`, `signal_processor/sell_decision.py`
- [x] **Short positions always used the 0.6% fallback fee** — `position_exit_fee_rate` falls back to `short_total_sold_quote` when `total_quote_spent` is 0. +1 test. `pnl_service.py`
- [x] **Account purge leaves bot reserved balances non-zero** — purge now zeroes the account's bots' `reserved_btc_balance`/`reserved_usd_balance` in the same transaction. +1 test. `account_purge.py`
- [x] **`time.sleep()` on the event loop** — article-fetch crawl delay now computes the wait under the lock and `await asyncio.sleep`s outside it (reserving the slot so concurrent same-domain fetches serialize). `article_content_service.py`
- [~] **Batch-analyzer semaphore allocated inside the retry loop** — NOT a bug. The semaphore is created fresh per attempt but correctly bounds the 7-timeframe `gather` within that attempt, and attempts/pairs are sequential, so there's no cross-attempt/pair concurrency to bound. Left as-is (optional micro-cleanup only). `batch_analyzer.py`
- [x] **Manual-mode DCA base-order back-calc breaks with volume scaling** — `_calculate_safety_order_amount` now derives the base-order size from the position's earliest entry trade (`_manual_base_order_size`) instead of `total_quote_spent/(1+count)`, which mis-sized `percentage_of_base` SOs under volume scaling (and worsened mid-cascade as the count grew). Robust fallback to the old average when no usable entry trade exists (test mocks), so existing behavior is unchanged there; also neutralizes the cascade-count inflation at `:952`. +3 tests (correct scaled size, count-independence, fallback). `indicator_based.py`

## 🟡 Tier 3 — performance

- [x] Missing AbortController/stale-guard — added to `DealChart.tsx` candle fetch and `LightweightChartModal/hooks/useChartData.ts` (cancelled guard + abort on cleanup, ignore canceled errors). A slow response for a previously-selected pair can no longer overwrite the current chart.
- [x] `transfers_router.get_transfer_summary` now aggregates in SQL (sum + count grouped by `transfer_type`) instead of hydrating every transfer row.
- [x] `batch_analyzer._calculate_batch_budget` now `asyncio.gather`s the two independent exchange calls (aggregate value + available balance), preserving each fallback.
- [x] `usePositionsData.ts` batch-price products are now `.sort()`ed so the query key is stable under position reordering (no needless refetch).
- [x] Bull-flag/pattern TTP now uses the configured `trailing_deviation` (was hardcoded 1%, ignoring the bot's setting; default still 1%). `indicator_based.py`
- [x] Chart instance recreated on every poll tick — `AccountValueChart.tsx`. Untangled into (a) a pure `buildAccountValueSeries` helper (split/total value selection + live-point append — now single-source and unit-tested), (b) an **init** effect keyed on container-readiness + `chartMode` that creates the chart/series once (rebuilds only on mode/range change, not on 5-min refetch or live-value ticks), and (c) a **data** effect that `setData`s in place and only re-fits the time-scale on a real data-shape change (so a live tick no longer resets zoom). Guarded by `accountValueChartData.test.ts` (8) + `AccountValueChart.test.tsx` (2: create-once, update-without-recreate). Also fixed two pre-existing frontend tests that sweep #1's AbortController/this change touched.
- [x] `account_snapshot_service.get_daily_activity` now aggregates in SQL (GROUP BY date/line/category with SUM+COUNT) instead of hydrating every closed position and transfer into Python. Date truncation uses `substr(cast(ts AS str), 1, 10)` — "YYYY-MM-DD" on both SQLite and Postgres (no dialect-specific date fn); line/category/amount/filters use dialect-safe `CASE`/`LIKE`/`upper`/`abs`/`coalesce`. All 13 existing equivalence tests pass unchanged + 2 new (cardspend→USD line, micro-transfer skip).

## ⚪ Tier 4 — cleanup

- [ ] Dead code: `pnl_service.calculate_profit` unused while 3 callers inline the same formula; `main.py:73-74` unused monitor imports; `bot_crud_router.py:851` `except as _`; `PerpsPortfolioPanel.tsx` dead component (unscoped query keys).
- [ ] AI provider `billing_url` list duplicated in `ai_credentials_router` + `system_router` — extract shared constant.
- [ ] Oversized files: `sell_executor.py` (1687), `rebalance_monitor.py` (1309), `indicator_based.py` (1248), `buy_executor.py` (1086) — split.
- [ ] Broad/ unscoped react-query keys: `useBotMutations` `invalidate(['positions'])` prefix; `PositionCard` `getQueryData(['bots'])`; `App.tsx` closed-positions badge.
- [ ] `syncAllChartsToRange` type declares 3 params, impl takes 2 (`useIndicators.ts` vs `useChartManagement.ts`).
- [ ] Silent `except Exception` without logging — `portfolio_service.py:299,372`, `rebalance_monitor.py:1186`.
- [ ] `system_router` `/api/trades` + `/api/signals` scoped to owned-only (not shared accounts) — managers see incomplete view; `get_coinbase` dep uses shared accounts.
- [ ] Webhook rate limit per-token only (`webhook_router.py:46`).
- [ ] `_article_fetch_counts` dict grows unbounded across user_ids (`article_content_service.py`).
- [ ] Quarterly report prior-period boundary wrong for non-Jan quarter starts (`report_scheduler._compute_full_prior_bounds`).
