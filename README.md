# Zenith Grid - Advanced Trading Bot Platform

A sophisticated self-hosted cryptocurrency trading platform with **AI-powered autonomous trading**, advanced DCA strategies, and professional chart analysis. Built to replace 3Commas with enhanced features and full control.

**IMPORTANT: This software is licensed under the GNU Affero General Public License v3.0 (AGPL v3). Please read the [LICENSE](LICENSE) file before using this software.**

## 🌟 Unique Features

### 🤖 **AI Autonomous Trading Bot**
The first and only DCA bot platform with built-in AI decision-making:
- **Multi-AI Provider Support**: Claude (Anthropic), GPT (OpenAI), Gemini (Google), Grok (xAI), Groq (Llama)
- **Autonomous Trading**: AI analyzes markets and makes intelligent buy/sell decisions
- **Never Sells at a Loss**: Hard-coded safety to protect capital
- **Token Optimized**: Smart caching, batching, and rate limiting
- **Sentiment Ready**: Framework for Twitter, news, and Reddit integration
- **Configurable Risk**: Conservative, Moderate, or Aggressive modes
- **Per-User API Keys**: Encrypted credential management

### 🎯 Advanced DCA Strategies
- **Multi-Pair Bots**: One bot trades multiple pairs simultaneously
- **Budget Splitting**: Optional budget division across pairs for safer allocation
- **Category Filtering**: Filter trading pairs by APPROVED, BORDERLINE, QUESTIONABLE, MEME, BLACKLISTED
- **Conditional DCA**: Custom conditions per phase (base order, safety orders, take profit)
- **Multi-Timeframe**: Different timeframes per indicator (5m, 15m, 30m, 1h, 4h, 1d)
- **Bot Templates**: Quick-start from Conservative/Balanced/Aggressive presets
- **6 Advanced Strategies**: Indicator-Based (custom), Bull Flag Scanner, AI Spot Opinion, Triangular Arbitrage, Spatial Arbitrage, Statistical Arbitrage

### 📊 Professional Dashboard
- **3Commas-Style Deals**: Active positions with real-time P&L
- **TradingView Charts**: Professional candlestick charts with indicators
- **Position Markers**: Entry price, TP/SL lines, safety order levels
- **Portfolio Tracking**: Real-time portfolio value and allocation (CEX & DEX)
- **Trade History**: Complete audit trail of all trades
- **Performance Metrics**: Win rate, total profit, active deals
- **News Aggregation**: Configurable multi-source crypto news with category filtering and subscription management
- **Article Reader with TTS**: Full article content with text-to-speech, voice cycling, and word-level sync
- **YouTube Integration**: Educational content from crypto channels
- **Market Intelligence**: 16+ indicator cards — Fear & Greed, BTC Dominance, Altseason Index, ATH Distance, Hash Rate, Mempool, Lightning Network, Stablecoin Market Cap, BTC RSI, Halving Countdown, US Debt, and more

### 🔐 Security & Multi-User
- **HTTPS**: Nginx reverse proxy with Let's Encrypt SSL (auto-renewing)
- **Security Headers**: HSTS (Strict-Transport-Security) + Content-Security-Policy
- **Multi-Factor Authentication**: TOTP (authenticator app) or Email-based MFA
- **Email Verification**: Required for new account activation
- **Trusted Devices**: 30-day device trust with geolocation tracking
- **Password Reset**: Secure email-based password recovery
- **Multi-User**: Full data isolation between users with per-user encrypted credentials
- **Encrypted at Rest**: All API keys and secrets encrypted with Fernet (AES-128-CBC + HMAC-SHA256)
- **Token Revocation**: Server-side JWT revocation on logout; password change invalidates all sessions
- **Rate Limiting**: Multi-layer — nginx (per-IP) + application (per-user/per-email/per-token)
- **Timing-Safe Auth**: Constant-time login prevents username enumeration

