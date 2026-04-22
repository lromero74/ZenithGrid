# PRP: Account Value First-Load Performance — Fast, Throttle-Safe Dashboard Totals

**Feature**: Make Account Value appear quickly on first login without hammering Coinbase with hundreds of price lookups
**Created**: 2026-04-21
**Last Updated**: 2026-04-22
**One-Pass Confidence Score**: 9/10

---

## Status Update

### Shipped on `main` in `v2.164.6`

The core Phase A work in this PRP has shipped:
- added `GET /api/accounts/{account_id}/account-value-summary`
- added `backend/app/services/account_value_summary_service.py`
- added shared bounded-concurrency paper valuation via `backend/app/services/paper_valuation_service.py`
- updated `frontend/src/App.tsx` and `frontend/src/pages/Dashboard.tsx` to use the summary path for first paint
- added stale snapshot fallback plus background refresh for paper accounts
- added `include_details=False` fast path for live Coinbase portfolio totals
- replaced one positions-page portfolio fetch with direct BTC/USD market-price fetch
- lazy-loaded Dashboard chart/sentiment widgets and added Vite manual chunking

### Follow-up started on `feature/dashboard-performance-followup`

The next pass is now focused on Dashboard request fan-out after the Account Value path was fixed.

Implemented on the follow-up branch:
- defer non-critical Dashboard queries by 2 seconds after first paint
- keep reservations, transfer summary, prop-guard status, and per-bot stats off the initial critical path
- keep core totals, bot list, and open/closed position counts immediate
- add backend `account_id` support to `GET /api/bots/` with a 404 for inaccessible accounts
- scope Dashboard, Closed Positions, and positions-page bot requests by `account_id` instead of fetching cross-account bot lists and filtering in the browser
- scope Dashboard open/closed position requests by `account_id` instead of fetching cross-account data and filtering client-side
- scope Closed Positions page closed-position requests by `account_id` as well
- stop Dashboard open/closed position polling while the tab is hidden
- dedupe repeated product IDs before positions-page batch price requests
- stop the positions page's custom batch price polling loop while the tab is hidden
- stop `Positions.tsx` summary/balance polling queries from refreshing in hidden tabs or on window focus
- stop Closed Positions failed-order polling from refreshing in hidden tabs or on window focus
- only poll the active tab on Closed Positions instead of refreshing both closed and failed datasets in parallel
- slow the Positions page's secondary summary queries (completed stats, realized PnL, balances) to a 2-minute cadence with non-zero staleness since open positions already refresh every 5 seconds
- replace the positions page's custom `setInterval` batch-price loop with a React Query-managed `/prices/batch` query keyed by the deduplicated open product list
- back off the open-positions polling interval from 5s to 30s when the account currently has no open deals, while keeping 5s polling for active deals
- remove the positions page's 10-second bot-metadata polling loop; bot labels/filters now use a long stale window instead of live polling
- trim the backend `GET /positions` hot path by replacing eager-loaded `trades` and `pending_orders` collections with aggregate queries for trade counts / first-buy / last-buy / pending counts, plus targeted lookup only for active limit-close orders
- scope the `GET /positions` blacklist query to just the symbols on the current page of results, and only preload bots for resize-budget calculation when a position lacks a strategy snapshot
- feed the positions list's `computed_max_budget` calculation from the aggregated first-buy quote amount so the hot list route can still derive resize budgets without touching `position.trades`
- stop expanding limit-close fill-history payloads on the positions list; the hot route now returns just the limit summary fields the card view actually uses
- trim `strategy_config_snapshot` on the list route down to the handful of keys the open-positions UI actually reads, while leaving the detail endpoint full-fidelity for modal/chart/edit flows
- centralize BTC/USD and ETH/USD market-price fetch policy in a shared `useMarketPrice()` hook
- switch `App`, `ClosedPositions`, and the positions hook to the shared market-price hook
- add `frontend/src/pages/Dashboard.test.tsx` coverage for deferred query behavior

### Current read on the bottleneck

The original Account Value bottleneck is no longer the main startup problem.
The next likely issue is query fan-out on the Dashboard:
- `bots`
- `open positions`
- `closed positions`
- `reservations`
- `transfer summary`
- `prop guard`
- per-bot `stats`

That means follow-up work should target startup request volume and polling pressure rather than reworking the summary endpoint again.

