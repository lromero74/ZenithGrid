# Trading Bot Platform - Handoff Document
**Date**: 2025-11-15
**Session**: Continuation - Multi-Pair Bots, Templates, AI Autonomous Bot
**Current Branch**: `master`
**Status**: ✅ Ready for laptop migration

---

## 🎯 Project Overview

This is a **3Commas replacement** - a DCA (Dollar Cost Averaging) trading bot platform with multiple advanced strategies, including a unique **AI-powered autonomous trading bot** that uses Claude AI.

### Tech Stack:
- **Backend**: Python 3.13, FastAPI, SQLAlchemy (async), SQLite
- **Frontend**: React + TypeScript, Vite, TailwindCSS, React Query
- **Trading**: Coinbase Advanced Trade API
- **AI**: Anthropic Claude 3.5 Sonnet API
- **Charts**: TradingView Lightweight Charts

---

## 📦 What Was Built (This Session)

### 1. **Multi-Pair Bots** ✅ Merged
- Bots can trade multiple pairs simultaneously
- Each pair operates independently with separate positions
- Signal evaluation runs per pair
- Database: `product_ids` JSON column, `product_id` tracking on positions
- **Branch**: `multi-pair-backend` → merged to master

### 2. **Budget Splitting Toggle** ✅ Merged
- Optional per-bot setting to divide budget across pairs
- When enabled: divides percentages by number of pairs (safer)
- When disabled: each pair gets full budget (3Commas style)
- **Branch**: `multi-pair-ui` → merged to master

### 3. **Bot Templates** ✅ Merged
- `BotTemplate` model in database
- Templates API with CRUD + `/seed-defaults` endpoint
- 3 default presets: Conservative, Balanced, Aggressive DCA
- Template selector in bot creation form
- **Branch**: `bot-templates` → merged to master

### 4. **AI Autonomous Trading Bot** ✅ Merged
- Claude 3.5 Sonnet integration for market analysis
- Never sells at a loss (hard requirement)
- Token-optimized (caching, batching, smart prompting)
- Configurable risk tolerance and budget management
- Sentiment analysis framework (ready for Twitter/news integration)
- **Branch**: `ai-autonomous-bot` → merged to master

---

## 🏗️ Project Structure

```
/home/louis/GetRidOf3CommasBecauseTheyGoDownTooOften/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app entry point
│   │   ├── database.py                # SQLAlchemy setup
│   │   ├── models.py                  # Database models (Bot, Position, Trade, etc.)
│   │   ├── config.py                  # Settings management
│   │   ├── coinbase_client.py         # Coinbase API client
│   │   ├── multi_bot_monitor.py       # Multi-bot signal monitoring
│   │   ├── trading_engine_v2.py       # Strategy-based trading engine
│   │   ├── strategies/                # Trading strategies
│   │   │   ├── __init__.py            # Base classes + registry
│   │   │   ├── ai_autonomous.py       # 🤖 AI bot (NEW!)
│   │   │   ├── conditional_dca.py     # Conditional DCA
│   │   │   ├── macd_dca.py            # MACD DCA
│   │   │   ├── rsi.py                 # RSI strategy
│   │   │   └── ...other strategies
│   │   └── routers/
│   │       ├── bots.py                # Bot CRUD endpoints
│   │       └── templates.py           # Template endpoints (NEW!)
│   ├── .env                           # Environment variables (NOT in git)
│   ├── .env.example                   # Template for .env
│   ├── requirements.txt               # Python dependencies
│   └── trading_bot.db                 # SQLite database
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Bots.tsx               # Bot management (with templates!)
│   │   │   ├── Dashboard.tsx          # Main dashboard
│   │   │   ├── Positions.tsx          # Active deals
│   │   │   └── ...other pages
│   │   ├── services/api.ts            # API client (added templatesApi)
│   │   └── types.ts                   # TypeScript types
│   └── package.json
├── bot.sh                             # Start/stop/restart script
├── 3COMMAS_REPLACEMENT_CHECKLIST.md   # Feature progress tracker
└── HANDOFF_DOCUMENT.md                # This file

```

