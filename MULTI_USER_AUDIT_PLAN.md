# Multi-User Data Isolation & Database Normalization Plan

**Status**: In Progress
**Created**: 2026-02-16
**Last Updated**: 2026-02-16
**Goal**: Ensure all user-specific queries are properly scoped and the database schema is normalized.

---

## Phase 1: User-Scoped Query Fixes (Critical)

All user-facing API endpoints must filter by `current_user.id` (or the user's account IDs).

### 1.1 `get_coinbase_from_db()` Functions
| File | Status | Notes |
|------|--------|-------|
| `bot_routers/bot_crud_router.py` | DONE | Added `user_id` param, callers pass `current_user.id` |
| `bot_routers/bot_validation_router.py` | DONE | Added `user_id` param, caller passes `current_user.id` |
| `routers/account_router.py` | DONE | Already has `user_id` param, callers pass `current_user.id` |
| `routers/market_data_router.py` (`get_coinbase()`) | DONE | Falls back to public API when no creds; market data is public so user-scoping is less critical |

### 1.2 Position Endpoint Ownership Verification
| Endpoint | File | Status | Notes |
|----------|------|--------|-------|
| `GET /positions/{id}/trades` | `position_query_router.py` | DONE | Added user account ownership check |
| `GET /positions/{id}/ai-logs` | `position_query_router.py` | DONE | Added user account ownership check |
| All limit order endpoints (5) | `position_limit_orders_router.py` | DONE | Created `_get_user_position()` helper, replaced all unscoped lookups |
| `POST /positions/{id}/add-funds` | `position_manual_ops_router.py` | DONE | Added user account ownership verification |
| `PATCH /positions/{id}/notes` | `position_manual_ops_router.py` | DONE | Added user account ownership verification |

### 1.3 Portfolio / Account Queries
| Endpoint | File | Status | Notes |
|----------|------|--------|-------|
| Generic CEX portfolio | `accounts_router.py` | DONE | Removed `account_id.is_(None)` fallback; strictly scoped to `account.id` |
| CEX portfolio PnL | `accounts/portfolio_utils.py` | DONE | Removed 3 `account_id.is_(None)` fallbacks (positions, bots, closed positions) |
| Portfolio (main) | `account_router.py` | DONE | Scoped open positions, closed positions, and bot queries to `user_account_ids` |
| Dashboard stats | `system_router.py` | DONE | Scoped current position, total positions, profit, win rate to user accounts |
| Recent trades | `system_router.py` | DONE | Scoped via user position IDs |
| Bot list price pre-fetch | `bot_routers/bot_crud_router.py` | DONE | Scoped open positions query to user accounts |
| Orphan bots (NULL account_id) | Database | DONE | 4 orphan bots assigned to user 1's default account |

### 1.4 Settings Queries
| Endpoint | File | Status | Issue |
|----------|------|--------|-------|
| `GET /settings/{key}` | `settings_router.py:213` | DONE | Global settings are correct — operational config (seasonality, AI provider, pair lists) applies system-wide |
| `PUT /settings/{key}` | `settings_router.py:232` | DONE | Same — admin-level settings, not user-specific |

**Resolution**: Settings remain global. Per-user customization of approved pairs is handled via the `BlacklistedCoin` override system (`user_id` column), not the settings table. Users override *which category a coin belongs to* for themselves; the global `allowed_coin_categories` setting defines which categories are tradeable.

### 1.5 WebSocket Notifications
| Item | Status | Notes |
|------|--------|-------|
| `WebSocketManager` user-scoped connections | DONE | Stores `(websocket, user_id)` tuples, broadcasts by user |
| `broadcast_order_fill` in buy_executor | DONE | Passes `position.user_id` |
| `broadcast_order_fill` in sell_executor | DONE | Passes `position.user_id` |
| `broadcast_order_fill` in limit_order_monitor (partial fill) | DONE | Passes `position.user_id` |
| `broadcast_order_fill` in limit_order_monitor (sell) | DONE | Passes `position.user_id` |

---

## Phase 2: Paper Trading Standalone (Done)

### 2.1 Public Market Data API
| File | Status | Notes |
|------|--------|-------|
| `coinbase_api/public_market_data.py` | DONE | Created — uses Coinbase public endpoints (no auth) |
| `exchange_clients/paper_trading_client.py` | DONE | All 10 fallbacks replaced with public API calls |
| `routers/market_data_router.py` | DONE | Falls back to `PublicMarketDataClient` when no creds |

---

## Phase 3: Database Normalization Audit

### 3.1 Current Schema Review (1NF/2NF/3NF)

**Tables to audit:**

| Table | Potential Issues | Status |
|-------|-----------------|--------|
| `bots` | `strategy_config` is JSON blob — functional dependencies on bot_id. `product_ids` is JSON array. | TODO |
| `positions` | Many columns, some only apply to specific position types (perps vs spot). Pattern data is JSON. | TODO |
| `accounts` | `paper_balances` is JSON blob. `prop_firm_config` is JSON. Multiple auto_buy columns. | TODO |
| `settings` | Key-value store — no normalization issues but may need `user_id` for multi-user | TODO |
| `users` | Looks clean | TODO |
| `trades` | Looks clean | TODO |
| `news_articles` | `image_data` stores base64 blobs inline | TODO |
| `ai_bot_logs` | `context` and `thinking` are text blobs | TODO |

### 3.2 1NF Violations (Atomic Values)
- `bots.product_ids` — JSON array of product IDs. Should be a junction table `bot_products(bot_id, product_id)`.
- `bots.strategy_config` — JSON blob. Could be extracted into `bot_strategy_params` but may hurt flexibility.
- `accounts.paper_balances` — JSON blob `{"BTC": 1.0, "USD": 100000}`. Could be `paper_balances(account_id, currency, amount)`.
- `positions.pattern_data` — JSON blob for strategy-specific data.

### 3.3 2NF Violations (Partial Dependencies)
- `positions` has many columns that depend on `product_type` not the full key:
  - `leverage`, `perps_margin_type`, `liquidation_price`, `funding_fees_total` — only for perps
  - `tp_order_id`, `sl_order_id`, `tp_price`, `sl_price` — only when bracket orders are used

### 3.4 3NF Violations (Transitive Dependencies)
- `positions.btc_usd_price_at_open` and `btc_usd_price_at_close` — derived from market data at a point in time, stored for historical reference. Acceptable denormalization for performance.
- `news_articles.image_data` — derived from `original_thumbnail_url`. Should be stored in filesystem, not DB.

### 3.5 Recommended Schema Changes
1. **Add `user_id` to `settings` table** (if settings become per-user)
2. **Extract `bot_products` junction table** from `bots.product_ids` JSON
3. **Move `news_articles.image_data`** to filesystem cache (already partially done with `cached_thumbnail_path`)
4. **Consider `paper_balances` table** instead of JSON blob on accounts

**Note**: SQLite doesn't support `ALTER TABLE DROP COLUMN` (only since 3.35.0) or complex DDL. Normalization changes require careful migration planning.

---

## Phase 4: Background Services Multi-User Support

Background services (bot monitor, order execution, limit order monitor) run on restart and process ALL users. They must:
- Properly discover and process bots/positions for ALL users (not just user 1)
- Use each bot's own account credentials for API calls
- Not leak data between users in shared caches
- Route notifications to the correct user

### 4.1 Bot Monitor / Check Cycles
| Item | Status | Issue |
|------|--------|-------|
| Bot iteration | DONE | Intentionally processes ALL users' bots; each bot uses its own `account_id` for exchange client |
| Exchange client creation | DONE | `get_exchange_for_bot()` → `get_exchange_client_for_account(db, bot.account_id)` — correctly scoped per-account |
| Price cache keys | DONE | `price_{product_id}` is global — correct since prices are same for all users |
| Balance cache keys | DONE | Scoped by `account_id` suffix (e.g., `balance_eth_3`, `aggregate_btc_1`) |

### 4.2 Order Execution on Restart
| Item | Status | Issue |
|------|--------|-------|
| Pending order discovery | DONE | Limit order monitor finds ALL users' positions (correct for background service) |
| Order reconciliation | DONE | `main.py` creates fresh exchange client per position via `position.account_id` |
| Position state recovery | DONE | Bot monitor discovers all bots → recovers positions per-bot with scoped exchange clients |

### 4.3 Limit Order Monitor
| Item | Status | Issue |
|------|--------|-------|
| Position discovery | DONE | Unscoped query is correct — background service must process all users' positions |
| Exchange client per position | DONE | `main.py` creates new `LimitOrderMonitor` instance per position with correctly scoped exchange client |
| Notification routing | DONE | `broadcast_order_fill` passes `user_id` |

### 4.4 Cache Scoping
| Cache Key | Scoped? | Notes |
|-----------|---------|-------|
| `price_{product_id}` | Global (correct) | Prices are same for all users |
| `all_products` | Global (correct) | Product list same for all |
| `stats_{product_id}` | Global (correct) | Stats same for all |
| `balance_eth_{account_id}` | Per-account (correct) | Scoped by account_id suffix |
| `aggregate_btc_{account_id}` | Per-account (correct) | Scoped by account_id suffix |
| `aggregate_usd_{account_id}` | Per-account (correct) | Scoped by account_id suffix |
| `accounts_list_{account_id}` | Per-account (correct) | Scoped by account_id suffix |

---

## Phase 5: Multi-User Exchange Client Creation

Each user may have different Coinbase API credentials (or none — paper trading only). The system must:
- Never use one user's API keys for another user's operations
- Fall back to public API (not system credentials) for paper-trading-only users
- Support users with no exchange account at all (paper trading)

| Item | Status | Notes |
|------|--------|-------|
| `exchange_service.get_exchange_client_for_account()` | DONE | Takes account_id, creates client per-account, passes `account_id` to `CoinbaseClient` for cache scoping |
| Paper trading client creation | DONE | Falls back to public API, not empty CoinbaseClient; real_client gets `account_id=cex_account.id` |
| System credential fallback removal | DONE | market_data_router falls back to `PublicMarketDataClient` (no auth needed for public market data) |

---

## Completion Checklist

- [x] Phase 2: Paper trading standalone (public market data)
- [x] Phase 1.1: get_coinbase_from_db user-scoping (bot_crud, bot_validation, account_router)
- [x] Phase 1.2: Position endpoint ownership verification (trades, ai-logs, limit orders, manual ops)
- [x] Phase 1.3: Portfolio/account queries scoped (account_router, accounts_router, portfolio_utils, system_router, bot_crud_router)
- [x] Phase 1.5: WebSocket notifications user-scoped
- [x] Phase 1.4: Settings resolved — global settings correct; per-user coin overrides via BlacklistedCoin.user_id
- [ ] Phase 3: Database normalization audit and migration plan
- [x] Phase 4: Background services multi-user — cache scoped by account_id, bot monitor & limit order monitor verified correct
- [x] Phase 5: Exchange client creation audit — all paths pass account_id, paper trading uses public API fallback