This latest pass trims one more avoidable source of overfetch:
- account-specific bot views no longer need full cross-account bot payloads just to throw most of them away client-side
- the positions page no longer keeps its manual batch price interval running in hidden tabs
- the remaining 30s/60s page-level polling queries on Positions and Closed Positions now follow the same hidden-tab / no-focus-refresh policy as the earlier Dashboard cleanup
- Closed Positions no longer refreshes both tabs' backing datasets at once
- the open positions screen now uses one React Query polling model for both position rows and deduplicated batch prices instead of mixing React Query with a separate manual timer
- the open positions screen now only stays on a 5-second cadence when there are actually active deals to watch
- each active-deals refresh is now lighter on the backend because the positions list endpoint no longer hydrates every trade and pending order row just to compute summary fields for the list
- the positions hot path also no longer pulls unrelated blacklist rows or unnecessary bot configs for positions that can compute their budget from the frozen snapshot alone
- the remaining list-route budget calculation no longer has to lazy-load trade rows for snapshot-less positions; it reuses the first-buy size already pulled by the aggregate query
- active limit-close rows also no longer JSON-parse and serialize fill-by-fill history on every poll; the list keeps only the summary stats the Positions cards render
- the list response also no longer ships the entire frozen strategy config blob for every open deal; it keeps only the keys the list/cards/charts/edit affordances actually read, and the detail endpoint still preserves the full snapshot when needed
- the remaining high-frequency pressure is now concentrated mostly in the necessity of the active-deals 5-second refresh itself rather than in auxiliary summary queries, bot metadata churn, duplicate timer infrastructure, avoidable ORM overfetch, or broad supporting lookups

---

## Context & Goal

### Problem

The Dashboard header and Dashboard page both depend on the portfolio endpoint for Account Value:
- `frontend/src/App.tsx`
- `frontend/src/pages/Dashboard.tsx`

That endpoint is cheap for a real Coinbase account, but it is extremely expensive for large paper accounts because `backend/app/services/account_service.py::_build_paper_portfolio()` fetches prices one asset at a time from Coinbase's public API, with a USD lookup first and a BTC fallback second.

On `testbot`, the real bottleneck is **not PostgreSQL**:
- `trading.positions`: 1,903 rows total
- `reporting.account_value_snapshots`: 746 rows total
- `SELECT * FROM trading.positions WHERE account_id = 7 AND status = 'closed'`: about `1.2 ms`
- `SELECT * FROM trading.positions WHERE account_id = 7 AND status = 'open'`: about `0.3 ms`
- `get_account_value_history(..., account_id=7)`: about `0.315 s`

The real bottleneck is the paper-account portfolio build on cold cache:
- account `7` (`Demo USD Paper`): 135 non-stable assets, first load `27.469 s`
- account `9` (`Demo Both Paper`): 145 non-stable assets, first load `3.408 s`
- account `3` (`Paper Trading`): 167 non-stable assets, first load `7.119 s`
- account `8` (`Demo BTC Paper`): 21 non-stable assets, first load `0.784 s`
- real Coinbase account `1`: `0.002 s`

Repeated calls for account `7` dropped to `0.002 s` after caches were warm. That means users are paying for a cold-start valuation burst on first login.

### Root Cause

The initial Account Value UI is waiting on work that is too expensive for the critical path:

1. The frontend asks the **full portfolio endpoint** for Account Value, even though the header only needs `total_usd_value`, `total_btc_value`, and maybe `btc_usd_price`.
2. The paper-account code path values every non-stable asset individually on first load.
3. Each unknown asset can trigger two outbound Coinbase requests (`-USD`, then `-BTC`).
4. The current behavior is sensitive to cold cache state, so "first login" is much slower than steady state.

### Goal

Make Account Value feel immediate on first login while staying friendly to Coinbase rate limits.

Success means:
- The header and dashboard can show a usable Account Value quickly, even on large paper accounts.
- We do **not** solve this by spraying unbounded parallel requests at Coinbase.
- Full holdings valuation still becomes accurate shortly afterward.
- The Portfolio page can remain heavier than the header if needed.

### What This Is Not

This PRP does **not** aim to:
- rewrite all portfolio logic
- remove live pricing entirely
- change how real Coinbase CEX accounts are valued
- introduce a new third-party pricing provider
- optimize the account value chart first; the chart is not the main bottleneck

