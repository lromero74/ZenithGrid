# Development Roadmap & Next Steps
**Created:** November 17, 2025
**Status:** Active Development Plan
**Last Updated:** November 17, 2025

---

## 📋 How to Use This Document

This roadmap tracks the prioritized development tasks for the trading bot platform. As you complete each item:

1. ✅ Change the status from ⏳ (Planned) to ✅ (Complete)
2. Add implementation notes under the item
3. Note the commit hash and date completed
4. Move completed sections to the bottom under "Completed Items"

---

## 🔥 Phase 1: High Priority Features (Next Milestone)

### 1. Notifications/Alerts System ⏳

**Priority:** Critical
**Estimated Effort:** Medium (2-3 days)
**Status:** Not Started

**Requirements:**
- [ ] Deal opened notifications
- [ ] Deal closed notifications (with profit/loss)
- [ ] Take profit hit alerts
- [ ] Stop loss hit alerts
- [ ] Safety order filled alerts
- [ ] Bot error notifications
- [ ] Browser push notifications support
- [ ] In-app notification center
- [ ] Notification preferences (enable/disable per type)
- [ ] Sound alerts (optional)

**Implementation Plan:**
1. **Backend:**
   - Create `Notification` model (user_id, type, message, read_status, timestamp)
   - Add notification creation in trading engine after key events
   - Create `/api/notifications` endpoints (GET, PATCH mark as read, DELETE)
   - Add SSE (Server-Sent Events) or WebSocket for real-time push

2. **Frontend:**
   - Create notification bell icon in header with badge count
   - Build notification dropdown/panel
   - Implement browser notification API integration
   - Add notification settings page
   - Sound notification system (optional)

3. **Testing:**
   - Test all notification types trigger correctly
   - Verify real-time delivery
   - Test browser notification permissions

**Files to Create/Modify:**
- `backend/app/models.py` - Add Notification model
- `backend/app/notifications.py` - Notification service
- `backend/app/routers/notifications.py` - API endpoints
- `backend/app/trading_engine_v2.py` - Trigger notifications on events
- `frontend/src/components/NotificationBell.tsx` - Notification UI
- `frontend/src/pages/NotificationSettings.tsx` - Settings page

**Notes:**
- Consider email notifications as Phase 2
- Browser notifications require user permission
- SSE is simpler than WebSocket for one-way notifications

---

### 2. Dashboard Analytics ⏳

**Priority:** High
**Estimated Effort:** Medium (2-3 days)
**Status:** Not Started

**Requirements:**
- [ ] Total profit metrics (24h, 7d, 30d, all time)
- [ ] Active deals count prominently displayed
- [ ] Total deals count (all time)
- [ ] Win rate calculation and display
- [ ] Best performing bot stats
- [ ] Worst performing bot stats
- [ ] Account value chart over time
- [ ] Profit/loss chart over time
- [ ] Recent activity feed (last 10 events)

**Implementation Plan:**
1. **Backend:**
   - Add `/api/dashboard/stats` endpoint with time-based aggregations
   - Calculate profit by time period (SQL queries with date filters)
   - Add account value history tracking (new table or extend existing)
   - Calculate per-bot statistics

2. **Frontend:**
   - Create stat cards with trend indicators (↑↓)
   - Build account value line chart (Recharts or Lightweight Charts)
   - Build profit/loss chart by day/week/month
   - Add time period selector (24h, 7d, 30d, all)
   - Create recent activity timeline

3. **Data Model:**
   - Consider `AccountValueSnapshot` table (timestamp, btc_value, usd_value)
   - Track daily for historical charts

**Files to Create/Modify:**
- `backend/app/routers/dashboard.py` - Enhanced dashboard endpoint
- `backend/app/models.py` - AccountValueSnapshot model (optional)
- `frontend/src/pages/Dashboard.tsx` - Add analytics components
- `frontend/src/components/StatCard.tsx` - Stat card component
- `frontend/src/components/ProfitChart.tsx` - Chart component

