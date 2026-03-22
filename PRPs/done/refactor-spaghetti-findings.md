# PRP: Refactor All Spaghetti-Check Findings

**Feature**: Comprehensive structural refactoring — file splits, function decomposition, dependency fixes, SoC enforcement
**Created**: 2026-02-25
**One-Pass Confidence Score**: 7/10 (large scope across 15 areas; each individual area is 8-9/10)

---

## Context & Goal

### Problem
A full-codebase spaghetti-check audit identified 1 CRITICAL, 137 HIGH, and 230 MEDIUM structural findings:
- **1 bidirectional dependency** (service imports from router)
- **7 files over 1200 lines** (up to 2151 lines)
- **16 functions over 200 lines** (up to 951 lines, CC=86)
- **6 chunks of business logic in routers** (~1500 lines total)
- **3 services using HTTPException** (framework coupling)
- **88 functions with 5+ parameters** (top: 15 params)

### Solution
Execute 15 refactoring work items in dependency order. Pure structural refactoring — no behavior changes, no new features. All existing tests must continue to pass.

### Scope
- **In**: File splits, function decomposition, import fixes, parameter objects, domain exceptions
- **Out**: New features, behavior changes, test coverage expansion (tests may need import updates only)

### Execution Strategy
This PRP is designed for **phased execution** — each phase is an independent branch/commit. Execute phases sequentially (Phase 1 first — it fixes the only CRITICAL finding). Within each phase, work items are independent and can be parallelized.

---

## Phase 1: Fix CRITICAL Dependency Violation (news subsystem)

### Work Item 1: Move business logic from news_router.py into services

**Problem**: `services/news_fetch_service.py` imports ~10 helper functions from `routers/news_router.py` via deferred imports (lines 38-47, 131-138). This is a bidirectional dependency: the router also imports from the service. The helpers are business logic (fetching, storing, cleaning up) that belongs in the service layer.

**Current State**:

`news_fetch_service.py` deferred imports:
```python
# Line 38-47 (inside fetch_all_news):
from app.routers.news_router import (
    _get_source_key_to_id_map,
    cleanup_articles_with_images,
    fetch_reddit_news,
    fetch_rss_news,
    get_news_sources_from_db,
    store_article_in_db,
)

# Line 131-138 (inside fetch_all_videos):
from app.routers.news_router import (
    _get_source_key_to_id_map,
    cleanup_old_videos,
    fetch_youtube_videos,
    get_video_sources_from_db,
    store_video_in_db,
)
```

**Functions to move FROM `news_router.py` INTO services**:

| Function | Lines in news_router.py | Destination |
|----------|------------------------|-------------|
| `get_news_sources_from_db()` | 164-187 | `news_fetch_service.py` |
| `get_video_sources_from_db()` | 189-209 | `news_fetch_service.py` |
| `_get_source_key_to_id_map()` | 242-249 | `news_fetch_service.py` |
| `fetch_rss_news()` | 883-981 | `news_fetch_service.py` |
| `fetch_reddit_news()` | 771-811 | `news_fetch_service.py` |
| `fetch_youtube_videos()` | 707-762 | `news_fetch_service.py` |
| `fetch_og_meta()` | 814-874 | `news_fetch_service.py` (used by fetch_rss_news) |
| `fetch_og_image()` | 877-880 | `news_fetch_service.py` (wrapper around fetch_og_meta) |
| `store_article_in_db()` | 369-409 | `news_fetch_service.py` |
| `store_video_in_db()` | 464-500 | `news_fetch_service.py` |
| `cleanup_articles_with_images()` | 1324-1437 | `news_fetch_service.py` |
| `cleanup_old_videos()` | 573-630 | `news_fetch_service.py` |

