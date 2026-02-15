# Changelog

All notable changes to ZenithGrid will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v1.31.3] - 2026-02-15

### Changed
- Fixed all 175+ Python flake8 lint issues across 50 files (zero remaining)
- Fixed all 7 frontend TypeScript errors (zero remaining)
- Sorted imports with isort on all modified files
- Removed dead code: shadowed method definitions in PaperTradingClient, unused variables, unused imports
- Replaced bare `except:` with `except Exception:` (E722)
- Changed SQLAlchemy `== True/False` comparisons to idiomatic `.is_(True)/.is_(False)` (E712)
- Fixed f-strings without placeholders, ambiguous variable names, whitespace formatting
- Removed unused `global` declarations that only read (never assigned) module-level variables
- Added `logger` definition to exchange_clients/base.py (was undefined)
- Fixed PnLChart.tsx to use correct field names (`cumulative_pnl_usd` instead of `cumulative_pnl`)
- No behavioral changes — all fixes are mechanical/cosmetic

## [v1.31.2] - 2026-02-15

### Changed
- Codebase housekeeping: deleted 16 stale markdown docs, 17 duplicate/obsolete scripts from backend
- Removed unused arbitrage package (stat_arb_analyzer, triangular_detector) and empty bot_monitoring module
- Removed unused FundingRatesResponse type from frontend
- Replaced duplicate SELL_FEE_RATE constant in TradingViewChartModal with import from positionUtils
- Removed ~20 debug console.log statements from frontend (useIndicators, DealChart, Charts, ClosedPositions)
- Downgraded WebSocket lifecycle logs from console.log to console.debug in NotificationContext
- Moved 4 useful scripts (clean_slate, sell_all_simple, check_all_accounts, update_trade_fills) to backend/scripts/

### Fixed
- get_coinbase() in dependencies.py, settings_router.py, and system_router.py now filters by authenticated user's account (was grabbing first account in DB regardless of user — critical for multi-user support)
- Removed stale "TODO: Once authentication is wired up" comments (auth has been wired up since v1.31.0)

## [v1.31.1] - 2026-02-15

### Changed
- Remove dead `get_current_user_optional` from auth_dependencies.py and auth_router.py
- Add Query bounds (ge/le) on all paginated limit parameters to prevent abuse
- Sanitize remaining `str(e)` in error responses across templates, news, and trading routers

### Fixed
- Removed console.log that leaked wallet_private_key in BotFormModal
- Sanitized WebSocket console.log to not expose JWT token or message payloads
- Fixed broken slippage-check fetch in helpers.ts (wrong env var → authFetch)
- Closed positions page now correctly fetches up to 500 results (was broken by undefined base URL)

### Security
- Added security headers middleware (X-Frame-Options: DENY, X-Content-Type-Options: nosniff, X-XSS-Protection, Referrer-Policy)
- File permissions hardened: .env, trading.db, and backups set to 600
- Added DB-level unique index migration for bot names to prevent race conditions
- All query limit parameters now bounded to prevent DoS via unbounded result sets

## [v1.31.0] - 2026-02-15

### Added
- Fernet encryption for API keys at rest (exchange credentials + AI provider keys)
- `authFetch()` helper and exported `api` instance for centralized authenticated HTTP calls
- WebSocket authentication via JWT query parameter
- Login rate limiting (5 attempts per 15 minutes per IP)
- Password strength requirements (min 8 chars, uppercase, lowercase, digit)
- JWT secret startup validation (refuses to start with default/empty secret)
- Auto-generate `JWT_SECRET_KEY` and `ENCRYPTION_KEY` in `setup.py`

### Changed
- Enforce authentication on all protected API endpoints (100% coverage)
  - Backend: all bot, position, settings, system, order history, strategies, scanner logs, validation, and limit order endpoints now require JWT
  - Only intentionally public endpoints remain unauthenticated (market data, candles, news, coin icons, auth)
- Frontend: eliminate all bare `axios` imports in favor of auth-enabled `api` instance
  - Fixed 13 frontend files using raw `fetch()` or bare `axios` that bypassed auth headers
  - Affects: LimitCloseModal, PositionCard, usePositionMutations, PerpsPortfolioPanel, Portfolio, Settings, useValidation, useBotsData, useChartsData, usePositionsData, DealChart, DepthChart, useChartData
- Tighten CORS (explicit methods/headers instead of wildcards)
- Sanitize error responses (generic messages instead of leaking internal exceptions)

### Fixed
- Portfolio page "Failed to fetch portfolio" error caused by missing auth headers on auto-refresh
- PnL chart showing "No closed positions yet" due to unauthenticated `/api/positions/pnl-timeseries` call
- AISentimentIcon causing continuous 401 errors every 30 seconds
- Path traversal vulnerability in coin icons endpoint
- Debug print statements leaking JWT tokens in `coinbase_api/auth.py`

### Security
- Every non-public endpoint now returns 401 without valid JWT token
- API keys encrypted at rest using Fernet symmetric encryption
- Credential decryption at all read points (exchange client, AI service, settings)
- `.env.bak*` patterns added to `.gitignore` to prevent accidental secret commits

## [v1.30.1] - 2026-02-15

### Fixed
- Widen bot edit modal (max-w-2xl → max-w-4xl) to fit volume/RSI indicator fields without horizontal scrolling

## [v1.30.0] - 2026-02-15

### Added
- Coinbase INTX perpetual futures support: API layer, bracket TP/SL orders, position monitoring
- Futures bot configuration: leverage (1-10x), margin type (Cross/Isolated), TP/SL percentages, direction
- Perps portfolio linking in Settings (discovers INTX portfolio UUID)
- Futures position display: leverage badge, liquidation price, TP/SL, unrealized PnL, funding fees
- Perps portfolio panel: margin balance, open positions summary
- Backend endpoints for perps products, portfolio, positions, modify TP/SL, close position
- Database migration for perpetual futures fields (accounts, bots, positions)

## [v1.29.0] - 2026-02-14

### Added
- CHANGELOG.md
- Min volume filter UI for bot configuration
- Increasing/decreasing operators for indicators

## [v1.28.2] - 2026-02-14

- Remove 6 PnL cards from Portfolio page

## [v1.28.1] - 2026-02-14

- Remove Portfolio Totals from Bots page (moved to Dashboard)

## [v1.28.0] - 2026-02-14

- Fix bot toggle switch, add Portfolio Totals to Dashboard, add same-pair deals config

## [v1.27.0] - 2026-02-14

- Fix indicator logs crash, add 7d projection basis, persist UI state

## [v1.26.3] - 2026-02-14

- Add compounded projected PnL row to Portfolio Totals

## [v1.26.2] - 2026-02-14

- Fix sparkline width by adding w-full to wrapper div

## [v1.26.1] - 2026-02-14

- Add show-stopped toggle, smart resize button, resize-all improvements

## [v1.26.0] - 2026-02-14

- Add all-time PnL, sparkline time labels, bot PnL %, fix PnL/day calc

## [v1.25.7] - 2026-02-14

- Add cascading filters to History page

## [v1.25.6] - 2026-02-14

- Add bot, market, and pair filters to History page

## [v1.25.5] - 2026-02-14

- Drive progress bar at 60fps via direct DOM updates, bypass React state

## [v1.25.4] - 2026-02-14

- Sort article and video source chips by category order

## [v1.25.3] - 2026-02-14

- Fix timeline progress bar getting stuck during TTS playback

## [v1.25.2] - 2026-02-14

- Remove all window.location.reload() calls to prevent TTS interruption

## [v1.25.1] - 2026-02-14

- Filter adult content from child TTS voices

## [v1.25.0] - 2026-02-14

- Add simultaneous deals for same pair (max_simultaneous_same_pair)

## [v1.24.3] - 2026-02-14

- Add missing source color mappings, suppress reconnect refetch when engaged
- Add missing article sources to category color map

## [v1.24.2] - 2026-02-13

- Assign rainbow-ordered colors to category filters (red→violet)

## [v1.24.1] - 2026-02-13

- Fix news source color mappings, sort categories, suppress refetch when engaged

## [v1.24.0] - 2026-02-13

- Add Volume RSI indicator and 10m/4h timeframes for bot conditions

## [v1.23.0] - 2026-02-13

- Add deal cooldown per pair to prevent immediate re-entry after close

## [v1.22.15] - 2026-02-13

- Fix MACD crossing detection: pass indicator cache for all strategies + noise filter

## [v1.22.14] - 2026-02-08

- Add Total Budget column to Positions page overall stats

## [v1.22.13] - 2026-02-08

- Fix TTS tracking drift, source filter colors, drop paywalled news sources

## [v1.22.12] - 2026-02-08

- Fix news sources missing summaries: replace title-only feeds, add og:description fallback

## [v1.22.11] - 2026-02-08

- Fix crossing detection re-firing bug & improve position decision history UX

## [v1.22.10] - 2026-02-08

- Fix AI/Finance news: correct RSS URLs and YouTube channel IDs

## [v1.22.9] - 2026-02-08

- Add AI and Finance as distinct news categories

## [v1.22.8] - 2026-02-08

- Show relative PnL delta on non-All timeframes in summary chart

## [v1.22.7] - 2026-02-08

- Add news router enhancements, sentiment card updates, and coin icons
- Add multi-select for news sources, matching category filter behavior
- Add resize deal budget feature to recalculate max_quote_allowed

## [v1.22.6] - 2026-02-08

- Respect bot reservations in auto-buy, remove force-run button from bot actions

## [v1.22.5] - 2026-02-08

- Exempt grid bots from seasonality, smooth sparkline data to 30 averaged points

## [v1.22.4] - 2026-02-08

- Refine carousel animation with realistic archery-inspired draw timing

## [v1.22.3] - 2026-02-08

- Enhance carousel bowstring animation with longer tension hold

## [v1.22.2] - 2026-02-08

- Clarify UI labels for AI analysis interval and cycle-based bot management

## [v1.22.1] - 2026-02-08

- Fix Portfolio Today PnL bug, persist news filters, remove article cap

## [v1.22.0] - 2026-02-08

- Add sparkline charts, replace dead feeds, add YouTube sources for all categories

## [v1.21.4] - 2026-02-07

- Restore projected debt milestones to US National Debt card

## [v1.21.3] - 2026-02-07

- Consolidate TTS voices into single shared constants file

## [v1.21.2] - 2026-02-07

- Fix Find Reading to navigate across pagination pages

## [v1.21.1] - 2026-02-07

- Fix bot actions menu clipped by overflow-hidden container

## [v1.21.0] - 2026-02-07

- Add multi-category news system with 50 sources across 9 categories

## [v1.20.41] - 2026-02-06

- Add pip dependency installation to update.py

## [v1.20.40] - 2026-02-03

- Implement seasonality auto-management for bots (Phase 4)

## [v1.20.39] - 2026-02-03

- Fix spurious error from audio.onerror when clearing src

## [v1.20.38] - 2026-02-03

- Fix race condition causing red button during TTS load

## [v1.20.37] - 2026-02-03

- Fix red button showing during article load

## [v1.20.36] - 2026-02-03

