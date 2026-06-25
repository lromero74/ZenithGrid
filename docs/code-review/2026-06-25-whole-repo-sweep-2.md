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

- [ ] **Candle cache pruned every cycle (cache defeated)** — `multi_bot_monitor.py:1132` uses `k.rsplit(":",1)[0]` on keys shaped `product:granularity:lookback`, yielding `product:granularity`, which never matches the bare product in `all_active_pairs` → every entry evicted each cycle → fresh Coinbase fetch per pair per tick (API-rate + latency). Fix: `k.split(":",1)[0]`.
- [ ] **Limit-close `profit_usd` only set for BTC pairs** — `limit_order_monitor.py:628` skips `profit_usd` for USD/USDC pairs, so limit-closes on those pairs are invisible to win-rate (`bot_stats_service` counts `profit_usd is not None and >0`). Fix: `else: profit_usd = profit_quote` (mirror `sell_executor`).
- [ ] **Portfolio unrealized P&L wrong for shorts + excludes USDC** — `portfolio_calculations._compute_position_pnl` uses long-only fields for all directions (shorts show $0) and drops USDC-quoted positions (`else: current_price=None`). Fix: direction-aware (mirror `pnl_service.calculate_profit`) + handle USDC like USD.
- [ ] **`_validate_market_fallback` divide-by-zero** — `sell_executor.py:216` (and `sell_decision.py:113`) divide by `total_quote_spent` with no guard → `ZeroDivisionError` aborts the sell-decision path. Fix: guard `if spent>0 else 0.0`.
- [ ] **Short positions always use the 0.6% fallback fee** — `pnl_service.position_exit_fee_rate` keys off `total_quote_spent` (0 for shorts) → always returns `DEFAULT_TAKER_FEE_RATE`, shifting the fee-adjusted TP floor wrong for every short. Fix: fall back to `short_total_sold_quote` denominator for shorts.
- [ ] **Account purge leaves bot reserved balances non-zero** — `account_purge.purge_account_history` deletes positions/trades but never zeroes `bot.reserved_btc_balance`/`reserved_usd_balance`, so post-purge bots think capital is deployed and refuse new positions. Fix: zero reserves for the account's bots in the same transaction.
- [ ] **`time.sleep()` on the event loop** — `article_content_service.py:288` blocks the loop for the crawl-delay inside an `async def`. Fix: `await asyncio.sleep(...)`.
- [ ] **Batch-analyzer semaphore allocated inside the retry loop** — `batch_analyzer.py:254` builds a new `Semaphore` per attempt per pair → no real concurrency bound. Fix: hoist allocation above the loops.
- [ ] **Manual-mode DCA base-order back-calc breaks with volume scaling** — `indicator_based.py:1019` (`total_quote_spent/(1+count)`) and the cascade count passed at `:952` mis-size SO #2+ when `safety_order_volume_scale≠1`. Fix: derive base size from the first entry trade, not total/count. (Verify carefully before changing real-money sizing.)

## 🟡 Tier 3 — performance

- [ ] Chart instance recreated on every poll tick — `AccountValueChart.tsx:199` (`history` in init effect deps). Init once, then `setData`.
- [ ] Missing AbortController/stale-guard — `DealChart.tsx:158`, `LightweightChartModal/hooks/useChartData.ts` (stale pair response can overwrite).
- [ ] `account_snapshot_service.get_daily_activity` hydrates all closed positions in Python — aggregate in SQL.
- [ ] `transfers_router.get_transfer_summary` full-table hydration, no limit/window — SQL aggregate.
- [ ] `batch_analyzer._calculate_batch_budget` two independent sequential awaits — `asyncio.gather`.
- [ ] `usePositionsData.ts:70` batch-price query key not sorted → refetch on reorder.
- [ ] Bull-flag TTP trailing deviation hardcoded 1% — `indicator_based.py:1146` ignores `trailing_deviation` config.

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
