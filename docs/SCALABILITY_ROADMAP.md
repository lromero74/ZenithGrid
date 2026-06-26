# ZenithGrid — Scalability & Microservices Roadmap

**Written:** 2026-03-21
**Context:** App is a layered monolith. (As of 2026-06-13 prod runs natively on an AWS Lightsail instance with local PostgreSQL; it previously ran on `fedora.local` with the app in the `zenith-box` distrobox and PostgreSQL in `postgres-box`.) Good internal structure, tight coupling at the data layer.

This document is divided into three phases:
- **Phase 1 — Immediate wins** (low risk, high bang-for-buck, no architecture change)
- **Phase 2 — Prep work** (internal refactors that enable future extraction without committing to microservices)
- **Phase 3 — Microservice extraction** (only when scale demands it, ordered by ease)

---

## Current Architecture Snapshot

| Layer | Count | Lines |
|---|---|---|
| Routers (trading, auth, social, content, reporting) | 35 | ~13,500 |
| Services (monitors, fetchers, schedulers, executors) | 52 | ~21,500 |
| Background tasks (single event loop) | 27 | — |
| Database | 1 shared PostgreSQL | All domains |

**Key coupling points** (the things that make extraction hard today):
1. **Single shared database** — no schema isolation between domains
2. **Auth is implicit everywhere** — `Depends(get_current_user)` in every endpoint; no API gateway
3. **Global exchange client pool** — credentials decrypted from app secret at runtime, cached in a module-level dict; no credentials service
4. **Single WebSocket manager** — game, chat, and order-fill notifications through the same `ws_manager` singleton
5. **27 asyncio tasks sharing one event loop** — no task queue, no priority tiers, no coordination
6. **Module-level cache singletons** — `api_cache`, `portfolio_cache` with a single shared cleanup job
7. **No inter-service messaging** — all coordination via direct shared DB queries

## Capacity Watch — 2026-06-26

Production has already shown that a single-user workload can briefly max out the
local PostgreSQL connection budget when the web app fans out requests while the
trader is holding many long-lived sessions. v3.13.14 reduces the immediate
pressure by batching Positions AI-opinion reads, lowering trader concurrency,
and making indicator logging best-effort.

**Deferred multi-user infrastructure step:** before opening the app to roughly
5-10 additional account managers, revisit the hosting/database shape rather
than only tuning in-process pools. The likely next move is some combination of:
PgBouncer transaction pooling in front of PostgreSQL, moving PostgreSQL off the
Lightsail app host (managed RDS or a larger EC2/Postgres host), keeping web and
trader as separate systemd roles, and upgrading away from bursty/noisy Lightsail
CPU if CPU steal remains high under load. Keep the new `/api/performance/capacity`
endpoint, `/api/performance/summary`, `pg_stat_activity`, and `vmstat`/CPU-steal
samples as the decision inputs.

---

## Phase 1 — Immediate Wins (Do Now)

These changes reduce resource contention and improve reliability **without any architecture change**. They address the symptoms already seen (DB pool exhaustion, event loop contention under load).

### 1.1 — Tier the 27 background tasks by priority ✅ DONE (v2.125.8)

**Problem:** All 27 tasks share the same asyncio event loop. A slow news fetch or weekly coin review competes with bot monitoring and order fills for CPU time. The 30-second DB pool timeout that appeared when saving a bot is a symptom of this.

**Fix:** Assign tasks to priority tiers. Tier 1 runs on the main trading event loop. Tier 2 and 3 run on a separate `asyncio` event loop in a dedicated daemon thread with its own smaller DB connection pool.

```
Main Event Loop (Tier 1 — real-time trading + in-memory state):
  MultiBotMonitor          10s interval
  LimitOrderMonitor        10s interval + 5m sweep
  OrderReconciliationMon   60s interval
  PropGuardMonitor         30s interval
  PerpsMonitor             60s interval
  MissingOrderDetector     5m interval
  MemoryCacheCleanup       5m interval    ← touches shared in-memory state
  AutoBuyMonitor           continuous     ← moved to secondary loop (v2.125.12, see Fix E/F/G)
  RebalanceMonitor         continuous     ← moved to secondary loop (v2.125.12)
  TradingPairMonitor       daily          ← moved to secondary loop (v2.125.12)
  TransferSync             daily          ← moved to secondary loop (v2.125.12)
  AccountSnapshotService   daily          ← moved to secondary loop (v2.125.12)

Secondary Event Loop (Tier 2/3):
  ContentRefreshService    30m / 60m      ← uses DB via news_fetch_service (session_maker injected)
  BanMonitor               daily, 30s startup delay
  ReportScheduler          15m interval
  CoinReviewScheduler      7 day interval   ← creates own CoinbaseClient per run (not from cache)
  DomainBlacklistService   weekly           ← HTTP only
  DebtCeilingMonitor       weekly           ← AI + sync DB
  DecisionLogCleanup       daily
  FailedConditionCleanup   6h interval
  FailedOrderCleanup       6h interval
  RevokedTokenCleanup      daily
  SessionCleanup           daily
  RateLimitCleanup         hourly
  ReportCleanup            weekly
  ChangelogCacheRebuild    startup only (synchronous, on main startup path)
```