### 🏦 Multi-Exchange Support
- **Coinbase Advanced Trade**: Spot trading + perpetual futures (INTX) via HMAC or CDP auth
- **ByBit V5**: Linear perpetual futures with real-time WebSocket equity tracking
- **MT5 Bridge**: FTMO and prop firm trading via custom EA bridge
- **DEX**: On-chain swaps on Ethereum, Arbitrum, Polygon, Base
- **PropGuard**: Automated drawdown protection for prop firm accounts (daily + total limits, kill switch)
- **Paper Trading**: Simulated exchange client for risk-free strategy testing

## 🏗️ Architecture

- **Backend**: Python 3.10+ + FastAPI + SQLAlchemy (async) + SQLite
- **Frontend**: React 18 + TypeScript + Vite + TanStack Query + TradingView Charts
- **Exchanges**: Coinbase Advanced Trade (HMAC/CDP), ByBit V5 (linear perps), MT5 Bridge, DEX (Ethereum/L2s)
- **AI**: Multi-provider support (Claude, GPT, Gemini, Grok, Groq)
- **Auth**: JWT + TOTP MFA + Email MFA + email verification + trusted devices
- **Deployment**: Nginx + Let's Encrypt SSL + systemd (AWS EC2 or self-hosted)

## 📋 Prerequisites

- **Python 3.10+** (Python 3.13 recommended)
- **Node.js 18+** and npm
- **Exchange account** — Coinbase (required for spot), ByBit/MT5 (optional for perps)
- **AI API key** (optional, for AI bots - Claude, GPT, Gemini, Grok, or Groq)
- **BTC and/or USD** in your Coinbase account

## 🚀 Quick Start

### Automated Setup (Recommended)

The easiest way to set up Zenith Grid is using the interactive setup wizard:

```bash
# Clone repository
git clone <your-repo-url>
cd ZenithGrid

# Run the setup wizard
python3 setup.py
```

The setup wizard will:
1. **Display and require acceptance of the LICENSE**
2. Create Python virtual environment and install all dependencies
3. Install frontend Node.js dependencies
4. Initialize the SQLite database
5. Generate .env file with secure JWT secrets
6. Prompt for optional AI provider (for coin categorization)
7. Create your admin user account
8. Configure your Coinbase API credentials
9. Optionally install systemd/launchd services for auto-start
10. **Start the services automatically**

That's it! Access the application at: **http://localhost:8100**

#### Setup Wizard Options

```bash
python3 setup.py                      # Full interactive setup
python3 setup.py --services-only      # Only create/install service files
python3 setup.py --uninstall-services # Stop and remove service files
python3 setup.py --cleanup            # Remove dependencies (venv, node_modules)
python3 setup.py --help               # Show all options
```

---

### Manual Setup (Alternative)

If you prefer manual control:

```bash
# Clone repository
git clone <your-repo-url>
cd ZenithGrid

# Backend setup
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend setup
cd ../frontend
npm install

# Return to root and start services
cd ..
./bot.sh start
```

Then configure API keys in `backend/.env` and create your admin user via the API.

**Get API Keys:**
- **Coinbase**: https://portal.cdp.coinbase.com/
- **ByBit** (optional, for perps): https://www.bybit.com/app/user/api-management
- **AI Providers** (optional):
  - Claude: https://console.anthropic.com/
  - GPT: https://platform.openai.com/
  - Gemini: https://aistudio.google.com/apikey

## 🎮 Usage

### Create Your First Bot

1. Open http://localhost:8100
2. Navigate to **"Bots"** page
3. Click **"Create New Bot"**
4. (Optional) Select a template: Conservative/Balanced/Aggressive
5. Choose strategy:
   - **Custom Bot (Indicator-Based)** - Mix-and-match conditions
   - **AI Spot Opinion** - AI-powered market analysis
   - **Bull Flag Scanner** - Automated pattern detection
   - **Grid Trading** - Grid-based strategy
6. Select trading pair(s)
7. Configure parameters
8. Click **"Start Bot"**

### Available Strategies

