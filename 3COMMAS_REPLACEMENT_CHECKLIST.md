# 3Commas Replacement - Implementation Checklist

**Goal:** Complete feature parity with 3Commas DCA bot functionality, then extend beyond.

**Status Key:**
- ✅ Complete
- 🚧 In Progress
- ⏳ Planned
- ❌ Not Started

---

## Core Bot Features

### Bot Management
- ✅ Create bots with multiple strategy types
- ✅ Edit bots while running (3Commas style)
- ✅ Start/Stop bots
- ✅ Multiple bots running simultaneously
- ✅ Multi-pair bots (trade multiple pairs with one bot)
- ✅ Budget splitting toggle (divide percentages across pairs)
- ✅ Bot templates (presets and custom templates)
- ✅ Clone/duplicate bots
- ✅ 3Commas-style UI (toggle switches, ... menu)
- ⏳ Import/export bot configs

### Strategy Support
- ✅ Conditional DCA (custom conditions per phase)
- ✅ Multi-timeframe indicators per condition
- ✅ Base Order conditions
- ✅ Safety Order conditions
- ✅ Take Profit conditions
- ✅ Min profit threshold for conditional exits
- ✅ **AI Autonomous Trading** (Claude AI-powered)
- ✅ **AI Provider Selection** (Claude or Gemini)
- ✅ **AI Reasoning Log Viewer** (view AI decision history)
- ✅ **Custom AI Instructions** (guide AI behavior)
- ✅ **Trailing take profit** (tracks peak, sells on drop from peak)
- ✅ **Trailing stop loss** (follows price up, protects profits)
- ⏳ Multiple take profit targets
- ⏳ DCA strategy presets (Aggressive, Conservative, etc.)

### Indicators & Conditions
- ✅ RSI
- ✅ MACD
- ✅ Bollinger Bands %
- ✅ EMA
- ✅ SMA
- ✅ Stochastic
- ✅ Price action
- ✅ Crossing operators (above/below)
- ✅ AND/OR logic between conditions
- ⏳ Volume indicators
- ⏳ Custom indicator combos

---

## Deals (Positions) Management

### Active Deals Display
- ✅ Separate "Active Deals" section
- ✅ Real-time P&L display (% and $)
- ✅ Funds usage progress bar
- ✅ Safety order ladder view
- ✅ Base order + safety orders breakdown
- ✅ Deal expandable details
- ✅ Chart integration in deal view (with timeframe selector)
- ✅ Entry price line on chart (dashed blue)
- ✅ Entry marker on chart (green arrow)
- ✅ Current price marker on chart (blue dot)
- ✅ Price legend below chart
- ✅ Take profit target line on chart (green dashed, +2%)
- ✅ Stop loss line on chart (red dashed, -2%)
- ✅ Safety order price levels on chart (gray dashed lines)
- ✅ Real-time current price (updates every 5s)
- ✅ Live P&L calculations with real prices
- ⏳ Trailing indicators
- ⏳ Time in position

### Deal Actions
- ✅ Expandable deal details
- ✅ Close position (panic sell / force close at market price)
- ✅ Add funds (manual safety order with amount input)
- ✅ Confirmation dialogs for destructive actions
- ✅ Error handling and user feedback
- ⏳ Cancel deal (if no orders filled)
- ⏳ Modify take profit
- ⏳ Modify stop loss
- ⏳ View on exchange

### Closed Deals History
- ✅ Collapsible history section
- ✅ Profit/loss summary
- ✅ Date range display
- ⏳ Filtering by bot
- ⏳ Filtering by profit/loss
- ⏳ Export to CSV
- ⏳ Performance analytics

---

## Charts & Analysis

### Chart Display
- ✅ Multiple timeframes (1m, 5m, 15m, 30m, 1h, 2h, 6h, 1d)
- ✅ Candlestick charts
- ✅ Multiple chart types (bar, line, area, baseline)
- ✅ Heikin-Ashi candles
- ✅ Volume display
- 🚧 Auto-scaling to relevant price range
- ⏳ Entry price markers on chart
- ⏳ Take profit markers
- ⏳ Stop loss markers
- ⏳ Safety order price levels
- ⏳ Current position overlay
- ⏳ Chart in deal view (not just separate page)

