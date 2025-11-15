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
- ⏳ Clone/duplicate bots
- ⏳ Bot templates
- ⏳ Import/export bot configs

### Strategy Support
- ✅ Conditional DCA (custom conditions per phase)
- ✅ Multi-timeframe indicators per condition
- ✅ Base Order conditions
- ✅ Safety Order conditions
- ✅ Take Profit conditions
- ✅ Min profit threshold for conditional exits
- ⏳ Trailing take profit
- ⏳ Trailing stop loss
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
- 🚧 Charts with price markers
- ⏳ Panic sell
- ⏳ Add funds
- ⏳ Trailing TP/SL

### Should Have (Important)
- ⏳ Bot templates
- ⏳ Clone bots
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

### Next Priority Items:
1. 🚧 **MULTI-PAIR BOTS** ⚠️ HIGH PRIORITY - Critical 3Commas feature
   - Allow 1 bot to trade multiple pairs simultaneously
   - Architecture: bot → multiple positions (one per pair)
   - Signal evaluation per pair
   - Configuration UI for selecting multiple pairs

2. ⏳ **Bot Templates**
   - Save/load bot configurations
   - Quick-start from presets

3. ⏳ **Trailing Take Profit / Stop Loss**
   - Dynamic TP that follows price upward
   - Implementation in trading engine

4. ⏳ **Position Notifications/Alerts**
   - Deal opened/closed notifications
   - TP/SL hit alerts

---

**Last Updated:** 2025-11-15 Evening
**Next Milestone:** Multi-Pair Bots (starting now)