**Functions that STAY in `news_router.py`** (they're used by endpoint handlers):
- `get_allowed_article_domains()` (93-121) — used by `get_article_content()` endpoint
- `get_source_scrape_policy()` (124-162) — used by `get_article_content()` endpoint
- `get_all_sources_from_db()` (212-239) — used by endpoints (calls get_news/video_sources_from_db, update to import from service)
- `get_articles_for_user()` (257-334) — query helper for endpoints
- `get_articles_from_db()` (337-366) — query helper for endpoints
- `get_seen_content_ids()` (412-422) — query helper for endpoints
- `article_to_news_item()` (425-456) — response formatter
- `get_videos_for_user()` (503-552) — query helper for endpoints
- `get_videos_from_db_list()` (555-570) — query helper for endpoints
- `video_to_item()` (633-653) — response formatter
- `get_videos_from_db()` (656-699) — query helper
- `get_news_from_db()` (990-1048) — query helper
- `_mark_content_fetch_failed()` (1504-1517) — used by get_article_content
- `get_article_content()` endpoint (1521-1795)
- All HTTP endpoint handlers

**Steps**:
1. Move the 12 functions listed above from `news_router.py` to `news_fetch_service.py`
2. Remove the deferred imports from `news_fetch_service.py` — the functions are now local
3. Update `news_router.py` to import from `news_fetch_service` where needed:
   - `get_all_sources_from_db()` calls `get_news_sources_from_db()` and `get_video_sources_from_db()` — update to `from app.services.news_fetch_service import get_news_sources_from_db, get_video_sources_from_db`
   - `cleanup_cache()` endpoint calls `cleanup_articles_with_images()` and `cleanup_old_videos()` — update import
   - `fetch_all_news()` wrapper at line 984-987 can be deleted entirely (it was just a deferred import wrapper)
4. Update any other files that import these functions from `news_router`:
   - Search: `from app.routers.news_router import` across entire codebase
   - Search: `from app.services.news_fetch_service import` to verify no remaining circular refs
5. Verify: `cd backend && ./venv/bin/python3 -c "from app.routers.news_router import router"` — no circular import crash
6. Verify: `cd backend && ./venv/bin/python3 -c "from app.services.news_fetch_service import fetch_all_news"` — clean import

**Dependencies for moved functions**:
- `fetch_rss_news` uses: `feedparser`, `aiohttp`, `NewsItem` (from `app.news_data`), `fetch_og_meta`
- `fetch_reddit_news` uses: `aiohttp`, `NewsItem`
- `fetch_youtube_videos` uses: `aiohttp`, `feedparser`, `VideoItem` (from `app.news_data`)
- `store_article_in_db` uses: `NewsArticle` model, `download_and_save_image` from `news_image_cache`
- `store_video_in_db` uses: `VideoArticle` model
- `cleanup_articles_with_images` uses: `NewsArticle`, `ArticleTTS` models, `NEWS_IMAGES_DIR`
- `cleanup_old_videos` uses: `VideoArticle` model, `ContentSource` model
- `get_news_sources_from_db` / `get_video_sources_from_db` use: `ContentSource` model, `async_session_maker`
- `_get_source_key_to_id_map` uses: `ContentSource` model, `async_session_maker`

All these dependencies are models, utilities, and external libraries — no router imports needed.

**Expected result**: `news_router.py` drops from ~1796 to ~900 lines. `news_fetch_service.py` grows from ~201 to ~900 lines. Bidirectional dependency eliminated.

**Lint**: `flake8 --max-line-length=120 backend/app/routers/news_router.py backend/app/services/news_fetch_service.py`

---

## Phase 2: Extract Business Logic from Routers

### Work Item 2: Extract account_router.py business logic to portfolio_service.py

**Problem**: `account_router.py` contains ~820 lines of pure business logic across 3 functions that should live in `services/portfolio_service.py`.

**Functions to extract**:

| Function | Lines | Current Location | Destination |
|----------|-------|-----------------|-------------|
| `get_portfolio()` body logic | 326-718 (394 lines) | `account_router.py` | `portfolio_service.py` as `get_account_portfolio_data()` |
| `_run_portfolio_conversion()` | 730-978 (248 lines) | `account_router.py` | `portfolio_service.py` as `run_portfolio_conversion()` |
| `get_balances()` body logic | 110-283 (175 lines) | `account_router.py` | `portfolio_service.py` as `get_account_balances()` |

**Pattern**: The router endpoint becomes a thin wrapper:
```python
@router.get("/portfolio")
async def get_portfolio(
    force_fresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_account_portfolio_data(db, current_user, force_fresh)
```

**`portfolio_service.py` already exists** (577 lines) with `get_cex_portfolio()`, `get_dex_portfolio()`, `get_generic_cex_portfolio()`. The new functions orchestrate these existing ones — they're the "controller" logic that calls the existing service functions plus does caching, paper trading, and aggregation.

**Steps**:
1. Read `account_router.py` fully to understand the 3 functions' dependencies
2. Create new async functions in `portfolio_service.py` with the extracted logic
3. Update `account_router.py` endpoints to call the service functions
4. Delete helper functions from `account_router.py` that are no longer needed
5. Update any imports

**Expected result**: `account_router.py` drops from ~1035 to ~400 lines.

**Lint**: `flake8 --max-line-length=120 backend/app/routers/account_router.py backend/app/services/portfolio_service.py`

---

### Work Item 3: Extract news_metrics_router.py fetch functions to market_metrics_service.py

**Problem**: `news_metrics_router.py` (1106 lines) has ~700 lines of `fetch_*` functions that call external APIs (Treasury, FRED, CoinGecko, mempool.space, blockchain.info, Alternative.me, Coinbase). These are service-layer data fetching functions, not router logic.

**Functions to extract** (create new `backend/app/services/market_metrics_service.py`):

| Function | Lines | External API |
|----------|-------|-------------|
| `get_shared_session()` | 84-89 | N/A (session management) |
| `record_metric_snapshot()` | 97-108 | None (DB write) |
| `prune_old_snapshots()` | 111-127 | None (DB cleanup) |
| `fetch_btc_block_height()` | 135-167 | blockchain.info |
| `fetch_us_debt()` | 170-315 | Treasury + FRED |
| `fetch_fear_greed_index()` | 318-353 | Alternative.me |
| `fetch_btc_dominance()` | 356-393 | CoinGecko |
| `fetch_altseason_index()` | 396-459 | CoinGecko |
| `fetch_stablecoin_mcap()` | 462-516 | CoinGecko |
| `fetch_mempool_stats()` | 519-567 | mempool.space |
| `fetch_hash_rate()` | 570-618 | mempool.space |
| `fetch_lightning_stats()` | 621-657 | mempool.space |
| `fetch_ath_data()` | 660-711 | CoinGecko |
| `fetch_btc_rsi()` | 714-774 | Coinbase |

**What stays in news_metrics_router.py**: The 15 endpoint handlers (lines 783-1105) become thin wrappers that import and call the service functions.

**Steps**:
1. Create `backend/app/services/market_metrics_service.py`
2. Move all `fetch_*` functions + `get_shared_session` + `record_metric_snapshot` + `prune_old_snapshots`
3. Move cache-related imports (`save_*_cache`, `load_*_cache`) to the new service
4. Update `news_metrics_router.py` to import from the service
5. The cache data structures (`_debt_cache`, `_cache_timestamps`, etc.) move with the functions

**Expected result**: `news_metrics_router.py` drops from ~1106 to ~400 lines. New `market_metrics_service.py` ~750 lines.

**Lint**: `flake8 --max-line-length=120 backend/app/routers/news_metrics_router.py backend/app/services/market_metrics_service.py`

---

### Work Item 4: Extract accounts_router.py business logic to services

**Problem**: `accounts_router.py` (1132 lines) has 3 functions with significant business logic.

**Functions to extract**:

| Function | Lines | Destination |
|----------|-------|-------------|
| `_validate_prop_firm_config()` | 52-92 | `services/account_service.py` (new) |
| `create_account()` body (encryption, connectivity test) | 376-525 | `services/account_service.py` |
| `get_account_portfolio()` body | 831-946 | Already calls `portfolio_service` — simplify to thin wrapper |

**Steps**:
1. Create `backend/app/services/account_service.py`
2. Move `_validate_prop_firm_config()` → `validate_prop_firm_config()`
3. Extract the create_account business logic (encryption, exchange client testing, default account setup) into `create_exchange_account()` in the service
4. Simplify `get_account_portfolio()` endpoint — it already delegates to `portfolio_service` but has ~122 lines of type-routing logic. Extract to `portfolio_service.get_portfolio_for_account()`
5. Update imports

**Expected result**: `accounts_router.py` drops from ~1132 to ~700 lines.

---

### Work Item 5: Split auth_router.py into sub-routers

**Problem**: `auth_router.py` is 2151 lines — the largest file in the codebase. It contains logically separate endpoint groups.

**Target structure** (follows existing bot_routers/position_routers pattern):
```
backend/app/auth_routers/
├── __init__.py              # Empty (sub-routers imported by parent)
├── schemas.py               # All Pydantic models (Lines 288-413)
├── helpers.py               # Shared helpers: hash_password, verify_password, create_*_token,
│                            #   decode_device_trust_token, _parse_device_name, _geolocate_ip,
│                            #   _build_user_response, _create_device_trust, get_user_by_email
│                            #   (Lines 415-610)
├── rate_limiters.py         # Rate limiting dicts + check functions (Lines 56-286)
├── auth_core_router.py      # login, refresh, logout, register, /me, change-password (Lines 617-957)
├── email_verify_router.py   # verify-email, resend-verification, verify-email-code (Lines 1078-1268)
├── password_router.py       # forgot-password, reset-password (Lines 1270-1386)
├── mfa_totp_router.py       # mfa/setup, verify-setup, disable, verify (Lines 1473-1694)
├── mfa_email_router.py      # mfa/verify-email-code, verify-email-link, email/enable, email/disable,
│                            #   resend-email (Lines 1702-2042)
├── device_trust_router.py   # mfa/devices list, revoke, revoke-all (Lines 2050-2151)
└── preferences_router.py    # accept-terms, preferences/* (Lines 1394-1465)
```

**Parent aggregator** (update existing `auth_router.py` to become thin):
```python
from fastapi import APIRouter
from app.auth_routers.auth_core_router import router as core_router
from app.auth_routers.email_verify_router import router as email_router
from app.auth_routers.password_router import router as password_router
from app.auth_routers.mfa_totp_router import router as mfa_totp_router
from app.auth_routers.mfa_email_router import router as mfa_email_router
from app.auth_routers.device_trust_router import router as device_router
from app.auth_routers.preferences_router import router as preferences_router

router = APIRouter(prefix="/api/auth", tags=["auth"])
router.include_router(core_router)
router.include_router(email_router)
router.include_router(password_router)
router.include_router(mfa_totp_router)
router.include_router(mfa_email_router)
router.include_router(device_router)
router.include_router(preferences_router)
```

**Sub-router pattern** (from existing `bot_routers/`):
- Sub-routers use `APIRouter()` with NO prefix (inherited from parent)
- Each sub-router is a standalone module importing from `schemas.py`, `helpers.py`, `rate_limiters.py`
- MFA sub-routers may share a `_complete_mfa_login()` helper — put it in `helpers.py`

**Steps**:
1. Create `backend/app/auth_routers/` directory
2. Create `schemas.py` with all Pydantic models from lines 288-413
3. Create `helpers.py` with all helper functions from lines 415-610
4. Create `rate_limiters.py` with rate limiting logic from lines 56-286
5. Create each sub-router file, importing from schemas/helpers/rate_limiters
6. Replace `auth_router.py` contents with the aggregator
7. Update `main.py` if needed (currently imports `from app.routers.auth_router import router as auth_router` — this should still work since auth_router.py still exports `router`)
8. Verify all auth endpoints still resolve: `./venv/bin/python3 -c "from app.routers.auth_router import router; print([(r.path, r.methods) for r in router.routes])"`

**Expected result**: `auth_router.py` drops from 2151 lines to ~20 lines (aggregator). 7 sub-modules each 50-200 lines.

---

### Work Item 6: Extract reports_router.py schedule logic

**Problem**: `reports_router.py` (1262 lines) has schedule CRUD endpoints with logic that should live in `report_scheduler.py`.

**What to extract**: The `update_schedule()` endpoint (lines 929-1043, ~115 lines) contains schedule recomputation logic (`compute_next_run_flexible()`, `build_periodicity_label()`, goal link management). The `create_schedule()` endpoint (lines 846-926) has similar logic.

**Steps**:
1. Extract schedule creation/update business logic into `services/report_scheduler.py` as `create_schedule_record()` and `update_schedule_record()`
2. Router endpoints become thin wrappers
3. `report_scheduler.py` already has `compute_next_run_flexible()` and `build_periodicity_label()` — the extracted logic just calls these

**Expected result**: `reports_router.py` drops from ~1262 to ~1050 lines (still approaching limit but under).

---

## Phase 3: Decompose God Functions (Trading Engine)

### Work Item 7: Decompose signal_processor.py:process_signal() (951 lines, CC=86)

**Problem**: `process_signal()` at line 170 is 951 lines with cyclomatic complexity of 86. It's the core trading decision function — handles signal analysis, budget calculation, buy decisions, trade execution, and sell decisions all in one function.

**Current signature**:
```python
async def process_signal(
    db, exchange, trading_client, bot, strategy, product_id,
    candles, current_price, pre_analyzed_signal=None,
    candles_by_timeframe=None, position_override=_POSITION_NOT_SET
):
```

**Decomposition plan** — extract into private helper functions within the same file (no file split needed — the file is 1120 lines total, under limit):

| New Function | Phase | Approx Lines | Source Lines |
|-------------|-------|-------------|-------------|
| `_handle_ai_failsafe()` | AI failsafe sell | ~80 | 228-308 |
| `_calculate_budget()` | Budget allocation | ~65 | 310-375 |
| `_decide_buy()` | Buy decision logic | ~200 | 397-599 |
| `_execute_buy_trade()` | Buy execution routing | ~200 | 646-851 |
| `_decide_and_execute_sell()` | Sell decision + execution | ~70 | 853-920+ |

**Process_signal becomes orchestrator** (~100 lines):
```python
async def process_signal(db, exchange, trading_client, bot, strategy, product_id,
                         candles, current_price, ...):
    # 1. Get position state
    position = await _get_position(db, bot, product_id, position_override)

    # 2. Analyze signal
    signal = pre_analyzed_signal or await strategy.analyze_signal(...)

    # 3. AI failsafe check
    failsafe_result = await _handle_ai_failsafe(db, exchange, trading_client, bot, position, signal, ...)
    if failsafe_result:
        return failsafe_result

    # 4. Calculate budget
    budget = await _calculate_budget(db, bot, position, ...)

    # 5. Buy decision
    should_buy, buy_amount, buy_reason = await _decide_buy(db, bot, strategy, signal, budget, ...)

    # 6. Execute buy
    if should_buy:
        trade = await _execute_buy_trade(db, exchange, trading_client, bot, position, ...)

    # 7. Sell decision + execution
    if position:
        await _decide_and_execute_sell(db, exchange, trading_client, bot, position, strategy, signal, ...)

    return result
```

**Key rule**: Each helper function receives only the parameters it needs — don't pass the entire parameter set. Use return values to communicate results back to the orchestrator.

**Steps**:
1. Read `signal_processor.py` fully
2. Create `_handle_ai_failsafe()` — extract lines 228-308
3. Create `_calculate_budget()` — extract lines 310-375
4. Create `_decide_buy()` — extract lines 397-599 (includes cooldown check, blacklist check, strategy.should_buy call)
5. Create `_execute_buy_trade()` — extract lines 646-851 (includes position creation, executor routing, signal recording)
6. Create `_decide_and_execute_sell()` — extract lines 853-920+
7. Rewrite `process_signal()` as orchestrator calling these helpers
8. Run existing tests: `pytest tests/test_signal_processor.py -v` (if exists)

**Lint**: `flake8 --max-line-length=120 backend/app/trading_engine/signal_processor.py`

---

### Work Item 8: Split multi_bot_monitor.py into focused modules

**Problem**: `multi_bot_monitor.py` is 2039 lines with 3 functions over 200 lines (CC 64-71).

**Target structure**:
```
backend/app/
├── multi_bot_monitor.py          # MultiBotMonitor class (trimmed to ~600 lines)
│                                 #   __init__, process_bot, _monitor_loop, caching
├── monitor/
│   ├── __init__.py
│   ├── batch_analyzer.py         # process_bot_batch() (~500 lines)
│   ├── pair_processor.py         # process_bot_pair() (~500 lines)
│   └── bull_flag_processor.py    # process_bull_flag_bot() (~250 lines)
```

**Steps**:
1. Create `backend/app/monitor/` directory
2. Extract `process_bot_batch()` → `batch_analyzer.py` as standalone async function
3. Extract `process_bot_pair()` → `pair_processor.py` as standalone async function
4. Extract `process_bull_flag_bot()` → `bull_flag_processor.py` as standalone async function
5. The `MultiBotMonitor` class keeps: `__init__`, `process_bot` (dispatch), candle caching, exchange caching, the main monitoring loop
6. `process_bot()` becomes a dispatcher that calls the extracted modules
7. Shared state (caches, semaphores) stays on the `MultiBotMonitor` instance — pass `self` or specific cache refs to extracted functions
8. Update all imports across the codebase (search for `from app.multi_bot_monitor import`)

**Expected result**: `multi_bot_monitor.py` drops from 2039 to ~600 lines. 3 new focused modules.

---

### Work Item 9: Decompose buy_executor.py and sell_executor.py

**Problem**: `execute_buy()` (426 lines) and `execute_sell()` (367 lines) are monolithic execution functions.

**Decomposition for buy_executor.py**:

| New Function | Purpose | Source Lines |
|-------------|---------|-------------|
| `_validate_order_size()` | Check exchange minimums | ~30 lines from 112-139 |
| `_reconcile_fill()` | Retry-based fill data retrieval | ~100 lines from 226-331 |
| `_create_buy_trade_record()` | Create Trade + update Position | ~40 lines from 363-402 |
| `_post_buy_operations()` | Logging, WebSocket, cache invalidation | ~45 lines from 408-450 |

**Decomposition for sell_executor.py**:

| New Function | Purpose | Source Lines |
|-------------|---------|-------------|
| `_try_limit_sell()` | Attempt limit order placement | ~50 lines from 432-484 |
| `_validate_market_fallback()` | Check profit before market fallback | ~25 lines from 486-510 |
| `_reconcile_sell_fill()` | Fill data retrieval (similar to buy) | ~80 lines |
| `_create_sell_trade_record()` | Create Trade + compute profit | ~40 lines |

**Shared utility**: Both buy and sell have nearly identical fill reconciliation retry logic. Extract to `trading_engine/fill_reconciler.py`:
```python
async def reconcile_order_fill(exchange, order_id, product_id, max_retries=10) -> FillData:
    """Retry-based order fill data retrieval with exponential backoff."""
```

**Steps**:
1. Create `trading_engine/fill_reconciler.py` with shared reconciliation logic
2. Extract helpers into `buy_executor.py` (private functions, same file — file is 764 lines, under limit)
3. Extract helpers into `sell_executor.py` (private functions, same file — file is 754 lines, under limit)
4. Both executors call the shared `reconcile_order_fill()`
5. Run tests: `pytest tests/test_buy_executor.py tests/test_sell_executor.py -v`

---

### Work Item 10: Decompose pdf_generator.py:generate_pdf() (771 lines)

**Problem**: `generate_pdf()` at line 78 is 771 lines building a PDF section by section.

**Note**: This file was already split from a larger `report_generator_service.py` (see `PRPs/refactor-report-generator.md`). The current path is `backend/app/services/report_generator_service/pdf_generator.py` (1101 lines total).

**Decomposition** — extract section builders as private functions within the same file:

| New Function | Section | Approx Lines |
|-------------|---------|-------------|
| `_build_pdf_header()` | Brand header | ~20 |
| `_build_pdf_metadata()` | Title, account, timestamp | ~15 |
| `_build_pdf_metrics_table()` | Key metrics (20+ rows) | ~60 |
| `_build_pdf_capital_movement()` | Capital flow section | ~40 |
| `_build_pdf_goals_section()` | Goals with expenses | ~150 |
| `_build_pdf_ai_section()` | AI summary with tiers | ~100 |
| `_build_pdf_comparison()` | Period comparison | ~50 |

**Steps**:
1. Read `pdf_generator.py` fully
2. Extract each section builder as a private function taking `(pdf, report_data, brand_colors)` parameters
3. `generate_pdf()` becomes an orchestrator that calls section builders in order
4. Run tests: `pytest tests/test_report_generator*.py -v`

---

## Phase 4: Strategy & Definition Refactoring

### Work Item 11: Extract strategy get_definition() into data configs

**Problem**: `indicator_based.py:get_definition()` (437 lines) and `grid_trading.py:get_definition()` (325 lines) are giant functions that construct `StrategyParameter` objects. This is static definition data, not logic.

**Approach**: Convert to data-driven configuration dictionaries within each file. Define parameters as a list of dicts, then iterate to construct `StrategyParameter` objects.

**Pattern**:
```python
# Instead of 437 lines of StrategyParameter() constructors:
_INDICATOR_PARAMS = [
    {"key": "max_concurrent_deals", "label": "Max Concurrent Deals", "type": "integer",
     "default": 1, "min_value": 1, "max_value": 50, "group": "deal_management",
     "description": "Maximum number of..."},
    # ... 70+ entries
]

def get_definition(self) -> StrategyDefinition:
    params = [StrategyParameter(**p) for p in _INDICATOR_PARAMS]
    return StrategyDefinition(name="Indicator Based", ..., parameters=params)
```

**Steps**:
1. Extract parameter definitions from `indicator_based.py:get_definition()` into `_INDICATOR_PARAMS` list at module level
2. Extract parameter definitions from `grid_trading.py:get_definition()` into `_GRID_PARAMS` list at module level
3. Rewrite `get_definition()` as a 5-line function that iterates the data
4. Verify parameter order and grouping is preserved

**Expected result**: `indicator_based.py` drops from 1480 to ~1100 lines. `grid_trading.py` drops from 1086 to ~800 lines.

---

### Work Item 12: Decompose indicator_based.py analyze_signal() and should_buy()

**Problem**: `analyze_signal()` (273 lines, CC=41) and `should_buy()` (218 lines, CC=32) are complex decision functions.

**Decomposition for analyze_signal()**:

| New Function | Purpose | Source Lines |
|-------------|---------|-------------|
| `_load_previous_indicators()` | Load from position/cache | ~20 |
| `_calculate_traditional_indicators()` | Per-timeframe indicator calc | ~55 |
| `_calculate_ai_indicators()` | AI evaluation with caching | ~60 |
| `_calculate_bull_flag_indicators()` | Bull flag pattern detection | ~15 |
| `_evaluate_phase_conditions()` | Phase condition evaluation | ~60 |

**Decomposition for should_buy()**:

| New Function | Purpose |
|-------------|---------|
| `_check_buy_conditions()` | Evaluate base_order_conditions from signal |
| `_calculate_buy_amount()` | Budget calculation based on order type |
| `_check_safety_order_conditions()` | DCA/safety order evaluation |

**Steps**:
1. Extract helpers as private methods on `IndicatorBasedStrategy` class
2. `analyze_signal()` becomes an orchestrator
3. `should_buy()` becomes an orchestrator
4. Run tests: `pytest tests/strategies/ -v`

---

## Phase 5: Domain Exceptions & Parameter Objects

### Work Item 13: Replace HTTPException in services with domain exceptions

**Problem**: 3 services use `fastapi.HTTPException` directly, coupling them to the web framework.

**Files affected**:
- `services/portfolio_service.py:15` — raises HTTPException(503)
- `services/bot_validation_service.py:12` — raises HTTPException(400) in 15 places
- `services/exchange_service.py:16` — raises HTTPException(400/503)

**Solution**: Create `backend/app/exceptions.py`:
```python
class AppError(Exception):
    """Base application error."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)

class ValidationError(AppError):
    """Input validation failure."""
    def __init__(self, message: str):
        super().__init__(message, status_code=400)

class ExchangeUnavailableError(AppError):
    """Exchange API unavailable."""
    def __init__(self, message: str = "Exchange service unavailable"):
        super().__init__(message, status_code=503)

class NotFoundError(AppError):
    """Resource not found."""
    def __init__(self, message: str):
        super().__init__(message, status_code=404)
```

**Add global exception handler in `main.py`**:
```python
from app.exceptions import AppError

@app.exception_handler(AppError)
async def app_error_handler(request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})
```

**Steps**:
1. Create `backend/app/exceptions.py` with domain exception classes
2. Add `AppError` exception handler in `main.py`
3. Update `portfolio_service.py`: replace `HTTPException(503, ...)` with `ExchangeUnavailableError(...)`
4. Update `bot_validation_service.py`: replace `HTTPException(400, ...)` with `ValidationError(...)`
5. Update `exchange_service.py`: replace `HTTPException(400/503, ...)` with appropriate domain exception
6. Run all tests to verify behavior unchanged (the exception handler translates to same HTTP responses)

**Lint**: `flake8 --max-line-length=120 backend/app/exceptions.py backend/app/main.py backend/app/services/portfolio_service.py backend/app/services/bot_validation_service.py backend/app/services/exchange_service.py`

---

### Work Item 14: Introduce parameter dataclasses for heavy-param functions

**Problem**: 88 functions have 5+ parameters. Top offenders:

| Function | Params | File |
|----------|--------|------|
| `create_exchange_client()` | 15 | `exchange_clients/factory.py` |
| `log_order_to_history()` | 12 | `trading_engine/order_logger.py` |
| `place_order()` | 11 | `exchange_clients/bybit_client.py` |
| `execute_perps_open()` | 11 | `trading_engine/perps_executor.py` |
| `process_signal()` | 10 | `trading_engine/signal_processor.py` |
| `broadcast_order_fill()` | 10 | `services/websocket_manager.py` |

**Approach**: Create dataclasses for the top 5 offenders only. Use `@dataclass` (already used in `season_detector.py` as a pattern).

**Example for `create_exchange_client`** (group by exchange type):
```python
@dataclass
class CoinbaseCredentials:
    key_name: Optional[str] = None
    private_key: Optional[str] = None

@dataclass
class ByBitCredentials:
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    testnet: bool = False

@dataclass
class ExchangeClientConfig:
    exchange_type: str
    exchange_name: str = "coinbase"
    coinbase: Optional[CoinbaseCredentials] = None
    bybit: Optional[ByBitCredentials] = None
    # ... etc
    account_id: Optional[int] = None

def create_exchange_client(config: ExchangeClientConfig) -> Optional[ExchangeClient]:
```

**For `log_order_to_history`**:
```python
@dataclass
class OrderLogEntry:
    product_id: str
    side: str
    order_type: str
    trade_type: str
    quote_amount: float
    price: float
    status: str
    order_id: Optional[str] = None
    base_amount: Optional[float] = None
    error_message: Optional[str] = None

async def log_order_to_history(db, bot, position, entry: OrderLogEntry):
```

**Steps**:
1. Define dataclasses near the functions they serve (in the same file, or in a shared `types.py` if used across modules)
2. Update function signatures to accept the dataclass
3. Update ALL callers to construct the dataclass instead of passing individual args
4. Search for all callers: `grep -rn "create_exchange_client\|log_order_to_history\|broadcast_order_fill" backend/app/`

**CRITICAL**: Update every caller. This is the most error-prone step — missing a caller means a runtime crash.

---

## Phase 6: Frontend Component Extraction (Lower Priority)

### Work Item 15: Extract frontend components into subcomponents and hooks

**Problem**: 6 frontend components exceed 950 lines each. Largest: `News.tsx` at 1586 lines.

**Approach**: Follow existing patterns from `pages/news/hooks/` and `pages/news/components/`.

**Priority order** (by impact):

**A. BotFormModal.tsx (1540 lines)**:
- Extract `useBotForm()` hook — form state, validation, submission logic
- Extract `<StrategyConfigSection>` — strategy-specific parameter rendering
- Extract `<CoinCategorySelector>` — coin category badge/filter UI
- Target: main component under 500 lines

**B. News.tsx (1586 lines)**:
- Already partially modularized (has hooks directory)
- Extract `<NewsFilterBar>` — filter controls UI (~40 lines)
- Extract `<ArticleList>` — article rendering section
- Extract `<VideoSection>` — video tab content
- Target: main component under 800 lines

**C. PnLChart.tsx (987 lines)**:
- Extract `<TimeRangeSelector>` — time range buttons
- Extract `<SummaryTab>`, `<DailyPnLTab>`, `<PairPnLTab>` — tab content
- Extract chart data transformation into `usePnLData()` hook
- Target: main component under 400 lines

**D. DealChart.tsx (954 lines)**:
- Extract chart configuration into `useDealChartConfig()` hook
- Extract `<PositionHeader>`, `<AnalysisSection>` subcomponents
- Target: main component under 400 lines

**E. ArticleReaderMiniPlayer.tsx (951 lines)**:
- Extract `<VolumeControls>`, `<PlaybackSpeedSelector>`
- Most logic already in `ArticleReaderContext` — focus on UI extraction
- Target: main component under 500 lines

**F. DCABudgetConfigForm.tsx (1150 lines)**:
- Extract `<DCALadderVisualization>` — safety order ladder display
- Extract `<BudgetBreakdownTable>` — budget allocation table
- Extract calculation logic into `useDCACalculations()` hook
- Target: main component under 600 lines

**Pattern reference** (from existing `pages/news/`):
```
pages/news/
├── hooks/
│   ├── useNewsData.ts       # Data fetching
│   ├── useNewsFilters.ts    # Filter state
│   ├── useSeenStatus.ts     # Read tracking
│   └── useTTSSync.ts        # Audio sync
├── components/
│   ├── ArticleContent.tsx   # Sub-component
│   └── TTSControls.tsx      # Sub-component
└── helpers.ts               # Utility functions
```

**Steps per component**:
1. Identify state that can move to a custom hook
2. Identify JSX sections that can become sub-components
3. Create hook files in component's directory
4. Create sub-component files
5. Update main component to use hooks and sub-components
6. Type-check: `cd frontend && npx tsc --noEmit`

---

## Validation Gates

After each work item, run:

```bash
# Python lint
cd /home/ec2-user/ZenithGrid && backend/venv/bin/python3 -m flake8 --max-line-length=120 backend/app/

# TypeScript type check (if frontend files changed)
cd /home/ec2-user/ZenithGrid/frontend && npx tsc --noEmit

# Full test suite
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m pytest tests/ -v

# Import validation (after Phase 1)
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -c "from app.routers.news_router import router"
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -c "from app.services.news_fetch_service import fetch_all_news"

# Verify file sizes after refactoring
wc -l backend/app/routers/news_router.py
wc -l backend/app/routers/auth_router.py
wc -l backend/app/multi_bot_monitor.py
wc -l backend/app/trading_engine/signal_processor.py
```

---

## Execution Order & Dependencies

```
Phase 1 (CRITICAL)
└── WI-1: news_router ↔ news_fetch_service fix

Phase 2 (HIGH — independent, can parallelize)
├── WI-2: account_router → portfolio_service
├── WI-3: news_metrics_router → market_metrics_service
├── WI-4: accounts_router → account_service
├── WI-5: auth_router → auth_routers/
└── WI-6: reports_router schedule logic

Phase 3 (HIGH — independent, can parallelize)
├── WI-7: signal_processor decomposition
├── WI-8: multi_bot_monitor split
├── WI-9: buy/sell executor decomposition
└── WI-10: pdf_generator decomposition

Phase 4 (MEDIUM — independent)
├── WI-11: strategy get_definition() data-driven
└── WI-12: indicator_based analyze_signal/should_buy decomposition

Phase 5 (MEDIUM — can run anytime)
├── WI-13: domain exceptions (replaces HTTPException in services)
└── WI-14: parameter dataclasses (top 5 offenders)

Phase 6 (LOW — independent, can parallelize)
├── WI-15A: BotFormModal extraction
├── WI-15B: News.tsx extraction
├── WI-15C: PnLChart extraction
├── WI-15D: DealChart extraction
├── WI-15E: ArticleReaderMiniPlayer extraction
└── WI-15F: DCABudgetConfigForm extraction
```

**Total**: 15 work items across 6 phases. Phases 2-6 are independent of each other. Within each phase, work items are independent and can be parallelized.

---

## Risk Mitigation

1. **Import breakage**: After every function move, grep the entire codebase for old import paths. The most common failure mode is a caller still importing from the old location.
2. **Runtime vs import-time**: Functions moved between modules may have import-time side effects (module-level caches, constants). Ensure these are initialized correctly in the new location.
3. **Test import paths**: Tests import private functions directly (e.g., `from app.routers.news_router import store_article_in_db`). These must be updated when functions move.
4. **Frontend HMR**: Frontend changes in dev mode don't need a restart, but `npx tsc --noEmit` must pass.
5. **Trading bot disruption**: Do NOT restart services during refactoring unless necessary. All changes are structural — no behavior changes means no restart needed until deployment.
6. **Circular imports**: After Phase 1, run the circular import checks. After any module reorganization, verify clean imports.

---

## Quality Checklist

- [x] All necessary context included (file paths, line numbers, function signatures)
- [x] Validation gates are executable
- [x] References existing patterns (bot_routers, position_routers, news/hooks)
- [x] Clear implementation path (phased, ordered, independent within phases)
- [x] Error handling documented (domain exceptions in WI-13)
- [x] Risk mitigation documented
- [x] No behavior changes — pure structural refactoring