---

## 🚀 Setup on New Machine

### Prerequisites:
- Python 3.13
- Node.js 18+ and npm
- Git

### Step 1: Clone Repository
```bash
cd ~  # Or wherever you want the project
git clone <your-repo-url>  # Or copy the folder
cd GetRidOf3CommasBecauseTheyGoDownTooOften
```

### Step 2: Backend Setup
```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file from template
cp .env.example .env

# Edit .env and add your API keys:
# - COINBASE_API_KEY
# - COINBASE_API_SECRET (or CDP keys)
# - ANTHROPIC_API_KEY (for AI bot)
nano .env
```

### Step 3: Frontend Setup
```bash
cd ../frontend
npm install
```

### Step 4: Start Application
```bash
cd ..  # Back to root
./bot.sh start
# Backend: http://localhost:8000
# Frontend: http://localhost:5173
```

---

## 🔑 Required Environment Variables

### Backend `.env` File:
```bash
# Coinbase API (Legacy HMAC or CDP)
COINBASE_API_KEY=your_api_key_here
COINBASE_API_SECRET=your_api_secret_here

# OR use CDP API (preferred):
# COINBASE_CDP_KEY_NAME=organizations/xxx/apiKeys/xxx
# COINBASE_CDP_PRIVATE_KEY=-----BEGIN EC PRIVATE KEY-----\n...\n-----END EC PRIVATE KEY-----

# Anthropic API (for AI Autonomous Bot)
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Application Settings (can use defaults)
DATABASE_URL=sqlite+aiosqlite:///./trading_bot.db
SECRET_KEY=your-secret-key-change-this
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

**Get API Keys:**
- **Coinbase**: https://portal.cdp.coinbase.com/
- **Anthropic**: https://console.anthropic.com/

---

## 📊 Current Git Status

### Branch: `master`
All features merged and ready to use.

### Recent Commits (Latest First):
```
eea7918 - Add AI Autonomous Trading Bot powered by Claude AI
c8fcbac - Update checklist: mark bot templates as complete
f463d64 - Add bot templates system with default presets
d93e0e3 - Add budget splitting option for multi-pair bots
d777d5d - Add multi-pair bot UI with checkbox selection
b60675e - Update checklist: mark multi-pair bots and budget splitting as complete
d36e7b6 - Add Take Profit and Stop Loss lines to deal charts
```

### All Branches:
- `master` - Current stable (everything merged here)
- `multi-pair-backend` - Merged
- `multi-pair-ui` - Merged
- `bot-templates` - Merged
- `ai-autonomous-bot` - Merged

---

## 🗄️ Database Schema Updates

### New Tables:
- `bot_templates` - Stores bot configuration templates

### Modified Tables:
- `bots` - Added `product_ids` (JSON), `split_budget_across_pairs` (Boolean)
- `positions` - Already had `product_id` for pair tracking

### Auto-Migration:
SQLAlchemy creates tables automatically on startup (`Base.metadata.create_all`).

---

## 🤖 AI Autonomous Bot - Details

### Strategy ID: `ai_autonomous`

### How It Works:
1. Every 15 minutes (configurable 5-120min), fetches price data
2. Summarizes market metrics (price change, volatility, trends)
3. Calls Claude API with structured prompt
4. Claude returns JSON: `{action, confidence, reasoning, allocation_pct, expected_profit}`
5. Bot executes if confidence is high enough:
   - Buy: confidence ≥ 60%
   - Sell: confidence ≥ 70% AND profit ≥ minimum

### Token Optimization:
- Analysis caching (5min TTL)
- Summarized data (not raw candles)
- Configurable intervals
- Tracks token usage (logged)

### Configuration:
```json
{
  "market_focus": "BTC|USD|ALL",
  "initial_budget_percentage": 10.0,
  "max_position_size_percentage": 25.0,
  "risk_tolerance": "conservative|moderate|aggressive",
  "analysis_interval_minutes": 15,
  "min_profit_percentage": 1.0
}
```

### Safety Rules:
- ✅ Never sells at a loss (hard-coded)
- ✅ Only sells if profit ≥ min_profit_percentage
- ✅ Budget limits enforced
- ✅ Position size limits enforced

### Sentiment Analysis (Planned):
Framework is in place at `_get_sentiment_data()` method.
Ready to integrate:
- Twitter API (for crypto-related tweets)
- News APIs (CryptoCompare, NewsAPI)
- Reddit API (r/cryptocurrency sentiment)
- Fear & Greed index (Alternative.me)

Claude's prompt already handles sentiment data when provided.

---

## 📝 Available Strategies

1. **AI Autonomous** (`ai_autonomous`) - NEW! Claude-powered
2. **Conditional DCA** (`conditional_dca`) - Custom conditions per phase
3. **MACD DCA** (`macd_dca`) - MACD-based DCA
4. **RSI** (`rsi`) - RSI-based trading
5. **Bollinger Bands** (`bollinger`) - Bollinger Band strategy
6. **Simple DCA** (`simple_dca`) - Basic DCA
7. **Advanced DCA** (`advanced_dca`) - Advanced DCA

All registered in `backend/app/strategies/__init__.py`

---

## 🧪 Testing the AI Bot

### 1. Seed Default Templates (First Time):
```bash
curl -X POST http://localhost:8000/api/templates/seed-defaults
```

### 2. Create AI Bot via API:
```bash
curl -X POST http://localhost:8000/api/bots \
  -H "Content-Type: application/json" \
  -d '{
    "name": "AI Trader",
    "description": "Claude-powered autonomous bot",
    "strategy_type": "ai_autonomous",
    "product_ids": ["ETH-BTC"],
    "strategy_config": {
      "market_focus": "BTC",
      "initial_budget_percentage": 10.0,
      "max_position_size_percentage": 25.0,
      "risk_tolerance": "moderate",
      "analysis_interval_minutes": 15,
      "min_profit_percentage": 1.0
    }
  }'
