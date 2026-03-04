# ZenithGrid Performance Audit — Big O Analysis

**Date:** 2026-03-03
**Scope:** Full-stack algorithmic and query performance analysis

---

## Critical Findings (Fix First)

### 1. MACD Calculation: O(n^2) -> O(n)
**`backend/app/indicator_calculator.py:230-271`**

The `calculate_macd` method recalculates the full EMA from scratch for every position in the prices array. With 200 candles: ~17,000 redundant EMA computations per bot cycle. Called on every cycle for every MACD-enabled bot.

```python
# CURRENT: O(n^2) — recomputes EMA from scratch for each price point
for i in range(slow_period, len(prices) + 1):
    f_ema = self.calculate_ema(temp_prices[:i], fast_period)   # O(n) each
    s_ema = self.calculate_ema(temp_prices[:i], slow_period)   # O(n) each
```

**Fix:** Use the standard incremental EMA recurrence — single O(n) pass. Same accuracy, ~100x faster with 200 candles.

---

### 2. Missing Database Indexes on Hot-Path Columns
**`backend/app/models/trading.py`**

The `positions` table's three most-queried columns all lack indexes:

| Column | Queried By | Frequency |
|--------|-----------|-----------|
| `bot_id` | Every bot cycle (multi_bot_monitor), bot list page | Every 5s per bot |
| `account_id` | Every position API call | Every user request |
| `status` | Almost every position query filters `status='open'` | Every query |

Also missing: `trades.position_id`, `positions.closed_at`, `Bot.account_id`

**Fix:** Add composite indexes:
- `(bot_id, status)` on positions — covers the hot-path bot cycle query
- `(account_id, status)` on positions — covers all position API calls
- `position_id` on trades — currently full table scan per position detail
- `(user_id, status, closed_at)` on positions — covers report range queries

---

### 3. N+1 Query: `list_bots()` — O(B) queries -> O(1)
**`backend/app/bot_routers/bot_crud_router.py:214-220`**

Every bot list page load issues 1 DB query per bot to fetch positions. With 20 bots = 20 round-trips.

**Fix:** Single `WHERE bot_id IN (...)` batch query, grouped by bot_id in Python.

---

### 4. `ClosedPositions` Polling 500 Records Every 5 Seconds
**`frontend/src/pages/ClosedPositions.tsx:83`**

```tsx
refetchInterval: 5000  // 500 immutable closed positions, every 5 seconds
```

Closed positions never change. This causes 500 records to serialize/deserialize/diff 12 times per minute, plus 3 useMemo passes over all 500 items each cycle = 1,500 array iterations every 5 seconds.

**Fix:** Change to `refetchInterval: 60000`. Immediate 12x reduction.

---

### 5. Dashboard Fetches 1,000 Closed Positions to Show 5
**`frontend/src/pages/Dashboard.tsx:83,157-159`**

```tsx
queryFn: () => positionsApi.getAll('closed', 1000)  // fetches 1,000
const recentDeals = [...allPositions].sort(...).slice(0, 5)  // uses 5
```

O(1,100 log 1,100) sort with `new Date()` construction on every render (~22,000 Date objects per render cycle).

**Fix:** Fetch only 5 recent positions from the API, or `useMemo` the sort.

---

## High-Priority Findings

### 6. `ArticleReaderContext` — 4Hz Re-render Cascade
**`frontend/src/contexts/ArticleReaderContext.tsx:928-1010`**

`tts.currentTime` in the context's `useMemo` dependency array invalidates it 4x/second during TTS playback. Every `useArticleReader()` subscriber re-renders at 4Hz.

**Fix:** Remove `currentTime`/`duration` from context value. Expose via ref + `requestAnimationFrame`.

---

### 7. Context Values Not Memoized (3 contexts)
- **`AuthContext.tsx:871-903`** — 1-second countdown timer causes O(N) consumer re-renders
- **`AccountContext.tsx:335-351`** — 60-second poll re-renders all consumers
- **`NotificationContext.tsx:301-308`** — WS state changes cascade

**Fix:** Wrap each context value in `useMemo`.

---

### 8. N+1 Pattern: `list_accounts()` — Per-Account Bot Count
**`backend/app/routers/accounts_router.py:225-229`**

```python
for account in accounts:
    bot_count_query = select(Bot).where(Bot.account_id == account.id)
    bot_count = len(bot_result.scalars().all())
```

**Fix:** Single `GROUP BY` aggregate query.

---

### 9. `get_order_stats()` — Full Table Materialization for Counts
**`backend/app/routers/order_history.py:209-229`**

Fetches ALL OrderHistory rows into Python memory just to `len()` them. Unbounded append-only table.

**Fix:** `SELECT COUNT(*), SUM(CASE WHEN status='success' THEN 1 END)...` — push aggregation to DB.

