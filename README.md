# ETH/BTC Trading Bot

A sophisticated automated trading bot for ETH/BTC on Coinbase with MACD-based DCA strategy, TradingView-style charts, and comprehensive position management.

## ✨ Key Features

### Trading & Strategy
- **MACD-Based Trading**: Automated buy/sell signals using MACD crossovers (works above AND below zero baseline)
- **DCA Strategy**: Dollar Cost Averaging into positions with configurable parameters
- **Profit Protection**: Minimum profit threshold ensures profitable exits (default 1%)
- **Position Limits**: Max BTC allocation per position (default 25% of balance)
- **Power Loss Recovery**: Automatic position recovery from database after restart

### Charts & Visualization
- **TradingView-Style Charts**: Professional candlestick charts with lightweight-charts library
- **Multiple Timeframes**: 1m, 5m, 15m, 30m, 1h, 2h, 6h, 1D intervals
- **Volume Indicator**: Toggle volume bars on/off
- **MACD Indicator**: Separate panel with MACD line, signal line, and histogram
- **Real-time Updates**: Live price and candle data from Coinbase

### Management & Control
- **GUI Configuration**: Manage API keys and all settings through web interface
- **Test Connection**: Verify Coinbase credentials before saving
- **Manual Controls**: Pause bot, cancel positions, or force close at market price
- **Position Tracking**: Track profits in both BTC and USD
- **Trade History**: Complete record of all buys and sells

### Technical
- **Persistence**: SQLite database survives restarts and power outages
- **Real-time Dashboard**: Monitor account value, positions, and market data
- **Management Script**: Simple `bot.sh` for start/stop/restart/status/logs
- **Production Ready**: Includes nginx config and systemd service files

## 🏗️ Architecture

- **Backend**: Python 3.13 + FastAPI + SQLAlchemy (async) + SQLite
- **Frontend**: React 18 + TypeScript + Vite + TanStack Query + Lightweight Charts
- **Exchange**: Coinbase Advanced Trade API
- **Deployment**: uvicorn + nginx + systemd

## 📋 Prerequisites

- **Python 3.13+**
- **Node.js 20+** and npm
- **Coinbase account** with API credentials
- **BTC and/or ETH** in your Coinbase account

## 🚀 Quick Start

### 1. Clone and Install

```bash
# Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install

# Return to project root
cd ..
```

### 2. Get Coinbase API Credentials

1. Go to https://www.coinbase.com/settings/api
2. Create a new API key with these permissions:
   - **View**: Read account balances and transaction history
   - **Trade**: Place buy and sell orders for ETH/BTC
3. Save your API Key and API Secret

### 3. Start the Bot

```bash
# Start both backend and frontend
./bot.sh start
```

### 4. Configure via Web UI

1. Open http://localhost:5173 in your browser
2. Go to **Settings**
3. Enter your Coinbase API Key and Secret
4. Click **Test Connection** to verify
5. Click **Save Settings**

### 5. Start Trading

1. Go to **Dashboard**
2. Review the TradingView-style chart
3. Adjust timeframe and indicators as desired
4. Click **Start Monitor** to begin automated trading

## 🎮 Using the Bot

### Management Script

```bash
./bot.sh start      # Start backend and frontend
./bot.sh stop       # Stop both services
./bot.sh restart    # Restart both services
./bot.sh status     # Check if running
./bot.sh logs       # View recent logs
```

### Dashboard (http://localhost:5173)

**Control Bar:**
- Monitor status indicator (running/stopped)
- Start/Stop monitor button
- Current ETH/BTC price

**Stats Cards:**
- Total positions completed
- Total profit in BTC
- Win rate percentage
- Current position details

**TradingView Chart:**
- Click timeframe buttons (1m to 1D)
- Toggle Volume indicator
- Toggle MACD indicator
- Interactive candlestick display

**Active Position Panel** (when position is open):
- Position details and profit
- **Cancel** button: Cancel position without selling
- **Force Close** button: Sell at current market price

### Position History (http://localhost:5173/positions)

View all completed positions with:
- Entry/exit prices and timestamps
- Total BTC spent and received
- Profit in BTC and USD
- Number of trades per position

### Settings (http://localhost:5173/settings)

**Coinbase API Credentials:**
- Enter API Key and Secret
- Test connection before saving
- Clear keys with confirmation

**Trading Parameters:**
- Initial BTC Percentage (default: 5%)
- DCA Percentage (default: 3%)
- Max BTC Usage (default: 25%)
- Minimum Profit % (default: 1%)

**MACD Indicator:**
- Candle Interval (1m to 1D)
- Fast Period (default: 12)
- Slow Period (default: 26)
- Signal Period (default: 9)

## 📊 Trading Strategy Explained

### MACD Signals

**Buy Signal (Cross-Up):**
- MACD line crosses above signal line
- Works regardless of position relative to zero baseline
- Opens new position OR adds to existing position (DCA)

**Sell Signal (Cross-Down):**
- MACD line crosses below signal line
- Only sells if profit ≥ minimum threshold
- Closes entire position

