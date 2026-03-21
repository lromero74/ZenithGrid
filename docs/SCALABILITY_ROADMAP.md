# ZenithGrid — Scalability & Microservices Roadmap

**Written:** 2026-03-21
**Context:** App is a layered monolith running on EC2 t2.micro (1 vCPU, 1GB RAM, ~200 users). Good internal structure, tight coupling at the data layer.

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

---

## Phase 1 — Immediate Wins (Do Now)

These changes reduce resource contention and improve reliability **without any architecture change**. They address the symptoms already seen (DB pool exhaustion, event loop contention under load).

### 1.1 — Tier the 27 background tasks by priority ✅ DONE (v2.125.8)

**Problem:** All 27 tasks share the same asyncio event loop. A slow news fetch or weekly coin review competes with bot monitoring and order fills for CPU time. The 30-second DB pool timeout that appeared when saving a bot is a symptom of this.

**Fix:** Assign tasks to priority tiers. Tier 1 runs on the main trading event loop. Tier 2 and 3 run on a separate `asyncio` event loop in a dedicated daemon thread with its own smaller DB connection pool.

```
Tier 1 — Real-time (main event loop, current behavior):
  MultiBotMonitor          10s interval
  LimitOrderMonitor        10s interval + 5m sweep
  OrderReconciliationMon   60s interval
  PropGuardMonitor         30s interval
  PerpsMonitor             60s interval
  MissingOrderDetector     5m interval
  MemoryCacheCleanup       5m interval  ← stays on main loop (touches shared in-memory state)

Tier 2 — Near-real-time (secondary loop, tolerate 1–2s delay):
  AutoBuyMonitor           continuous
  RebalanceMonitor         continuous
  TransferSync             daily, starts after 20m
  AccountSnapshotService   daily, starts after 5m
  BanMonitor               daily
  ReportScheduler          15m interval

Tier 3 — Batch (secondary loop, can lag minutes):
  ContentRefreshService    30m / 60m intervals (news, videos)
  DomainBlacklistService   weekly
  DebtCeilingMonitor       weekly
  TradingPairMonitor       daily
  CoinReviewScheduler      7 day interval
  DecisionLogCleanup       daily
  FailedConditionCleanup   6h interval
  FailedOrderCleanup       6h interval
  RevokedTokenCleanup      daily
  SessionCleanup           daily
  RateLimitCleanup         hourly
  ReportCleanup            weekly
  ChangelogCacheRebuild    startup only (synchronous, stays on main startup path — too fast to move)
```

**Implementation notes (learned during execution):**
- New module `app/secondary_loop.py` owns: loop lifecycle (`start_secondary_loop`, `stop_secondary_loop`), DB engine creation bound to the secondary loop, `schedule(coro)` helper using `asyncio.run_coroutine_threadsafe`, and `get_secondary_session_maker()`.
- **asyncpg is event-loop bound**: DB connections bind to the loop that created the engine. Secondary loop creates its own `create_async_engine` instance INSIDE the loop (via `asyncio.run_coroutine_threadsafe(_init_secondary_engine(), loop).result()`). Main and secondary engines are completely independent.
- **Pool budget**: Main (size=8, overflow=4=12) + Read (size=4, overflow=2=6) + Secondary (size=3, overflow=2=5) = 23 max vs `max_connections=25`. Tight but within limits.
- **Session maker injection pattern**: Coroutine-style tasks accept `session_maker=None` with `sm = session_maker or _default_session_maker` fallback. Class-based monitors get `set_session_maker(sm)` / `_get_sm()` methods. Backwards-compatible — tests and direct calls still work without injection.
- **`coin_review_service.py` required threading session_maker through 5 layers**: `run_coin_review_scheduler` → `_get_last_review_timestamp`, `run_weekly_review` → `get_tracked_coins`, `update_coin_statuses` → `get_coinbase_client_from_db`. All now have `session_maker=None` parameter.
- **`MemoryCacheCleanup` stays on main loop**: It touches in-memory state shared with request handlers (`auto_buy_monitor._account_timers`, `rebalance_monitor._account_timers`, rate-limit dicts). Moving it to the secondary loop would create cross-thread races.
- **`ContentRefreshService`, `DomainBlacklistService`, `DebtCeilingMonitor` do NOT use `async_session_maker`** (HTTP-only services) — no `set_session_maker()` needed, just `schedule(service.start())`.
- **Shutdown**: `stop_secondary_loop()` stops the loop which cancels all running Tier 2/3 coroutines. Individual `_cancel_task()` calls for Tier 2/3 removed from `shutdown_event()`. Module-level task globals reduced from 14 to 4 (Tier 1 only).
- **`build_changelog_cache()` stays synchronous on main startup path**: It runs `git log` (< 1 second), is startup-only, and not a loop — no benefit to moving it.