1. **🎯 Indicator-Based (Universal/Custom Bot)** - Mix-and-match framework with 20+ technical indicators, multi-timeframe support, and phase-based conditions
2. **📊 Bull Flag Scanner** - Automated bullish reversal pattern detection with volume confirmation
3. **🤖 AI Spot Opinion** - Real-time LLM-based market analysis (Claude, GPT, Gemini, Grok, Groq)
4. **🔺 Triangular Arbitrage** - Single-exchange 3-way currency cycle profitability detection
5. **🌐 Spatial Arbitrage** - Cross-exchange (CEX vs DEX) price difference exploitation
6. **📈 Statistical Arbitrage (Pairs Trading)** - Mean-reversion trading between correlated pairs

## 💡 AI Bot Quick Start

### Step 1: Add Your AI Provider (One-Time Setup)

1. Open the application at http://localhost:8100
2. Navigate to **Settings** page
3. Click **"AI Provider Credentials"** button
4. Choose your AI provider (Claude, GPT, Gemini, Grok, or Groq)
5. Enter your API key (stored encrypted in database)
6. Optionally set as default for new bots

### Step 2: Create an AI Bot

1. Navigate to **Bots** page
2. Click **"Create New Bot"**
3. Select strategy: **"AI Spot Opinion"**
4. Choose trading pairs (e.g., ETH-BTC, SOL-BTC)
5. Configure bot settings in the form:
   - AI model (e.g., claude-sonnet-4)
   - Confidence threshold (70%)
   - Min profit percentage (1.0%)
   - Max position size
   - Enable technical pre-filter (optional)
6. Click **"Create Bot"**

All configuration is done through the web interface - no manual JSON editing required!

### How It Works:
1. Every 15 minutes (configurable), fetches market data
2. Applies optional technical pre-filter to reduce API costs
3. Calls your chosen AI (Claude/GPT/Gemini) for analysis
4. AI returns: buy/hold/sell + confidence score + reasoning
5. Bot executes if confidence exceeds threshold
6. **Never sells at a loss** - waits for profit target
7. All decisions logged with reasoning in AI Bot Reasoning tab

### Token Optimization:
- Analysis caching (5min TTL)
- Configurable intervals (5-120min)
- Summarized data (not raw candles)
- Structured prompts for concise responses
- Usage tracking and logging

**Estimated Cost**: $0.10-0.50/day per bot (depends on interval)

## 🔧 Commands

### Service Management

```bash
./bot.sh start                       # Start backend + frontend
./bot.sh stop                        # Stop both
./bot.sh restart --dev --back-end    # Restart backend only (dev mode)
./bot.sh restart --dev --front-end   # Restart frontend only (dev mode)
./bot.sh restart --dev --both        # Restart both services (dev mode)
./bot.sh restart --prod              # Rebuild + restart (prod mode)
./bot.sh status                      # Check status
./bot.sh logs                        # View logs
```

### Updating Zenith Grid

The `update.py` script automates the entire update process:

```bash
python3 update.py                    # Full update with confirmation prompts
python3 update.py --yes              # Auto-confirm all prompts (recommended for automation)
python3 update.py --dry-run          # Preview what would be done without executing
python3 update.py --preview          # Preview incoming commits before pulling
python3 update.py --preview -d       # Preview with full file diffs
python3 update.py --changelog        # Show last 5 versions' changes
python3 update.py --changelog 10     # Show last 10 versions' changes
python3 update.py --changelog v0.86.0  # Show what changed in specific version
```

**What the update script does:**
1. Pulls latest changes from git (origin/main)
2. Stops backend and/or frontend services (only services with changes)
3. Backs up database (timestamped backup)
4. Runs all database migrations (idempotent, safe to re-run)
5. Installs npm dependencies (only if package.json/lock changed)
6. Restarts services (only services that were stopped)

**Advanced options:**
```bash
python3 update.py --no-backup        # Skip database backup (not recommended)
python3 update.py --skip-pull        # Skip git pull (if already pulled manually)
```

**Best practice for production:**
```bash
# Check recent updates
python3 update.py --changelog

# Preview what will change
python3 update.py --preview

# Apply the update
python3 update.py --yes
```

## 📊 Features Comparison