---

## Constraints

### Must Respect Coinbase Throttling

We are pulling prices from Coinbase. Any fix that simply parallelizes 100-150 asset lookups is risky and can easily trade latency for throttling.

This PRP must therefore follow these rules:
- bounded concurrency only
- short-TTL cache for successful prices
- meaningful negative cache for unsupported symbols
- stale-while-revalidate behavior where possible
- keep heavy holdings valuation off the login critical path

### UX Principle

Best-in-class behavior here is:
1. show a recent Account Value immediately
2. indicate refresh/loading subtly
3. replace it with fresh data when ready

Users should not stare at a skeleton waiting for 100+ symbols to be repriced.

---

## Existing Code Patterns (Reference)

### Frontend critical path

Original state when this PRP was written:
- `frontend/src/App.tsx` fetched the full portfolio path for Account Value
- `frontend/src/pages/Dashboard.tsx` also fetched the full portfolio path for Account Value

Current state after Phase A:
- Account Value first paint uses `useAccountValueSummary()`
- the full portfolio payload is no longer required for header/dashboard Account Value rendering
- the remaining frontend startup cost is now dominated more by query fan-out than by summary valuation

### Backend portfolio entry points

For specific accounts:
- `backend/app/routers/accounts_query_router.py`
- `GET /api/accounts/{account_id}/portfolio`
- `app.services.account_service.get_portfolio_for_account()`

Paper trading branch:
- `backend/app/services/account_service.py::_build_paper_portfolio()`

Real Coinbase branch:
- `backend/app/services/portfolio_service.py::get_cex_portfolio()`

### Current account-value chart endpoints

These are already separate and comparatively cheap:
- `backend/app/routers/account_value_router.py`
- `GET /api/account-value/history`
- `GET /api/account-value/activity`

They should not be the first target for this performance fix.

---

## Proposed Solution

Split "fast Account Value summary" from "full portfolio valuation."

### Phase 1 strategy

Introduce a lightweight account-value summary path that returns:
- `total_usd_value`
- `total_btc_value`
- `btc_usd_price`
- metadata such as `is_stale`, `as_of`, or `refreshing`

This path should be safe to serve quickly from cache or recent computed state.

The header and dashboard should use this new summary endpoint instead of the full portfolio endpoint for first paint.

### Phase 2 strategy

Keep full portfolio valuation for:
- Portfolio page
- holdings tables
- balance breakdown
- precise per-asset percentages

But move it off the login-critical path and make the paper-account branch throttle-safe:
- cap concurrency
- reuse cached prices
- negative-cache unsupported symbols
- allow stale prices on first paint and revalidate in background

---

## Recommended Design

### 1. New summary endpoint

Add a dedicated endpoint, for example:
- `GET /api/accounts/{account_id}/account-value-summary`

Response shape:

```json
{
  "account_id": 7,
  "total_usd_value": 1073.69,
  "total_btc_value": 0.0112,
  "btc_usd_price": 95842.12,
  "as_of": "2026-04-21T22:15:00Z",
  "is_stale": true,
  "is_refreshing": true
}
```

This endpoint should not build the full holdings array.

### 2. New paper-account valuation cache

Create a dedicated cache for paper account value summary, separate from the full portfolio response.

Cache keys:
- `paper_account_value_summary_{account_id}`
- `paper_asset_price_usd_{symbol}`
- `paper_asset_price_btc_{symbol}`
- `paper_asset_symbol_negative_{symbol}_{quote}`

Recommended TTLs:
- account summary: `30-60s`
- successful symbol price: `60-300s`
- negative symbol cache: `15-60 min`

Implementation note:
- explicit summary caching shipped
- symbol-level success/negative caching is effectively handled by the Coinbase public market data helpers via `api_cache`

### 3. Stale-while-revalidate for summary

If a cached summary exists:
- return it immediately
- optionally trigger refresh in background if stale

If no cached summary exists:
- compute it with bounded concurrency
- store it
- return it

This avoids making every first visible render wait on a full repricing sweep.

### 4. Bounded concurrency for paper price refresh

Do **not** use unbounded `asyncio.gather()` across all symbols.

Use a semaphore or small worker pool.