**Notes:**
- Cache expensive calculations (daily profit, etc.)
- Consider background job to snapshot account value daily
- Use existing closed positions data for historical profit

---

### 3. Performance Analytics ⏳

**Priority:** High
**Estimated Effort:** Medium-Large (3-4 days)
**Status:** Not Started

**Requirements:**
- [ ] Per-bot profit/loss tracking and display
- [ ] Per-pair profit/loss analysis
- [ ] Average deal duration (by bot, by pair)
- [ ] Average profit per deal
- [ ] Max drawdown calculation
- [ ] Sharpe ratio (risk-adjusted returns)
- [ ] Win rate per bot/pair
- [ ] Total fees paid tracking
- [ ] ROI calculations

**Implementation Plan:**
1. **Backend:**
   - Create `/api/analytics/bots` endpoint
   - Create `/api/analytics/pairs` endpoint
   - Implement statistical calculations:
     - Average deal duration: `AVG(closed_at - opened_at)`
     - Average profit: `AVG(profit_btc)` grouped by bot/pair
     - Max drawdown: Track running max value and calculate largest drop
     - Sharpe ratio: `(avg_return - risk_free_rate) / std_dev_returns`
   - Add caching for expensive calculations

2. **Frontend:**
   - Create Analytics page (new tab)
   - Bot performance table with sortable columns
   - Pair performance table
   - Visual charts for key metrics
   - Comparison view (compare multiple bots)

3. **Database:**
   - May need to track additional metadata on positions
   - Consider materialized views for complex calculations

**Files to Create/Modify:**
- `backend/app/routers/analytics.py` - New analytics router
- `backend/app/analytics.py` - Calculation functions
- `frontend/src/pages/Analytics.tsx` - New analytics page
- `frontend/src/components/BotPerformanceTable.tsx`
- `frontend/src/components/PairPerformanceTable.tsx`

**Notes:**
- Sharpe ratio requires risk-free rate assumption (use 0% or treasury rate)
- Max drawdown needs careful calculation across all positions
- Consider daily cron job to pre-calculate expensive metrics

---

## 📊 Phase 2: Important Features

### 4. Import/Export Bot Configurations ⏳

**Priority:** Medium-High
**Estimated Effort:** Small-Medium (1-2 days)
**Status:** Not Started

**Requirements:**
- [ ] Export single bot to JSON file
- [ ] Export all bots to JSON file
- [ ] Import bot from JSON file
- [ ] Validation on import (check required fields)
- [ ] Import with new name (avoid conflicts)
- [ ] Share bot templates between users
- [ ] Template marketplace (future enhancement)

**Implementation Plan:**
1. **Backend:**
   - Add `GET /api/bots/{id}/export` endpoint
   - Add `GET /api/bots/export-all` endpoint
   - Add `POST /api/bots/import` endpoint
   - Validation logic for imported configs
   - Handle strategy_config JSON properly

2. **Frontend:**
   - Add "Export" button in bot cards (... menu)
   - Add "Export All" button in Bots page header
   - Add "Import Bot" button with file picker
   - File download using browser APIs
   - Import preview before confirmation

**JSON Format:**
```json
{
  "version": "1.0",
  "bot": {
    "name": "My Bot",
    "description": "...",
    "strategy_type": "conditional_dca",
    "product_ids": ["ETH-BTC"],
    "strategy_config": {...}
  }
}
```

**Files to Create/Modify:**
- `backend/app/routers/bots.py` - Add export/import endpoints
- `frontend/src/pages/Bots.tsx` - Add import/export UI
- `frontend/src/components/BotImportModal.tsx` - Import preview modal

---

### 5. Multiple Take Profit Targets ⏳

**Priority:** Medium
**Estimated Effort:** Medium-Large (3-4 days)
**Status:** Not Started

**Requirements:**
- [ ] Configure multiple TP levels (e.g., 2% for 50%, 5% for 50%)
- [ ] Partial position closing
- [ ] Ladder-style profit taking
- [ ] Track remaining position size
- [ ] Update average buy price after partial sells
- [ ] UI to configure TP ladder
- [ ] Visual representation in charts

