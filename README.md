# 3Commas Replacement - Advanced Trading Bot Platform

A sophisticated self-hosted cryptocurrency trading platform with **AI-powered autonomous trading**, advanced DCA strategies, and professional chart analysis. Built to replace 3Commas with enhanced features and full control.

## 🌟 Unique Features

### 🤖 **AI Autonomous Trading Bot** (NEW!)
The first and only DCA bot platform with built-in AI decision-making:
- **Claude AI Integration**: Uses Anthropic's Claude 3.5 Sonnet for market analysis
- **Autonomous Trading**: AI analyzes markets and makes intelligent buy/sell decisions
- **Never Sells at a Loss**: Hard-coded safety to protect capital
- **Token Optimized**: Smart caching, batching, and rate limiting
- **Sentiment Ready**: Framework for Twitter, news, and Reddit integration
- **Configurable Risk**: Conservative, Moderate, or Aggressive modes

### 🎯 Advanced DCA Strategies
- **Multi-Pair Bots**: One bot trades multiple pairs simultaneously
- **Budget Splitting**: Optional budget division across pairs for safer allocation
- **Conditional DCA**: Custom conditions per phase (base order, safety orders, take profit)
- **Multi-Timeframe**: Different timeframes per indicator
- **Bot Templates**: Quick-start from Conservative/Balanced/Aggressive presets
- **7 Strategies**: MACD, RSI, Bollinger Bands, Conditional DCA, AI, and more

### 📊 Professional Dashboard
- **3Commas-Style Deals**: Active positions with real-time P&L
- **TradingView Charts**: Professional candlestick charts with indicators
- **Position Markers**: Entry price, TP/SL lines, safety order levels
- **Portfolio Tracking**: Real-time portfolio value and allocation
- **Trade History**: Complete audit trail of all trades
- **Performance Metrics**: Win rate, total profit, active deals

## 🏗️ Architecture

- **Backend**: Python 3.13 + FastAPI + SQLAlchemy (async) + SQLite
- **Frontend**: React 18 + TypeScript + Vite + TanStack Query + TradingView Charts
- **Exchange**: Coinbase Advanced Trade API
- **AI**: Anthropic Claude 3.5 Sonnet API
- **Deployment**: uvicorn + nginx + systemd (optional)

## 📋 Prerequisites

- **Python 3.13+**
- **Node.js 18+** and npm
- **Coinbase account** with API credentials
- **Anthropic API key** (optional, for AI bot only)
- **BTC and/or ETH** in your Coinbase account

## 🚀 Quick Start

### 1. Clone and Install

```bash
# Clone repository
git clone <your-repo-url>
cd GetRidOf3CommasBecauseTheyGoDownTooOften

# Backend setup
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend setup
cd ../frontend
npm install

# Return to root
cd ..
```

### 2. Configure API Keys

```bash
cd backend
cp .env.example .env
nano .env
```

Add your API keys:
```bash
# Required for all bots
COINBASE_API_KEY=your_coinbase_key
COINBASE_API_SECRET=your_coinbase_secret

# Optional - for AI Autonomous Bot only
ANTHROPIC_API_KEY=your_anthropic_key
```

**Get API Keys:**
- **Coinbase**: https://portal.cdp.coinbase.com/
- **Anthropic**: https://console.anthropic.com/

### 3. Start the Platform

```bash
./bot.sh start
```

Access at: **http://localhost:5173**

## 🎮 Usage

### Create Your First Bot

1. Open http://localhost:5173
2. Navigate to **"Bots"** page
3. Click **"Create New Bot"**
4. (Optional) Select a template: Conservative/Balanced/Aggressive
5. Choose strategy:
   - **AI Autonomous** - Claude AI-powered (NEW!)
   - **Conditional DCA** - Custom conditions
   - **MACD DCA** - MACD-based DCA
   - **RSI** - RSI-based trading
   - **Bollinger Bands** - BB strategy