### Technical Indicators
- ✅ SMA with configurable period
- ✅ EMA with configurable period
- ✅ RSI with overbought/oversold zones
- ✅ MACD with histogram
- ✅ Bollinger Bands
- ✅ Stochastic Oscillator
- ✅ Multiple indicators simultaneously
- ✅ Indicator customization (colors, periods)
- ⏳ Indicator alerts/notifications

### Trading Pairs
- ✅ All Coinbase USD pairs available
- ✅ All Coinbase BTC pairs available
- ✅ Visual indicator (•) for held coins
- ✅ Grouped by quote currency
- ✅ Dynamic pair list from API
- ⏳ Favorites/pinned pairs
- ⏳ Search/filter pairs

---

## Portfolio Management

### Portfolio Display
- ✅ Total portfolio value (USD & BTC)
- ✅ All coin holdings displayed
- ✅ Individual coin values
- ✅ Portfolio allocation percentages
- ✅ Available vs held balances
- ✅ Sortable columns
- ✅ Real-time price updates (60s)
- ✅ Manual refresh button
- ✅ Chart view for each coin (USD & BTC pairs)
- ⏳ Portfolio history/performance
- ⏳ Profit/loss tracking
- ⏳ Asset allocation pie chart

### Caching & Performance
- ✅ Shared cache between components
- ✅ No refetch on page navigation
- ✅ Smart refresh intervals
- ✅ Manual refresh available
- ✅ Efficient API usage

---

## Dashboard

### Overview Stats
- ⏳ Total profit (all time)
- ⏳ Total profit (24h, 7d, 30d)
- ⏳ Active deals count
- ⏳ Total deals count
- ⏳ Win rate
- ⏳ Best/worst performing bot
- ⏳ Account value chart

### Recent Activity
- ⏳ Recent deal opens/closes
- ⏳ Recent trades
- ⏳ Bot status changes
- ⏳ Alerts/notifications

### Quick Actions
- ⏳ Quick start bot
- ⏳ Quick view active deals
- ⏳ Quick access to settings

---

## Settings & Configuration

### API Configuration
- ⏳ Coinbase API credentials
- ⏳ Test connection
- ⏳ Multiple exchange support prep

### Bot Defaults
- ⏳ Default DCA settings
- ⏳ Default risk settings
- ⏳ Default take profit %
- ⏳ Default stop loss %
- ⏳ Preferred pairs

### Notifications
- ⏳ Deal opened
- ⏳ Deal closed
- ⏳ Take profit hit
- ⏳ Stop loss hit
- ⏳ Safety order filled
- ⏳ Bot errors

### UI Preferences
- ✅ Page state persistence
- ✅ Chart settings persistence
- ⏳ Theme customization
- ⏳ Default views
- ⏳ Display preferences

---

## Safety & Risk Management

### Position Limits
- ⏳ Max concurrent deals per bot
- ⏳ Max total concurrent deals
- ⏳ Max funds per deal
- ⏳ Max funds total
- ⏳ Daily loss limits

### Safeguards
- ✅ Validation on bot creation
- ✅ Config validation on updates
- ⏳ Insufficient funds warnings
- ⏳ High risk warnings
- ⏳ Confirmation dialogs for destructive actions

---

## Data & Analytics

### Performance Metrics
- ⏳ Per-bot profit/loss
- ⏳ Per-pair profit/loss
- ⏳ Average deal duration
- ⏳ Average profit per deal
- ⏳ Max drawdown
- ⏳ Sharpe ratio
- ⏳ Risk-adjusted returns

### Reporting
- ⏳ Export deal history
- ⏳ Export trade history
- ⏳ Tax reporting
- ⏳ Performance reports

---

## 3Commas Feature Parity Checklist

### Must Have (Core)
- ✅ DCA bot with safety orders
- ✅ Multiple indicators per phase
- ✅ Multi-timeframe conditions
- ✅ Edit running bots
- ✅ Real-time deal tracking
- ✅ Safety order ladder
- ✅ Charts with price markers
- ✅ Panic sell (close position)
- ✅ Add funds (manual safety order)
- ✅ Trailing TP/SL

