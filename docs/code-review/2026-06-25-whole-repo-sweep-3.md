# Whole-repo code review sweep #3 — 2026-06-25

Third sweep (6 parallel Sonnet reviewers) after v3.13.0. The codebase was already
swept twice this session; this pass focused on fresh eyes + regressions from this
session's work (the 3 module splits, grace, the v3.12.x fixes). Every item below was
**re-verified against current source** by the orchestrator. Status: `[ ]` open ·
`[x]` fixed · `~` deferred/non-issue.

Context: account runs **long-only** (0 open shorts, 0 short-capable bots), so the
short-path findings are **latent** — real bugs that can't fire in the current config
but would if shorts/bidirectional are ever enabled. Fixed defensively anyway.

## 🔴 Tier 1 — correctness & security

- [x] **Short-OPEN fill has no terminal-status gate** — `_reconcile_short_sell_fill` now gates on `_TERMINAL_ORDER_STATUSES` (mirrors the close-short/buy reconcilers); a mid-fill short-open keeps polling and exhaustion returns unconfirmed (no booking). +4 tests. `sell_executor_short.py`
- [x] **Report iframe has no `sandbox`** — added `sandbox="allow-same-origin allow-popups"` (CSS + links work, scripts/forms/top-nav blocked). `ReportViewModal.tsx`

## 🟠 Tier 2 — short-path correctness (latent)

- [x] **Short DCA/grace budget shows full `max_quote_allowed`** — `_calculate_budget` now uses a direction-aware "deployed quote" (`short_total_sold_quote` for shorts, `total_quote_spent` for longs) for both the remainder and the grace-expanded remainder. (`:344` pair-level SUM still long-only — noted; only matters for concurrent same-pair shorts.) `_shared.py`
- [x] **Pattern TSL/TTP broken for shorts** — the long/bull-flag pattern-TSL block now skips shorts (`direction != "short"`); shorts use the standard inverted trailing stop (already correct). `indicator_based.py`

## 🟡 Tier 3 — performance

- [ ] Webhook rate-limit dicts (`_rate_limit_store`, `_ip_rate_limit_store`) never evict stale keys — add a prune to `cleanup_in_memory_caches` (pattern used by every other rate-limit dict).
- [ ] `multi_bot_monitor.cleanup_caches` evicts candles with the flat 300s default TTL instead of the per-granularity TTL → prematurely drops still-valid hourly/daily candles. Use `CANDLE_CACHE_TTL.get(granularity, …)`.
- [ ] `multi_bot_monitor` pair-prune deletes a candle cache entry without popping its fetch lock (orphaned locks until next TTL sweep). Add `_candle_fetch_locks.pop(k, None)`.
- [ ] `PortfolioChartModal.tsx` candle fetch missing AbortController/stale-guard (the pattern applied to DealChart/useChartData this session was missed here).
- [ ] `Positions.tsx` handlers (`openAddFundsModal`, `openNotesModal`, `togglePosition`, `handleCheckSlippage`) not `useCallback` → defeats `memo` on `PositionCard` every poll tick.
- [~] `get_generic_cex_portfolio` unbounded closed-position load (non-Coinbase path) — pre-existing sweep-1 deferral; non-Coinbase accounts only.
- [~] `coin_review_service` / `cache.invalidate` sync I/O on loop — background/dead paths; low urgency.
- [~] `speculative_weights_cache` no periodic eviction — ~100 bytes/user, negligible.

## ⚪ Tier 4 — cleanup

- [ ] Architecture docs (`backend.json`) missing the 3 new split modules — run `architecture-sync`.
- [ ] `0.999` haircut literal duplicated 3× (`rebalance_monitor:735`, `position_coin_audit`, vs `sell_executor.SELL_BALANCE_HAIRCUT`) — single-source it.
- [ ] Orphaned `EXCHANGE_MIN_USD` comment left in `rebalance_monitor` after the split (constant moved to `rebalance_planning`).
- [ ] `_TF_PREFIXES` frozenset allocated per call in `indicator_based_indicators._calculate_traditional_indicators` — lift to module level.
- [ ] Stale `_get_trade_params` comment (says `convert_currency`, code routes via BTC).
- [~] Shadow-member ticker/slippage endpoints use manager scope (UX asymmetry, not a leak); `copy_bot_to_account` sets `user_id=manager`; `request: Request = None` idiom; `btcSeriesRef: any` typing — minor, low value.