| Feature | 3Commas | Zenith Grid |
|---------|---------|-------------|
| DCA Bots | ✅ | ✅ |
| Multi-Pair Bots | ✅ | ✅ |
| Conditional Trading | ✅ | ✅ |
| Bot Templates | ✅ | ✅ |
| **AI-Powered Trading** | ❌ | ✅ **5+ AI providers** |
| **Multi-AI Support** | ❌ | ✅ **Claude, GPT, Gemini, Grok, Groq** |
| **Bull Flag Scanner** | ❌ | ✅ **Automated pattern detection** |
| **Arbitrage Strategies** | Limited | ✅ **3 types** |
| **News + TTS Reader** | ❌ | ✅ **Multi-source with text-to-speech** |
| **Market Sentiment** | ❌ | ✅ **16+ indicator cards** |
| **Multi-Exchange** | ✅ | ✅ **Coinbase + ByBit + MT5 + DEX** |
| **Prop Firm Safety** | ❌ | ✅ **PropGuard drawdown monitoring** |
| **MFA / 2FA** | ✅ | ✅ **TOTP + Email MFA** |
| **HTTPS / SSL** | ✅ | ✅ **Let's Encrypt auto-renewing** |
| **Category Filtering** | ❌ | ✅ **5 categories** |
| **Self-Hosted** | ❌ | ✅ |
| **No Monthly Fees** | ❌ | ✅ |
| **Full Source Control** | ❌ | ✅ |
| Multi-Timeframe | Limited | ✅ **6 timeframes** |
| Budget Splitting | Basic | ✅ Advanced |
| Real-time Charts | ✅ | ✅ TradingView |
| Position Management | ✅ | ✅ |
| Portfolio Tracking | ✅ | ✅ **CEX + DEX** |
| Paper Trading | ✅ | ✅ **Simulated exchange** |

## 🛡️ Safety Features

- **Never Sell at a Loss** (AI bot hard-coded rule)
- **Budget Limits** per bot with percentage allocation
- **Position Size Limits** (max concurrent deals)
- **Category Filtering** (blacklist risky coins)
- **Confirmation Dialogs** for destructive actions
- **Real-time P&L** tracking with visual indicators
- **Stop Loss** support (percentage or pattern-based)
- **Take Profit** targets (percentage or conditions-based)
- **Trailing Stop Loss** with deviation percentage
- **Trailing Take Profit** with pullback protection
- **Safety Order** ladder with configurable steps
- **PropGuard**: Automated prop firm drawdown monitoring with daily/total limits and kill switch
- **API Key Encryption** (Fernet AES-128-CBC + HMAC-SHA256)
- **Multi-User Support** with full data isolation
- **MFA**: TOTP (authenticator app) or email-based two-factor authentication
- **HTTPS**: Nginx + Let's Encrypt with auto-renewing certificates
- **Security Headers**: HSTS + CSP to prevent MITM and XSS
- **Multi-Layer Rate Limiting**: Nginx (per-IP) + app-level (per-user, per-token, per-email)
- **Real-time Notifications**: WebSocket order fill alerts with audio

## 📖 Documentation