---

### 10. Per-Bot Stats Queries on Dashboard — O(N) API Calls/10s
**`frontend/src/pages/Dashboard.tsx:595-600`**

Each `BotCard` spawns its own `useQuery` with `refetchInterval: 10000`. With 10 bots = 1 API request/second from stats alone.

**Fix:** Batch into a single `/api/bots/bulk-stats` endpoint.

---

## Medium-Priority Findings

### 11. `PositionCard` / `BotListItem` Not Memoized
Both lack `React.memo`, causing O(N) re-renders on every 5-second poll cycle.

### 12. Report Service: O(B x P) Nested Scan
**`backend/app/services/report_data_service.py:154-172`** — For each bot, scans all closed positions twice. Fix with `defaultdict` grouping: O(B+P).

### 13. `signal_processor.py` — Full ORM Load for SUM
**`backend/app/trading_engine/signal_processor.py:318-325`** — Loads all open Position objects to sum one column. Fix with `SELECT SUM(total_quote_spent)`.

### 14. Duplicate Portfolio Query Key
**`frontend/src/pages/bots/hooks/useBotsData.ts`** uses `'account-portfolio-bots'` instead of `'account-portfolio'`, causing a duplicate network request.

### 15. `_needs_aggregate_indicators` — O(CxT) -> O(C+T)
**`backend/app/strategies/indicator_based.py:186`** — Rebuilds take-profit condition list inside a loop. Pre-build a set.

### 16. Safety Order Calculator — O(S) Loop for Geometric Series
**`backend/app/strategies/safety_order_calculator.py`** — Three files compute `sum(r^k)` in loops. Replace with closed-form `(r^n - 1)/(r - 1)`.

### 17. Double Open-Position Query in Monitor Loop
**`backend/app/multi_bot_monitor.py:429,499`** — Same exact query fires twice per bot per cycle, 70 lines apart.

### 18. Dashboard Unmemoized Array Operations
**`frontend/src/pages/Dashboard.tsx:140-158,536-568`** — 7 unmemoized filter/reduce/sort on up to 1,000 items. `bots.filter(b => !b.is_active)` called 4 times in one render.

---

## Low-Priority Findings

### 19. `grid_trading.py` Percentile Lookup — O(L*B) -> O(L*log B)
**`backend/app/strategies/grid_trading.py:243-251`** — Linear scan over sorted cumulative distribution. Replace with `bisect.bisect_left`.

### 20. `IndicatorCalculator` Re-instantiation
**`backend/app/trading_engine/signal_processor.py:118`** — New instance created every bot cycle (stateless class). Use module-level singleton.

### 21. `position_manager.py` List-Build for Count
**`backend/app/trading_engine/position_manager.py:215-217`** — Builds list just to count buy trades. Replace with `sum(1 for ...)`.

### 22. Sort When Min/Max Suffices
**`backend/app/position_routers/position_query_router.py:99-100`** — Sorts buy_trades O(T log T) to get first/last. Replace with `min()`/`max()` O(T).

### 23. Report Transfer Data Double Scan
**`backend/app/services/report_data_service.py:198-223`** — Two O(T) passes to sum deposits/withdrawals. Merge into one pass.

### 24. `ClosedPositions` BTC Price Outside React Query
**`frontend/src/pages/ClosedPositions.tsx:51-68`** — Raw `setInterval` for BTC price instead of using the `['btc-usd-price']` React Query cache already populated by `App.tsx`.

### 25. Redundant `uniquePairs`/`availableBots` Memos
**`frontend/src/pages/ClosedPositions.tsx:114-158`** — Two memos each iterate all 500 records. Combine into one pass.

---

## Impact Summary

| # | Location | Current | Optimized | Type |
|---|----------|---------|-----------|------|
| 1 | indicator_calculator.py | O(n^2) | O(n) | Algorithm |
| 2 | positions/trades tables | Full table scan | O(log n) | Missing indexes |
| 3 | bot_crud_router.py | O(B) queries | O(1) query | N+1 |
| 4 | ClosedPositions.tsx | 500 records/5s | 500 records/60s | Over-polling |
| 5 | Dashboard.tsx | O(1100 log 1100)/render | O(1) cached | Unmemoized |
| 6 | ArticleReaderContext | 4 re-renders/sec | 0 re-renders | Context design |
| 7 | 3 contexts | O(N) consumers/tick | O(0) when unchanged | Missing useMemo |
| 8 | accounts_router.py | O(A) queries | O(1) query | N+1 |
| 9 | order_history.py | O(N) rows to Python | O(1) scalar | Wrong aggregation |
| 10 | Dashboard BotCards | O(B) API calls/10s | O(1) call/10s | N+1 API |

**None of these optimizations affect correctness or accuracy.**