**Implementation Plan:**
1. **Database:**
   - Modify Position model:
     - `initial_base_acquired` (total bought)
     - `remaining_base_amount` (not yet sold)
   - Track partial sells in trades table

2. **Backend:**
   - Update strategy_config to support TP array:
     ```json
     {
       "take_profit_targets": [
         {"percentage": 2.0, "amount_pct": 50},
         {"percentage": 5.0, "amount_pct": 50}
       ]
     }
     ```
   - Update trading engine sell logic to handle partial sells
   - Recalculate position status after each partial sell

3. **Frontend:**
   - TP ladder configuration UI
   - Show remaining position vs sold
   - Chart markers for multiple TP levels

**Files to Create/Modify:**
- `backend/app/models.py` - Modify Position model
- `backend/app/trading_engine_v2.py` - Partial sell logic
- `backend/app/strategies/conditional_dca.py` - Multi-TP support
- `frontend/src/pages/Bots.tsx` - TP ladder config UI
- `frontend/src/pages/Positions.tsx` - Show partial sells

**Notes:**
- Complex feature, may need careful testing
- Consider how this interacts with trailing TP
- Position status needs new states: "partially_closed"

---

### 6. Position Management Enhancements ⏳

**Priority:** Medium
**Estimated Effort:** Small-Medium (2 days)
**Status:** Not Started

**Requirements:**
- [ ] Cancel deal (if no orders filled yet)
- [ ] Modify take profit % on open positions
- [ ] Modify stop loss % on open positions
- [ ] View position on Coinbase exchange (direct link)
- [ ] Manual DCA buy button
- [ ] Edit position notes

**Implementation Plan:**
1. **Backend:**
   - `POST /api/positions/{id}/cancel` - Only if no trades
   - `PATCH /api/positions/{id}/take-profit` - Update TP target
   - `PATCH /api/positions/{id}/stop-loss` - Update SL target
   - Validation: can't modify closed positions

2. **Frontend:**
   - Add buttons in position card actions
   - Confirmation modals for modifications
   - Input validation (TP must be > current price for longs)
   - "View on Coinbase" link (construct URL from product_id)

**Files to Create/Modify:**
- `backend/app/routers/positions.py` - New endpoints
- `frontend/src/pages/Positions.tsx` - Add action buttons

**Coinbase URL Format:**
```
https://www.coinbase.com/advanced-trade/spot/{product_id}
Example: https://www.coinbase.com/advanced-trade/spot/ETH-BTC
```

---

## 🎨 Phase 3: UI/UX Improvements

### 7. Filtering & Export ⏳

**Priority:** Medium
**Estimated Effort:** Small-Medium (2 days)
**Status:** Not Started

**Requirements:**
- [ ] Filter closed deals by bot
- [ ] Filter by profit range (e.g., show only profitable)
- [ ] Filter by loss range
- [ ] Filter by date range
- [ ] Export deal history to CSV
- [ ] Export trade history to CSV
- [ ] Tax reporting (CSV with cost basis)

**Implementation Plan:**
1. **Backend:**
   - Enhance `/api/positions` with query params:
     - `bot_id`, `min_profit`, `max_profit`, `start_date`, `end_date`
   - Add `/api/positions/export` endpoint (CSV format)
   - Add `/api/trades/export` endpoint
   - Tax report format: Date, Type, Amount, Price, Cost Basis, Gain/Loss

2. **Frontend:**
   - Filter panel above closed positions table
   - Date range picker
   - Bot selector dropdown
   - Profit/loss range sliders
   - Export buttons (CSV download)

**CSV Format Example:**
```csv
Date,Bot,Pair,Entry Price,Exit Price,Profit BTC,Profit %,Profit USD
2025-11-15,Bot 1,ETH-BTC,0.034,0.035,0.001,2.94,75.00
```

**Files to Create/Modify:**
- `backend/app/routers/positions.py` - Add filtering and export
- `frontend/src/pages/Positions.tsx` - Add filter UI
- `frontend/src/components/FilterPanel.tsx` - Filter component