**Implementation notes (learned during execution):**
- New module `app/secondary_loop.py` owns: loop lifecycle (`start_secondary_loop`, `stop_secondary_loop`), DB engine creation bound to the secondary loop, `schedule(coro)` helper using `asyncio.run_coroutine_threadsafe`, and `get_secondary_session_maker()`.
- **asyncpg is event-loop bound**: DB connections bind to the loop that created the engine. Secondary loop creates its own `create_async_engine` instance INSIDE the loop (via `asyncio.run_coroutine_threadsafe(_init_secondary_engine(), loop).result()`). Main and secondary engines are completely independent.
- **Pool budget**: Main (size=8, overflow=4=12) + Read (size=4, overflow=2=6) + Secondary (size=3, overflow=2=5) = 23 max vs `max_connections=25`. Tight but within limits.
- **Session maker injection pattern**: Coroutine-style tasks accept `session_maker=None` with `sm = session_maker or _default_session_maker` fallback. Class-based monitors get `set_session_maker(sm)` / `_get_sm()` methods. Backwards-compatible — tests and direct calls still work without injection.
- **`coin_review_service.py` required threading session_maker through 5 layers**: `run_coin_review_scheduler` → `_get_last_review_timestamp`, `run_weekly_review` → `get_tracked_coins`, `update_coin_statuses` → `get_coinbase_client_from_db`. All now have `session_maker=None` parameter.
- **`MemoryCacheCleanup` stays on main loop**: It touches in-memory state shared with request handlers (rate-limit dicts). `cleanup_stale_entries()` on auto_buy_monitor and rebalance_monitor is called from here — those monitors now run on the secondary loop, so these calls are cross-thread dict mutations. Protected with `threading.Lock` on `_account_timers_lock` in both monitors.
- **`DomainBlacklistService` and `DebtCeilingMonitor` do NOT use `async_session_maker`** (HTTP-only services) — no `set_session_maker()` needed, just `schedule(service.start())`.
- **`ContentRefreshService` was incorrectly identified as HTTP-only during initial Phase 1.1** — it calls `news_fetch_service.fetch_all_news()` and `fetch_all_videos()`, which had 8 `async_session_maker()` call sites. Running it on the secondary loop caused `asyncpg: Future attached to a different loop` errors in production (v2.125.8). **Fix C (v2.125.9)**: threaded `session_maker` through all 8 DB call sites in `news_fetch_service.py` and added `set_session_maker`/`_get_sm` to `ContentRefreshService`. Now runs safely on the secondary loop.
- **CoinbaseClient rate limit lock fixed (v2.125.9)**: `CoinbaseClient._rate_limit_lock` was `asyncio.Lock()`. Replaced with `threading.Lock`. The critical section (float reads/writes) is < 1 µs; the actual sleep uses `await asyncio.sleep(wait)` (loop-agnostic). `_account_timers_lock` (threading.Lock) also added to both monitors for cross-thread dict safety.
- **Deeper asyncio.Lock constraint — 5 monitors stay on main loop (v2.125.11)**: Moving AutoBuyMonitor, RebalanceMonitor, TradingPairMonitor, AccountSnapshotService, TransferSync to the secondary loop caused `RuntimeError: Task got Future attached to a different loop` and `asyncio.Lock is bound to a different event loop` errors in production. Root cause: these monitors call helper functions (`calculate_aggregate_usd_value`, `get_exchange_client_for_account`, `public_market_data._public_request`, etc.) that use module-level `asyncio.Lock` objects and the main pool's `async_session_maker`. **ContentRefreshService does NOT call any of these helpers — it is safely on the secondary loop.**
- **5 monitors successfully migrated to secondary loop (v2.125.12+)**: After resolving all asyncio.Lock blockers listed below, AutoBuyMonitor, RebalanceMonitor, TradingPairMonitor, AccountSnapshotService, and TransferSync were moved to the secondary loop. All 27 background tasks are now correctly tiered.
- **Fix E — `public_market_data._rate_lock` → threading.Lock (v2.125.12)**: Used slot-reserve pattern: compute wait and advance `_last_request_time` inside `threading.Lock`, then `await asyncio.sleep(wait)` outside the lock. Pattern identical to CoinbaseClient fix.
- **Fix F — `exchange_service._exchange_client_lock` → threading.Lock (v2.125.12)**: The lock previously guarded an `async with` block containing DB queries and client construction — incompatible with threading.Lock. Restructured so ALL async work happens OUTSIDE the lock. threading.Lock wraps only the fast dict read/write for cache check and cache write (double-checked locking pattern). Also threaded `session_maker` parameter through `get_exchange_client_for_account` so PropGuardClient can receive the correct session_maker at construction time.
- **Fix G — `api_cache._lock` → threading.Lock (v2.125.12, discovered in production)**: `SimpleCache._lock` was `asyncio.Lock()`. When main loop called `calculate_aggregate_quote_value()` and acquired the lock first, any secondary-loop call to the same `api_cache` singleton raised `Future attached to a different loop`. All 8 `async with self._lock:` blocks contain only pure dict reads/writes (no `await`), so converting to `threading.Lock` (sync `with self._lock:`) is safe.
- **Fix H — `ByBitClient._rate_lock` → threading.Lock (v2.125.13)**: Same slot-reserve pattern as Fix E. `pybit` package also confirmed as a requirements.txt dependency and installed (`pip install pybit`).
- **Fix I — `PropGuardClient._order_lock` → loop-aware asyncio.Lock (v2.125.13)**: Per-account locks that guard async work (await inside the lock) cannot use threading.Lock. Fix: keyed by `(id(asyncio.get_running_loop()), account_id)` so each event loop gets its own `asyncio.Lock` per account. Lock no longer stored in `__init__` (would bind to creation loop) — looked up lazily via `_get_account_lock(self._account_id)` at every `async with` call site.
- **Fix J — `PaperTradingClient._balance_lock` → loop-aware asyncio.Lock (v2.125.13)**: Same `(id(loop), account_id)` key pattern as Fix I.
- **Fix K — `PaperTradingClient` direct `async_session_maker` import → injected `session_maker` (v2.125.14)**: `_reload_balances`, `_save_balances`, and `calculate_aggregate_quote_value` all imported `async_session_maker` (main pool, maxsize=5 Queue) directly. When `RebalanceMonitor` (secondary loop) called these for paper trading accounts, the secondary loop tried to `await main_pool_queue.get()` → "Queue is bound to a different event loop". Pattern for finding this class of bug: grep for `from app.database import async_session_maker` inside exchange client implementations. Any hardcoded import (instead of injected session_maker) is a potential secondary-loop crash if that client is used from both loops.
- **`api_cache.get_or_fetch` `_in_flight` Future cross-loop risk (not yet fixed)**: `get_or_fetch` stores `asyncio.Future` objects in `_in_flight` dict (keyed by cache key). If the main loop puts a Future in `_in_flight["X"]` and the secondary loop simultaneously calls `get_or_fetch("X")`, the secondary loop would `await main_loop_future` → RuntimeError. This race is narrow (same uncached key, both loops, within the same cache TTL window) and `account_balance_api.py` avoids `get_or_fetch` entirely. If it becomes a problem, key `_in_flight` by `(id(loop), cache_key)` the same way as per-account locks.
- **How to test cross-loop bugs**: Standard `pytest-asyncio` tests run all code on one loop — they never trigger cross-loop failures. To catch these: (1) write "session_maker injection" tests that assert the injected sm is called (not the global), (2) write explicit two-loop tests using `asyncio.new_event_loop()` and `asyncio.run_coroutine_threadsafe()` to call affected functions from a secondary loop.
- **Shutdown**: Secondary-loop monitors get `running = False` signal; `stop_secondary_loop()` handles actual task cancellation. `await monitor.stop()` only for main loop monitors (price_monitor, perps_monitor). Module-level task globals reduced from 6 to 4.
- **`build_changelog_cache()` stays synchronous on main startup path**: It runs `git log` (< 1 second), is startup-only, and not a loop — no benefit to moving it.

