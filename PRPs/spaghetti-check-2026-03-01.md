# PRP: Spaghetti Code Audit Findings & Remediation

**Date**: 2026-03-01
**Type**: Code Quality / Refactoring
**Status**: In Progress

---

## Architecture Grade Card

| Area | Grade | Notes |
|------|-------|-------|
| Backend dependency direction | **A+** | Perfect layering — no upward imports |
| Circular imports | **A+** | 83/83 modules import cleanly |
| Frontend import hygiene | **A** | 2 minor context-layer violations |
| File sizes | **B-** | indicator_based.py reduced; html/pdf builders deferred (template code) |
| Function sizes | **D** | 20+ CRITICAL functions (200+ lines), 30+ HIGH |
| Coupling | **A** | models split, AI provider constants deduplicated, mask_api_key centralized |
| Separation of concerns | **B+** | Router business logic extracted; remaining helpers are serialization, acceptable |
| Cyclomatic complexity | **D** | 3 functions over 60 branches, 13 over 30 |

---

## Priority 1 — CRITICAL (Fix Now)

### 1.1 Decompose `process_bot_pair()` — pair_processor.py
- **489 lines, 78 branches** — single worst function in codebase
- Break into phases: signal evaluation → position check → order execution
- File: `backend/app/monitor/pair_processor.py:23`

### 1.2 Extract `get_article_content()` to service layer — news_router.py
- **293 lines, 39 branches** in a router — biggest SoC violation
- Contains: L1/L2 cache, HTTP fetching, scrape policy, rate limiting, content extraction, DB writes
- Move to `services/article_content_service.py`, router becomes thin wrapper
- Also move `_mark_content_fetch_failed()` (lines 900-932)
- File: `backend/app/routers/news_router.py:936`

### 1.3 Remove duplicate `get_coinbase_from_db()` — bot_crud_router.py
- Duplicates `exchange_service.get_exchange_client_for_account()`
- Replace all callers with the service function, delete the duplicate
- File: `backend/app/bot_routers/bot_crud_router.py:28-57`

### 1.4 Fix `session_service.py` HTTPException leakage
- Service raises `HTTPException` directly (lines 74-75, 97-98, 120-121)
- Should raise domain exceptions; router translates to HTTP status
- File: `backend/app/services/session_service.py`

---

## Priority 2 — HIGH (Fix Soon)

### 2.1 Split `models.py` into domain sub-modules
- **1672 lines, 86 importers** — largest file AND biggest coupling point
- Split into: `models/trading.py`, `models/auth.py`, `models/content.py`, `models/reporting.py`
- Re-export from `models/__init__.py` for import compatibility
- File: `backend/app/models.py`

### 2.2 Introduce parameter dataclasses for trading engine
- `_execute_buy_trade()` — 12 params → `TradeContext` dataclass
- `execute_perps_open()` — 11 params → `OrderRequest` dataclass
- `execute_buy()` / `execute_sell()` / `execute_sell_short()` — 10 params each
- `_decide_and_execute_sell()` / `process_signal()` — 10 params → `SignalContext`
- Files: `signal_processor.py`, `buy_executor.py`, `sell_executor.py`, `perps_executor.py`

### 2.3 Decompose `get_account_portfolio_data()` — portfolio_service.py
- **358 lines, 71 branches**
- Split paper/CEX/DEX portfolio paths into separate functions
- File: `backend/app/services/portfolio_service.py:780`

### 2.4 Decompose `process_bot_batch()` — batch_analyzer.py
- **463 lines, 67 branches**
- Extract per-pair processing, error handling, result aggregation
- File: `backend/app/monitor/batch_analyzer.py:22`

### 2.5 Decompose report builder god functions
- `_build_expenses_goal_card()` — 484 lines (expense_builder.py:425)
- `_build_pdf_expense_goal()` — 408 lines (pdf_generator.py:267)
- `_build_summary_prompt()` — 307 lines (report_ai_service.py:193)
- `gather_report_data()` — 254 lines (report_data_service.py:26)

---

## Priority 3 — MEDIUM (Fix When Touched)