### Should Have (Important)
- ✅ Bot templates
- ✅ Clone bots (smart name incrementing)
- ⏳ Multiple exchanges
- ⏳ Notifications
- ⏳ Performance analytics
- ⏳ Risk limits

### Nice to Have (Enhancement)
- ⏳ Mobile responsive
- ⏳ Dark/light themes
- ⏳ Keyboard shortcuts
- ⏳ Advanced filtering
- ⏳ Custom indicators
- ⏳ Backtesting

---

## Beyond 3Commas (Future)

### Advanced Features
- ⏳ AI-powered signal generation
- ⏳ Sentiment analysis integration
- ⏳ Social trading / copy trading
- ⏳ Advanced order types
- ⏳ Grid trading
- ⏳ Arbitrage bots
- ⏳ Portfolio rebalancing
- ⏳ Webhook integrations

---

## Technical Debt & Improvements

### Code Quality
- ⏳ Add unit tests
- ⏳ Add integration tests
- ⏳ Error boundary components
- ⏳ Logging improvements
- ⏳ Performance monitoring

### Infrastructure
- ⏳ Database migrations
- ⏳ Backup/restore
- ⏳ Rate limiting
- ⏳ Monitoring/alerting
- ⏳ Documentation

---

## Recent Updates (2025-11-15)

### Completed This Session (Latest First):
1. ✅ **Dashboard Overhaul (3Commas Style)** 🌟
   - Total profit metrics (BTC & USD) with trend indicators
   - Win rate calculation with profitable/total ratio
   - Active deals count prominently displayed
   - Account value from portfolio
   - Recent deals table (last 5 deals)
   - Enhanced bot cards with Start/Stop quick actions
   - Per-bot profit and deal stats
   - Real-time updates every 5-10 seconds
   - **Branch: dashboard-overhaul** (ready for review)

2. ✅ **Position Product ID Tracking**
   - Added product_id column to Position model
   - Positions now store their trading pair (e.g., "SOL-USD", "ETH-BTC")
   - Charts in deal view now show correct pair
   - Removed hardcoded "ETH-BTC" limitation
   - Bot product_id automatically assigned to positions

2. ✅ **Deal Action Buttons (3Commas Critical Features)**
   - Close Position (panic sell) - Force close at market price
   - Add Funds modal with amount input
   - Confirmation dialogs for destructive actions
   - Real-time processing feedback
   - Error handling with user-friendly messages
   - Auto-refresh after actions complete

2. ✅ **3Commas-Style Deals Page**
   - Redesigned Positions page to match 3Commas "Deals" layout
   - Active deals prominently displayed at top
   - Collapsible closed position history
   - Safety order ladder with visual indicators
   - Funds usage progress bar
   - Real-time P&L display

3. ✅ **Inline Chart Integration**
   - Added charts directly in deal view (3Commas style)
   - Timeframe selector (5m, 15m, 30m, 1h, 4h, 1d)
   - Entry price line (blue dashed)
   - Entry marker (green arrow showing where position opened)
   - Current price marker (blue dot)
   - Price legend
   - Auto-scaling chart

4. ✅ **Edit Running Bots**
   - Removed restriction preventing edits to active bots
   - Now matches 3Commas behavior (edit anytime)
   - Changes apply to future signals only

5. ✅ **All Coinbase Trading Pairs**
   - Dynamic pair list from Coinbase API (368+ pairs)
   - Visual indicator (•) for coins in portfolio
   - Grouped by USD/BTC pairs

6. ✅ **Portfolio Caching & Performance**
   - Smart caching (no refetch on page navigation)
   - Manual refresh button
   - Shared cache across components

### Latest Session Completed (2025-11-15 Evening):
1. ✅ **Take Profit & Stop Loss Chart Lines**
   - Green dashed TP line at +2% above entry
   - Red dashed SL line at -2% below entry
   - Enhanced legend with color coding
   - **Branch: chart-tp-sl-lines** → merged to master