**Impact:** Trading monitors get CPU/DB pool priority. Slow tasks no longer block order execution. Main pool's 12 connections reserved for Tier 1 + API request handlers.
**Effort:** Medium — 11 files changed, 14 new tests.

---

### 1.2 — Move cleanup and batch jobs to APScheduler

**Problem:** All 27 tasks are hand-rolled `asyncio.sleep()` loops. There's no retry logic, no error isolation, no visibility into task health. A crashing cleanup task silently dies.

**Fix:** Move all Tier 2 and Tier 3 tasks to [APScheduler](https://apscheduler.readthedocs.io/) (already available in most Python setups). APScheduler gives you:
- Cron-style scheduling (not sleep-loop drift)
- Per-job error handlers
- Job history / next-run visibility (useful for admin panel)
- Easy migration to distributed backends later (Redis, SQLAlchemy store)

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

## Phase 2 — Prep Work (Enabling Future Extraction)

These are **internal refactors** that don't change behavior but reduce coupling. Each one makes a future microservice extraction cheaper. Do them opportunistically — when touching a related area anyway.

### 2.1 — Domain-scoped database schemas

**Problem:** All tables are in the `public` schema. There's no isolation between trading, social, content, and reporting data. A microservice extraction would require a data migration and cross-schema foreign keys.

**Fix:** Introduce PostgreSQL schemas as namespaces (not separate databases yet). Group tables:
```
schema: trading    → Bot, Position, Order, Trade, PendingOrder, Indicator*, Decision*, Signal*, BlacklistedPair
schema: portfolio  → Account, Transfer, AccountValueHistory, ExchangeBalance
schema: reporting  → Goal, Expense, Report, ReportSchedule
schema: social     → Friend, GameRoom, ChatMessage, ChatGroup, ChatChannel
schema: content    → NewsSource, Article, VideoSource, Video
schema: auth       → User, Session, RevokedToken, DeviceTrust, RateLimitAttempt
schema: system     → BanLog, CoinMetadata, DisplayName
```

Cross-schema foreign keys work in PostgreSQL (`schema_a.table.column → schema_b.table.column`). This is not a breaking change — it's a rename migration. But it makes future extraction obvious: each schema becomes a service's database.

**Impact:** Zero runtime impact. Dramatically simplifies future extraction.
**Effort:** Medium — requires a careful migration (rename all table references, update SQLAlchemy `__table_args__`).

---

### 2.2 — Service abstraction layer (ServiceRegistry pattern)

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

**Impact:** Zero runtime impact. Creates an explicit service boundary.
**Effort:** Low per service, high to do everywhere at once — do it incrementally.

---

### 2.3 — Introduce an internal event bus

**Problem:** All inter-service coordination goes through direct database queries. When an order fills, the bot monitor queries Position directly, the reconciliation monitor queries Trade directly, the report scheduler queries Goal directly. There's no event stream — everything polls.

**Fix:** Add a lightweight in-process event bus (not Kafka — just a `dict[str, list[Callable]]` or use `asyncio.Queue`). Publish domain events:

```python
await event_bus.publish("order.filled", {"position_id": ..., "amount": ..., "price": ...})
await event_bus.publish("bot.stopped", {"bot_id": ..., "reason": ...})
await event_bus.publish("goal.achieved", {"goal_id": ..., "user_id": ...})
```

Services subscribe to events they care about. Today the bus is in-process. When you extract a service, you swap the in-process bus for NATS or Redis Pub/Sub — **no subscriber code changes**.

**Impact:** Decouples monitors from the trading core. Enables event-driven architecture later.
**Effort:** Medium — requires identifying the key events and wiring publishers.

---

### 2.4 — Extract exchange client into a credentials service interface

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

**Impact:** Zero runtime impact. Makes credential management portable.
**Effort:** Medium — touching exchange_service.py and all callers.

---

### 2.5 — Move WebSocket fan-out to a pub/sub model

**Problem:** `ws_manager` is a module-level singleton that directly maps `connection_id → WebSocket`. It works on a single server. It breaks the moment you run two backend processes (which you'd need for horizontal scale).

**Fix:** Add a Redis Pub/Sub adapter behind a `BroadcastBackend` interface:

```python
class BroadcastBackend(Protocol):
    async def publish(self, channel: str, message: dict): ...
    async def subscribe(self, channel: str) -> AsyncIterator[dict]: ...

class InProcessBroadcast:
    """Current behavior — asyncio.Queue per connection."""
    ...

class RedisBroadcast:
    """Future — Redis pub/sub for multi-process fan-out."""
    ...
```

[`broadcaster`](https://github.com/encode/broadcaster) is a lightweight library that already implements this pattern and works with FastAPI/Starlette WebSockets.

**Impact:** Enables multi-process WebSocket servers. Required for any horizontal scale.
**Effort:** Medium — isolated to `ws_manager.py` and the three WebSocket endpoint handlers.

---

### 2.6 — Distributed rate limiting (prep for multi-process)

**Problem:** Rate limiting state is stored in `RateLimitAttempt` (PostgreSQL). This works correctly today. But the middleware uses a per-request DB write, which adds latency under load.

**Fix:** Move rate limit counters to Redis (or keep them in PostgreSQL but add a Redis cache layer for the hot path). The `rate_limiters.py` module already has a clean interface — swap the storage backend.

**Impact:** Lower auth endpoint latency under concurrent login attempts.
**Effort:** Low — isolated to `rate_limiters.py`.

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
All changes are code-only. Already on EC2 + PostgreSQL.

### Phase 2 — Add Redis
Redis is the only new dependency for Phase 2. It enables:
- WebSocket pub/sub (2.5)
- Distributed rate limiting (2.6)
- APScheduler job store (1.2) — optional, SQLAlchemy store also works

A single `redis-server` on the same EC2 instance is sufficient at current scale.

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
  → t3.small (more RAM, burst CPU) — ~$15/mo, handles ~1K users
  → t3.medium + RDS PostgreSQL — ~$50/mo, handles ~5K users
  → ECS Fargate (per-service containers) — scales on demand
```

---

## What NOT to Do

- **Don't extract Trading Core first.** It's the most coupled, the most critical, and the riskiest. Extract the safe things first and let the trading core run cleanly.
- **Don't add Kubernetes prematurely.** Docker Compose + a second EC2 instance is sufficient until you need more than 2 replicas.
- **Don't split the database before the schemas are clean.** Domain schema separation (2.1) must come before database separation. Cross-database JOINs are painful.
- **Don't build a custom event bus.** Use NATS (simple, fast, battle-tested) or Redis Streams. The in-process bus from Phase 2 is a bridge, not a destination.
- **Don't try to do Phase 3 all at once.** Each extraction is a mini-project. Plan for 2–4 weeks per service extraction at real production quality.