```

### 3. Create via UI:
1. Go to http://localhost:5173
2. Navigate to "Bots" page
3. Click "Create New Bot"
4. Select strategy: "AI Autonomous Trading"
5. Configure parameters
6. Start bot

---

## 🔍 Important Files for AI Bot

### Backend:
- `backend/app/strategies/ai_autonomous.py` - Main strategy implementation
- `backend/app/strategies/__init__.py` - Strategy registration
- `backend/requirements.txt` - Added `anthropic==0.39.0`
- `backend/.env.example` - Added `ANTHROPIC_API_KEY` documentation

### Frontend:
Frontend automatically supports AI bot (fetches strategies from API).
No frontend changes needed - it's fully dynamic!

---

## 📚 Documentation Files

1. **3COMMAS_REPLACEMENT_CHECKLIST.md** - Feature progress tracker
   - Updated with AI bot details
   - Tracks all completed/planned features
   - Includes implementation notes

2. **HANDOFF_DOCUMENT.md** - This file
   - Complete setup guide
   - Current state snapshot
   - Migration instructions

3. **README.md** - Not created yet (TODO)

---

## 🐛 Known Issues / Notes

### 1. API Key Required for AI Bot
- AI bot requires `ANTHROPIC_API_KEY` in `.env`
- Gracefully handles missing key (shows error only when strategy is used)
- Other strategies work fine without it

### 2. Token Costs
- Claude API charges per token (input + output)
- Default config: 15min intervals = ~96 calls/day
- Estimated cost: ~$0.10-0.50/day per bot (depends on usage)
- Users can adjust `analysis_interval_minutes` to reduce costs

### 3. Multi-Pair Budget Splitting
- Default: Each pair gets full budget independently (3Commas style)
- Enable `split_budget_across_pairs` for safer allocation
- Example: 30% with 3 pairs = 10% per pair (split) vs 90% total (default)

### 4. Database Migrations
- Currently using SQLAlchemy's `create_all()` (auto-creates tables)
- No formal migration system (Alembic) yet
- For production, consider adding Alembic migrations

---

## 🎯 Next Steps / TODO

### Immediate (Ready to Implement):
1. **Trailing Take Profit / Stop Loss**
   - Dynamic TP that follows price upward
   - Implementation in trading engine
   - UI configuration

2. **Clone/Duplicate Bots**
   - Quick copy of existing bot configuration
   - Increment name automatically

3. **AI Bot Sentiment Integration**
   - Twitter API integration
   - News headline aggregation
   - Reddit sentiment analysis
   - Fear & Greed index

### Future Enhancements:
- Position notifications/alerts
- Performance analytics dashboard
- Backtesting system
- Multiple exchange support
- Mobile app (React Native)

---

## 🔧 Useful Commands

### Start/Stop/Restart:
```bash
./bot.sh start    # Start backend + frontend
./bot.sh stop     # Stop both
./bot.sh restart  # Restart both
./bot.sh status   # Check status
```

### Backend Only:
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Only:
```bash
cd frontend
npm run dev
```

### Database:
```bash
# View database (if sqlite3 installed)
sqlite3 backend/trading_bot.db

