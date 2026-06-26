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

## 🟠 Notable bugs  (in progress on `fix/sweep-tier2-notable`)

- [x] Persistent portfolio cache **age-check** — added in v3.11.1 (rejects >120s entries). (sync-I/O-under-lock perf item still open below.)
- [x] `all_positions_exhausted_safety_orders` **cascade undercount + short-blindness** — now uses `count_deployed_safety_orders`/`entry_trades_for_position`. +2 tests. `position_manager.py`
- [x] **`fixed_usd` budget cap** — added to the budget gate so `fixed_usd` bots get a real per-deal cap (sizing paths already routed to the USD fields). +2 tests. `position_manager.py`
- [x] `order_reconciliation_monitor` **fetch_limit clamp** to Coinbase's 1000 cap. `order_reconciliation_monitor.py`
- [x] `take_profit_percent` **typo** → `take_profit_percentage`. `PositionCard.tsx`
- [x] `botRebalancerApi` **`r.ok` checks** added (throws on HTTP error). `botRebalancerApi.ts`
- [x] `batch_analyzer` outer except now `db.rollback()`s before returning. `batch_analyzer.py`
- [x] Null-safe `float(... or 0)` on fill fields (was TypeError on null). `limit_order_monitor.py` (×5)
- [x] Candle cache is **length-aware** — a 200-candle request is no longer served a cached 100 (key stays shared; reused only when it holds ≥ requested). `multi_bot_monitor.py`
- [x] Frontend candle fetch **AbortController + cancelled guard** — stale pair's response can't overwrite. `useChartsData.ts`
- [x] `PriceBar` TP target now matches the chart (`take_profit_percentage` first). `PriceBar.tsx`
- [~] Persistent cache **sync file I/O under lock** — moved to 🟡 perf (wrap in `asyncio.to_thread`). `cache.py`
- [~] `PositionCard` `getQueryData(['bots'])` key — **deferred**: needs account-context threading; has a `bot.is_active` fallback; low impact.
- [~] react-query keys missing `account_id` (PerpsPortfolioPanel, transfer summary) — **deferred**: those endpoints are user-aggregate by design (scope by all accessible accounts), so the key isn't a cross-account bug; making them account-specific is a feature, not a fix.
- [~] `limit_order_monitor`:144 / `batch_analyzer`:434 swallow-and-continue — **deferred**: intentional resilience (errors are logged and the fill is re-detected next cycle); re-raising would abort the whole monitor cycle. Revisit only if misses are observed.
<!-- Reconciled 2026-06-26: the raw findings below were triaged into the [x]/~ entries
     above and re-verified fixed against current source. -->
- [x] `_close_sell_position_as_dust` clamped over-book — fixed (values dust at `effective_base`/clamped wallet balance).
- [x] `order_reconciliation_monitor` `fetch_limit` — clamped to Coinbase's 1000 cap (`:265`).
- [~] limit_order_monitor swallow-and-continue — deferred (intentional resilience; fill re-detected next cycle).
- [x] batch_analyzer outer `except` now `db.rollback()`s; per-product swallow deferred (resilience).
- [x] pair_processor candle cache — lookback/length-aware (distinct sizes kept under distinct keys).
- [x] `float(... or 0)` null guards present on fill fields.

## 🟡 Performance  (in progress on `perf/sweep-tier3`)

- [x] **Missing prod indexes** added via idempotent migration `add_perf_indexes_tier3.py` (verified genuinely absent on prod): `ai_opinion_log(account_id)`, `pending_orders(bot_id)`, `speculative_weights_proposals(account_id)`, `rate_limit_attempts(category,key,attempted_at)`. Also added all of these + the existing compounds (`order_history(bot_id,timestamp)`, `ai_opinion_log(user,product,created_at)`) to the ORM `__table_args__` with matching names → fresh installs match prod, no redundant indexes. **Requires a prod migration run.**
- [x] Sync engine now uses `pool_pre_ping` + `pool_recycle` (stale-conn errors). `database.py`
- [x] `_previous_market_context` bounded (LRU-ish evict, cap 1000) — no longer grows forever. `_shared.py`/`sell_decision.py`
- [x] Persistent portfolio cache file I/O moved off the event loop (`asyncio.to_thread`). `cache.py`
- [~] **Deferred (more involved, lower urgency):** unbounded full-history loads (`get_generic_cex_portfolio`, `get_daily_activity` → aggregate in SQL); `get_account_balances` 2nd Coinbase breakdown for `untracked_usd` (cache usually warm); chart re-init on every poll tick; `Positions.tsx` `useCallback`; batch budget `gather`; transfer-summary / copy-bot loops; `batch_price` query re-key.

## ⚪ Low / cleanup  (in progress on `cleanup/sweep-tier4`)

- [x] `dca_target_reference` param type `"string"` → `"str"`. `indicator_params.py`
- [x] Removed dead `db.execute(select(...))` (discarded result) in `create_or_update_cex_account`. `exchange_service.py`
- [x] Routine per-cycle budget lines `logger.warning` → `logger.info`. `batch_analyzer.py`
- [x] Blacklist account enumeration: 403 → 404. `blacklist_router.py`
- [x] `VirtualizedPositionList` `scrollMargin` now measured after mount (was always 0). `VirtualizedPositionList.tsx`
- [x] **FK-parity pass (v3.13.8):** added `ondelete="CASCADE"` to the ORM for `AIOpinionLog.user_id` (migration 080) and `BotRebalancerGroup.account_id` (migration 076) so fresh installs (`create_all`) match migrated prod; both now covered by the `test_fk_delete_policies` guard. `Position.signals` is already SET NULL at the FK; its relationship-level `delete-orphan` is left as-is (account-purge is the real deletion path; direct `db.delete(position)` isn't used on a money path).
- [~] **Deferred:** migration number collisions (`077`/`086` ×2) — renaming applied migrations risks re-runs; collision is cosmetic (both run).
- [~] **Deferred (low):** `manual_max_dca_orders` percentage back-calc; webhook per-IP rate limit; `syncAllChartsToRange` 3-vs-2-param interface; broad react-query invalidations; `fill_reconciler` BTC-fee comment wording.

## Likely false positive (not fixing)
- `is_paper` "used before assignment" in `_post_sell_operations`/close-short — Python doesn't block-scope and the assignment is the first statement in the `try`; defined before any await that could fail. Not a real bug.