- Fix TTS button colors: grey spinner during loading

## [v1.20.35] - 2026-02-03

- Fix TTS auto-retry and error state handling

## [v1.20.34] - 2026-02-03

- Add 50+ TTS voices from all English locales

## [v1.20.33] - 2026-02-03

- Fix TTS article navigation state sync issues

## [v1.20.32] - 2026-02-03

- Sync frontend season wheel with halving-anchored backend logic

## [v1.20.31] - 2026-02-03

- Enhance season detector with halving cycle anchoring

## [v1.20.30] - 2026-02-03

- Add seasonality toggle to Bots page

## [v1.20.29] - 2026-02-03

- Fix clone bot, update season colors, position wheel icons

## [v1.20.28] - 2026-02-02

- Add margin-right to season badge for spacing

## [v1.20.27] - 2026-02-02

- Fix season badge spacing in header

## [v1.20.26] - 2026-02-02

- Move season indicator to site header

## [v1.20.25] - 2026-02-02

- Rename market seasons to Winter/Spring/Summer/Fall

## [v1.20.24] - 2026-02-02

- Fix market season algorithm: better bear vs accumulation detection

## [v1.20.23] - 2026-02-02

- Add market season card and info tooltips to carousel
- Add 6 new market metrics cards to carousel

## [v1.20.22] - 2026-02-02

- Reset auto-cycle timer on manual carousel interaction

## [v1.20.21] - 2026-02-02

- Fix carousel transform calculation for infinite scroll

## [v1.20.20] - 2026-02-02

- Add infinite carousel with swipe/touch support

## [v1.20.19] - 2026-02-02

- Add spring animation to market sentiment carousel

## [v1.20.18] - 2026-02-02

- Add market metrics carousel with BTC dominance, altseason index, and stablecoin supply

## [v1.20.17] - 2026-02-02

- Add debt ceiling display and weekly AI monitoring

## [v1.20.16] - 2026-02-02

- Fix synthetic chart timeframes and stabilize debt rate calculation

## [v1.20.15] - 2026-02-02

- Reorder mini player controls: volume before replay, queue before close
- Revert "Reorder mini player controls: volume before replay, queue before close"

## [v1.20.14] - 2026-02-02

- Reorder mini player controls: volume before replay, queue before close

## [v1.20.13] - 2026-02-02

- Update article reader controls to match YouTube pattern

## [v1.20.12] - 2026-02-02

- Improve word highlighting for TTS sync

## [v1.20.11] - 2026-02-02

- Mini player thumbnail click navigates to News and finds article

## [v1.20.10] - 2026-02-01

- Add missing news sources to setup.py defaults

## [v1.20.9] - 2026-02-01

- Revert Playwright implementation
- Skip Playwright for bot-blocked sites like The Block
- Add Playwright support for JS-heavy sites like The Block

## [v1.20.8] - 2026-02-01

- Make video and article players mutually exclusive

## [v1.20.7] - 2026-02-01

- Use migration flag for voice cycling localStorage fix
- Force clear stale voice cycling localStorage value

## [v1.20.6] - 2026-02-01

- Restore voice cycling toggle with proper localStorage handling
- Debug: Force voice cycling always on to isolate issue
- Use persistent Audio element to fix autoplay between articles

## [v1.20.5] - 2026-02-01

- Change progress bar to word-based instead of time-based

## [v1.20.4] - 2026-02-01

- Fix word highlighting for en-dash separated words

## [v1.20.3] - 2026-02-01

- Fix word highlighting for em-dash separated words
- Add TODO for Playwright support for JS-rendered articles

## [v1.20.2] - 2026-01-31

- Fix word highlighting for hyphenated words and end-of-playback

## [v1.20.1] - 2026-01-31

- Fix voice cycling and improve word highlighting sync

## [v1.20.0] - 2026-01-31

- Add article reader with mini-player and voice cycling TTS
- Add synchronized TTS with word highlighting and auto-scroll

## [v1.19.1] - 2026-01-27

- Revert "Add acronym expansion for consistent TTS pronunciation"
- Add acronym expansion for consistent TTS pronunciation
- Strip markdown formatting from article text before TTS
- Fix TTS autoplay blocked by browser policy

## [v1.19.0] - 2026-01-27

- Add text-to-speech for reading news articles aloud

## [v1.18.4] - 2026-01-27

- Add missing dependencies for complete fresh install

## [v1.18.3] - 2026-01-27

- Sync setup.py schema defaults with production database

## [v1.18.2] - 2026-01-27

- Add polished toast notification for clipboard copy

## [v1.18.1] - 2026-01-27

- Improve bot import/export UX

## [v1.18.0] - 2026-01-27

- Add bot import/export functionality

## [v1.17.9] - 2026-01-27

- Fix Charts page not rendering data after loading

## [v1.17.8] - 2026-01-27

- Fix JSON field parsing for AI/Indicator logs
- Optimize AI/Indicator log loading with SQL UNION query

## [v1.17.7] - 2026-01-26

- Add pulse/glow notification effect for new AI and Indicator logs

## [v1.17.6] - 2026-01-26

- Add infinite loop scrolling to PnL carousel (Price is Right wheel effect)
- Fix number clipping in Projected PnL carousel
- Fix toggle overlap and add smooth vertical scrolling to PnL carousel
- Add auto-scrolling carousel for Projected PnL with expand/collapse toggle
- Add tasteful boxes around each Projected PnL timeframe for better grouping
- Add whitespace-nowrap and width constraints to prevent PnL text wrapping
- Further reduce Active trades column padding to free up space
- Reduce table column padding to prevent PnL text wrapping

## [v1.17.5] - 2026-01-26

- Add dual-currency (BTC/USD) display to bot PnL and Projected PnL columns

## [v1.17.4] - 2026-01-26

- Fix missing closing parenthesis in PnLChart.tsx ternary operator
- Add dual-currency display to PnL by day and by pair bar charts

## [v1.17.3] - 2026-01-26

- Increase news article thumbnail resolution by 50%

## [v1.17.2] - 2026-01-26

- Improve Portfolio table readability and reduce width
- Fix profit_btc calculation - compute dynamically from existing fields
- Fix linting warnings in PnLChart.tsx
- Add dual-currency (BTC/USD) display to Bots PnL chart with toggle

## [v1.17.1] - 2026-01-26

- Add chart panning constraints to Account Value chart

## [v1.17.0] - 2026-01-26

- Add Last Year to historical period selector

## [v1.16.0] - 2026-01-26

- Add WTD (Week To Date) and improve font consistency

## [v1.15.0] - 2026-01-26

- Reorganize realized PnL into logical groups

## [v1.14.0] - 2026-01-26

- Add selectable realized PnL periods with Last Month and Last Quarter

## [v1.13.0] - 2026-01-26

- Add MTD/QTD/YTD selector for realized PnL

## [v1.12.0] - 2026-01-26

- Add 4-week and YTD realized PnL tracking
- Add realized PnL stats (daily/weekly) to Positions page

## [v1.11.1] - 2026-01-26

- Fix: Handle nested condition groups in interval calculation

## [v1.11.0] - 2026-01-26

- Phase 3: Lazy fetching - only fetch timeframes for current trading phase
- Phase 2: Smart check scheduling based on indicator timeframes

## [v1.10.0] - 2026-01-26

- Phase 1: Smart candle caching with per-timeframe TTL

## [v1.9.9] - 2026-01-26

- Add image compression for news article thumbnails

## [v1.9.8] - 2026-01-26

- Add automated cleanup job for old failed orders

## [v1.9.7] - 2026-01-26

- Add automated cleanup job for failed condition logs

## [v1.9.6] - 2026-01-26

- Add detailed budget logging to indicator logs for GUI visibility

## [v1.9.5] - 2026-01-26

- Fix technical checks to evaluate conditions and execute trades

## [v1.9.4] - 2026-01-25

- Fix frontend N/A display for indicator condition details
- Fix AI indicator evaluation: pass product_id to analyze_signal
- Fix AI indicator evaluation: pass db and user_id to analyze_signal
- Fix syntax error in AIBotLogs.tsx (extra closing paren)
- Fix AI Bot Reasoning logs for indicator-based bots with AI indicators

## [v1.9.3] - 2026-01-25

- Add no-cache headers to positions API to prevent browser HTTP caching
- Fix stale cache showing incorrect positions/gains on page load

## [v1.9.2] - 2026-01-23

- Fix aggregate cache causing incorrect budget allocation after deposits
- Smart video muting: only mute on iOS devices
- Fix iPad video autoplay issue by starting videos muted

## [v1.9.1] - 2026-01-19

- Fix budget calculator to match order execution logic

## [v1.9.0] - 2026-01-19

- Add automatic paper trading account creation

## [v1.8.7] - 2026-01-19

- Improve Indicator Logs UI with better filter labels and stats
- Enable indicator logging for ALL evaluations, not just matches
- Stop tracking CLAUDE.md in git (add to .gitignore)
- Fix all TypeScript compilation errors

## [v1.8.6] - 2026-01-19

- Fix budget calculator: divide by max deals, not number of pairs
- Fix TypeScript linting errors: unused imports and type mismatches
- Fix bot config DCA budget validation math errors
- Fix trading router exchange client import

## [v1.8.5] - 2026-01-18

- Fix trading router import and disable sell when positions are open

## [v1.8.4] - 2026-01-18

- Add quick sell buttons to Portfolio page

## [v1.8.3] - 2026-01-18

- Fix TypeScript types for bidirectional trading and multi-currency balances

## [v1.8.2] - 2026-01-18

- Setup: Offer existing values as defaults when re-running

## [v1.8.1] - 2026-01-18

- Make setup.py safe to run multiple times (idempotent)

## [v1.8.0] - 2026-01-18

- Add migration to convert coin categorizations to global entries
- Fix setup.py to seed coin categorizations as global entries
- Add copy-to-account feature for bots

## [v1.7.3] - 2026-01-18

- Add smooth curved lines to chart (like 3Commas)

## [v1.7.2] - 2026-01-18