# Backup database
cp backend/trading_bot.db backend/trading_bot.db.backup
```

### Git:
```bash
# Check status
git status

# View recent commits
git log --oneline -10

# View changes
git diff

# Create new branch for feature
git checkout -b feature-name
```

---

## 📞 Support / Questions

### Documentation:
- **3Commas Checklist**: See `3COMMAS_REPLACEMENT_CHECKLIST.md`
- **Code Comments**: All strategies have detailed docstrings
- **API Docs**: http://localhost:8000/docs (FastAPI auto-docs)

### Debugging:
- **Backend Logs**: `tail -f .pids/backend.log`
- **Frontend Logs**: Browser console
- **Database**: Use SQLite browser or `sqlite3` CLI

---

## 🎓 Learning Resources

### FastAPI:
- https://fastapi.tiangolo.com/

### React Query:
- https://tanstack.com/query/latest/docs/framework/react/overview

### Anthropic Claude API:
- https://docs.anthropic.com/claude/reference/getting-started-with-the-api

### Coinbase Advanced Trade:
- https://docs.cdp.coinbase.com/advanced-trade/docs/welcome

---

## ✅ Migration Checklist

When moving to laptop:

- [ ] Copy entire project folder
- [ ] Install Python 3.13
- [ ] Install Node.js 18+
- [ ] Create backend venv: `python3 -m venv venv`
- [ ] Install backend deps: `pip install -r requirements.txt`
- [ ] Install frontend deps: `npm install`
- [ ] Copy `.env` file (or create new with API keys)
- [ ] Add Anthropic API key to `.env`
- [ ] Test backend: `./bot.sh start`
- [ ] Verify at http://localhost:5173
- [ ] Create test AI bot
- [ ] Verify strategies show up (should see 7 total)

---

## 🎉 Session Summary

### Features Completed:
1. ✅ Multi-Pair Bots (backend + frontend)
2. ✅ Budget Splitting Toggle
3. ✅ Bot Templates (3 default presets)
4. ✅ **AI Autonomous Trading Bot** (unique feature!)

### Lines of Code Added:
- Backend: ~500 lines (AI strategy)
- Frontend: ~150 lines (templates UI, multi-pair UI)
- Total: ~650 new lines

### Files Modified/Created:
- 11 files modified
- 2 files created (ai_autonomous.py, templates.py)

### Commits:
- 4 major commits
- All merged to master
- Clean history, ready for production

---

**End of Handoff Document**

*Last Updated: 2025-11-15*
*Ready for laptop migration ✅*
