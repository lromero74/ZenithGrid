# Quick Start Guide

## Automated Setup (Recommended)

The setup wizard handles everything:

```bash
git clone <your-repo-url>
cd ZenithGrid
python3 setup.py
```

The wizard will:
1. Display and require acceptance of the LICENSE
2. Create Python virtual environment and install dependencies
3. Install frontend Node.js dependencies
4. Initialize the SQLite database
5. Generate `.env` file with secure JWT secrets
6. Create your admin user account
7. Configure your Coinbase API credentials
8. Optionally install systemd/launchd services for auto-start
9. Start the services

**Access:** http://localhost:5173

---

## Manual Setup

### 1. Get Coinbase API Credentials

1. Go to https://portal.cdp.coinbase.com/
2. Create CDP API key with trade permissions
3. Save your API Key Name and Private Key

### 2. Setup Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Setup Frontend

```bash
cd frontend
npm install
```

### 4. Run the Application

```bash
# From project root
./bot.sh start
```

Or manually:

**Terminal 1 - Backend:**
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8100
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

**Access:** http://localhost:5173

### 5. First-Time Configuration

1. Log in with the credentials created during setup
2. Navigate to **Settings** to configure exchange credentials
3. Optionally add AI provider keys (Claude, GPT, Gemini, Grok, Groq)
4. Navigate to **Bots** and create your first bot

---

## Service Management

### Using bot.sh (development)

```bash
./bot.sh start      # Start backend + frontend
./bot.sh stop       # Stop both
./bot.sh restart    # Restart both
./bot.sh status     # Check status
./bot.sh logs       # View logs
```

### Using systemd (production / EC2)

```bash
sudo systemctl restart trading-bot-backend trading-bot-frontend
sudo journalctl -u trading-bot-backend -f   # Backend logs
sudo journalctl -u trading-bot-frontend -f  # Frontend logs
```

---

## Updating

```bash
python3 update.py          # Full update with prompts
python3 update.py --yes    # Auto-confirm (recommended for automation)
python3 update.py --preview  # Preview incoming changes first
```

---

## Key Features

- **6 Trading Strategies**: Indicator-Based (custom), Bull Flag Scanner, AI Spot Opinion, Triangular/Spatial/Statistical Arbitrage
- **Multi-AI Support**: Claude, GPT, Gemini, Grok, Groq
- **Multi-Pair Bots**: One bot trades multiple pairs simultaneously
- **Phase-Based Conditions**: Separate conditions for base order, safety orders, and take profit
- **Trailing TP/SL**: Follows price to maximize profits
- **Real-Time Dashboard**: Live P&L, portfolio value, market data
- **News Aggregation**: Multi-source crypto news with AI summaries

## Safety Tips

- Start with small amounts - test strategies with minimal capital
- Monitor regularly - check dashboard and AI reasoning logs
- Secure your keys - never share API credentials
- Use SSH tunnel or HTTPS for remote access
- Trading involves risk - only invest what you can afford to lose