6. Select trading pair(s)
7. Configure parameters
8. Click **"Start Bot"**

### Available Strategies

1. **🤖 AI Autonomous** - Claude AI analyzes markets and makes decisions
2. **📊 Conditional DCA** - Custom conditions per phase
3. **📈 MACD DCA** - MACD-based DCA
4. **🎯 RSI** - RSI-based trading
5. **📉 Bollinger Bands** - Bollinger Band strategy
6. **💰 Simple DCA** - Basic DCA
7. **⚡ Advanced DCA** - Advanced DCA

## 💡 AI Bot Quick Start

### Configuration Example:
```json
{
  "name": "AI Trader Pro",
  "strategy_type": "ai_autonomous",
  "product_ids": ["ETH-BTC", "SOL-BTC"],
  "split_budget_across_pairs": true,
  "strategy_config": {
    "market_focus": "BTC",
    "initial_budget_percentage": 10.0,
    "max_position_size_percentage": 25.0,
    "risk_tolerance": "moderate",
    "analysis_interval_minutes": 15,
    "min_profit_percentage": 1.0
  }
}
```

### How It Works:
1. Every 15 minutes (configurable), fetches market data
2. Summarizes price trends, volatility, and key metrics
3. Calls Claude AI for analysis
4. Claude returns: buy/hold/sell + confidence score + reasoning
5. Bot executes if confident enough (60%+ buy, 70%+ sell)
6. **Never sells at a loss** - waits for profit
7. Budget grows with successful trades

### Token Optimization:
- Analysis caching (5min TTL)
- Configurable intervals (5-120min)
- Summarized data (not raw candles)
- Structured prompts for concise responses
- Usage tracking and logging

**Estimated Cost**: $0.10-0.50/day per bot (depends on interval)

## 🔧 Commands

```bash
./bot.sh start      # Start backend + frontend
./bot.sh stop       # Stop both
./bot.sh restart    # Restart both
./bot.sh status     # Check status
./bot.sh logs       # View logs
```

## 📊 Features Comparison

| Feature | 3Commas | This Platform |
|---------|---------|---------------|
| DCA Bots | ✅ | ✅ |
| Multi-Pair Bots | ✅ | ✅ |
| Conditional Trading | ✅ | ✅ |
| Bot Templates | ✅ | ✅ |
| **AI-Powered Trading** | ❌ | ✅ **Unique!** |
| **Self-Hosted** | ❌ | ✅ |
| **No Monthly Fees** | ❌ | ✅ |
| **Full Source Control** | ❌ | ✅ |
| Multi-Timeframe | Limited | ✅ Full |
| Budget Splitting | Basic | ✅ Advanced |
| Real-time Charts | ✅ | ✅ TradingView |
| Position Management | ✅ | ✅ |

## 🛡️ Safety Features

- **Never Sell at a Loss** (AI bot)
- **Budget Limits** per bot
- **Position Size Limits**
- **Confirmation Dialogs** for destructive actions
- **Real-time P&L** tracking
- **Stop Loss** support
- **Take Profit** targets
- **Safety Order** ladder

## 📖 Documentation