2. ✅ **Safety Order Price Level Visualization**
   - Gray dashed horizontal lines showing DCA ladder
   - Dynamically calculated from bot config (deviation, step scale, max orders)
   - Shows first 3 SO levels in legend + count
   - Adjusts based on bot's DCA strategy
   - **Branch: chart-safety-order-levels** (with real-time prices)

3. ✅ **Real-Time Price Updates**
   - New `/api/ticker/{product_id}` endpoint
   - Live prices fetching every 5 seconds
   - "Current Price" column in deal cards with ▲/▼ indicators
   - Accurate unrealized P&L using real-time data
   - Chart legend shows live current price
   - **Branch: chart-safety-order-levels** → merged to master

4. ✅ **Dashboard Edit Button Fix**
   - Fixed broken hash-based navigation
   - Proper state-based routing via onNavigate prop
   - Edit button now correctly navigates to Bots page
   - Committed directly to master

### Latest Features Completed (2025-11-15 Night):
1. ✅ **MULTI-PAIR BOTS** 🌟 Critical 3Commas feature
   - Backend: bot → multiple positions (one per pair)
   - Signal evaluation runs independently for each pair
   - Position tracking includes product_id for correct chart display
   - Trading engine filters by both bot_id AND product_id
   - **Branch: multi-pair-backend** → merged to master

2. ✅ **Multi-Pair Bot UI**
   - Checkbox multi-select for trading pairs
   - Shows all selected pairs in bot cards
   - Backward compatible with single-pair bots
   - Validation requires at least one pair
   - **Branch: multi-pair-ui** (initial commit) → merged to master

3. ✅ **Budget Splitting Toggle**
   - Optional per-bot setting to divide budget across pairs
   - When enabled: divides base_order_percentage, safety_order_percentage, max_btc_usage_percentage by number of pairs
   - When disabled: each pair gets full budget independently (3Commas default)
   - UI shows clear explanations and calculated percentages
   - Example: 30% max with 3 pairs → 10% per pair (safe) vs 90% total (default)
   - **Branch: multi-pair-ui** → merged to master

4. ✅ **Bot Templates System** 📝 3Commas feature
   - BotTemplate model with full strategy configuration
   - Templates API with CRUD operations + seed endpoint
   - Template selector in bot creation form (dropdown at top)
   - 3 default presets: Conservative, Balanced, Aggressive DCA
   - Conservative: 2% base, 3 SOs, 1.5% profit, -5% SL
   - Balanced: 5% base, 4 SOs, 2% profit, -10% SL
   - Aggressive: 10% base, 5 SOs, 3% profit, no SL
   - Templates pre-fill entire form (name, strategy, pairs, config)
   - Default templates cannot be edited/deleted (protected)
   - **Branch: bot-templates** → merged to master

5. ✅ **AI Autonomous Trading Bot** 🤖 UNIQUE FEATURE
   - Claude AI-powered autonomous trading strategy
   - Makes intelligent buy/sell decisions to maximize profit
   - **Core Features:**
     - Analyzes market data with Claude 3.5 Sonnet
     - Never sells at a loss (hard requirement)
     - Budget grows with profits
     - Configurable risk tolerance (conservative/moderate/aggressive)
   - **Token Optimization:**
     - Analysis caching (5min TTL by default)
     - Configurable analysis interval (5-120 min, default 15min)
     - Summarized market data (not raw candles)
     - Structured prompts for concise responses
     - Token usage tracking and logging
   - **Configuration Parameters:**
     - Market focus (BTC/USD/ALL pairs)
     - Initial budget % (1-50%, default 10%)
     - Max position size % (5-100%, default 25%)
     - Risk tolerance (conservative/moderate/aggressive)
     - Analysis interval (5-120 min)
     - Min profit % to sell (0.1-10%, default 1%)
   - **Sentiment Analysis (Planned):**
     - Framework in place for Twitter/news integration
     - Placeholder for Fear & Greed index
     - Reddit sentiment analysis ready
     - Will consider social/news when making decisions
   - Requires ANTHROPIC_API_KEY in .env
   - **Branch: ai-autonomous-bot** (in progress)