Recommended starting limit:
- `5` concurrent public Coinbase requests

This is intentionally conservative. If we later confirm headroom, increase to `8-10`, but start low.

### 5. Negative-cache unsupported products

When Coinbase returns 404 for:
- `RONIN-USD`
- `RONIN-BTC`

cache that miss so later logins do not retry both lookups immediately.

This is especially important for demo portfolios with many long-tail assets.

### 6. Frontend critical-path cleanup

Update:
- `frontend/src/App.tsx`
- `frontend/src/pages/Dashboard.tsx`

So they:
- wait for `selectedAccount`
- fetch the summary endpoint for Account Value
- stop using `/api/account/portfolio` as an early fallback on login

The full portfolio query can remain for places that really need holdings.

---

## Implementation Blueprint

### TDD Requirement

Write failing tests first. No implementation before red tests exist.

---

### Step 1 — Add backend tests for summary endpoint and stale cache behavior

Create tests in:
- `backend/tests/routers/test_accounts_router.py` or a new `test_account_value_summary_router.py`
- `backend/tests/services/test_account_value_summary_service.py`

Required tests:
- happy path: returns cached summary immediately for a paper account
- edge case: stale cached summary returns with `is_stale=true`
- failure case: inaccessible account returns 404
- happy path: real Coinbase account summary still works
- edge case: negative-cached unsupported symbol does not refetch immediately

### Step 2 — Add service-level tests for bounded concurrency

Write a service test that:
- seeds a paper account with many non-stable balances
- mocks Coinbase public price calls
- asserts the implementation never exceeds the configured concurrency limit

Required tests:
- happy path: 100 assets resolve with bounded concurrency
- edge case: some symbols only exist as `-BTC` pairs
- failure case: unsupported symbols are negative-cached and counted as zero

### Step 3 — Add frontend tests for new critical path

Update or add tests near:
- `frontend/src/App.tsx`
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/services/api.test.ts`

Required tests:
- happy path: header uses summary endpoint instead of full portfolio endpoint for first paint
- edge case: no `selectedAccount` means no premature aggregate portfolio request
- failure case: stale summary still renders values instead of a blank loading state

### Step 4 — Implement backend summary service

Suggested new service:
- `backend/app/services/account_value_summary_service.py`

Responsibilities:
- fetch cached summary
- compute fresh summary when needed
- perform bounded-concurrency paper pricing
- use negative cache for unsupported symbols
- reuse existing real-account portfolio logic where it is already cheap

Keep responsibilities narrow:
- summary service returns totals only
- full portfolio service keeps returning holdings/breakdowns

### Step 5 — Add router endpoint

Suggested location:
- `backend/app/routers/accounts_query_router.py`

Add:
- `GET /api/accounts/{account_id}/account-value-summary`

Use `accessible_accounts_filter()` for account access.

### Step 6 — Update frontend to consume summary endpoint

Change:
- `frontend/src/App.tsx`
- `frontend/src/pages/Dashboard.tsx`
- optionally `frontend/src/services/api.ts`

Behavior:
- header Account Value uses summary query
- dashboard Account Value card uses summary query
- full portfolio query remains only where holdings are actually needed

Status:
- shipped on `main`

### Step 7 — Optional background refresh hook

If implementation remains straightforward, add a background refresh trigger for stale summary values.

If that adds too much complexity, defer it and ship:
- immediate cached summary
- explicit refresh on normal poll interval

KISS applies here.

Status:
- shipped in a simple form via stale snapshot fallback + background refresh + quick recheck polling

### Step 8 — Dashboard fan-out follow-up

Now that Account Value is fast, reduce remaining startup pressure from non-critical Dashboard queries.

Current implementation direction:
- defer non-critical Dashboard queries for about 2 seconds after first paint
- keep per-bot stats off the initial render critical path
- keep reservations and transfer summary out of the initial burst
- continue gating prop-guard calls to prop-firm accounts only

Likely next tests:
- happy path: first paint renders core dashboard content before deferred queries fire
- edge case: non-prop accounts never hit prop-guard status
- failure case: deferred query failures do not block core dashboard render

---

## File-Level Plan

### Backend

Likely touched files:
- `backend/app/services/account_service.py`
- `backend/app/routers/accounts_query_router.py`
- `backend/app/services/account_cache.py` or cache module equivalents
- `backend/app/services/account_value_summary_service.py` (new)
- `backend/tests/services/test_account_value_summary_service.py` (new)
- `backend/tests/routers/test_account_value_summary_router.py` (new or merged into existing router tests)

### Frontend

Likely touched files:
- `frontend/src/App.tsx`
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/services/api.test.ts`