- **[📄 Handoff Document](HANDOFF_DOCUMENT.md)** - Complete setup & migration guide
- **[✅ Feature Checklist](3COMMAS_REPLACEMENT_CHECKLIST.md)** - Progress tracker
- **[🔌 API Docs](http://localhost:8000/docs)** - FastAPI auto-docs (when running)

## 🔄 Persistence & Recovery

### What Happens After Power Loss?

**Scenario:** Bot running with active position, power outage for 2 weeks.

**On Restart:**
1. ✅ Loads active position from database
2. ✅ Reconnects to Coinbase
3. ✅ Resumes monitoring for signals
4. ✅ Maintains accurate profit calculations
5. ✅ Continues strategy execution

**Database Stores:**
- All positions (open, closed, cancelled)
- Complete trade history with prices
- Bot configurations and templates
- Market data and signals
- Profit in BTC and USD

## 🌱 Roadmap

- [x] Multi-pair bots
- [x] Budget splitting
- [x] Bot templates (Conservative/Balanced/Aggressive)
- [x] **AI autonomous trading** 🤖
- [ ] **Sentiment analysis** (Twitter, news, Reddit)
- [ ] Trailing take profit / stop loss
- [ ] Position notifications / alerts
- [ ] Performance analytics dashboard
- [ ] Backtesting system
- [ ] Multiple exchange support
- [ ] Mobile app (React Native)

## 🐛 Troubleshooting

### Backend won't start
```bash
# Check logs
tail -f .pids/backend.log

# Common issues:
# - Missing API credentials (add to .env)
# - Port 8000 in use
# - Missing dependencies (pip install -r requirements.txt)
```

### AI Bot not working
```bash
# Check if ANTHROPIC_API_KEY is set
grep ANTHROPIC_API_KEY backend/.env

# Verify strategy is loaded
curl http://localhost:8000/api/bots/strategies | grep ai_autonomous

# Check logs for API errors
tail -f .pids/backend.log | grep "Claude"
```

### Chart not displaying
```bash
cd frontend
npm install
npm run dev
```

## 🔒 Security Notes

- ⚠️ **Never commit `.env`** to version control
- ⚠️ **Test with small amounts** first
- ⚠️ **Monitor regularly** for unexpected behavior
- ⚠️ **Use SSH tunnel** for remote access
- ⚠️ **Rotate API keys** periodically
- ⚠️ **Trading involves risk** - only invest what you can afford to lose

## 📝 Recent Updates

### 2025-11-15 - AI Autonomous Bot
- ✅ Claude AI integration for autonomous trading
- ✅ Token-optimized analysis (caching, batching)
- ✅ Never sells at a loss safety rule
- ✅ Configurable risk tolerance
- ✅ Sentiment analysis framework

### 2025-11-15 - Templates & Multi-Pair
- ✅ Bot templates (3 default presets)
- ✅ Multi-pair bot support
- ✅ Budget splitting toggle
- ✅ Template selector in bot form

### 2025-11-10 - Chart Enhancements
- ✅ Take Profit / Stop Loss lines
- ✅ Safety order price levels
- ✅ Real-time price updates (5s interval)
- ✅ Live P&L calculations

## 📄 License

Zenith Grid is licensed under the **GNU Affero General Public License v3.0 (AGPL v3)**.

This means:
- ✅ Free to use, modify, and distribute
- ✅ Open source - full code access
- ✅ Network copyleft - if you run a modified version as a service, you must share your changes
- ✅ Commercial use allowed if you comply with AGPL (open source your modifications)

For commercial licensing options (proprietary use, closed-source modifications), see [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md) or contact louis_romero@outlook.com

Full license text: [LICENSE](LICENSE)

## ☕ Support Development

If you find Zenith Grid useful, consider supporting continued development:

- **Bitcoin (BTC):** [PLACEHOLDER_BTC_ADDRESS]
- **PayPal:** [PLACEHOLDER_PAYPAL]
- **USDC:** [PLACEHOLDER_USDC_ADDRESS]

Every contribution helps maintain and improve this project!

## ⚠️ Disclaimer

**This software is for educational purposes only.**

Trading cryptocurrencies involves substantial risk of loss and is not suitable for every investor. Past performance is not indicative of future results. The authors are not responsible for any losses incurred. **Use at your own risk.**

The AI trading bot is experimental. AI decisions are not guaranteed to be profitable. Always monitor your bots and start with small amounts.

---

🤖 **Built with Claude Code**

For detailed documentation, see [HANDOFF_DOCUMENT.md](HANDOFF_DOCUMENT.md)
# Auto-deployment enabled - pushes to main will deploy automatically within 1 minute
