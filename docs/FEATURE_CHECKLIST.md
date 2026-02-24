# ZenithGrid - Feature Checklist

**Goal:** Full DCA bot feature parity, then extend beyond with advanced and proprietary features.

**Status Key:**
- ✅ Complete
- ⏳ Planned
- ❌ Not Started

---

## Core Bot Features

### Bot Management
- ✅ Create bots with multiple strategy types
- ✅ Edit bots while running
- ✅ Start/Stop bots
- ✅ Multiple bots running simultaneously
- ✅ Multi-pair bots (trade multiple pairs with one bot)
- ✅ Budget splitting toggle (divide percentages across pairs)
- ✅ Bot templates (presets and custom templates)
- ✅ Clone/duplicate bots
- ✅ Professional UI (toggle switches, ... menu)
- ✅ Import/export bot configs

### Strategy Support
- ✅ Indicator-Based (custom conditions per phase)
- ✅ Multi-timeframe indicators per condition
- ✅ Base Order conditions
- ✅ Safety Order conditions
- ✅ Take Profit conditions
- ✅ Min profit threshold for conditional exits
- ✅ **AI Autonomous Trading** (multi-provider)
- ✅ **AI Provider Selection** (Claude, GPT, Gemini, Grok, Groq)
- ✅ **AI Reasoning Log Viewer** (view AI decision history)
- ✅ **Custom AI Instructions** (guide AI behavior)
- ✅ **Trailing take profit** (tracks peak, sells on drop from peak)
- ✅ **Trailing stop loss** (follows price up, protects profits)
- ✅ **Grid Trading** strategy
- ✅ **Bull Flag Scanner** strategy
- ✅ **Arbitrage strategies** (Triangular, Spatial, Statistical)
- ✅ **Bidirectional trading** (long + short)
- ✅ **Paper trading** mode
- ⏳ Multiple take profit targets

### Indicators & Conditions
- ✅ RSI
- ✅ MACD (line, signal, histogram)
- ✅ Bollinger Bands %
- ✅ EMA / SMA crosses
- ✅ Stochastic (%K, %D)
- ✅ Price action
- ✅ Volume
- ✅ Volume RSI
- ✅ AI Buy / AI Sell (aggregate signals)
- ✅ Bull Flag detection
- ✅ Crossing operators (above/below)
- ✅ Increasing/Decreasing operators (with strength thresholds)
- ✅ AND/OR logic between conditions

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
- ✅ Entry price line on chart
- ✅ Entry marker on chart
- ✅ Current price marker on chart
- ✅ Take profit target line on chart
- ✅ Stop loss line on chart
- ✅ Safety order price levels on chart
- ✅ Real-time current price (updates every 5s)
- ✅ Live P&L calculations with real prices
- ✅ Limit order management (place, cancel, monitor)

### Deal Actions
- ✅ Expandable deal details
- ✅ Close position (panic sell / force close at market price)
- ✅ Add funds (manual safety order with amount input)
- ✅ Confirmation dialogs for destructive actions
- ✅ Error handling and user feedback
- ✅ Place limit orders (buy/sell)

### Closed Deals History
- ✅ Collapsible history section
- ✅ Profit/loss summary
- ✅ Date range display
- ✅ Order history with full audit trail
- ⏳ Export to CSV

---

## Charts & Analysis

### Chart Display
- ✅ Multiple timeframes (1m, 5m, 15m, 30m, 1h, 2h, 6h, 1d)
- ✅ Candlestick charts
- ✅ Multiple chart types (bar, line, area, baseline)
- ✅ Heikin-Ashi candles
- ✅ Volume display
- ✅ Entry price markers on chart
- ✅ Take profit markers
- ✅ Stop loss markers
- ✅ Safety order price levels
- ✅ Chart in deal view (not just separate page)

### Technical Indicators
- ✅ SMA with configurable period
- ✅ EMA with configurable period
- ✅ RSI with overbought/oversold zones
- ✅ MACD with histogram
- ✅ Bollinger Bands
- ✅ Stochastic Oscillator
- ✅ Multiple indicators simultaneously
- ✅ Indicator customization (colors, periods)

### Trading Pairs
- ✅ All Coinbase USD pairs available
- ✅ All Coinbase BTC pairs available
- ✅ Visual indicator for held coins
- ✅ Grouped by quote currency
- ✅ Dynamic pair list from API
- ✅ Coin categorization (APPROVED/BORDERLINE/QUESTIONABLE/MEME/BLACKLISTED)

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
- ✅ CEX + DEX portfolio tracking
- ✅ Account value snapshots (daily)

---

## Dashboard

### Overview Stats
- ✅ Total profit metrics (BTC & USD)
- ✅ Active deals count
- ✅ Win rate calculation
- ✅ Account value from portfolio
- ✅ Per-bot profit and deal stats
- ✅ Recent deals table
- ✅ Real-time updates

### Notifications
- ✅ WebSocket real-time notifications
- ✅ Order fill notifications
- ✅ In-app notification display

### Market Intelligence
- ✅ Fear & Greed Index
- ✅ BTC dominance tracking
- ✅ US National Debt monitoring
- ✅ Market sentiment cards

---

## News & Content

- ✅ Multi-source news aggregation (Reddit, CoinDesk, CoinTelegraph, The Block, etc.)
- ✅ YouTube integration (educational channels)
- ✅ AI-powered article summaries
- ✅ Text-to-speech for articles
- ✅ Content source management
- ✅ User source subscriptions

---

## Settings & Configuration

- ✅ Coinbase API credentials (encrypted storage)
- ✅ AI provider credentials (encrypted, per-user)
- ✅ Test connection functionality
- ✅ Page state persistence
- ✅ Chart settings persistence
- ✅ Seasonality data management

---

## Safety & Risk Management

- ✅ Max concurrent deals per bot
- ✅ Budget percentage allocation per bot
- ✅ Validation on bot creation
- ✅ Config validation on updates
- ✅ Confirmation dialogs for destructive actions
- ✅ API key encryption at rest
- ✅ JWT authentication
- ✅ Rate limiting on API endpoints
- ✅ Security headers
- ✅ Error sanitization (no internal details leaked)

---

## Infrastructure

- ✅ Database migrations (auto-discovered, idempotent)
- ✅ Automated update script (`update.py`)
- ✅ systemd service management
- ✅ Background task scheduling (13 tasks)
- ✅ Graceful shutdown (ShutdownManager)
- ✅ WebSocket support for live updates
- ✅ Database backup automation (via update script)
- ⏳ Docker Compose deployment
- ⏳ HTTPS/SSL via reverse proxy

---

## Core Feature Parity

### Must Have (Core) - ALL COMPLETE
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
- ✅ Clone bots
- ✅ Notifications (WebSocket)
- ⏳ Multiple exchanges

### Advanced & Proprietary Features
- ✅ AI-powered trading (5+ AI providers)
- ✅ Bull Flag pattern scanner
- ✅ Arbitrage strategies (3 types)
- ✅ News aggregation (8+ sources)
- ✅ Category filtering (5 categories)
- ✅ Self-hosted / no monthly fees
- ✅ Grid trading
- ✅ Paper trading
- ✅ Bidirectional trading
- ✅ DEX portfolio tracking
- ✅ Perpetual futures support (in development)
- ⏳ Enhanced sentiment analysis
- ⏳ Backtesting system
- ⏳ Mobile app

---

*Last Updated: 2026-02-15*