**Impact:** Trading monitors get CPU/DB pool priority. Slow tasks no longer block order execution. Main pool's 12 connections reserved for Tier 1 + API request handlers. 20 of 27 background tasks now on secondary loop.
**Effort:** Medium — 13 files changed, 36 new tests across two phases.

---

### 1.2 — Move cleanup and batch jobs to APScheduler ✅ DONE (v2.126.0)

**Problem:** All 27 tasks are hand-rolled `asyncio.sleep()` loops. There's no retry logic, no error isolation, no visibility into task health. A crashing cleanup task silently dies.

**Fix:** Move all Tier 2 and Tier 3 tasks to [APScheduler](https://apscheduler.readthedocs.io/) (already available in most Python setups). APScheduler gives you:
- Cron-style scheduling (not sleep-loop drift)
- Per-job error handlers
- Job history / next-run visibility (useful for admin panel)
- Easy migration to distributed backends later (Redis, SQLAlchemy store)

**Implementation notes (learned during execution):**
- `AsyncIOScheduler` from APScheduler 3.11.2 used. Scheduler instance lives in `app/scheduler.py` as a module-level singleton imported by `main.py`.
- `job.modify(next_run_time=datetime.utcnow())` is the correct way to trigger an immediate run without destroying the `IntervalTrigger`. `reschedule()` would have destroyed the trigger.
- All secondary-loop sleep-loop tasks converted to APScheduler `IntervalTrigger` jobs. Main-loop monitors (MultiBotMonitor, LimitOrderMonitor, etc.) retain their own asyncio loops — APScheduler is for the background cleanup/batch tier only.
- v2.126.1 patched a TTS shutdown test failure caused by the APScheduler refactor (test expected the old sleep-loop shutdown sequence).

**Impact:** Frees ~15 manual asyncio loops. Reduces main.py startup block from ~150 lines to ~30 lines.
**Effort:** Low-medium — drop-in replacement per task.

---

### 1.3 — Add a read replica (or separate connection pool) for analytics ✅ DONE (v2.125.7)

**Problem:** Report generation, goal snapshots, and market metrics do heavy aggregate queries (`SUM`, `GROUP BY`, window functions) against the same connection pool that handles order fills. On PostgreSQL this causes query queue contention.

**Fix (short term):** Create a second `async_session_maker` with a separate engine pointing to the **same database** but configured as a read-only connection (set `execution_options={'postgresql_readonly': True}`). Route all report/analytics queries through it. This separates the connection pool budget without needing a real replica.

**Fix (medium term):** Set up a PostgreSQL streaming replica (pg_basebackup + replication slot). Route `ReportDataService`, `GoalSnapshotService`, `MarketMetricsService` to the replica URL.

**Implementation notes (learned during execution):**
- `read_engine` + `read_async_session_maker` + `get_read_db()` added to `database.py`. Write pool: `size=8, overflow=4` (12 max). Read pool: `size=4, overflow=2` (6 max). Total 18 vs `max_connections=25` — leaves 7 for sync engine, psql admin, migrations.
- 8 GET endpoints in `reports_router.py` and 3 GET endpoints in `account_value_router.py` switched to `Depends(get_read_db)`. Write endpoints (POST/PUT/DELETE) unchanged.
- `market_metrics_service.get_metric_history_data()` now uses `read_async_session_maker`. `record_metric_snapshot()` and `prune_old_snapshots()` correctly stay on write pool — **the PRP was wrong to classify them as reads**; they do INSERT/DELETE + commit.
- `report_scheduler.py` NOT changed: `generate_report_for_schedule()` uses a single session for both reads (fetching goals, snapshots, trend data) AND writes (creating Report row, updating schedule timestamps). Splitting would require refactoring the entire function signature and all its callers. Deferred.
- FastAPI's `Dependant.dependencies` returns `Dependant` objects directly (not `DependencyInfo` wrappers) in current FastAPI versions. Use `dep.call` and `dep.dependencies` for tree traversal.
- `get_current_user` itself uses `Depends(get_db)` internally, so `get_db` appears as a transitive dependency of EVERY endpoint. Dependency tests must check only direct (top-level) dependencies to avoid false positives.

**Impact:** Analytics read queries no longer compete with trading writes for the 12-connection write pool.
**Effort:** Low — 5 files changed, 22 new tests.

---

### 1.4 — Async geo lookup for ban monitor (burst improvement) ✅ DONE (v2.125.6)

**Problem:** `ban_monitor._query_fail2ban()` calls `_lookup_ip_geo()` synchronously in a thread pool executor — one HTTP request at a time. With 200+ banned IPs, the initial refresh after a restart takes minutes (even with the cache fix in v2.125.4).

**Fix:** Two-pass design in `_query_fail2ban`: Pass 1 collects all (ip, jail) pairs from all jails; Pass 2 calls `_lookup_ip_geo_bulk()` for all unique IPs concurrently (`ThreadPoolExecutor(max_workers=10)` + `as_completed()`). The geo cache from v2.125.4 ensures warm runs are instant; this makes the cold start fast too.

**Implementation notes (learned during execution):**
- `_query_fail2ban` already runs inside `run_in_executor(None, ...)` (it's a sync function called from an async context) — so `asyncio.gather()` + `aiohttp` would NOT work. Using `concurrent.futures.ThreadPoolExecutor` + `as_completed` is the correct approach for threading within a thread.
- `aiohttp` not needed — stdlib `urllib.request` works fine in a thread pool. No new dependencies added.
- `MAX_GEO_WORKERS = 10` constant at module level for easy tuning.
- Deduplicate IPs with `dict.fromkeys()` (preserves order, unlike `set()`).
- Cache short-circuit: cached IPs are resolved before the executor starts — zero overhead on warm runs.
- Failed lookups return `{}` and are not cached, so they'll retry next run.

**Impact:** Ban monitor first-pass refresh goes from O(n) × 500ms to O(ceil(n/10)) × 500ms — ~10× faster for 200 IPs.
**Effort:** Low — isolated change in `ban_monitor.py`, 8 new tests.

---

### 1.5 — Separate TTS processing to a thread pool ✅ DONE (v2.125.5)

**Problem:** TTS generation is CPU-bound (or waits on an external TTS API). It currently runs on the async event loop, blocking other requests during generation.

**Fix:** Move TTS generation calls inside `run_in_executor(thread_pool)` with a bounded `ThreadPoolExecutor(max_workers=2)` dedicated to TTS. This prevents a slow TTS job from stalling unrelated API responses.

**Implementation notes (learned during execution):**
- `edge_tts.Communicate.stream()` is already an **async generator** — it was NOT blocking the event loop. Only the file I/O (`read_bytes`, `write_bytes`, `mkdir`) was blocking.
- Executor created at **module level** in `main.py` (not in `startup_event`) so it's available in tests without triggering the full startup lifecycle. Plain thread pools have no async dependency.
- Deferred import pattern (`from app.main import app as _app` inside `_get_tts_executor()`) avoids the circular import chain: `news_tts_router → news_router → main.py`.
- Named helper `_write_tts_file()` used instead of lambda to avoid closure capture bugs in the thread pool.
- `run_in_executor(None, ...)` safe fallback when executor is None — uses default thread pool.

**Impact:** News article playback no longer affects trading API latency.
**Effort:** Low — 2 files changed, 13 new tests.

---

## Deferred Tech-Debt & Perf Backlog (tactical, unscheduled)

Tracked-but-deferred items from the 2026-06 code-review sweeps (#1–#5). Each was
**verified low-priority** at the time — none touch correctness, money, or security
(those were all fixed and shipped through v3.13.8). Pick these up opportunistically
when touching the relevant area; none warrant a release on their own.

**Performance (non-blocking):**
- [ ] **Lightsail CPU steal / noisy-neighbor watch item.** On 2026-06-26 after the v3.13.12/v3.13.13 loading fixes, production was healthy on hard budgets (web/trader/nginx/PostgreSQL/Redis active, memory ~2.4 GiB available, disk ~17% used, PostgreSQL ~55-66/100 connections, `/api/health` ~80 ms, small `/api/prices/batch` ~30 ms), but `vmstat` samples still showed high CPU steal (`st`) during noisy-host windows. CPU steal mainly causes sluggishness, delayed trader loops, slower restarts, and possible timeout cascades if sustained; it is not expected to directly cause wrong trades or data corruption. Current decision: stay on Lightsail for now because the app is not high-frequency and sub-second timing is not critical. Revisit only if `st` stays above ~20-30% for minutes while the app feels stuck, trader loops fall materially behind, API timeouts return, or DB/API pools start backing up again. Recommended future options, in order: keep trimming wasted trader/background work, add lightweight steal/request-latency monitoring, try stop/start or snapshot/recreate to land on quieter hardware, resize Lightsail, split web and trader onto separate hosts, or migrate to EC2 for better placement/instance control.
- [ ] Non-Coinbase portfolio paths hydrate all closed positions in Python — aggregate in SQL like the Coinbase path's `_query_closed_pnl`. *Deferred: non-Coinbase only; account is Coinbase.* `portfolio_service.py` (`get_generic_cex_portfolio`), `account_snapshot_service.py` (`get_daily_activity`)
- [ ] `get_account_balances` does a 2nd full Coinbase breakdown for `untracked_usd` — fetch once. *Deferred: cache usually warm.* `portfolio_service.py`
- [ ] Frontend: charts re-create the instance every poll tick (init once + `setData`); `batch_price` query re-keyed by a new array ref each render; broad react-query `['positions']` invalidations touch other accounts. *Deferred: micro-perf; regression risk > benefit.* `AccountValueChart.tsx`, `usePositionsData.ts`, `useBotMutations.ts`
- [ ] Unbounded loops in `get_transfer_summary` / `copy_bot_to_account` name-collision. `transfers_router.py`, `bot_crud_router.py`
- [ ] `speculative_weights_cache` / `_rebalancer_group_cache` no periodic eviction (~100 bytes/user, negligible). `coin_review_service` / `cache.invalidate` sync I/O on background/dead paths.

**Cleanup / minor:**
- [ ] Migration number collisions `077_*` ×2, `086_*` ×2. *Deferred: cosmetic; renaming applied migrations risks re-runs.* `backend/migrations/`
- [ ] Webhook rate-limit is per-token only (enumerable across IPs) — add per-IP. `webhook_router.py`
- [ ] `manual_max_dca_orders` percentage-mode base-size back-calc overstates (volume-scaled). `indicator_based.py`
- [ ] `syncAllChartsToRange` 3-param interface vs 2-param impl (silently ignored arg). `useIndicators.ts` / `useChartManagement.ts`
- [ ] Misleading BTC-fee comment. `fill_reconciler.py`
- [ ] `Position.signals` relationship-level `delete-orphan` vs the FK's SET NULL — left as-is (account-purge is the real deletion path; `db.delete(position)` isn't used on a money path). `models/trading.py`

**Concurrency (no real race; documented):**
- [ ] `rebalance_monitor._processing` / `auto_buy_monitor._pending_orders` / `multi_bot_monitor` caches — single-threaded asyncio means no torn writes; only logical-ordering windows around the admin-triggered `cleanup_caches`, off any money path. Revisit only if a symptom appears.
- [ ] `get_perps_portfolio` owner-only scope vs `list_perps_positions` accessible-member scope — functional asymmetry, not a data leak. `position_routers/perps_router.py`

## Phase 2 — Prep Work (Enabling Future Extraction)

These are **internal refactors** that don't change behavior but reduce coupling. Each one makes a future microservice extraction cheaper. Do them opportunistically — when touching a related area anyway.

### 2.1 — Domain-scoped database schemas ✅ DONE (v2.132.0)

**Problem:** All tables are in the `public` schema. There's no isolation between trading, social, content, and reporting data. A microservice extraction would require a data migration and cross-schema foreign keys.

**Fix:** Introduce PostgreSQL schemas as namespaces (not separate databases yet). Group tables:
```
schema: auth       → User, Group, Role, Permission, TrustedDevice, EmailVerificationToken,
                     RevokedToken, ActiveSession, RateLimitAttempt (12 tables)
schema: trading    → Account, Bot, BotProduct, BotTemplate, BotTemplateProduct, Position,
                     Trade, Signal, PendingOrder, OrderHistory, BlacklistedCoin (11 tables)
schema: reporting  → AccountValueSnapshot, MetricSnapshot, PropFirmState,
                     PropFirmEquitySnapshot, ReportGoal, ExpenseItem, GoalProgressSnapshot,
                     ReportSchedule, ReportScheduleGoal, Report, AccountTransfer, Donation (12 tables)
schema: social     → Friendship, FriendRequest, BlockedUser, GameResult, GameResultPlayer,
                     GameHistoryVisibility, GameHighScore, Tournament, TournamentPlayer,
                     TournamentDeleteVote, ChatChannel, ChatChannelMember, ChatMessage,
                     ChatMessageReaction (14 tables)
schema: content    → AIProviderCredential, NewsArticle, VideoArticle, ContentSource,
                     UserSourceSubscription, ArticleTTS, UserVoiceSubscription,
                     UserArticleTTSHistory, UserContentSeenStatus (9 tables)
schema: system     → Setting, MarketData, AIBotLog, ScannerLog, IndicatorLog (5 tables)
```

Cross-schema foreign keys work in PostgreSQL (`schema_a.table.column → schema_b.table.column`). This is not a breaking change — it's a rename migration. But it makes future extraction obvious: each schema becomes a service's database.

**Implementation notes (learned during execution):**
- Migration `068_domain_schemas.py`: `CREATE SCHEMA IF NOT EXISTS` × 6, then `ALTER TABLE public.X SET SCHEMA Y` for all 63 tables. Idempotent — checks `information_schema.tables WHERE table_schema = 'public'` before each move. PostgreSQL-only (SQLite: no-op).
- All 7 model files updated with `{'schema': 'name'}` as the last element of `__table_args__`. Models with existing `UniqueConstraint`/`Index` constraints merge the dict into the tuple: `(UniqueConstraint(...), {'schema': 'x'})`.
- Junction `Table()` objects in `auth.py` (`user_groups`, `group_roles`, `role_permissions`): `schema="auth"` passed as a keyword argument directly to `Table()`, not via `__table_args__`.
- Cross-schema FK strings updated across all model files: `ForeignKey("users.id")` → `ForeignKey("auth.users.id")`, `ForeignKey("accounts.id")` → `ForeignKey("trading.accounts.id")`, `ForeignKey("bots.id")` → `ForeignKey("trading.bots.id")` etc. ~45 FK strings changed total.
- `setup.py`: `CREATE SCHEMA IF NOT EXISTS` for all 6 schemas executed before `Base.metadata.create_all()` on fresh PostgreSQL installs.
- `database.py`: `connect_args = {"options": "-csearch_path=auth,trading,reporting,social,content,system,public"}` added to PostgreSQL engine kwargs for ad-hoc psql compatibility.
- `GRANT USAGE ON SCHEMA` + `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES` executed per schema for `zenithgrid_app` role.
- **FK OID semantics**: PostgreSQL stores FK constraints by OID, not name. Moving a table to a new schema preserves all existing FK constraints — no drop/recreate needed.
- Tests: `TestSchemaAssignments` (DB-level, queries `information_schema.tables`, PostgreSQL-only via `pytestmark`) + `TestSQLAlchemySchemaMetadata` (ORM-level, checks `__table__.schema` and FK `target_fullname` values). Total 40 tests.
- `conftest.py` `db_sync_conn` fixture uses `importlib.util.spec_from_file_location` to load `db_utils.py` by absolute path — avoids `tests/migrations/__init__.py` shadowing the real `backend/migrations/` package.

**Impact:** Zero runtime impact. Dramatically simplifies future extraction — each schema becomes a service's database.
**Effort:** Medium — 9 files changed (7 model files, migration, setup.py, database.py), 40 new tests.

---

### 2.2 — Service abstraction layer (ServiceRegistry pattern) ✅ DONE (v2.131.0)

**Problem:** Routers import services directly as module-level functions. There's no seam to swap a local service for a remote API call without changing router code.

**Fix:** Introduce a thin `ServiceRegistry` (a simple dataclass or `contextvar`) that routers receive via `Depends()`. Today it returns the local implementation; tomorrow it could return an HTTP client to a remote service.

```python
# Today:
from app.services.news_fetch_service import get_latest_articles
articles = await get_latest_articles(db, user_id)

# After:
from app.registry import services
articles = await services.news.get_latest_articles(user_id)
# services.news is either LocalNewsFetchService or RemoteNewsFetchClient
```

This doesn't need to happen everywhere at once — do it when you touch a service. Start with content and social (the easiest extraction candidates).

**Implementation notes (learned during execution):**
- `app/registry.py` — `ServiceRegistry` dataclass holding four abstraction singletons: `event_bus`, `broadcast` (BroadcastBackend), `rate_limiter` (RateLimitBackend), `credentials` (CredentialsProvider). Module-level `_default_registry` populated at import time with today's in-process implementations.
- `get_registry()` FastAPI dependency returns `_default_registry`. Routers receive all four backends via a single `Depends(get_registry)` injection instead of importing singletons directly.
- The registry is the Phase 3 swap point: replacing `_default_registry` at startup switches all four backends simultaneously (NATS, Redis, remote credentials service) with no router changes.
- Zero behavior change — all fields hold the same local implementations already in use.

**Impact:** Zero runtime impact. Single swap point for all four service backends in Phase 3.
**Effort:** Low — single file addition (`app/registry.py`).

---

### 2.3 — Introduce an internal event bus ✅ DONE (v2.127.0)

**Problem:** All inter-service coordination goes through direct database queries. When an order fills, the bot monitor queries Position directly, the reconciliation monitor queries Trade directly, the report scheduler queries Goal directly. There's no event stream — everything polls.

**Fix:** Add a lightweight in-process event bus (not Kafka — just a `dict[str, list[Callable]]` or use `asyncio.Queue`). Publish domain events:

```python
await event_bus.publish("order.filled", {"position_id": ..., "amount": ..., "price": ...})
await event_bus.publish("bot.stopped", {"bot_id": ..., "reason": ...})
await event_bus.publish("goal.achieved", {"goal_id": ..., "user_id": ...})
```

Services subscribe to events they care about. Today the bus is in-process. When you extract a service, you swap the in-process bus for NATS or Redis Pub/Sub — **no subscriber code changes**.

**Implementation notes (learned during execution):**
- `app/event_bus.py` — `InProcessEventBus` with `asyncio.create_task()` for fire-and-forget dispatch; `_safe_call()` isolates handler exceptions; module-level singleton `event_bus`.
- Topic constants: `ORDER_FILLED`, `POSITION_OPENED`, `POSITION_CLOSED`, `BOT_STARTED`, `BOT_STOPPED`, `GOAL_ACHIEVED` — namespaced strings (map to NATS subjects in Phase 3 unchanged).
- Payload dataclasses: `OrderFilledPayload`, `PositionOpenedPayload`, `PositionClosedPayload`, `BotStartedPayload`, `BotStoppedPayload`.
- **Best-effort publisher pattern**: all `event_bus.publish()` calls at the 5 active call sites (buy_executor, sell_executor, limit_order_monitor ×2, bot_control_router ×2) are wrapped in `try/except` — a bus failure never breaks the trade path.
- Subscribers wired in `_wire_event_bus_subscribers()` called from `startup_event()` in `main.py`. The `ORDER_FILLED` subscriber triggers scheduler jobs (`job.modify(next_run_time=datetime.utcnow())`) to avoid poll delay after fills.
- Future swap: replace `event_bus = InProcessEventBus()` singleton assignment in startup with a NATS/Redis implementation — no publisher or subscriber code changes needed.

**Impact:** Decouples monitors from the trading core. Enables event-driven architecture later.
**Effort:** Medium — requires identifying the key events and wiring publishers.

---

### 2.4 — Extract exchange client into a credentials service interface ✅ DONE (v2.130.0)

**Problem:** `get_exchange_client_for_account(db, account_id)` decrypts account credentials inline from the database and returns a `CoinbaseClient`. This logic is scattered across `exchange_service.py`, 3 other services, and 6+ routers. It cannot be externalized without significant surgery.

**Fix:** Wrap credential access behind a `CredentialsProvider` interface:

```python
class CredentialsProvider(Protocol):
    async def get_api_key(self, account_id: int) -> ApiCredential: ...
    async def get_exchange_client(self, account_id: int) -> ExchangeClient: ...

class LocalCredentialsProvider:
    """Current behavior — decrypt from DB."""
    ...

class RemoteCredentialsProvider:
    """Future — call a credentials microservice."""
    ...
```

Inject `CredentialsProvider` via `Depends()` or `ServiceRegistry`. Today it's always `LocalCredentialsProvider`. When you extract trading to its own service, you swap it for `RemoteCredentialsProvider`.

**Implementation notes (learned during execution):**
- `app/services/credentials_provider.py` — `CredentialsProvider` Protocol + `LocalCredentialsProvider` wrapping `get_exchange_client_for_account()`. Callers pass `db=` (existing session) or `session_maker=` (factory); when neither is provided, the default pool is used automatically.
- `RemoteCredentialsProvider` stub documents the Phase 3 HTTP API architecture and raises `NotImplementedError`.
- Wired into `ServiceRegistry` as `registry.credentials`.
- Zero behavior change — `LocalCredentialsProvider` delegates to the existing function.

**Impact:** Zero runtime impact. Makes credential management portable — one stub swap for a credentials microservice.
**Effort:** Medium — touching exchange_service.py and all callers.

---

### 2.5 — Move WebSocket fan-out to a pub/sub model ✅ DONE (seam added, swap-ready)

**Problem:** `ws_manager` is a module-level singleton that directly maps `connection_id → WebSocket`. It works on a single server. It breaks the moment you run two backend processes (which you'd need for horizontal scale).

**Fix:** Add a `BroadcastBackend` protocol in front of `ws_manager`'s fan-out methods. `ws_manager` remains the **connection registry** (connect/disconnect/sweep). `BroadcastBackend` is the **fan-out layer** only.

**Implementation notes (learned during execution):**
- `app/services/broadcast_backend.py` — single new file (no existing files changed).
- The `BroadcastBackend` protocol exposes the **ws_manager fan-out surface**, not a generic channel-based pub/sub. Methods: `broadcast(message, user_id)`, `send_to_user(user_id, message)`, `send_to_room(player_ids, message, exclude_user)`, `broadcast_order_fill(event)`. This mirrors the ws_manager interface exactly — zero behavior change.
- `@runtime_checkable` on the Protocol enables `isinstance(obj, BroadcastBackend)` checks in tests.
- `InProcessBroadcast(manager)` takes an injected `WebSocketManager` — clean for testing (no global patching needed).
- `RedisBroadcast` stub documents the Phase 3 architecture in its docstring: `PUBLISH ws:user:{user_id}` + worker-side subscription that delivers to local sockets. Raises `NotImplementedError` on all methods.
- Module singleton: `broadcast_backend: BroadcastBackend = InProcessBroadcast(ws_manager)` — same pattern as `event_bus` and `ws_manager`.
- The roadmap's original sketch (`publish(channel, message)` / `subscribe(channel)`) was adapted — a channel-based interface doesn't match the existing ws_manager call sites. The current interface is more ergonomic at the call site and maps cleanly to Redis channels in Phase 3 (one channel per user ID, one for rooms).
- **Existing call sites NOT migrated** — `ws_manager.broadcast_order_fill()` etc. still call `ws_manager` directly. Migration of call sites happens in Phase 3 when `RedisBroadcast` is implemented. The seam is in place; the swap is a one-line change to the singleton assignment.
- `broadcaster` library (mentioned in original roadmap) NOT used — it would add a dependency for zero benefit at single-process scale.

**Impact:** Seam is in place. Multi-process WebSocket fan-out is a one-file implementation away (RedisBroadcast) + singleton swap.
**Effort (to activate):** Low — implement `RedisBroadcast`, point `broadcast_backend` at it, migrate call sites to `broadcast_backend`.

---

### 2.6 — Distributed rate limiting (prep for multi-process) ✅ DONE (seam added, swap-ready)

**Problem:** Rate limiting state is stored in `RateLimitAttempt` (PostgreSQL). This works correctly today. But the middleware uses a per-request DB write, which adds latency under load.

**Fix:** Move rate limit counters to Redis (or keep them in PostgreSQL but add a Redis cache layer for the hot path). The `rate_limiters.py` module already has a clean interface — swap the storage backend.

**Implementation notes (learned during execution):**
- `app/auth_routers/rate_limit_backend.py` — `RateLimitBackend` Protocol + `PostgresRateLimitBackend` wrapping the three PostgreSQL helpers (`record_attempt`, `count_recent`, `cleanup`). Zero behavior change.
- `RedisRateLimitBackend` stub documents the Phase 3 key pattern (`INCR` + `EXPIRE` per key) and raises `NotImplementedError`.
- Wired into `ServiceRegistry` as `registry.rate_limiter`.
- **Existing call sites NOT migrated** — `rate_limiters.py` still calls the helpers directly. Migration happens when `RedisRateLimitBackend` is implemented.

**Impact (to activate):** Lower auth endpoint latency under concurrent login attempts — atomic Redis `INCR`/`EXPIRE` replaces a DB write per attempt.
**Effort (to activate):** Low — implement `RedisRateLimitBackend`, point `registry.rate_limiter` at it, migrate call sites.

---

## Phase 3 — Microservice Extraction (When Scale Demands It)

Extract services **in this order** — easiest to hardest. Each one requires Phase 2 prep work to be done first for that domain.

### Extraction 1 — Content Service

**Extract:** news_router, sources_router, news_tts_router, news_metrics_router, coin_icons_router
**Services:** news_fetch, article_content, content_refresh, news_image_cache, domain_blacklist
**Models:** NewsSource, Article, VideoSource, Video (no foreign keys into trading schema)

**Prerequisites:**
- [ ] Domain schema split (2.1) — `content` schema separated
- [ ] ServiceRegistry for content (2.2) — routers call `services.content.*`
- [ ] Event bus (2.3) — publish `article.published` instead of direct cache invalidation

**What you get:** Content fetching and TTS no longer compete with bot monitoring for CPU or DB connections. Can be scaled independently if article volume grows.

---

### Extraction 2 — Social & Gaming Service

**Extract:** friends_router, game_history_router, tournament_router, sessions_router, chat_router, display_name_router
**Services:** game_room_manager, game_ws_handler, chat_service, chat_ws_handler, friend_notifications
**Models:** Friend, GameRoom, ChatMessage, ChatGroup, ChatChannel (no foreign keys into trading schema)

**Prerequisites:**
- [ ] Domain schema split (2.1) — `social` schema separated
- [ ] WebSocket pub/sub backend (2.5) — Redis fan-out for game and chat events
- [ ] ServiceRegistry for social (2.2)
- [ ] User ID passed as a primitive (not a SQLAlchemy ORM object)

**What you get:** Game and chat logic runs separately. WebSocket connections for games don't share process memory with trading monitors.

---

### Extraction 3 — Reporting Service

**Extract:** reports_router, donations_router, account_value_router, seasonality_router (read paths)
**Services:** report_scheduler, report_data, report_ai, goal_snapshot, market_metrics, coin_review
**Models:** Goal, Expense, Report, ReportSchedule

**Prerequisites:**
- [ ] Domain schema split (2.1) — `reporting` schema separated
- [ ] Read replica (1.3) — reporting service points at read replica only
- [ ] Event bus (2.3) — subscribe to `order.filled` and `bot.stopped` events instead of querying Position directly
- [ ] ServiceRegistry for reporting (2.2)

**What you get:** Heavy aggregate queries are fully isolated. Report AI generation (slow, external API) doesn't affect trading.

---

### Extraction 4 — Portfolio & Accounting Service

**Extract:** accounts_router, transfers_router, account_router, account_value_router (write paths)
**Services:** portfolio_service, auto_buy_monitor, rebalance_monitor, transfer_sync, account_snapshot, dex_wallet_service
**Models:** Account, Transfer, AccountValueHistory

**Prerequisites:**
- [ ] CredentialsProvider interface (2.4) — exchange client decoupled from inline DB queries
- [ ] Domain schema split (2.1) — `portfolio` schema separated
- [ ] Event bus (2.3) — subscribe to `order.filled` to update balances
- [ ] ServiceRegistry for portfolio (2.2)

**What you get:** Portfolio rebalancing and auto-buy logic run independently. Exchange client credential management is centralized.

**Note:** This is also where you'd introduce a **credentials microservice** — a hardened vault-like service that holds decrypted API keys and issues short-lived signed tokens to the trading service. Required for proper multi-tenant security at scale.

---

### Extraction 5 — Auth Service (Required for All Above)

**Extract:** auth_core_router, mfa_totp_router, mfa_email_router, email_verify_router, password_router, device_trust_router, rate_limiters
**Services:** email service, encryption, token validation
**Models:** User, Session, RevokedToken, DeviceTrust, RateLimitAttempt

**This must happen before any other extraction** because every service needs a way to validate tokens without hitting the main monolith's DB. Options:

1. **Shared JWT secret** — All services validate the JWT locally (no auth service call per request). Token revocation doesn't propagate instantly (acceptable for most use cases).
2. **Auth service API** — Services call `/auth/validate` on the auth service per request. Adds latency but supports instant revocation.
3. **OAuth2 / OIDC** — Full standards-based approach. Most portable. Most complex to implement.

**Recommended approach:** Start with option 1 (shared JWT secret across services). Upgrade to option 2 or 3 only if instant revocation becomes a security requirement.

**Prerequisites:**
- [ ] Distributed rate limiting (2.6) — Redis backend
- [ ] Domain schema split (2.1) — `auth` schema separated
- [ ] User passed as primitive ID everywhere (not ORM object)

---

### Extraction 6 — Trading Core (Last)

**Extract:** bot_crud_router, bot_control_router, position_query_router, position_actions_router, position_limit_orders_router, perps_router, trading_router, blacklist_router
**Services:** grid_trading, limit_order_monitor, order_reconciliation, multi_bot_monitor, perps_monitor
**Models:** Bot, Position, Order, Trade, PendingOrder, Indicator*, Decision*, Signal*

**This is the hardest extraction.** The trading core is the heart of the application — it has the most cross-cutting dependencies, the tightest real-time constraints, and the most risk if broken.

**Prerequisites (all of the above, plus):**
- [ ] Internal event bus upgraded to NATS or Redis Streams — order fills must be publishable to portfolio and reporting services
- [ ] Exchange client extracted via CredentialsProvider (2.4)
- [ ] Auth service validated (Extraction 5)
- [ ] Separate `trading` PostgreSQL database — no more cross-schema JOINs

**Why do this last?** If the trading service goes down, nothing else matters. Get everything else working independently first so the trading core can run lean and focused.

---

## Decision Triggers — When to Move to Each Phase

| Trigger | Action |
|---|---|
| DB pool exhaustion happens again | Phase 1.1 (tier tasks) + Phase 1.3 (read pool split) |
| Event loop latency causes missed bot signals | Phase 1.1 (separate task tiers) immediately |
| Server memory > 800MB consistently | Phase 1.2 (APScheduler) — move batch tasks off main process |
| Users > 500 concurrent | Phase 2.5 (WebSocket pub/sub) — single process WebSocket won't scale |
| Users > 1,000 or need horizontal scale | Phase 2 complete + begin Phase 3 extractions |
| Security requirement: instant token revocation | Phase 2.6 (Redis rate limiting) + Auth Service (Extraction 5) |
| Trading volume justifies dedicated infra | Phase 3 in full, Trading Core last |

---

## Infrastructure Required Per Phase

### Phase 1 — No new infrastructure
All changes are code-only. Already on the `fedora.local` host with PostgreSQL in `postgres-box`.

### Phase 2 — Add Redis
Redis is the only new dependency for Phase 2. It enables:
- WebSocket pub/sub (2.5)
- Distributed rate limiting (2.6)
- APScheduler job store (1.2) — optional, SQLAlchemy store also works

A single Redis/Valkey instance on the same `fedora.local` host is sufficient at current scale.

### Phase 3 — Container orchestration + service mesh
Each extracted service runs as its own process (Docker container). You'll need:
- **Container runtime**: Docker Compose (dev), ECS Fargate or Kubernetes (prod)
- **API gateway**: Kong, Traefik, or AWS API Gateway for routing and auth validation
- **Message broker**: NATS or Redis Streams for inter-service events
- **Service discovery**: Built into ECS or Kubernetes
- **Per-service databases**: PostgreSQL schemas promoted to separate RDS instances
- **Secrets manager**: AWS Secrets Manager or Vault for credentials service (Extraction 4)

At the point you're doing Phase 3, you're likely also moving off t2.micro. The natural upgrade path is:
```
t2.micro (now)
  → larger self-hosted Fedora box or VM (more RAM/CPU), handles ~1K users
  → managed PostgreSQL plus larger app host, handles ~5K users
  → ECS Fargate (per-service containers) — scales on demand
```

---

## What NOT to Do

- **Don't extract Trading Core first.** It's the most coupled, the most critical, and the riskiest. Extract the safe things first and let the trading core run cleanly.
- **Don't add Kubernetes prematurely.** Docker Compose + a second EC2 instance is sufficient until you need more than 2 replicas.
- **Don't split the database before the schemas are clean.** Domain schema separation (2.1) must come before database separation. Cross-database JOINs are painful.
- **Don't build a custom event bus.** Use NATS (simple, fast, battle-tested) or Redis Streams. The in-process bus from Phase 2 is a bridge, not a destination.
- **Don't try to do Phase 3 all at once.** Each extraction is a mini-project. Plan for 2–4 weeks per service extraction at real production quality.