---

### 8. UI Polish ⏳

**Priority:** Low-Medium
**Estimated Effort:** Medium (2-3 days)
**Status:** Not Started

**Requirements:**
- [ ] Mobile responsive design (all pages)
- [ ] Dark/light theme toggle
- [ ] Keyboard shortcuts (e.g., 'n' for new bot)
- [ ] Advanced filtering on all pages
- [ ] Favorites/pinned trading pairs
- [ ] Search/filter pairs in selection dropdowns
- [ ] Loading skeletons instead of spinners
- [ ] Toast notifications for actions

**Implementation Plan:**
1. **Theme System:**
   - Use Tailwind dark mode classes
   - Theme context provider
   - Persist preference in localStorage

2. **Mobile Responsive:**
   - Test all pages on mobile viewport
   - Adjust layouts for small screens
   - Mobile-friendly modals and dropdowns

3. **Keyboard Shortcuts:**
   - Global keyboard event listener
   - Shortcut overlay (press '?' to show)
   - Common shortcuts: n (new bot), / (search), esc (close modal)

4. **Pair Management:**
   - Favorites stored in localStorage or user preferences
   - Star icon to favorite/unfavorable
   - Filter to show only favorites
   - Search input in pair selector

**Files to Create/Modify:**
- `frontend/src/contexts/ThemeContext.tsx` - Theme provider
- `frontend/src/hooks/useKeyboardShortcuts.ts` - Shortcuts hook
- `frontend/src/components/ShortcutOverlay.tsx` - Help overlay
- Multiple CSS/Tailwind updates for dark mode

---

## 🔧 Phase 4: Technical & Infrastructure

### 9. Code Quality ⏳

**Priority:** Medium (Ongoing)
**Estimated Effort:** Large (ongoing effort)
**Status:** Not Started

**Requirements:**
- [ ] Unit tests for backend services
- [ ] Unit tests for frontend components
- [ ] Integration tests for API endpoints
- [ ] E2E tests for critical user flows
- [ ] Error boundary components in React
- [ ] Improved logging framework (structured logs)
- [ ] Performance monitoring (APM)
- [ ] Code coverage reporting

**Implementation Plan:**
1. **Backend Testing:**
   - Use pytest for unit tests
   - Test each strategy independently
   - Test trading engine logic
   - Mock Coinbase API calls
   - Integration tests with test database

2. **Frontend Testing:**
   - Use Vitest + React Testing Library
   - Test critical components
   - Test API integration layer
   - Snapshot tests for UI components

3. **CI/CD:**
   - GitHub Actions workflow
   - Run tests on PR
   - Automated deployment on merge to main

**Files to Create:**
- `backend/tests/` - Test directory
- `frontend/src/__tests__/` - Test directory
- `.github/workflows/test.yml` - CI workflow
- `pytest.ini` - Pytest configuration
- `vitest.config.ts` - Vitest configuration

---

### 10. Infrastructure ⏳

**Priority:** Medium
**Estimated Effort:** Medium (2-3 days)
**Status:** Not Started

**Requirements:**
- [ ] Formal database migrations (Alembic)
- [ ] Automated backup system
- [ ] Restore from backup functionality
- [ ] API rate limiting
- [ ] System health monitoring
- [ ] Alerting for system errors
- [ ] Multiple exchange support (architecture)
- [ ] Environment-based configuration

**Implementation Plan:**
1. **Alembic Migrations:**
   - Initialize Alembic
   - Create initial migration from current schema
   - Update deployment to run migrations
   - Document migration workflow

2. **Backup System:**
   - Daily cron job to backup SQLite database
   - Backup to S3 or local disk with rotation
   - Restore script with verification
   - Test restore process

3. **Rate Limiting:**
   - Use slowapi or custom middleware
   - Limit by IP address or API key
   - Different limits for different endpoints
   - Return 429 with Retry-After header

4. **Monitoring:**
   - Health check endpoint `/health`
   - Prometheus metrics export (optional)
   - Error tracking (Sentry integration)
   - Uptime monitoring (UptimeRobot, etc.)