- Remove horizontal dashed current price lines from chart
- Remove rightOffset and barSpacing that were hiding data
- Add chart padding and margins to separate price lines from opposite axes
- Fix BTC y-axis to always show 8 decimal places
- Change BTC line color to solid orange (#ff8800)
- Fix chart default time range to 'all' instead of disabled '30d'

## [v1.7.1] - 2026-01-18

- Add account filter toggle to value chart - show selected account or all accounts

## [v1.7.0] - 2026-01-18

- Comprehensive macOS setup.py fixes for seamless installation

## [v1.6.3] - 2026-01-18

- Fix setup.py to properly install Homebrew and npm on macOS
- Fix account value snapshots to match portfolio display
- Fix account value chart to use authenticated API instance
- Fix account value chart authentication and paper trading toggle

## [v1.6.2] - 2026-01-17

- Complete paper trading snapshot implementation
- Fix account snapshot service SQLAlchemy async issues

## [v1.6.1] - 2026-01-17

- Update CLAUDE.md: Use systemctl for both backend and frontend services
- Add comprehensive plan verification document
- Complete bidirectional DCA grid bot implementation
- Final verification against implementation plan
- Phase 5: Add reservation display to Dashboard
- Add implementation summary and progress documentation
- Phase 3-4: Short order execution and bot validation
- Document per-account (per-CEX) reservation isolation
- Separate live and paper trading reservations
- Add asset conversion tracking for bidirectional bots
- Add bidirectional DCA grid bot foundation

## [v1.5.2] - 2026-01-16

- Fix import error: get_current_user from auth_dependencies

## [v1.5.1] - 2026-01-16

- Exclude paper trading accounts from account value chart by default

## [v1.5.0] - 2026-01-16

- Add account value history chart with daily snapshots

## [v1.4.0] - 2026-01-16

- Add ETH/USD price display next to BTC price in header

## [v1.3.1] - 2026-01-16

- Fix BTC/USD price display in header for paper trading

## [v1.3.0] - 2026-01-16

- Fix paper trading history isolation and update setup.py schema

## [v1.2.0] - 2026-01-14

- Restore AccountSwitcher dropdown, exclude paper trading from list
- Remove AccountSwitcher dropdown, keep only Paper Trading toggle
- Remove temporary debugging code
- Fix black screen: Add missing botsFetching destructuring
- CRITICAL FIX: Exclude paper trading accounts from get_coinbase_from_db
- Add temporary debug logging for bots page filtering issue
- Improve Bots page empty state message for account switching
- Fix: Reduce bot list refetch interval from 5s to 30s
- Add production-ready enhancements: rebalancing cooldown and exchange minimum validation
- Change paper trading toggle to orange when enabled
- Fix paper trading portfolio format to match frontend expectations
- Fix paper trading portfolio and balance queries
- Fix paper trading portfolio display in header
- Fix paper trading balances to show virtual balances
- Add Paper Trading balance management UI
- Fix import path for get_current_user in paper trading router
- Add paper trading functionality
- Update grid trading status documentation - ALL PHASES COMPLETE
- Phase 4: Complete Hybrid AI range mode
- Phase 7: Implement time-based grid rotation
- Phase 6: Implement volume-weighted grid levels
- Phase 5: Implement AI-Dynamic Grid optimization
- Add comprehensive grid trading implementation status document
- Fix unit test expectations for grid calculations
- Add strategies API endpoint and wire frontend to use it
- Phase 8: Enhanced frontend balance display with 3-column layout
- Phase 3: Dynamic breakout detection and grid rebalancing
- Phase 1-2: Grid order placement and neutral/long grid execution
- Phase 1: Implement GridTradingStrategy with core calculations
- Phase 0: Add capital reservation tracking for grid trading bots

## [v1.0.0] - 2026-01-13

- Show ALL quote currency balances (BTC, ETH, USD, USDC, USDT)
- Show reserved and available balances for all quote currencies
- Track BTC profit for all positions and show available balance
- Implement completed trades profit statistics on Positions page
- Fix backspace delete functionality for all numeric input fields

## [v0.134.2] - 2026-01-11

- Emphasize coin categorization is a critical safety feature

## [v0.134.1] - 2026-01-11

- Remove unused get_api_key_for_provider() fallback function

## [v0.134.0] - 2026-01-11

- Separate user and system AI API keys: users must configure their own

## [v0.133.13] - 2026-01-11

- Remove unused config variables: secret_key and ticker_interval

## [v0.133.12] - 2026-01-11

- Add missing video_articles table to setup.py database initialization

## [v0.133.11] - 2026-01-11

- Clarify AI Bot Quick Start is entirely GUI-based

## [v0.133.10] - 2026-01-11

- Remove auto-deployment comment from README

## [v0.133.9] - 2026-01-11

- Remove Recent Updates section from README

## [v0.133.8] - 2026-01-11

- Add update.py usage documentation to README

## [v0.133.7] - 2026-01-11

- Update README to accurately reflect setup ease and current capabilities

## [v0.133.6] - 2026-01-11

- Fix: Always monitor existing positions regardless of category filter

## [v0.133.5] - 2026-01-11

- Add category badges to pairs list and counts to category checkboxes

## [v0.133.4] - 2026-01-11

- Remove category permissions UI from Settings page
- Add bot-level category filtering for trading pairs
- Add dedicated MEME category for coin review
- Add auto-add new pairs option to bot configuration
- Reduce log noise from delisted pairs and fix port reference

## [v0.133.3] - 2026-01-09

- Fix portfolio conversion ImportError crash preventing sell orders

## [v0.133.2] - 2026-01-09

- Fix auto-buy BTC toggle not persisting on page refresh

## [v0.133.1] - 2026-01-09

- Make portfolio conversion per-account instead of global

## [v0.133.0] - 2026-01-09

- Restore Portfolio Conversion UI to Settings page

## [v0.132.0] - 2026-01-08

- Rename repository from GetRidOf3CommasBecauseTheyGoDownTooOften to ZenithGrid

## [v0.131.3] - 2026-01-08

- Clean up test files
- Add donation addresses to README

## [v0.131.2] - 2026-01-08

- Add donation addresses to LICENSE file

## [v0.131.1] - 2026-01-08

- Major refactoring: Modularize all large components and update licensing
- Fix setup.py: Add missing user_attempt_number column to positions table

## [v0.131.0] - 2026-01-08

- Major refactoring: Modularize all large components + fix auto-calculate budget

## [v0.130.1] - 2026-01-03

- Fix auto-buy USD conversion bugs

## [v0.130.0] - 2026-01-03

- Fix percentage placeholders appearing during portfolio refetch
- Fix loading screen when changing timeframes - use keepPreviousData
- Fix absurd projection calculations by using linear extrapolation
- Fix loading spinner appearing when changing timeframes
- Show full timeframe window in chart including zero-profit days
- Fix projections not updating when changing timeframes
- Prevent loading spinner when changing timeframes in Bots page
- Fix timeframe selector requiring double-click by adding explicit button type

## [v0.129.2] - 2026-01-03

- Fix auto-calculate safety order sizing bugs
- Archive all migration files - not needed for fresh installs
- Fix deal number migration to not assign numbers to failed positions

## [v0.129.1] - 2026-01-02

- Fix auto-calculate budget bug and UI deal number display
- Use Edit Order API for bid fallback instead of cancel-and-replace
- Implement Coinbase native Edit Order API for limit price updates

## [v0.129.0] - 2026-01-02

- Keep order type when enabling auto-calculate, compute optimal values
- Only auto-calculate base order size when toggle is enabled
- Auto-calculate base order size to fit budget with safety orders
- Use print() instead of logger for startup reconciliation messages
- Fix: Integrate startup reconciliation into main limit order monitor

## [v0.127.5] - 2026-01-02

- Add startup reconciliation for limit orders

## [v0.127.4] - 2026-01-02

- Fix base order sizing to reserve budget for safety orders

## [v0.127.3] - 2026-01-02

- Add rate limiting to Coinbase API calls to prevent 403 errors

## [v0.127.2] - 2026-01-02

- Add safety check: Prevent market order fallback below minimum profit target

## [v0.127.1] - 2026-01-02

- Fix: Round buy amounts to exchange increment to prevent profit loss on sell
- Fix model import: Setting -> Settings (plural)

## [v0.128.0] - 2026-01-01

- Add configurable cleanup for old decision logs

## [v0.127.0] - 2026-01-01

- Add unified decision logs (AI + Indicators)

## [v0.126.2] - 2026-01-01

- Fix all strategy parameter number inputs (including take profit)

## [v0.126.1] - 2026-01-01

- Fix number input fields allowing proper backspace/deletion

## [v0.126.0] - 2026-01-01

- Add clickable deal numbers with trade history popup

## [v0.125.0] - 2025-12-31

- Implement dual numbering system and 3Commas-style deal tracking

## [v0.124.1] - 2025-12-31

- Fix changelog cache not auto-refreshing when new tags created

## [v0.124.0] - 2025-12-31

- Add auto-buy BTC with stablecoins feature

## [v0.123.0] - 2025-12-31

- Add explicit auto-calculate toggle for DCA budget calculator

## [v0.122.2] - 2025-12-31

- Enforce exchange minimums in budget calculator with warnings

## [v0.122.1] - 2025-12-31

- Make order size fields read-only when budget calculator active

## [v0.122.0] - 2025-12-31

- Add DCA budget calculator with auto-sizing breakdown

## [v0.121.0] - 2025-12-31

- Make PnL projections configurable by chart timeframe

## [v0.120.0] - 2025-12-31

- Replace AI indicators with unified AI Spot Opinion system

## [v0.119.1] - 2025-12-31

- Fix Dashboard metrics to show accurate profit and win rate stats

## [v0.119.0] - 2025-12-26

- Frontend: Add real-time progress tracking for portfolio conversion
- Backend: Add real-time progress tracking for portfolio conversion

## [v0.118.0] - 2025-12-26

- Add detailed progress tracking to portfolio conversion
- Complete symmetric portfolio conversion logic + dust filtering

## [v0.117.0] - 2025-12-26

- Add rate limit delays to portfolio conversion (0.2s between orders)
- Add detailed error logging for Coinbase API failures
- Add error handling for Coinbase API failures in sell-portfolio endpoint
- Improve sell-portfolio-to-base: handle missing trading pairs via USD route
- Fix sell-portfolio-to-base endpoint - correct create_market_order call

## [v0.116.0] - 2025-12-25

- Enhance MissingOrderDetector to catch sell orders and stuck pending orders

## [v0.115.3] - 2025-12-25

- Fix critical duplicate limit order bug and position data inconsistencies

## [v0.115.2] - 2025-12-21

- Fix changelog Load More being slow - remove repeated git fetch

## [v0.115.1] - 2025-12-21

- Improve changelog loading performance

## [v0.115.0] - 2025-12-21

- Add About page with paginated changelog, fix stopped bots monitoring

## [v0.114.0] - 2025-12-18

- Add bidirectional chart synchronization for indicator panels

## [v0.113.4] - 2025-12-15

- Revert speculative bar spacing change - data is correct, label thinning is normal

## [v0.113.3] - 2025-12-15

- Adjust chart time scale spacing for better label visibility
- Add debug logging for PnL chart date range issue

## [v0.113.2] - 2025-12-15

- Fix PnL chart date range using string comparison

## [v0.113.1] - 2025-12-15

- Fix PnL chart not showing dates up to today

## [v0.113.0] - 2025-12-15

- Add >= and <= operators to phase condition selector

## [v0.112.16] - 2025-12-14

- Update cleanup documentation and fix setup.py service template
- Update cleanup script with comprehensive retention policies
- Add daily database cleanup script

## [v0.112.15] - 2025-12-14

- Add coin icon proxy to avoid CORS issues

## [v0.112.14] - 2025-12-14

- Fix recharts negative dimension warning by setting minimum chart height
- Fix greenlet SQLAlchemy error by eager loading Position.trades

## [v0.112.13] - 2025-12-14

- Add 14 days time range option

## [v0.112.12] - 2025-12-14

- Fix time range button logic - enable up to first covering timeframe

## [v0.112.11] - 2025-12-14

- Disable time range buttons that wouldn't show additional data

## [v0.112.10] - 2025-12-14

- Add 1 year time range filter to Bot Management PnL chart

## [v0.112.9] - 2025-12-14

- Fix AI coin review providers and model names

## [v0.112.8] - 2025-12-14

- Fix greenlet conflict by using sync SQLite for AI provider lookup

## [v0.112.7] - 2025-12-14

- Add AI provider selection for coin review

## [v0.112.6] - 2025-12-14

- Fix HTML entity encoding in og:image URLs (e.g., &amp; -> &)

## [v0.112.5] - 2025-12-14

- Add image proxy endpoint for cached thumbnails

## [v0.112.4] - 2025-12-14

- Add og:image fallback for feeds without thumbnails (Blockworks)

## [v0.112.3] - 2025-12-14

- Fix news loading performance by using URL thumbnails instead of base64

## [v0.112.2] - 2025-12-14

- Switch articles to client-side pagination for instant page changes

## [v0.112.1] - 2025-12-14

- Fix indicator logging: respect bot capacity and DCA slots

## [v0.112.0] - 2025-12-14

- Add pagination for news articles, remove video limit

## [v0.111.2] - 2025-12-14

- Fix: Use only closed candles for indicator calculations

## [v0.111.1] - 2025-12-13

- Skip entry indicator logging when position already exists

## [v0.111.0] - 2025-12-13

- Fix dropdown to float but start at button position
- Fix playlist dropdown to anchor below button instead of fixed position
- Extend news/video max age from 7 to 14 days

## [v0.110.0] - 2025-12-13

- Add new crypto news and YouTube sources

## [v0.109.5] - 2025-12-13

- Tone down pulse animation - subtler outline and fewer pulses

## [v0.109.4] - 2025-12-13

- Fix pulse animation using outline instead of box-shadow to avoid conflict with ring classes

## [v0.109.3] - 2025-12-13

- Reorganize MiniPlayer layout with stacked rows and enhance pulse effect

## [v0.109.2] - 2025-12-13

- Add pulsing red halo effect when clicking Find Playing button

## [v0.109.1] - 2025-12-13

- Fix time scrubber not updating on video autoplay
- Add db backup files to gitignore
- Add hover-to-scroll to News page 'Start from video' dropdown

## [v0.109.0] - 2025-12-13

- Fix VIDEO_CACHE_CHECK_MINUTES import and add MiniPlayer enhancements

## [v0.108.0] - 2025-12-13

- Add background content refresh and video database storage
- Fix video autoplay skipping every other video

## [v0.107.0] - 2025-12-13

- Add scroll-to-playing button for video list
- Add halo effect to currently playing video in News page
- Add database cleanup service creation to setup.py wizard

## [v0.106.2] - 2025-12-13

- Fix PnL chart to prevent zooming beyond data bounds

## [v0.106.1] - 2025-12-13

- Fix stopped bots to properly manage open positions

## [v0.106.0] - 2025-12-13

- Add database cleanup maintenance script with systemd timer

## [v0.105.2] - 2025-12-13

- Fix Active Deals showing empty due to failed position flood
- Increase throttling delays to allow API requests during bot monitoring
- Add throttling constants for t2.micro CPU optimization
- Add processing delays to reduce CPU burst on t2.micro
- Optimize API call frequency with increased cache TTLs

## [v0.105.1] - 2025-12-12

- Add percentage field validation against exchange minimums
- Add price_drop as visible DCA condition in indicator logs
- Fix: Remove redundant max_concurrent_deals division in calculate_base_order_size
- Fix: Respect split_budget_across_pairs toggle
- Fix budget_percentage: 0 means 0, 100 means 100
- Fix: budget_percentage=0 now means 100% (All) as UI indicates
- Fix MACD display: show 8 decimals, scientific notation for tiny values
- Fix USD-based bot form: dynamic currency labels
- Fix indicator precision: use 8 decimals for MACD values
- Fix indicator value display precision in logs
- Fix indicator logging and add higher timeframe support
- Add ONE_HOUR candle fetching for hourly MACD/RSI conditions
- Fix crossing detection for BB% and other indicators
- Skip logging DCA/Exit conditions for pairs without positions
- Fix crossing detection for indicator_based entry conditions
- Fix crossing detection for entry conditions (MACD Bot fix)

## [v0.105.0] - 2025-12-12

- Add daily trading pair monitor to sync delisted/new pairs
- Add deal age display to position cards

## [v0.104.1] - 2025-12-12

- Fix playlist double-advance bug: prevent nextVideo from being called twice
- Revert MiniPlayer to before background playback changes
- Fix YouTube player controls and background playback
- Keep YouTube video playing when tab loses focus

## [v0.104.0] - 2025-12-11

- Add bot creation fixes, optimistic updates, and schema sync
- Add npm dependency handling to update.py
- Upgrade all npm dependencies to latest major versions
- Update npm dependencies and CLAUDE.md environment detection

## [v0.103.2] - 2025-12-11

- Add rate limiting between order executions to prevent Coinbase 403 throttling

## [v0.103.1] - 2025-12-11

- Fix playlist auto-advance: subscribe to YouTube iframe events
- Increase video hover size to 6x (672x384px)
- Fix video hover: use overflow-visible and explicit size change
- Add hover-to-enlarge effect on mini player video

## [v0.103.0] - 2025-12-10

- Fix limit order UI: CoinbaseAdapter time_in_force and price step arrows
- Fix: Edit Limit Price now properly preselects current limit price
- Update setup.py schema for pending_orders GTD fields

## [v0.102.0] - 2025-12-10

- Add GTD (Good 'til Date) order type support for limit close orders

## [v0.101.0] - 2025-12-10

- Show Deal # and pair in limit close modal title
- Make depth chart rows dynamically fill available space
- Round mark price UP to valid precision for sell orders
- Add quick-select buttons for Bid, Mark, Ask prices in limit close modal
- Enhance limit close modal: clickable depth chart, extended slider range
- Highlight limit price in depth chart with light grey outline

## [v0.100.16] - 2025-12-10

- Add /api/market/btc-usd-price endpoint
- Add today's USD value for closed BTC positions (HODL tracker)
- Show USD profit value for closed BTC pair positions

## [v0.100.15] - 2025-12-09

- Add ESC key handler to LimitCloseModal
- Extend slider range when limit price is outside bid-ask
- Fix Coinbase orderbook API endpoint
- Fix: Add get_product_book to CoinbaseAdapter

## [v0.100.14] - 2025-12-09

- Add Level 2 order book depth chart to limit close modal
- Fix slider resetting: remove price reset from fetchTicker

## [v0.100.13] - 2025-12-09

- Fix slider resetting to mark on ticker updates

## [v0.100.12] - 2025-12-09

- Add tick marks on slider to show valid price levels

## [v0.100.11] - 2025-12-09

- Slider snaps to valid precision steps for each coin

## [v0.100.10] - 2025-12-09

- Add breakeven tick mark to limit close slider

## [v0.100.9] - 2025-12-09

- Improve visual loss indicators in limit close modal

## [v0.100.8] - 2025-12-09

- Add loss confirmation alert for limit close orders

## [v0.100.7] - 2025-12-09

- Fix: Handle whole number base_increment in get_base_precision()
- Fix crossing detection for indicator-based strategies
- Add database seeding for fresh installs

## [v0.100.6] - 2025-12-09

- Extract thumbnails from RSS description HTML as fallback
- Derive allowed article domains from database instead of hardcoded list
- Add Bitcoin Magazine and BeInCrypto to allowed article domains
- Replace Reddit sources with Bitcoin Magazine and BeInCrypto
- Fix: Correct Reddit source names in migration
- Fix: Add auth headers to sources API calls
- Fix: Replace get_async_db with get_db in sources_router

## [v0.100.5] - 2025-12-09

- Add user source subscription UI and migrate news to DB sources

## [v0.100.4] - 2025-12-09

- Add database-backed content sources with user subscriptions

## [v0.100.3] - 2025-12-09

- Sync setup.py with production schema

## [v0.100.2] - 2025-12-09

- Add 6 new crypto YouTube channels to video news

## [v0.100.1] - 2025-12-09

- Unify video playback: individual videos open in expanded modal

## [v0.100.0] - 2025-12-09

- Add play/pause controls to mini-player
- Refactor: Single morphing player that transforms between mini-bar and modal
- Fix: Collapse mini-player when full modal opens to prevent duplicate playback
- Fix: Remove duplicate video iframe from mini-player thumbnail area

## [v0.99.0] - 2025-12-09

- Feature: Add persistent mini-player for video playlist

## [v0.98.0] - 2025-12-09

- Add video player modal for Play All in Crypto News
- Add alias support to update.py completion
- Add bash completion script for update.py

## [v0.97.1] - 2025-12-09

- Feature: Add longer timeframes (2d, 3d, 1w, 2w, 1M)

## [v0.97.0] - 2025-12-09

- Fix: Verify profit at mark price before placing limit sell orders

## [v0.96.9] - 2025-12-09

- Add indicator condition logging for non-AI bots

## [v0.96.8] - 2025-12-09

- Fix AI indicator detection to prioritize type field over legacy indicator field

## [v0.96.7] - 2025-12-09

- Fix update_ai_bots_with_dca migration to detect already applied state
- Fix migration idempotency detection for table creation migrations

## [v0.96.5] - 2025-12-09

- Fix: AI min confluence score default from 65 to 40 (moderate preset)

## [v0.96.4] - 2025-12-09

- Add graceful shutdown to wait for in-flight orders before stopping

## [v0.96.3] - 2025-12-09

- UI: Hide Safety Orders/Take Profit for pattern-based entries

## [v0.96.2] - 2025-12-09

- Bull Flag: Use pattern-calculated TSL/TTP instead of percentage-based config

## [v0.96.1] - 2025-12-09

- Add toggleable Safety Orders option to bot form
- Fix: Bull flag params not reading migrated config values

## [v0.96.0] - 2025-12-09

- Fix: AI log only shows SELL for pairs with positions

## [v0.95.9] - 2025-12-09

- Fix: Condition exits now require Take Profit % as minimum

## [v0.95.8] - 2025-12-08

- Fix: Add 'equal' and 'not_equal' operators to phase condition evaluator

## [v0.95.7] - 2025-12-08

- Fix: Add ai_buy/ai_sell/bull_flag handler in phase_conditions

## [v0.95.6] - 2025-12-08

- Fix BB indicator key format mismatch (2.0 vs 2)

## [v0.95.5] - 2025-12-08

- Fix THREE_MINUTE timeframe detection and BB% lower band requirement

## [v0.95.4] - 2025-12-08

- Fix TypeError in should_sell() when take_profit_percentage is None

## [v0.95.3] - 2025-12-08

- Fix: Recalibrate AI confluence thresholds to match scoring reality

## [v0.95.2] - 2025-12-07

- Fix: Don't migrate blacklisted_coins user_id in multi-user migration

## [v0.95.1] - 2025-12-07

- Fix: Bot AI icon detection for grouped condition format

## [v0.95.0] - 2025-12-07

- Fix: Remove Position model properties that cause async greenlet errors
- Feature: Accurate DCA tick marks based on reference price setting
- UI: Show all DCA target levels as tick marks on position cards

## [v0.94.0] - 2025-12-07

- Feature: DCA target improvements

## [v0.93.0] - 2025-12-07

- Lint: Fix remaining lint errors (E712, F541, F841, E741)
- Lint: Remove unused imports (F401) - 14 errors fixed

## [v0.92.2] - 2025-12-07

- UI: Show time in changelog version dates

## [v0.92.1] - 2025-12-07

- Fix: Handle fixed_btc order type and show position ID in failed orders
- Backend: Use condition-level AI risk presets and handle grouped conditions
- UI: Add risk preset and AI provider selectors for AI Buy/Sell indicators
- Feature: Advanced condition builder with grouping and NOT support

## [v0.92.0] - 2025-12-07

- Fix: Allow full BTC precision (8 decimals) in order amount inputs
- Fix: Enforce max_safety_orders limit in indicator_based strategy
- UI: Add funds modal with slider for percentage of available balance
- Fix: Handle null profit in WebSocket order fill handler
- Fix: Apply candle gap-filling to all timeframes, not just THREE_MINUTE
- Fix: Show clear BUY/SELL/HOLD decisions in AI bot logs for indicator_based strategy
- Fix: Handle NaN values in ThreeCommasStyleForm number inputs
- Fix: Handle AI logging for indicator_based strategy
- Fix: Add AI logging to process_bot_pair for non-batch strategies
- Add Max Concurrent Deals field to ThreeCommasStyleForm
- UI: Make Safety Order Volume/Step Scale always visible
- Fix: Add missing db.commit() calls for scanner logs
- Fix: Handle None aggregate_value in debug print statements
- Fix condition type normalization for bot edit form
- Fix Strategy Parameters section for indicator_based bots
- Fix: Strip query params from JWT URI to fix 401 errors
- Fix: Add market_context parameter to IndicatorBasedStrategy.should_sell()
- Fix: Add **kwargs to IndicatorBasedStrategy.should_buy()
- Fix: Initialize candles variable before use in process_single_bot
- Fix: Move prepare_market_context to candle_utils
- Refactor: Replace pre-baked strategies with unified indicator-based bot builder

## [v0.91.0] - 2025-12-06

- Refactor: Extract indicator modals from DealChart.tsx
- Refactor: Extract types and utils from MarketSentimentCards.tsx
- Refactor: Remove duplicate CandleData interface from Portfolio.tsx
- Refactor: Extract DEX constants and ABIs to dedicated module
- Refactor: Extract portfolio utilities from accounts_router.py
- Refactor: Remove duplicate utilities from LightweightChartModal
- Refactor: Extract news utilities from News.tsx
- Refactor: Extract IndicatorSettingsModal from Charts.tsx
- Refactor: Extract candle utilities from multi_bot_monitor.py
- Refactor: Extract bot utilities from Bots.tsx
- Refactor: Extract DealChart component from Positions.tsx
- Refactor: Extract utilities and AISentimentIcon from Positions.tsx
- Refactor: Extract models, sources, and cache from news_router.py
- Refactor: Extract debt ceiling data from news_router.py
- Docs: Add housekeeping file splitting plan

## [v0.90.0] - 2025-12-06

- Enhance AI providers UI to use API data directly
- Add AI provider credentials UI to Settings page

## [v0.89.0] - 2025-12-06

- Wire up AI providers to use database credentials with .env fallback
- Add per-user AI provider credentials storage in database
- Add Groq AI provider support (14,400 RPD free tier)

## [v0.88.2] - 2025-12-06

- Fix: Store news images as base64 in database instead of filesystem

## [v0.88.1] - 2025-12-06

- Fix: Proxy /static route to backend for cached news images

## [v0.88.0] - 2025-12-06

- Feat: Database-backed news caching with local image storage

## [v0.87.10] - 2025-12-06

- Feat: Add update available indicator in header

## [v0.87.9] - 2025-12-06

- Fix: Expose version in root endpoint for reliable frontend access

## [v0.87.8] - 2025-12-06

- Fix: Use dynamic path resolution for git version detection

## [v0.87.7] - 2025-12-06

- Fix: Fetch app version from backend API instead of Vite build-time

## [v0.87.6] - 2025-12-06

- Fix: Extend price bar range to always show next DCA level

## [v0.87.5] - 2025-12-06

- Fix: Color version number instead of 'Installed:' label

## [v0.87.4] - 2025-12-06

- Color 'Installed:' label based on how far behind

## [v0.87.3] - 2025-12-06

- Fix: Show only next DCA tick on position bar

## [v0.87.2] - 2025-12-06

- Simplify changelog header to show Latest/Installed only

## [v0.87.1] - 2025-12-06

- Fix: Show DCA tick marks for AI bots with manual DCA targets

## [v0.87.0] - 2025-12-06

- Feat: Add 3Commas-style deal editing for open positions

## [v0.86.7] - 2025-12-06

- Fix changelog wording: use 'Installed' instead of 'Current version'

## [v0.86.6] - 2025-12-06

- Enhance changelog to show current version and unpulled updates

## [v0.86.5] - 2025-12-06

- Smart service restart detection in update.py

## [v0.86.4] - 2025-12-06

- Add --changelog flag to update.py

## [v0.86.3] - 2025-12-06

- Fix insufficient_funds calculation to use current position values

## [v0.86.2] - 2025-12-06

- Make order recording atomic to prevent missed trades
- Add missing order detector service to prevent untracked trades

## [v0.86.1] - 2025-12-06

- Fix: History page missing recently closed positions

## [v0.86.0] - 2025-12-06

- Fix: Profit target now uses bot config with sell-side fee adjustment
- Fix: Account for trading fees in base amount for BTC pairs
- Fix: product-precision endpoint URL in LimitCloseModal
- Add video playlist auto-play feature to News page
- Fix: Bull flag pullback detection now finds red candles within window
- Add --preview flag to update.py to view incoming changes

## [v0.85.1] - 2025-12-05

- Fix: History badge not persisting viewed state

## [v0.85.0] - 2025-12-05

- Fix budget percentage calculation for manual sizing mode

## [v0.84.6] - 2025-12-05

- Fix coin categorization showing all as approved + add --skip-pull flag

## [v0.84.5] - 2025-12-04

- Add idempotency checks to migrations

## [v0.84.4] - 2025-12-04

- Fix History badge to track closed/failed counts separately

## [v0.84.3] - 2025-12-04

- Fix migrations to use relative paths instead of hardcoded paths

## [v0.84.2] - 2025-12-04

- Skip service restart in update.py when already up to date

## [v0.84.1] - 2025-12-04

- Add user_id and user_deal_number columns to setup.py schema

## [v0.84.0] - 2025-12-04

- Add user-specific deal numbers for positions

## [v0.83.0] - 2025-12-04

- Add git check to setup.py for version display

## [v0.82.0] - 2025-12-04

- Auto-inject git version into app at build time
- Add version display to header

## [v0.81.0] - 2025-12-04

- Update: Add frontend service support to update.py
- Add update.py script for automated production updates
- Add EULA/risk disclaimer acceptance flow for users
- Add license agreement acceptance to setup wizard
- Fix: Persist failed orders seen count across sessions

## [v0.80.0] - 2025-12-04

- Setup: Make Gemini default AI provider, add PEM key format handling
- Fix: Rename limit order monitor method to match main.py call
- Refactor: Make coin categorization admin-only with global visibility
- Fix: Update bot routers and coin review service to get Coinbase client from database
- Fix: Update all routers to get Coinbase client from database
- Fix: Position router dependencies now get Coinbase client from database
- Fix: Update account_router to get exchange client from database
- Fix: Use _current_exchange to avoid property conflict
- Fix: Set exchange client per-bot in monitoring loop
- Fix: Guard against None order_monitor in start/stop
- Multi-user Coinbase credentials from database
- Add setup introduction with step overview and confirmation prompt
- Fix bcrypt import error in setup wizard
- Add multi-provider AI support for coin categorization
- Clarify system vs per-user AI API keys in setup wizard
- Protect git-tracked deployment scripts during cleanup
- Auto-restart setup with Python 3.11 after installation
- Add animated spinner for long-running operations
- Offer to install Homebrew on Mac if not present
- Auto-install Python 3.11 when version too old
- Require Python 3.10+ and pin exact dependency versions
- Use flexible version constraints in requirements.txt
- Add --cleanup flag to setup wizard
- Remove setup.sh wrapper - users run python3 setup.py directly
- Add --uninstall-services flag to setup wizard
- Add --services-only flag to setup wizard
- Improve setup wizard to auto-detect and install dependencies
- Add setup wizard for initial application configuration
- Store history badge count in database per user
- Add confirmation dialog for sign out button
- Add password change UI to Settings page
- Add public signup with comprehensive EULA and risk disclosure
- Add user filtering to all routers and frontend auth interceptors
- Add multi-user support with JWT authentication
- Fix: Set account_id when creating positions
- Fix: Clear stale position errors when market data fetch succeeds
- Add ONE_MINUTE option to bull flag scanner timeframe
- Clean up debug logging after verifying gap-fill works
- Switch gap-fill debug logging to print() for guaranteed visibility
- Add entry-point debug logging to gap-fill function
- Add always-on gap-fill debug logging with max_gap info
- Add detailed gap-fill debug logging
- Add info-level logging for candle gap-filling to debug THREE_MINUTE issues
- Add candle gap-filling for sparse BTC pairs like charting platforms
- Fix Coinbase API 400 error from exceeding 300 candle limit
- Fix THREE_MINUTE BB% conditions failing on low-volume pairs
- Add Polyform Noncommercial 1.0.0 license
- Feat: Close article modal with ESC key
- Feat: Use compound interest for PnL projections
- Fix: Extract video_id from YouTube Shorts URLs
- Fix: Video playback affecting multiple videos in News page
- Cleanup: Remove verbose debug print statements from candle caching
- Fix: Request 300 ONE_MINUTE candles upfront for THREE_MINUTE cache
- Debug: Add print statements for candle caching visibility
- Change cache debug to logger.info to be visible
- Add debug logging for candle cache hits/misses
- Update handoff doc - mark both issues as fixed
- Fix BB% THREE_MINUTE indicator not populating for AI bots
- Fix force-close 500 error and add BB% debug logging
- Add detailed rejection reasons to bull flag pattern detection

## [v0.79.0] - 2025-11-30

- Fix PnL charts to show all dates, including days with no trades
- Feature: Add pagination to History page

## [v0.78.3] - 2025-11-30

- Fix: Add account_id to order history API response

## [v0.78.2] - 2025-11-30

- Fix: Show loading indicator for projected PnL percentages

## [v0.78.1] - 2025-11-30

- Fix: Trust initial AI buy signal for DCA, don't let secondary AI block it
- Fix: AI bots require buy signal for DCA, price drop is safeguard
- Fix: DCA no longer requires signal_type=buy
- debug: Add detailed logging to DCA decision flow
- debug: Add DCA decision logging to diagnose why DCAs aren't executing
- Perf: Increase cache TTLs and skip dust balances for faster API
- Perf: Parallelize API calls in aggregate value calculations
- Fix: DCA Completed count showing 0 instead of actual count

## [v0.78.0] - 2025-11-30

- Add Win Rate column to Bots table
- Add batched concurrency to bull flag scanner for rate limiting
- Fix: Bull flag scanner now scans all approved coins (was limited to 50)
- Fix volume detection and bull flag pattern validation
- Revert: Re-enable redirect_slashes to fix 404 errors
- Fix: Increase refetch intervals to prevent constant reload loop
- Fix: Disable redirect_slashes to prevent 307 redirects
- Fix: Batch position price fetches to avoid Coinbase rate limits
- Fix: Use get_product() for volume detection in bull flag scanner
- Fix: Optimize list_bots endpoint - pre-fetch aggregate values and batch price requests
- Fix: Add batched price fetching to accounts_router to prevent rate limits
- Speed up portfolio loading with batched price fetching
- Fix portfolio pagination and add debugging logs
- Add scanner logs feature for bull flag strategy
- Fix: Add aggregate_value parameter to bull_flag should_buy
- Add volume confirmation to bull flag pattern detection
- Fix: Bull flag scanner get_candles API compatibility
- Fix: Frontend Active Trades display for bull_flag strategy
- Fix: Bot stats max_concurrent_positions and portfolio missing assets
- Fix: Render bull_flag strategy parameter groups in frontend
- Fix: Make product_id Optional in BotResponse for multi-pair strategies
- Fix circular import in bull_flag_scanner
- Add bull flag USD trading strategy with TSL/TTP

## [v0.77.0] - 2025-11-30

- Fix: Add account_id to API response schemas for multi-account filtering
- Extract market sentiment cards into reusable component
- Reorganize nav: group account-specific vs general pages
- Add account filtering to PnLChart and pnl-timeseries API
- Simplify account filtering after DB migration
- Fix account filtering: DEX accounts now show only their own data
- Make History and Dashboard pages account-specific
- Fix header Account Value to use account-specific portfolio
- Fix Portfolio CEX/DEX account switching regression
- Fix all TypeScript errors in frontend codebase
- Add coin icons to Settings page coin categories list
- Add real-time order fill notifications with audio and visual alerts
- Improve news caching: 15-min refresh, 7-day retention, merge strategy
- Add 15-minute auto-refresh for news articles and videos
- Fix debt ceiling display: show values under $1T in billions
- Add complete US debt ceiling history from 1939 to present
- Add political context and source links to debt ceiling history
- Move debt ceiling history to modal, rename Milestones to Projected Milestones
- Move debt ceiling history to backend API
- Add debt ceiling history section showing last 7 increases/suspensions
- Add debt milestone countdowns for $1T and $5T markers
- Show specific estimated date for BTC halving countdown
- Fix Max safety orders display for AI autonomous bots
- Move commercialization roadmap to separate file
- Add commercialization roadmap for Zenith Grid
- Remove brotli from Accept-Encoding (not installed)
- Add full browser headers to article fetcher to fix 403 errors
- Default to reader mode when opening articles, always show thumbnail
- Fix duplicate title in reader mode with fuzzy matching
- Enhance reader mode with markdown formatting support
- Fix paragraph preservation in reader mode article content
- Add Reader Mode for news articles
- Add article preview modal to News page
- Add prominent open-in-new-tab button for videos
- Add inline YouTube video playback to News page
- Move News link to between Dashboard and Bots in nav
- Fix news timestamps: add UTC timezone indicator (Z suffix)
- Add periodic refresh for news article timestamps
- Add cache files and db backup patterns to gitignore
- Fix US debt counter to always count up
- Add US National Debt counter and halving countdown format toggle
- Fix BTC halving countdown timer - use stable dependency
- Add Fear/Greed Index and BTC Halving countdown to News page
- Add video news section with YouTube crypto channels
- Add feedparser dependency for news aggregation
- Fix Dashboard bot cards: profit and deals display
- Add crypto news aggregation tab with 24-hour caching

## [v0.76.0] - 2025-11-29

- Fix: Summary PnL chart shows relative profit for time range
- Fix: Most profitable bot card respects time range filter
- Fix: PnL by pair chart respects time range filter
- Fix: PnL stat should sum profits within selected time range
- Fix: PnL stat also showing $0 on by_pair tab
- Fix: Closed trades count incorrectly showing days instead of trades
- Optimize startup: lazy load pages and defer non-critical API calls
- Fix Portfolio page showing different values than header
- Fix AI Reasoning modal missing initial buy log
- Fix Dashboard showing different Account Value than header
- Fix order validation to use correct aggregate BTC value from balance_breakdown
- Fix section numbering: Strategy Parameters shows as 6 for AI, 7 for others
- Add validation to block save when manual order values are below exchange minimum
- Fix NaN warning in strategy parameter inputs
- Frontend: Budget settings only show in AI mode, not Manual mode
- Frontend: Add Max Concurrent Positions to Bot Budget Allocation section
- Frontend: Move Budget Allocation into Strategy Parameters for AI bots
- Fix aggregate BTC calculation: use current prices, not cost basis
- Frontend: Reorganize AI bot settings with conditional budget display
- Manual order sizing: use aggregate value for percentage calculations
- Add Manual Order Sizing group to frontend display order
- Optimize portfolio API: parallel price fetches + fix balance breakdown
- Fix portfolio balance breakdown for legacy positions
- Add 3Commas-style manual order sizing override
- Add MINIMUM PERCENTAGE to AI prompts to prevent below-minimum orders
- Update Claude API link to billing page
- Fix position_status in AI bot logs to show actual status
- Increase AI review timeout to 3 minutes
- Update AI review to scan all Coinbase coins in batches
- Extend tracked coins to include USD and USDC markets
- Redesign BlacklistManager with single table and category dropdowns
- Fix route order: Move /categories before /{symbol} to prevent conflicts
- Revert trailing slashes - endpoint works without them
- Fix: Add trailing slashes to category API endpoints
- Add category trading permissions with toggle UI
- Add weekly AI coin review service
- Add APPROVED coin category with green badges
- Add color-coded blacklist badges: BORDERLINE (yellow), QUESTIONABLE (orange), BLACKLISTED (red)
- Fix blacklist API trailing slash redirect issue
- Add coin blacklist feature
- Add THREE_MINUTE* synthetic candle support via 1-min aggregation
- Fix: Use ONE_MINUTE candles (THREE_MINUTE not supported by Coinbase)
- Support multi-timeframe BB% and faster technical checks
- Add debug logging for BB% take profit condition evaluation
- Add configurable DCA drop settings for AI bots
- Fix broken take profit conditions and add BB% support for AI bots
- Fix volume filter to always analyze pairs with open positions
- Fix deprecated token pricing - don't show misleading values
- Add legacy token price mapping for deprecated tokens
- Fix CoinGecko price fetching for free tier limits
- Add CoinGecko price fetching for DEX token valuations
- Fix DEX portfolio to show all tokens regardless of USD pricing
- Add old GALA token address (v1) for migration compatibility
- Switch to PublicNode RPC endpoints
- Add rate limiting delays and switch to Ankr RPC
- Switch to Cloudflare Ethereum RPC for better rate limits
- Add cUSDC, GALA, MANA tokens to DEX wallet service
- Fix corrupted DAI contract address
- Fix DEX portfolio rendering with optional chaining
- Integrate account filtering across all main pages
- Add account-specific portfolio endpoint with DEX support
- Fix accounts dropdown menu visibility
- Remove unused legacy Trading/MACD parameters from Settings
- Remove legacy Coinbase API credentials section from Settings
- Phase 9: Complete UI account switching integration
- Update handoff document with implementation status
- Phases 6-8: Complete Arbitrage Strategy Implementation
- Phase 5: Account Management & Context Switching
- Fix web3.py v6+ compatibility: Update middleware import
- Phase 4: Complete DEX frontend UI integration
- Phase 3: Complete Uniswap V3 integration with swap execution
- Phase 3: Add DEX client skeleton for Ethereum + Uniswap V3
- Fix order reconciliation monitor to use exchange_client
- Fix settings attribute names in main.py
- Phase 2: Add DEX fields to database schema
- Refactor: Complete exchange abstraction layer (Phase 1)
- Add exchange abstraction layer (Phase 1 foundation)
- Fix MP line to use bot's min_profit_percentage instead of hardcoded 2%
- Implement DCA budget protection to prevent insufficient DCA funds
- Fix AI budget calculation to use per-position budget
- Add Grok AI provider support to client validation
- Skip logging technical-only HOLD checks to reduce UI noise
- Implement two-tier bot checking architecture for efficient monitoring
- Fix Bollinger Band % crossing threshold input and add 3m timeframe
- Add exchange minimum order size requirement to AI prompts
- Add PhaseConditionSelector UI handler to AI Autonomous custom sell conditions
- Fix import error: use IndicatorCalculator class instead of standalone functions
- Add custom technical sell conditions to AI Autonomous strategy
- Replace hardcoded USDC PnL with dynamic API calculations
- Add USDC PnL placeholder cards to match BTC/USD column layout
- Add separate USDC Balance Breakdown column
- Fix budget availability check - add actual BTC balance verification
- Fix Dashboard Edit button to properly navigate and open bot edit modal
- Reorder bot config sections: group all AI-related settings together
- Improve Risk Tolerance UX with Manual option and preset visibility
- Add Duration column to closed positions table
- Sort History page tables by most recent first
- Fix limit order price precision: use product-specific decimals
- Implement product minimum fetching from product_precision.json
- AI aware of product minimums: inform AI and validate before execution
- Fix orphaned positions: mark as failed instead of expunging
- Add hard constraint: DCA only on meaningful drops below cost basis
- Add AI failsafe: auto-sell profitable positions when AI analysis fails
- Remove strict mode - AI bots are now purely AI-directed
- Improve control mode description to clarify AI vs user control
- Add toggle switch for AI bot control mode with conditional parameter display
- Fix AI autonomous strategy parameter handling and reorganization
- Update CLAUDE.md with production notes
- Add unrealized PnL sorting to Holdings table
- Fix USD Balance Breakdown to show only USD-denominated assets
- CRITICAL FIX: DCA failures should not abort entire bot cycle
- Add adaptive limit order with bid fallback
- Fix budget calculation: divide by max_concurrent_deals for fair per-position budget
- Sort closed positions by closure date (most recent first)
- Simplify sell order precision handling to match buy orders
- Add automatic order reconciliation monitor
- Fix market order fill tracking to handle slow fills properly
- Add precision rounding to all sell orders and enable OrderMonitor
- Fix get_order() unwrapping and add precision to strategy limit sells
- Fix limit order precision - use product_precision.json instead of Coinbase API
- Add enhanced error logging for limit order failures
- Fix limit close order size precision
- Implement proper partial fill handling for limit close orders
- Fix History sorting: closed positions now sort by closed_at desc
- Update Phase 5 bug report with Bugs #6 and #7
- Fix Bug #7: AIAutonomousStrategy missing _prepare_market_context
- Add logging to debug Coinbase limit order response format
- Bug #6: Add error logging to limit-close endpoint
- Fix Vite proxy IPv6 issue - use 127.0.0.1 instead of localhost
- Fix syntax error in strategy signatures
- Fix all 5 bugs identified in Phase 5 investigation
- Phase 5: Bug investigation report (no fixes applied)
- Phase 4: Code cleanup - unused variables and imports
- Phase 3: Type hint improvements
- Add HouseKeeping 1.1 progress report
- Phase 2: Code style improvements (PEP 8 compliance)
- Phase 1: Code formatting and documentation improvements
- Fix PEP 8 indentation and spacing issues (E129, E131, E302)
- Update bug investigation - all clear to proceed
- Add detailed potential bugs investigation report
- Add comprehensive code quality analysis for HouseKeeping_1.1
- Add handoff summary section - refactoring complete and ready for merge
- Update verification doc with post-deployment fixes summary
- CRITICAL FIX v5: Remove OLD_BACKUP files from repository
- CRITICAL FIX v4: Correct dependency overrides in main.py
- CRITICAL FIX v3: Change empty path endpoints from "" to "/"
- CRITICAL FIX v2: Remove prefix parameter entirely from sub-routers
- Add router include verification to API signature document
- CRITICAL FIX: Add explicit empty prefix to all sub-routers
- Add deployment instructions for HouseKeeping_1.0 production testing
- HOUSEKEEPING: Refactoring Complete - 7 Major Files Under 500 Lines
- STEP 7: Refactor positions_router.py (804 → 6 modules)
- STEP 6: Refactor bots.py router (760 → 5 modules)
- STEP 5: Add extraction plan for multi_bot_monitor.py
- Add session summary (4/13 files complete)
- Update progress: STEP 4 complete (coinbase_unified_client.py)
- STEP 4.5: Refactor coinbase_unified_client.py into wrapper (~260 lines)
- STEP 4.4: Extract coinbase_api/order_api.py (~300 lines)
- STEP 4.3: Extract coinbase_api/market_data_api.py (~150 lines)
- STEP 4.2: Extract coinbase_api/account_balance_api.py (~300 lines)
- Add STEP 4 detailed status tracking
- STEP 4.1: Extract coinbase_api/auth.py (~220 lines)
- Update progress: STEP 3 complete (trading_engine_v2.py)
- Add detailed completion plan for STEPs 4-13
- STEP 3.6: Refactor trading_engine_v2.py into wrapper class (~180 lines)
- STEP 3.5: Extract signal_processor.py from trading_engine_v2.py (~325 lines)
- STEP 3.4: Extract sell_executor.py from trading_engine_v2.py (~235 lines)
- STEP 3.3: Extract buy_executor.py from trading_engine_v2.py (~330 lines)
- Add comprehensive housekeeping progress tracker
- Document STEP 3 completion plan for trading_engine_v2.py refactoring
- STEP 3.2: Extract order_logger.py from trading_engine_v2.py (119 lines)
- STEP 3.1: Extract position_manager.py from trading_engine_v2.py (99 lines)
- STEP 2.FINAL: Refactor main.py - split into 5 routers (1658 → 133 lines)
- STEP 2.5: Extract system_router.py from main.py (207 lines)
- STEP 2.4: Extract settings_router.py from main.py (159 lines)
- STEP 2.3: Extract market_data_router.py from main.py (196 lines)
- STEP 2.2: Extract account_router.py from main.py (371 lines)
- STEP 2.1: Extract positions_router.py from main.py (769 lines)
- STEP 1.9: Rename original ai_autonomous.py to _OLD_BACKUP.py
- STEP 1.8b: Create main __init__.py to wire all extracted modules together
- STEP 1.8a: Extract strategy_definition.py (230 lines) from ai_autonomous.py
- STEP 1.7: Extract trading_decisions.py module (buy/sell/DCA logic)
- STEP 1.6: Extract market_analysis.py module (market context, web search, caching)
- STEP 1.5: Extract Grok API provider module
- STEP 1.4: Extract Gemini API provider module
- STEP 1.3: Extract Claude API provider module
- STEP 1.2: Extract prompts.py module with all prompt templates
- STEP 1.1: Create ai_autonomous/ directory structure
- Add detailed refactoring plan with 13 steps and risk assessment
- Add HOUSEKEEPING.md documentation for refactoring work
- Fix Portfolio BTC Balance Breakdown calculation
- Add trade statistics columns to Bots table
- Phase 3.1: Add overall PnL to Holdings table
- Phase 2.3 (Part 2): Complete bot limit order close execution logic
- Phase 2.3 (Part 1): Add bot limit order close configuration
- Add AI bot API credit indicators
- Add market close slippage warnings
- Fix: Move Pydantic model definitions before endpoint usage
- Add budget utilization percentage to bot cards
- Add deployment notes for v1.5.0 database migration

## [v0.75.0] - 2025-11-23

- Add limit order monitoring background service
- Add limit order status display and edit/cancel UI
- Add limit close modal UI with bid/ask slider
- Add limit order position closing - backend implementation
- Fix Portfolio BTC Balance Breakdown calculations

## [v0.74.3] - 2025-11-22

- Add cryptocurrency icons to Positions page

## [v0.74.2] - 2025-11-22

- Add sub-badges to Closed and Failed tabs in History page
- Rewrite badge logic to use simple count delta
- Add 1ms to most recent timestamp to properly clear badge
- Fix badge clear to use most recent position timestamp
- Add debug logging for badge count calculation
- Fix History tab badge timer infinite loop

## [v0.74.1] - 2025-11-22

- Suppress React Router v7 future flag warnings
- Add 2% minimum drop requirement for DCA safety orders
- updated to ignore yet another naming convention for db backups :-/

## [v0.74.0] - 2025-11-22

- Add USD value display next to BTC volume in Positions page

## [v0.73.0] - 2025-11-22

- Fix closed positions main table timestamps to use local timezone
- Convert History page timestamps to local timezone

## [v0.72.0] - 2025-11-22

- Add URL-based routing with React Router
- Add BTC/USD price display to header with 2-minute updates
- Show AI reasoning from most recent buy decision onwards
- Add position_id filter to AI bot logs API endpoint
- Link AI decision logs to positions after position creation

## [v0.71.0] - 2025-11-22

- Fix session corruption in batch AI decision logging by expunging failed positions instead of rollback
- Fix duplicate timestamp error in P&L chart by deduplicating data points
- Fix SQLAlchemy async session corruption in AI decision logging
- Fix budget calculation bug preventing bots from scanning for new opportunities
- Fix aggregate BTC calculation to include positions from database

## [v0.70.0] - 2025-11-22

- Use portfolio breakdown for aggregate BTC calculation to include all positions (even those in open trades)
- Fix aggregate BTC calculation by forcing fresh account data + document BTC bot budget rules in CLAUDE.md
- Make aggregate BTC calculation logs visible by changing to logger.warning()
- Add CRITICAL budget calculation documentation to CLAUDE.md
- Fix budget calculation logging visibility - change INFO to WARNING level
- Add Force Run feature for bots
- Use bot's actual budget_percentage in logs instead of hardcoded 90%
- Fix budget calculation: aggregate should be total account BTC value, not just available balance
- Fix double-subtraction bug in budget calculation - available balance already excludes positions
- Remove caching from get_btc_balance() to always fetch fresh balance
- Add Python bytecode cache clearing to bot.sh start/restart commands
- Simplify calculate_aggregate_btc_value to return actual BTC balance
- Fix aggregate BTC calculation to include BTC + BTC pairs only
- Simplify aggregate BTC calculation to use actual BTC balance
- Temporarily disable aggregate BTC cache to debug balance calculation
- Add debug logging to aggregate BTC value calculation
- Fix Coinbase API rate limiting (429 errors) with caching and retries
- Add fallback to get_accounts() when portfolio endpoint returns 403
- Fix budget calculation and config refresh bugs
- Add fallback to get_accounts() when portfolio endpoint returns 403
- Add debugging for History page badge auto-clear timer
- Create backend/scripts folder for one-off helper scripts
- Add auto-clearing timer to History page notification badge
- Trigger immediate re-analysis after position closes
- Fix order fill race condition with retry mechanism
- Fix double budget division bug in trading engine
- Fix critical database session bug preventing batch trades
- Fix double budget division causing orders below Coinbase minimum
- Add debug prints to _get_confidence_threshold_for_action to diagnose threshold issue
- Add debug prints for Grok batch analysis
- Add debug prints to see signal_data in should_buy()
- Add debug prints for budget calculation and should_buy logic
- Add debug prints for result processing loop to find exact hang point
- Add detailed debug prints in process_bot and process_bot_batch to find hang location
- Add debug prints in bot processing loop to find where it hangs
- Add comprehensive debug prints throughout monitor loop
- Use print() instead of logger for debugging - logger not showing in journalctl
- Add debug logging to diagnose why monitor loop isn't running
- Handle 403 rate limit errors gracefully with budget fallback
- Remove debug prints - monitor loop now working correctly
- Add debug prints throughout monitor loop
- Add more debug prints in monitor_loop
- Add debug prints to diagnose monitor loop not starting
- Fix multi-bot monitor not starting - AI bots now trade
- Remove unused bot-level AI Analysis Interval field
- Allow AI Analysis Interval range of 1-1440 minutes instead of 5-120
- Add database backups and temporary test scripts to .gitignore
- Fix execute_buy() to use actual filled amounts from Coinbase
- Reduce sell amount to 99% to handle discrepancy between tracked and actual balances
- Adjust bar chart margins to prevent top-squishing
- Restructure layout to match 3Commas time filter and chart tabs
- Make chart height match sidebar cards height
- Fix chart disposal error when navigating away from Bots page
- Add 'Most profitable bot' card and active trades count
- Improve bar chart tooltips to match 3Commas style
- Restructure P&L chart with sidebar stats like 3Commas
- Fix Summary PnL chart not displaying after switching tabs
- Add daily P&L bar chart for 'PnL by day' tab
- Replace P&L by pair table with bar chart
- Fix P&L endpoint route order - move before {position_id} route
- Add 3Commas-style P&L chart with comprehensive analytics
- Add professional loading spinners to improve UX
- Fix budget allocation to use max_concurrent_deals instead of pair count
- Fix force-close position to use profit_quote instead of profit_btc
- Add automatic deployment system
- Test backend auto-restart
- Test auto-deployment system
- Add deployment script for pulling from git on EC2
- Add percentage gains to Portfolio Totals on Bots page
- Add budget-aware bot monitoring and insufficient funds indicator
- Add red badge to History tab showing new closed positions
- Make site mobile-friendly with responsive layouts
- Add projected PnL display to Bots page
- Update risk tolerance confidence thresholds
- Fix React controlled input warnings in Bots.tsx
- Fix bot stats 500 error and frontend format crash
- Add OpenAI library and document AI strategy dependencies
- Upgrade Anthropic SDK to 0.74.0 to fix AsyncClient initialization error
- Add adaptive AI evaluation intervals and risk-based confidence thresholds
- Pass position and action context to strategy for intelligent web search
- Add DCA arrows to position chart and synthetic candles for entry timing
- Fix bot-macos.sh to only kill server processes, not browser connections
- Create unified AI prompt templates and add bot PnL tracking
- Give AI full control over sell decisions for autonomous bots
- Fix trade type labels: show 'Take Profit' for sell orders instead of 'DCA'
- Add macOS-compatible bot manager script
- Extend AI log time window to include 30s after position close
- Add backfill script to link existing AI logs to positions
- Add expandable closed positions with trade details, duration, and AI reasoning history
- Add failed order tracking and fix portfolio accuracy
- Add batch price endpoint and optimize frontend price fetching
- Add 10 second timeout to Vite API proxy
- Revert to simple f-string formatting that worked for base orders
- Fix API connection by using Vite proxy instead of direct backend URL
- Configure backend to use port 8100, frontend stays on 5173
- Revert frontend to use backend on port 8000
- Update frontend to use backend port 8100
- Fix Coinbase precision - use fixed-width decimal formatting
- Fix limit_price precision and remove hardcoded dev paths
- Consolidate Coinbase API clients into unified implementation
- Apply precision formatting to legacy CoinbaseClient as well
- Fix PREVIEW_INVALID_QUOTE_SIZE_PRECISION error by applying proper precision formatting
- Add retry logic and error tracking for market data failures
- Fix DCA order precision to avoid Coinbase PREVIEW_INVALID_QUOTE_SIZE_PRECISION error
- Fix DCA order size calculation to use position's initial balance
- Update bot.sh to use systemctl for service management
- Fix sell order execution by properly handling Coinbase API response
- Add minimum order size validation warnings to bot creation modal
- Fix import error - use CoinbaseClient directly
- Add minimum order size validation
- Add detailed branch workflow and cleanup instructions
- Add comprehensive development roadmap
- Consolidate documentation into /docs folder
- Fix Coinbase quote size precision error
- Fix TypeScript linting errors
- Improve Coinbase error message extraction
- Add notes and error fields to PositionResponse schema
- Add position notes feature (like 3Commas)
- Add position error tracking and display (like 3Commas)
- Add detailed Coinbase error logging for failed orders
- Fix DCA not triggering due to missing current_price in batch mode
- Fix duplicate AI log entries for batch analysis
- Add comprehensive debug logging to track duplicate AI opinion source
- Fix REAL cause of duplicate AI opinions - double monitor loop start
- Document duplicate AI opinions race condition fix in HANDOFF.md
- Fix duplicate AI opinions race condition
- Extract API_BASE_URL to centralized config
- Add 3Commas-style manual vs automatic DCA tracking
- Document DCA greenlet fix and API rate limit optimization
- Fix greenlet error preventing DCA order evaluation
- Add close position confirmation modal with proper warnings
- Document pending frontend work and known issues in HANDOFF
- Wire up position action buttons with proper handlers
- Improve bot monitoring responsiveness and database stability
- Sell 99.99% to prevent precision/rounding rejections
- Fix critical bug: Require order_id for buy/sell trades
- Integrate order monitor into MultiBotMonitor
- Fix duplicate AI log entries for batch analysis
- Add AI sentiment indicators and DCA visualization, fix bugs
- Add ESC key handler to close bot config modal
- Only show 'All' buttons for markets with available pairs
- Hide unavailable markets instead of graying them out
- Implement 3Commas-style single-market constraint for pair selection
- Reorganize bot configuration form into numbered sections
- Add 3Commas-style pair selection and interval configuration
- Fix Dashboard BotCard profit display error
- Add comprehensive PnL stats broken down by USD/BTC
- Refactor charts: separate oscillator panes with synchronized time scales
- Improve chart indicators: add priceScaleId and MACD/RSI enhancements
- Fix duplicate Entry/Target labels when changing chart type
- Fix price axis disappearing when switching to Heikin-Ashi
- Re-add indicator rendering functionality
- Fix chart: remove stop loss line and use actual profit target from config
- Use actual profit target from bot config instead of hardcoded 2%
- Remove stop loss reference line from chart (not used in strategy)
- Implement full indicator rendering system for TradingView charts
- Fix chart not displaying: use correct 'time' field from API
- Fix chart NaN error by filtering invalid candle data
- Adjust sell confidence threshold to 65%
- Lower AI sell confidence threshold to 50%
- Raise AI confidence threshold to 80% for all trades
- Fix AI ambivalence by adding temperature=0 to all AI calls
- Add order monitoring service for limit orders
- Add limit order support to trading engine
- Add pending_orders_count to API and frontend (Part 3 - Final)
- Add safety_order_type configuration parameter (Part 2)
- Add pending_orders system for limit order tracking (Part 1)
- Fix averaging orders (Avg. O) display to match 3Commas logic
- Add lightweight chart modal option with full programmatic control
- Add position reference prices to chart modal header
- Prevent background page scroll when chart modal is open
- Fix TradingView widget cleanup error on modal close
- Fix TradingView widget initialization error
- Add TradingView chart integration to Active Deals page
- Feature: Add clickable sorting to table column headers
- UX: Add 3Commas-style overall stats panel and simplified filters
- UX: Add 3Commas-style column headers to deals table
- Fix: Display base currency correctly in Volume column
- UX: Remove redundant coin amount from Filled percentage line
- UX: Add smart collision detection for price bar labels
- UX: Redesign price bar to match 3Commas with vertical tick marks
- Fix: Close unclosed Active Deals Section div and fix ternary operator
- Fix: Remove duplicate JSX code causing TypeScript compilation errors
- Major UX: Transform deal cards to 3Commas-style horizontal layout
- Feature: Add 3Commas-style tick marks with labels on Price Movement bar
- Feature: Add 3Commas-style dynamic labels to Price Movement bar
- Fix: Dynamic range for Price Movement bar visualization
- Fix: Use get_current_price() for ticker endpoint
- Fix: Align chart P&L calculation with main position P&L display
- Fix: Resolve greenlet async error (xd2s) in AIBotLog database operations
- Fix: Resolve AIBotLog SQLAlchemy error (7s2a) by fixing context field duplication
- Lint: Fix final architectural errors (E402, F401)
- Lint: Fix all remaining linting errors (E712, F841, F821, E722)
- Lint: Apply Python best practices and fix linting errors
- Fix: Move formatPrice utility to top level to fix DealChart scope error
- Refactor: Migrate to StrategyTradingEngine and remove old TradingEngine
- cleanup: Remove unused price_monitor.py file
- Refactor: Extract middleware to separate module
- docs: Update HANDOFF.md with Step 2 (schema extraction) completion
- Refactor: Extract Pydantic schemas to centralized schemas module
- docs: Update HANDOFF.md with Phase 1 modularization progress
- Refactor: Extract shared indicator utilities to eliminate code duplication
- Restore full Positions.tsx with all features lost in merge
- Restore Gain/Loss metadata line to position charts
- Housekeeping: Clean up old files and improve gitignore
- Fix: Replace totalProfitBTC with totalProfitQuote in Dashboard
- Fix: Update Positions.tsx field names for multi-currency support
- Fix: Re-apply timezone-aware date formatting to Positions page after merge
- Complete bot balance isolation system and fix portfolio/timezone issues
- Add modular multi-quote currency support (BTC + USD) - Phase 1
- Move closed positions to separate History page
- Update price indicator label from 'Entry' to 'Avg Entry'
- Add visual price movement indicator to position cards
- Fix Current Profit showing 0% in compact position view
- Fix USD currency display in positions/deals
- Fix frontend display of USD prices in AI Bot Logs
- Fix USD price display formatting in AI logs
- Fix Grok model name and implement Claude batch analysis
- Use candle data for current price instead of unreliable ticker API
- Fix AI bot logging to only process pairs with valid market data
- Fix AI Bot price data collection for batch analysis
- Enhance DealChart with full Charts page functionality
- Add bot name display to position details
- Fix hardcoded currency symbols in position details
- Fix crypto price precision for AI analysis
- Fix KeyError when candles are empty
- Add Grok support + optimize batch analysis for position quota
- Add Grok AI support with batch analysis
- WIP: Add batch AI analysis for multi-pair bots
- Add per-bot check_interval with AI provider-specific defaults
- Add position-specific AI logs modal
- Fix API quota issues - increase monitor interval to 10min and fix middleware
- Fix price display in AI logs and add product_id to positions
- Fix critical trade execution bug - trades now execute successfully
- Add transaction rollback: positions only persist if trade succeeds
- Update handoff: Monitor likely not starting - key hypothesis identified
- Add comprehensive handoff document for trade execution bug investigation
- Add debug logging to trace trade execution failure
- Fix critical database transaction conflicts preventing trades
- Add product_id to AI bot logs API response
- Add profit calculation method option (cost_basis vs base_order)
- Fix product_id bug and implement parallel batch processing
- Fix division by zero error in AI autonomous strategy
- Fix AI logs to show AI's actual recommendation, not bot's action
- Change hold icon from Minus to CircleDot for better clarity
- Add trading pair to AI logs + UI improvements
- Fix AI autonomous bot analysis and reasoning logs
- Implement smart budget division by max concurrent deals
- Add max concurrent deals and AI provider display
- Update checklist: Mark AI features and 3Commas UI as complete
- Add AI provider API key fields to Settings config
- Add AI provider selection, dynamic trading pairs, and 3Commas-style UI
- Final session update: Mark all completed features in checklist
- Add AI bot reasoning logs and custom instructions
- Update checklist: mark clone bots and AI log infrastructure as complete
- Add Clone Bots and AI Reasoning Log features
- Fix: Stopped bots now continue managing existing positions
- Update checklist: mark trailing TP/SL as complete
- Add proper trailing take profit and trailing stop loss
- Add .claude/ and .pids/ to gitignore
- Update README with AI bot and all new features
- Add comprehensive handoff document for laptop migration
- Add AI Autonomous Trading Bot powered by Claude AI
- Update checklist: mark bot templates as complete
- Add bot templates system with default presets
- Update checklist: mark multi-pair bots and budget splitting as complete
- Add budget splitting option for multi-pair bots
- Add multi-pair bot UI - frontend implementation
- WIP: Multi-pair bots backend implementation
- Update checklist with recent completed features
- Fix bot Edit button not working on Dashboard
- Add real-time price updates to Deals page
- Add safety order price level visualization to deal charts
- Add Take Profit and Stop Loss lines to deal charts
- Update settings
- Add multi-pair bots to roadmap as critical 3Commas feature
- Update checklist with dashboard overhaul completion
- Overhaul Dashboard with 3Commas-style metrics and recent deals
- Add product_id tracking to positions for accurate chart display
- Implement 3Commas-style DCA bot platform with full deal management
- Add crossing above/below operators to all applicable indicators
- Refactor to true 3Commas-style phase-based conditions
- Add comprehensive user guide for conditional strategy builder
- Implement 3Commas-style conditional DCA strategy system
- Add Heikin-Ashi candle option to Charts page
- Implement advanced charting with TradingView-style indicators
- Fix chart error handling and port management
- Fix lightweight-charts v5 API - use correct method names
- Add comprehensive documentation
- Fix lightweight-charts v5 API compatibility
- Initial commit: ETH/BTC trading bot with TradingView-style charts