- **[🏗️ Architecture](docs/ARCHITECTURE.md)** - System architecture with Mermaid diagrams
- **[📰 News Content Architecture](docs/NEWS_CONTENT_ARCHITECTURE.md)** - News, TTS, and content source rules
- **[✅ Feature Checklist](docs/FEATURE_CHECKLIST.md)** - Progress tracker
- **[📖 Quick Start](docs/QUICKSTART.md)** - Getting started guide
- **[🔌 API Docs](http://localhost:8100/docs)** - FastAPI auto-docs (when running)

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
- AI decision logs with reasoning
- News articles, TTS audio cache, and seen status
- Account value snapshots for historical charting
- Prop firm equity snapshots and drawdown history

## 🌱 Roadmap

- [x] Multi-pair bots
- [x] Budget splitting
- [x] Bot templates (Conservative/Balanced/Aggressive)
- [x] **AI autonomous trading with multi-provider support**
- [x] **Bull Flag pattern scanner**
- [x] **Arbitrage strategies** (Triangular, Spatial, Statistical)
- [x] **News aggregation with TTS article reader**
- [x] **Market sentiment dashboard** (16+ indicator cards)
- [x] **Category filtering system**
- [x] **Trailing take profit / stop loss**
- [x] **Portfolio tracking** (CEX + DEX)
- [x] **Multi-exchange support** (Coinbase, ByBit, MT5 Bridge, DEX)
- [x] **MFA / 2FA** (TOTP + Email)
- [x] **HTTPS with Let's Encrypt SSL**
- [x] **Real-time WebSocket notifications** (toast + audio)
- [x] **PropGuard** prop firm safety monitoring
- [x] **Paper trading mode**
- [x] **Email verification & password reset** (AWS SES)
- [ ] **Enhanced sentiment analysis** (Twitter/X, social signals)
- [ ] **Backtesting system** for strategy validation
- [ ] **Additional exchanges** (Binance, Kraken, etc.)
- [ ] **Telegram / email alerts** for position events
- [ ] **Performance analytics dashboard** (advanced metrics)
- [ ] **Mobile app** (React Native)

## 🐛 Troubleshooting

### Backend won't start
```bash
# Check logs
tail -f .pids/backend.log

# Common issues:
# - Missing API credentials (add to backend/.env)
# - Port 8100 in use (kill existing process or change port)
# - Missing dependencies (pip install -r requirements.txt)
# - Python version (requires Python 3.10+)
```

### AI Bot not working
```bash
# Check AI provider credentials in Settings page
# Navigate to Settings → AI Provider Credentials

# Verify AI strategies are loaded
curl http://localhost:8100/api/bots/strategies | grep "ai_spot_opinion"

# Check logs for API errors
tail -f .pids/backend.log | grep -E "Claude|GPT|Gemini|AI"

# Check AI Bot Reasoning logs in Dashboard
# Navigate to Dashboard → AI Bot Reasoning tab
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
- ⚠️ **Enable MFA** for all user accounts (TOTP or Email)
- ⚠️ **Use HTTPS** in production (Nginx + Let's Encrypt included)
- ⚠️ **Rotate API keys** periodically
- ⚠️ **Trading involves risk** - only invest what you can afford to lose

## 📄 License

**IMPORTANT: You must read and agree to the license terms before using this software.**

Zenith Grid is licensed under the **GNU Affero General Public License v3.0 (AGPL v3)**.

### What This Means:
- ✅ **Free to use, modify, and distribute**
- ✅ **Open source** - full code access
- ✅ **Network copyleft** - if you run a modified version as a service, you must share your changes
- ✅ **Commercial use allowed** if you comply with AGPL (open source your modifications)

### License Requirements:
- The `setup.py` wizard will display the full license and require your acceptance
- Read the complete license: **[LICENSE](LICENSE)**
- For commercial licensing without AGPL obligations (proprietary forks, closed-source use), contact: louis_romero@outlook.com

### Commercial Licensing:
For commercial licensing options that don't require open-sourcing your modifications, see [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md) or contact louis_romero@outlook.com

## ☕ Support Development

If you find Zenith Grid useful, consider supporting continued development:

- **Bitcoin (BTC):** 3LehBoma3aeDwdgMYK3hyr2TGfxkJs55MV
- **PayPal:** @farolito74
- **USDC:** 0x8B7Ff39C772c90AB58A3d74dCd17F1425b4001c0

Every contribution helps maintain and improve this project!

## ⚠️ Disclaimer

**This software is for educational and informational purposes.**

Trading cryptocurrencies involves substantial risk of loss and is not suitable for every investor. Past performance is not indicative of future results. The authors and contributors are not responsible for any losses incurred. **Use at your own risk.**

### Important Warnings:
- **AI trading bots are experimental** - AI decisions are not guaranteed to be profitable
- **Start with small amounts** - Test strategies with minimal capital first
- **Monitor regularly** - Automated trading still requires supervision
- **Understand the risks** - Only invest what you can afford to lose completely
- **No financial advice** - This software does not provide investment advice
- **Your responsibility** - You are solely responsible for your trading decisions

---

🤖 **Built with Claude Code**

For detailed documentation, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