**Files to Create/Modify:**
- `backend/alembic/` - Alembic directory
- `backend/alembic.ini` - Alembic config
- `scripts/backup.sh` - Backup script
- `scripts/restore.sh` - Restore script
- `backend/app/middleware/rate_limit.py` - Rate limiting
- `backend/app/routers/health.py` - Health check

---

## 🚀 Phase 5: Advanced Features (Future)

### 11. AI & Sentiment Analysis ⏳

**Priority:** Low (Future)
**Estimated Effort:** Large (5-7 days)
**Status:** Framework in place, needs implementation

**Requirements:**
- [ ] Twitter sentiment analysis integration
- [ ] News headline aggregation
- [ ] Reddit sentiment analysis (r/cryptocurrency)
- [ ] Fear & Greed Index integration
- [ ] Social trading / copy trading system
- [ ] Sentiment-based trading signals
- [ ] Sentiment dashboard visualization

**Implementation Plan:**
1. **Sentiment Sources:**
   - Twitter API v2 (requires approval)
   - News APIs (NewsAPI, CryptoCompare)
   - Reddit API (PRAW library)
   - Fear & Greed API (Alternative.me)

2. **Sentiment Analysis:**
   - Use AI to analyze text sentiment
   - Aggregate scores across sources
   - Weight by source credibility
   - Feed to AI autonomous bot

3. **Copy Trading:**
   - Track leader performance
   - Auto-copy bot configurations
   - Auto-mirror trades (optional)
   - Leaderboard system

**Notes:**
- Twitter API requires developer account approval
- Sentiment analysis is noisy - use as one signal among many
- Copy trading requires careful risk management

---

### 12. Additional Trading Features ⏳

**Priority:** Low (Future)
**Estimated Effort:** Large (varies by feature)
**Status:** Not Started

**Features:**
- [ ] Grid trading strategy
- [ ] Arbitrage bot (cross-exchange)
- [ ] Portfolio rebalancing
- [ ] Webhook integrations (TradingView alerts)
- [ ] Custom indicator development UI
- [ ] Backtesting framework
- [ ] Paper trading mode (simulated)
- [ ] Multi-exchange support (Binance, Kraken, etc.)

**Notes:**
- Each feature is a substantial project
- Prioritize based on user demand
- Multi-exchange requires abstraction layer

---

### 13. Limit Orders (Partially Complete) ⏳

**Priority:** Medium
**Estimated Effort:** Medium (2-3 days)
**Status:** Database and API partially complete

**Remaining Work:**
See `docs/LIMIT_ORDERS_TODO.md` for detailed plan:
- [ ] Update trading engine to support limit orders
- [ ] Create order monitoring service
- [ ] Frontend pending orders display
- [ ] Testing with real limit orders
- [ ] Cancel stale orders logic

**Next Steps:**
1. Implement `execute_limit_buy()` in trading engine
2. Create `OrderMonitorService` background task
3. Update frontend to show pending order count
4. Test with real orders on Coinbase

---

## ✅ Completed Items

*(Items will be moved here as they're completed)*

---

## 📝 Development Notes

### Priority System
- **Critical:** Blocks other work or severely impacts UX
- **High:** Important features that users are actively requesting
- **Medium:** Nice to have, improves experience
- **Low:** Future enhancements, not urgent

### Estimation Guide
- **Small:** < 1 day
- **Medium:** 1-3 days
- **Large:** 3-7 days
- **Very Large:** 1-2 weeks

### Workflow
1. Pick highest priority item that's ⏳ Planned
2. Create feature branch: `git checkout -b feature/item-name`
3. Implement with tests
4. Update this document with ✅ and notes
5. Create PR and merge to main
6. Move completed item to "Completed Items" section

### Branch Naming Convention
- `feature/notifications` - New features
- `fix/bug-name` - Bug fixes
- `refactor/component-name` - Code refactoring
- `docs/update-readme` - Documentation updates

---

**Last Updated:** November 17, 2025
**Next Review:** Check progress weekly, reprioritize as needed