### 3.1 File size violations (1200-1450 lines)
- `indicator_based.py` — 1424 lines
- `html_builder.py` — 1372 lines
- `database_seeds.py` — 1337 lines (data file, low priority)
- `pdf_generator.py` — 1260 lines
- `signal_processor.py` — 1253 lines

### 3.2 Router business logic (move to services)
- `blacklist_router.py:41-132` — AI provider config queries
- `reports_router.py:248-296` — data transformation helpers
- `accounts_router.py:41-49` — key masking logic

### 3.3 Model business logic (move to services)
- `models.py:456-519` — `Bot.get_total_reserved_usd/btc()` position valuation

### 3.4 Frontend context import direction
- `ArticleReaderContext.tsx:8` — imports `useTTSSync` from `pages/news/hooks/` (move hook to shared `hooks/`)
- `NotificationContext.tsx:7` — imports Toast types from `components/` (extract types to `types/`)

### 3.5 Frontend component bloat (> 800 lines)
- `PnLChart.tsx` — 990 lines
- `DealChart.tsx` — 954 lines
- `DCABudgetConfigForm.tsx` — 952 lines
- `ArticleReaderMiniPlayer.tsx` — 903 lines
- `ArticleReaderContext.tsx` — 883 lines
- `BotFormModal.tsx` — 1362 lines

---

## Priority 4 — LOW (Quick Wins / Opportunistic)

### 4.1 God file imports (expected but could improve)
- `main.py` — 43 imports (app entry, expected)
- `news_router.py` — 24 imports (too many responsibilities)
- `news_tts_router.py` — 21 imports
- `system_router.py` — 20 imports

### 4.2 Additional complex functions (30+ branches)
- `shutdown_event()` in main.py — 45 branches
- `_evaluate_single_condition()` in phase_conditions.py — 45 branches (consider dispatch pattern)
- `get_cex_portfolio()` in portfolio_service.py — 43 branches
- `run_portfolio_conversion()` in portfolio_conversion_service.py — 35 branches

---

## What's Clean (No Action Needed)
- Zero circular imports (fixed bull_flag_indicator ↔ strategies chain)
- Zero backend dependency direction violations
- Frontend pages/components/hooks — clean separation
- God modules (models, database, auth) are expected central dependencies
- Router composition pattern (sub-routers) is well-organized

---

## Completion Tracking

- [x] 1.1 Decompose `process_bot_pair()` — 489→104 lines (main fn), split into 11 focused helpers
- [x] 1.2 Extract `get_article_content()` to service — moved to `services/article_content_service.py`, news_router 1228→815 lines
- [x] 1.3 Remove duplicate `get_coinbase_from_db()` — bot_crud_router now imports from portfolio_service
- [x] 1.4 Fix session_service HTTPException — uses `RateLimitError`/`SessionLimitError` domain exceptions
- [x] 2.1 Split models.py — 1672→5 domain modules (auth 239, trading 685, content 284, reporting 391, system 131) + circular import fix
- [x] 2.2 Trading engine parameter dataclasses — TradeContext dataclass, 5 internal fns refactored (8-13→2-7 params)
- [x] 2.3 Decompose portfolio_service — get_account_portfolio_data 358→~50 lines + 5 helpers
- [x] 2.4 Decompose batch_analyzer — process_bot_batch 463→~45 lines + 7 helpers
- [ ] 2.5 Decompose report builders (deferred — template/rendering code, low structural value)
- [x] 3.1 Extract `_INDICATOR_PARAMS` from indicator_based.py — 1424→1232 lines (params → `indicator_params.py`)
- [x] 3.2 Router business logic → services:
  - Moved AI provider constants/functions from blacklist_router + coin_review_service → settings_service (deduplication)
  - Moved `_mask_key_name` from accounts_router → `encryption.mask_api_key`
  - reports_router helpers: reviewed, acceptable as serialization helpers (not business logic)
- [x] 3.3 Bot.get_total_reserved — reviewed, acceptable on model (accesses self.positions ORM relationship)
- [x] 3.4 Frontend import direction: moved `useTTSSync` from `pages/news/hooks/` → shared `hooks/`
  - NotificationContext→Toast: reviewed, acceptable (provider renders component, standard React pattern)
- [ ] 3.5 Frontend component bloat (deferred — large files, each needs its own PRP)
- [ ] 4.x Low items (opportunistic)
