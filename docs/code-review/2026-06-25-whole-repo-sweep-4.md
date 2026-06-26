# Whole-repo code review sweep #4 — 2026-06-25

Fourth sweep (5 parallel Sonnet reviewers) after v3.13.3, each told to read sweep #3
first and hunt only *new* issues. Every item was **re-verified against current source**
by the orchestrator before action (a few agent severity labels were corrected).

Context shift from prior sweeps: **paper bot 45 "Short Test (Bidirectional)" is now
active**, so the short-path items are no longer purely latent — they are what the
short-path shakedown will exercise. Status: `[ ]` open · `[x]` fixed · `~` deferred.

## 🟢 Batch 1 — correctness (shipped v3.13.4)

- [x] **A** `GridVisualizer.tsx:53` — `priceRange = upper - lower` could be 0 → `Infinity`/`NaN` into a CSS `bottom:` style. Guarded with `|| 1`. +2 vitest tests.
- [x] **B** `TradingViewChartModal.tsx:5-16` — local copies of `getFeeAdjustedProfitMultiplier`/`getTakeProfitPercent` ignored the exchange (always Coinbase 0.6%) → wrong target line for ByBit/MT5. Removed the duplicates, imported the authoritative `positionUtils` versions, pass `exchange` + a `bot_config` shim (rule 13). Covered by existing `positionUtils.test.ts`.
- [x] **D** `sell_decision.py:111` — limit-TP mark-profit gate used the long formula (→ 0 for shorts) → permanently blocked closing a short via limit TP. Now direction-aware. +3 tests.
- [x] **E** `indicator_based.py:133` — short DCA reference price fell back to `average_buy_price` (0 for shorts) → SO triggers collapsed to 0. Now falls back to the first short entry price. +4 tests.
- [x] **F+G** `batch_analyzer.py:89` (bot-level) and `_shared.py:344` (pair-level SQL) summed only `total_quote_spent` → understated a short's deployed capital → budget over-allocation. Consolidated the direction-aware "deployed quote" into one source of truth `trading_engine/position_quote.deployed_quote` (rule 13); the SQL aggregate mirrors it with a CASE. +7 tests (incl. SQL/Python parity).
- [x] **H** `buy_executor.py:1026-1062` — close-short reconcile + position-close commit happened *after* the in-flight shutdown barrier was released (a shutdown mid-reconcile would strand the short open), and there was no zero-fill guard. Both calls moved inside the barrier; added a zero/unconfirmed-fill guard. +1 test.

## 🟠 Batch 2 — deferred (next tier)

- [ ] **C** `perps_router.py:179,278` — `modify_tp_sl` + `close_perps_position` read the position via `manager_account_ids` but place/cancel/close orders against the **caller's** broker, not `position.account_id`'s (the wrong-broker class fixed in v2.166.5 elsewhere; perps was missed). Fix: build the exchange client from `position.account_id`.
- [ ] **K** `account_snapshot_service.py:74,160` — two `except Exception: pass` silently swallow BTC price-fetch failures (snapshots write NULL, broken API key unnoticed). Add a debug log.
- [ ] **L** `portfolio_service.py:302,375` — hardcoded `$95,000`/`$3,500` fallback prices → misleading valuations. Use last-known cache or 0/None.
- [ ] **M** `season_detector.get_current_season` — 3 sequential uncached external API calls (fresh session each) per bot-start/poll; dups `market_metrics_service`. `asyncio.gather` + reuse cache.
- [ ] **N** `goal_snapshot_service` — N+1 SELECT per goal; pre-fetch in one `IN` query.
- [ ] **O** quick wins — shared `BUY_FEE_RESERVE=0.99` constant (3 copies), module-level `import time` (prop_guard/dex_client), `_VOL_LOOKBACK_SECONDS`.
- [ ] **P** `grid_trading_service.check_and_run_rotation` — dead re-export shim; remove.

## ⚪ Verified NOT bugs (dismissed)

- `get_next_user_deal_number`/`get_next_user_attempt_number` scoped to `user_id` — the
  columns are named `user_*`; per-user global numbering is **by design**, not a leak.
- `indicator_based.py` `not hasattr(trailing_tp_active)` dead guard — harmless (the
  `is None` line below covers it); not worth churn.
- `rebalancer PUT` / `automation rules` manager-vs-owner asymmetry — more restrictive,
  not a leak; UX nit only.