---

## Acceptance Criteria

### Functional

- Header Account Value no longer depends on the full portfolio payload.
- Dashboard first load for paper accounts returns a usable Account Value quickly.
- Unsupported symbols do not cause repeated cold-start retry storms.
- Real Coinbase account behavior remains correct.
- Non-critical Dashboard queries do not block first paint.

### Performance

Targets for first visible Account Value:
- real Coinbase account: unchanged, near-instant
- cached paper account: under `250 ms`
- cold paper account summary: materially lower than current `27.469 s`; target under `2 s` for demo accounts

The full portfolio page may still take longer than the summary path.

### Safety

- No unbounded parallel request fan-out to Coinbase
- bounded concurrency enforced by tests
- unsupported products negative-cached
- no auth regression on account access
- deferred Dashboard queries must not hide or delay core account totals

---

## Risks & Mitigations

### Risk 1 — Summary and full portfolio drift

If the summary service duplicates too much logic, totals can diverge from the Portfolio page.

Mitigation:
- centralize valuation helpers where possible
- keep summary shape small
- add tests comparing summary totals and full portfolio totals under mocked pricing

### Risk 2 — Background refresh complexity

If stale-while-revalidate becomes too clever, we risk race conditions or duplicate refreshes.

Mitigation:
- ship cached-summary-first behavior even without background refresh if needed
- prefer simple poll-based refresh over task orchestration on v1

### Risk 3 — Coinbase throttling during refresh bursts

Even with better UX, background refresh can still be noisy if many users log in together.

Mitigation:
- low concurrency cap
- short summary TTL
- negative cache
- avoid redundant summary + full-portfolio fetches on the same screen

---

## Rollout Order

### Phase A — Fast Summary Path

Ship first:
- new summary service
- new summary endpoint
- frontend header/dashboard switched to it
- negative cache
- bounded concurrency

This is the highest-impact, lowest-risk slice.

Status:
- complete and shipped on `main`

### Phase B — Full Portfolio Cleanup

After Phase A proves stable:
- evaluate whether the full portfolio endpoint also needs paper-account optimization
- possibly reuse the same per-asset cache there
- optionally add background revalidation for the Portfolio page too

Status:
- still open
- lower priority than Dashboard startup fan-out unless fresh profiling shows Portfolio has become the main pain point

### Phase C — Dashboard Startup Fan-Out

After the summary path is fixed:
- defer non-critical Dashboard queries until just after first paint
- reduce per-bot startup query bursts
- profile whether polling intervals need further tightening

Status:
- in progress on `feature/dashboard-performance-followup`

---

## Open Questions

1. Should the summary endpoint return the last snapshot if no recent live valuation is available?
2. Should paper accounts prefer cached prices from prior portfolio views, even if somewhat stale?
3. Do we want a tiny "refreshing..." indicator on the Account Value card when stale data is shown?

Recommended answers for first implementation:
- `1.` Yes, if recent enough and clearly marked stale.
- `2.` Yes.
- `3.` Yes, subtle only.

Additional follow-up questions:
- Should bot stats stay deferred permanently, or only until the bot cards scroll into view?
- Should Dashboard open/closed positions be consolidated into a single backend summary endpoint to reduce request count?
- Should BTC/ETH market-price queries be centralized into a shared hook so `App` and `Positions` reuse the same policy?

Answered since last update:
- BTC/ETH market-price queries now use a shared hook and shared API helper. The next question is whether other one-off market-price fetches, such as modal-level fetches, should join the same path too.

---

## PRP Score

**9/10** — The bottleneck is measured, localized, and reproducible on `testbot`. The fastest safe path is also the cleanest product path: stop making the login-critical Account Value depend on full holdings valuation. The main engineering judgment is choosing conservative cache TTLs and a concurrency cap that improves latency without antagonizing Coinbase. Starting with a lightweight summary endpoint plus bounded-concurrency paper valuation keeps blast radius low and aligns with KISS/YAGNI.
