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

- [x] Webhook rate-limit dicts now self-evict — `_within_limit` sweeps fully-expired keys once a store exceeds 5000 entries (bounds token/IP scanning growth). `webhook_router.py`
- [x] `multi_bot_monitor.cleanup_caches` now uses the per-granularity `CANDLE_CACHE_TTL` (was the flat 300s default → premature eviction of hourly/daily candles). `multi_bot_monitor.py`
- [x] `multi_bot_monitor` pair-prune now pops the fetch lock alongside the candle entry. `multi_bot_monitor.py`
- [x] `PortfolioChartModal.tsx` candle fetch now has AbortController + cancelled guard (test updated for the new `signal`).
- [x] `Positions.tsx` handlers wrapped in `useCallback` (`togglePosition` uses functional setState to stay dep-free) so they no longer defeat `PositionCard`'s memo each poll.
- [~] `get_generic_cex_portfolio` unbounded closed-position load (non-Coinbase path) — pre-existing sweep-1 deferral; non-Coinbase accounts only.
- [~] `coin_review_service` / `cache.invalidate` sync I/O on loop — background/dead paths; low urgency.
- [~] `speculative_weights_cache` no periodic eviction — ~100 bytes/user, negligible.

## ⚪ Tier 4 — cleanup

- [x] Architecture docs synced (`architecture-sync` run) — the 3 split modules + email/SQL-aggregation/grace changes now documented; also fixed a stale migration count.
- [x] `0.999` haircut at `rebalance_monitor:735` now imports `SELL_BALANCE_HAIRCUT` (single-source; no import cycle). (`position_coin_audit`'s copy is named + documented, left.)
- [x] Orphaned `EXCHANGE_MIN_USD` comment removed from `rebalance_monitor`.
- [x] `_TF_PREFIXES` lifted to module level in `indicator_based_indicators.py`.
- [x] Stale `_get_trade_params` comment corrected (BTC-intermediary routing).
- [~] Shadow-member ticker/slippage endpoints use manager scope (UX asymmetry, not a leak); `copy_bot_to_account` sets `user_id=manager`; `request: Request = None` idiom; `btcSeriesRef: any` typing — minor, low value.