### DCA (Dollar Cost Averaging)

**Example with 1 BTC balance:**
1. MACD Cross-Up → Buy 0.05 BTC worth of ETH (5% initial)
2. Price drops, MACD Cross-Up → Buy 0.03 BTC more (3% DCA)
3. Price drops again, MACD Cross-Up → Buy 0.03 BTC more (3% DCA)
4. Price rises, profit > 1%, MACD Cross-Down → Sell all ETH

**Position Limits:**
- Maximum 25% of BTC balance per position
- Prevents over-allocation to single trade
- DCA buys stop when limit reached

### Choosing Timeframes

**Shorter (1m, 5m, 15m):**
- More signals, faster trades
- Good for volatile markets
- Higher transaction fees
- More false signals

**Longer (1h, 2h, 6h, 1D):**
- Fewer signals, longer trends
- Lower transaction fees
- Better for swing trading
- Fewer false signals

**Recommended:** Start with 5-15 minute intervals and adjust based on results.

## 🔄 Persistence & Recovery

### What Happens After Power Loss?

**Scenario:** Bot running with active position, power goes out for 2 weeks.

**On Restart:**
1. ✅ Loads active position from database
2. ✅ Reconnects to Coinbase
3. ✅ Resumes monitoring for signals
4. ✅ Maintains accurate profit calculations
5. ✅ Continues DCA strategy if applicable

**Database Stores:**
- All positions (open, closed, cancelled)
- Complete trade history with prices
- MACD signals and market data
- Profit in BTC and USD

**Manual Backup:**
```bash
cp backend/trading.db backend/trading.db.backup
cp backend/.env backend/.env.backup
```

## 🚀 Deployment to EC2

### Automated Deployment

```bash
# From your local machine
cd deployment
./deploy.sh your-ec2-ip your-key.pem
```

This script:
- Installs all dependencies
- Configures nginx and systemd
- Sets up the database
- Starts the services

### Manual Deployment

See [DOCUMENTATION.md](DOCUMENTATION.md) for detailed manual deployment instructions.

### Access Production Bot

```bash
# Via SSH tunnel (secure)
ssh -i your-key.pem -L 8080:localhost:80 ubuntu@your-ec2-ip

# Then open: http://localhost:8080
```

## 📖 Full Documentation

See [DOCUMENTATION.md](DOCUMENTATION.md) for:
- Complete API reference
- Detailed architecture
- Troubleshooting guide
- Development guide
- Security considerations

## 🔧 Configuration Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| **Coinbase API Key** | - | Your Coinbase API key |
| **Coinbase API Secret** | - | Your Coinbase API secret |
| **Initial BTC %** | 5.0% | BTC to spend on first buy |
| **DCA %** | 3.0% | BTC to spend on additional buys |
| **Max BTC Usage %** | 25.0% | Max BTC per position |
| **Min Profit %** | 1.0% | Min profit to sell |
| **Candle Interval** | 5 min | Timeframe for MACD |
| **MACD Fast** | 12 | Fast EMA period |
| **MACD Slow** | 26 | Slow EMA period |
| **MACD Signal** | 9 | Signal line period |

## 🐛 Troubleshooting

### Backend won't start

```bash
# Check logs
tail -f .pids/backend.log

# Common issues:
# - Missing API credentials (add in Settings)
# - Port 8000 already in use
# - Missing dependencies (run pip install -r requirements.txt)
```

### Chart not displaying

```bash
# Rebuild frontend
cd frontend
npm install
npm run dev
```

### Position not recovering

```bash
# Check database
sqlite3 backend/trading.db "SELECT * FROM positions WHERE status='open';"

# Check backend logs
tail -f .pids/backend.log
```

### MACD signals not triggering

- Ensure monitor is running (Dashboard shows "Running")
- Wait for 26+ candles to accumulate (MACD calculation requires history)
- Verify API credentials are valid
- Check backend logs for errors

## 🔒 Security Notes

- ⚠️ **Never commit `.env` file** to version control
- ⚠️ **Test with small amounts** first
- ⚠️ **Monitor regularly** for unexpected behavior
- ⚠️ **Use SSH tunnel** for remote access (not public internet)
- ⚠️ **Rotate API keys** periodically
- ⚠️ **Trading involves risk** - only invest what you can afford to lose

## 📝 Git Repository

This project uses git for version control:

```bash
# View status
git status

# Add changes
git add .

# Commit changes
git commit -m "Description"

# View history
git log --oneline
```

## 📄 License

Private use only.

## ⚠️ Disclaimer

**This software is for educational purposes only.**

Trading cryptocurrencies involves substantial risk of loss and is not suitable for every investor. Past performance is not indicative of future results. The authors are not responsible for any losses incurred. **Use at your own risk.**

---

🤖 **Generated with Claude Code**

For detailed documentation, see [DOCUMENTATION.md](DOCUMENTATION.md)

For quick start guide, see [QUICKSTART.md](QUICKSTART.md)