### Latest Session Completed (2025-11-15 - MacBook Migration + Trailing TP/SL):
1. ✅ **Trailing Take Profit / Stop Loss** 🌟
   - Proper trailing TP that tracks peak price after hitting target
   - Sells when price drops by X% from peak (not just target + deviation)
   - Trailing SL that follows price upward to protect profits
   - Database: Added highest_price_since_tp, trailing_tp_active, highest_price_since_entry columns
   - Implemented in conditional_dca and advanced_dca strategies
   - New parameters: trailing_stop_loss (bool), trailing_stop_deviation (%)
   - **Branch: trailing-tp-sl** → merged to master
   - Example: Entry $100, TP 3%, Trailing 1% → Price hits $110 → Sells at $108.90 (8.9% profit)

### Latest Session Progress (2025-11-15 - Full Day):
1. ✅ **Clone/Duplicate Bots** 🎉
   - Backend: POST /api/bots/{id}/clone endpoint
   - Auto-increments name intelligently (Bot → Bot (Copy) → Bot (Copy 2))
   - Cloned bot starts stopped (safe default)
   - Frontend: Clone button with Copy icon between Edit and Delete
   - Preserves all configuration

2. ✅ **AI Bot Reasoning Log - Complete** 🧠
   - Database: AIBotLog model (thinking, decision, confidence, context)
   - Backend API: POST/GET /api/bots/{id}/logs endpoints
   - **Integrated with AI strategy:** Automatically saves every decision
   - Logs saved after both buy and sell decisions
   - Only logs for AI autonomous bots (strategy check)

3. ✅ **Custom Instructions for AI Bots** 🎯
   - New parameter: custom_instructions (text type)
   - Frontend: Textarea with helpful default behavior description
   - Backend: Instructions appended to Claude API prompt
   - Examples: "Focus on BTC pairs", "Avoid low volume hours"

### Completed Today - Full Summary:
✅ Trailing Take Profit / Stop Loss (proper implementation)
✅ Stopped Bot Position Management (continues managing existing positions)
✅ Clone/Duplicate Bots
✅ AI Reasoning Log Infrastructure + Integration
✅ Custom Instructions for AI Bots

### Latest Session Completed (2025-11-15 - Late Night):
1. ✅ **AI Reasoning Log Viewer** 🧠
   - Full modal component with filtering and auto-refresh
   - Filter by decision type (all/buy/sell/hold)
   - Color-coded confidence levels (green/yellow/red)
   - Auto-refresh every 10 seconds
   - Shows AI thinking, decision, confidence, price, position status
   - Integrated into Bots page with "AI Logs" button

2. ✅ **AI Provider Selection (Claude/Gemini)** 🤖
   - Choose between Claude or Gemini for AI autonomous trading
   - Full Gemini API integration with token tracking
   - Lazy loading of Gemini library
   - Both providers use identical prompts
   - API keys configured in .env

3. ✅ **Dynamic Trading Pairs** 🔄
   - Replaced hardcoded pairs with dynamic API fetch
   - Bot creation and Charts page now use identical pair lists
   - Auto-updates when new pairs available on Coinbase
   - Grouped by BTC/USD pairs

4. ✅ **3Commas-Style Bot UI** 🎨
   - Toggle switches for enable/disable (green when active)
   - "..." dropdown menu for edit, clone, delete
   - Click-outside handler for menus
   - Status indicator (Running/Stopped)
   - Clean, professional 3Commas-inspired design

### Next Priority Items:
1. ⏳ **Position Notifications/Alerts**
   - Deal opened/closed notifications
   - TP/SL hit alerts
   - Safety order filled alerts
   - Browser notifications or in-app alerts

2. ⏳ **Dashboard Statistics**
   - Total profit (all time, 24h, 7d, 30d)
   - Active deals count
   - Win rate calculation
   - Best/worst performing bot

3. ⏳ **Import/Export Bot Configs**
   - Export bot configuration to JSON
   - Import bot from JSON file
   - Share bot templates between users

4. ⏳ **Multiple Take Profit Targets**
   - Set multiple TP levels (e.g., 2% for 50%, 5% for 50%)
   - Partial position closing
   - Ladder-style profit taking

---

**Last Updated:** 2025-11-15 (MacBook - Late Night)
**Next Milestone:** Notifications & Dashboard Analytics
